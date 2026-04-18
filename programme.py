from __future__ import annotations

from pathlib import Path
import json

from models import ShowSettings, ShowState


def generate_programme(show: ShowSettings, state: ShowState, out_dir: str = ".show_output") -> tuple[Path, Path]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    md_path = out / f"{show.id}_programme.md"
    json_path = out / f"{show.id}_programme.json"

    lines = []
    lines.append(f"# Programme: {show.title}")
    lines.append("")
    lines.append(f"- Show ID: `{show.id}`")
    lines.append(f"- Status: **{state.status}**")
    lines.append(f"- Rehearsal: `{show.rehearsal}`")
    lines.append(f"- Total cost (USD): `{state.total_cost_usd:.2f}`")
    lines.append("")
    lines.append("## Scene Summary")
    lines.append("")

    for scene_id, scene_state in state.scenes.items():
        lines.append(f"### {scene_id}")
        lines.append(f"- Status: `{scene_state.status}`")
        if scene_state.selected_strategy:
            lines.append(f"- Strategy used: `{scene_state.selected_strategy}`")
        if scene_state.warnings:
            lines.append(f"- Warnings: {', '.join(scene_state.warnings)}")
        lines.append("")

    md_path.write_text("\n".join(lines), encoding="utf-8")
    json_path.write_text(json.dumps(state.to_dict(), indent=2), encoding="utf-8")
    return md_path, json_path
