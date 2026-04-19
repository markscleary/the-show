from __future__ import annotations

import copy
import json
import logging
import os
import time
from dataclasses import dataclass, replace
from typing import Any, Dict, Optional
from uuid import uuid4

import httpx


@dataclass
class AdapterResult:
    success: bool
    output: Any = None
    error_type: Optional[str] = None
    message: Optional[str] = None
    duration_ms: int = 0
    cost_usd: float = 0.0


# Methods / actions that produce side effects and need idempotency protection
_SIDE_EFFECTFUL_METHODS = {"send", "post", "pay", "delete", "write", "publish"}
_SIDE_EFFECTFUL_ACTIONS = {
    "send-email",
    "send-message",
    "post-to",
    "make-payment",
    "delete-file",
    "write-file",
    "write-json",
    "publish-to",
}


def is_side_effectful(strategy) -> bool:
    """Return True if this strategy performs a side effect requiring idempotency."""
    if strategy.method in _SIDE_EFFECTFUL_METHODS:
        return True
    if strategy.action and strategy.action in _SIDE_EFFECTFUL_ACTIONS:
        return True
    return False


def attach_idempotency_key(strategy) -> Any:
    """Return a copy of the strategy with an idempotency key injected into params."""
    key = f"show-{uuid4().hex[:16]}"
    new_params = dict(strategy.params)
    new_params["_idempotency_key"] = key
    return replace(strategy, params=new_params)


_FALLBACK_MODEL = "qwen-noThink"
_RETRIABLE_STATUS_CODES = {429, 502, 503}

# Indirection so tests can monkeypatch without touching the global time module
_sleep = time.sleep


def _do_llm_call(proxy_url: str, master_key: str, model: str, prompt: str, max_tokens: int) -> dict:
    """Single (non-retrying) HTTP call to the LiteLLM proxy. Returns parsed output dict."""
    try:
        response = httpx.post(
            f"{proxy_url}/v1/chat/completions",
            headers={"Authorization": f"Bearer {master_key}"},
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": max_tokens,
            },
            timeout=120.0,
        )
    except httpx.ConnectError:
        raise  # caller handles

    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise httpx.HTTPStatusError(
            f"[sub-agent] HTTP {response.status_code} from proxy: {response.text[:400]}",
            request=exc.request,
            response=exc.response,
        ) from exc

    data = response.json()
    choices = data.get("choices")
    if not choices:
        raise RuntimeError(f"[sub-agent] Empty choices in proxy response: {data}")

    content = choices[0]["message"]["content"]
    if not content:
        raise RuntimeError("[sub-agent] Empty content in proxy response")

    cost_est = 0.0
    usage = data.get("usage")
    if usage:
        input_tokens = usage.get("prompt_tokens", 0)
        output_tokens = usage.get("completion_tokens", 0)
        cost_est = (input_tokens / 1_000_000) * 3.0 + (output_tokens / 1_000_000) * 15.0
        logging.info(
            "[sub-agent] model=%s input_tokens=%d output_tokens=%d cost_est=$%.6f",
            model, input_tokens, output_tokens, cost_est,
        )

    def _embed_cost(result: dict | list) -> dict | list:
        if cost_est == 0.0:
            return result
        if isinstance(result, dict):
            result["_cost_usd"] = cost_est
        elif isinstance(result, list) and result and isinstance(result[0], dict):
            result[0]["_cost_usd"] = cost_est
        return result

    try:
        return _embed_cost(json.loads(content))
    except json.JSONDecodeError:
        pass

    try:
        from sanitise import strip_markdown_fences
    except ImportError:
        from sanitize import strip_markdown_fences  # type: ignore[no-redef]
    cleaned = strip_markdown_fences(content)
    try:
        return _embed_cost(json.loads(cleaned))
    except json.JSONDecodeError:
        return _embed_cost({"text": content})


