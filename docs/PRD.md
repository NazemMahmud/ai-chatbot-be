# AI Chatbot Widget - Product Requirements Document (PRD)

## Summary

A privacy-focused, embeddable AI chatbot widget that businesses can train on their own data (documents, websites, databases) and deploy on any website. The system runs on self-hosted models, ensuring complete data privacy.

---

## 1. Problem Statement

Businesses need AI chatbots for customer support, documentation assistance, and lead generation. Current solutions either:
- Require sending sensitive data to third-party APIs (OpenAI, etc.)
- Are expensive at scale
- Lack customization for specific business knowledge
- Are complex to integrate

**Our Solution**: A self-hosted, privacy-first RAG chatbot that learns from your data and embeds anywhere with a single script tag.

---

## 2. Target Users

### Primary
- **Small-Medium Businesses** wanting AI support without data privacy concerns
- **SaaS Companies** needing documentation chatbots
- **E-commerce** sites wanting product Q&A bots
- **Healthcare/Legal/Finance** companies with strict data compliance requirements

### Secondary
- Developers building custom AI assistants
- Agencies managing multiple client chatbots

---

## 3. Core Features (MVP - Phase 1)

### 3.1 Knowledge Ingestion
| Source | Priority | MVP |
|--------|----------|-----|
| PDF files | P0 | ✅ |
| TXT/Markdown | P0 | ✅ |
| DOCX | P0 | ✅ |
| Website URL scraping | P1 | ✅ |
| HTML files | P1 | ✅ |
| CSV/Excel | P1 | ✅ |
| Database connection (Text2SQL) | P1 | ✅ |
| XML | P2 | ❌ |

### 3.2 Bot Management
- Create/edit/delete bots
- Configure bot personality (system prompt)
- Set welcome message
- Toggle citation display
- Choose response language

### 3.3 Chat Interface
- Real-time streaming responses
- Conversation history
- Source citations with links
- Mobile-responsive design

### 3.4 Embeddable Widget
```html
<!-- Single line integration -->
<script src="https://yourapp.com/widget.js" data-bot-id="xxx"></script>
```

Features:
- Floating chat bubble (bottom-right)
- Full-page embed option
- Customizable colors/branding
- Domain restriction for security

### 3.5 Dashboard
- Bot analytics (conversations, messages, popular questions)
- Conversation logs
- Document management
- Usage tracking

---

## 4. Technical Architecture

### 4.1 System Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                         CLIENT LAYER                            │
├─────────────────┬─────────────────┬─────────────────────────────┤
│   Dashboard     │   Widget (JS)   │   Public API               │
│   (Nuxt 3)      │   (Vue 3)       │   (REST)                   │
└────────┬────────┴────────┬────────┴──────────┬──────────────────┘
         │                 │                   │
         ▼                 ▼                   ▼
┌─────────────────────────────────────────────────────────────────┐
│                      API GATEWAY (FastAPI)                      │
├─────────────────────────────────────────────────────────────────┤
│  Auth  │  Bot Mgmt  │  Documents  │  Chat  │  Widget  │ Billing │
└────────┴────────────┴──────────────┴────────┴──────────┴────────┘
         │                                    │
         ▼                                    ▼
┌─────────────────────┐          ┌────────────────────────────────┐
│   Background Jobs   │          │        AI Layer (Ollama)       │
│   (Celery/ARQ)      │          ├────────────────────────────────┤
│                     │          │  Chat: configurable (default   │
│  - Doc parsing      │◄────────►│    SmolLM3-3B or llama3.2:3b)  │
│  - Chunking         │          │  Embed: configurable (default  │
│  - Embedding        │          │    nomic-embed-text or e5-small)│
│  - URL scraping     │          │  SQL: configurable (default    │
│  - DB sync          │          │    sqlcoder:7b) — on demand    │
└─────────┬───────────┘
          │
          ▼
