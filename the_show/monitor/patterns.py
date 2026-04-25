from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

DEFAULT_STALLED_SECONDS = int(os.environ.get("THE_SHOW_STALLED_THRESHOLD", "600"))
DEFAULT_RETRY_STORM_MAX = int(os.environ.get("THE_SHOW_RETRY_STORM_MAX", "5"))
DEFAULT_RETRY_STORM_WINDOW = int(os.environ.get("THE_SHOW_RETRY_STORM_WINDOW", "60"))
DEFAULT_POLICY_DENIAL_MAX = int(os.environ.get("THE_SHOW_POLICY_DENIAL_MAX", "3"))
OLLAMA_BASE_URL = os.environ.get("THE_SHOW_OLLAMA_URL", "http://localhost:11434")
QWEN_MODEL = os.environ.get("THE_SHOW_QWEN_MODEL", "qwen3:14b")


def _parse_ts(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def detect_stalled(
    events: List[Dict[str, Any]],
    threshold_seconds: int = DEFAULT_STALLED_SECONDS,
) -> Optional[Dict[str, Any]]:
    """Return stall info if no event for longer than threshold_seconds."""
    if not events:
        return None
    last = events[-1]
    elapsed = (datetime.now(timezone.utc) - _parse_ts(last["created_at"])).total_seconds()
    if elapsed > threshold_seconds:
        return {
            "elapsed_seconds": elapsed,
            "threshold_seconds": threshold_seconds,
            "last_event_type": last["event_type"],
            "last_scene_id": last.get("scene_id"),
        }
    return None


def detect_retry_storm(
    events: List[Dict[str, Any]],
    max_retries: int = DEFAULT_RETRY_STORM_MAX,
    window_seconds: int = DEFAULT_RETRY_STORM_WINDOW,
) -> List[Dict[str, Any]]:
    """Return entries for scenes with retry count > max_retries within window."""
    now = datetime.now(timezone.utc)
    scene_retries: Dict[str, int] = {}
    for ev in events:
        if ev["event_type"] != "attempt" or not ev.get("scene_id"):
            continue
        age = (now - _parse_ts(ev["created_at"])).total_seconds()
        if age <= window_seconds:
            scene_retries[ev["scene_id"]] = scene_retries.get(ev["scene_id"], 0) + 1
    return [
        {
            "scene_id": sid,
            "retry_count": count,
            "max_retries": max_retries,
            "window_seconds": window_seconds,
        }
        for sid, count in scene_retries.items()
        if count > max_retries
    ]


def detect_cost_runaway(
    events: List[Dict[str, Any]],
    soft_cap_usd: Optional[float],
    hard_cap_usd: Optional[float],
) -> Optional[Dict[str, Any]]:
    """Return cost info if cumulative cost exceeds a cap."""
    if not soft_cap_usd and not hard_cap_usd:
        return None
    total = sum(ev.get("cost_usd") or 0.0 for ev in events)
    if hard_cap_usd and total >= hard_cap_usd:
        return {"total_cost_usd": total, "cap_usd": hard_cap_usd, "cap_type": "hard"}
    if soft_cap_usd and total >= soft_cap_usd:
        return {"total_cost_usd": total, "cap_usd": soft_cap_usd, "cap_type": "soft"}
    return None


def detect_policy_denials(
    events: List[Dict[str, Any]],
    max_denials: int = DEFAULT_POLICY_DENIAL_MAX,
) -> List[Dict[str, Any]]:
    """Return entries for scenes that have hit policy_denied >= max_denials times."""
    scene_counts: Dict[str, int] = {}
    for ev in events:
        if ev["event_type"] == "policy_denied" and ev.get("scene_id"):
            scene_counts[ev["scene_id"]] = scene_counts.get(ev["scene_id"], 0) + 1
    return [
        {"scene_id": sid, "denial_count": count, "max_denials": max_denials}
        for sid, count in scene_counts.items()
        if count >= max_denials
    ]


def check_ollama_available(base_url: str = OLLAMA_BASE_URL) -> Optional[str]:
    """
    Return the Qwen model name if available, else None.
    Logs a warning and available models if Qwen isn't found.
    """
    try:
        req = urllib.request.Request(f"{base_url}/api/tags", method="GET")
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read())
        models = [m["name"] for m in data.get("models", [])]
        if QWEN_MODEL in models:
            return QWEN_MODEL
        logger.warning(
            "Qwen model '%s' not found in Ollama. Available: %s. "
            "Oscillation detection disabled.",
            QWEN_MODEL,
            models,
        )
        return None
    except Exception as exc:
        logger.warning("Ollama not reachable (%s). Oscillation detection disabled.", exc)
        return None


def detect_oscillation(
    scene_id: str,
    strategy_outputs: List[str],
    ollama_base_url: str = OLLAMA_BASE_URL,
    model: str = QWEN_MODEL,
) -> Optional[Dict[str, Any]]:
    """
    Use Qwen to classify whether successive strategy outputs are oscillating.
    Returns details dict if oscillating, else None.
    Only called when retry count > 3 and hard-signal rules haven't fired.
    """
    if len(strategy_outputs) < 2:
        return None

    recent = strategy_outputs[-4:]  # last 4 outputs max
    prompt = (
        "You are analysing an AI agent that is retrying a task. "
        "Look at these successive strategy outputs and classify whether the agent "
        "is making genuine progress (converging), getting worse (diverging), "
        "or going in circles with superficial changes (oscillating).\n\n"
        "Outputs (oldest first):\n"
    )
    for i, out in enumerate(recent, 1):
        prompt += f"{i}. {out[:500]}\n"
    prompt += (
        "\nRespond with exactly one word: converging, diverging, or oscillating. "
        "No explanation."
    )

    payload = json.dumps({
        "model": model,
        "prompt": prompt,
        "stream": False,
    }).encode()

    try:
        req = urllib.request.Request(
            f"{ollama_base_url}/api/generate",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read())
        classification = result.get("response", "").strip().lower()
        if "oscillat" in classification:
            return {
                "scene_id": scene_id,
                "classification": classification,
                "outputs_checked": len(recent),
            }
        return None
    except Exception as exc:
        logger.warning("Oscillation check failed for scene %s: %s", scene_id, exc)
        return None