def call_sub_agent(model: str, prompt: str, max_tokens: int = 2000) -> dict:
    """Make a real LLM call via the LiteLLM proxy with retry and Qwen fallback.

    Retries up to 3 times with exponential backoff on transient errors (ConnectError,
    429/502/503). If the primary model exhausts all attempts, falls back to
    _FALLBACK_MODEL (qwen-noThink via local Ollama through the proxy).

    Raises:
        RuntimeError: proxy unreachable after all retries and fallback
        httpx.HTTPStatusError: non-retriable HTTP error
    """
    proxy_url = os.getenv("LITELLM_PROXY_URL", "http://localhost:4000")
    master_key = os.getenv("LITELLM_MASTER_KEY", "")

    last_exc: Optional[Exception] = None
    for attempt in range(1, 4):
        try:
            return _do_llm_call(proxy_url, master_key, model, prompt, max_tokens)
        except httpx.ConnectError as exc:
            last_exc = exc
            logging.warning(
                "[sub-agent] Attempt %d/3: proxy unreachable at %s: %s",
                attempt, proxy_url, exc,
            )
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code if exc.response is not None else 0
            if status in _RETRIABLE_STATUS_CODES:
                last_exc = exc
                logging.warning(
                    "[sub-agent] Attempt %d/3: HTTP %d from proxy", attempt, status
                )
            else:
                raise
        if attempt < 3:
            _sleep(2 ** (attempt - 1))

    # Primary model exhausted — try fallback if it's a different model
    if model != _FALLBACK_MODEL:
        logging.warning(
            "[sub-agent] Primary model '%s' failed after 3 attempts — falling back to '%s'",
            model, _FALLBACK_MODEL,
        )
        try:
            return _do_llm_call(proxy_url, master_key, _FALLBACK_MODEL, prompt, max_tokens)
        except (httpx.ConnectError, httpx.HTTPStatusError, RuntimeError) as exc:
            raise RuntimeError(
                f"[sub-agent] Primary '{model}' and fallback '{_FALLBACK_MODEL}' both failed: {exc}"
            ) from exc

    raise RuntimeError(
        f"[sub-agent] LiteLLM proxy unreachable at {proxy_url} after 3 attempts: {last_exc}"
    ) from last_exc


def execute_strategy(strategy, resolved_inputs: Dict[str, Any], rehearsal: bool = False) -> AdapterResult:
    """Stub executor — replace with real integrations in Session 4."""
    start = time.time()

    # --- tool-call: read-csv ---
    if strategy.method == "tool-call" and strategy.action == "read-csv":
        path = strategy.params.get("path", "")
        if "backup" in path:
            output = [{"name": "Backup Contact", "email": "backup@example.com"}] * 50
        else:
            output = [{"name": "Contact", "email": "contact@example.com"}] * 100
        return AdapterResult(
            success=True,
            output=output,
            duration_ms=int((time.time() - start) * 1000),
            cost_usd=0.0,
        )

    # --- tool-call: write-json ---
    if strategy.method == "tool-call" and strategy.action == "write-json":
        path = strategy.params.get("path", "/tmp/the-show-output.json")
        return AdapterResult(
            success=True,
            output=path,
            duration_ms=int((time.time() - start) * 1000),
            cost_usd=0.0,
        )

    # --- sub-agent ---
    if strategy.method == "sub-agent":
        model = strategy.params.get("model", "")
        brief = getattr(strategy, "brief", None) or strategy.params.get("brief", "")

        # Build prompt: include resolved inputs as context if present
        if resolved_inputs:
            context_lines = []
            for key, val in resolved_inputs.items():
                serialised = json.dumps(val, indent=2) if not isinstance(val, str) else val
                context_lines.append(f"--- {key} ---\n{serialised}")
            context_block = "\n\n".join(context_lines)
            prompt = f"{brief}\n\n=== INPUTS ===\n{context_block}"
        else:
            prompt = brief

        if not prompt:
            return AdapterResult(
                success=False,
                error_type="unsupported",
                message="sub-agent strategy has no brief or prompt",
                duration_ms=int((time.time() - start) * 1000),
                cost_usd=0.0,
            )

        try:
            output = call_sub_agent(model=model, prompt=prompt)
        except RuntimeError as exc:
            return AdapterResult(
                success=False,
                error_type="timeout" if "unreachable" in str(exc).lower() else "unsupported",
                message=str(exc),
                duration_ms=int((time.time() - start) * 1000),
                cost_usd=0.0,
            )
        except httpx.HTTPStatusError as exc:
            status_code = exc.response.status_code if exc.response is not None else 0
            error_type = "rate-limit" if status_code == 429 else "unsupported"
            return AdapterResult(
                success=False,
                error_type=error_type,
                message=str(exc),
                duration_ms=int((time.time() - start) * 1000),
                cost_usd=0.0,
            )

        # Extract cost estimate if the output dict carries a _cost_usd sentinel
        # (used by call_sub_agent when the proxy returns usage data, and by test mocks)
        cost_est = 0.0
        if isinstance(output, dict):
            cost_est = float(output.pop("_cost_usd", 0.0))
        elif isinstance(output, list) and output and isinstance(output[0], dict):
            # Pull from the first item if it's a list and first element carries the key
            cost_est = float(output[0].pop("_cost_usd", 0.0))

        return AdapterResult(
            success=True,
            output=output,
            duration_ms=int((time.time() - start) * 1000),
            cost_usd=cost_est,
        )

    # --- human-approval is handled by the executor stub before reaching here ---

    return AdapterResult(
        success=False,
        error_type="unsupported",
        message=f"Unsupported strategy method/action: {strategy.method}/{strategy.action}",
        duration_ms=int((time.time() - start) * 1000),
        cost_usd=0.0,
    )
