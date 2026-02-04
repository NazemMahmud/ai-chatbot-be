# Approach Guide — Document Learning & Chat System

## Current State

The project has a Streamlit prototype (`app.py`) using HuggingFace embeddings + Pinecone for vector storage. The target architecture (defined in PRD, TECH_STACK, DEVELOPMENT_GUIDE) moves to FastAPI + Nuxt 3 + Ollama + pgvector.

This guide covers two approaches:
1. **Backend (FastAPI)**: Document learning APIs + Query/Chat APIs + Database Query APIs
2. **Frontend (Vue/Nuxt)**: Document upload UI + DB connection UI + Chat UI

---

## Model Options & Alternatives

The system needs **three types of models**, all configurable via environment variables. Models are swappable — the pipeline stays the same, only the model name changes.

### Embedding Models (vectorize documents, web pages, DB content)

| Model | Params | Dims | Latency | Self-hosted | Best For |
|-------|--------|------|---------|-------------|----------|
| **e5-small** | 118M | 384 | ~16ms | Yes (free) | Fastest, beat all 7B+ models in Top-5 accuracy |
| **all-MiniLM-L6-v2** | 22M | 384 | <30ms | Yes (free) | Tiniest, good for prototyping |
| **nomic-embed-text** | 137M | 768 | ~30ms | Yes (Ollama) | Good default, easy Ollama install |
| **BGE-M3** | 568M | 1024 | <30ms | Yes (free) | Hybrid dense/sparse retrieval, multilingual |
| **mpnet-base-v2** | 110M | 768 | <30ms | Yes (free) | Solid general-purpose |

**Default recommendation**: `nomic-embed-text` for Ollama simplicity, or `e5-small` for speed.

### Chat/LLM Models (generate answers from retrieved context)

| Model | Params | VRAM | Speed | Quality | Ollama Support |
|-------|--------|------|-------|---------|----------------|
| **Qwen3-0.6B** | 0.6B | ~1GB | Very fast | Decent for simple Q&A | Yes |
| **Gemma-3n-E2B** | 5B (runs like 2B) | ~2GB | Fast | Good, multimodal | Yes |
| **llama3.2:3b** | 3B | 4GB | ~50 tok/s | 85/100 | Yes |
| **SmolLM3-3B** | 3B | ~3GB | Fast | Beats llama3.2:3b | Yes |
| **Phi-3 Mini** | 3.8B | ~4GB | Fast | Strong reasoning | Yes |
| **Mistral 7B** | 7B | ~5GB (Q4) | ~35 tok/s | Very good | Yes |
| **Qwen2.5:7b** | 7B | 8GB | ~30 tok/s | 92/100 | Yes |
| **Llama 3.1 8B** | 8B | ~4GB (Q4) | ~30 tok/s | Excellent for RAG | Yes |

**Default recommendation**: `SmolLM3-3B` (outperforms llama3.2:3b, 64K context). Upgrade to `Qwen2.5:7b` if 8GB VRAM available.

### Text-to-SQL Models (database connection feature)

| Model | Params | VRAM | Key Strength | Self-hosted |
|-------|--------|------|--------------|-------------|
| **Arctic-Text2SQL-R1-7B** | 7B | ~5GB (Q4) | SOTA on BIRD benchmark, beats GPT-4o | Yes |
| **Defog SQLCoder-7B-2** | 7B | ~5GB (Q4) | Mature, proven, runs on consumer HW | Yes |
| **PremSQL (prem-1B-SQL)** | 1B | ~1GB | Smallest viable Text2SQL model | Yes |

**Default recommendation**: `Arctic-Text2SQL-R1-7B` for accuracy, or `prem-1B-SQL` for minimal resources.

### Hardware Profiles (models only, not including infra)

| Profile | Embedding | Chat LLM | Text2SQL | Total VRAM |
|---------|-----------|----------|----------|------------|
| **Minimal** (8GB RAM) | e5-small | SmolLM3-3B (Q4) | prem-1B-SQL | ~3.5GB |
| **Balanced** (16GB RAM) | nomic-embed-text | Qwen2.5:7b (Q4) | Arctic-Text2SQL-R1-7B | ~11GB |
| **Quality** (24GB+ VRAM) | BGE-M3 | Llama 3.1 8B | Arctic-Text2SQL-R1-14B | ~22GB |

See **System Resource Requirements** section below for full calculation including Docker infra, Docling, and parallel execution.

---

## Model Installation for Development

### Option A: Ollama (recommended for chat + embedding models)

Ollama is the simplest way to run models locally. It manages downloads, quantization, and serving behind a single API.

```bash
# Install Ollama
curl -fsSL https://ollama.com/install.sh | sh
# Or on macOS: brew install ollama

# Start Ollama server (runs on http://localhost:11434)
ollama serve

# Pull embedding model (pick one)
ollama pull nomic-embed-text          # 768 dims, ~300MB — default
ollama pull all-minilm:l6-v2          # 384 dims, ~50MB — lightest

# Pull chat model (pick one)
ollama pull smollm3:3b                # ~2GB — recommended default
ollama pull llama3.2:3b               # ~2GB — previous default
ollama pull qwen2.5:7b                # ~4.5GB — better quality
ollama pull mistral:7b                # ~4GB — strong general purpose
ollama pull phi3:mini                 # ~2.3GB — good reasoning

# Pull text2sql model (if using DB feature)
ollama pull sqlcoder:7b               # ~4GB — Defog SQLCoder
```

