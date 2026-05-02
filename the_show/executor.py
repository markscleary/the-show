from __future__ import annotations

import copy
import random
import time
from typing import Any, Dict, Optional, Tuple

from the_show.adapters import AdapterResult, execute_strategy, is_side_effectful, attach_idempotency_key
from the_show.models import AttemptRecord, Scene, ShowSettings, ShowState, Strategy
from the_show.programme import generate_programme
from the_show.sanitise import strip_markdown_fences
from the_show.state import (
    SUCCESS_STATES,
    TERMINAL_STATES,
    add_event,
    get_db_path,
    initialize_state,
    persist_delivered_status,
    persist_scene_output,
    persist_scene_state,
    persist_show_state,
    persist_state,
    get_unacknowledged_monitor_events,
    acknowledge_monitor_events as _acknowledge_monitor_events,
)


class ExecutionError(Exception):
    pass


# ──────────────────────────────────────────────────────────────────────────────
# Input resolution
# ──────────────────────────────────────────────────────────────────────────────

def resolve_inputs(scene: Scene, state: ShowState) -> Dict[str, Any]:
    resolved = {}
    for input_name, binding in scene.inputs.items():
        expr = binding[5:-1]  # strip "from(" and ")"
        scene_id, output_name = expr.split(".", 1)
        try:
            resolved[input_name] = state.outputs[scene_id][output_name]
        except KeyError as exc:
            raise ExecutionError(
                f"Unable to resolve input '{input_name}' from binding {binding}."
            ) from exc
    return resolved


# ──────────────────────────────────────────────────────────────────────────────
# Success evaluation
# ──────────────────────────────────────────────────────────────────────────────

def meets_success(output: Any, success_when: Dict[str, Any]) -> bool:
    """Check whether output satisfies the given success criteria."""
    if output is None:
        return False
    if not success_when:
        return True  # no criteria = accept any non-None output

    schema = success_when.get("schema")
    if schema:
        schema_l = schema.lower().strip()
        if "[]" in schema or schema_l.startswith("list[") or schema_l.startswith("list "):
            if not isinstance(output, list):
                print(f"[WARN] Schema check: expected list, got {type(output).__name__}")
                return False
        elif schema_l in ("string", "str"):
            if not isinstance(output, str):
                print(f"[WARN] Schema check: expected string, got {type(output).__name__}")
                return False
        elif schema_l in ("int", "integer", "float", "number"):
            if not isinstance(output, (int, float)):
                print(f"[WARN] Schema check: expected number, got {type(output).__name__}")
                return False
        else:
            # Object/dict schema
            if not isinstance(output, dict):
                print(f"[WARN] Schema check for '{schema}': expected dict, got {type(output).__name__}")
                return False
        print(f"[INFO] Basic schema check for '{schema}' — OK")

    min_length = success_when.get("min-length")
    if min_length is not None:
        try:
            if len(output) < min_length:
                return False
        except TypeError:
            return False

    all_records_have = success_when.get("all-records-have")
    if all_records_have and isinstance(output, list):
        for record in output:
            if not isinstance(record, dict):
                return False
            for f in all_records_have:
                if f not in record:
                    return False

    return True


# ──────────────────────────────────────────────────────────────────────────────
# Backoff
# ──────────────────────────────────────────────────────────────────────────────

def sleep_with_backoff(attempt: int, base_delay: float, jitter: bool) -> None:
    delay = base_delay * (2 ** max(0, attempt - 1))
    if jitter:
        delay += random.uniform(0, 0.25)
    time.sleep(delay)


# ──────────────────────────────────────────────────────────────────────────────
# Human-approval — calls the real Urgent Contact dispatcher
# ──────────────────────────────────────────────────────────────────────────────

