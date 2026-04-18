# The Show

A framework for running agents unattended — scenes, fallbacks, adaptive variations, and a programme at the end.

See [docs/The_Show_v0.2_Spec.md](docs/The_Show_v0.2_Spec.md) for the v0.2 spec.
The locked v0.4.1 spec will be placed in `docs/` when uploaded.

---

## Current state

**Runtime:** v0.2 skeleton + Session 1 bug fixes
**Spec version target:** v0.4.1 LOCKED

### What works
- YAML show loading with kebab-to-snake field conversion (Bug 1 fixed)
- Scene execution with correct spec order: Principal → Adaptive(Principal) → Fallback 1 → Adaptive(Fallback 1) → … → Cut (Bug 2 fixed)
- `continue-with-partial` cut condition propagates partial output to downstream scenes
- Stub adapters for `tool-call` and `sub-agent` methods
- Programme generation (markdown + JSON) in `.show_output/`

### What doesn't yet
- **Session 2:** SQLite state persistence
- **Session 3:** Urgent Contact (blocked-show escalation)
- **Session 4:** Real channel adapters (Telegram, email, MCP)
- **Session 5:** Execution Monitor

---

## How to run

```bash
# Set up environment (once)
uv venv --python 3.11 .venv
uv pip install -r requirements.txt

# Validate a show file
uv run python cli.py validate example_show.yaml

# Run a show
uv run python cli.py run example_show.yaml

# Inspect state file
uv run python cli.py peek .show_state/outreach-enrichment-001_state.json
```

Programme output lands in `.show_output/`.
State files land in `.show_state/`.

## Files

- `models.py` — core dataclasses
- `loader.py` — YAML loading and validation
- `executor.py` — scene execution loop
- `state.py` — state persistence (JSON for now; SQLite in Session 2)
- `programme.py` — markdown and JSON reporting
- `adapters.py` — stub agent/tool execution adapters
- `cli.py` — CLI entry point
- `example_show.yaml` — sample show definition
