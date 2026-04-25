"""Tests for the Telegram channel adapter."""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from the_show.urgent_contact.channels.base import ChannelAdapter, InboundResponse
from the_show.urgent_contact.channels.telegram import TelegramChannel


@pytest.fixture
def adapter():
    return TelegramChannel(
        bot_token="test-bot-token",
        allowed_user_ids=["111111", "222222"],
    )


# ──────────────────────────────────────────────────────────────────────────────
# Protocol conformance
# ──────────────────────────────────────────────────────────────────────────────

def test_conforms_to_protocol(adapter):
    assert isinstance(adapter, ChannelAdapter)


def test_channel_type(adapter):
    assert adapter.channel_type == "telegram"


def test_supported_auth_methods(adapter):
    assert "channel-native" in adapter.supported_auth_methods


# ──────────────────────────────────────────────────────────────────────────────
# send()
# ──────────────────────────────────────────────────────────────────────────────

def test_send_calls_telegram_api(adapter):
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    with patch("the_show.urgent_contact.channels.telegram.requests.post", return_value=mock_resp) as mock_post:
        adapter.send("111111", "Urgent: please approve", "channel-native", None)
        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args
        assert "sendMessage" in call_kwargs[0][0]
        payload = call_kwargs[1]["json"]
        assert payload["chat_id"] == "111111"
        assert "Urgent" in payload["text"]


def test_send_raises_on_api_error(adapter):
    import requests as req
    mock_resp = MagicMock()
    mock_resp.raise_for_status.side_effect = req.HTTPError("404")
    with patch("the_show.urgent_contact.channels.telegram.requests.post", return_value=mock_resp):
        with pytest.raises(req.HTTPError):
            adapter.send("111111", "msg", "channel-native", None)


# ──────────────────────────────────────────────────────────────────────────────
# poll_responses()
# ──────────────────────────────────────────────────────────────────────────────

def _make_updates(chat_id: str, from_id: str, text: str, update_id: int = 1):
    return {
        "result": [
            {
                "update_id": update_id,
                "message": {
                    "message_id": 42,
                    "from": {"id": int(from_id)},
                    "chat": {"id": int(chat_id)},
                    "date": 1713400000,
                    "text": text,
                },
            }
        ]
    }


def test_poll_returns_response_for_matching_chat(adapter):
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = _make_updates("111111", "111111", "APPROVE")
    with patch("the_show.urgent_contact.channels.telegram.requests.get", return_value=mock_resp):
        results = adapter.poll_responses("111111")
    assert len(results) == 1
    assert results[0].raw_text == "APPROVE"
    assert results[0].channel_type == "telegram"
    assert results[0].channel_handle == "111111"


def test_poll_sets_verified_for_allowed_user(adapter):
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = _make_updates("111111", "111111", "APPROVE")
    with patch("the_show.urgent_contact.channels.telegram.requests.get", return_value=mock_resp):
        results = adapter.poll_responses("111111")
    assert results[0].channel_verified_identity is True


def test_poll_unverified_for_unknown_user(adapter):
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = _make_updates("111111", "999999", "APPROVE")
    with patch("the_show.urgent_contact.channels.telegram.requests.get", return_value=mock_resp):
        results = adapter.poll_responses("111111")
    assert results[0].channel_verified_identity is False


def test_poll_skips_other_chat_ids(adapter):
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    # update is from chat 999999, but we're polling for 111111
    mock_resp.json.return_value = _make_updates("999999", "999999", "APPROVE")
    with patch("the_show.urgent_contact.channels.telegram.requests.get", return_value=mock_resp):
        results = adapter.poll_responses("111111")
    assert results == []


def test_poll_returns_empty_on_network_error(adapter):
    import requests as req
    with patch(
        "the_show.urgent_contact.channels.telegram.requests.get",
        side_effect=req.ConnectionError("timeout"),
    ):
        results = adapter.poll_responses("111111")
    assert results == []


def test_poll_advances_offset(adapter):
    assert adapter._offset == 0
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = _make_updates("111111", "111111", "APPROVE", update_id=7)
    with patch("the_show.urgent_contact.channels.telegram.requests.get", return_value=mock_resp):
        adapter.poll_responses("111111")
    assert adapter._offset == 8


# ──────────────────────────────────────────────────────────────────────────────
# Cancellation
# ──────────────────────────────────────────────────────────────────────────────

def test_supports_cancellation_false(adapter):
    assert adapter.supports_cancellation() is False


def test_cancel_pending_is_noop(adapter):
    adapter.cancel_pending("111111")  # must not raise