**Via Docker (for docker-compose setup):**

```yaml
# docker/docker-compose.yml — ollama service
ollama:
  image: ollama/ollama
  ports:
    - "11434:11434"
  volumes:
    - ollama_data:/root/.ollama

# After container is up:
docker exec ollama ollama pull nomic-embed-text
docker exec ollama ollama pull smollm3:3b
docker exec ollama ollama pull sqlcoder:7b
```

**Verify installation:**

```bash
# Test chat model
curl http://localhost:11434/api/generate \
  -d '{"model": "smollm3:3b", "prompt": "Hello", "stream": false}'

# Test embedding model
curl http://localhost:11434/api/embeddings \
  -d '{"model": "nomic-embed-text", "prompt": "Hello world"}'

# List installed models
ollama list
```

### Option B: HuggingFace + Sentence-Transformers (for embedding models not on Ollama)

Some embedding models (e5-small, BGE-M3) are not available on Ollama. Use them directly via Python:

```bash
pip install sentence-transformers
```

```python
# backend/app/services/embedding.py — HuggingFace provider
from sentence_transformers import SentenceTransformer

# Model auto-downloads on first use to ~/.cache/huggingface/
model = SentenceTransformer("intfloat/e5-small-v2")      # 118M, 384 dims
# model = SentenceTransformer("BAAI/bge-m3")             # 568M, 1024 dims
# model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")  # 22M, 384 dims

embeddings = model.encode(["Hello world", "How are you"])
# Returns: numpy array of shape (2, 384)
```

### Option C: HuggingFace Transformers (for Text2SQL models not on Ollama)

Arctic-Text2SQL-R1-7B is available on HuggingFace but not on Ollama:

```bash
pip install transformers torch accelerate
```

```python
# backend/app/services/text2sql.py — HuggingFace provider
from transformers import AutoModelForCausalLM, AutoTokenizer

model_name = "Snowflake/Arctic-Text2SQL-R1-7B"
tokenizer = AutoTokenizer.from_pretrained(model_name)
model = AutoModelForCausalLM.from_pretrained(
    model_name,
    torch_dtype="auto",
    device_map="auto"       # auto-places on GPU if available
)
# Model auto-downloads on first use to ~/.cache/huggingface/ (~14GB)
```

### Option D: Pre-download Models for Offline/CI

```bash
# Pre-download HuggingFace models to a local directory
pip install huggingface_hub
huggingface-cli download intfloat/e5-small-v2 --local-dir ./models/e5-small
huggingface-cli download Snowflake/Arctic-Text2SQL-R1-7B --local-dir ./models/arctic-text2sql

# Then load from local path in code:
model = SentenceTransformer("./models/e5-small")
```

### How FastAPI Loads Models at Startup

```python
# backend/app/main.py
from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.config import settings

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load ML models once at startup, release on shutdown."""
    # Embedding model (HuggingFace path)
    if settings.EMBED_PROVIDER == "huggingface":
        from sentence_transformers import SentenceTransformer
        app.state.embed_model = SentenceTransformer(settings.EMBED_MODEL_NAME)

    # Text2SQL model (only if DB feature enabled)
    if settings.ENABLE_DB_CONNECTOR and settings.SQL_PROVIDER == "huggingface":
        from transformers import AutoModelForCausalLM, AutoTokenizer
        app.state.sql_tokenizer = AutoTokenizer.from_pretrained(settings.SQL_MODEL_NAME)
        app.state.sql_model = AutoModelForCausalLM.from_pretrained(
            settings.SQL_MODEL_NAME, torch_dtype="auto", device_map="auto"
        )

    yield  # app runs here

    # Cleanup on shutdown
    if hasattr(app.state, "embed_model"):
        del app.state.embed_model
    if hasattr(app.state, "sql_model"):
        del app.state.sql_model

app = FastAPI(lifespan=lifespan)
```

```python
# backend/app/config.py
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # --- Model Configuration ---

    # Embedding: "ollama" or "huggingface"
    EMBED_PROVIDER: str = "ollama"
    EMBED_MODEL_NAME: str = "nomic-embed-text"       # ollama model name or HF model ID
    EMBED_DIMENSIONS: int = 768                       # must match model output dims

    # Chat LLM: always via Ollama
    CHAT_MODEL_NAME: str = "smollm3:3b"
    CHAT_TEMPERATURE: float = 0.7

    # Text2SQL: "ollama" or "huggingface"
    ENABLE_DB_CONNECTOR: bool = False
    SQL_PROVIDER: str = "ollama"
    SQL_MODEL_NAME: str = "sqlcoder:7b"               # ollama model name or HF model ID

    # Ollama
    OLLAMA_BASE_URL: str = "http://localhost:11434"

    class Config:
        env_file = ".env"
```

---

## Approach 1: FastAPI Backend

The backend splits into **three distinct API groups**.

---

### Group A: Document Learning APIs (Ingestion Pipeline)

#### Step 1 — Project Scaffolding

