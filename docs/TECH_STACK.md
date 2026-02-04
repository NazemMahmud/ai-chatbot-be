# Technology Stack Recommendations

## Final Tech Stack (Optimized for Cost & Simplicity)

```
┌────────────────────────────────────────────────────────────┐
│                     FRONTEND LAYER                         │
├────────────────────────────────────────────────────────────┤
│  Dashboard: Nuxt 3 + TailwindCSS                           │
│  Widget: Vanilla JS + Vue 3 (~20KB gzipped)                │
│  UI Components: Nuxt UI / PrimeVue                         │
└────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                     BACKEND LAYER                           │
├─────────────────────────────────────────────────────────────┤
│  Framework: FastAPI (Python 3.11+)                         │
│  ORM: SQLAlchemy 2.0 (async)                               │
│  Validation: Pydantic v2                                   │
│  Auth: JWT + httponly cookies                              │
│  Background Jobs: ARQ (Redis-based, async)                 │
│  File Parsing: Dual mode — simple (pypdf, python-docx,     │
│    beautifulsoup4) or Docling (IBM, handles everything)    │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                      AI LAYER                               │
├─────────────────────────────────────────────────────────────┤
│  Runtime: Ollama (self-hosted) + HuggingFace (optional)    │
│  Chat: configurable — SmolLM3-3B (default), Qwen2.5:7b,   │
│         llama3.2:3b, Mistral 7B, Phi-3 Mini               │
│  Embed: configurable — nomic-embed-text (default),         │
│         e5-small (fastest), BGE-M3 (multilingual)          │
│  SQL: configurable — sqlcoder:7b (default),                │
│       Arctic-Text2SQL-R1-7B (SOTA) — loaded on demand      │
│  Fallback: CPU inference for low-traffic                   │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                     DATA LAYER                              │
├─────────────────────────────────────────────────────────────┤
│  Database: PostgreSQL 16 + pgvector extension              │
│  Cache/Queue: Redis 7                                      │
│  File Storage: MinIO (dev) / S3 or Backblaze B2 (prod)     │
│  Migrations: Alembic                                       │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                   INFRASTRUCTURE                            │
├─────────────────────────────────────────────────────────────┤
│  Containers: Docker + Docker Compose                       │
│  Hosting: Hetzner (recommended) / DigitalOcean / Railway   │
│  CDN: Cloudflare (free tier)                               │
│  Monitoring: Prometheus + Grafana (optional)               │
│  CI/CD: GitHub Actions                                     │
└─────────────────────────────────────────────────────────────┘
```

---

## Why These Choices?

### Backend: FastAPI

**Key Libraries**:
```
fastapi>=0.109.0
uvicorn[standard]>=0.27.0
sqlalchemy[asyncio]>=2.0.25
asyncpg>=0.29.0
pydantic>=2.5.0
python-jose[cryptography]  # JWT
passlib[bcrypt]            # Password hashing
python-multipart           # File uploads
httpx                      # Async HTTP client
arq                        # Background jobs
```

### Database: PostgreSQL + pgvector

| Alternative | Why pgvector              |
|-------------|---------------------------|
| Pinecone    | Expensive, vendor lock-in |
| Qdrant      | Extra service to manage   |
| Weaviate    | Complex, overkill for MVP |
| Chroma      | Not production-ready      |

**Benefits of pgvector**:
- Single database for everything
- ACID transactions across relational + vector data
- Familiar SQL interface
- Easy backups and migrations
- Great performance up to ~10M vectors

### AI Models: Configurable via Ollama + HuggingFace

All models are swappable via a single env var. No code changes needed.

#### Chat LLM Options

| Model | Params | VRAM | Quality | Best For |
|-------|--------|------|---------|----------|
| **SmolLM3-3B** (default) | 3B | ~3GB | Beats llama3.2:3b, 64K context | Default choice |
| Qwen3-0.6B | 0.6B | ~1GB | Decent for simple Q&A | Ultra-low resource |
| llama3.2:3b | 3B | 4GB | 85/100 | Previous default |
| Qwen2.5:7b | 7B | 8GB | 92/100 | Quality upgrade |
| Mistral 7B | 7B | ~5GB (Q4) | Very good | Strong general purpose |
| Llama 3.1 8B | 8B | ~4GB (Q4) | Excellent for RAG | Large context needs |

#### Embedding Options

| Model | Params | Dims | Latency | Provider |
|-------|--------|------|---------|----------|
| **nomic-embed-text** (default) | 137M | 768 | ~30ms | Ollama |
| e5-small | 118M | 384 | ~16ms | HuggingFace |
| all-MiniLM-L6-v2 | 22M | 384 | <30ms | Ollama / HuggingFace |
| BGE-M3 | 568M | 1024 | <30ms | HuggingFace |

