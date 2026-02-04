# Development Guide

## Project Structure

```
ai-chatbot/
├── backend/                    # FastAPI application
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py            # FastAPI app entry
│   │   ├── config.py          # Settings & env vars
│   │   ├── database.py        # DB connection
│   │   │
│   │   ├── api/               # API routes
│   │   │   ├── __init__.py
│   │   │   ├── deps.py        # Dependencies (auth, db session)
│   │   │   ├── auth.py
│   │   │   ├── bots.py
│   │   │   ├── documents.py
│   │   │   ├── datasources.py # DB connection endpoints
│   │   │   ├── chat.py
│   │   │   └── widget.py
│   │   │
│   │   ├── models/            # SQLAlchemy models
│   │   │   ├── __init__.py
│   │   │   ├── user.py
│   │   │   ├── organization.py
│   │   │   ├── bot.py
│   │   │   ├── document.py
│   │   │   ├── datasource.py  # db_connections table
│   │   │   └── conversation.py
│   │   │
│   │   ├── schemas/           # Pydantic schemas
│   │   │   ├── __init__.py
│   │   │   ├── user.py
│   │   │   ├── bot.py
│   │   │   ├── document.py
│   │   │   └── chat.py
│   │   │
│   │   ├── services/          # Business logic
│   │   │   ├── __init__.py
│   │   │   ├── auth.py
│   │   │   ├── bot.py
│   │   │   ├── document.py
│   │   │   ├── embedding.py   # multi-provider (Ollama / HuggingFace)
│   │   │   ├── db_connector.py # connect to external DBs
│   │   │   ├── text2sql.py    # natural language → SQL
│   │   │   ├── chat.py
│   │   │   └── rag.py
│   │   │
│   │   ├── workers/           # Background jobs
│   │   │   ├── __init__.py
│   │   │   ├── tasks.py
│   │   │   └── document_processor.py
│   │   │
│   │   └── utils/
│   │       ├── __init__.py
│   │       ├── chunking.py
│   │       ├── parsers.py     # Dual mode: simple (pypdf/docx) or docling
│   │       └── scraper.py
│   │
│   ├── tests/
│   ├── alembic/               # DB migrations
│   ├── requirements.txt
│   ├── Dockerfile
│   └── pyproject.toml
│
├── frontend/                   # Dashboard (Nuxt 3)
│   ├── pages/                 # File-based routing
│   │   ├── index.vue
│   │   ├── login.vue
│   │   └── dashboard/
│   │       ├── index.vue
│   │       └── bots/
│   ├── components/            # Vue components
│   ├── composables/           # Vue composables
│   ├── stores/                # Pinia stores
│   ├── server/                # Nuxt server routes
│   ├── assets/
│   ├── nuxt.config.ts
│   ├── package.json
│   └── Dockerfile
│
├── widget/                     # Embeddable widget (Vue 3)
│   ├── src/
│   │   ├── main.ts
│   │   ├── App.vue
│   │   ├── components/
│   │   │   ├── ChatBubble.vue
│   │   │   ├── ChatWindow.vue
│   │   │   └── MessageList.vue
│   │   └── styles.css
│   ├── package.json
│   └── vite.config.ts
│
├── docker/
│   ├── docker-compose.yml     # Local development
│   ├── docker-compose.prod.yml
│   └── ollama/
│       └── Dockerfile
│
├── docs/
│   ├── PRD.md
│   ├── DEVELOPMENT_GUIDE.md
│   ├── API.md
│   └── DEPLOYMENT.md
│
├── scripts/
│   ├── setup.sh
│   ├── seed.py
│   └── migrate.sh
│
├── .env.example
├── .gitignore
├── Makefile
└── README.md
```

---

## Local Development Setup

### Prerequisites
- Docker & Docker Compose
- Python 3.11+
- Node.js 20+
- 8GB+ RAM minimum (16GB+ recommended for Text2SQL feature)

### 1. Clone & Setup

```bash
# Clone repository
git clone https://github.com/yourusername/ai-chatbot.git
cd ai-chatbot

# Copy environment file
cp .env.example .env

# Start infrastructure (Postgres, Redis, MinIO, Ollama)
make infra-up

# Pull required models (see Model Installation section below for options)
make pull-models
```

