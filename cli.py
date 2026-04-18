from __future__ import annotations

import argparse
import json
from pathlib import Path

from executor import run_show
from loader import load_show, ValidationError


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
    show = load_show(path)
    state = run_show(show)
    print(f"Show finished with status: {state.status}")
    print(f"Total cost: ${state.total_cost_usd:.2f}")
    return 0


def cmd_peek(path: str) -> int:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    print(f"Show: {data['title']} ({data['show_id']})")
    print(f"Status: {data['status']}")
    print(f"Total cost: ${data['total_cost_usd']:.2f}")
    print("Scenes:")
    for scene_id, scene_state in data["scenes"].items():
        print(f"  - {scene_id}: {scene_state['status']}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="The Show runtime skeleton")
    sub = parser.add_subparsers(dest="command", required=True)

    p_validate = sub.add_parser("validate")
    p_validate.add_argument("path")

    p_run = sub.add_parser("run")
    p_run.add_argument("path")

    p_peek = sub.add_parser("peek")
    p_peek.add_argument("path")

    args = parser.parse_args()

    if args.command == "validate":
        return cmd_validate(args.path)
    if args.command == "run":
        return cmd_run(args.path)
    if args.command == "peek":
        return cmd_peek(args.path)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
