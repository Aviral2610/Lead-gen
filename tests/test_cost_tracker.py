"""Unit tests for cost tracker."""

import pytest
from src.monitoring.cost_tracker import CostTracker


class TestCostTracker:
    def test_log_calls(self):
        tracker = CostTracker()
        tracker.log_call("prospeo_search", 10)
        tracker.log_call("claude_sonnet", 5)

        assert tracker.total_calls == 15
        assert tracker.total_spend > 0

    def test_summary(self):
        tracker = CostTracker()
        tracker.log_call("openai_gpt4o", 3)

        summary = tracker.summary()
        assert summary["total_api_calls"] == 3
        assert "by_service" in summary
        assert "openai_gpt4o" in summary["by_service"]

    def test_zero_calls(self):
        tracker = CostTracker()
        assert tracker.total_calls == 0
        assert tracker.total_spend == 0.0

    def test_custom_cost_overrides(self):
        tracker = CostTracker(cost_overrides={"custom_service": 0.1})
        tracker.log_call("custom_service", 5)
        assert tracker.total_spend == pytest.approx(0.5)
