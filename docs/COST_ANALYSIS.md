# Cost Analysis

> For detailed SaaS pricing tiers, see [PRICING.md](./PRICING.md)

## 1. Infrastructure Cost Analysis

### Self-Hosted (Your Own Server / VPS)

#### Option A: Budget Setup (Starting Out)
**Best for**: Development, testing, first 10 customers

| Component | Provider | Spec | Monthly Cost |
|-----------|----------|------|--------------|
| GPU Server | Hetzner / Vast.ai | RTX 3090 (24GB VRAM) | $100-150 |
| OR CPU-only | Hetzner AX41 | AMD Ryzen, 64GB RAM | $50-60 |
| Database | Same server | PostgreSQL + pgvector | $0 (included) |
| Redis | Same server | Redis | $0 (included) |
| Storage | Same server | 1TB NVMe | $0 (included) |
| CDN/Domain | Cloudflare | Free tier | $0 |
| **Total** | | | **$50-150/mo** |

#### Option B: Production Setup (10-100 customers)
**Best for**: Real customers with SLA requirements

| Component | Provider | Spec | Monthly Cost |
|-----------|----------|------|--------------|
| App Server | Hetzner CCX33 | 8 vCPU, 32GB RAM | $65 |
| GPU Server | RunPod / Lambda | A10 (24GB VRAM) | $200-300 |
| Database | Managed Postgres | 2 vCPU, 4GB, 100GB | $30-50 |
| Redis | Managed Redis | 1GB | $15 |
| Storage | S3/Backblaze B2 | 500GB | $5-10 |
| CDN | Cloudflare Pro | | $20 |
| Monitoring | Grafana Cloud | Free tier | $0 |
| **Total** | | | **$335-460/mo** |

#### Option C: Scale Setup (100+ customers)
**Best for**: Growing SaaS with enterprise customers

| Component | Provider | Spec | Monthly Cost |
|-----------|----------|------|--------------|
| App Servers (2x) | Hetzner CCX53 | 16 vCPU, 64GB each | $260 |
| GPU Cluster (2x) | RunPod | 2x A10G | $500-600 |
| Database | AWS RDS | db.r6g.large | $150 |
| Redis Cluster | AWS ElastiCache | cache.r6g.large | $100 |
| Storage | S3 | 2TB + transfer | $50 |
| Load Balancer | AWS ALB | | $25 |
| CDN | Cloudflare Business | | $200 |
| **Total** | | | **$1,285-1,385/mo** |

---

### AWS Full Cloud (For Comparison)

| Component | AWS Service | Spec | Monthly Cost |
|-----------|-------------|------|--------------|
| App Server | EC2 t3.xlarge | 4 vCPU, 16GB | $120 |
| GPU Instance | EC2 g5.xlarge | A10G, 24GB VRAM | $800+ |
| Database | RDS PostgreSQL | db.t3.medium | $65 |
| Redis | ElastiCache | cache.t3.micro | $15 |
| Storage | S3 | 100GB | $5 |
| **Total** | | | **$1,000+/mo** |

**Verdict**: AWS is 3-5x more expensive. Avoid for MVP unless you have funding.

---

## 2. Per-Customer Cost Breakdown

### Resource Usage Estimates

| Action | Resource | Cost per Unit |
|--------|----------|---------------|
| Embed 1 page (~500 tokens) | GPU compute | ~$0.0001 |
| 1 chat message (RAG) | GPU compute + DB | ~$0.001-0.003 |
| Store 1000 chunks | pgvector | ~$0.01/month |
| 1GB file storage | S3/MinIO | ~$0.02/month |

### Customer Tier Usage Patterns

| Tier | Docs/Month | Messages/Month | Storage | Monthly Cost to Serve |
|------|------------|----------------|---------|----------------------|
| Free | 5 | 100 | 10MB | ~$0.50 |
| Starter | 50 | 1,000 | 100MB | ~$2-3 |
| Pro | 500 | 10,000 | 1GB | ~$10-15 |
| Business | 2,000 | 50,000 | 10GB | ~$40-60 |

---

## 3. Model Recommendations (Cost-Optimized)

### For Your Use Case (Chatbot Only)

| Model | Size | VRAM | Quality | Speed | Recommendation |
|-------|------|------|---------|-------|----------------|
| **llama3.2:1b** | 1.3GB | 2GB | ⭐⭐ | ⭐⭐⭐⭐⭐ | Budget/high volume |
| **llama3.2:3b** | 2.0GB | 4GB | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | **Best value (MVP)** |
| Qwen2.5:3b | 2.0GB | 4GB | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | Multilingual option |
| Phi-3-mini | 2.3GB | 4GB | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ | Microsoft's small model |
| Mistral-7B | 4.1GB | 8GB | ⭐⭐⭐⭐ | ⭐⭐⭐ | Upgrade path |
| **Qwen2.5:7b** | 4.7GB | 8GB | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | **Best quality** |

