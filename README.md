# The Show

A framework for running agents unattended — scenes, fallbacks, adaptive variations, urgent contact escalation, and a programme at the end.

**Status:** v1.1.0 — production-ready, on PyPI, used in real operations at [Short+Sweet International](https://shortandsweet.org). Open source, runtime free.

[![CI](https://github.com/markscleary/the-show/actions/workflows/ci.yml/badge.svg)](https://github.com/markscleary/the-show/actions/workflows/ci.yml) [![PyPI](https://img.shields.io/pypi/v/the-show.svg)](https://pypi.org/project/the-show/) [![Runner](https://img.shields.io/badge/runner-live-brightgreen)](https://raw.githubusercontent.com/markscleary/the-show/status/status/runner-status.json) [![Discussions](https://img.shields.io/github/discussions/markscleary/the-show)](https://github.com/markscleary/the-show/discussions) [![Open issues](https://img.shields.io/github/issues/markscleary/the-show)](https://github.com/markscleary/the-show/issues)

Have a question? [Discussions](https://github.com/markscleary/the-show/discussions). Found a bug? [Issues](https://github.com/markscleary/the-show/issues).

---

## What it is

The Show is an orchestration runtime for creative work. It uses a theatrical metaphor — programmes, scenes, Stage Manager, Urgent Contact — because the metaphor maps onto how creative operators already think. You write a programme. The Stage Manager runs it, persisting state after every scene. When something needs a human decision, the Urgent Contact system sends a signed, authenticated request across Telegram, email, SMS or WhatsApp. You respond. The show continues.

The specific differentiator: async cancellation mid-LLM-call across four signed-link channels with typed response schemas and per-channel authentication. When the first valid response comes in, outstanding sends are cancelled. That combination doesn't exist elsewhere as a coherent system.

The v1.0 release was built by running The Show on itself — `examples/build-v1.0-release.yaml` is the programme that built v1.0. It's in the repo.

---

Here's what a programme looks like — three scenes from the Curiosity Cat launch announcement that ran on 23 April 2026:

```yaml
running-order:

  - scene: draft_english
    title: "Draft English announcement"
    outputs:
      post: {type: object}
    principal:
      method: sub-agent
      agent: gemini
      brief: "Draft a 280-char social post for the Curiosity Cat launch."
      params: {model: gemini-flash}
    cut: {condition: escalate, reason: "Cannot proceed without English draft"}

  - scene: draft_arabic
    title: "Draft Arabic announcement"
    depends-on: [draft_english]
    inputs:
      english_post: from(draft_english.post)
    outputs:
      post: {type: object}
    principal:
      method: sub-agent
      agent: gemini
      brief: "Translate the English post to natural Arabic for the UAE market."
      params: {model: gemini-flash}
    cut: {condition: escalate}

  - scene: approve_drafts
    title: "Operator approval"
    depends-on: [draft_english, draft_arabic]
    outputs:
      decision: {type: string}
    principal:
      method: human-approval
      brief: "Reply APPROVE to publish, REJECT to abort."
    cut: {condition: escalate}
```

The full programme is at [`examples/curiosity-cat-launch-announcement.yaml`](examples/curiosity-cat-launch-announcement.yaml). The operator guide explains the metaphor and the mechanics in detail — see [`docs/OPERATOR_GUIDE.md`](docs/OPERATOR_GUIDE.md).

---

## Current state

**Version:** v1.1.0 — 231 passing tests

### What works
- SQLite state (`~/.the-show/state/<show-id>.db`, WAL mode)
- Crash recovery — interrupted shows prompt for resume on next run
- Full scene state vocabulary including `cascading-dependency-failure` and `played-fallback-N`
- Per-strategy `success-when` overrides (falls back to scene-level)
- Basic schema validation in `meets_success` (list / dict / string / number)
- Markdown-fence sanitisation on untrusted output (`sanitise.py`)
- Field-validator hook — logs INFO, skips (real validators planned)
- Idempotency key generation for side-effectful strategies (logged to event DB)
- **Urgent Contact** — real dispatcher:
  - Three auth methods: channel-native, reply-token (6-digit), signed-link (HMAC-SHA256)
  - Strict response parsing: APPROVE / REJECT / STOP / CONTINUE only; invalid format sends a correction prompt and keeps polling
  - Sequential and parallel dispatch modes; `critical` severity forces parallel
  - Cancellation of pending sends on first valid response
  - Exhaustion path (`blocked-no-response`) when all contacts fail to reply
  - DAG pruning: exhausted/blocked scene cascades `cascading-dependency-failure` to all transitive dependents
  - Frequency throttle: default 3 unplanned matters per show; `human-approval` scenes always exempt; `critical` always bypasses
  - Mock channel for testing (file-drop at `~/.the-show/urgent-mock/`)
- **Real channel adapters:**
  - **Telegram** — dedicated urgent-contact bot, polling-based, channel-native auth
  - **Email** — SMTP send + signed action links, HMAC-SHA256 tokens, 24h expiry
  - **WhatsApp** — skeleton with setup checklist; send() raises NotImplementedError until Meta onboarding complete
  - **SMS** — Twilio, reply-token auth
  - **Signed-link server** — Flask app on port 5099; handles email link clicks + WhatsApp / Twilio webhooks
- `load_adapters()` in `dispatcher.py` — registers only configured adapters; warns if credentials missing; mock always available
- Programme reads from SQLite event log
- `tests/` — 231 passing pytest tests

### Current limitations
- WhatsApp `send()` raises `NotImplementedError` until Meta Business API onboarding completes
- Link server is localhost-only — needs reverse proxy or Cloudflare Tunnel for WhatsApp and Twilio webhooks
- Execution Monitor — not yet enabled
- `STOP` keyword — parsed and returned but does not yet abort the whole show
- Field-level validators — hook exists, no real validators
- Basic schema validation only — no JSON Schema deep validation

---

## Install

```bash
# From PyPI
pip install the-show

# Or from source
git clone https://github.com/markscleary/the-show.git
cd the-show
pip install -e ".[dev]"
```

See [`docs/QUICKSTART.md`](docs/QUICKSTART.md) for a five-minute walkthrough.

---

## How to run

```bash
# Validate a show file
the-show validate example_show.yaml

# Run a show (with crash-resume)
the-show run example_show.yaml

# Inspect current state
the-show peek outreach-enrichment-001

# Regenerate programme from saved state
the-show programme outreach-enrichment-001

# Print event log
the-show events outreach-enrichment-001 [--since=<ISO>] [--limit=N]

# Run tests (from a source checkout)
pytest tests/
```

State DB: `~/.the-show/state/<show-id>.db`
Programme output: `~/.the-show/state/<show-id>/programme.md` and `programme.json`

### Testing Urgent Contact end-to-end

Run a show that contains a `human-approval` scene. When the dispatcher raises a matter via the mock channel, drop a JSON response file to resolve it:

```bash
# 1. Start the show — it will block on the human-approval scene
the-show run example_show.yaml

# 2. In another terminal, find the matter ID from the event log
the-show events outreach-enrichment-001 --limit=5

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
- `example_show.yaml` — 5-scene example covering core scene mechanics
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
- `tests/` — pytest suite (231 tests)

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

---

## Documentation

- **[Quickstart](docs/QUICKSTART.md)** — get a programme running in 5 minutes.
- **[Operator Guide](docs/OPERATOR_GUIDE.md)** — the theatrical metaphor, how scenes work, approval gates, urgent contact mechanics. The starting point for anyone running The Show.
- **[Spec v0.4.2](docs/SS_The_Show_Spec_v0.4.2_PATCH_19Apr26.md)** — formal specification and patch notes.

---

### Coming next

- Execution Monitor — watches running scenes, triggers Urgent Contact on anomalies.
- WhatsApp send() implementation once Meta Business API onboarding lands.
- Stronger STOP semantics — parsed STOP aborts the whole show, not just the scene.