### 2. Backend Setup

```bash
cd backend

# Create virtual environment
python -m venv venv
source venv/bin/activate  # or `venv\Scripts\activate` on Windows

# Install dependencies
pip install -r requirements.txt

# Run migrations
alembic upgrade head

# Start development server
uvicorn app.main:app --reload --port 8000
```

### 3. Frontend Setup

```bash
cd frontend
npm install
npm run dev
```

### 4. Widget Development

```bash
cd widget
npm install
npm run dev
```

---

## Environment Variables

```bash
# .env.example

# App
APP_NAME=AI-Chatbot
APP_ENV=development
SECRET_KEY=your-secret-key-min-32-chars
API_URL=http://localhost:8000
FRONTEND_URL=http://localhost:3000

# Database
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/chatbot
REDIS_URL=redis://localhost:6379/0

# Storage (MinIO for local, S3 for production)
STORAGE_TYPE=minio
MINIO_ENDPOINT=localhost:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin
MINIO_BUCKET=chatbot

# Ollama
OLLAMA_BASE_URL=http://localhost:11434

# Model Configuration — all models are swappable via these env vars
# Embedding: "ollama" or "huggingface"
EMBED_PROVIDER=ollama
EMBED_MODEL_NAME=nomic-embed-text
EMBED_DIMENSIONS=768

# Chat LLM (via Ollama): smollm3:3b, llama3.2:3b, qwen2.5:7b, mistral:7b
CHAT_MODEL_NAME=smollm3:3b
CHAT_TEMPERATURE=0.7

# Document Parser: "docling" or "simple"
# docling = heavy, handles mixed content/images/tables/multilingual (~1.7GB, 3-4GB RAM)
# simple = light, text-only extraction via pypdf/python-docx (~170MB, 200MB RAM)
PARSER_TYPE=simple

# Text2SQL (for DB connector feature)
ENABLE_DB_CONNECTOR=false
SQL_PROVIDER=ollama
SQL_MODEL_NAME=sqlcoder:7b

# Rate Limiting
RATE_LIMIT_REQUESTS=100
RATE_LIMIT_WINDOW=60

# JWT
JWT_SECRET=your-jwt-secret
JWT_EXPIRY_HOURS=24
```

---

## Docker Compose (Development)

```yaml
# docker/docker-compose.yml
version: '3.8'

services:
  postgres:
    image: pgvector/pgvector:pg16
    environment:
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres
      POSTGRES_DB: chatbot
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data

  minio:
    image: minio/minio
    command: server /data --console-address ":9001"
    environment:
      MINIO_ROOT_USER: minioadmin
      MINIO_ROOT_PASSWORD: minioadmin
    ports:
      - "9000:9000"
      - "9001:9001"
    volumes:
      - minio_data:/data

  ollama:
    image: ollama/ollama
    ports:
      - "11434:11434"
    volumes:
      - ollama_data:/root/.ollama
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]

volumes:
  postgres_data:
  redis_data:
  minio_data:
  ollama_data:
```

---

## Key Implementation Details

### 1. Document Processing Pipeline

```python
# backend/app/services/document.py
from app.utils.parsers import parse_pdf, parse_docx, parse_text
from app.utils.chunking import chunk_text
from app.services.embedding import generate_embeddings

async def process_document(document_id: str, db: AsyncSession):
    """Background task to process uploaded document."""

    # 1. Get document record
    doc = await get_document(db, document_id)
    await update_status(db, document_id, "processing")

    try:
        # 2. Download file from storage
        file_content = await storage.download(doc.file_path)

        # 3. Parse based on file type
        if doc.mime_type == "application/pdf":
            text = parse_pdf(file_content)
        elif doc.mime_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
            text = parse_docx(file_content)
        else:
            text = file_content.decode("utf-8")

        # 4. Chunk the text
        chunks = chunk_text(
            text,
            chunk_size=512,
            chunk_overlap=50,
            metadata={"document_id": document_id, "source": doc.name}
        )

        # 5. Generate embeddings (batch)
        embeddings = await generate_embeddings([c.text for c in chunks])

        # 6. Store in pgvector
        await store_chunks(db, doc.bot_id, chunks, embeddings)

        # 7. Update status
        await update_status(db, document_id, "ready", chunk_count=len(chunks))

    except Exception as e:
        await update_status(db, document_id, "failed", error=str(e))
        raise
```

