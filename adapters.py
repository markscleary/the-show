from __future__ import annotations

import copy
import time
from dataclasses import dataclass, replace
from typing import Any, Dict, Optional
from uuid import uuid4


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
        # Find the first list value in resolved_inputs regardless of key name
        input_list: list = next(
            (v for v in resolved_inputs.values() if isinstance(v, list)),
            [],
        )
        if not input_list:
            # Fallback: generate synthetic contacts so stub always returns data
            input_list = [
                {"name": f"Contact {i}", "email": f"c{i}@example.com"}
                for i in range(100)
            ]

        output = []
        for item in input_list[:50]:
            row = dict(item) if isinstance(item, dict) else {"value": item}
            row.setdefault("title", "Director")
            row.setdefault("website", "https://example.com")
            row.setdefault("linkedin", "https://linkedin.com/in/example")
            output.append(row)

        return AdapterResult(
            success=True,
            output=output,
            duration_ms=int((time.time() - start) * 1000),
            cost_usd=0.25,
        )

    # --- human-approval is handled by the executor stub before reaching here ---

    return AdapterResult(
        success=False,
        error_type="unsupported",
        message=f"Unsupported strategy method/action: {strategy.method}/{strategy.action}",
        duration_ms=int((time.time() - start) * 1000),
        cost_usd=0.0,
    )
