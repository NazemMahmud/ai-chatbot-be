# Feature 1: Document Upload → Parse → Learn

## Complete Testing Guide

This guide walks you through testing the document processing pipeline.

---

## Prerequisites Setup

### 1. Install Dependencies

```bash
cd C:\Piash\Project\Parse\Parse\ai-chatbot-be

# Create virtual environment (if not exists)
python -m venv .venv

# Activate virtual environment
# Windows:
.venv\Scripts\activate
# Linux/Mac:
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Start Docker Services

```bash
# Start PostgreSQL (pgvector) and Redis
docker-compose up -d postgres redis

# Verify services are running
docker ps
```

### 3. Install and Start Ollama

```bash
# Download Ollama from https://ollama.ai
# Then pull the embedding model:
ollama pull nomic-embed-text

# Verify it's running:
curl http://localhost:11434/api/tags
```

### 4. Run Database Migrations

```bash
# Create initial migration (if tables don't exist)
alembic revision --autogenerate -m "Initial tables"

# Apply migrations
alembic upgrade head
```

---

## Running the Application

### Terminal 1: Start FastAPI Server

```bash
cd C:\Piash\Project\Parse\Parse\ai-chatbot-be
.venv\Scripts\activate  # Windows
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Terminal 2: Start ARQ Worker

```bash
cd C:\Piash\Project\Parse\Parse\ai-chatbot-be
.venv\Scripts\activate  # Windows
arq app.workers.document_worker.WorkerSettings
```

---

## API Testing

### Using Swagger UI

Open: http://localhost:8000/docs

### Using curl/httpie

#### Step 1: Create a Bot

```bash
curl -X POST http://localhost:8000/api/v1/bots \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Test Bot",
    "description": "My first chatbot"
  }'
```

**Response:**
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "name": "Test Bot",
  "description": "My first chatbot",
  "model": "llama3.2:3b",
  "is_active": true,
  ...
}
```

Save the `id` for the next step!

#### Step 2: Upload a Document

```bash
# Replace {bot_id} with the actual bot ID from Step 1
# Create a test file first:
echo "This is a test document about AI and machine learning." > test.txt

# Upload with simple parser (default)
curl -X POST "http://localhost:8000/api/v1/documents/{bot_id}/upload" \
  -F "file=@test.txt" \
  -F "parser_type=simple"
```

**Response (202 Accepted):**
```json
{
  "id": "660e8400-e29b-41d4-a716-446655440001",
  "name": "test.txt",
  "status": "pending",
  "mime_type": "text/plain",
  "parser_type": "simple",
  "message": "Document accepted for processing..."
}
```

#### Step 3: Check Processing Status

```bash
# Replace {document_id} with the ID from Step 2
curl http://localhost:8000/api/v1/documents/{document_id}/status
```

**Status Values:**
- `pending` - Waiting in queue
- `processing` - Worker is parsing/chunking/embedding
- `ready` - Successfully processed
- `failed` - Error occurred (check `error_message`)

**Example Response:**
```json
{
  "id": "660e8400-e29b-41d4-a716-446655440001",
  "name": "test.txt",
  "status": "ready",
  "chunk_count": 3,
  "error_message": null,
  "created_at": "2024-01-15T10:30:00Z",
  "updated_at": "2024-01-15T10:30:05Z"
}
```

---

## Testing Different File Types

### PDF Document

```bash
curl -X POST "http://localhost:8000/api/v1/documents/{bot_id}/upload" \
  -F "file=@document.pdf" \
  -F "parser_type=simple"
```

### Word Document

```bash
curl -X POST "http://localhost:8000/api/v1/documents/{bot_id}/upload" \
  -F "file=@document.docx" \
  -F "parser_type=simple"
```

### Scanned PDF / Image (requires Docling)

```bash
# First install docling: pip install docling
curl -X POST "http://localhost:8000/api/v1/documents/{bot_id}/upload" \
  -F "file=@scanned_document.pdf" \
  -F "parser_type=docling"
```

---

## Verify Data in Database

```bash
# Connect to PostgreSQL
docker exec -it ai-chatbot-be-postgres-1 psql -U postgres -d chatbot

# Check bots
SELECT id, name, is_active FROM bots;

# Check documents
SELECT id, name, status, chunk_count, parser_type FROM documents;

# Check chunks (with embedding)
SELECT id, document_id, LEFT(content, 100) as content_preview,
       array_length(embedding, 1) as embed_dims
FROM document_chunks LIMIT 5;

# Exit
\q
```

---

## Troubleshooting

### Worker Not Processing Jobs

1. Check Redis is running: `docker ps | grep redis`
2. Check worker logs in Terminal 2
3. Verify Redis connection: `redis-cli ping` (should return PONG)

### Embedding Errors

1. Verify Ollama is running: `curl http://localhost:11434/api/tags`
2. Check if model is pulled: `ollama list`
3. Pull model if missing: `ollama pull nomic-embed-text`

### Database Connection Errors

1. Check PostgreSQL is running: `docker ps | grep postgres`
2. Verify connection string in `.env`
3. Run migrations: `alembic upgrade head`

### File Upload Errors

- Max file size: 50MB
- Allowed types: PDF, DOCX, TXT, MD, HTML, CSV, Images
- Images require `parser_type=docling`

---

## API Endpoints Summary

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Health check |
| POST | `/api/v1/bots` | Create bot |
| GET | `/api/v1/bots` | List bots |
| GET | `/api/v1/bots/{id}` | Get bot |
| PATCH | `/api/v1/bots/{id}` | Update bot |
| DELETE | `/api/v1/bots/{id}` | Delete bot |
| POST | `/api/v1/documents/{bot_id}/upload` | Upload document |
| GET | `/api/v1/documents/{bot_id}` | List documents |
| GET | `/api/v1/documents/{id}/status` | Get status |
| GET | `/api/v1/documents/{id}/detail` | Get full details |
| DELETE | `/api/v1/documents/{id}` | Delete document |

---

## Architecture Overview

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   FastAPI API   │────▶│   Redis Queue   │────▶│   ARQ Worker    │
│                 │     │                 │     │                 │
│ POST /upload    │     │ document_queue  │     │ process_doc_job │
└────────┬────────┘     └─────────────────┘     └────────┬────────┘
         │                                               │
         │                                               ▼
         │                                    ┌─────────────────────┐
         │                                    │ Processing Pipeline │
         │                                    ├─────────────────────┤
         ▼                                    │ 1. Parse (pypdf)    │
┌─────────────────┐                           │ 2. Chunk (langchain)│
│   PostgreSQL    │◀──────────────────────────│ 3. Embed (ollama)   │
│   (pgvector)    │                           │ 4. Store vectors    │
│                 │                           └─────────────────────┘
│ - bots          │
│ - documents     │
│ - chunks+embeds │
└─────────────────┘
```
