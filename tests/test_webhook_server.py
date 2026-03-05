"""Tests for the webhook server."""

import pytest
from unittest.mock import MagicMock, patch


@pytest.fixture
def client():
    # Import app after patching config so no real .env is required
    with patch("src.utils.config.get_config") as mock_get_config:
        mock_cfg = MagicMock()
        mock_cfg.anthropic_key = "test"
        mock_cfg.slack_webhook_url = ""
        mock_get_config.return_value = mock_cfg

        import importlib
        import scripts.webhook_server as ws
        importlib.reload(ws)
        ws.app.config["TESTING"] = True
        with ws.app.test_client() as c:
            yield c


def test_health_endpoint(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "ok"


def test_missing_payload_returns_400(client):
    resp = client.post("/webhook/instantly", data="not json",
                       content_type="text/plain")
    assert resp.status_code == 400


def test_unsubscribe_event(client):
    resp = client.post(
        "/webhook/instantly",
        json={"event": "unsubscribe", "email": "user@example.com"},
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["action"] == "suppress"


def test_hard_bounce_event(client):
    resp = client.post(
        "/webhook/instantly",
        json={"event": "bounce", "email": "bad@example.com", "bounce_type": "hard"},
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["action"] == "suppress"


def test_soft_bounce_event(client):
    resp = client.post(
        "/webhook/instantly",
        json={"event": "bounce", "email": "soft@example.com", "bounce_type": "soft"},
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["action"] == "log"


def test_unknown_event_is_ignored(client):
    resp = client.post(
        "/webhook/instantly",
        json={"event": "opened", "email": "a@b.com"},
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "ignored"


@patch("scripts.webhook_server._get_classifier")
def test_reply_event_classifies_and_routes(mock_get_classifier, client):
    mock_classifier = MagicMock()
    mock_classifier.process_reply.return_value = {
        "email": "prospect@co.com",
        "category": "INTERESTED",
        "action": "slack_alert",
    }
    mock_get_classifier.return_value = mock_classifier

    resp = client.post(
        "/webhook/instantly",
        json={
            "event": "reply",
            "email": "prospect@co.com",
            "reply_text": "Sounds interesting!",
        },
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["category"] == "INTERESTED"
    assert data["action"] == "slack_alert"


@patch("scripts.webhook_server._get_classifier")
def test_reply_event_missing_text_returns_400(mock_get_classifier, client):
    resp = client.post(
        "/webhook/instantly",
        json={"event": "reply", "email": "a@b.com"},
    )
    assert resp.status_code == 400
