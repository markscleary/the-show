"""Scene 4: Adapter contract formalisation tests."""
from __future__ import annotations

import pytest

from urgent_contact.channels.adapter_base import AbstractChannelAdapter, AbstractSubAgentAdapter
from urgent_contact.channels.telegram import TelegramChannel
from urgent_contact.channels.email import EmailChannel
from urgent_contact.channels.gemini_adapter import GeminiSubAgentAdapter


def test_telegram_channel_is_abstract_channel_adapter():
    adapter = TelegramChannel("dummy-token", [])
    assert isinstance(adapter, AbstractChannelAdapter)


def test_email_channel_is_abstract_channel_adapter():
    adapter = EmailChannel(
        smtp_host="localhost",
        smtp_port=25,
        username="u",
        password="p",
        from_addr="f@x.com",
        signing_secret="secret",
        link_base_url="http://localhost",
    )
    assert isinstance(adapter, AbstractChannelAdapter)


def test_gemini_sub_agent_adapter_has_required_attributes():
    adapter = GeminiSubAgentAdapter()
    assert hasattr(adapter, "agent_type")
    assert hasattr(adapter, "model")
    assert hasattr(adapter, "timeout_seconds")
    assert hasattr(adapter, "retry_policy")


def test_all_adapters_have_non_empty_error_surface():
    telegram = TelegramChannel("dummy-token", [])
    email = EmailChannel(
        smtp_host="localhost",
        smtp_port=25,
        username="u",
        password="p",
        from_addr="f@x.com",
        signing_secret="secret",
        link_base_url="http://localhost",
    )
    gemini = GeminiSubAgentAdapter()

    assert len(telegram.error_surface()) > 0
    assert len(email.error_surface()) > 0
    assert len(gemini.error_surface()) > 0
