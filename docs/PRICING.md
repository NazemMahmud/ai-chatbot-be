# SaaS Pricing Model

## Pricing Strategy

**Model**: Tiered pricing with soft usage limits (overage charges or throttling)

**Why This Model**:
- Predictable revenue for you
- Predictable costs for customers
- Scales with value delivered
- Easy to understand

---

## Pricing Tiers

### Free Tier (Lead Generation)
**Price**: $0/month

| Feature   | Limit                        |
|-----------|------------------------------|
| Bots      | 1                            |
| Messages  | 50/month                     |
| Documents | 5 (max 5MB each)             |
| Storage   | 10MB                         |
| Branding  | "Powered by YourBrand" badge |
| Support   | Community                    |

**Purpose**: Let users try the product, collect leads, build trust

---

### Starter Tier (Hobbyist / Small Business)
**Price**: $29/month (or $290/year = 2 months free)

| Feature   | Limit                        |
|-----------|------------------------------|
| Bots      | 2                            |
| Messages  | 1,000/month                  |
| Documents | 100                          |
| Storage   | 500MB                        |
| Analytics | Basic                        |
| Branding  | "Powered by YourBrand" badge |
| Support   | Email (48h response)         |

**Overage**: $0.01/message after limit

**Target**: Personal blogs, small businesses, indie hackers

---

### Pro Tier (Growing Business)
**Price**: $79/month (or $790/year)

| Feature      | Limit                |
|--------------|----------------------|
| Bots         | 5                    |
| Messages     | 10,000/month         |
| Documents    | 500                  |
| Storage      | 5GB                  |
| Analytics    | Advanced             |
| Branding     | Custom (no badge)    |
| API Access   | ✅                    |
| URL Scraping | ✅                    |
| Support      | Priority email (24h) |

**Overage**: $0.005/message after limit

**Target**: E-commerce, SaaS documentation, growing startups

---

### Business Tier (Teams / Agencies)
**Price**: $199/month (or $1,990/year)

| Feature      | Limit              |
|--------------|--------------------|
| Bots         | 20                 |
| Messages     | 50,000/month       |
| Documents    | 2,000              |
| Storage      | 25GB               |
| Team Members | 5 seats            |
| Analytics    | Full + exports     |
| Branding     | White-label widget |
| API Access   | ✅                  |
| Webhooks     | ✅                  |
| Support      | Phone + dedicated  |

**Overage**: $0.003/message after limit

**Target**: Agencies, mid-market companies, multi-brand businesses

---

### Enterprise (Custom)
**Price**: Custom ($500+/month)

| Feature        | Offering                  |
|----------------|---------------------------|
| Bots           | Unlimited                 |
| Messages       | Custom limits             |
| Infrastructure | Dedicated (optional)      |
| SLA            | 99.9% uptime guarantee    |
| Integrations   | Custom development        |
| Deployment     | On-premise option         |
| Support        | Dedicated account manager |
| Security       | SOC2, HIPAA compliance    |

**Target**: Healthcare, finance, legal, large enterprises

---

## Competitor Comparison

| Feature            | Chatbase   | CustomGPT  | Botsonic   | **YourProduct** |
|--------------------|------------|------------|------------|-----------------|
| Free tier          | ✅          | ✅          | ✅          | ✅               |
| Starting price     | $19        | $49        | $49        | **$29**         |
| Self-hosted        | ❌          | ❌          | ❌          | **✅**           |
| Data privacy       | Cloud only | Cloud only | Cloud only | **On-premise**  |
| Messages (starter) | 2,000      | 1,000      | 1,000      | 1,000           |
| White-label        | $399       | $299       | $249       | **$199**        |
| API access         | $99        | $99        | $99        | **$79**         |
| Custom models      | ❌          | ❌          | ❌          | **✅**           |

**Your Differentiator**: Privacy + Self-hosted = Premium positioning at competitive price

---

## Revenue Projections

### Conservative Growth Scenario

| Month | Free Users | Paid Users | MRR    | Costs | Profit |
|-------|------------|------------|--------|-------|--------|
| 1     | 50         | 0          | $0     | $150  | -$150  |
| 2     | 100        | 2          | $58    | $150  | -$92   |
| 3     | 200        | 5          | $145   | $200  | -$55   |
| 4     | 350        | 10         | $350   | $250  | $100   |
| 5     | 500        | 20         | $750   | $350  | $400   |
| 6     | 700        | 35         | $1,400 | $450  | $950   |
| 12    | 2,000      | 150        | $6,500 | $800  | $5,700 |

**Assumptions**:
- 5% free-to-paid conversion
- Tier distribution: 30% Starter, 50% Pro, 20% Business
- 3% monthly churn
- Infrastructure scales with usage

---

## Break-Even Analysis

| Infrastructure Setup   | Monthly Cost | Paid Users Needed  |
|------------------------|--------------|--------------------|
| Budget (Hetzner basic) | $60          | 2 Starter          |
| MVP (Hetzner + GPU)    | $150         | 3 Starter or 2 Pro |
| Production             | $400         | 6 Pro              |
| Scale                  | $1,300       | 7 Business         |

**You break even with ~5-10 paying customers**

---

## Unit Economics

### Cost to Serve per Customer

| Tier            | Infra Cost | Gross Margin |
|-----------------|------------|--------------|
| Free            | ~$0.50/mo  | N/A          |
| Starter ($29)   | ~$2-3/mo   | **90%**      |
| Pro ($79)       | ~$10-15/mo | **85%**      |
| Business ($199) | ~$40-60/mo | **75%**      |

### LTV Calculation (12-month avg)

| Tier     | Monthly | Retention | LTV    |
|----------|---------|-----------|--------|
| Starter  | $29     | 8 months  | $232   |
| Pro      | $79     | 12 months | $948   |
| Business | $199    | 18 months | $3,582 |

### CAC Targets

| Tier     | LTV    | Target CAC | LTV:CAC |
|----------|--------|------------|---------|
| Starter  | $232   | < $50      | 4.6:1   |
| Pro      | $948   | < $200     | 4.7:1   |
| Business | $3,582 | < $700     | 5.1:1   |

---

## Pricing Psychology Tips

1. **Anchor high**: Show Enterprise first on pricing page
2. **Highlight Pro**: Most popular badge (best margin)
3. **Annual discount**: 2 months free drives commitment
4. **Free tier limits**: Enough to try, not enough to stay
5. **Overage pricing**: Decreases with tier (rewards upgrades)

---

## Implementation Checklist

- [ ] Stripe account setup
- [ ] Create products & prices in Stripe
- [ ] Implement subscription webhooks
- [ ] Usage tracking (messages, storage)
- [ ] Overage calculation logic
- [ ] Upgrade/downgrade flows
- [ ] Invoice generation
- [ ] Cancellation flow with feedback