### 2. Chunking Strategy

```python
# backend/app/utils/chunking.py
from dataclasses import dataclass
from typing import List

@dataclass
class Chunk:
    text: str
    metadata: dict
    start_index: int
    end_index: int

def chunk_text(
    text: str,
    chunk_size: int = 512,
    chunk_overlap: int = 50,
    metadata: dict = None
) -> List[Chunk]:
    """
    Split text into overlapping chunks.
    Uses sentence-aware splitting to avoid cutting mid-sentence.
    """
    import re

    # Split by sentences
    sentences = re.split(r'(?<=[.!?])\s+', text)

    chunks = []
    current_chunk = []
    current_length = 0
    start_idx = 0

    for sentence in sentences:
        sentence_len = len(sentence.split())

        if current_length + sentence_len > chunk_size:
            # Save current chunk
            chunk_text = " ".join(current_chunk)
            chunks.append(Chunk(
                text=chunk_text,
                metadata=metadata or {},
                start_index=start_idx,
                end_index=start_idx + len(chunk_text)
            ))

            # Start new chunk with overlap
            overlap_words = chunk_size - chunk_overlap
            current_chunk = current_chunk[-overlap_words:] if overlap_words > 0 else []
            current_length = sum(len(s.split()) for s in current_chunk)
            start_idx = start_idx + len(chunk_text) - len(" ".join(current_chunk))

        current_chunk.append(sentence)
        current_length += sentence_len

    # Don't forget last chunk
    if current_chunk:
        chunk_text = " ".join(current_chunk)
        chunks.append(Chunk(
            text=chunk_text,
            metadata=metadata or {},
            start_index=start_idx,
            end_index=start_idx + len(chunk_text)
        ))

    return chunks
```

### 3. RAG Chat Service

```python
# backend/app/services/rag.py
from app.services.embedding import generate_embedding
from app.services.llm import generate_response
from sqlalchemy import text

async def rag_chat(
    bot_id: str,
    query: str,
    conversation_history: list,
    db: AsyncSession
) -> AsyncGenerator[str, None]:
    """
    Retrieve relevant chunks and generate streaming response.
    """

    # 1. Get bot config
    bot = await get_bot(db, bot_id)

    # 2. Embed the query
    query_embedding = await generate_embedding(query)

    # 3. Vector similarity search
    results = await db.execute(
        text("""
            SELECT content, metadata,
                   1 - (embedding <=> :query_embedding) as similarity
            FROM document_chunks
            WHERE bot_id = :bot_id
            ORDER BY embedding <=> :query_embedding
            LIMIT 5
        """),
        {"bot_id": bot_id, "query_embedding": query_embedding}
    )
    chunks = results.fetchall()

    # 4. Build prompt
    context = "\n\n".join([
        f"[Source: {c.metadata.get('source', 'Unknown')}]\n{c.content}"
        for c in chunks
    ])

    system_prompt = f"""{bot.system_prompt or "You are a helpful assistant."}

Use the following context to answer the user's question.
If you cannot find the answer in the context, say so honestly.
Always cite your sources when possible.

Context:
{context}
"""

    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(conversation_history[-10:])  # Last 10 messages
    messages.append({"role": "user", "content": query})

    # 5. Stream response from LLM
    async for token in generate_response(
        model=bot.model,
        messages=messages,
        temperature=bot.temperature
    ):
        yield token

    # 6. Return sources for citation
    yield {"sources": [{"content": c.content[:200], "source": c.metadata.get("source")} for c in chunks[:3]]}
```

### 4. Embedding Service (Multi-Provider)

