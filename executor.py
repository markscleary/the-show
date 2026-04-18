from __future__ import annotations

import copy
from typing import Any, Dict
import time
import random

from adapters import execute_strategy
from models import AttemptRecord, Scene, ShowSettings, ShowState
from programme import generate_programme
from state import add_event, initialize_state, persist_state


class ExecutionError(Exception):
    pass


def resolve_inputs(scene: Scene, state: ShowState) -> Dict[str, Any]:
    resolved = {}
    for input_name, binding in scene.inputs.items():
        expr = binding[5:-1]  # from(scene.output)
        scene_id, output_name = expr.split(".", 1)
        try:
            resolved[input_name] = state.outputs[scene_id][output_name]
        except KeyError as exc:
            raise ExecutionError(
                f"Unable to resolve input '{input_name}' from binding {binding}."
            ) from exc
    return resolved


def meets_success(scene: Scene, output: Any) -> bool:
    rules = scene.success_when
    if output is None:
        return False
    min_length = rules.get("min-length")
    if min_length is not None:
        try:
            if len(output) < min_length:
                return False
        except TypeError:
            return False
    return True


def sleep_with_backoff(attempt: int, base_delay: float, jitter: bool) -> None:
    delay = base_delay * (2 ** max(0, attempt - 1))
    if jitter:
        delay += random.uniform(0, 0.25)
    time.sleep(delay)


def run_strategy(scene: Scene, strategy, resolved_inputs: Dict[str, Any], show: ShowSettings, state: ShowState, label: str):
    policy = scene.retry_policy
    attempts = max(1, policy.max_attempts)

    for attempt_num in range(1, attempts + 1):
        result = execute_strategy(strategy, resolved_inputs, rehearsal=show.rehearsal)
        record = AttemptRecord(
            scene=scene.scene,
            strategy_label=label,
            status="success" if result.success else "failed",
            error_type=result.error_type,
            message=result.message,
            duration_ms=result.duration_ms,
            cost_usd=result.cost_usd,
        )
        state.scenes[scene.scene].attempts.append(record)
        state.total_cost_usd += result.cost_usd
        persist_state(state)

        if result.success and meets_success(scene, result.output):
            return True, result

        retriable = result.error_type in set(policy.retriable_errors)
        if attempt_num < attempts and retriable:
            sleep_with_backoff(attempt_num, policy.base_delay_seconds, policy.jitter)
            continue
        return False, result

    return False, result


def apply_adaptation(scene: Scene, strategy):
    """Return an adapted copy of strategy with reduced params, or None if not applicable."""
    if not scene.adaptive.allowed:
        return None
    adapted = copy.copy(strategy)
    params = dict(adapted.params)
    if "batch-size" in params:
        minimum = scene.adaptive.bounds.get("batch-size", {}).get("min", 1)
        params["batch-size"] = max(minimum, int(params["batch-size"]) // 2)
        adapted.params = params
        return adapted
    return None


def handle_cut(scene: Scene) -> str:
    if scene.cut.condition == "escalate":
        return "blocked"
    if scene.cut.condition == "continue":
        return "cut"
    if scene.cut.condition == "continue-with-partial":
        return "played-partial"
    return "failed"


def run_show(show: ShowSettings) -> ShowState:
    state = initialize_state(show)
    state.status = "running"
    add_event(state, "show_started", {"show_id": show.id})
    persist_state(state)

    for scene in show.running_order:
        scene_state = state.scenes[scene.scene]

        unresolved = [dep for dep in scene.depends_on if state.scenes[dep].status not in {
            "played-principal", "played-fallback", "played-adaptive", "played-partial"
        }]
        if unresolved:
            scene_state.status = "cut"
            scene_state.warnings.append(f"Unresolved dependencies: {', '.join(unresolved)}")
            persist_state(state)
            continue

        scene_state.status = "running"
        persist_state(state)

        resolved_inputs = resolve_inputs(scene, state) if scene.inputs else {}

        improvisation = show.sliders.get("improvisation", "script")
        adaptive_enabled = improvisation in {"standard", "jazz"} and scene.adaptive.allowed

        # Spec section 9 order:
        # Principal → Adaptive(Principal) → Fallback 1 → Adaptive(Fallback 1) → … → Cut
        all_strategies = [("principal", scene.principal)] + [
            (f"fallback-{i}", fb) for i, fb in enumerate(scene.fallbacks, start=1)
        ]

        scene_success = False
        last_result = None

        for label, strategy in all_strategies:
            success, result = run_strategy(scene, strategy, resolved_inputs, show, state, label)
            last_result = result

            if success:
                if label == "principal":
                    scene_state.status = "played-principal"
                elif label.startswith("fallback"):
                    scene_state.status = "played-fallback"
                else:
                    scene_state.status = "played-adaptive"
                scene_state.selected_strategy = label
                for output_name in scene.outputs.keys():
                    state.outputs.setdefault(scene.scene, {})[output_name] = result.output
                persist_state(state)
                scene_success = True
                break

            # Try adaptive variation of this strategy before moving to next
            if adaptive_enabled:
                adapted = apply_adaptation(scene, strategy)
                if adapted is not None:
                    adaptive_label = f"adaptive({label})"
                    success, result = run_strategy(scene, adapted, resolved_inputs, show, state, adaptive_label)
                    last_result = result
                    if success:
                        scene_state.status = "played-adaptive"
                        scene_state.selected_strategy = adaptive_label
                        for output_name in scene.outputs.keys():
                            state.outputs.setdefault(scene.scene, {})[output_name] = result.output
                        persist_state(state)
                        scene_success = True
                        break

        if scene_success:
            continue

        # All strategies (and their adaptive variations) have failed
        scene_state.status = handle_cut(scene)

        # continue-with-partial: propagate whatever output we have so downstream can use it
        if scene_state.status == "played-partial" and last_result is not None and last_result.output is not None:
            for output_name in scene.outputs.keys():
                state.outputs.setdefault(scene.scene, {})[output_name] = last_result.output

        persist_state(state)

        if scene_state.status == "blocked":
            state.status = "paused"
            add_event(state, "show_blocked", {"scene": scene.scene})
            persist_state(state)
            break
        if scene_state.status == "failed":
            state.status = "aborted"
            add_event(state, "show_failed", {"scene": scene.scene})
            persist_state(state)
            break

    if state.status == "running":
        state.status = "completed"
    add_event(state, "show_finished", {"status": state.status})
    persist_state(state)
    generate_programme(show, state)
    return state