┌─────────────────────────────────────────────────────────────────┐
│                       DATA LAYER                                │
├──────────────────┬──────────────────┬───────────────────────────┤
│   PostgreSQL     │   Redis          │   S3/MinIO                │
│   + pgvector     │   (Queue/Cache)  │   (File Storage)          │
│                  │                  │                           │
│  - Users/Orgs    │  - Job queue     │  - Original documents     │
│  - Bots          │  - Rate limits   │  - Bot avatars            │
│  - Conversations │  - Session cache │                           │
│  - Embeddings    │                  │                           │
└──────────────────┴──────────────────┴───────────────────────────┘
```

### 4.2 RAG Pipeline

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│   Upload     │────►│   Parse &    │────►│   Chunk      │
│   Document   │     │   Extract    │     │   (512 tok)  │
└──────────────┘     └──────────────┘     └──────┬───────┘
                                                 │
                                                 ▼
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│   Store in   │◄────│   Generate   │◄────│   Clean &    │
│   pgvector   │     │   Embeddings │     │   Normalize  │
└──────────────┘     └──────────────┘     └──────────────┘

QUERY TIME:
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│   User       │────►│   Embed      │────►│   Vector     │
│   Question   │     │   Query      │     │   Search     │
└──────────────┘     └──────────────┘     └──────┬───────┘
                                                 │
                                                 ▼
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│   Stream     │◄────│   LLM        │◄────│   Build      │
│   Response   │     │   Generate   │     │   Prompt     │
└──────────────┘     └──────────────┘     └──────────────┘
```

### 4.3 Tech Stack (Final Recommendations)

| Layer | Technology | Reasoning |
|-------|------------|-----------|
| **Chat LLM** | Configurable via Ollama (default: `SmolLM3-3B`) | Outperforms llama3.2:3b, 64K context, ~3GB VRAM. Alternatives: `Qwen2.5:7b`, `llama3.2:3b`, `Mistral 7B` |
| **Embeddings** | Configurable (default: `nomic-embed-text` via Ollama) | 768 dims, good quality/speed. Alternatives: `e5-small` (fastest, 384 dims), `BGE-M3` (multilingual, 1024 dims) |
| **Text2SQL** | Configurable (default: `sqlcoder:7b` via Ollama) | For DB connection feature. Alternative: `Arctic-Text2SQL-R1-7B` (SOTA accuracy). Loaded on demand only |
| **Doc Parser** | Dual mode: `simple` (pypdf/docx, lightweight) or `docling` (IBM, handles images/tables/OCR/multilingual). Selectable per request via API parameter |
| **Backend** | FastAPI + Python 3.11 | Async, fast, great ecosystem |
| **Task Queue** | ARQ (Redis-based) | Lighter than Celery, async-native |
| **Database** | PostgreSQL 16 + pgvector | Single DB, easy ops |
| **Cache/Queue** | Redis 7 | Fast, reliable |
| **File Storage** | MinIO (self-hosted) / S3 | S3-compatible |
| **Dashboard** | Nuxt 3 + TailwindCSS | Modern, SSR, great DX |
| **Widget** | Vanilla JS + Vue 3 | Lightweight bundle (~20KB) |
| **Deployment** | Docker Compose → K8s | Start simple, scale later |

---

## 5. Database Schema (MVP)