#### Text2SQL Options (for DB connector feature)

| Model | Params | VRAM | Accuracy | Provider |
|-------|--------|------|----------|----------|
| **sqlcoder:7b** (default) | 7B | ~5GB | Proven, mature | Ollama |
| Arctic-Text2SQL-R1-7B | 7B | ~5GB | SOTA, beats GPT-4o | HuggingFace |
| prem-1B-SQL | 1B | ~1GB | Smallest viable | HuggingFace |

```
Hardware Profiles:

Minimal (8GB RAM):    nomic-embed-text + SmolLM3-3B          → ~3GB
Balanced (16GB RAM):  nomic-embed-text + Qwen2.5:7b + sqlcoder:7b → ~11GB
Quality (24GB+ VRAM): BGE-M3 + Llama 3.1 8B + Arctic-Text2SQL  → ~22GB
```

### Task Queue: ARQ over Celery

| Feature          | Celery | ARQ        |
|------------------|--------|------------|
| Setup complexity | High   | Low        |
| Dependencies     | Many   | Redis only |
| Async native     | No     | Yes        |
| Memory footprint | Heavy  | Light      |
| Learning curve   | Steep  | Gentle     |

**ARQ Example**:
```python
# Much simpler than Celery
from arq import create_pool

async def process_document(ctx, doc_id: str):
    # Your processing logic
    pass

# Enqueue job
redis = await create_pool(RedisSettings())
await redis.enqueue_job('process_document', doc_id)
```

### Frontend: Nuxt 3

| Feature | Nuxt 3 Advantage |
|---------|------------------|
| SSR/SSG | Built-in, zero config |
| Auto-imports | Components, composables auto-imported |
| File-based routing | Intuitive page structure |
| TypeScript | First-class support |
| DevTools | Excellent Vue DevTools |
| Learning curve | Gentler than React ecosystem |

**Dashboard Pages**:
```
pages/
├── index.vue                    # Landing page
├── login.vue                    # Auth
├── dashboard/
│   ├── index.vue                # Overview
│   ├── bots/
│   │   ├── index.vue            # Bot list
│   │   ├── new.vue              # Create bot
│   │   └── [id]/
│   │       ├── index.vue        # Bot settings
│   │       ├── documents.vue    # Doc management
│   │       ├── datasources.vue  # DB connections
│   │       ├── chat.vue         # Test chat
│   │       └── analytics.vue    # Stats
│   └── settings.vue             # Account settings
```

### Widget: Vanilla JS + Vue 3

**Why Vue for widget?**
- Vue 3 (petite-vue or full) is ~16KB gzipped
- Consistent with dashboard codebase
- Reactive without complexity
- Vanilla JS loader with lazy-loaded Vue UI

**Target Size**: < 25KB gzipped total

---

## Dependency Versions (Tested Compatibility)

### Backend (requirements.txt)
```
# Core
fastapi==0.109.2
uvicorn[standard]==0.27.1
pydantic==2.6.1
pydantic-settings==2.1.0

# Database
sqlalchemy[asyncio]==2.0.25
asyncpg==0.29.0
alembic==1.13.1
pgvector==0.2.5

# Auth
python-jose[cryptography]==3.3.0
passlib[bcrypt]==1.7.4

# HTTP
httpx==0.26.0
python-multipart==0.0.9

# Background Jobs
arq==0.25.0

# File Processing — Simple parser (PARSER_TYPE=simple)
pypdf==4.0.1
python-docx==1.1.0
beautifulsoup4==4.12.3
lxml==5.1.0
openpyxl==3.1.2
pandas==2.2.0

# File Processing — Docling parser (PARSER_TYPE=docling)
# Install with CPU-only PyTorch to save ~8GB disk:
#   pip install docling --extra-index-url https://download.pytorch.org/whl/cpu
# docling==2.70.0

# AI Models (HuggingFace provider — optional, if not using Ollama for all)
sentence-transformers==3.0.0   # For e5-small, BGE-M3 embeddings
# transformers==4.38.0         # Uncomment for Arctic-Text2SQL via HuggingFace
# torch==2.2.0                 # Uncomment for HuggingFace model inference

# DB Connector
cryptography==42.0.2           # Encrypt DB connection strings
aiomysql==0.2.0                # MySQL async driver (optional)
aiosqlite==0.20.0              # SQLite async driver (optional)

# Utils
python-slugify==8.0.2
orjson==3.9.13

# Dev
pytest==8.0.0
pytest-asyncio==0.23.4
ruff==0.2.1
```

### Frontend (package.json)
```json
{
  "dependencies": {
    "nuxt": "3.10.0",
    "vue": "3.4.15",
    "@nuxt/ui": "2.13.0",
    "@pinia/nuxt": "0.5.1",
    "pinia": "2.1.7",
    "@vueuse/nuxt": "10.7.2",
    "@nuxtjs/tailwindcss": "6.11.0",
    "lucide-vue-next": "0.323.0"
  },
  "devDependencies": {
    "typescript": "5.3.3"
  }
}
```

