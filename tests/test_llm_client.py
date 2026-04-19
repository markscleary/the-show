"""Tests for call_sub_agent() — retry logic, Qwen fallback, and schema validation."""
from __future__ import annotations

import json

import httpx
import pytest

import adapters
from adapters import _FALLBACK_MODEL, call_sub_agent
from executor import meets_success


# ── Helpers ───────────────────────────────────────────────────────────────────

def _proxy_response(content_dict: dict, usage: dict | None = None) -> dict:
    data: dict = {
        "choices": [{"message": {"content": json.dumps(content_dict)}}],
    }
    if usage:
        data["usage"] = usage
    return data


def _make_do_llm_call(responses: list):
    """Return a fake _do_llm_call that pops from a list of (model -> result) entries.

    Each entry is either:
      - A dict to return as the parsed result
      - An exception instance to raise
    """
    calls: list[str] = []

    def fake(proxy_url, master_key, model, prompt, max_tokens):
        calls.append(model)
        if not responses:
            raise RuntimeError("No more responses in fake")
        item = responses.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item

    fake.calls = calls  # type: ignore[attr-defined]
    return fake


# ── Successful call ───────────────────────────────────────────────────────────

def test_success_returns_parsed_output(monkeypatch):
    """A clean proxy response is parsed and returned."""
    expected = {"key": "value"}
    monkeypatch.setattr(adapters, "_do_llm_call", _make_do_llm_call([dict(expected)]))
    monkeypatch.setattr(adapters, "_sleep", lambda s: None)

    result = call_sub_agent("gemini-flash", "test prompt")
    assert result == expected


def test_success_embeds_cost_sentinel(monkeypatch):
    """Cost is embedded when _do_llm_call returns a dict with _cost_usd."""
    output = {"result": "ok", "_cost_usd": 0.042}
    monkeypatch.setattr(adapters, "_do_llm_call", _make_do_llm_call([output]))
    monkeypatch.setattr(adapters, "_sleep", lambda s: None)

    result = call_sub_agent("gemini-flash", "test prompt")
    assert result["_cost_usd"] == pytest.approx(0.042)


# ── Retry behaviour ───────────────────────────────────────────────────────────

def test_retries_three_times_on_connect_error_then_falls_back(monkeypatch):
    """ConnectError from primary triggers 3 attempts, then falls back to qwen-noThink."""
    fake = _make_do_llm_call([
        httpx.ConnectError("refused"),
        httpx.ConnectError("refused"),
        httpx.ConnectError("refused"),
        {"fallback": True},  # fallback model call succeeds
    ])
    monkeypatch.setattr(adapters, "_do_llm_call", fake)
    monkeypatch.setattr(adapters, "_sleep", lambda s: None)

    result = call_sub_agent("gemini-flash", "test prompt")

    assert result == {"fallback": True}
    assert fake.calls.count("gemini-flash") == 3
    assert _FALLBACK_MODEL in fake.calls


def test_retries_three_times_on_429_then_falls_back(monkeypatch):
    """HTTP 429 from primary triggers 3 attempts, then falls back to qwen-noThink."""
    def _429():
        mock_resp = type("R", (), {"status_code": 429})()
        return httpx.HTTPStatusError(
            "429", request=httpx.Request("POST", "http://x"), response=mock_resp
        )

    fake = _make_do_llm_call([_429(), _429(), _429(), {"ok": True}])
    monkeypatch.setattr(adapters, "_do_llm_call", fake)
    monkeypatch.setattr(adapters, "_sleep", lambda s: None)

    result = call_sub_agent("gemini-flash", "test prompt")
    assert result == {"ok": True}
    assert fake.calls.count("gemini-flash") == 3
    assert _FALLBACK_MODEL in fake.calls


def test_non_retriable_4xx_raised_immediately(monkeypatch):
    """HTTP 400 (not in retriable set) is raised on first attempt without retry."""
    def _400():
        mock_resp = type("R", (), {"status_code": 400})()
        return httpx.HTTPStatusError(
            "400", request=httpx.Request("POST", "http://x"), response=mock_resp
        )

    fake = _make_do_llm_call([_400()])
    monkeypatch.setattr(adapters, "_do_llm_call", fake)
    monkeypatch.setattr(adapters, "_sleep", lambda s: None)

    with pytest.raises(httpx.HTTPStatusError):
        call_sub_agent("gemini-flash", "test prompt")

    assert len(fake.calls) == 1  # no retries, no fallback


