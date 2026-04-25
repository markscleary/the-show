"""Tests for the WhatsApp channel adapter (skeleton)."""
from __future__ import annotations

import pytest

from the_show.urgent_contact.channels.base import ChannelAdapter
from the_show.urgent_contact.channels.whatsapp import WhatsAppChannel


@pytest.fixture
def adapter(queue_db):
    return WhatsAppChannel(
        phone_number_id="12345",
        access_token="test-access-token",
        verify_token="test-verify-token",
    )


# ──────────────────────────────────────────────────────────────────────────────
# Protocol conformance
# ──────────────────────────────────────────────────────────────────────────────

def test_conforms_to_protocol(adapter):
    assert isinstance(adapter, ChannelAdapter)


def test_channel_type(adapter):
    assert adapter.channel_type == "whatsapp"


def test_supported_auth_methods(adapter):
    assert "reply-token" in adapter.supported_auth_methods


# ──────────────────────────────────────────────────────────────────────────────
# send() — skeleton raises NotImplementedError
# ──────────────────────────────────────────────────────────────────────────────

def test_send_raises_not_implemented(adapter):
    with pytest.raises(NotImplementedError) as exc_info:
        adapter.send("+61412345678", "msg", "reply-token", "123456")
    assert "Meta Business API" in str(exc_info.value)


# ──────────────────────────────────────────────────────────────────────────────
# poll_responses()
# ──────────────────────────────────────────────────────────────────────────────

def test_poll_empty_when_no_responses(adapter, queue_db):
    results = adapter.poll_responses("+61412345678")
    assert results == []


def test_poll_returns_queued_response(adapter, queue_db):
    import the_show.urgent_contact.link_queue as lq
    lq.write_whatsapp_response("+61412345678", "APPROVE 123456")

    results = adapter.poll_responses("+61412345678")
    assert len(results) == 1
    assert results[0].raw_text == "APPROVE 123456"
    assert results[0].channel_type == "whatsapp"
    assert results[0].channel_verified_identity is False  # reply-token; dispatcher verifies


def test_poll_consumes_responses(adapter, queue_db):
    import the_show.urgent_contact.link_queue as lq
    lq.write_whatsapp_response("+61412345678", "REJECT 654321")

    first = adapter.poll_responses("+61412345678")
    second = adapter.poll_responses("+61412345678")
    assert len(first) == 1
    assert len(second) == 0


def test_poll_filters_by_number(adapter, queue_db):
    import the_show.urgent_contact.link_queue as lq
    lq.write_whatsapp_response("+61411111111", "APPROVE 111111")
    lq.write_whatsapp_response("+61422222222", "REJECT 222222")

    results = adapter.poll_responses("+61411111111")
    assert len(results) == 1
    assert results[0].raw_text == "APPROVE 111111"


# ──────────────────────────────────────────────────────────────────────────────
# Cancellation
# ──────────────────────────────────────────────────────────────────────────────

def test_supports_cancellation_false(adapter):
    assert adapter.supports_cancellation() is False


def test_cancel_pending_is_noop(adapter):
    adapter.cancel_pending("+61412345678")  # must not raise