def run_human_approval(
    scene: Scene,
    strategy: Strategy,
    show: ShowSettings,
    state: ShowState,
    label: str,
) -> Tuple[bool, AdapterResult]:
    """Invoke the Urgent Contact dispatcher for a human-approval strategy."""

    # Rehearsal: resolve instantly with synthetic approval — no real channels
    if show.rehearsal:
        from the_show.rehearsal_adapter import synthetic_approval, log_urgent_send
        resolution = synthetic_approval()
        log_urgent_send(show.id, scene.scene, strategy.brief or scene.title, resolution)

        if resolution in ("APPROVE", "CONTINUE"):
            result = AdapterResult(success=True, output=resolution, duration_ms=0, cost_usd=0.0)
            success = True
        elif resolution == "STOP":
            result = AdapterResult(
                success=False, output=None, error_type="show-stop", duration_ms=0, cost_usd=0.0
            )
            success = False
        elif resolution == "exhausted":
            result = AdapterResult(
                success=False, output=None, error_type="blocked-no-response", duration_ms=0, cost_usd=0.0
            )
            success = False
        else:
            result = AdapterResult(
                success=False, output=None, error_type=resolution, duration_ms=0, cost_usd=0.0
            )
            success = False

        record = AttemptRecord(
            scene=scene.scene,
            strategy_label=label,
            status="success" if success else "failed",
            error_type=result.error_type,
            duration_ms=0,
            cost_usd=0.0,
        )
        state.scenes[scene.scene].attempts.append(record)
        add_event(
            state.show_id,
            "urgent_contact_resolved",
            scene_id=scene.scene,
            strategy_label=label,
            payload={"resolution": resolution, "rehearsal": True},
        )
        return success, result

    from the_show.urgent_contact.dispatcher import UrgentContactDispatcher, load_adapters

    db_path = get_db_path(state.show_id)
    adapters = list(load_adapters().values())
    dispatcher = UrgentContactDispatcher(
        db_path=str(db_path),
        show=show,
        adapters=adapters,
    )

    from datetime import datetime, timedelta, timezone as tz
    if scene.timeout_seconds:
        deadline_iso = (
            datetime.now(tz.utc) + timedelta(seconds=scene.timeout_seconds)
        ).isoformat()
    else:
        deadline_iso = None

    # Normalise strategy.to to a list before forwarding.
    to_list: Optional[list] = None
    if strategy.to is not None:
        to_list = [strategy.to] if isinstance(strategy.to, str) else list(strategy.to)

    resolution = dispatcher.raise_urgent_matter(
        trigger_type="human-approval",
        severity=strategy.severity or "urgent",
        prompt=strategy.brief or scene.title,
        deadline=deadline_iso,
        scene_id=scene.scene,
        channels=strategy.channels,
        to=to_list,
    )

    # Map resolution to (success, AdapterResult) for the outer strategy loop
    if resolution in ("APPROVE", "CONTINUE"):
        result = AdapterResult(success=True, output=resolution, duration_ms=0, cost_usd=0.0)
        success = True
    elif resolution == "STOP":
        result = AdapterResult(
            success=False, output=None, error_type="show-stop", duration_ms=0, cost_usd=0.0
        )
        success = False
    elif resolution == "exhausted":
        result = AdapterResult(
            success=False, output=None, error_type="blocked-no-response", duration_ms=0, cost_usd=0.0
        )
        success = False
    else:
        # REJECT or throttled
        result = AdapterResult(
            success=False, output=None, error_type=resolution, duration_ms=0, cost_usd=0.0
        )
        success = False

    record = AttemptRecord(
        scene=scene.scene,
        strategy_label=label,
        status="success" if success else "failed",
        error_type=result.error_type,
        duration_ms=0,
        cost_usd=0.0,
    )
    state.scenes[scene.scene].attempts.append(record)
    add_event(
        state.show_id,
        "urgent_contact_resolved",
        scene_id=scene.scene,
        strategy_label=label,
        payload={"resolution": resolution},
    )
    return success, result


# ──────────────────────────────────────────────────────────────────────────────
# Strategy execution (single strategy, with retries)
# ──────────────────────────────────────────────────────────────────────────────

def run_strategy(
    scene: Scene,
    strategy: Strategy,
    resolved_inputs: Dict[str, Any],
    show: ShowSettings,
    state: ShowState,
    label: str,
    effective_success_when: Dict[str, Any],
) -> Tuple[bool, AdapterResult]:
    """Run one strategy (with retries). Returns (success, last_result)."""

    # Human-approval: handled by Urgent Contact dispatcher, not by the adapter
    if strategy.method == "human-approval":
        return run_human_approval(scene, strategy, show, state, label)

    # Attach idempotency key once for all retries of this strategy invocation
    if is_side_effectful(strategy):
        strategy = attach_idempotency_key(strategy)
        add_event(
            state.show_id,
            "idempotency_key_attached",
            scene_id=scene.scene,
            strategy_label=label,
            payload={"key": strategy.params.get("_idempotency_key")},
        )

    policy = scene.retry_policy
    attempts = max(1, policy.max_attempts)

    last_result: Optional[AdapterResult] = None
    for attempt_num in range(1, attempts + 1):
        result = execute_strategy(
            strategy,
            resolved_inputs,
            rehearsal=show.rehearsal,
            show_id=state.show_id,
            scene_id=scene.scene,
            effective_success_when=effective_success_when,
        )
        last_result = result

        # Sanitise untrusted string output before success evaluation
        if scene.input_trust == "untrusted" and isinstance(result.output, str):
            result.output = strip_markdown_fences(result.output)

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

        add_event(
            state.show_id,
            "attempt",
            scene_id=scene.scene,
            strategy_label=label,
            payload={
                "attempt": attempt_num,
                "status": record.status,
                "error_type": record.error_type,
                "message": record.message,
            },
            cost=result.cost_usd,
            duration_ms=result.duration_ms,
        )
        persist_show_state(state)

        if result.success and meets_success(result.output, effective_success_when):
            return True, result

        retriable = result.error_type in set(policy.retriable_errors)
        if attempt_num < attempts and retriable:
            sleep_with_backoff(attempt_num, policy.base_delay_seconds, policy.jitter)
            continue
        return False, result

    return False, last_result  # type: ignore[return-value]