```
backend/
├── app/
│   ├── main.py              # FastAPI app + CORS + model lifespan
│   ├── config.py            # pydantic-settings (env vars + model config)
│   ├── database.py          # async SQLAlchemy + pgvector session
│   ├── api/
│   │   ├── documents.py     # upload/status endpoints
│   │   ├── datasources.py   # database connection endpoints
│   ├── models/
│   │   ├── document.py      # documents + document_chunks tables
│   │   ├── datasource.py    # db_connections table
│   ├── schemas/
│   │   ├── document.py      # Pydantic request/response models
│   │   ├── datasource.py    # DB connection schemas
│   ├── services/
│   │   ├── document.py      # orchestrates parse → chunk → embed → store
│   │   ├── embedding.py     # multi-provider: Ollama or HuggingFace
│   │   ├── db_connector.py  # connect to external DBs, read schema+data
│   │   ├── text2sql.py      # natural language → SQL generation
│   ├── utils/
│   │   ├── parsers.py       # PDF, DOCX, TXT, HTML, MD, CSV extractors
│   │   ├── chunking.py      # sentence-aware text splitter
│   │   ├── scraper.py       # website/URL scraper
│   └── workers/
│       └── tasks.py         # ARQ background jobs
```

#### Step 2 — Infrastructure (Docker First)

- Spin up `pgvector/pgvector:pg16`, `redis:7-alpine`, `ollama/ollama`, `minio/minio` via `docker/docker-compose.yml`
- Pull models based on hardware profile:
  ```bash
  # Minimal
  ollama pull nomic-embed-text && ollama pull smollm3:3b

  # Balanced (add text2sql)
  ollama pull nomic-embed-text && ollama pull qwen2.5:7b && ollama pull sqlcoder:7b

  # Or use HuggingFace for embedding + text2sql (auto-downloads on first run)
  pip install sentence-transformers transformers torch
  ```
- Create DB with `CREATE EXTENSION vector;`

#### Step 3 — Database Models + Migrations

- Define `documents` table:
  - `id`, `bot_id`, `name`, `source_type` (file/url/text/database), `mime_type`, `status`, `file_path`, `chunk_count`
- Define `document_chunks` table:
  - `id`, `document_id`, `bot_id`, `content`, `metadata` (JSONB), `embedding` vector(N)
  - **N = configurable** via `EMBED_DIMENSIONS` env var (384 for e5-small, 768 for nomic, 1024 for BGE-M3)
- Define `db_connections` table (for database knowledge source):
  - `id`, `bot_id`, `name`, `db_type` (postgres/mysql/sqlite), `connection_string_encrypted`, `schema_cache` (JSONB), `status`, `last_synced_at`
- Create IVFFlat index on the embedding column
- Use Alembic for migrations

#### Step 4 — Document Parser (`utils/parsers.py`)

Two parser modes, selectable via `PARSER_TYPE` env var or per-request API parameter:

**Mode 1: `simple`** — Lightweight, text-only extraction (~170MB disk, ~200MB RAM)

| Parser | Library | Source |
|--------|---------|--------|
| `parse_pdf()` | pypdf | File upload |
| `parse_docx()` | python-docx | File upload |
| `parse_txt()` / `parse_md()` | plain read | File upload |
| `parse_html()` | beautifulsoup4 | File upload or URL scrape |
| `parse_csv()` | pandas | File upload |
| `parse_xlsx()` | openpyxl | File upload |

Limitations: cannot read images/scanned content, breaks table structure, no layout detection.

**Mode 2: `docling`** — Comprehensive, handles everything (~1.7GB disk, 3-4GB RAM spike)

| Capability | Supported |
|------------|-----------|
| Text extraction | Yes |
| Scanned/image PDFs (OCR) | Yes, built-in |
| Table structure preservation | Yes, 97.9% accuracy |
| Multi-column layout | Yes, reading order preserved |
| Formulas / code blocks | Yes |
| Multilingual | Yes, any language |
| Formats: PDF, DOCX, PPTX, XLSX, HTML, images | Yes, all in one |

```python
# backend/app/utils/parsers.py
from app.config import settings

def parse_document(file_path: str, mime_type: str, parser_type: str = None) -> str:
    """Parse any document to text. Parser selectable via param or env var."""
    use_parser = parser_type or settings.PARSER_TYPE

    if use_parser == "docling":
        from docling.document_converter import DocumentConverter
        converter = DocumentConverter()
        result = converter.convert(file_path)
        return result.document.export_to_markdown()
    else:
        # Simple mode — per-format parsers
        if mime_type == "application/pdf":
            return _parse_pdf(file_path)
        elif mime_type.endswith("wordprocessingml.document"):
            return _parse_docx(file_path)
        elif mime_type == "text/html":
            return _parse_html(file_path)
        elif mime_type in ("text/csv", "application/vnd.ms-excel"):
            return _parse_csv(file_path)
        else:
            return _parse_text(file_path)
```

The API upload endpoint accepts an optional `parser_type` parameter:

```
POST /api/bots/{bot_id}/documents/upload
  Body: multipart/form-data
  Fields:
    file: <binary>
    parser_type: "simple" | "docling"    ← optional, defaults to PARSER_TYPE env var
```

#### Step 5 — Chunking (`utils/chunking.py`)

