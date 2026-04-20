from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Dict, Optional

REHEARSAL_DIR = Path.home() / ".the-show" / "rehearsal"


def get_rehearsal_dir(show_id: str = "") -> Path:
    sub = REHEARSAL_DIR / show_id if show_id else REHEARSAL_DIR / "_default"
    sub.mkdir(parents=True, exist_ok=True)
    return sub


def rehearsal_output_path(show_id: str, original_path: str) -> str:
    """Redirect a write-json path to the rehearsal output directory."""
    dest = get_rehearsal_dir(show_id) / "outputs"
    dest.mkdir(parents=True, exist_ok=True)
    name = Path(original_path).name or "output.json"
    return str(dest / name)


def canned_sub_agent_response(scene_id: str, model: str, success_when: Dict[str, Any]) -> Any:
    """Return a deterministic canned response whose type matches the declared output schema."""
    schema = (success_when or {}).get("schema", "")
    schema_l = schema.lower().strip() if schema else ""

    if "[]" in schema or schema_l.startswith("list[") or schema_l.startswith("list "):
        return [{"rehearsal": True, "scene": scene_id, "item": 1}]
    if schema_l in ("string", "str"):
        return f"[REHEARSAL] Canned response for scene '{scene_id}'"
    if schema_l in ("int", "integer", "float", "number"):
        return 0
    return {"rehearsal": True, "scene": scene_id, "model": model}


def synthetic_approval() -> str:
    """Return the configured synthetic resolution (default: APPROVE).

    Set SHOW_REHEARSAL_APPROVAL=REJECT|STOP|CONTINUE|TIMEOUT to inject
    failure paths in rehearsal.
    """
    raw = os.environ.get("SHOW_REHEARSAL_APPROVAL", "APPROVE").upper()
    if raw == "TIMEOUT":
        return "exhausted"
    if raw in ("APPROVE", "REJECT", "STOP", "CONTINUE"):
        return raw
    return "APPROVE"


def log_urgent_send(show_id: str, scene_id: Optional[str], prompt: str, resolution: str) -> Path:
    """Log an intercepted urgent-contact send to the rehearsal log. Returns log path."""
    log_dir = get_rehearsal_dir(show_id)
    log_file = log_dir / "urgent_contact.log"
    entry = {
        "type": "urgent_contact",
        "show_id": show_id,
        "scene_id": scene_id,
        "prompt": prompt,
        "synthetic_resolution": resolution,
        "logged_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    with log_file.open("a") as f:
        f.write(json.dumps(entry) + "\n")
    return log_file


def log_sub_agent_call(show_id: str, scene_id: str, model: str, prompt_snippet: str) -> None:
    """Log an intercepted sub-agent call to the rehearsal log."""
    log_dir = get_rehearsal_dir(show_id)
    log_file = log_dir / "sub_agent_calls.log"
    entry = {
        "type": "sub_agent",
        "show_id": show_id,
        "scene_id": scene_id,
        "model": model,
        "prompt_snippet": prompt_snippet[:200],
        "logged_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    with log_file.open("a") as f:
        f.write(json.dumps(entry) + "\n")