# ──────────────────────────────────────────────────────────────────────────────
# Adaptation
# ──────────────────────────────────────────────────────────────────────────────

def apply_adaptation(scene: Scene, strategy: Strategy) -> Optional[Strategy]:
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


# ──────────────────────────────────────────────────────────────────────────────
# Cut handling
# ──────────────────────────────────────────────────────────────────────────────

def handle_cut(scene: Scene) -> str:
    if scene.cut.condition == "escalate":
        return "blocked"
    if scene.cut.condition == "continue":
        return "cut"
    if scene.cut.condition == "continue-with-partial":
        return "played-partial"
    return "failed"


# ──────────────────────────────────────────────────────────────────────────────
# Monitor signal integration
# ──────────────────────────────────────────────────────────────────────────────

_MONITOR_ESCALATION_MAP = {
    "cost-runaway": ["cost-hard-cap-reached"],
    "stalled": ["any-scene-duration-over", "any-scene-duration-over-seconds"],
    "policy-denials": ["repeated-policy-denials"],
}


def check_monitor_signals(show_id: str) -> list:
    """Query monitor_events for unacknowledged triggers."""
    return get_unacknowledged_monitor_events(show_id)


def acknowledge_monitor_events(show_id: str, event_ids: list) -> None:
    """Mark monitor events as processed by stage manager."""
    _acknowledge_monitor_events(show_id, event_ids)


def _handle_monitor_signals(show_id: str, show: "ShowSettings", state: "ShowState") -> bool:
    """
    Check unacknowledged monitor events. Raise urgent matters for escalation-mapped triggers.
    Acknowledges all events after processing.
    Returns True if the show should be aborted (critical unhandled signal).
    """
    events = check_monitor_signals(show_id)
    if not events:
        return False

    escalate_when = show.bible.escalation  # top-level escalation dict from Prompt Book

    for ev in events:
        trigger = ev["trigger_type"]
        escalation_keys = _MONITOR_ESCALATION_MAP.get(trigger, [])
        should_escalate = any(escalate_when.get(k) for k in escalation_keys)

        if should_escalate and ev["severity"] in ("urgent", "critical") and not show.rehearsal:
            from the_show.urgent_contact.dispatcher import UrgentContactDispatcher, load_adapters
            db_path = get_db_path(state.show_id)
            adapters = list(load_adapters().values())
            dispatcher = UrgentContactDispatcher(
                db_path=str(db_path),
                show=show,
                adapters=adapters,
            )
            details = ev.get("details") or {}
            prompt = (
                f"Monitor alert: {trigger} detected. "
                f"Details: {details}"
            )
            dispatcher.raise_urgent_matter(
                trigger_type=f"monitor-{trigger}",
                severity=ev["severity"],
                prompt=prompt,
                deadline=None,
                scene_id=ev.get("scene_id"),
            )
            add_event(
                state.show_id,
                "monitor_escalated",
                scene_id=ev.get("scene_id"),
                payload={"trigger_type": trigger, "monitor_event_id": ev["id"]},
            )

        elif trigger in ("oscillation", "retry-storm"):
            # Warning-only — log to event stream but don't escalate unless operator configured
            add_event(
                state.show_id,
                f"monitor_warning_{trigger.replace('-', '_')}",
                scene_id=ev.get("scene_id"),
                payload=ev.get("details"),
            )

    acknowledge_monitor_events(show_id, [ev["id"] for ev in events])
    return False


# ──────────────────────────────────────────────────────────────────────────────
# Field validator hook (hook only — validators not implemented until later)
# ──────────────────────────────────────────────────────────────────────────────

