"""Tests for the CLI scripts (lead_personalizer, reply_processor, run_pipeline)."""

import csv
import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

# Ensure google stack is mocked before any script importing sheets_crm is loaded
import tests.test_crm  # noqa: F401 — triggers google-stack mock as a side effect

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


# ---------------------------------------------------------------------------
# lead_personalizer.py tests
# ---------------------------------------------------------------------------

class TestLeadPersonalizer:
    def _write_csv(self, path, rows, fieldnames=None):
        if fieldnames is None:
            fieldnames = list(rows[0].keys()) if rows else []
        with open(path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

    def test_process_csv_writes_output(self):
        from scripts.lead_personalizer import process_csv

        leads = [
            {"business_name": "Co A", "specific_detail": "x", "pain_point": "y"},
            {"business_name": "Co B", "specific_detail": "a", "pain_point": "b"},
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            input_path = os.path.join(tmpdir, "in.csv")
            output_path = os.path.join(tmpdir, "out.csv")
            self._write_csv(input_path, leads)

            with patch("scripts.lead_personalizer.get_config"), \
                 patch("scripts.lead_personalizer.EmailWriter") as MockWriter:
                writer_instance = MockWriter.return_value
                writer_instance.personalize_lead.side_effect = lambda l: {
                    **l, "ai_first_line": f"Line for {l['business_name']}"
                }

                process_csv(input_path, output_path, delay=0)

            assert os.path.exists(output_path)
            with open(output_path, newline="") as f:
                rows = list(csv.DictReader(f))
            assert len(rows) == 2
            assert rows[0]["ai_first_line"] == "Line for Co A"
            assert "ai_first_line" in rows[0]

    def test_process_csv_adds_ai_first_line_column(self):
        from scripts.lead_personalizer import process_csv

        leads = [{"business_name": "Shop", "specific_detail": "d", "pain_point": "p"}]

        with tempfile.TemporaryDirectory() as tmpdir:
            input_path = os.path.join(tmpdir, "in.csv")
            output_path = os.path.join(tmpdir, "out.csv")
            self._write_csv(input_path, leads)

            with patch("scripts.lead_personalizer.get_config"), \
                 patch("scripts.lead_personalizer.EmailWriter") as MockWriter:
                MockWriter.return_value.personalize_lead.side_effect = lambda l: {
                    **l, "ai_first_line": "Generated."
                }
                process_csv(input_path, output_path, delay=0)

            with open(output_path, newline="") as f:
                reader = csv.DictReader(f)
                assert "ai_first_line" in reader.fieldnames

    def test_process_csv_handles_personalization_error(self):
        from scripts.lead_personalizer import process_csv

        leads = [{"business_name": "Broken", "specific_detail": "x", "pain_point": "y"}]

        with tempfile.TemporaryDirectory() as tmpdir:
            input_path = os.path.join(tmpdir, "in.csv")
            output_path = os.path.join(tmpdir, "out.csv")
            self._write_csv(input_path, leads)

            with patch("scripts.lead_personalizer.get_config"), \
                 patch("scripts.lead_personalizer.EmailWriter") as MockWriter:
                MockWriter.return_value.personalize_lead.side_effect = Exception("API error")
                process_csv(input_path, output_path, delay=0)

            with open(output_path, newline="") as f:
                rows = list(csv.DictReader(f))
            assert rows[0]["ai_first_line"] == ""


# ---------------------------------------------------------------------------
# reply_processor.py tests
# ---------------------------------------------------------------------------

class TestReplyProcessor:
    def test_process_single_returns_result(self):
        from scripts.reply_processor import process_single

        with patch("scripts.reply_processor.get_config"), \
             patch("scripts.reply_processor.ReplyClassifier") as MockCls:
            MockCls.return_value.process_reply.return_value = {
                "email": "a@b.com",
                "category": "INTERESTED",
                "action": "slack_alert",
            }
            result = process_single("a@b.com", "Let's connect!")

        assert result["category"] == "INTERESTED"
        assert result["action"] == "slack_alert"

    def test_process_csv_classifies_all_rows(self):
        from scripts.reply_processor import process_csv

        rows = [
            {"email": "a@co.com", "reply_body": "Yes please"},
            {"email": "b@co.com", "reply_body": "Not interested"},
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = os.path.join(tmpdir, "replies.csv")
            with open(csv_path, "w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=["email", "reply_body"])
                writer.writeheader()
                writer.writerows(rows)

            with patch("scripts.reply_processor.get_config"), \
                 patch("scripts.reply_processor.ReplyClassifier") as MockCls:
                MockCls.return_value.process_reply.side_effect = [
                    {"email": "a@co.com", "category": "INTERESTED", "action": "slack_alert"},
                    {"email": "b@co.com", "category": "NOT_INTERESTED", "action": "log_and_remove"},
                ]
                results = process_csv(csv_path)

        assert len(results) == 2
        categories = {r["category"] for r in results}
        assert "INTERESTED" in categories
        assert "NOT_INTERESTED" in categories

    def test_process_csv_skips_rows_missing_fields(self):
        from scripts.reply_processor import process_csv

        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = os.path.join(tmpdir, "replies.csv")
            with open(csv_path, "w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=["email", "reply_body"])
                writer.writeheader()
                writer.writerow({"email": "", "reply_body": "hi"})   # missing email
                writer.writerow({"email": "a@b.com", "reply_body": ""})  # missing body

            with patch("scripts.reply_processor.get_config"), \
                 patch("scripts.reply_processor.ReplyClassifier"):
                results = process_csv(csv_path)

        assert results == []

    def test_process_csv_writes_json_output(self):
        from scripts.reply_processor import process_csv

        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = os.path.join(tmpdir, "replies.csv")
            output_path = os.path.join(tmpdir, "out.json")
            with open(csv_path, "w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=["email", "reply_body"])
                writer.writeheader()
                writer.writerow({"email": "x@y.com", "reply_body": "Interested!"})

            with patch("scripts.reply_processor.get_config"), \
                 patch("scripts.reply_processor.ReplyClassifier") as MockCls:
                MockCls.return_value.process_reply.return_value = {
                    "email": "x@y.com", "category": "INTERESTED", "action": "slack_alert"
                }
                process_csv(csv_path, output_path)

            assert os.path.exists(output_path)
            with open(output_path) as f:
                data = json.load(f)
            assert len(data) == 1
            assert data[0]["category"] == "INTERESTED"


# ---------------------------------------------------------------------------
# run_pipeline.py tests
# ---------------------------------------------------------------------------

class TestRunPipeline:
    def _make_leads(self, n=2):
        return [
            {
                "email": f"lead{i}@co.com",
                "business_name": f"Company {i}",
                "website": f"https://co{i}.com",
                "email_verified": True,
            }
            for i in range(n)
        ]

    @patch("scripts.run_pipeline.InstantlyClient")
    @patch("scripts.run_pipeline.EmailWriter")
    @patch("scripts.run_pipeline.WebsiteResearcher")
    @patch("scripts.run_pipeline.EmailEnricher")
    @patch("scripts.run_pipeline.GoogleMapsScraper")
    @patch("scripts.run_pipeline.get_config")
    def test_pipeline_dry_run_skips_outreach(
        self, mock_cfg, mock_scraper_cls, mock_enricher_cls,
        mock_researcher_cls, mock_writer_cls, mock_instantly_cls
    ):
        from scripts.run_pipeline import run_pipeline

        mock_scraper_cls.return_value.scrape.return_value = self._make_leads()
        mock_enricher_cls.return_value.process_batch.return_value = self._make_leads()
        mock_researcher_cls.return_value.research.return_value = {
            "main_service": "", "specific_detail": "", "pain_point": "", "tech_stack": ""
        }
        mock_writer_cls.return_value.personalize_lead.side_effect = lambda l: l

        with tempfile.TemporaryDirectory() as tmpdir:
            out = os.path.join(tmpdir, "out.json")
            run_pipeline(search_queries=["test"], dry_run=True, output_file=out)

        mock_instantly_cls.return_value.add_leads_batch.assert_not_called()

    @patch("scripts.run_pipeline.InstantlyClient")
    @patch("scripts.run_pipeline.EmailWriter")
    @patch("scripts.run_pipeline.WebsiteResearcher")
    @patch("scripts.run_pipeline.EmailEnricher")
    @patch("scripts.run_pipeline.GoogleMapsScraper")
    @patch("scripts.run_pipeline.get_config")
    def test_pipeline_returns_verified_leads(
        self, mock_cfg, mock_scraper_cls, mock_enricher_cls,
        mock_researcher_cls, mock_writer_cls, mock_instantly_cls
    ):
        from scripts.run_pipeline import run_pipeline

        leads = self._make_leads(3)
        mock_scraper_cls.return_value.scrape.return_value = leads
        mock_enricher_cls.return_value.process_batch.return_value = leads
        mock_researcher_cls.return_value.research.return_value = {}
        mock_writer_cls.return_value.personalize_lead.side_effect = lambda l: l

        with tempfile.TemporaryDirectory() as tmpdir:
            out = os.path.join(tmpdir, "out.json")
            result = run_pipeline(search_queries=["q"], skip_outreach=True, output_file=out)

        assert len(result) == 3

    @patch("scripts.run_pipeline.get_config")
    def test_pipeline_raises_on_missing_source(self, mock_cfg):
        from scripts.run_pipeline import run_pipeline
        import pytest
        with pytest.raises(ValueError, match="Provide --queries or --icp"):
            run_pipeline()

    @patch("scripts.run_pipeline.get_config")
    def test_pipeline_raises_on_unknown_icp(self, mock_cfg):
        from scripts.run_pipeline import run_pipeline
        import pytest
        with pytest.raises(ValueError, match="not found"):
            run_pipeline(icp_name="Nonexistent ICP Profile")

    @patch("scripts.run_pipeline.InstantlyClient")
    @patch("scripts.run_pipeline.EmailWriter")
    @patch("scripts.run_pipeline.WebsiteResearcher")
    @patch("scripts.run_pipeline.EmailEnricher")
    @patch("scripts.run_pipeline.GoogleMapsScraper")
    @patch("scripts.run_pipeline.get_config")
    def test_pipeline_returns_empty_when_no_leads(
        self, mock_cfg, mock_scraper_cls, mock_enricher_cls,
        mock_researcher_cls, mock_writer_cls, mock_instantly_cls
    ):
        from scripts.run_pipeline import run_pipeline

        mock_scraper_cls.return_value.scrape.return_value = []
        result = run_pipeline(search_queries=["empty query"])
        assert result == []
