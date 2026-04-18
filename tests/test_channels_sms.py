"""Tests for the SMS (Twilio) channel adapter."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from urgent_contact.channels.base import ChannelAdapter
from urgent_contact.channels.sms import SMSChannel


@pytest.fixture
def adapter(queue_db):
    return SMSChannel(
        account_sid="ACtest",
        auth_token="authtest",
        from_number="+15005550006",
    )


# ──────────────────────────────────────────────────────────────────────────────
# Protocol conformance
# ──────────────────────────────────────────────────────────────────────────────

def test_conforms_to_protocol(adapter):
    assert isinstance(adapter, ChannelAdapter)


def test_channel_type(adapter):
    assert adapter.channel_type == "sms"


def test_supported_auth_methods(adapter):
    assert "reply-token" in adapter.supported_auth_methods


# ──────────────────────────────────────────────────────────────────────────────
# send()
# ──────────────────────────────────────────────────────────────────────────────

def test_send_calls_twilio(adapter):
    mock_client = MagicMock()
    with patch("urgent_contact.channels.sms.TwilioClient", mock_client):
        adapter.send("+61412345678", "URGENT: reply APPROVE 123456", "reply-token", "123456")
    mock_client.assert_called_once_with("ACtest", "authtest")
    mock_client.return_value.messages.create.assert_called_once_with(
        to="+61412345678",
        from_="+15005550006",
        body="URGENT: reply APPROVE 123456",
    )


def test_send_raises_if_twilio_unavailable(adapter):
    with patch("urgent_contact.channels.sms._TWILIO_AVAILABLE", False):
        with pytest.raises(ImportError, match="twilio package"):
            adapter.send("+61412345678", "msg", "reply-token", "000000")


# ──────────────────────────────────────────────────────────────────────────────
# poll_responses()
# ──────────────────────────────────────────────────────────────────────────────

def test_poll_empty_when_no_responses(adapter, queue_db):
    results = adapter.poll_responses("+61412345678")
    assert results == []


def test_poll_returns_sms_reply(adapter, queue_db):
    import urgent_contact.link_queue as lq
    lq.write_sms_response("+61412345678", "APPROVE 123456")

    results = adapter.poll_responses("+61412345678")
    assert len(results) == 1
    assert results[0].raw_text == "APPROVE 123456"
    assert results[0].channel_type == "sms"
    assert results[0].channel_handle == "+61412345678"
    assert results[0].channel_verified_identity is False  # reply-token auth; dispatcher verifies


def test_poll_consumes_response(adapter, queue_db):
    import urgent_contact.link_queue as lq
    lq.write_sms_response("+61412345678", "REJECT 654321")

    first = adapter.poll_responses("+61412345678")
    second = adapter.poll_responses("+61412345678")
    assert len(first) == 1
    assert len(second) == 0


def test_poll_filters_by_phone_number(adapter, queue_db):
    import urgent_contact.link_queue as lq
    lq.write_sms_response("+61400000001", "APPROVE 111111")
    lq.write_sms_response("+61400000002", "REJECT 222222")

    results = adapter.poll_responses("+61400000001")
    assert len(results) == 1
    assert results[0].raw_text == "APPROVE 111111"


# ──────────────────────────────────────────────────────────────────────────────
# Cancellation
# ──────────────────────────────────────────────────────────────────────────────

def test_supports_cancellation_false(adapter):
    assert adapter.supports_cancellation() is False


def test_cancel_pending_is_noop(adapter):
    adapter.cancel_pending("+61412345678")  # must not raise