- Sentence-aware splitting (512 tokens, 50 overlap)
- Returns list of `Chunk(text, metadata, start_index, end_index)`

#### Step 6 — Embedding Service (`services/embedding.py`)

Multi-provider embedding service — supports both Ollama and HuggingFace:

```python
# backend/app/services/embedding.py
import httpx
from app.config import settings

class EmbeddingService:
    def __init__(self, app_state=None):
        self.provider = settings.EMBED_PROVIDER

        if self.provider == "huggingface" and app_state:
            self.model = app_state.embed_model  # loaded at startup

    async def generate_embedding(self, text: str) -> list[float]:
        if self.provider == "ollama":
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{settings.OLLAMA_BASE_URL}/api/embeddings",
                    json={"model": settings.EMBED_MODEL_NAME, "prompt": text}
                )
                return response.json()["embedding"]
        else:
            return self.model.encode(text).tolist()

    async def generate_embeddings(self, texts: list[str], batch_size: int = 32) -> list[list[float]]:
        if self.provider == "huggingface":
            return self.model.encode(texts, batch_size=batch_size).tolist()
        else:
            # Ollama: batch via asyncio.gather
            import asyncio
            embeddings = []
            for i in range(0, len(texts), batch_size):
                batch = texts[i:i + batch_size]
                batch_results = await asyncio.gather(*[
                    self.generate_embedding(t) for t in batch
                ])
                embeddings.extend(batch_results)
            return embeddings
```

#### Step 7 — Document Processing Pipeline (`services/document.py`)

Core orchestrator flow:

```
download file → detect type → parse → chunk → embed → store in pgvector
```

Updates document status through lifecycle: `pending → processing → ready | failed`

#### Step 8 — Background Worker (`workers/tasks.py`)

- ARQ worker picks up `process_document_task(document_id)`
- Document processing is async/heavy — must not block the API
- Also handles `sync_database_task(db_connection_id)` for DB ingestion

#### Step 9 — API Endpoints (`api/documents.py`)

```
POST   /api/bots/{bot_id}/documents/upload     → accept multipart file, save to MinIO, enqueue ARQ job
POST   /api/bots/{bot_id}/documents/url        → accept URL, enqueue scrape+process job
GET    /api/bots/{bot_id}/documents             → list all documents with status
GET    /api/documents/{doc_id}/status           → poll processing status
DELETE /api/documents/{doc_id}                  → remove doc + its chunks
```

**Upload endpoint flow:**

1. Validate file type (PDF, DOCX, TXT, MD, HTML, CSV, XLSX)
2. Upload file to MinIO/S3
3. Create `documents` row with `status=pending`
4. Enqueue `process_document_task` via ARQ
5. Return `202 Accepted` with document ID + status

---

### Group B: Query/Chat APIs (RAG Retrieval)

Build this **after** Group A works end-to-end.

#### Step 1 — RAG Service (`services/rag.py`)

1. Embed user query via configured embedding model
2. Vector similarity search against `document_chunks` filtered by `bot_id`
3. Build prompt: system prompt + retrieved context + conversation history (last 10 messages)
4. Stream response from configured chat LLM

#### Step 2 — Chat API Endpoints (`api/chat.py`)

```
POST   /api/bots/{bot_id}/chat                 → streaming SSE response (authenticated/dashboard use)
GET    /api/bots/{bot_id}/conversations         → list conversations
GET    /api/conversations/{conv_id}/messages    → message history
```

#### Step 3 — Widget Public Endpoints (`api/widget.py`)

```
GET    /api/widget/{bot_id}/config              → bot name, welcome message, theme (public, no auth)
POST   /api/widget/{bot_id}/chat                → chat for widget users (session_id based, rate-limited)
```

**Key difference**: Dashboard chat uses JWT auth. Widget chat uses `session_id` + domain allowlist + rate limiting.

#### Step 4 — Streaming Implementation

- Use FastAPI `StreamingResponse` with `media_type="text/event-stream"`
- Ollama returns tokens via streaming — forward them as SSE chunks
- Final chunk includes `sources` (cited document names/snippets)

---

### Group C: Database Query APIs (Text-to-SQL)

Build this **after** Groups A and B. This is a separate knowledge source alongside documents and URLs.

#### Step 1 — DB Connector Service (`services/db_connector.py`)

Connects to external databases provided by the user, reads schema and data:

```python
# backend/app/services/db_connector.py
import sqlalchemy
from sqlalchemy import inspect, text

class DBConnector:
    SUPPORTED_DRIVERS = {
        "postgres": "postgresql+asyncpg",
        "mysql": "mysql+aiomysql",
        "sqlite": "sqlite+aiosqlite",
    }

    async def test_connection(self, db_type: str, connection_string: str) -> bool:
        """Verify the external DB is reachable."""
        driver = self.SUPPORTED_DRIVERS[db_type]
        engine = sqlalchemy.create_async_engine(f"{driver}://{connection_string}")
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True

    async def get_schema(self, db_type: str, connection_string: str) -> dict:
        """Extract table names, columns, types, relationships."""
        engine = sqlalchemy.create_engine(
            f"{self.SUPPORTED_DRIVERS[db_type].replace('+asyncpg','').replace('+aiomysql','').replace('+aiosqlite','')}://{connection_string}"
        )
        inspector = inspect(engine)
        schema = {}
        for table_name in inspector.get_table_names():
            columns = inspector.get_columns(table_name)
            schema[table_name] = [
                {"name": col["name"], "type": str(col["type"])}
                for col in columns
            ]
        return schema

    async def sync_to_chunks(self, db_connection_id: str, bot_id: str, db):
        """Read DB schema + sample data → create document chunks for RAG."""
        # 1. Get connection config
        # 2. Extract schema as text description
        # 3. Optionally sample rows for context
        # 4. Chunk schema descriptions
        # 5. Generate embeddings
        # 6. Store in document_chunks with source_type="database"
        pass
```