```python
# backend/app/services/embedding.py
import httpx
from app.config import settings

class EmbeddingService:
    """Supports both Ollama and HuggingFace embedding models."""

    def __init__(self, app_state=None):
        self.provider = settings.EMBED_PROVIDER
        if self.provider == "huggingface" and app_state:
            self.model = app_state.embed_model  # loaded at startup via lifespan

    async def generate_embedding(self, text: str) -> list[float]:
        if self.provider == "ollama":
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{settings.OLLAMA_BASE_URL}/api/embeddings",
                    json={"model": settings.EMBED_MODEL_NAME, "prompt": text}
                )
                response.raise_for_status()
                return response.json()["embedding"]
        else:
            return self.model.encode(text).tolist()

    async def generate_embeddings(self, texts: list[str], batch_size: int = 32) -> list[list[float]]:
        if self.provider == "huggingface":
            return self.model.encode(texts, batch_size=batch_size).tolist()
        else:
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

### 5. Widget Implementation (Vue 3)

```vue
<!-- widget/src/App.vue -->
<script setup lang="ts">
import { ref, onMounted } from 'vue'
import ChatBubble from './components/ChatBubble.vue'
import ChatWindow from './components/ChatWindow.vue'

interface Props {
  botId: string
  apiUrl: string
  position?: 'bottom-right' | 'bottom-left'
  theme?: 'light' | 'dark'
}

const props = defineProps<Props>()

const isOpen = ref(false)
const botConfig = ref<any>(null)
const messages = ref<Array<{ role: string; content: string }>>([])
const sessionId = ref(localStorage.getItem('chatbot_session') || crypto.randomUUID())

onMounted(async () => {
  localStorage.setItem('chatbot_session', sessionId.value)
  await fetchBotConfig()
})

async function fetchBotConfig() {
  const response = await fetch(`${props.apiUrl}/api/widget/${props.botId}/config`)
  botConfig.value = await response.json()

  // Add welcome message
  if (botConfig.value.welcomeMessage) {
    messages.value.push({
      role: 'assistant',
      content: botConfig.value.welcomeMessage
    })
  }
}

