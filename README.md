# The Show

A framework for running agents unattended — scenes, fallbacks, adaptive variations, urgent contact escalation, and a programme at the end.

See [docs/The_Show_v0.2_Spec.md](docs/The_Show_v0.2_Spec.md) for the v0.2 spec.
The locked v0.4.1 spec will be placed in `docs/` when uploaded.

---

## Current state

**Runtime:** Session 4 — Real channel adapters: Telegram, email, WhatsApp (skeleton), SMS
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
  - Mock channel for testing (file-drop at `~/.the-show/urgent-mock/`)
- **Real channel adapters (Session 4):**
  - **Telegram** — dedicated urgent-contact bot, polling-based, channel-native auth
  - **Email** — SMTP send + signed action links, HMAC-SHA256 tokens, 24h expiry
  - **WhatsApp** — skeleton with setup checklist; send() raises NotImplementedError until Meta onboarding complete
  - **SMS** — Twilio, reply-token auth
  - **Signed-link server** — Flask app on port 5099; handles email link clicks + WhatsApp / Twilio webhooks
- `load_adapters()` in `dispatcher.py` — registers only configured adapters; warns if credentials missing; mock always available
- Programme reads from SQLite event log
- `tests/` — 146 passing pytest tests

### Known stubs (addressed in later sessions)
- WhatsApp `send()` raises `NotImplementedError` until Mark completes Meta Business API onboarding
- Link server is localhost-only — needs reverse proxy or Cloudflare Tunnel for WhatsApp/Twilio webhooks
- Execution Monitor — not running (Session 5)
- `STOP` keyword — parsed and returned but does not yet abort the whole show (Session 5)
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
  - `channels/base.py` — ChannelAdapter protocol and InboundResponse type
  - `channels/config.py` — env var config helpers for all channels
  - `channels/mock.py` — file-drop mock channel for testing
  - `channels/telegram.py` — polling Telegram Bot API adapter
  - `channels/email.py` — SMTP send + signed-link poll adapter
  - `channels/whatsapp.py` — WhatsApp Business API skeleton
  - `channels/sms.py` — Twilio SMS adapter
  - `link_queue.py` — shared SQLite for email/SMS/WhatsApp webhook responses
  - `link_server.py` — Flask server: `/respond`, `/whatsapp-webhook`, `/twilio-webhook`
- `tests/` — pytest suite (146 tests)

### Channel configuration

Copy `.env.example` to `.env` and fill in credentials:

```bash
cp .env.example .env
# edit .env
```

Channels activate automatically when their env vars are set. Missing vars emit a warning and the channel is skipped; the mock channel is always available.

**Telegram** — fastest to activate: create a bot with BotFather and set `URGENT_TELEGRAM_BOT_TOKEN` plus the authorised user IDs.

**Email** — create a Gmail App Password, set `URGENT_SMTP_*` vars and `URGENT_EMAIL_SIGNING_SECRET`.

**WhatsApp** — requires Meta Business API onboarding (1–7 days). See `channels/whatsapp.py` class docstring for the setup checklist.

**SMS** — Twilio account required. Trial accounts can only send to verified numbers.

### Running the link server

The link server receives email link clicks and Twilio/WhatsApp webhooks.

```bash
# Manual (for development)
.venv/bin/python -m urgent_contact.link_server

# Via launchd (production — after filling in the plist env vars)
launchctl load ~/Library/LaunchAgents/org.shortandsweet.urgent-link-server.plist
```

For WhatsApp and Twilio webhooks (which require HTTPS), use ngrok:
```bash
ngrok http 5099
# Use the resulting https://*.ngrok.io URL in Meta / Twilio dashboards
```

### Coming in Session 5
- Execution Monitor — watches running scenes, triggers Urgent Contact on anomalies

### Coming in Session 6
- First real show end-to-end with live Telegram notifications