#### Step 2 — Text-to-SQL Service (`services/text2sql.py`)

When a user asks a question that needs live DB data (not just RAG context):

```python
# backend/app/services/text2sql.py
class Text2SQLService:
    async def generate_sql(self, question: str, schema: dict, db_type: str) -> str:
        """Convert natural language question to SQL query."""
        prompt = self._build_prompt(question, schema, db_type)

        if settings.SQL_PROVIDER == "ollama":
            # Call Ollama with sqlcoder model
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{settings.OLLAMA_BASE_URL}/api/generate",
                    json={"model": settings.SQL_MODEL_NAME, "prompt": prompt, "stream": False}
                )
                return self._extract_sql(response.json()["response"])
        else:
            # Use HuggingFace model loaded at startup
            # app.state.sql_model / app.state.sql_tokenizer
            pass

    async def execute_and_answer(self, question: str, db_connection, db) -> str:
        """Full flow: question → SQL → execute → natural language answer."""
        # 1. Generate SQL from question + schema
        # 2. Validate SQL (read-only, no mutations)
        # 3. Execute against external DB
        # 4. Format results
        # 5. Pass results + question to chat LLM for natural language answer
        pass
```

#### Step 3 — Database API Endpoints (`api/datasources.py`)

```
POST   /api/bots/{bot_id}/datasources              → add DB connection (encrypted)
GET    /api/bots/{bot_id}/datasources               → list connected databases
POST   /api/datasources/{ds_id}/test                → test connection
POST   /api/datasources/{ds_id}/sync                → sync schema + data to vector store
GET    /api/datasources/{ds_id}/schema              → view extracted schema
DELETE /api/datasources/{ds_id}                     → remove connection + its chunks
POST   /api/bots/{bot_id}/query-db                  → natural language → SQL → answer (live query)
```

**Two modes for database knowledge:**

1. **Sync mode (RAG)**: Schema + sample data are chunked and embedded into pgvector like any document. Questions are answered from vector search. Good for "what tables exist?" or "describe the users table".

2. **Live query mode (Text2SQL)**: User question is converted to SQL, executed against the connected DB in real-time, results are returned. Good for "how many orders were placed last month?" or "show me top 5 customers by revenue".

#### Step 4 — Security for DB Connections

- Connection strings encrypted at rest (AES-256 via `cryptography` library)
- Generated SQL is validated: only `SELECT` statements allowed, no `DROP/DELETE/UPDATE/INSERT`
- Query timeout enforced (5 seconds max)
- Row limit enforced (1000 rows max per query)

---

## Approach 2: Vue/Nuxt Frontend

### Project Structure

```
frontend/
├── pages/
│   ├── index.vue                        # landing/login
│   └── dashboard/
│       └── bots/
│           └── [id]/
│               ├── documents.vue        # document upload & management
│               ├── datasources.vue      # database connections
│               └── chat.vue             # chat interface
├── components/
│   ├── documents/
│   │   ├── DocumentUploader.vue         # drag-drop + file picker
│   │   ├── DocumentList.vue             # list with status badges
│   │   └── DocumentStatusBadge.vue      # pending/processing/ready/failed
│   ├── datasources/
│   │   ├── AddDatabaseForm.vue          # DB type, host, port, credentials
│   │   ├── DatasourceList.vue           # connected DBs with sync status
│   │   └── SchemaViewer.vue             # view extracted schema
│   └── chat/
│       ├── ChatWindow.vue
│       ├── MessageBubble.vue
│       └── ChatInput.vue
├── composables/
│   ├── useDocuments.ts                  # API calls for document CRUD
│   ├── useDatasources.ts               # API calls for DB connections
│   ├── useChat.ts                       # API calls + SSE streaming
│   └── useApi.ts                        # base fetch wrapper with auth
├── stores/
│   ├── documents.ts                     # Pinia store for document state
│   ├── datasources.ts                   # Pinia store for DB connections
│   └── chat.ts                          # Pinia store for messages
├── nuxt.config.ts
```

---

### Phase A: Document Upload Interface

#### Step 1 — Nuxt 3 Project Setup

- Initialize with `npx nuxi init frontend`
- Install dependencies: `@nuxt/ui`, `@pinia/nuxt`, `@vueuse/nuxt`, `@nuxtjs/tailwindcss`
- Configure `nuxt.config.ts` with API proxy to backend (`http://localhost:8000`)

#### Step 2 — `DocumentUploader.vue` Component

