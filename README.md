# The Show

A framework for running agents unattended — scenes, fallbacks, adaptive variations, and a programme at the end.

See [docs/The_Show_v0.2_Spec.md](docs/The_Show_v0.2_Spec.md) for the v0.2 spec.
The locked v0.4.1 spec will be placed in `docs/` when uploaded.

---

## Current state

**Runtime:** Session 2 — SQLite state, v0.4.1 scope aligned (Urgent Contact stubbed)
**Spec version target:** v0.4.1 LOCKED

### What works
- SQLite state (`~/.the-show/state/<show-id>.db`, WAL mode)
- Crash recovery — interrupted shows prompt for resume on next run
- Full scene state vocabulary including `cascading-dependency-failure` and `played-fallback-N`
- Per-strategy `success-when` overrides (falls back to scene-level)
- Basic schema validation in `meets_success` (list / dict / string / number)
- Markdown-fence sanitisation on untrusted output (`sanitise.py`)
- Field-validator hook — logs INFO, skips (real validators are a later session)
- Idempotency key generation for side-effectful strategies (logged to event DB)
- `human-approval` stub — auto-APPROVEs with TODO pointing to Session 3
- Programme reads from SQLite event log
- `tests/` — 47 passing pytest smoke tests

### Known stubs (addressed in later sessions)
- `human-approval` — auto-APPROVEs immediately (Session 3)
- Execution Monitor — not running (Session 5)
- Real channel adapters — Telegram / email / MCP not implemented (Session 4)
- Field-level validators — hook exists, no real validators (later)
- Basic schema validation only — no JSON Schema deep-validation (later)

---

## How to run

```bash
# Set up environment (once)
uv venv --python 3.11 .venv
uv pip install -r requirements.txt

# Validate a show file
uv run python cli.py validate example_show.yaml

# Run a show (with crash-resume)
uv run python cli.py run example_show.yaml

# Inspect current state
uv run python cli.py peek outreach-enrichment-001

# Regenerate programme from saved state
uv run python cli.py programme outreach-enrichment-001

# Print event log
uv run python cli.py events outreach-enrichment-001 [--since=<ISO>] [--limit=N]

# Run tests
uv run pytest tests/
```

State DB: `~/.the-show/state/<show-id>.db`
Programme output: `~/.the-show/state/<show-id>/programme.md` and `programme.json`

## Files

- `models.py` — core dataclasses (Strategy now has `success_when`)
- `loader.py` — YAML loading and validation
- `executor.py` — scene execution loop (resume, all v0.4.1 states, stubs)
- `state.py` — SQLite state layer (WAL, resume, event log)
- `sanitise.py` — markdown fence stripper for untrusted output
- `programme.py` — reads from SQLite, generates markdown + JSON
- `adapters.py` — stub adapters + idempotency key utilities
- `cli.py` — CLI: validate / run / peek / programme / events
- `example_show.yaml` — 5-scene example (covers all Session 2 features)
- `tests/` — pytest suite (47 tests)