def test_fallback_model_raises_runtime_error_when_itself_fails(monkeypatch):
    """If the model IS the fallback and all 3 attempts fail, RuntimeError is raised."""
    fake = _make_do_llm_call([
        httpx.ConnectError("refused"),
        httpx.ConnectError("refused"),
        httpx.ConnectError("refused"),
    ])
    monkeypatch.setattr(adapters, "_do_llm_call", fake)
    monkeypatch.setattr(adapters, "_sleep", lambda s: None)

    with pytest.raises(RuntimeError, match="unreachable"):
        call_sub_agent(_FALLBACK_MODEL, "test prompt")


def test_both_primary_and_fallback_fail_raises_runtime_error(monkeypatch):
    """If primary AND fallback both fail, a RuntimeError naming both is raised."""
    fake = _make_do_llm_call([
        httpx.ConnectError("refused"),
        httpx.ConnectError("refused"),
        httpx.ConnectError("refused"),
        httpx.ConnectError("fallback also gone"),
    ])
    monkeypatch.setattr(adapters, "_do_llm_call", fake)
    monkeypatch.setattr(adapters, "_sleep", lambda s: None)

    with pytest.raises(RuntimeError, match="fallback"):
        call_sub_agent("gemini-flash", "test prompt")


def test_sleep_called_between_retries(monkeypatch):
    """Exponential backoff sleep is called after each failed attempt."""
    sleep_calls: list[float] = []

    # One failure then success → one sleep(1) before the second attempt
    fake = _make_do_llm_call([
        httpx.ConnectError("refused"),
        {"ok": True},
    ])
    monkeypatch.setattr(adapters, "_do_llm_call", fake)
    monkeypatch.setattr(adapters, "_sleep", lambda s: sleep_calls.append(s))

    call_sub_agent("gemini-flash", "test prompt")

    assert len(sleep_calls) == 1  # one sleep between attempt 1 (fail) and attempt 2 (success)
    assert sleep_calls[0] == 1.0  # 2^(1-1) = 1


# ── Sub-agent integration via execute_strategy ────────────────────────────────

def test_execute_strategy_sub_agent_returns_output(monkeypatch):
    """execute_strategy with sub-agent method calls call_sub_agent and wraps result."""
    from adapters import execute_strategy
    from models import Strategy

    expected = {"name": "Test", "value": 42}
    monkeypatch.setattr(adapters, "call_sub_agent", lambda model, prompt, **kw: dict(expected))

    strategy = Strategy(
        method="sub-agent",
        agent="gemini",
        params={"model": "gemini-flash"},
        brief="Do some task",
    )
    result = execute_strategy(strategy, {})

    assert result.success is True
    assert result.output == expected


def test_execute_strategy_sub_agent_propagates_cost(monkeypatch):
    """Cost sentinel in call_sub_agent output is extracted into AdapterResult."""
    from adapters import execute_strategy
    from models import Strategy

    monkeypatch.setattr(
        adapters,
        "call_sub_agent",
        lambda model, prompt, **kw: {"data": "x", "_cost_usd": 0.07},
    )

    strategy = Strategy(
        method="sub-agent",
        agent="gemini",
        params={"model": "gemini-flash"},
        brief="Compute something",
    )
    result = execute_strategy(strategy, {})

    assert result.cost_usd == pytest.approx(0.07)
    assert "_cost_usd" not in result.output


# ── Schema validation ─────────────────────────────────────────────────────────

def test_meets_success_rejects_wrong_type_for_list_schema():
    """Schema check: list schema rejects a dict."""
    assert meets_success({"a": 1}, {"schema": "item[]"}) is False


def test_meets_success_rejects_wrong_type_for_dict_schema():
    """Schema check: dict schema rejects a list."""
    assert meets_success([1, 2], {"schema": "SomeSchema"}) is False


def test_meets_success_rejects_wrong_type_for_string_schema():
    """Schema check: string schema rejects a number."""
    assert meets_success(42, {"schema": "string"}) is False


def test_meets_success_accepts_correct_type_for_list_schema():
    """Schema check: list schema accepts a list."""
    assert meets_success([{"a": 1}], {"schema": "record[]"}) is True


def test_meets_success_accepts_correct_type_for_dict_schema():
    """Schema check: dict schema accepts a dict."""
    assert meets_success({"key": "val"}, {"schema": "Record"}) is True
