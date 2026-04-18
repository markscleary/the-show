# The Show

A framework for running agents unattended — scenes, fallbacks, adaptive variations, urgent contact escalation, and a programme at the end.

See [docs/The_Show_v0.2_Spec.md](docs/The_Show_v0.2_Spec.md) for the v0.2 spec.
The locked v0.4.1 spec will be placed in `docs/` when uploaded.

---

## Current state

**Runtime:** Session 3 — Urgent Contact with auth, strict parsing, cancellation, DAG pruning, throttle
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
- **Urgent Contact** — real dispatcher replacing the Session 2 stub:
  - Three auth methods: channel-native, reply-token (6-digit), signed-link (HMAC-SHA256)
  - Strict response parsing: APPROVE / REJECT / STOP / CONTINUE only; invalid format sends a correction prompt and keeps polling
  - Sequential and parallel dispatch modes; `critical` severity forces parallel
  - Cancellation of pending sends on first valid response
  - Exhaustion path (`blocked-no-response`) when all contacts fail to reply
  - DAG pruning: exhausted/blocked scene cascades `cascading-dependency-failure` to all transitive dependents
  - Frequency throttle: default 3 unplanned matters per show; `human-approval` scenes always exempt; `critical` always bypasses
  - Mock channel for testing (file-drop at `~/.the-show/mock_responses/<matter-id>.json`)
- Programme reads from SQLite event log
- `tests/` — 84 passing pytest tests

### Known stubs (addressed in later sessions)
- Real channel adapters — Telegram / WhatsApp / email / SMS not yet wired (Session 4)
- Execution Monitor — not running (Session 5)
- `STOP` keyword — parsed and returned but does not yet abort the whole show (Session 4/5)
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

### Testing Urgent Contact end-to-end

Run a show that contains a `human-approval` scene. When the dispatcher raises a matter via the mock channel, drop a JSON response file to resolve it:

```bash
# 1. Start the show — it will block on the human-approval scene
uv run python cli.py run example_show.yaml

# 2. In another terminal, find the matter ID from the event log
uv run python cli.py events outreach-enrichment-001 --limit=5

# 3. Drop a response for that matter ID (replace <matter-id> with the real value)
mkdir -p ~/.the-show/mock_responses
echo '{"keyword": "APPROVE", "auth_token": null}' \
  > ~/.the-show/mock_responses/<matter-id>.json

# 4. The dispatcher will pick it up within the next poll interval (default 5 s)
#    and unblock the show.
```

The `THE_SHOW_POLL_INTERVAL` environment variable controls the poll delay (seconds, default `5`). Set it to `0` or `0.01` in tests for instant resolution.

---

## Files

- `models.py` — core dataclasses (Strategy now has `success_when`)
- `loader.py` — YAML loading and validation
- `executor.py` — scene execution loop (resume, all v0.4.1 states, real urgent contact)
- `state.py` — SQLite state layer (WAL, resume, event log, urgent matter / send tables)
- `sanitise.py` — markdown fence stripper for untrusted output
- `programme.py` — reads from SQLite, generates markdown + JSON
- `adapters.py` — stub adapters + idempotency key utilities
- `cli.py` — CLI: validate / run / peek / programme / events
- `example_show.yaml` — 5-scene example (covers all Session 2 + 3 features)
- `urgent_contact/` — Urgent Contact subsystem
  - `dispatcher.py` — raise matters, fire sends, poll, cancel, return resolution
  - `auth.py` — channel-native / reply-token / signed-link auth
  - `parser.py` — strict APPROVE / REJECT / STOP / CONTINUE keyword parser
  - `throttle.py` — per-show matter frequency limit
  - `degradation.py` — DAG pruning for cascading-dependency-failure
  - `channels/base.py` — ChannelAdapter ABC and InboundResponse type
  - `channels/mock.py` — file-drop mock channel for testing
- `tests/` — pytest suite (84 tests)

### Coming in Session 4
- Real channel adapters: Telegram bot, WhatsApp Business API, email (SMTP/IMAP), SMS (Twilio)
- `STOP` keyword wired to show-abort path
- Signed-link base URL configured and served

### Coming in Session 5
- Execution Monitor — watches running scenes, triggers Urgent Contact on anomalies
