.PHONY: install test lint run-pipeline setup-sheets webhook help

PYTHON := python
VENV   := .venv

# ── Setup ────────────────────────────────────────────────────────────────────

install:
	$(PYTHON) -m pip install -r requirements.txt

venv:
	$(PYTHON) -m venv $(VENV)
	$(VENV)/bin/pip install -r requirements.txt
	@echo "Activate with: source $(VENV)/bin/activate"

# ── Testing ──────────────────────────────────────────────────────────────────

test:
	$(PYTHON) -m pytest

test-v:
	$(PYTHON) -m pytest -v

test-cov:
	$(PYTHON) -m pytest --cov=src --cov-report=term-missing

# ── Pipeline ─────────────────────────────────────────────────────────────────

# Example: make run QUERIES="barbers in Toronto"
run:
	$(PYTHON) scripts/run_pipeline.py --queries $(QUERIES) --dry-run

# Example: make run-icp ICP="Local Service Businesses"
run-icp:
	$(PYTHON) scripts/run_pipeline.py --icp "$(ICP)" --dry-run

# ── Google Sheets setup ───────────────────────────────────────────────────────

# Example: make setup-sheets CREDS=path/to/service_account.json
setup-sheets:
	$(PYTHON) scripts/setup_sheets.py --credentials $(CREDS)

# ── Webhook server ────────────────────────────────────────────────────────────

webhook:
	$(PYTHON) scripts/webhook_server.py

webhook-public:
	$(PYTHON) scripts/webhook_server.py --host 0.0.0.0 --port 5000

# ── Utilities ────────────────────────────────────────────────────────────────

# Example: make personalize INPUT=leads.csv OUTPUT=out.csv
personalize:
	$(PYTHON) scripts/lead_personalizer.py --input $(INPUT) --output $(OUTPUT)

# Example: make classify-reply EMAIL=ceo@co.com REPLY="Let's chat"
classify-reply:
	$(PYTHON) scripts/reply_processor.py --email "$(EMAIL)" --reply "$(REPLY)"

# ── Help ─────────────────────────────────────────────────────────────────────

help:
	@echo "Available targets:"
	@echo "  install          Install Python dependencies"
	@echo "  venv             Create a virtualenv and install dependencies"
	@echo "  test             Run all tests"
	@echo "  test-v           Run tests with verbose output"
	@echo "  test-cov         Run tests with coverage report (requires pytest-cov)"
	@echo "  run              QUERIES='...' Run pipeline in dry-run mode"
	@echo "  run-icp          ICP='...' Run an ICP profile in dry-run mode"
	@echo "  setup-sheets     CREDS=... Initialize Google Sheets tabs and headers"
	@echo "  webhook          Start webhook server on localhost:5000"
	@echo "  webhook-public   Start webhook server on 0.0.0.0:5000"
	@echo "  personalize      INPUT=... OUTPUT=... Batch personalize a leads CSV"
	@echo "  classify-reply   EMAIL=... REPLY=... Classify a single reply"
