from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from the_show import state as _state

OUT_BASE = Path.home() / ".the-show" / "state"


def _out_dir(show_id: str) -> Path:
    d = OUT_BASE / show_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def generate_programme(show_id: str) -> tuple[Path, Path]:
    """Generate markdown and JSON programme from SQLite state."""
    show_state = _state.load_show_state(show_id)
    events = _state.get_events(show_id)
    outputs = _state.load_scene_outputs(show_id)

    out_dir = _out_dir(show_id)
    md_path = out_dir / "programme.md"
    json_path = out_dir / "programme.json"

    # ── Markdown ─────────────────────────────────────────────────────────────
    lines: list[str] = []
    lines += [f"# Programme: {show_state.title}", ""]
    lines += [
        f"- Show ID: `{show_state.show_id}`",
        f"- Status: **{show_state.status}**",
        f"- Total cost (USD): `{show_state.total_cost_usd:.4f}`",
        "",
    ]

    # Outcome counts
    statuses = [sc.status for sc in show_state.scenes.values()]
    played = sum(
        1 for s in statuses
        if s in _state.SUCCESS_STATES
    )
    lines += [
        "## Outcome",
        "",
        f"- Scenes played: {played} of {len(statuses)}",
        f"- Scenes cut / blocked / failed: {len(statuses) - played}",
        "",
    ]

    lines += ["## Scene Summary", ""]
    for scene_id, sc in show_state.scenes.items():
        lines.append(f"### {scene_id}")
        lines.append(f"- Status: `{sc.status}`")
        if sc.selected_strategy:
            lines.append(f"- Strategy: `{sc.selected_strategy}`")
        if sc.warnings:
            lines.append(f"- Warnings: {', '.join(sc.warnings)}")
        lines.append("")

    # Urgent matters
    matters = _state.get_urgent_matters(show_id)
    lines += ["## Urgent Matters", ""]
    if matters:
        for m in matters:
            res = f" → {m['resolution']}" if m.get("resolution") else ""
            lines.append(f"- #{m['id']} [{m['severity']}] {m['status']}{res}  scene={m['scene_id']}")
    else:
        lines.append("_None._")
    lines.append("")

    # Monitor signals
    monitor_events = _state.get_monitor_events(show_id)
    lines += ["## Monitor Signals", ""]
    if monitor_events:
        from collections import Counter
        by_type = Counter(ev["trigger_type"] for ev in monitor_events)
        lines.append(f"- Total monitor events: {len(monitor_events)}")
        for trigger_type, count in sorted(by_type.items()):
            lines.append(f"  - {trigger_type}: {count}")
        escalated = [ev for ev in monitor_events if ev["acknowledged"]]
        lines.append(f"- Events acknowledged (processed by Stage Manager): {len(escalated)}")
    else:
        lines.append("_No monitor events._")
    lines.append("")

    # Recent events
    lines += ["## Event Log (last 10)", ""]
    for ev in events[-10:]:
        scene_tag = f" [{ev['scene_id']}]" if ev["scene_id"] else ""
        lines.append(f"- `{ev['created_at']}` **{ev['event_type']}**{scene_tag}")
    lines.append("")

    md_path.write_text("\n".join(lines), encoding="utf-8")

    # ── JSON ─────────────────────────────────────────────────────────────────
    doc = {
        "show_id": show_state.show_id,
        "title": show_state.title,
        "status": show_state.status,
        "total_cost_usd": show_state.total_cost_usd,
        "scenes": {
            sid: {
                "status": sc.status,
                "selected_strategy": sc.selected_strategy,
                "warnings": sc.warnings,
            }
            for sid, sc in show_state.scenes.items()
        },
        "outputs": {
            sid: {k: "<truncated>" for k in ov}
            for sid, ov in outputs.items()
        },
        "events": events,
        "monitor_events": monitor_events,
    }
    json_path.write_text(json.dumps(doc, indent=2), encoding="utf-8")

    return md_path, json_path
