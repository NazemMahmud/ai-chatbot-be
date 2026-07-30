# AI Chatbot Backend

A multi-tenant platform for building document-grounded AI chatbots (Retrieval-Augmented Generation). Organizations sign up, create bots, upload documents, and get a chatbot that answers strictly from those documents — reachable through a REST API, an embeddable JavaScript widget, and chat-channel integrations (Telegram / WhatsApp).

Under the hood it runs an asynchronous ingestion pipeline (parse → chunk → embed → store) and an advanced hybrid retrieval pipeline (vector + keyword search, Reciprocal Rank Fusion, cross-encoder reranking, and neighbour expansion) — not a naïve top-k cosine lookup.

Built with FastAPI, async SQLAlchemy 2.0, PostgreSQL + pgvector, a Redis-backed ARQ worker, and local LLM inference via Ollama. Storage, parsing, embedding, and chunking are all swappable behind service abstractions.

>NOTE: Don't follow it as a production ready solution. This will act as a guideline how to proceed to build an AI RAG-based Chatbot

## What this project demonstrates
For anyone who wants to check this as a work sample, the codebase shows:

* **Advanced RAG, done properly** — hybrid retrieval combining semantic (vector/pgvector) and lexical (Postgres `tsvector`) search, merged with Reciprocal Rank Fusion, re-scored by a cross-encoder reranker (FlashRank, ONNX — no PyTorch), then expanded with neighbouring chunks for context. History-aware query contextualization, semantic chunking, and optional multi-query rewriting and agentic retry-on-refusal are all implemented.
* **Async-first, decoupled processing** — FastAPI + async SQLAlchemy + `asyncpg` throughout; uploads return `202 Accepted` and heavy work is handed to a Redis-backed **ARQ** worker, so the API stays responsive and processing scales independently.
* **Multi-tenant SaaS architecture** — organizations, members, invitations, ownership transfers, soft-deletes, and a full **RBAC** layer (roles, permissions, permission checks).
* **Authentication & security** — JWT access tokens (PyJWT) with Argon2 password hashing (`pwdlib`), token records, and per-endpoint rate limiting.
* **Multiple delivery surfaces from one core** — REST API, a self-contained embeddable widget served from the backend, and a provider/facade layer for chat-channel integrations.
* **Production-shaped conventions** — a consistent `ApiResponse` envelope, centralized exception handling, Pydantic v2 validation, Alembic migrations, structured logging, and a DB-verifying health endpoint.

## Feature modules
| Module                | 	What it does                                                                                          |
|-----------------------|--------------------------------------------------------------------------------------------------------|
| Auth	                 | Sign-up (creates a user + organization), sign-in, sign-out, current-user — JWT + Argon2                |
| Organizations         | 	Create/manage orgs, ownership transfer, membership leave logs, soft-delete                            |
| Members & Invitations | 	Invite users, accept/decline, manage roles, remove members                                            |
| RBAC                  | 	Roles, permissions, role–permission mapping, permission checks on actions                             |
| Bots                  | 	CRUD for chatbots (name, description, per-bot system prompt)                                          |
| Documents             | 	Upload → async parse/chunk/embed pipeline; status polling; list/detail/delete                         |
| Chat                  | 	RAG chat with conversation memory and history-aware retrieval                                         |
| Widget                | 	Public per-bot config + chat endpoints and an embeddable chatbot.js bundle                            |
| Integrations          | 	Telegram / WhatsApp providers via a facade + webhook handlers (router present; currently not mounted) |

## Tech stack
| Layer               | 	Technology                                                |
|---------------------|------------------------------------------------------------|
| Language            | 	Python 3.11+                                              |
| Web framework       | 	FastAPI                                                   |
| ORM / DB access     | 	SQLAlchemy 2.0 (async) + asyncpg                          |
| Database            | 	PostgreSQL 16 + pgvector                                  |
| Migrations          | 	Alembic                                                   |
| Background jobs     | 	ARQ (Redis-backed)                                        |
| Embeddings / LLM    | 	Ollama (`nomic-embed-text`, 768-dim)                      |
| Reranking           | 	FlashRank cross-encoder (`ms-marco-MiniLM-L-12-v2`, ONNX) |
| Auth	               | 	PyJWT + `pwdlib[argon2]`                                  |
| Object storage      | 	Local filesystem or MinIO / S3                            |
| Validation / config | 	Pydantic v2 + pydantic-settings                           |
| Containers          | 	Docker Compose (Postgres, Redis, MinIO)                   |

