from __future__ import annotations

from collections import deque
from typing import List

from models import ShowSettings, ShowState
from state import TERMINAL_STATES, persist_scene_state


def prune_dag_on_blocked(
    state: ShowState,
    show: ShowSettings,
    blocked_scene_id: str,
) -> List[str]:
    """
    Forward-traverse the DAG from blocked_scene_id.
    Mark every scene that (transitively) depends on it as
    'cascading-dependency-failure', unless already terminal.
    Returns list of affected scene IDs.
    """
    # Build: scene_id -> list of scenes that depend on it
    dependents: dict[str, List[str]] = {}
    for scene in show.running_order:
        for dep in scene.depends_on:
            dependents.setdefault(dep, []).append(scene.scene)

    queue: deque[str] = deque([blocked_scene_id])
    affected: List[str] = []

    while queue:
        parent_id = queue.popleft()
        for child_id in dependents.get(parent_id, []):
            sc = state.scenes.get(child_id)
            if sc is None or sc.status in TERMINAL_STATES:
                continue
            sc.status = "cascading-dependency-failure"
            persist_scene_state(state.show_id, sc)
            affected.append(child_id)
            queue.append(child_id)

    return affected