### Embedding Models

| Model | Dimensions | Quality | Speed | Recommendation |
|-------|------------|---------|-------|----------------|
| all-MiniLM-L6-v2 | 384 | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ | Fallback |
| **nomic-embed-text** | 768 | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | **MVP choice** |
| mxbai-embed-large | 1024 | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | Premium tier |
| bge-m3 | 1024 | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | Multilingual |

### My Final Recommendation

```
MVP Stack:
├── Chat Model: llama3.2:3b (via Ollama)
├── Embed Model: nomic-embed-text (via Ollama)
└── Total VRAM needed: ~6GB (fits RTX 3060/3070)

Upgrade Path:
├── Chat Model: Qwen2.5:7b-instruct
├── Embed Model: bge-m3
└── Total VRAM needed: ~12GB (RTX 3090/4080)
```

---

## 4. Cost Optimization Tips

### Infrastructure
1. **Start with Hetzner** - 50-70% cheaper than AWS for same specs
2. **Use CPU for embeddings** - Much cheaper, only slightly slower
3. **GPU only for chat** - Share one GPU across all customers
4. **Batch embedding jobs** - Run during off-peak hours
5. **Cache frequent queries** - Redis for repeated questions

### Operations
1. **Quantized models** - Use Q4_K_M quantization (50% smaller, 95% quality)
2. **Connection pooling** - pgBouncer for database efficiency
3. **Lazy loading** - Only load models when needed
4. **CDN for widget** - Cloudflare free tier handles millions of requests

### Code-Level
```python
# Good: Batch embeddings
embeddings = await embed_batch(texts)  # One API call

# Bad: Individual embeddings
for text in texts:
    embedding = await embed_single(text)  # N API calls
```

---

## 5. Scaling Economics

### Unit Economics at Scale

| Scale | Users | MRR | Infra Cost | Gross Margin |
|-------|-------|-----|------------|--------------|
| Seed | 100 | $3,000 | $400 | 87% |
| Growth | 500 | $20,000 | $1,500 | 92% |
| Scale | 2,000 | $100,000 | $5,000 | 95% |

**Why margins improve at scale**:
- GPU utilization increases (shared resource)
- Database queries become more efficient with proper indexing
- CDN costs are flat regardless of traffic
- Support costs don't scale linearly

---

## 6. MVP Budget Recommendation

### Minimum Viable Budget (First 6 Months)

| Category | Monthly | 6-Month Total |
|----------|---------|---------------|
| Server (Hetzner) | $60 | $360 |
| Domain + SSL | $2 | $12 |
| Email (Resend) | $0 | $0 (free tier) |
| Monitoring | $0 | $0 (free tier) |
| Payment (Stripe) | 2.9% | Variable |
| **Total Fixed** | **$62** | **$372** |

### Recommended Starting Stack

```
1. Hetzner AX41-NVMe ($50/mo)
   - AMD Ryzen 5 3600
   - 64GB RAM
   - 2x 512GB NVMe
   - Runs: Ollama (CPU mode), Postgres, Redis, API, Frontend

2. OR Hetzner GPU Server ($100-150/mo)
   - RTX 3090 or RTX 4090
   - Much faster inference
   - Better user experience

3. Cloudflare (Free)
   - DNS, CDN, DDoS protection, SSL

4. Backblaze B2 ($5/mo)
   - File storage, S3-compatible

Total: $55-155/month to start
```

---

## Summary

| Decision | Recommendation |
|----------|----------------|
| **Chat Model** | llama3.2:3b (upgrade to Qwen2.5:7b later) |
| **Embed Model** | nomic-embed-text |
| **Hosting** | Hetzner (EU) or DigitalOcean (US) |
| **Database** | PostgreSQL + pgvector |
| **Starting Budget** | $60-150/month |
| **Target Margin** | 85%+ at scale |

> See [PRICING.md](./PRICING.md) for detailed SaaS pricing tiers and revenue projections.

Your friend's suggestions were mostly correct. The main adjustments:
1. **Skip AWS** for MVP - too expensive
2. **Use ARQ instead of Celery** - lighter, async-native
3. **Start with Hetzner** - best price/performance for this workload
4. **Qwen2.5:7b only if needed** - 3B models are sufficient for most chatbots