- Drag-and-drop zone + file input button
- Accepted types: `.pdf`, `.docx`, `.txt`, `.md`, `.html`, `.csv`, `.xlsx`, `.pptx`, images
- Parser toggle: radio/dropdown to choose `simple` or `docling` (defaults to env var)
  - Show helper text: "Simple: fast, text-only" / "Docling: slower, handles images, tables, scanned docs"
- On file select:
  - `POST /api/bots/{botId}/documents/upload` as `multipart/form-data` with `parser_type` field
  - Show upload progress bar
  - On success (202) → add to document list with `status: pending`

#### Step 3 — `DocumentList.vue` + Status Polling

- Fetch `GET /api/bots/{botId}/documents` on mount
- For documents with `status: pending | processing`:
  - Poll `GET /api/documents/{docId}/status` every 3–5 seconds
- Display status badge:
  - `pending` → yellow
  - `processing` → blue spinner
  - `ready` → green
  - `failed` → red
- Delete button per document → `DELETE /api/documents/{docId}`

#### Step 4 — `useDocuments.ts` Composable

```ts
export function useDocuments(botId: string) {
  const uploadDocument = (file: File) => { /* POST multipart */ }
  const listDocuments = () => { /* GET list */ }
  const pollStatus = (docId: string) => { /* GET status with interval */ }
  const deleteDocument = (docId: string) => { /* DELETE */ }
  return { uploadDocument, listDocuments, pollStatus, deleteDocument }
}
```

---

### Phase B: Database Connection Interface

#### Step 5 — `AddDatabaseForm.vue`

- Form fields: DB type (dropdown: PostgreSQL/MySQL/SQLite), host, port, database name, username, password
- "Test Connection" button → `POST /api/datasources/{dsId}/test`
- "Save & Sync" button → saves connection + triggers schema sync

#### Step 6 — `DatasourceList.vue`

- List connected databases with sync status
- "Re-sync" button per datasource → `POST /api/datasources/{dsId}/sync`
- "View Schema" expand → shows tables/columns from `SchemaViewer.vue`
- Delete button → `DELETE /api/datasources/{dsId}`

#### Step 7 — `useDatasources.ts` Composable

```ts
export function useDatasources(botId: string) {
  const addDatasource = (config: DBConfig) => { /* POST */ }
  const listDatasources = () => { /* GET list */ }
  const testConnection = (dsId: string) => { /* POST test */ }
  const syncDatasource = (dsId: string) => { /* POST sync */ }
  const getSchema = (dsId: string) => { /* GET schema */ }
  const deleteDatasource = (dsId: string) => { /* DELETE */ }
  return { addDatasource, listDatasources, testConnection, syncDatasource, getSchema, deleteDatasource }
}
```

---

### Phase C: Chat Interface (Question & Answer)

#### Step 8 — `ChatWindow.vue`

- Scrollable message list with auto-scroll to bottom
- Input box at the bottom
- Each `MessageBubble` shows role (user/assistant) + content + optional sources
- Assistant messages render incrementally (streaming)
- Source badges show if answer came from document, URL, or database

#### Step 9 — `useChat.ts` Composable with SSE Streaming

```ts
export function useChat(botId: string) {
  const messages = ref<Message[]>([])

  async function sendMessage(content: string) {
    messages.value.push({ role: 'user', content })
    messages.value.push({ role: 'assistant', content: '' })  // placeholder

    const response = await fetch(`/api/bots/${botId}/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        message: content,
        history: messages.value.slice(-10)
      })
    })

    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    const lastIdx = messages.value.length - 1

    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      messages.value[lastIdx].content += decoder.decode(value)
    }
  }

  return { messages, sendMessage }
}
```

#### Step 10 — Wire Pages

- `pages/dashboard/bots/[id]/documents.vue` → uses `DocumentUploader` + `DocumentList`
- `pages/dashboard/bots/[id]/datasources.vue` → uses `AddDatabaseForm` + `DatasourceList`
- `pages/dashboard/bots/[id]/chat.vue` → uses `ChatWindow`
- All pages share the bot context via route param `[id]`

---

## Recommended Build Sequence

| Order | What | Where |
|-------|------|-------|
| 1 | Docker infra + pull models + DB schema + Alembic migrations | Backend |
| 2 | File parsers + chunking + multi-provider embedding service | Backend |
| 3 | Document upload API + ARQ worker pipeline | Backend |
| 4 | Test: upload a PDF → verify chunks + embeddings in pgvector | Backend |
| 5 | RAG service + Chat streaming API | Backend |
| 6 | Test: query via curl/httpie → get streamed answer with sources | Backend |
| 7 | Nuxt project setup + document upload UI | Frontend |
| 8 | Connect upload UI → backend, verify status polling works | Full stack |
| 9 | Chat UI with streaming | Frontend |
| 10 | Connect chat UI → backend, verify end-to-end Q&A | Full stack |
| 11 | DB connector service + Text2SQL service | Backend |
| 12 | Database connection API endpoints | Backend |
| 13 | Test: connect to a test DB → sync schema → ask question | Backend |
| 14 | Database connection UI + schema viewer | Frontend |
| 15 | Connect datasource UI → backend, verify sync + live query | Full stack |

---

## System Resource Requirements

### Parallel Execution Scenarios

All these processes can run **at the same time**:

```
ALWAYS RUNNING:
  FastAPI server              → ~200 MB RAM
  ARQ worker                  → ~200 MB RAM
  PostgreSQL + pgvector       → ~200-500 MB RAM
  Redis                       → ~50 MB RAM
  MinIO                       → ~100 MB RAM
  Nuxt dev server (dev only)  → ~300 MB RAM
  ─────────────────────────────────
  Base overhead:              ~1-1.5 GB RAM

