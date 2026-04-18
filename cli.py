from __future__ import annotations

import argparse
import sys
from pathlib import Path

from executor import run_show
from loader import load_show, ValidationError
from programme import generate_programme
from state import (
    archive_db,
    count_completed_scenes,
    get_db_path,
    get_events,
    get_show_status,
    load_show_state,
    show_exists,
)


# ──────────────────────────────────────────────────────────────────────────────
# Commands
# ──────────────────────────────────────────────────────────────────────────────

def cmd_validate(path: str) -> int:
    try:
        show = load_show(path)
        print(f"VALID: {show.id} - {show.title}")
        print(f"Scenes: {len(show.running_order)}")
        return 0
    except ValidationError as exc:
        print(f"INVALID: {exc}")
        return 1


def cmd_run(path: str) -> int:
    try:
        show = load_show(path)
    except ValidationError as exc:
        print(f"INVALID: {exc}")
        return 1

    resume_state = None

    if show_exists(show.id):
        status = get_show_status(show.id)
        if status in {"running", "paused"}:
            completed, total = count_completed_scenes(show.id)
            print(f"A previous run of this show was interrupted. Status: {status}")
            print(f"Completed scenes: {completed:03d} of {total:03d}")
            try:
                answer = input("Resume? [y/N] ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                answer = "n"
            if answer == "y":
                resume_state = load_show_state(show.id)
                print(f"Resuming from scene {completed + 1}…")
            else:
                abandoned = archive_db(show.id)
                print(f"Previous run archived to: {abandoned.name}")
        else:
            # completed or aborted — archive and start fresh
            abandoned = archive_db(show.id)
            print(f"Previous run ({status}) archived to: {abandoned.name}")

    state = run_show(show, resume_state=resume_state)
    print(f"\nShow finished: {state.status}")
    print(f"Total cost: ${state.total_cost_usd:.4f}")
    db_path = get_db_path(show.id)
    print(f"State DB: {db_path}")
    return 0


def cmd_peek(show_id: str) -> int:
    if not show_exists(show_id):
        print(f"No state found for show '{show_id}'")
        return 1
    try:
        state = load_show_state(show_id)
    except ValueError as exc:
        print(f"Error: {exc}")
        return 1

    print(f"Show: {state.title} ({state.show_id})")
    print(f"Status: {state.status}")
    print(f"Total cost: ${state.total_cost_usd:.4f}")
    print(f"Scenes ({len(state.scenes)}):")
    for scene_id, sc in state.scenes.items():
        strat = f" — {sc.selected_strategy}" if sc.selected_strategy else ""
        print(f"  {scene_id}: {sc.status}{strat}")

    events = get_events(show_id)
    if events:
        print("\nLast 5 events:")
        for ev in events[-5:]:
            scene_tag = f" [{ev['scene_id']}]" if ev["scene_id"] else ""
            print(f"  {ev['created_at']}  {ev['event_type']}{scene_tag}")

    print("\nUrgent matters: none (Session 3)")
    return 0


def cmd_programme(show_id: str) -> int:
    if not show_exists(show_id):
        print(f"No state found for show '{show_id}'")
        return 1
    try:
        md_path, json_path = generate_programme(show_id)
        print(f"Programme written:")
        print(f"  Markdown: {md_path}")
        print(f"  JSON:     {json_path}")
        return 0
    except Exception as exc:
        print(f"Error generating programme: {exc}")
        return 1


def cmd_events(show_id: str, since: str | None = None, limit: int | None = None) -> int:
    if not show_exists(show_id):
        print(f"No state found for show '{show_id}'")
        return 1
    events = get_events(show_id, since=since, limit=limit)
    if not events:
        print("No events found.")
        return 0
    for ev in events:
        scene_tag = f" [{ev['scene_id']}]" if ev["scene_id"] else ""
        strat_tag = f" ({ev['strategy_label']})" if ev["strategy_label"] else ""
        cost_tag = f" ${ev['cost_usd']:.4f}" if ev["cost_usd"] else ""
        print(f"{ev['created_at']}  {ev['event_type']}{scene_tag}{strat_tag}{cost_tag}")
    return 0


# ──────────────────────────────────────────────────────────────────────────────
# Entry point
# ──────────────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(description="The Show — unattended agent orchestration")
    sub = parser.add_subparsers(dest="command", required=True)

    p_validate = sub.add_parser("validate", help="Validate a show YAML file")
    p_validate.add_argument("path")

    p_run = sub.add_parser("run", help="Run a show (with crash-resume support)")
    p_run.add_argument("path")

    p_peek = sub.add_parser("peek", help="Inspect current state of a show")
    p_peek.add_argument("show_id")

    p_prog = sub.add_parser("programme", help="Regenerate programme from saved state")
    p_prog.add_argument("show_id")

    p_ev = sub.add_parser("events", help="Print the event log for a show")
    p_ev.add_argument("show_id")
    p_ev.add_argument("--since", default=None, help="ISO timestamp — show events after this time")
    p_ev.add_argument("--limit", type=int, default=None, help="Maximum events to show")

    args = parser.parse_args()

    if args.command == "validate":
        return cmd_validate(args.path)
    if args.command == "run":
        return cmd_run(args.path)
    if args.command == "peek":
        return cmd_peek(args.show_id)
    if args.command == "programme":
        return cmd_programme(args.show_id)
    if args.command == "events":
        return cmd_events(args.show_id, since=args.since, limit=args.limit)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
