from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Optional

from the_show.state import get_monitor_events, show_exists
from the_show.monitor.watcher import request_stop


def cmd_monitor_start(show_id: str) -> int:
    """Run the monitor in the foreground (blocks until stopped)."""
    import logging
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [monitor] %(message)s")

    if not show_exists(show_id):
        print(f"No state found for show '{show_id}'")
        return 1

    from the_show.monitor.watcher import run_monitor, DEFAULT_POLL_INTERVAL
    run_monitor(show_id, poll_interval=DEFAULT_POLL_INTERVAL)
    return 0


def cmd_monitor_stop(show_id: str) -> int:
    """Send the stop signal to a running monitor."""
    request_stop(show_id)
    print(f"Stop signal sent to monitor for show '{show_id}'.")
    return 0


def cmd_monitor_events(show_id: str, limit: Optional[int] = 20) -> int:
    """Print recent monitor events for a show."""
    if not show_exists(show_id):
        print(f"No state found for show '{show_id}'")
        return 1
    events = get_monitor_events(show_id, limit=limit)
    if not events:
        print("No monitor events.")
        return 0
    print(f"Monitor events for show '{show_id}' ({len(events)} shown):\n")
    for ev in events:
        ack = "✓" if ev["acknowledged"] else "○"
        scene_tag = f" [{ev['scene_id']}]" if ev["scene_id"] else ""
        print(
            f"  {ack} #{ev['id']} [{ev['severity'].upper()}] {ev['trigger_type']}{scene_tag}"
            f"  {ev['created_at']}"
        )
        if ev.get("details"):
            import json
            print(f"     {json.dumps(ev['details'])}")
    return 0


def launch_monitor_subprocess(show_id: str) -> subprocess.Popen:
    """Launch monitor as a background subprocess. Returns the Popen handle."""
    cli_path = Path(__file__).parent.parent / "cli.py"
    proc = subprocess.Popen(
        [sys.executable, str(cli_path), "monitor-start", show_id],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return proc
