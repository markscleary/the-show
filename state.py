from __future__ import annotations

from pathlib import Path
import json
from typing import Dict

from models import ShowSettings, ShowState, SceneState


STATE_DIR = Path(".show_state")


def initialize_state(show: ShowSettings) -> ShowState:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    state = ShowState(show_id=show.id, title=show.title, status="planned")
    for scene in show.running_order:
        state.scenes[scene.scene] = SceneState(scene=scene.scene)
    return state


def persist_state(state: ShowState) -> Path:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    path = STATE_DIR / f"{state.show_id}_state.json"
    path.write_text(json.dumps(state.to_dict(), indent=2), encoding="utf-8")
    return path


def load_state(path: str | Path) -> Dict:
    path = Path(path)
    return json.loads(path.read_text(encoding="utf-8"))


def add_event(state: ShowState, event_type: str, payload: Dict) -> None:
    state.events.append({"event_type": event_type, "payload": payload})