ON DEMAND (can overlap):
  Ollama: embedding model     → 300 MB - 1 GB (stays loaded ~5 min after use)
  Ollama: chat LLM            → 2-8 GB (stays loaded ~5 min after use)
  Ollama: text2sql model      → 1-5 GB (loaded only for DB queries)
  Docling (in ARQ worker)     → 3-4 GB spike (only during document parsing)
```

**Worst case**: User A uploads a PDF (Docling spike + embedding) while User B chats (chat LLM) while User C queries a database (text2sql model). All three Ollama models loaded + Docling active.

**Typical case**: Document processing and chat don't happen at the exact same second. Ollama unloads idle models after ~5 minutes. Docling spike is brief (seconds to minutes per document).

### Local Development (Your PC)

| Profile | RAM | Disk | GPU | Parser | DB feature | What works |
|---------|-----|------|-----|--------|------------|------------|
| **Lite** | **8 GB** | ~8 GB | None | simple | No | Upload text docs, chat |
| **Standard** | **16 GB** | ~12 GB | None | docling | No | Upload any docs (images, tables), chat |
| **Full** | **32 GB** | ~20 GB | Optional | docling | Yes | Everything including DB queries |

**Lite breakdown (8 GB RAM):**
```
Base infra:                      ~1 GB
Ollama (embed + chat, swapped):  ~3 GB peak (only one model loaded at a time)
FastAPI + worker:                ~400 MB
Nuxt dev:                        ~300 MB
═══════════════════════════════════════
Peak:                            ~5 GB
Free for OS/browser:             ~3 GB ✓
```

**Standard breakdown (16 GB RAM):**
```
Base infra:                      ~1 GB
Ollama (embed loaded):           ~300 MB
Ollama (chat LLM on request):   ~3 GB
Docling (during parsing spike):  ~4 GB  ← temporary, in worker process
FastAPI + worker:                ~400 MB
Nuxt dev:                        ~300 MB
═══════════════════════════════════════
Peak (parsing + chat overlap):   ~9 GB
Free for OS/browser:             ~7 GB ✓
```

**Full breakdown (32 GB RAM):**
```
Base infra:                      ~1 GB
Ollama (embed loaded):           ~300 MB
Ollama (chat qwen2.5:7b):       ~5 GB
Ollama (sqlcoder:7b, overlap):   ~5 GB   ← if DB query during chat
Docling (during parsing spike):  ~4 GB   ← if parsing during chat
FastAPI + worker:                ~400 MB
Nuxt dev:                        ~300 MB
═══════════════════════════════════════
Worst case (all simultaneous):   ~16 GB
Free for OS/browser:             ~16 GB ✓
With GPU (8GB+ VRAM):            Ollama offloads to GPU, frees ~8 GB RAM
```

### Disk Space Breakdown

```
Docker images:
  pgvector/pgvector:pg16         → ~400 MB
  redis:7-alpine                 → ~30 MB
  minio/minio                    → ~200 MB
  ollama/ollama                  → ~800 MB
  ─────────────────────────────────
  Docker total:                  ~1.4 GB

Ollama models (in ~/.ollama or Docker volume):
  nomic-embed-text               → ~300 MB
  smollm3:3b                     → ~2 GB
  sqlcoder:7b (optional)         → ~4 GB
  qwen2.5:7b (optional)         → ~4.5 GB
  ─────────────────────────────────
  Models total:                  ~2.3 - 11 GB (depends on choices)

Python packages:
  Simple parsers only            → ~170 MB
  + Docling (CPU-only)           → ~1.7 GB
  + sentence-transformers        → ~500 MB
  + transformers + torch (HF)    → ~2-3 GB
  ─────────────────────────────────
  Python total:                  ~170 MB - 5 GB (depends on features)

Node.js:
  Frontend (node_modules)        → ~300 MB
  Widget (node_modules)          → ~100 MB
  ─────────────────────────────────
  Node total:                    ~400 MB