async function sendMessage(content: string) {
  messages.value.push({ role: 'user', content })

  const response = await fetch(`${props.apiUrl}/api/widget/${props.botId}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      message: content,
      session_id: sessionId.value,
      history: messages.value.slice(-10)
    })
  })

  // Handle streaming response
  const reader = response.body?.getReader()
  const decoder = new TextDecoder()
  let assistantMessage = ''

  messages.value.push({ role: 'assistant', content: '' })
  const lastIndex = messages.value.length - 1

  while (reader) {
    const { done, value } = await reader.read()
    if (done) break

    assistantMessage += decoder.decode(value)
    messages.value[lastIndex].content = assistantMessage
  }
}
</script>

<template>
  <div class="chatbot-widget" :class="[position, theme]">
    <ChatBubble v-if="!isOpen" @click="isOpen = true" />
    <ChatWindow
      v-else
      :bot-config="botConfig"
      :messages="messages"
      @close="isOpen = false"
      @send="sendMessage"
    />
  </div>
</template>
```

```vue
<!-- widget/src/components/ChatWindow.vue -->
<script setup lang="ts">
import { ref } from 'vue'

defineProps<{
  botConfig: any
  messages: Array<{ role: string; content: string }>
}>()

const emit = defineEmits<{
  close: []
  send: [message: string]
}>()

const input = ref('')

function handleSend() {
  if (!input.value.trim()) return
  emit('send', input.value)
  input.value = ''
}
</script>

<template>
  <div class="chat-window">
    <div class="chat-header">
      <span>{{ botConfig?.name || 'Chat' }}</span>
      <button @click="emit('close')">×</button>
    </div>

    <div class="chat-messages">
      <div
        v-for="(msg, i) in messages"
        :key="i"
        :class="['message', msg.role]"
      >
        {{ msg.content }}
      </div>
    </div>

    <div class="chat-input">
      <input
        v-model="input"
        placeholder="Type a message..."
        @keyup.enter="handleSend"
      />
      <button @click="handleSend">Send</button>
    </div>
  </div>
</template>
```

```typescript
// widget/src/main.ts - Entry point for widget
import { createApp } from 'vue'
import App from './App.vue'
import './styles.css'

// Get config from script tag
const script = document.currentScript as HTMLScriptElement
const botId = script?.dataset.botId
const apiUrl = script?.dataset.apiUrl || 'https://api.yourchatbot.com'
const position = script?.dataset.position || 'bottom-right'
const theme = script?.dataset.theme || 'light'

// Create mount point
const container = document.createElement('div')
container.id = 'chatbot-widget-root'
document.body.appendChild(container)

// Mount Vue app
createApp(App, { botId, apiUrl, position, theme }).mount(container)
```

---

## Background Jobs with ARQ

```python
# backend/app/workers/tasks.py
from arq import create_pool
from arq.connections import RedisSettings

async def process_document_task(ctx, document_id: str):
    """Process uploaded document (parse, chunk, embed)."""
    from app.services.document import process_document
    from app.database import get_session

    async with get_session() as db:
        await process_document(document_id, db)

async def scrape_url_task(ctx, bot_id: str, url: str):
    """Scrape and index a URL."""
    from app.utils.scraper import scrape_url
    from app.services.document import create_document_from_text

    content = await scrape_url(url)
    async with get_session() as db:
        doc = await create_document_from_text(
            db, bot_id, url, content, source_type="url"
        )
        await process_document(doc.id, db)

class WorkerSettings:
    functions = [process_document_task, scrape_url_task]
    redis_settings = RedisSettings.from_dsn(settings.REDIS_URL)
    max_jobs = 10
    job_timeout = 300  # 5 minutes
```

---

## Testing Strategy

### Unit Tests
```python
# backend/tests/test_chunking.py
import pytest
from app.utils.chunking import chunk_text

def test_chunk_text_basic():
    text = "This is sentence one. This is sentence two. This is sentence three."
    chunks = chunk_text(text, chunk_size=5, chunk_overlap=1)

    assert len(chunks) >= 1
    assert all(len(c.text.split()) <= 6 for c in chunks)

def test_chunk_text_overlap():
    text = " ".join([f"Word{i}" for i in range(100)])
    chunks = chunk_text(text, chunk_size=20, chunk_overlap=5)

    # Check overlap exists
    for i in range(1, len(chunks)):
        prev_words = set(chunks[i-1].text.split()[-5:])
        curr_words = set(chunks[i].text.split()[:5])
        assert len(prev_words & curr_words) > 0
```

### Integration Tests
```python
# backend/tests/test_api.py
import pytest
from httpx import AsyncClient

@pytest.mark.asyncio
async def test_create_bot(client: AsyncClient, auth_headers):
    response = await client.post(
        "/api/orgs/test-org/bots",
        json={"name": "Test Bot", "system_prompt": "You are helpful."},
        headers=auth_headers
    )
    assert response.status_code == 201
    assert response.json()["name"] == "Test Bot"

@pytest.mark.asyncio
async def test_upload_document(client: AsyncClient, auth_headers, test_bot):
    with open("tests/fixtures/sample.pdf", "rb") as f:
        response = await client.post(
            f"/api/bots/{test_bot.id}/documents/upload",
            files={"file": ("sample.pdf", f, "application/pdf")},
            headers=auth_headers
        )
    assert response.status_code == 202
    assert response.json()["status"] == "pending"
```

---

## Makefile Commands

```makefile
# Makefile

.PHONY: help install dev test lint format migrate

help:
	@echo "Available commands:"
	@echo "  make install     - Install all dependencies"
	@echo "  make dev         - Start development servers"
	@echo "  make test        - Run tests"
	@echo "  make lint        - Run linters"
	@echo "  make migrate     - Run database migrations"
	@echo "  make pull-models - Pull Ollama models"

install:
	cd backend && pip install -r requirements.txt
	cd frontend && npm install
	cd widget && npm install

dev:
	docker-compose -f docker/docker-compose.yml up -d
	cd backend && uvicorn app.main:app --reload &
	cd frontend && npm run dev &
	cd widget && npm run dev

infra-up:
	docker-compose -f docker/docker-compose.yml up -d

infra-down:
	docker-compose -f docker/docker-compose.yml down

pull-models:
	docker exec ollama ollama pull smollm3:3b
	docker exec ollama ollama pull nomic-embed-text

pull-models-full:
	docker exec ollama ollama pull smollm3:3b
	docker exec ollama ollama pull nomic-embed-text
	docker exec ollama ollama pull sqlcoder:7b

pull-models-quality:
	docker exec ollama ollama pull qwen2.5:7b
	docker exec ollama ollama pull nomic-embed-text
	docker exec ollama ollama pull sqlcoder:7b

test:
	cd backend && pytest -v

lint:
	cd backend && ruff check .
	cd frontend && npm run lint

format:
	cd backend && ruff format .
	cd frontend && npm run format

migrate:
	cd backend && alembic upgrade head

migrate-new:
	cd backend && alembic revision --autogenerate -m "$(name)"
```

---

## Model Installation

All AI models are configurable via environment variables. Choose a provider and model based on your hardware.

### Ollama Models (recommended)

Ollama manages model downloads, quantization, and serving behind a single REST API.

```bash
# Install Ollama
curl -fsSL https://ollama.com/install.sh | sh    # Linux
brew install ollama                               # macOS

# Start server
ollama serve

# --- Embedding Models (pick one) ---
ollama pull nomic-embed-text          # 768 dims, ~300MB — default
ollama pull all-minilm:l6-v2          # 384 dims, ~50MB — lightest

# --- Chat Models (pick one) ---
ollama pull smollm3:3b                # ~2GB — recommended default
ollama pull llama3.2:3b               # ~2GB — previous default
ollama pull qwen2.5:7b                # ~4.5GB — better quality (needs 8GB VRAM)
ollama pull mistral:7b                # ~4GB — strong general purpose
ollama pull phi3:mini                 # ~2.3GB — good reasoning

# --- Text2SQL Models (pick one, only if ENABLE_DB_CONNECTOR=true) ---
ollama pull sqlcoder:7b               # ~4GB — Defog SQLCoder

# Verify
ollama list
curl http://localhost:11434/api/generate -d '{"model":"smollm3:3b","prompt":"Hi","stream":false}'
```

### HuggingFace Models (alternative for embedding & text2sql)

Some models aren't available on Ollama. Use them directly via Python:

```bash
# For embedding models (e5-small, BGE-M3)
pip install sentence-transformers

# For Text2SQL (Arctic-Text2SQL-R1-7B)
pip install transformers torch accelerate
```

Models auto-download to `~/.cache/huggingface/` on first use. Set `EMBED_PROVIDER=huggingface` or `SQL_PROVIDER=huggingface` in `.env`.

### Pre-download for Offline/CI

```bash
pip install huggingface_hub
huggingface-cli download intfloat/e5-small-v2 --local-dir ./models/e5-small
huggingface-cli download Snowflake/Arctic-Text2SQL-R1-7B --local-dir ./models/arctic-text2sql
```

### Hardware Profiles

| Profile | Embedding | Chat LLM | Text2SQL | Total VRAM |
|---------|-----------|----------|----------|------------|
| **Minimal** (8GB RAM) | nomic-embed-text | smollm3:3b | — | ~3GB |
| **Balanced** (16GB RAM) | nomic-embed-text | qwen2.5:7b | sqlcoder:7b | ~11GB |
| **Quality** (24GB+ VRAM) | BGE-M3 (HF) | Llama 3.1 8B | Arctic-Text2SQL-R1-7B (HF) | ~22GB |

See [APPROACH_GUIDE.md](./APPROACH_GUIDE.md) for full model comparison tables and FastAPI integration patterns.

---

## System Resource Requirements

All models/services can run in parallel. Here's what you actually need.

### What runs simultaneously (worst case)

```
Process 1: FastAPI API server                      → ~200 MB RAM
Process 2: ARQ background worker                   → ~200 MB RAM
Process 3: Docling (during document processing)    → ~3-4 GB RAM (spikes), CPU 100%
Process 4: Ollama (embedding model, always loaded)  → model-dependent
Process 5: Ollama (chat LLM, loaded on request)     → model-dependent
Process 6: Ollama (text2sql, loaded on request)     → model-dependent (if enabled)
Process 7: PostgreSQL + pgvector                    → ~200-500 MB RAM
Process 8: Redis                                    → ~50 MB RAM
Process 9: MinIO                                    → ~100 MB RAM
Process 10: Nuxt frontend dev server                → ~300 MB RAM
```

Ollama keeps a model loaded for ~5 minutes after last use, then unloads it. If two models are requested within that window, both stay in RAM/VRAM.

### Local Development (your PC)

| Profile | RAM needed | Disk needed | GPU | Parser |
|---------|-----------|-------------|-----|--------|
| **Lite** (just get it running) | **8 GB** | ~8 GB | None | simple |
| **Standard** (recommended for dev) | **16 GB** | ~12 GB | None | simple or docling |
| **Full** (all features, Docling + DB) | **32 GB** | ~20 GB | Optional | docling |

#### Lite — 8 GB RAM, no GPU

```
Docker infra:            ~800 MB (Postgres + Redis + MinIO)
Ollama (nomic-embed):    ~300 MB
Ollama (smollm3:3b):     ~3 GB (loaded on chat request)
FastAPI + ARQ worker:    ~400 MB
Nuxt dev server:         ~300 MB
─────────────────────────────────
Peak (during chat):      ~5 GB RAM
```

- Parser: `PARSER_TYPE=simple` (pypdf, no Docling)
- No text2sql: `ENABLE_DB_CONNECTOR=false`
- Embedding + chat model never loaded simultaneously (Ollama swaps them)
- Disk: ~3 GB models + ~3 GB Docker images + ~2 GB Python packages

#### Standard — 16 GB RAM, no GPU

```
Docker infra:            ~800 MB
Ollama (nomic-embed):    ~300 MB (stays loaded)
Ollama (smollm3:3b):     ~3 GB (loaded on chat request)
Docling (during parse):  ~3-4 GB (spike, only during document processing)
FastAPI + ARQ worker:    ~400 MB
Nuxt dev server:         ~300 MB
─────────────────────────────────
Peak (parsing + chat):   ~8-9 GB RAM
```

- Parser: `PARSER_TYPE=docling` — handles mixed content
- No text2sql yet
- Docling spike is temporary — only while ARQ worker processes a document
- Disk: ~3 GB models + ~3 GB Docker images + ~4 GB Python packages (with Docling)

#### Full — 32 GB RAM, optional GPU

```
Docker infra:            ~800 MB
Ollama (nomic-embed):    ~300 MB (stays loaded)
Ollama (qwen2.5:7b):     ~5 GB (during chat)
Ollama (sqlcoder:7b):    ~5 GB (during DB query, may overlap with chat)
Docling (during parse):  ~4 GB (spike)
FastAPI + ARQ worker:    ~400 MB
Nuxt dev server:         ~300 MB
─────────────────────────────────
Peak (all simultaneous): ~16 GB RAM
Worst case (chat + DB query + parsing): ~20 GB RAM
```

- All features enabled
- With GPU (8GB+ VRAM): Ollama offloads chat + embed to GPU, frees ~8 GB RAM
- Disk: ~12 GB models + ~3 GB Docker images + ~5 GB Python packages

### Production Server

| Tier | Server spec | Monthly cost (Hetzner) | Features |
|------|------------|----------------------|----------|
| **Small** | 8 vCPU, 16 GB RAM, 160 GB SSD | ~$15/mo | Simple parser, basic chat |
| **Medium** | 8 vCPU, 32 GB RAM, 240 GB SSD | ~$30/mo | Docling + chat + DB connector |
| **GPU** | 8 vCPU, 32 GB RAM, RTX 3060 12GB | ~$80-150/mo | All features, fast inference |

---

## Next Steps

1. **Week 1**: Set up project structure, Docker environment, database schema
2. **Week 2**: Implement auth, org, and bot CRUD APIs
3. **Week 3**: Build document upload and processing pipeline
4. **Week 4**: Implement RAG chat with streaming
5. **Week 5**: Create dashboard UI
6. **Week 6**: Build and test embeddable widget

See [DEPLOYMENT.md](./DEPLOYMENT.md) for production deployment guide.
