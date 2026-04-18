from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional
import time


@dataclass
class AdapterResult:
    success: bool
    output: Any = None
    error_type: Optional[str] = None
    message: Optional[str] = None
    duration_ms: int = 0
    cost_usd: float = 0.0


def execute_strategy(strategy, resolved_inputs: Dict[str, Any], rehearsal: bool = False) -> AdapterResult:
    '''
    Stub executor.

    Replace this with real integrations to:
    - local tools
    - MCP endpoints
    - agent runtimes
    - model providers
    '''
    start = time.time()

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

    if strategy.method == "sub-agent":
        contacts = resolved_inputs.get("contacts", [])
        output = []
        for item in contacts[:50]:
            output.append(
                {
                    **item,
                    "title": "Director",
                    "website": "https://example.com",
                    "linkedin": "https://linkedin.com/in/example",
                }
            )
        return AdapterResult(
            success=True,
            output=output,
            duration_ms=int((time.time() - start) * 1000),
            cost_usd=0.25,
        )

    return AdapterResult(
        success=False,
        error_type="unsupported",
        message=f"Unsupported strategy method/action: {strategy.method}/{strategy.action}",
        duration_ms=int((time.time() - start) * 1000),
        cost_usd=0.0,
    )