## Supported file types
| Format                                             | 	Parser                                              |
|----------------------------------------------------|------------------------------------------------------|
| PDF, Word, TXT, Markdown, HTML, CSV                | 		`simple` (fast, text-only via pypdf / python-docx) |
| Scanned PDFs, images, tables, multi-column layouts | 	`docling` (heavier; OCR + layout, optional install) |

# Getting started
## Prerequisites

Install these before anything else. None of them go inside the Python virtual environment — they are standalone services.

### 1. Docker Desktop
Used to run PostgreSQL, Redis, and (optionally) MinIO. Ignore if you wanna use them locally
- Download: https://www.docker.com/products/docker-desktop/

### 2. Python 3.11+
```bash
python --version   # must be 3.11 or higher
```
Download: https://www.python.org/downloads/

### 3. Ollama
Used to run the embedding model locally. Ollama is a standalone application — do **not** `pip install` it and do **not** install it inside the virtual environment.

- **Windows**: Download installer from https://ollama.com/download
- **macOS**: `brew install ollama`
- **Linux**: `curl -fsSL https://ollama.com/install.sh | sh`

After installing, pull the required models:
```bash
# Embedding model (required — used during document processing)
ollama pull nomic-embed-text
```

Verify Ollama is running:
```bash
curl http://localhost:11434/api/tags
# Should return a JSON list of installed models
```

---

## Installation

### Step 1 — Clone the repository

```bash
git clone <repository-url>
cd ai-chatbot-be
```

### Step 2 — Create and activate a Python virtual environment

```bash
# Create the venv
python -m venv .venv

# Activate it:

# Windows (PowerShell)
.venv\Scripts\Activate.ps1

# Windows (git bash)
source .venv/Scripts/Activate

# Windows (CMD)
.venv\Scripts\activate.bat

# macOS / Linux
source .venv/bin/activate
```

You should see `(.venv)` at the start of your terminal prompt. **The venv must be activated in every terminal window you open.**

### Step 3 — Install Python dependencies

```bash
pip install -r requirements.txt
```

### Step 4 — Configure environment variables

```bash
# Copy the example env file
cp .env.example .env
```

Open `.env` in a text editor. For local development the defaults mostly work. Key decisions:

**Option A — Local file storage (simpler, no MinIO needed):**
```env
STORAGE_TYPE=local
STORAGE_LOCAL_PATH=./uploads
```

**Option B — MinIO storage (matches docker-compose.yml):**
```env
STORAGE_TYPE=minio
MINIO_ENDPOINT=localhost:9000
MINIO_ACCESS_KEY=minioadmin # this is sample, use your own value
MINIO_SECRET_KEY=minioadmin # this is sample, use your own value
MINIO_BUCKET=chatbot
```

Everything else can stay as the default for local development.

### Step 5 — Start infrastructure with Docker
Ignore if you wanna use local setup

```bash
docker-compose up -d
```

This starts three containers:
- **postgres** — PostgreSQL 16 with pgvector on port `5432`
- **redis** — Redis 7 on port `6379`
- **minio** — MinIO on port `9000` (API) + `9001` (web console). Skip if using `STORAGE_TYPE=local`

Check all containers are healthy:
```bash
docker-compose ps
```

All services should show `healthy` or `running`.

### Step 6 — Run database migrations

```bash
alembic upgrade head
```

Verify the tables were created:
```bash
docker exec -it $(docker-compose ps -q postgres) psql -U postgres -d chatbot -c "\dt"
```

Expected output:
```
              List of relations
 Schema |      Name       | Type  |  Owner
--------+-----------------+-------+----------
 public | alembic_version | table | postgres
 public | bots            | table | postgres
 public | document_bots   | table | postgres
 public | document_chunks | table | postgres
 public | documents       | table | postgres
```