```sql
-- Core entities
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    name VARCHAR(255),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE organizations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    slug VARCHAR(100) UNIQUE NOT NULL,
    owner_id UUID REFERENCES users(id),
    plan VARCHAR(50) DEFAULT 'free',
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE org_members (
    org_id UUID REFERENCES organizations(id),
    user_id UUID REFERENCES users(id),
    role VARCHAR(50) DEFAULT 'member',
    PRIMARY KEY (org_id, user_id)
);

CREATE TABLE bots (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID REFERENCES organizations(id),
    name VARCHAR(255) NOT NULL,
    slug VARCHAR(100) NOT NULL,
    system_prompt TEXT,
    welcome_message TEXT,
    model VARCHAR(100) DEFAULT 'smollm3:3b',
    temperature FLOAT DEFAULT 0.7,
    show_citations BOOLEAN DEFAULT true,
    allowed_domains TEXT[], -- for widget security
    widget_config JSONB DEFAULT '{}',
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(org_id, slug)
);

CREATE TABLE bot_api_keys (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    bot_id UUID REFERENCES bots(id),
    key_hash VARCHAR(255) NOT NULL,
    name VARCHAR(100),
    last_used_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    bot_id UUID REFERENCES bots(id),
    name VARCHAR(255) NOT NULL,
    source_type VARCHAR(50) NOT NULL, -- 'file', 'url', 'text', 'database'
    source_url TEXT,
    file_path TEXT,
    file_size INTEGER,
    mime_type VARCHAR(100),
    status VARCHAR(50) DEFAULT 'pending', -- pending, processing, ready, failed
    error_message TEXT,
    chunk_count INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Vector storage with pgvector
CREATE TABLE document_chunks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID REFERENCES documents(id) ON DELETE CASCADE,
    bot_id UUID REFERENCES bots(id), -- denormalized for faster queries
    content TEXT NOT NULL,
    metadata JSONB DEFAULT '{}',
    embedding vector(768), -- configurable: 384 (e5-small), 768 (nomic), 1024 (BGE-M3)
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_chunks_embedding ON document_chunks
USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

CREATE INDEX idx_chunks_bot ON document_chunks(bot_id);

CREATE TABLE conversations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    bot_id UUID REFERENCES bots(id),
    session_id VARCHAR(255), -- for anonymous widget users
    user_id UUID REFERENCES users(id), -- null for widget users
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID REFERENCES conversations(id) ON DELETE CASCADE,
    role VARCHAR(20) NOT NULL, -- 'user', 'assistant'
    content TEXT NOT NULL,
    sources JSONB, -- cited chunks
    token_count INTEGER,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE usage_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID REFERENCES organizations(id),
    bot_id UUID REFERENCES bots(id),
    event_type VARCHAR(50) NOT NULL, -- 'message', 'embedding', 'scrape'
    tokens_used INTEGER,
    metadata JSONB,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_usage_org_date ON usage_events(org_id, created_at);

-- Database connections (for Text2SQL feature)
CREATE TABLE db_connections (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    bot_id UUID REFERENCES bots(id),
    name VARCHAR(255) NOT NULL,
    db_type VARCHAR(50) NOT NULL, -- 'postgres', 'mysql', 'sqlite'
    connection_string_encrypted TEXT NOT NULL, -- AES-256 encrypted
    schema_cache JSONB DEFAULT '{}', -- cached table/column info
    status VARCHAR(50) DEFAULT 'pending', -- pending, connected, synced, failed
    last_synced_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);
```

---

## 6. API Endpoints (MVP)

### Authentication
```
POST   /api/auth/register
POST   /api/auth/login
POST   /api/auth/logout
GET    /api/auth/me
```

### Organizations
```
GET    /api/orgs
POST   /api/orgs
GET    /api/orgs/{org_id}
PATCH  /api/orgs/{org_id}
```

### Bots
```
GET    /api/orgs/{org_id}/bots
POST   /api/orgs/{org_id}/bots
GET    /api/bots/{bot_id}
PATCH  /api/bots/{bot_id}
DELETE /api/bots/{bot_id}
POST   /api/bots/{bot_id}/api-keys
```

### Documents
```
GET    /api/bots/{bot_id}/documents
POST   /api/bots/{bot_id}/documents/upload    # file upload
POST   /api/bots/{bot_id}/documents/url       # URL scrape
DELETE /api/documents/{doc_id}
GET    /api/documents/{doc_id}/status
```

### Chat
```
POST   /api/bots/{bot_id}/chat                # streaming response
GET    /api/bots/{bot_id}/conversations
GET    /api/conversations/{conv_id}/messages
```

### Datasources (Database Connections)
```
POST   /api/bots/{bot_id}/datasources         # add DB connection
GET    /api/bots/{bot_id}/datasources          # list connections
POST   /api/datasources/{ds_id}/test           # test connection
POST   /api/datasources/{ds_id}/sync           # sync schema to vector store
GET    /api/datasources/{ds_id}/schema         # view extracted schema
DELETE /api/datasources/{ds_id}                # remove connection
POST   /api/bots/{bot_id}/query-db             # natural language → SQL → answer
```

