# AI Lead Generation System

Automated pipeline for scraping, enriching, personalizing, and sending cold outreach at scale using n8n, Apify, Claude/GPT, and Instantly.

**Pipeline:** Source (Apify) -> Enrich (Prospeo/Hunter) -> Personalize (Claude/GPT) -> Send (Instantly) -> Track (Google Sheets)

## Architecture

```
[Apify Scrapers] -> [n8n Orchestrator] -> [Email Enrichment APIs]
       -> [Claude/GPT Personalization] -> [Instantly Sending]
       -> [Google Sheets CRM] -> [Slack Alerts]
```

### Design Principles

- **AI researches, humans craft templates.** LLMs extract prospect details and generate personalized first lines, but the email structure uses proven human-written templates.
- **Waterfall enrichment.** Multiple email providers queried sequentially for 85-95% email validity vs ~40% from a single source.
- **Modular pipeline.** Each stage (scrape, enrich, personalize, send, track) is independent and can be swapped or run standalone.

## Project Structure

```
Lead-gen/
├── docker-compose.yml          # n8n + PostgreSQL deployment
├── requirements.txt            # Python dependencies
├── .env.example                # Environment variable template
│
├── src/                        # Core Python modules
│   ├── scraping/
│   │   ├── apify_google_maps.py    # Google Maps lead scraper
│   │   └── apollo_scraper.py       # Apollo.io B2B lead scraper
│   ├── enrichment/
│   │   └── waterfall.py            # Multi-provider email enrichment
│   ├── personalization/
│   │   ├── website_researcher.py   # GPT-4o website analysis
│   │   └── email_writer.py         # Claude first-line generation
│   ├── outreach/
│   │   └── instantly_client.py     # Instantly.ai API client
│   ├── crm/
│   │   └── sheets_crm.py          # Google Sheets CRM integration
│   ├── reply_handling/
│   │   └── classifier.py          # AI reply classification + routing
│   └── utils/
│       ├── config.py               # Environment configuration
│       ├── rate_limiter.py         # Rate limiting + retry logic
│       └── logger.py              # Centralized logging
│
├── scripts/                    # Standalone CLI scripts
│   ├── run_pipeline.py             # Full pipeline orchestrator
│   ├── lead_personalizer.py        # Batch CSV personalizer
│   └── reply_processor.py          # Reply classification tool
│
├── n8n_workflows/              # Importable n8n workflow JSONs
│   ├── 01_daily_lead_scraping.json
│   ├── 02_enrichment_personalization.json
│   └── 03_campaign_push_monitoring.json
│
├── templates/
│   └── email_sequences.json        # Proven email sequence templates
│
└── config/
    ├── icp_templates.json          # Ideal Customer Profile definitions
    ├── sending_limits.json         # Email sending safety limits
    ├── compliance.json             # CAN-SPAM / GDPR / CASL framework
    ├── dns_setup.md                # DNS configuration guide
    └── kpi_benchmarks.json         # Performance benchmarks + alerts
```

## Quick Start

### 1. Environment Setup

```bash
# Clone and enter the project
git clone <repo-url> && cd Lead-gen

# Copy environment template and fill in API keys
cp .env.example .env

# Install Python dependencies
pip install -r requirements.txt
```

### 2. Required API Keys

| Service | Purpose | Free Tier |
|---------|---------|-----------|
| Apify | Google Maps scraping | $5/month credit (~1,200 leads) |
| OpenAI | GPT-4o website analysis | Pay-per-use |
| Anthropic | Claude email personalization | Pay-per-use |
| Prospeo | Email enrichment + verification | $39/mo starter |
| Hunter.io | Email enrichment (fallback) | 25 lookups/month free |
| Instantly | Email sending + warm-up | $37/mo starter |
| Firecrawl | Website scraping | Free tier available |

### 3. Run the Pipeline (Python)

```bash
# Full pipeline with dry run (no emails sent)
python scripts/run_pipeline.py \
  --queries "barbers in Toronto" "dentists in Austin" \
  --dry-run

# Full pipeline with Instantly push
python scripts/run_pipeline.py \
  --queries "plumbers in NYC" \
  --output output/results.json

# Batch personalize a CSV
python scripts/lead_personalizer.py \
  --input enriched_leads.csv \
  --output personalized_leads.csv

# Classify replies
python scripts/reply_processor.py \
  --email "prospect@company.com" \
  --reply "Sounds interesting, let's chat next week"
```

### 4. Run with n8n (Recommended for Production)

```bash
# Start n8n + PostgreSQL
docker compose up -d

# Access n8n at http://localhost:5678
# Import workflows from n8n_workflows/ directory
```

**Workflow schedule:**
- `01_daily_lead_scraping.json` - Runs daily at 9 AM
- `02_enrichment_personalization.json` - Runs daily at 11 AM
- `03_campaign_push_monitoring.json` - Runs daily at 2 PM + webhook listener

## Cost Estimates

### Budget Stack ($150-400/month)

| Layer | Tool | Cost/mo |
|-------|------|---------|
| Orchestration | n8n (self-hosted) | $0 |
| Scraping | Apify | $0-49 |
| Enrichment | Prospeo + Hunter | $39-79 |
| AI | Claude API + GPT-4o | $20-50 |
| Sending | Instantly | $37-97 |
| CRM | Google Sheets | $0 |

**AI cost breakdown:** ~$2-5 per 1,000 leads for Claude Sonnet personalization. ~$0.50/1,000 leads for GPT-4o-mini research.

## Deliverability

Before sending any cold emails:

1. **DNS records** - Configure SPF, DKIM, DMARC on all sending domains (see `config/dns_setup.md`)
2. **Warm-up** - Run Instantly warm-up for 2-4 weeks before cold sending
3. **Verification** - Every email verified before sending (bounce rate must stay < 2%)
4. **Limits** - Never exceed 50 emails/inbox/day
5. **Tracking** - Disable open tracking (destroys deliverability)
6. **Format** - Plain text only, zero links in first email

## Compliance

This system includes compliance configurations for:
- **CAN-SPAM** (United States) - Opt-out model
- **GDPR** (EU) - Legitimate Interest basis for B2B
- **CASL** (Canada) - Implied consent for existing relationships

See `config/compliance.json` for full framework. Always consult with legal counsel before launching campaigns.

## KPI Targets

| Metric | Average | Good | Excellent |
|--------|---------|------|-----------|
| Reply Rate | 5-6% | 8-12% | 15%+ |
| Meeting Book Rate | 1-2% | 3-5% | 7%+ |
| Bounce Rate | < 3% | < 2% | < 1% |
| Cost per Meeting | $50+ | $30-50 | < $30 |

## Scaling Path

1. **Validation (100 leads/day)** - Run budget stack for 4 weeks, test 3 ICPs, find winning template (target: 8%+ reply rate)
2. **Growth (500 leads/day)** - Add Clay for enrichment, 5-10 more inboxes, LinkedIn parallel channel
3. **Scale (2,000+ leads/day)** - Clay Pro, 20-50 inboxes, intent data triggers, proper CRM

> Never scale sending faster than you can scale reply handling.
