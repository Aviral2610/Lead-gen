#!/usr/bin/env python3
"""Lightweight webhook server to receive events from Instantly.ai and
process them using the Python reply-classification pipeline.

This is the standalone Python alternative to the n8n workflow
(03_campaign_push_monitoring.json). Use it when you don't have n8n
running or want to handle webhooks directly.

Instantly sends POST requests with JSON payloads when:
  - A prospect replies to an email
  - An email bounces
  - A prospect unsubscribes

Supported event types (Instantly webhook event field):
  reply          → classify reply with Claude, route accordingly
  bounce         → log bounce for deliverability monitoring
  unsubscribe    → suppress contact in CRM

Usage:
    pip install flask
    python scripts/webhook_server.py
    python scripts/webhook_server.py --port 8080 --host 0.0.0.0

Then point your Instantly webhook URL to:
    http://your-server:5000/webhook/instantly

To expose locally via ngrok for testing:
    ngrok http 5000
"""

import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

try:
    from flask import Flask, request, jsonify
except ImportError:
    print("Flask is required: pip install flask")
    sys.exit(1)

from src.reply_handling.classifier import ReplyClassifier
from src.utils.config import get_config
from src.utils.logger import setup_logger

logger = setup_logger("webhook_server", log_file="logs/webhooks.log")

app = Flask(__name__)

# Suppress Flask's default access log noise; our logger handles it
log = logging.getLogger("werkzeug")
log.setLevel(logging.WARNING)


def _get_classifier() -> ReplyClassifier:
    """Create a classifier instance (lazily, to avoid requiring config at import)."""
    return ReplyClassifier(get_config())


@app.route("/health", methods=["GET"])
def health():
    """Simple health check endpoint."""
    return jsonify({"status": "ok"}), 200


@app.route("/webhook/instantly", methods=["POST"])
def handle_instantly_webhook():
    """Handle incoming Instantly.ai webhook events."""
    payload = request.get_json(silent=True)
    if not payload:
        logger.warning("Received empty or non-JSON webhook payload.")
        return jsonify({"error": "Invalid payload"}), 400

    event_type = payload.get("event", "").lower()
    email = payload.get("email", "")
    logger.info("Received Instantly event: type=%s email=%s", event_type, email)

    if event_type == "reply":
        reply_text = payload.get("reply_text") or payload.get("body", "")
        if not reply_text:
            logger.warning("Reply event missing reply_text for %s", email)
            return jsonify({"error": "Missing reply_text"}), 400

        try:
            classifier = _get_classifier()
            result = classifier.process_reply(email, reply_text)
            logger.info(
                "Reply from %s classified as %s → action: %s",
                email, result.get("category"), result.get("action"),
            )
            return jsonify(result), 200
        except Exception as e:
            logger.error("Failed to classify reply from %s: %s", email, e)
            return jsonify({"error": str(e)}), 500

    elif event_type == "bounce":
        bounce_type = payload.get("bounce_type", "unknown")
        logger.warning("Bounce event: email=%s type=%s", email, bounce_type)
        # Hard bounces should be suppressed; soft bounces logged only
        if bounce_type == "hard":
            logger.warning(
                "Hard bounce for %s — remove from future campaigns.", email
            )
        return jsonify({"status": "logged", "action": "suppress" if bounce_type == "hard" else "log"}), 200

    elif event_type == "unsubscribe":
        logger.info("Unsubscribe request from %s", email)
        return jsonify({"status": "logged", "action": "suppress"}), 200

    else:
        logger.info("Unhandled event type '%s' — ignoring.", event_type)
        return jsonify({"status": "ignored", "event": event_type}), 200


def main():
    import argparse
    parser = argparse.ArgumentParser(
        description="Webhook server for Instantly.ai events."
    )
    parser.add_argument("--host", default="127.0.0.1", help="Bind host (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=5000, help="Bind port (default: 5000)")
    parser.add_argument("--debug", action="store_true", help="Enable Flask debug mode")
    args = parser.parse_args()

    logger.info("Starting webhook server on %s:%d", args.host, args.port)
    logger.info("Instantly webhook URL: http://%s:%d/webhook/instantly", args.host, args.port)
    app.run(host=args.host, port=args.port, debug=args.debug)


if __name__ == "__main__":
    main()