def run_field_validators(scene: Scene) -> None:
    """Log field validator intentions. Actual validation is not yet implemented."""
    for _output_name, output_spec in scene.outputs.items():
        field_validators = output_spec.get("field-validators", {})
        for field_name, validator_spec in field_validators.items():
            validator_type = (
                validator_spec.split(":")[0]
                if isinstance(validator_spec, str) and ":" in validator_spec
                else str(validator_spec)
            )
            print(
                f"[INFO] Field validator '{validator_type}' on field '{field_name}'"
                f" — not yet implemented, skipping"
            )


# ──────────────────────────────────────────────────────────────────────────────
# Store scene output
# ──────────────────────────────────────────────────────────────────────────────

def store_scene_output(scene: Scene, state: ShowState, output: Any) -> None:
    """Write all declared outputs to in-memory state and SQLite."""
    is_trusted = scene.input_trust == "trusted"
    for output_name in scene.outputs.keys():
        state.outputs.setdefault(scene.scene, {})[output_name] = output
        persist_scene_output(
            state.show_id, scene.scene, output_name, output, is_trusted=is_trusted
        )


# ──────────────────────────────────────────────────────────────────────────────
# Main run loop
# ──────────────────────────────────────────────────────────────────────────────

def run_show(
    show: ShowSettings,
    resume_state: Optional[ShowState] = None,
) -> ShowState:
    if resume_state is not None:
        state = resume_state
        state.status = "running"
        persist_show_state(state)
        add_event(state.show_id, "show_resumed", payload={"show_id": show.id})
    else:
        state = initialize_state(show)
        state.status = "running"
        persist_show_state(state)
        add_event(state.show_id, "show_started", payload={"show_id": show.id})

    improvisation = show.sliders.get("improvisation", "script")
    adaptive_enabled_global = improvisation in {"standard", "jazz"}

    for scene in show.running_order:
        scene_state = state.scenes.setdefault(scene.scene, __import__("the_show.models", fromlist=["SceneState"]).SceneState(scene=scene.scene))

        # Skip scenes already in a terminal state (resume path)
        if scene_state.status in TERMINAL_STATES:
            continue

        # ── Monitor signals ───────────────────────────────────────────────────
        _handle_monitor_signals(state.show_id, show, state)

        # ── Dependency check ─────────────────────────────────────────────────
        unresolved = [
            dep for dep in scene.depends_on
            if state.scenes.get(dep) is None
            or state.scenes[dep].status not in SUCCESS_STATES
        ]
        if unresolved:
            # Cascading failure if any dependency ended in blocked-no-response
            cascading = any(
                state.scenes.get(dep) and state.scenes[dep].status == "blocked-no-response"
                for dep in unresolved
            )
            if cascading:
                scene_state.status = "cascading-dependency-failure"
                skip_msg = f"cascading: dependency '{unresolved[0]}' blocked-no-response"
            else:
                scene_state.status = "skipped"
                dep_statuses = [
                    f"'{dep}' ({state.scenes[dep].status if state.scenes.get(dep) else 'missing'})"
                    for dep in unresolved
                ]
                skip_msg = f"skipped: unresolved dependencies — {', '.join(dep_statuses)}"
            scene_state.skip_reason = skip_msg
            scene_state.warnings.append(skip_msg)
            persist_scene_state(state.show_id, scene_state)
            add_event(
                state.show_id,
                "scene_skipped",
                scene_id=scene.scene,
                payload={"reason": scene_state.status, "unresolved": unresolved},
            )
            continue

        # ── Mark running ─────────────────────────────────────────────────────
        scene_state.status = "running"
        persist_scene_state(state.show_id, scene_state)

        resolved_inputs = resolve_inputs(scene, state) if scene.inputs else {}

        # ── Build strategy list ───────────────────────────────────────────────
        all_strategies = [("principal", scene.principal)] + [
            (f"fallback-{i}", fb) for i, fb in enumerate(scene.fallbacks, start=1)
        ]

        adaptive_enabled = adaptive_enabled_global and scene.adaptive.allowed

        scene_success = False
        last_result: Optional[AdapterResult] = None

        for label, strategy in all_strategies:
            # Per-strategy success_when; fall back to scene-level
            effective_success_when = strategy.success_when or scene.success_when

            success, result = run_strategy(
                scene, strategy, resolved_inputs, show, state, label, effective_success_when
            )
            last_result = result

            if success:
                if label == "principal":
                    scene_state.status = "played-principal"
                elif label.startswith("fallback-"):
                    idx = label.split("-")[1]
                    scene_state.status = f"played-fallback-{idx}"
                else:
                    scene_state.status = "played-adaptive"

                scene_state.selected_strategy = label
                run_field_validators(scene)
                store_scene_output(scene, state, result.output)
                persist_scene_state(state.show_id, scene_state)
                add_event(
                    state.show_id,
                    "scene_played",
                    scene_id=scene.scene,
                    strategy_label=label,
                    payload={"status": scene_state.status},
                )
                scene_success = True
                break

            # Special error types from human-approval — break immediately
            if result.error_type in ("blocked-no-response", "show-stop"):
                break

            # Try adaptive variation of this strategy before moving to next
            if adaptive_enabled:
                adapted = apply_adaptation(scene, strategy)
                if adapted is not None:
                    adaptive_label = f"adaptive({label})"
                    adaptive_success_when = effective_success_when  # inherit parent
                    success, result = run_strategy(
                        scene, adapted, resolved_inputs, show, state,
                        adaptive_label, adaptive_success_when,
                    )
                    last_result = result
                    if success:
                        scene_state.status = "played-adaptive"
                        scene_state.selected_strategy = adaptive_label
                        run_field_validators(scene)
                        store_scene_output(scene, state, result.output)
                        persist_scene_state(state.show_id, scene_state)
                        add_event(
                            state.show_id,
                            "scene_played",
                            scene_id=scene.scene,
                            strategy_label=adaptive_label,
                            payload={"status": "played-adaptive"},
                        )
                        scene_success = True
                        break

        if scene_success:
            continue

        # ── All strategies failed — check for special error types ─────────────

        if last_result and last_result.error_type == "show-stop":
            scene_state.status = "blocked"
            persist_scene_state(state.show_id, scene_state)
            state.status = "aborted"
            persist_show_state(state)
            add_event(state.show_id, "show_stopped", scene_id=scene.scene,
                      payload={"reason": "STOP received from human"})
            break

        if last_result and last_result.error_type == "blocked-no-response":
            scene_state.status = "blocked-no-response"
            persist_scene_state(state.show_id, scene_state)
            add_event(state.show_id, "scene_blocked_no_response", scene_id=scene.scene)
            # DAG pruning: mark all dependent scenes as cascading-dependency-failure
            from the_show.urgent_contact.degradation import prune_dag_on_blocked
            pruned = prune_dag_on_blocked(state, show, scene.scene)
            for pruned_id in pruned:
                add_event(
                    state.show_id,
                    "scene_cascading_failure",
                    scene_id=pruned_id,
                    payload={"blocked_by": scene.scene},
                )
            continue  # keep running non-dependent scenes

        # must-complete: pause the show so it can be resumed and re-tried
        if scene.must_complete:
            scene_state.status = "running"  # left as running — will re-try on resume
            persist_scene_state(state.show_id, scene_state)
            state.status = "paused"
            persist_show_state(state)
            add_event(
                state.show_id,
                "show_paused_must_complete",
                scene_id=scene.scene,
                payload={"reason": "must-complete scene exhausted all strategies"},
            )
            break

        # Normal cut handling
        scene_state.status = handle_cut(scene)

        # continue-with-partial: propagate last output so downstream can bind to it
        if (
            scene_state.status == "played-partial"
            and last_result is not None
            and last_result.output is not None
        ):
            store_scene_output(scene, state, last_result.output)

        persist_scene_state(state.show_id, scene_state)
        add_event(
            state.show_id,
            "scene_cut",
            scene_id=scene.scene,
            payload={"status": scene_state.status, "cut_condition": scene.cut.condition},
        )

        if scene_state.status == "blocked":
            state.status = "paused"
            persist_show_state(state)
            add_event(state.show_id, "show_blocked", scene_id=scene.scene)
            break
        if scene_state.status == "failed":
            state.status = "aborted"
            persist_show_state(state)
            add_event(state.show_id, "show_failed", scene_id=scene.scene)
            break

    if state.status == "running":
        state.status = "completed"

    persist_show_state(state)
    add_event(state.show_id, "show_finished", payload={"status": state.status})

    # Attempt programme delivery.
    # On success: DB status → "delivered". In-memory state stays "completed" so callers
    # get a stable return value (existing API contract). Read DB to check delivery.
    if state.status == "completed":
        try:
            generate_programme(show.id)
            persist_delivered_status(state.show_id)
        except Exception as exc:
            import logging
            logging.warning(
                "[executor] generate_programme failed — status stays 'completed': %s", exc
            )
    else:
        try:
            generate_programme(show.id)
        except Exception:
            pass

    return state
