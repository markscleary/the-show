"""Signed-link HTTP endpoint + webhook receiver for email, WhatsApp, and Twilio SMS.

Run standalone:
    python -m urgent_contact.link_server

Or via launchd — see ~/Library/LaunchAgents/org.shortandsweet.urgent-link-server.plist

Session 4 note: this server binds to localhost only. For WhatsApp and Twilio webhooks
(which require a public HTTPS URL) use ngrok: `ngrok http 5099` and configure the
resulting HTTPS URL in Meta / Twilio dashboards.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import time

from flask import Flask, jsonify, request

from urgent_contact import link_queue

app = Flask(__name__)


# ──────────────────────────────────────────────────────────────────────────────
# Token helpers
# ──────────────────────────────────────────────────────────────────────────────

def _signing_secret() -> str:
    secret = os.environ.get("URGENT_EMAIL_SIGNING_SECRET", "")
    if not secret:
        raise EnvironmentError("URGENT_EMAIL_SIGNING_SECRET is not set")
    return secret


def _verify_link_token(token: str) -> tuple[int, str, int] | None:
    """Verify and decode a link token.

    Returns (matter_id, action, expiry_ts) on success, None on failure.
    Token payload: base64url("{matter_id}:{action}:{expiry}:{sig}")
    """
    try:
        # Restore base64 padding stripped by rstrip("=")
        padded = token + "==" * ((-len(token)) % 4 if len(token) % 4 else 0)
        decoded = base64.urlsafe_b64decode(padded).decode()
        parts = decoded.split(":")
        if len(parts) != 4:
            return None
        matter_id_str, action, expiry_str, received_sig = parts
        matter_id = int(matter_id_str)
        expiry_ts = int(expiry_str)

        if time.time() > expiry_ts:
            return None

        msg = f"{matter_id}:{action}:{expiry_ts}"
        expected_sig = hmac.new(
            _signing_secret().encode(), msg.encode(), hashlib.sha256
        ).hexdigest()[:32]
        if not hmac.compare_digest(received_sig, expected_sig):
            return None

        if action not in ("APPROVE", "REJECT", "STOP", "CONTINUE"):
            return None

        return matter_id, action, expiry_ts
    except Exception:
        return None


# ──────────────────────────────────────────────────────────────────────────────
# Routes
# ──────────────────────────────────────────────────────────────────────────────

@app.route("/respond", methods=["GET"])
def handle_email_response():
    """Process a signed-link click from an email action button."""
    token = request.args.get("token", "")
    handle = request.args.get("handle", "")

    if not token or not handle:
        return _error_page(), 400

    result = _verify_link_token(token)
    if result is None:
        return _error_page(), 400

    matter_id, action, _ = result
    link_queue.write_link_response(matter_id, handle, action, token)
    return _success_page(action), 200


@app.route("/whatsapp-webhook", methods=["GET"])
def whatsapp_verify():
    """Meta webhook verification challenge."""
    verify_token = os.environ.get("URGENT_WHATSAPP_VERIFY_TOKEN", "")
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge", "")

    if mode == "subscribe" and token == verify_token and verify_token:
        return challenge, 200
    return "Forbidden", 403


@app.route("/whatsapp-webhook", methods=["POST"])
def whatsapp_receive():
    """Receive and queue inbound WhatsApp messages."""
    data = request.get_json(force=True, silent=True) or {}
    try:
        for entry in data.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {})
                for msg in value.get("messages", []):
                    from_number = msg.get("from", "")
                    body = (msg.get("text") or {}).get("body", "")
                    if from_number and body:
                        link_queue.write_whatsapp_response(from_number, body)
    except Exception:
        pass
    return jsonify({"status": "ok"}), 200


@app.route("/twilio-webhook", methods=["POST"])
def twilio_receive():
    """Receive and queue inbound Twilio SMS replies."""
    from_number = request.form.get("From", "")
    body = request.form.get("Body", "")
    if from_number and body:
        link_queue.write_sms_response(from_number, body)
    # Twilio expects an empty TwiML response
    return (
        '<?xml version="1.0" encoding="UTF-8"?><Response></Response>',
        200,
        {"Content-Type": "text/xml"},
    )


# ──────────────────────────────────────────────────────────────────────────────
# HTML helpers
# ──────────────────────────────────────────────────────────────────────────────

def _success_page(action: str) -> str:
    return (
        "<!DOCTYPE html><html><head><title>Response Recorded</title></head>"
        "<body style='font-family:sans-serif;max-width:480px;margin:3em auto;text-align:center'>"
        "<h2>Response recorded</h2>"
        f"<p>Your response <strong>{action}</strong> has been logged.</p>"
        "<p>You can close this tab.</p>"
        "</body></html>"
    )


def _error_page() -> str:
    return (
        "<!DOCTYPE html><html><head><title>Invalid Link</title></head>"
        "<body style='font-family:sans-serif;max-width:480px;margin:3em auto;text-align:center'>"
        "<h2>Link unavailable</h2>"
        "<p>This link is no longer valid or has expired. Please check your email for a newer message.</p>"
        "</body></html>"
    )


def create_app() -> Flask:
    """Return the Flask app for use with WSGI servers or tests."""
    return app


if __name__ == "__main__":
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

    host = os.environ.get("URGENT_LINK_ENDPOINT_HOST", "127.0.0.1")
    port = int(os.environ.get("URGENT_LINK_ENDPOINT_PORT", "5099"))
    app.run(host=host, port=port)
