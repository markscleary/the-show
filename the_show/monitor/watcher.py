from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from the_show import state as _state_mod
from the_show.state import (
    add_monitor_event,
    get_events,
)
from the_show.monitor.patterns import (
    DEFAULT_POLICY_DENIAL_MAX,
    DEFAULT_RETRY_STORM_MAX,
    DEFAULT_RETRY_STORM_WINDOW,
    DEFAULT_STALLED_SECONDS,
    check_ollama_available,
    detect_cost_runaway,
    detect_oscillation,
    detect_policy_denials,
    detect_retry_storm,
    detect_stalled,
)

logger = logging.getLogger(__name__)

DEFAULT_POLL_INTERVAL = float(os.environ.get("THE_SHOW_MONITOR_POLL_INTERVAL", "5.0"))
_OSCILLATION_MIN_RETRIES = 3


def _stop_file(show_id: str) -> Path:
    return _state_mod.STATE_BASE / f"{show_id}.monitor_stop"


def request_stop(show_id: str) -> None:
    """Write the sentinel file that signals the monitor to exit."""
    _stop_file(show_id).touch()


def _should_stop(show_id: str) -> bool:
    return _stop_file(show_id).exists()


def _clear_stop(show_id: str) -> None:
    p = _stop_file(show_id)
    if p.exists():
        p.unlink()


def run_monitor(
    show_id: str,
    poll_interval: float = DEFAULT_POLL_INTERVAL,
    stalled_threshold: int = DEFAULT_STALLED_SECONDS,
    retry_storm_max: int = DEFAULT_RETRY_STORM_MAX,
    retry_storm_window: int = DEFAULT_RETRY_STORM_WINDOW,
    policy_denial_max: int = DEFAULT_POLICY_DENIAL_MAX,
    soft_cap_usd: Optional[float] = None,
    hard_cap_usd: Optional[float] = None,
) -> None:
    """
    Monitor loop — runs as a separate process.

    Polls the SQLite event log for patterns, writes monitor_events for any
    triggers fired. Does NOT call the dispatcher directly — the Stage Manager
    consults monitor_events between scenes.
    """
    _clear_stop(show_id)
    logger.info("Monitor started for show '%s' (poll %.1fs)", show_id, poll_interval)

    # Check Qwen availability once at startup
    qwen_model = check_ollama_available()

    # Track already-fired triggers to avoid duplicates within a run
    fired_stalled = False
    fired_retry_storms: set = set()
    fired_cost_runaway: Optional[str] = None  # cap_type
    fired_policy_denials: set = set()
    fired_oscillations: set = set()

    while not _should_stop(show_id):
        try:
            events = get_events(show_id)

            # ── Stalled ───────────────────────────────────────────────────────
            if not fired_stalled:
                stall = detect_stalled(events, stalled_threshold)
                if stall:
                    add_monitor_event(
                        show_id,
                        trigger_type="stalled",
                        severity="warning",
                        scene_id=stall.get("last_scene_id"),
                        details=stall,
                        threshold_config=f"stalled_threshold={stalled_threshold}s",
                    )
                    logger.warning("STALLED: %s", stall)
                    fired_stalled = True

            # ── Retry storm ───────────────────────────────────────────────────
            storms = detect_retry_storm(events, retry_storm_max, retry_storm_window)
            for storm in storms:
                sid = storm["scene_id"]
                if sid not in fired_retry_storms:
                    add_monitor_event(
                        show_id,
                        trigger_type="retry-storm",
                        severity="warning",
                        scene_id=sid,
                        details=storm,
                        threshold_config=f"max={retry_storm_max} in {retry_storm_window}s",
                    )
                    logger.warning("RETRY STORM scene=%s: %s", sid, storm)
                    fired_retry_storms.add(sid)

            # ── Cost runaway ──────────────────────────────────────────────────
            runaway = detect_cost_runaway(events, soft_cap_usd, hard_cap_usd)
            if runaway and runaway["cap_type"] != fired_cost_runaway:
                severity = "critical" if runaway["cap_type"] == "hard" else "urgent"
                add_monitor_event(
                    show_id,
                    trigger_type="cost-runaway",
                    severity=severity,
                    details=runaway,
                    threshold_config=f"cap_type={runaway['cap_type']} cap={runaway['cap_usd']}",
                )
                logger.warning("COST RUNAWAY: %s", runaway)
                fired_cost_runaway = runaway["cap_type"]

            # ── Policy denials ────────────────────────────────────────────────
            denials = detect_policy_denials(events, policy_denial_max)
            for denial in denials:
                sid = denial["scene_id"]
                if sid not in fired_policy_denials:
                    add_monitor_event(
                        show_id,
                        trigger_type="policy-denials",
                        severity="urgent",
                        scene_id=sid,
                        details=denial,
                        threshold_config=f"max_denials={policy_denial_max}",
                    )
                    logger.warning("POLICY DENIALS scene=%s: %s", sid, denial)
                    fired_policy_denials.add(sid)

            # ── Oscillation (soft signal via Qwen — only if Ollama available) ─
            if qwen_model:
                _check_oscillation(
                    show_id, events, fired_oscillations, qwen_model
                )

        except Exception as exc:
            logger.error("Monitor poll error: %s", exc)

        time.sleep(poll_interval)

    logger.info("Monitor stopping for show '%s'", show_id)
    _clear_stop(show_id)


def _check_oscillation(
    show_id: str,
    events: List[Dict[str, Any]],
    fired: set,
    qwen_model: str,
) -> None:
    """Check for oscillation on scenes with >_OSCILLATION_MIN_RETRIES attempts."""
    from the_show.monitor.patterns import OLLAMA_BASE_URL

    # Count attempts per scene and collect their outputs
    scene_attempts: Dict[str, List[Dict]] = {}
    for ev in events:
        if ev["event_type"] == "attempt" and ev.get("scene_id"):
            scene_attempts.setdefault(ev["scene_id"], []).append(ev)

    for scene_id, attempts in scene_attempts.items():
        if scene_id in fired:
            continue
        if len(attempts) <= _OSCILLATION_MIN_RETRIES:
            continue
        # Extract strategy labels from payloads as proxy for "output"
        outputs = []
        for a in attempts:
            label = a.get("strategy_label") or ""
            payload = a.get("payload") or {}
            outputs.append(f"{label}: {payload.get('status','')} {payload.get('error_type','')}")

        result = detect_oscillation(scene_id, outputs, OLLAMA_BASE_URL, qwen_model)
        if result:
            add_monitor_event(
                show_id,
                trigger_type="oscillation",
                severity="warning",
                scene_id=scene_id,
                details=result,
                threshold_config=f"min_retries={_OSCILLATION_MIN_RETRIES}",
            )
            logger.warning("OSCILLATION scene=%s: %s", scene_id, result)
            fired.add(scene_id)