### Widget (Public)
```
GET    /api/widget/{bot_id}/config            # bot config for widget
POST   /api/widget/{bot_id}/chat              # widget chat endpoint
```

### Analytics
```
GET    /api/bots/{bot_id}/analytics
GET    /api/orgs/{org_id}/usage
```

---

## 7. Widget Integration

### Embed Code
```html
<!-- Floating bubble (default) -->
<script
  src="https://chat.yourapp.com/widget.js"
  data-bot-id="bot_xxxxx"
  data-position="bottom-right"
  data-theme="light"
  async>
</script>

<!-- Inline embed -->
<div id="chatbot-container"></div>
<script
  src="https://chat.yourapp.com/widget.js"
  data-bot-id="bot_xxxxx"
  data-target="#chatbot-container"
  data-mode="inline"
  async>
</script>
```

### Widget Security
1. **Domain Allowlist**: Widget only works on registered domains
2. **Rate Limiting**: Per-IP and per-session limits
3. **Bot Token**: Short-lived tokens for API calls
4. **CORS**: Strict origin checking

---

## 8. Non-Functional Requirements

### Performance
- Chat response start: < 500ms (time to first token)
- Document indexing: < 30s for 10-page PDF
- Widget load time: < 100ms (lazy-loaded)
- Vector search: < 50ms for 100K chunks

### Scalability
- Support 100 concurrent chat sessions per server
- Handle 1M+ document chunks per organization
- Horizontal scaling via container orchestration

### Security
- All data encrypted at rest (AES-256)
- TLS 1.3 for all connections
- No data leaves self-hosted infrastructure
- GDPR/SOC2 compliance-ready architecture

---

## 9. Development Phases

### Phase 1: MVP (Weeks 1-6)
- [x] Project setup, Docker environment
- [ ] User auth (email/password)
- [ ] Organization & bot CRUD
- [ ] File upload (PDF, TXT, DOCX, CSV, XLSX)
- [ ] Document parsing & chunking
- [ ] Configurable embedding generation & storage (Ollama or HuggingFace)
- [ ] Configurable chat LLM (SmolLM3-3B default, swappable)
- [ ] Basic RAG chat
- [ ] Simple dashboard UI
- [ ] Embeddable widget v1
- [ ] Basic analytics

### Phase 2: Production Ready (Weeks 7-10)
- [ ] URL scraping
- [ ] Database connection (Text2SQL with sqlcoder/Arctic models)
- [ ] Streaming responses
- [ ] Widget customization
- [ ] Domain restrictions
- [ ] Rate limiting
- [ ] Conversation history
- [ ] Usage tracking
- [ ] Billing integration (Stripe)

### Phase 3: Scale (Weeks 11-14)
- [ ] Team management
- [ ] Multiple model options
- [ ] Advanced analytics
- [ ] Webhook integrations
- [ ] White-label options
- [ ] API access for developers

---

## 10. Success Metrics

### Product Metrics
- Time to first bot: < 5 minutes
- Documents indexed successfully: > 95%
- Chat response relevance: > 80% (user feedback)

### Business Metrics
- Free → Paid conversion: > 5%
- Monthly churn: < 5%
- NPS: > 40

---

## Appendix A: Competitor Analysis

| Feature | Chatbase | CustomGPT | Botsonic | **Our Product** |
|---------|----------|-----------|----------|-----------------|
| Self-hosted | ❌ | ❌ | ❌ | ✅ |
| Data privacy | Cloud | Cloud | Cloud | **On-premise** |
| Starting price | $19/mo | $49/mo | $49/mo | **$29/mo** |
| Custom models | ❌ | ❌ | ❌ | ✅ |
| White-label | $399/mo | $299/mo | $249/mo | **$99/mo** |

Our differentiator: **True data privacy with self-hosted AI models.**
