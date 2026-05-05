"""
Entity extraction service with document-type-aware entity filtering.
"""
from app.enums import DocumentType

TYPE_ENTITY_PRIORITY = {
    DocumentType.STORY: {"person", "location", "event", "work_of_art", "group"},
    DocumentType.ECOMMERCE: {"product", "money", "organization"},
    DocumentType.LAW: {"law", "organization", "date", "person"},
    DocumentType.FINANCE: {"money", "organization", "date", "percent"},
    DocumentType.MEDICAL: {"person", "organization", "date"},
    DocumentType.GENERAL: None,  # None = keep all types (default behavior)
}


def get_entity_filter(document_type: str | DocumentType) -> set[str] | None:
    """Get entity types to prioritize for a document type."""
    # Convert string to enum if necessary
    if isinstance(document_type, str):
        try:
            document_type = DocumentType(document_type)
        except ValueError:
            document_type = DocumentType.GENERAL

    return TYPE_ENTITY_PRIORITY.get(document_type, None)


def should_include_entity(document_type: str | DocumentType, entity_type: str) -> bool:
    """Check if an entity type should be included for the given document type."""
    entity_filter = get_entity_filter(document_type)
    if entity_filter is None:
        return True  # Keep all types for general/unknown types
    return entity_type in entity_filter