Or, you can use dbeaver/phpmyadmin or similar to view database.
---

## Running the Application

You need **three terminal windows** open at the same time. Activate `.venv` in each one.

### Terminal 1 — FastAPI API server

```bash
uvicorn app.main:app --reload --port 8000
```

Available at:
- **API base URL**: `http://localhost:8000`
- **Swagger / interactive docs**: `http://localhost:8000/docs`
- **Health check**: `http://localhost:8000/health`

### Terminal 2 — ARQ background worker

```bash
arq app.workers.document_worker.WorkerSettings
```

This is needed for document parsing and learn after document upload. Run only when you need this. This process picks up document processing jobs from Redis and runs the full parse → chunk → embed → store pipeline. Without it, uploaded documents will stay in `pending` status forever.

Expected output on start:
```
INFO  Document worker starting...
```

### Terminal 3 — Ollama (if not already running)

```bash
ollama serve
```

On Windows, Ollama may already be running in the system tray after installation. You can verify:
```bash
curl http://localhost:11434/api/tags
```

---

### System

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/health` | Health check — returns DB connection status |

Full interactive documentation with request/response schemas is at `http://localhost:8000/docs`.

---

## Usage Examples

### 1. Create a bot

```bash
curl -X POST http://localhost:8000/api/bots \
  -H "Content-Type: application/json" \
  -d '{
    "name": "My Assistant",
    "description": "A helpful assistant trained on company documents"
  }'
```

Response:
```json
{
  "success": true,
  "message": "Bot created successfully",
  "data": {
    "id": "a1b2c3d4-e5f6-...",
    "name": "My Assistant",
    "is_active": true
  }
}
```

Save the `id` — you will need it when uploading documents.

### 2. Upload a document

```bash
curl -X POST http://localhost:8000/api/documents/upload \
  -F "data_file=@/path/to/your/document.pdf" \
  -F "parser_type=simple" \
  -F 'bot_ids=["a1b2c3d4-e5f6-..."]'
```

- `data_file` — the file to upload (PDF, DOCX, TXT, MD, HTML, CSV supported)
- `parser_type` — `"simple"` (fast, text-only) or `"docling"` (heavy, handles images/tables)
- `bot_ids` — JSON array of bot UUIDs to link the document to (optional)

Response (202 Accepted — processing starts in the background):
```json
{
  "success": true,
  "message": "Document accepted for processing",
  "data": {
    "id": "doc-uuid-...",
    "name": "document.pdf",
    "status": "pending",
    "chunk_count": 0
  }
}
```

### 3. Poll processing status

```bash
curl http://localhost:8000/api/documents/doc-uuid-.../status
```

| Status       | Meaning                                             |
|--------------|-----------------------------------------------------|
| `pending`    | Queued, waiting for the worker to pick it up        |
| `processing` | Worker is actively parsing, chunking, and embedding |
| `ready`      | Fully processed — searchable embeddings are stored  |
| `failed`     | Processing failed — check `error_message`           |

When ready:
```json
{
  "success": true,
  "data": {
    "status": "ready",
    "chunk_count": 12,
    "error_message": null
  }
}
```

### 4. List documents

```bash
# All documents for a specific bot
curl "http://localhost:8000/api/documents?bot_id=a1b2c3d4-...&status=ready"

# All documents regardless of bot
curl "http://localhost:8000/api/documents"
```

---

## Verifying Document Learning Worked

After a document reaches `status: ready`, you can verify the embeddings are correctly stored in the database:

```bash
# Connect to PostgreSQL inside the Docker container
docker exec -it $(docker-compose ps -q postgres) psql -U postgres -d chatbot
```

```sql
-- 1. Check document status and chunk count
SELECT name, status, chunk_count, error_message
FROM documents
ORDER BY created_at DESC
LIMIT 5;

-- 2. Preview chunks and confirm embeddings exist
SELECT
  (metadata->>'chunk_index')::int AS idx,
  LEFT(content, 80)               AS preview,
  vector_dims(embedding)          AS dims
FROM document_chunks
WHERE document_id = 'your-doc-uuid-here'
ORDER BY idx;
```

