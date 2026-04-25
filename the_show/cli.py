from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from the_show import __version__
from the_show.executor import run_show
from the_show.loader import load_show, ValidationError
from the_show.monitor.cli import cmd_monitor_start, cmd_monitor_stop, cmd_monitor_events, launch_monitor_subprocess
from the_show.programme import generate_programme
from the_show.state import (
    archive_db,
    count_completed_scenes,
    get_db_path,
    get_events,
    get_send_by_token,
    get_show_status,
    get_urgent_matters,
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


def cmd_run(path: str, rehearsal: bool = False) -> int:
    try:
        show = load_show(path)
    except ValidationError as exc:
        print(f"INVALID: {exc}")
        return 1

    if rehearsal:
        show.rehearsal = True
        print("[REHEARSAL MODE] No real LLM calls, no real channel sends, approvals synthetic.")

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

    monitor_proc = launch_monitor_subprocess(show.id)
    try:
        state = run_show(show, resume_state=resume_state)
    finally:
        from the_show.monitor.watcher import request_stop
        request_stop(show.id)
        try:
            monitor_proc.wait(timeout=5)
        except Exception:
            monitor_proc.kill()
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

    matters = get_urgent_matters(show_id)
    if matters:
        print(f"\nUrgent matters ({len(matters)}):")
        for m in matters:
            res = f" → {m['resolution']}" if m.get("resolution") else ""
            print(f"  #{m['id']} [{m['severity']}] {m['status']}{res}  scene={m['scene_id']}")
    else:
        print("\nUrgent matters: none")
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


def cmd_respond(handle: str, text: str) -> int:
    """Write a response to the mock urgent channel responses file."""
    from the_show.urgent_contact.channels.mock import MOCK_DIR, RESPONSES_FILE
    MOCK_DIR.mkdir(parents=True, exist_ok=True)
    entry = {
        "handle": handle,
        "text": text,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    with RESPONSES_FILE.open("a") as f:
        f.write(json.dumps(entry) + "\n")
    print(f"Response written for handle '{handle}': {text!r}")
    return 0


def cmd_click_link(token: str, action: str = "APPROVE") -> int:
    """Simulate a signed-link click by looking up the send and writing a response."""
    from the_show.urgent_contact.channels.mock import MOCK_DIR, RESPONSES_FILE
    from the_show.urgent_contact.auth import verify_signed_token

    # Find the send record by token to get the handle and show_id
    # We need to search all show DBs — look through state files
    state_dir = Path.home() / ".the-show" / "state"
    if not state_dir.exists():
        print("No state directory found.")
        return 1

    send = None
    show_id = None
    db_path = None
    for db_file in state_dir.glob("*.db"):
        candidate_show_id = db_file.stem
        s = get_send_by_token(str(db_file), token)
        if s is not None:
            send = s
            show_id = candidate_show_id
            db_path = str(db_file)
            break

    if send is None:
        print(f"No pending send found with token '{token}'.")
        return 1

    # Verify the token is valid HMAC
    if not verify_signed_token(token, show_id):
        print(f"Token '{token}' failed HMAC verification.")
        return 1

    handle = send["channel_handle"]
    MOCK_DIR.mkdir(parents=True, exist_ok=True)
    entry = {
        "handle": handle,
        "text": f"{action} {token}",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "signed_link_token": token,
    }
    with RESPONSES_FILE.open("a") as f:
        f.write(json.dumps(entry) + "\n")
    print(f"Signed-link click recorded: {action} for '{handle}' (token: {token[:12]}...)")
    return 0


def cmd_urgent(show_id: str) -> int:
    """Show all urgent matters for a show."""
    if not show_exists(show_id):
        print(f"No state found for show '{show_id}'")
        return 1
    matters = get_urgent_matters(show_id)
    if not matters:
        print(f"No urgent matters for show '{show_id}'.")
        return 0
    print(f"Urgent matters for show '{show_id}' ({len(matters)} total):\n")
    for m in matters:
        print(f"  Matter #{m['id']} — {m['severity'].upper()} [{m['status']}]")
        print(f"    Scene:      {m['scene_id']}")
        print(f"    Trigger:    {m['trigger_type']}")
        print(f"    Prompt:     {m['prompt'][:80]}")
        print(f"    Created:    {m['created_at']}")
        if m.get("resolution"):
            print(f"    Resolution: {m['resolution']} (by {m.get('resolved_by_contact','?')} via {m.get('resolved_by_channel','?')})")
            print(f"    Resolved:   {m['resolved_at']}")
        print()
    return 0


# ──────────────────────────────────────────────────────────────────────────────
# Entry point
# ──────────────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(description="The Show — unattended agent orchestration")
    parser.add_argument("--version", action="version", version=f"the-show {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p_validate = sub.add_parser("validate", help="Validate a show YAML file")
    p_validate.add_argument("path")

    p_run = sub.add_parser("run", help="Run a show (with crash-resume support)")
    p_run.add_argument("path")
    p_run.add_argument("--rehearsal", action="store_true",
                       help="Dry-run: no real LLM calls, no real channel sends, approvals synthetic")

    p_peek = sub.add_parser("peek", help="Inspect current state of a show")
    p_peek.add_argument("show_id")

    p_prog = sub.add_parser("programme", help="Regenerate programme from saved state")
    p_prog.add_argument("show_id")

    p_ev = sub.add_parser("events", help="Print the event log for a show")
    p_ev.add_argument("show_id")
    p_ev.add_argument("--since", default=None, help="ISO timestamp — show events after this time")
    p_ev.add_argument("--limit", type=int, default=None, help="Maximum events to show")

    p_respond = sub.add_parser("respond", help="Write a response to the mock urgent channel")
    p_respond.add_argument("handle", help="Contact handle (e.g. @producer)")
    p_respond.add_argument("text", help="Response text (e.g. 'APPROVE 123456')")

    p_click = sub.add_parser("click-link", help="Simulate clicking a signed approval link")
    p_click.add_argument("token", help="The signed link token from the approval message")
    p_click.add_argument("--action", default="APPROVE",
                         choices=["APPROVE", "REJECT", "CONTINUE", "STOP"],
                         help="Action to submit (default: APPROVE)")

    p_urgent = sub.add_parser("urgent", help="Show all urgent matters for a show")
    p_urgent.add_argument("show_id")

    p_mon_start = sub.add_parser("monitor-start", help="Run the monitor in the foreground")
    p_mon_start.add_argument("show_id")

    p_mon_stop = sub.add_parser("monitor-stop", help="Stop a running monitor")
    p_mon_stop.add_argument("show_id")

    p_mon_ev = sub.add_parser("monitor-events", help="Show recent monitor events")
    p_mon_ev.add_argument("show_id")
    p_mon_ev.add_argument("--limit", type=int, default=20)

    args = parser.parse_args()

    if args.command == "validate":
        return cmd_validate(args.path)
    if args.command == "run":
        return cmd_run(args.path, rehearsal=getattr(args, "rehearsal", False))
    if args.command == "peek":
        return cmd_peek(args.show_id)
    if args.command == "programme":
        return cmd_programme(args.show_id)
    if args.command == "events":
        return cmd_events(args.show_id, since=args.since, limit=args.limit)
    if args.command == "respond":
        return cmd_respond(args.handle, args.text)
    if args.command == "click-link":
        return cmd_click_link(args.token, action=args.action)
    if args.command == "urgent":
        return cmd_urgent(args.show_id)
    if args.command == "monitor-start":
        return cmd_monitor_start(args.show_id)
    if args.command == "monitor-stop":
        return cmd_monitor_stop(args.show_id)
    if args.command == "monitor-events":
        return cmd_monitor_events(args.show_id, limit=args.limit)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
