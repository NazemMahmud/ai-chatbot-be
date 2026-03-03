"""
Entity Extraction Service - Extracts named entities from text using spaCy NER.

Runs at index time (during document processing) to build the document_entities
table. This makes exhaustive queries like "list ALL characters/people/companies"
deterministic and 100% complete — no LLM guessing required.

Model: en_core_web_sm (~15MB, fast, CPU-only)
Speed: ~2-5 seconds for 400 chunks
Entity types extracted: PERSON, ORG, GPE (places), LOC, DATE, MONEY, PRODUCT, EVENT, etc.
"""
import logging
from collections import Counter

logger = logging.getLogger(__name__)

# Lazy-loaded spaCy model singleton
_nlp = None


# Map spaCy entity labels to simpler, user-friendly types
ENTITY_TYPE_MAP = {
    "PERSON": "person",
    "ORG": "organization",
    "GPE": "location",       # geopolitical entity (countries, cities)
    "LOC": "location",       # non-GPE locations (mountains, rivers)
    "FAC": "location",       # facilities (buildings, airports)
    "DATE": "date",
    "TIME": "time",
    "MONEY": "money",
    "PERCENT": "percent",
    "PRODUCT": "product",
    "EVENT": "event",
    "WORK_OF_ART": "work_of_art",
    "LAW": "law",
    "LANGUAGE": "language",
    "NORP": "group",          # nationalities, religious/political groups
    "QUANTITY": "quantity",
    "ORDINAL": "ordinal",
    "CARDINAL": "number",
}

# Entity types worth storing (skip noisy ones like ordinals, numbers)
KEEP_TYPES = {
    "person", "organization", "location", "date", "money",
    "product", "event", "work_of_art", "law", "group",
}


def _get_nlp():
    """Lazy-load spaCy model (singleton)."""
    global _nlp
    if _nlp is None:
        try:
            import spacy
            _nlp = spacy.load("en_core_web_sm")
            logger.info("[NER] spaCy model loaded (en_core_web_sm)")
        except ImportError:
            logger.warning(
                "[NER] spaCy not installed. Entity extraction disabled. "
                "Install with: pip install spacy && python -m spacy download en_core_web_sm"
            )
            return None
        except OSError:
            logger.warning(
                "[NER] spaCy model not found. Download with: "
                "python -m spacy download en_core_web_sm"
            )
            return None
    return _nlp


def extract_entities(text: str) -> list[dict]:
    """
    Extract named entities from a single text chunk.

    Args:
        text: Chunk content

    Returns:
        List of dicts: {"type": str, "value": str, "count": int, "snippet": str}
    """
    nlp = _get_nlp()
    if nlp is None:
        return []

    try:
        doc = nlp(text)

        # Count each (type, value) pair
        entity_counts: Counter = Counter()
        entity_snippets: dict[tuple[str, str], str] = {}

        for ent in doc.ents:
            mapped_type = ENTITY_TYPE_MAP.get(ent.label_)
            if mapped_type not in KEEP_TYPES:
                continue

            # Normalize: strip whitespace, skip very short entities
            value = ent.text.strip()
            if len(value) < 2:
                continue

            key = (mapped_type, value)
            entity_counts[key] += 1

            # Store first snippet for this entity
            if key not in entity_snippets:
                start = max(0, ent.start_char - 60)
                end = min(len(text), ent.end_char + 60)
                entity_snippets[key] = text[start:end].strip()

        return [
            {
                "type": etype,
                "value": evalue,
                "count": count,
                "snippet": entity_snippets.get((etype, evalue), ""),
            }
            for (etype, evalue), count in entity_counts.items()
        ]

    except Exception as e:
        logger.error(f"[NER] Entity extraction failed: {e}")
        return []


def extract_entities_batch(chunks: list[str]) -> list[list[dict]]:
    """
    Extract entities from multiple chunks efficiently using spaCy's pipe.

    Args:
        chunks: List of chunk content strings

    Returns:
        List of entity lists (one per chunk, same order as input)
    """
    nlp = _get_nlp()
    if nlp is None:
        return [[] for _ in chunks]

    try:
        results = []
        # spaCy's pipe is much faster for batch processing
        for doc in nlp.pipe(chunks, batch_size=50):
            entity_counts: Counter = Counter()
            entity_snippets: dict[tuple[str, str], str] = {}

            for ent in doc.ents:
                mapped_type = ENTITY_TYPE_MAP.get(ent.label_)
                if mapped_type not in KEEP_TYPES:
                    continue

                value = ent.text.strip()
                if len(value) < 2:
                    continue

                key = (mapped_type, value)
                entity_counts[key] += 1

                if key not in entity_snippets:
                    start = max(0, ent.start_char - 60)
                    end = min(len(doc.text), ent.end_char + 60)
                    entity_snippets[key] = doc.text[start:end].strip()

            chunk_entities = [
                {
                    "type": etype,
                    "value": evalue,
                    "count": count,
                    "snippet": entity_snippets.get((etype, evalue), ""),
                }
                for (etype, evalue), count in entity_counts.items()
            ]
            results.append(chunk_entities)

        logger.info(f"[NER] Extracted entities from {len(chunks)} chunks")
        return results

    except Exception as e:
        logger.error(f"[NER] Batch entity extraction failed: {e}")
        return [[] for _ in chunks]