Expected output:
```
 idx | preview                                            | dims
-----+----------------------------------------------------+------
   0 | Machine learning is a subset of AI. It enables... |  768
   1 | ...enables computers to learn. Neural networks...  |  768
```

`dims = 768` confirms `nomic-embed-text` embeddings are stored correctly. The document is now ready to be used for vector similarity search (RAG chat).

---

## Configuration Reference

All settings are in `.env`. Defaults are suitable for local development.

| Variable              | Default                                                         | Description                                                |
|-----------------------|-----------------------------------------------------------------|------------------------------------------------------------|
| `APP_ENV`             | `development`                                                   | `development` or `production`                              |
| `DATABASE_URL`        | `postgresql+asyncpg://postgres:postgres@localhost:5432/chatbot` | PostgreSQL async connection string                         |
| `REDIS_URL`           | `redis://localhost:6379/0`                                      | Redis connection string                                    |
| `STORAGE_TYPE`        | `local`                                                         | `local` (files in `./uploads/`) or `minio`                 |
| `STORAGE_LOCAL_PATH`  | `./uploads`                                                     | Directory for local file storage                           |
| `MINIO_ENDPOINT`      | `localhost:9000`                                                | MinIO host:port                                            |
| `MINIO_ACCESS_KEY`    | `minioadmin`                                                    | MinIO access key                                           |
| `MINIO_SECRET_KEY`    | `minioadmin`                                                    | MinIO secret key                                           |
| `MINIO_BUCKET`        | `chatbot`                                                       | MinIO bucket name                                          |
| `OLLAMA_BASE_URL`     | `http://localhost:11434`                                        | Ollama server URL                                          |
| `OLLAMA_EMBED_MODEL`  | `nomic-embed-text`                                              | Embedding model (must match `EMBED_DIMENSIONS`)            |
| `OLLAMA_LLM_MODEL`    | `llama3.2:3b`                                                   | Chat LLM model                                             |
| `EMBED_DIMENSIONS`    | `768`                                                           | Embedding vector size — must match the model               |
| `DEFAULT_PARSER_TYPE` | `simple`                                                        | `simple` or `docling` — used when not specified per upload |
| `CHUNK_SIZE`          | `1000`                                                          | Max characters per text chunk                              |
| `CHUNK_OVERLAP`       | `200`                                                           | Overlap characters between consecutive chunks              |
| `WORKER_MAX_JOBS`     | `10`                                                            | Max concurrent background jobs per worker process          |
| `WORKER_JOB_TIMEOUT`  | `3600`                                                          | Max seconds a single job can run before timeout            |

---

## Troubleshooting

### Worker fails with `All connection attempts failed`

Ollama is not running or not reachable.

```bash
# Check if Ollama is running
curl http://localhost:11434/api/tags

# Start Ollama if it is not running
ollama serve

# Check if the embedding model is downloaded
ollama list
# Should show: nomic-embed-text

# Pull the model if missing
ollama pull nomic-embed-text
```

Then re-upload the document. Documents stuck in `failed` status will not retry automatically.

### Document stays in `pending` forever

The ARQ worker is not running. Open a terminal (with `.venv` activated) and run:

```bash
arq app.workers.document_worker.WorkerSettings
```

### `type "vector" does not exist`

The pgvector PostgreSQL extension was not enabled. Run:

```bash
alembic upgrade head
```

The first migration enables it automatically. See `docs/alembic-third-party-types.md` for details.

### `relation "documents" does not exist`

Migrations have not been applied. Run:

```bash
alembic upgrade head
```

### API starts but returns 500 on every request

Check the database connection in `.env`. Make sure the Docker containers are running:

```bash
docker-compose ps
docker-compose up -d   # restart if stopped
```

### Port already in use

```bash
# Windows — find what is using port 5432
netstat -ano | findstr :5432
taskkill /PID <pid> /F

# macOS / Linux
lsof -i :5432
kill <pid>

# Or simply restart Docker containers
docker-compose down && docker-compose up -d
```

### `ModuleNotFoundError` when starting API or worker

The virtual environment is not activated. Run the activation command for your OS:

```bash
# Windows PowerShell
.venv\Scripts\Activate.ps1

# macOS / Linux
source .venv/bin/activate
```