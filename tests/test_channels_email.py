"""Tests for the Email channel adapter."""
from __future__ import annotations

import base64
import hashlib
import hmac
import time
from unittest.mock import MagicMock, patch

import pytest

from the_show.urgent_contact.channels.base import ChannelAdapter
from the_show.urgent_contact.channels.email import EmailChannel


SECRET = "test-signing-secret"


@pytest.fixture
def adapter(queue_db):
    return EmailChannel(
        smtp_host="smtp.example.com",
        smtp_port=587,
        username="bot@example.com",
        password="secret",
        from_addr="bot@example.com",
        signing_secret=SECRET,
        link_base_url="http://127.0.0.1:5099",
    )


def _make_token(matter_id: int, action: str, expiry_ts: int, secret: str = SECRET) -> str:
    msg = f"{matter_id}:{action}:{expiry_ts}"
    sig = hmac.new(secret.encode(), msg.encode(), hashlib.sha256).hexdigest()[:32]
    return base64.urlsafe_b64encode(f"{msg}:{sig}".encode()).decode().rstrip("=")


# ──────────────────────────────────────────────────────────────────────────────
# Protocol conformance
# ──────────────────────────────────────────────────────────────────────────────

def test_conforms_to_protocol(adapter):
    assert isinstance(adapter, ChannelAdapter)


def test_channel_type(adapter):
    assert adapter.channel_type == "email"


def test_supported_auth_methods(adapter):
    assert "channel-native" in adapter.supported_auth_methods


# ──────────────────────────────────────────────────────────────────────────────
# send()
# ──────────────────────────────────────────────────────────────────────────────

def test_send_calls_smtp(adapter):
    mock_smtp_instance = MagicMock()
    mock_smtp_class = MagicMock(return_value=mock_smtp_instance)
    mock_smtp_instance.__enter__ = MagicMock(return_value=mock_smtp_instance)
    mock_smtp_instance.__exit__ = MagicMock(return_value=False)
    with patch("the_show.urgent_contact.channels.email.smtplib.SMTP", mock_smtp_class):
        adapter.send("user@example.com", "Urgent: please review", "channel-native", "5-abc-defsig")
    mock_smtp_class.assert_called_once_with("smtp.example.com", 587)
    mock_smtp_instance.send_message.assert_called_once()


def test_send_email_contains_action_links(adapter):
    sent_messages = []

    def fake_send_message(msg):
        sent_messages.append(msg)

    mock_smtp_instance = MagicMock()
    mock_smtp_instance.__enter__ = MagicMock(return_value=mock_smtp_instance)
    mock_smtp_instance.__exit__ = MagicMock(return_value=False)
    mock_smtp_instance.send_message.side_effect = fake_send_message
    with patch("the_show.urgent_contact.channels.email.smtplib.SMTP", MagicMock(return_value=mock_smtp_instance)):
        adapter.send("user@example.com", "Check this out", "channel-native", "3-abc-defsig")

    assert sent_messages
    payload = sent_messages[0].as_string()
    for action in ("APPROVE", "REJECT", "STOP", "CONTINUE"):
        assert action in payload


def test_send_links_include_handle(adapter):
    sent_messages = []

    def fake_send_message(msg):
        sent_messages.append(msg)

    mock_smtp_instance = MagicMock()
    mock_smtp_instance.__enter__ = MagicMock(return_value=mock_smtp_instance)
    mock_smtp_instance.__exit__ = MagicMock(return_value=False)
    mock_smtp_instance.send_message.side_effect = fake_send_message
    with patch("the_show.urgent_contact.channels.email.smtplib.SMTP", MagicMock(return_value=mock_smtp_instance)):
        adapter.send("mark@example.com", "urgent matter", "channel-native", "1-abc-sig")

    payload = sent_messages[0].as_string()
    assert "mark%40example.com" in payload or "mark@example.com" in payload


# ──────────────────────────────────────────────────────────────────────────────
# poll_responses()
# ──────────────────────────────────────────────────────────────────────────────

def test_poll_empty_when_no_responses(adapter, queue_db):
    results = adapter.poll_responses("user@example.com")
    assert results == []


def test_poll_returns_queued_response(adapter, queue_db):
    import the_show.urgent_contact.link_queue as lq
    expiry = int(time.time()) + 3600
    token = _make_token(1, "APPROVE", expiry)
    lq.write_link_response(1, "user@example.com", "APPROVE", token)

    results = adapter.poll_responses("user@example.com")
    assert len(results) == 1
    assert results[0].raw_text == "APPROVE"
    assert results[0].channel_verified_identity is True
    assert results[0].channel_type == "email"


def test_poll_consumes_responses(adapter, queue_db):
    import the_show.urgent_contact.link_queue as lq
    expiry = int(time.time()) + 3600
    token = _make_token(2, "REJECT", expiry)
    lq.write_link_response(2, "user@example.com", "REJECT", token)

    first = adapter.poll_responses("user@example.com")
    second = adapter.poll_responses("user@example.com")
    assert len(first) == 1
    assert len(second) == 0  # already consumed


def test_poll_filters_by_handle(adapter, queue_db):
    import the_show.urgent_contact.link_queue as lq
    expiry = int(time.time()) + 3600
    lq.write_link_response(1, "alice@example.com", "APPROVE", _make_token(1, "APPROVE", expiry))
    lq.write_link_response(1, "bob@example.com", "REJECT", _make_token(1, "REJECT", expiry))

    results = adapter.poll_responses("alice@example.com")
    assert len(results) == 1
    assert results[0].raw_text == "APPROVE"


# ──────────────────────────────────────────────────────────────────────────────
# Token generation helpers
# ──────────────────────────────────────────────────────────────────────────────

def test_make_link_token_verifiable(adapter):
    expiry = int(time.time()) + 3600
    token = adapter._make_link_token(42, "APPROVE", expiry)
    # Decode and verify manually
    padded = token + "==" * ((-len(token)) % 4 if len(token) % 4 else 0)
    decoded = base64.urlsafe_b64decode(padded).decode()
    parts = decoded.split(":")
    assert len(parts) == 4
    matter_id, action, expiry_str, sig = parts
    assert matter_id == "42"
    assert action == "APPROVE"


def test_extract_matter_id(adapter):
    assert adapter._extract_matter_id("5-abc123-defsig") == 5
    assert adapter._extract_matter_id(None) == 0
    assert adapter._extract_matter_id("bad") == 0


# ──────────────────────────────────────────────────────────────────────────────
# Cancellation
# ──────────────────────────────────────────────────────────────────────────────

def test_supports_cancellation_false(adapter):
    assert adapter.supports_cancellation() is False
