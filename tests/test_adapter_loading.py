"""Tests for load_adapters() in urgent_contact.dispatcher."""
from __future__ import annotations

import logging

import pytest

from urgent_contact.channels.mock import MockChannel
from urgent_contact.dispatcher import load_adapters


def test_returns_only_mock_when_no_env_vars(monkeypatch):
    """With no channel env vars, only MockChannel is returned."""
    for key in (
        "URGENT_TELEGRAM_BOT_TOKEN",
        "URGENT_SMTP_HOST",
        "URGENT_WHATSAPP_ACCESS_TOKEN",
        "URGENT_TWILIO_ACCOUNT_SID",
        "SHOW_TEST_MODE",
    ):
        monkeypatch.delenv(key, raising=False)

    adapters = load_adapters()

    assert "mock" in adapters
    assert isinstance(adapters["mock"], MockChannel)
    assert "telegram" not in adapters
    assert "email" not in adapters
    assert "whatsapp" not in adapters
    assert "sms" not in adapters


def test_includes_telegram_when_token_set(monkeypatch):
    """Telegram adapter is loaded when URGENT_TELEGRAM_BOT_TOKEN is present."""
    monkeypatch.setenv("URGENT_TELEGRAM_BOT_TOKEN", "fake-token-123")
    monkeypatch.delenv("SHOW_TEST_MODE", raising=False)

    adapters = load_adapters()

    assert "telegram" in adapters
    assert adapters["telegram"].channel_type == "telegram"


def test_test_mode_forces_mock_only(monkeypatch):
    """SHOW_TEST_MODE=1 returns only MockChannel even when real env vars are set."""
    monkeypatch.setenv("SHOW_TEST_MODE", "1")
    monkeypatch.setenv("URGENT_TELEGRAM_BOT_TOKEN", "fake-token-123")
    monkeypatch.setenv("URGENT_SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("URGENT_EMAIL_SIGNING_SECRET", "secret")

    adapters = load_adapters()

    assert list(adapters.keys()) == ["mock"]
    assert isinstance(adapters["mock"], MockChannel)


def test_test_mode_logs_warning(monkeypatch, caplog):
    """SHOW_TEST_MODE=1 logs a warning that MockChannel is forced."""
    monkeypatch.setenv("SHOW_TEST_MODE", "1")

    with caplog.at_level(logging.WARNING, logger="root"):
        load_adapters()

    messages = [r.message for r in caplog.records]
    assert any("SHOW_TEST_MODE" in m for m in messages)


def test_logs_warning_for_missing_telegram(monkeypatch, caplog):
    """A warning is logged when URGENT_TELEGRAM_BOT_TOKEN is absent."""
    monkeypatch.delenv("URGENT_TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("SHOW_TEST_MODE", raising=False)

    with caplog.at_level(logging.WARNING, logger="root"):
        load_adapters()

    messages = [r.message for r in caplog.records]
    assert any("telegram" in m.lower() for m in messages)


def test_logs_warning_for_missing_email(monkeypatch, caplog):
    """A warning is logged when URGENT_SMTP_HOST is absent."""
    monkeypatch.delenv("URGENT_SMTP_HOST", raising=False)
    monkeypatch.delenv("SHOW_TEST_MODE", raising=False)

    with caplog.at_level(logging.WARNING, logger="root"):
        load_adapters()

    messages = [r.message for r in caplog.records]
    assert any("smtp" in m.lower() or "email" in m.lower() for m in messages)


def test_logs_warning_for_missing_whatsapp(monkeypatch, caplog):
    """A warning is logged when URGENT_WHATSAPP_ACCESS_TOKEN is absent."""
    monkeypatch.delenv("URGENT_WHATSAPP_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("SHOW_TEST_MODE", raising=False)

    with caplog.at_level(logging.WARNING, logger="root"):
        load_adapters()

    messages = [r.message for r in caplog.records]
    assert any("whatsapp" in m.lower() for m in messages)


def test_logs_warning_for_missing_sms(monkeypatch, caplog):
    """A warning is logged when URGENT_TWILIO_ACCOUNT_SID is absent."""
    monkeypatch.delenv("URGENT_TWILIO_ACCOUNT_SID", raising=False)
    monkeypatch.delenv("SHOW_TEST_MODE", raising=False)

    with caplog.at_level(logging.WARNING, logger="root"):
        load_adapters()

    messages = [r.message for r in caplog.records]
    assert any("twilio" in m.lower() or "sms" in m.lower() for m in messages)
