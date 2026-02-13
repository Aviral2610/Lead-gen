"""Unit tests for campaign health monitor."""

import pytest
from src.monitoring.campaign_monitor import CampaignHealth


class TestCampaignHealth:
    def test_healthy_campaign(self):
        health = CampaignHealth(
            campaign_id="test",
            total_sent=1000,
            total_opened=300,
            total_replied=50,
            total_bounced=10,
            total_unsubscribed=5,
        )
        assert health.bounce_rate == pytest.approx(1.0)
        assert health.reply_rate == pytest.approx(5.0)
        assert health.open_rate == pytest.approx(30.0)
        assert health.is_healthy()

    def test_unhealthy_bounce_rate(self):
        health = CampaignHealth(
            campaign_id="test",
            total_sent=1000,
            total_bounced=50,
        )
        assert health.bounce_rate == pytest.approx(5.0)
        assert not health.is_healthy(max_bounce_pct=2.0)

    def test_zero_sends(self):
        health = CampaignHealth(campaign_id="test")
        assert health.bounce_rate == 0.0
        assert health.reply_rate == 0.0
        assert health.is_healthy()

    def test_unsubscribe_rate(self):
        health = CampaignHealth(
            campaign_id="test",
            total_sent=100,
            total_unsubscribed=5,
        )
        assert health.unsubscribe_rate == pytest.approx(5.0)
        assert not health.is_healthy(max_unsub_pct=2.0)