### Widget (package.json)
```json
{
  "dependencies": {
    "vue": "3.4.15"
  },
  "devDependencies": {
    "vite": "5.0.12",
    "@vitejs/plugin-vue": "5.0.3",
    "typescript": "5.3.3"
  }
}
```

---

## Docker Images

```yaml
# Recommended versions
services:
  postgres:
    image: pgvector/pgvector:pg16  # Postgres 16 with pgvector

  redis:
    image: redis:7-alpine

  minio:
    image: minio/minio:latest

  ollama:
    image: ollama/ollama:latest
```

---

## Alternatives Considered (And Why Not)

### Vector Databases

| Option | Verdict |
|--------|---------|
| **pgvector** | ✅ Use this - simple, integrated |
| Pinecone | ❌ Expensive, cloud-only |
| Qdrant | ⚠️ Good, but extra complexity |
| Milvus | ❌ Overkill for this scale |
| Chroma | ❌ Not production-ready |

### LLM APIs (vs Self-Hosted)

| Option | Verdict |
|--------|---------|
| OpenAI | ❌ Privacy concerns, expensive at scale |
| Anthropic | ❌ Same issues |
| **Ollama** | ✅ Self-hosted, free, privacy |
| vLLM | ⚠️ More complex, use for high scale |
| LocalAI | ⚠️ Alternative to Ollama, less polished |

### Hosting Providers

| Provider | Cost | Verdict |
|----------|------|---------|
| **Hetzner** | $50-150/mo | ✅ Best value |
| DigitalOcean | $80-200/mo | ⚠️ Good, slightly pricier |
| AWS | $300+/mo | ❌ Too expensive for MVP |
| Railway | $20+/mo | ⚠️ Good for quick start, scales poorly |
| Render | $25+/mo | ⚠️ Easy but limited GPU options |

---

## Quick Reference

### Commands to Install Models
```bash
# Install Ollama
curl -fsSL https://ollama.com/install.sh | sh    # Linux
brew install ollama                               # macOS

# Pull models — minimal setup
ollama pull smollm3:3b            # Chat model (~2GB) — recommended default
ollama pull nomic-embed-text      # Embedding model (~300MB)

# Pull models — with DB connector
ollama pull sqlcoder:7b           # Text2SQL model (~4GB)

# Pull models — quality setup
ollama pull qwen2.5:7b            # Better chat model (~4.5GB)

# For HuggingFace models (e5-small, BGE-M3, Arctic-Text2SQL)
pip install sentence-transformers  # Embedding models
pip install transformers torch     # Text2SQL models
# Models auto-download on first use to ~/.cache/huggingface/

# Test
ollama run smollm3:3b "Hello, how are you?"
```

### API Endpoints (Ollama)
```bash
# Generate chat completion
curl http://localhost:11434/api/generate \
  -d '{"model": "smollm3:3b", "prompt": "Hello"}'

# Generate embedding
curl http://localhost:11434/api/embeddings \
  -d '{"model": "nomic-embed-text", "prompt": "Hello world"}'

# Generate SQL (if sqlcoder pulled)
curl http://localhost:11434/api/generate \
  -d '{"model": "sqlcoder:7b", "prompt": "SELECT query for...", "stream": false}'

# List models
curl http://localhost:11434/api/tags
```

### pgvector Setup
```sql
-- Enable extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Create table with vector column
CREATE TABLE embeddings (
  id SERIAL PRIMARY KEY,
  content TEXT,
  embedding vector(768)  -- configurable: 384 (e5-small), 768 (nomic), 1024 (BGE-M3)
);

-- Create index for fast similarity search
CREATE INDEX ON embeddings
USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 100);

-- Query similar vectors
SELECT content, 1 - (embedding <=> '[0.1, 0.2, ...]') as similarity
FROM embeddings
ORDER BY embedding <=> '[0.1, 0.2, ...]'
LIMIT 5;
```

---

## Migration Path

### Phase 1 (MVP)
```
SmolLM3-3B + nomic-embed-text + pgvector + single server
All models configurable via env vars
```

### Phase 2 (Growth)
```
Add: Qwen2.5:7b option + sqlcoder:7b for DB connector + Redis caching + dedicated GPU server
```

### Phase 3 (Scale)
```
Add: Load balancing + multiple GPU nodes + Qdrant (if pgvector bottlenecks)
Arctic-Text2SQL-R1-7B for improved SQL accuracy
```

### Phase 4 (Enterprise)
```
Add: Kubernetes + vLLM for inference + dedicated clusters per customer
Per-tenant model selection
```
