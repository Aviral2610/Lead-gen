"""Unit tests for suppression list manager."""

import json
import tempfile
from pathlib import Path

import pytest
from src.compliance.suppression import SuppressionManager


@pytest.fixture
def tmp_suppression_file(tmp_path):
    return tmp_path / "test_suppression.json"


@pytest.fixture
def suppression_mgr(tmp_suppression_file):
    return SuppressionManager(filepath=tmp_suppression_file)


class TestSuppressionManager:
    def test_add_and_check(self, suppression_mgr):
        suppression_mgr.add("test@example.com", reason="unsubscribe")
        assert suppression_mgr.is_suppressed("test@example.com")
        assert suppression_mgr.is_suppressed("TEST@EXAMPLE.COM")
        assert not suppression_mgr.is_suppressed("other@example.com")

    def test_remove(self, suppression_mgr):
        suppression_mgr.add("test@example.com", reason="unsubscribe")
        assert suppression_mgr.is_suppressed("test@example.com")
        suppression_mgr.remove("test@example.com")
        assert not suppression_mgr.is_suppressed("test@example.com")

    def test_persistence(self, tmp_suppression_file):
        mgr1 = SuppressionManager(filepath=tmp_suppression_file)
        mgr1.add("persist@example.com", reason="bounce")

        mgr2 = SuppressionManager(filepath=tmp_suppression_file)
        assert mgr2.is_suppressed("persist@example.com")

    def test_filter_leads(self, suppression_mgr):
        suppression_mgr.add("blocked@example.com", reason="spam")

        leads = [
            {"email": "blocked@example.com", "name": "Blocked"},
            {"email": "allowed@example.com", "name": "Allowed"},
        ]
        allowed, suppressed = suppression_mgr.filter_leads(leads)
        assert len(allowed) == 1
        assert len(suppressed) == 1
        assert allowed[0]["email"] == "allowed@example.com"

    def test_empty_email_not_suppressed(self, suppression_mgr):
        assert not suppression_mgr.is_suppressed("")
        assert not suppression_mgr.is_suppressed(None)

    def test_bulk_add(self, suppression_mgr):
        entries = [
            {"email": "a@test.com", "reason": "bounce"},
            {"email": "b@test.com", "reason": "unsubscribe"},
        ]
        suppression_mgr.bulk_add(entries)
        assert suppression_mgr.count == 2
        assert suppression_mgr.is_suppressed("a@test.com")
        assert suppression_mgr.is_suppressed("b@test.com")

    def test_export(self, suppression_mgr):
        suppression_mgr.add("export@test.com", reason="manual", source="admin")
        exported = suppression_mgr.export()
        assert len(exported) == 1
        assert exported[0]["email"] == "export@test.com"
        assert exported[0]["reason"] == "manual"

    def test_duplicate_add_is_idempotent(self, suppression_mgr):
        suppression_mgr.add("dup@test.com", reason="bounce")
        suppression_mgr.add("dup@test.com", reason="spam")
        assert suppression_mgr.count == 1
