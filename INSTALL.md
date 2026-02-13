# Installation & Usage Guide

Complete guide to setting up, configuring, and running the AI Lead Generation System.

---

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Installation](#installation)
3. [Configuration](#configuration)
4. [Running the Pipeline](#running-the-pipeline)
5. [Scripts Reference](#scripts-reference)
6. [n8n Workflow Setup](#n8n-workflow-setup)
7. [Suppression List & Compliance](#suppression-list--compliance)
8. [Monitoring & Alerts](#monitoring--alerts)
9. [Email Templates](#email-templates)
10. [Troubleshooting](#troubleshooting)
11. [Cost Management](#cost-management)

---

## Prerequisites

### System Requirements

- Python 3.11 or higher
- Docker and Docker Compose (for n8n workflows)
- Git

### Required API Accounts

Sign up for each service and obtain API keys:

| Service | Purpose | Sign-Up URL | Free Tier |
|---------|---------|-------------|-----------|
| **Apify** | Google Maps scraping | https://apify.com | $5/month credit (~1,200 leads) |
| **OpenAI** | GPT-4o website analysis | https://platform.openai.com | Pay-per-use |
| **Anthropic** | Claude email personalization | https://console.anthropic.com | Pay-per-use |
| **Prospeo** | Email enrichment + verification | https://prospeo.io | $39/mo starter |
| **Hunter.io** | Email enrichment (fallback) | https://hunter.io | 25 lookups/month free |
| **Instantly** | Email sending + warm-up | https://instantly.ai | $37/mo starter |
| **Firecrawl** | Website scraping | https://firecrawl.dev | Free tier available |

### Optional Services

| Service | Purpose |
|---------|---------|
| **Google Sheets API** | Lightweight CRM tracking |
| **Slack** | Real-time alerts for hot leads |

---

## Installation

### Step 1: Clone the Repository

```bash
git clone <repo-url>
cd Lead-gen
```

### Step 2: Create a Virtual Environment

```bash
python -m venv venv
source venv/bin/activate   # Linux/macOS
# or
venv\Scripts\activate      # Windows
```

### Step 3: Install Dependencies

```bash
pip install -r requirements.txt
```

### Step 4: Configure Environment Variables

```bash
cp .env.example .env
```

Open `.env` and fill in your API keys (see [Configuration](#configuration) below).

### Step 5: Validate Setup

Run the health check to verify all API keys are working:

```bash
python scripts/health_check.py
```

Expected output:

```
[OK] Apify: authenticated successfully.
[OK] OpenAI: authenticated successfully.
[OK] Anthropic: key format valid.
[OK] Prospeo: API key accepted.
[OK] Hunter.io: authenticated successfully.
[OK] Instantly: authenticated successfully.
=== Results: 6/6 checks passed ===
All API keys validated successfully.
```

### Step 6: Run Tests

```bash
python -m pytest tests/ -v
```

All 25 tests should pass.

---

## Configuration

### Required Environment Variables

Edit your `.env` file with real values for these keys:

```bash
# Core API Keys (all required)
APIFY_API_TOKEN=apify_api_xxx
OPENAI_API_KEY=sk-xxx
ANTHROPIC_API_KEY=sk-ant-xxx
PROSPEO_API_KEY=xxx
HUNTER_API_KEY=xxx
INSTANTLY_API_KEY=xxx
INSTANTLY_CAMPAIGN_ID=xxx
```

### Optional Environment Variables

```bash
# Google Sheets CRM
GOOGLE_SHEETS_SPREADSHEET_ID=your_spreadsheet_id
# You also need a service account JSON file for Google Sheets

# Firecrawl (website scraping for personalization)
FIRECRAWL_API_KEY=fc-xxx

# Slack (real-time alerts)
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/XXX/YYY/ZZZ
```

### AI Model Configuration

Change models globally without modifying code:

```bash
# Default: claude-sonnet-4-20250514
CLAUDE_MODEL=claude-sonnet-4-20250514

# Default: gpt-4o
OPENAI_MODEL=gpt-4o
```

### Pipeline Tuning

```bash
# Maximum leads scraped per search query (default: 100)
MAX_LEADS_PER_SEARCH=100

# Batch size for enrichment processing (default: 20)
ENRICHMENT_BATCH_SIZE=20

# Max emails per inbox per day — never exceed 50 (default: 50)
MAX_EMAILS_PER_INBOX_PER_DAY=50

# Concurrency for async operations (default: 10)
ASYNC_CONCURRENCY=10
```

### API Timeouts

```bash
# Short timeout for quick lookups (default: 15s)
API_TIMEOUT_SHORT=15

# Long timeout for AI calls and scraping (default: 60s)
API_TIMEOUT_LONG=60
```

### Google Sheets Setup (Optional)

If using Google Sheets as a CRM:

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a project and enable the Google Sheets API
3. Create a Service Account and download the JSON credentials
4. Share your spreadsheet with the service account email
5. Set `GOOGLE_SHEETS_SPREADSHEET_ID` in `.env`

The spreadsheet should have three tabs:
- **Raw Leads** — scraped lead data
- **Enriched Leads** — leads with verified emails and AI personalization
- **Campaign Tracker** — outreach status and replies

---

## Running the Pipeline

### Full Pipeline (Recommended Start)

Run with `--dry-run` first to test without sending emails:

```bash
python scripts/run_pipeline.py \
  --queries "barbers in Toronto" "dentists in Austin" \
  --dry-run
```

This will:
1. Scrape Google Maps for leads matching your queries
2. Filter against the suppression list
3. Enrich emails via Prospeo and Hunter.io waterfall
4. Verify all email addresses
5. Scrape prospect websites for personalization data
6. Generate AI-personalized first lines with Claude
7. Save results to `output/pipeline_results_<timestamp>.json`
8. Log estimated API costs

### Full Pipeline with Outreach

Once you've verified the output looks correct:

```bash
python scripts/run_pipeline.py \
  --queries "plumbers in NYC" \
  --output output/nyc_plumbers.json
```

This pushes verified, personalized leads to your Instantly campaign.

### Custom Output Location

```bash
python scripts/run_pipeline.py \
  --queries "landscaping in Miami" \
  --output results/miami_landscapers.json
```

### Skip Outreach (Save Results Only)

```bash
python scripts/run_pipeline.py \
  --queries "auto repair in Chicago" \
  --skip-outreach
```

### Pipeline Stages

The pipeline runs these stages in order:

```
Stage 1: Scraping (Apify Google Maps)
  └─ Stage 1b: Suppression Filter
Stage 2: Email Enrichment & Verification (Prospeo → Hunter.io waterfall)
Stage 3: Website Research (Firecrawl) + AI Personalization (Claude)
Stage 4: Push to Outreach (Instantly)
Summary: Cost tracking + pipeline metrics
```

### Pipeline Output Format

The output JSON contains an array of lead objects:

```json
[
  {
    "business_name": "Joe's Barbershop",
    "email": "joe@joesbarbershop.com",
    "phone": "+14165551234",
    "website": "https://joesbarbershop.com",
    "address": "123 Queen St W, Toronto",
    "rating": 4.7,
    "review_count": 342,
    "category": "Barber shop",
    "city": "Toronto",
    "email_verified": true,
    "enrichment_source": "prospeo",
    "main_service": "Men's grooming and haircuts",
    "specific_detail": "Recently expanded to a second location on King St",
    "pain_point": "Managing online bookings across two locations",
    "tech_stack": "Squarespace, Square Appointments",
    "ai_first_line": "Congrats on the King St expansion — managing bookings across two spots must be keeping you busy."
  }
]
```

---

## Scripts Reference

### `scripts/run_pipeline.py` — Full Pipeline

```bash
python scripts/run_pipeline.py --queries "QUERY1" "QUERY2" [OPTIONS]

Options:
  --queries, -q    Search queries (required, one or more)
  --dry-run        Run pipeline but don't push to Instantly
  --skip-outreach  Skip the Instantly push step
  --output, -o     Custom output file path
```

### `scripts/lead_personalizer.py` — Batch CSV Personalizer

Personalize a CSV of pre-enriched leads:

```bash
python scripts/lead_personalizer.py \
  --input enriched_leads.csv \
  --output personalized_leads.csv \
  --delay 1.0

Options:
  --input, -i    Input CSV path (required)
  --output, -o   Output CSV path (default: personalized_leads.csv)
  --delay, -d    Delay between API calls in seconds (default: 1.0)
```

The input CSV should have columns: `business_name`, `specific_detail`, `pain_point`.
The output CSV adds an `ai_first_line` column.

### `scripts/reply_processor.py` — Reply Classifier

Classify a single reply:

```bash
python scripts/reply_processor.py \
  --email "prospect@company.com" \
  --reply "Sounds interesting, let's chat next week"
```

Batch process a CSV of replies:

```bash
python scripts/reply_processor.py \
  --csv replies.csv \
  --output classified_replies.json
```

The CSV should have columns: `email`, `reply_body`.

Reply categories:
| Category | Action |
|----------|--------|
| `INTERESTED` | Slack alert to sales team |
| `MEETING_REQUEST` | Slack alert (high priority) |
| `QUESTION` | AI-drafted response for human review |
| `NOT_INTERESTED` | Log and remove from campaign |
| `OUT_OF_OFFICE` | Reschedule follow-up |
| `UNSUBSCRIBE` | Add to suppression list |

### `scripts/health_check.py` — API Validation

```bash
python scripts/health_check.py
```

Validates all 6 API keys and reports pass/fail status. Run this before every pipeline execution to catch expired keys or connectivity issues early.

---

## n8n Workflow Setup

For production use, n8n provides scheduled, automated execution.

### Step 1: Start n8n

```bash
docker compose up -d
```

This starts:
- **n8n** on `http://localhost:5678`
- **PostgreSQL** for workflow persistence

### Step 2: Access n8n Dashboard

Open `http://localhost:5678` in your browser. Login with the credentials from `.env`:

```
Username: admin (N8N_BASIC_AUTH_USER)
Password: your_password (N8N_BASIC_AUTH_PASSWORD)
```

### Step 3: Import Workflows

Import each JSON file from the `n8n_workflows/` directory:

1. Click **Workflows** → **Import from File**
2. Import `01_daily_lead_scraping.json`
3. Import `02_enrichment_personalization.json`
4. Import `03_campaign_push_monitoring.json`

### Step 4: Configure Credentials in n8n

For each workflow, add your API credentials through the n8n UI:

1. Go to **Settings** → **Credentials**
2. Add credentials for: Apify, OpenAI, Anthropic, Prospeo, Hunter, Instantly, Google Sheets

### Step 5: Activate Workflows

Toggle each workflow to **Active**. Default schedule:

| Workflow | Schedule | Purpose |
|----------|----------|---------|
| `01_daily_lead_scraping` | Daily at 9:00 AM | Scrape new leads |
| `02_enrichment_personalization` | Daily at 11:00 AM | Enrich and personalize |
| `03_campaign_push_monitoring` | Daily at 2:00 PM + webhook | Push to Instantly, monitor replies |

### Stopping n8n

```bash
docker compose down       # Stop containers (data preserved)
docker compose down -v    # Stop and delete all data (destructive)
```

---

## Suppression List & Compliance

### Overview

The suppression list prevents emailing people who have opted out. This is legally required under CAN-SPAM, GDPR, and CASL.

### How It Works

The suppression list is stored at `data/suppression_list.json` (configurable via `SUPPRESSION_FILE` env var). Every pipeline run automatically:

1. Loads the suppression list
2. Filters out suppressed emails before enrichment
3. Logs how many leads were suppressed

### Managing the Suppression List

**Programmatically:**

```python
from src.compliance.suppression import SuppressionManager

mgr = SuppressionManager()

# Add a single email
mgr.add("unsubscribed@example.com", reason="unsubscribe", source="instantly")

# Check if suppressed
mgr.is_suppressed("unsubscribed@example.com")  # True

# Bulk import
mgr.bulk_add([
    {"email": "bounce1@test.com", "reason": "hard_bounce"},
    {"email": "spam@test.com", "reason": "spam_complaint"},
])

# Filter a list of leads
allowed, suppressed = mgr.filter_leads(leads)

# Export for auditing
entries = mgr.export()
```

### Suppression Reasons

| Reason | Source |
|--------|--------|
| `unsubscribe` | Prospect clicked unsubscribe |
| `hard_bounce` | Email address doesn't exist |
| `spam_complaint` | Prospect marked email as spam |
| `manual` | Manually added (e.g., competitor, partner) |
| `not_interested` | Replied with explicit rejection |

### Compliance Reference

See `config/compliance.json` for the full CAN-SPAM, GDPR, and CASL framework. Key requirements:

- Include unsubscribe link in every email
- Honor unsubscribe requests within 24 hours
- Only email business addresses (never personal)
- Include your physical business address
- Maintain suppression list across ALL campaigns

---

## Monitoring & Alerts

### Campaign Health Monitoring

The pipeline automatically checks campaign health before pushing new leads. Alerts fire when:

| Metric | Threshold | Action |
|--------|-----------|--------|
| Bounce rate | > 2% | Pause campaign, clean email list |
| Unsubscribe rate | > 2% | Review targeting and copy |
| Reply rate | < 3% (after 500+ sends) | A/B test new templates |

### Slack Alerts

If `SLACK_WEBHOOK_URL` is configured, you'll receive Slack notifications for:

- Hot leads (INTERESTED or MEETING_REQUEST replies)
- Campaign health alerts
- Bounce rate warnings

### Cost Tracking

Every pipeline run logs estimated API costs to `data/cost_log.json`. View the summary in pipeline logs:

```
Cost summary: 157 calls, $2.3400 estimated total.
  apify_gmaps: 2 calls, $0.0082
  claude_sonnet: 45 calls, $0.1350
  firecrawl_scrape: 45 calls, $0.4500
  openai_gpt4o: 45 calls, $0.2250
  prospeo_search: 50 calls, $0.5000
  prospeo_verify: 50 calls, $0.2500
```

### KPI Benchmarks

Target metrics for cold email campaigns (from `config/kpi_benchmarks.json`):

| Metric | Average | Good | Excellent |
|--------|---------|------|-----------|
| Open Rate | 42% | 55% | 65%+ |
| Reply Rate | 5.5% | 10% | 15%+ |
| Meeting Book Rate | 1.5% | 4% | 7%+ |
| Bounce Rate | < 3% | < 2% | < 1% |
| Cost per Meeting | $50+ | $30-50 | < $30 |

---

## Email Templates

Email sequence templates are in `templates/email_sequences.json`. Two templates are included:

### Standard B2B Outreach (3-email sequence)

| Email | Delay | Purpose |
|-------|-------|---------|
| #1 | Day 0 | AI-personalized opener + value prop |
| #2 | Day 3 | Case study follow-up |
| #3 | Day 10 | Soft breakup email |

### Local Business Outreach (3-email sequence)

| Email | Delay | Purpose |
|-------|-------|---------|
| #1 | Day 0 | Website-specific opener + local angle |
| #2 | Day 3 | Local success story |
| #3 | Day 10 | Friendly close |

### Template Variables

These variables are automatically filled by the pipeline:

| Variable | Source |
|----------|--------|
| `{{ai_personalized_first_line}}` | Claude AI (per lead) |
| `{{business_name}}` | Apify scraping |
| `{{category}}` | Apify scraping |
| `{{city}}` | Apify scraping |
| `{{pain_point}}` | GPT-4o website analysis |
| `{{specific_detail}}` | GPT-4o website analysis |

### Best Practices

- Send **Tuesday-Thursday at 10 AM** local time (40% higher response)
- **Zero links** in email #1
- **Plain text only** (no HTML or images)
- **Disable open tracking** (kills deliverability)
- Always include **unsubscribe link**

---

## Troubleshooting

### Common Issues

**`EnvironmentError: Missing required environment variable`**

```bash
# Verify your .env file exists and has all required keys
cat .env | grep -c "="
# Should show at least 7 key-value pairs

# Run health check
python scripts/health_check.py
```

**`HTTP 401 Unauthorized` from any API**

Your API key is invalid or expired. Check the specific service dashboard and update `.env`.

**`HTTP 429 Too Many Requests`**

You're hitting rate limits. The system retries automatically with exponential backoff, but if persistent:

```bash
# Increase delay between calls
API_RATE_LIMIT_DELAY=2
```

**Apify run times out**

Increase the Apify polling timeout or reduce the number of leads per search:

```bash
MAX_LEADS_PER_SEARCH=50
```

**No leads found after enrichment**

- Check if Prospeo/Hunter credits are exhausted
- Verify the search queries return results on Google Maps
- Try broader queries (e.g., "restaurants in Toronto" instead of "vegan restaurants in downtown Toronto")

**Empty AI first lines**

- Verify Anthropic API key is valid
- Check that leads have `specific_detail` and `pain_point` from website research
- If Firecrawl key is missing, website research returns empty data

### Log Files

All logs are written to the `logs/` directory:

| File | Content |
|------|---------|
| `logs/pipeline.log` | Full pipeline execution logs |
| `logs/personalizer.log` | Batch personalization logs |
| `logs/replies.log` | Reply processing logs |

### Checking API Costs

```bash
# View cost log
cat data/cost_log.json | python -m json.tool
```

---

## Cost Management

### Estimated Cost Per 1,000 Leads

| Service | Cost |
|---------|------|
| Apify (scraping) | $4.10 |
| Prospeo (enrichment) | $10.00 |
| Prospeo (verification) | $5.00 |
| Hunter.io (fallback) | $15.00 |
| Firecrawl (website scrape) | $10.00 |
| OpenAI GPT-4o (analysis) | $5.00 |
| Claude Sonnet (personalization) | $3.00 |
| **Total** | **~$35-50** |

### Cost Optimization Tips

1. **Skip Firecrawl for leads without websites** — the pipeline already does this
2. **Use Hunter.io only as fallback** — Prospeo is checked first in the waterfall
3. **Run dry-run first** — catch issues before spending on enrichment
4. **Set `MAX_LEADS_PER_SEARCH`** wisely — start with 50, scale up
5. **Monitor `data/cost_log.json`** — track spend per session

### Monthly Budget Guide

| Scale | Leads/Month | Estimated Cost |
|-------|-------------|----------------|
| Testing | 500 | $25-50 |
| Validation | 2,000 | $100-150 |
| Growth | 10,000 | $400-600 |
| Scale | 50,000 | $1,800-2,500 |

---

## Project Structure

```
Lead-gen/
├── src/                           # Core Python modules
│   ├── scraping/
│   │   ├── apify_google_maps.py       # Google Maps lead scraper
│   │   └── apollo_scraper.py          # Apollo.io B2B lead scraper
│   ├── enrichment/
│   │   └── waterfall.py               # Multi-provider email enrichment
│   ├── personalization/
│   │   ├── website_researcher.py      # GPT-4o website analysis
│   │   └── email_writer.py            # Claude first-line generation
│   ├── outreach/
│   │   └── instantly_client.py        # Instantly.ai API client
│   ├── crm/
│   │   └── sheets_crm.py             # Google Sheets CRM
│   ├── reply_handling/
│   │   └── classifier.py             # AI reply classification
│   ├── compliance/
│   │   └── suppression.py            # Suppression list manager
│   ├── monitoring/
│   │   ├── campaign_monitor.py        # Campaign health monitoring
│   │   └── cost_tracker.py            # API cost tracking
│   └── utils/
│       ├── config.py                  # Centralized configuration
│       ├── logger.py                  # Logging with secrets masking
│       ├── rate_limiter.py            # Rate limiting + smart retry
│       └── validators.py             # Email/URL/phone validation
│
├── scripts/                       # CLI scripts
│   ├── run_pipeline.py                # Full pipeline orchestrator
│   ├── lead_personalizer.py           # Batch CSV personalizer
│   ├── reply_processor.py            # Reply classifier
│   └── health_check.py               # API key validator
│
├── tests/                         # Test suite
│   ├── test_validators.py
│   ├── test_suppression.py
│   ├── test_cost_tracker.py
│   └── test_campaign_monitor.py
│
├── n8n_workflows/                 # n8n automation workflows
│   ├── 01_daily_lead_scraping.json
│   ├── 02_enrichment_personalization.json
│   └── 03_campaign_push_monitoring.json
│
├── templates/
│   └── email_sequences.json           # Email sequence templates
│
├── config/
│   ├── icp_templates.json             # Ideal Customer Profiles
│   ├── sending_limits.json            # Sending safety limits
│   ├── compliance.json                # Legal compliance framework
│   ├── kpi_benchmarks.json            # Performance benchmarks
│   └── dns_setup.md                   # DNS configuration guide
│
├── docker-compose.yml             # n8n + PostgreSQL
├── requirements.txt               # Python dependencies
├── .env.example                   # Environment template
└── INSTALL.md                     # This file
```