PostgreSQL data:                 → grows with usage (~100 MB per 100K chunks)
MinIO data:                      → grows with uploads (original files stored)
```

**Total disk by profile:**

| Profile | Docker | Models | Python | Node | Total |
|---------|--------|--------|--------|------|-------|
| Lite | 1.4 GB | 2.3 GB | 170 MB | 400 MB | **~4.5 GB** |
| Standard | 1.4 GB | 2.3 GB | 2 GB | 400 MB | **~6 GB** |
| Full | 1.4 GB | 7 GB | 4 GB | 400 MB | **~13 GB** |
| Full + all model options | 1.4 GB | 11 GB | 5 GB | 400 MB | **~18 GB** |

### Production Server

| Tier | Spec | Monthly cost (Hetzner) | RAM headroom | Features |
|------|------|----------------------|-------------|----------|
| **Small** | 4 vCPU, 16 GB RAM, 80 GB SSD | ~$15/mo | Tight | Simple parser, basic chat, no DB |
| **Medium** | 8 vCPU, 32 GB RAM, 240 GB SSD | ~$30/mo | Comfortable | Docling + chat + DB connector |
| **GPU** | 8 vCPU, 32 GB RAM, RTX 3060 12GB | ~$80-150/mo | Plenty | All features, fast inference |

On production, the Nuxt frontend is pre-built (no dev server overhead), and Docling processing runs in isolated worker containers that can be scaled independently.

---

## Key Architectural Notes

| Change | From (Prototype) | To (New Architecture) |
|--------|-------------------|----------------------|
| Vector DB | Pinecone (external) | pgvector (self-hosted PostgreSQL) |
| LLM/Embeddings | HuggingFace API | Ollama + HuggingFace (self-hosted, configurable) |
| Embedding Model | `all-MiniLM-L6-v2` (hardcoded) | Configurable: `nomic-embed-text`, `e5-small`, `BGE-M3` |
| Chat Model | None | Configurable: `SmolLM3-3B`, `Qwen2.5:7b`, `llama3.2:3b` |
| Text2SQL Model | None | Configurable: `sqlcoder:7b`, `Arctic-Text2SQL-R1-7B` |
| Document Parser | None (basic web scrape) | Dual mode: `simple` (pypdf/docx) or `docling` (IBM, handles images/tables/multilingual) |
| Knowledge Sources | Website scraping only | Documents + URLs + Database connections |
| Processing | Synchronous (Streamlit) | Async background jobs via ARQ |
| Frontend | Streamlit | Nuxt 3 + TailwindCSS |
| API | None | FastAPI with REST endpoints |
| File Storage | None | MinIO (dev) / S3 (prod) |

- **Bot-scoped everything** — documents, chunks, datasources, and conversations are all filtered by `bot_id`
- **Models are swappable** — change a single env var to switch models, no code changes needed
- **Parser is selectable per request** — API accepts `parser_type` parameter, defaults to `PARSER_TYPE` env var
- **Embedding dimension is configurable** — `EMBED_DIMENSIONS` env var drives the pgvector column size via Alembic migration
- **Streaming is essential** — both the chat API and the frontend must handle SSE/chunked responses
- **Text2SQL is isolated** — loaded on demand, only when `ENABLE_DB_CONNECTOR=true`, doesn't consume VRAM otherwise
- **Docling runs in worker, not API process** — the 3-4GB RAM spike during parsing happens in the ARQ background worker, isolated from the main API serving chat requests


-------

Last addition:
All four docs are updated. Here's a summary of what changed and the direct answer to your
  questions:

  ---
  Resource requirements — the short answer

  For your local PC (development):
  ┌──────────────────────────────────────────────────┬────────────┬─────────────┐
  │               What you want to run               │ RAM needed │ Disk needed │
  ├──────────────────────────────────────────────────┼────────────┼─────────────┤
  │ Basic (text docs + chat only)                    │ 8 GB       │ ~4.5 GB     │
  ├──────────────────────────────────────────────────┼────────────┼─────────────┤
  │ With Docling (images/tables/scanned docs)        │ 16 GB      │ ~6 GB       │
  ├──────────────────────────────────────────────────┼────────────┼─────────────┤
  │ Everything (Docling + DB connector + all models) │ 32 GB      │ ~13-18 GB   │
  └──────────────────────────────────────────────────┴────────────┴─────────────┘
  For production server:
  ┌────────┬─────────────────────────┬──────────┐
  │  Tier  │          Spec           │ ~Cost/mo │
  ├────────┼─────────────────────────┼──────────┤
  │ Small  │ 4 vCPU, 16 GB RAM       │ ~$15     │
  ├────────┼─────────────────────────┼──────────┤
  │ Medium │ 8 vCPU, 32 GB RAM       │ ~$30     │
  ├────────┼─────────────────────────┼──────────┤
  │ GPU    │ 8 vCPU, 32 GB, RTX 3060 │ ~$80-150 │
  └────────┴─────────────────────────┴──────────┘
  Parallel execution — what actually happens

  Ollama keeps a model loaded for ~5 minutes after its last use, then unloads it. So if a
  chat request and a DB query happen within the same 5-minute window, both the chat LLM
  (~3-5GB) and text2sql model (~5GB) are in memory simultaneously. Add Docling processing a
  document at the same time (~4GB spike), and that's the worst case.

  In practice on 16GB RAM, this rarely happens — documents process in seconds/minutes and the
   spike is temporary in the ARQ worker process. The 16GB profile handles typical dev usage
  comfortably.

  Files updated

  - APPROACH_GUIDE.md — Added dual-parser code with per-request parser_type parameter, full
  resource breakdown for all parallel scenarios (3 profiles: lite/standard/full), disk space
  calculation, production server tiers, upload UI parser toggle
  - DEVELOPMENT_GUIDE.md — Env vars updated with PARSER_TYPE=simple|docling, added full
  System Resource Requirements section with parallel execution diagram and all three profiles
  - PRD.md — Tech stack table now includes Doc Parser row
  - TECH_STACK.md — Backend layer updated, requirements.txt includes Docling install
  instructions with CPU-only flag
