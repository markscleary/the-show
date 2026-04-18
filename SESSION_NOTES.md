# Session Notes

## Session 1 — Foundation

**Date:** 18 April 2026

### What was done
- Project set up from v0.2 skeleton bundle
- Bug 1 fixed: Bible loader now converts kebab-case YAML keys to snake_case before passing to Bible dataclass
- Bug 2 fixed: Execution order now matches spec (Principal → Adaptive(Principal) → Fallback 1 → Adaptive(Fallback 1) → … → Cut)
- `continue-with-partial` cut now propagates last result output to `state.outputs` for downstream scenes
- `apply_adaptation` now takes any strategy (not just principal) and uses `copy.copy` to avoid mutating the original
- Python 3.11 environment set up via uv
- Example show runs end-to-end and produces a programme

### Notes for later sessions

**v0.4.1 spec not yet uploaded at session start.** Built from v0.2 skeleton. Session 2 should reconcile against the locked v0.4.1 spec before adding SQLite. Mark needs to place `SS_The_Show_Spec_v0.4.1_LOCKED_18Apr26.md` in `docs/` before Session 2 begins.

**Adaptation logic is minimal.** `apply_adaptation` only handles `batch-size` halving. The v0.4.1 spec likely defines richer adaptation bounds. Do not expand this until Session 2 after reading the full spec.

**State dir naming.** The state dir is `.show_state` (underscore) in the code but `.show-state` (hyphen) was in the gitignore spec. Both are gitignored — confirmed `.show_state/` is in .gitignore. Fine for now.

**Stub adapters always succeed.** The `tool-call/read-csv` and `sub-agent` stubs return success. To test fallback/cut paths, a test show with a deliberately failing principal will be needed. Leave for later sessions.

**No input-trust enforcement.** The `input_trust` field is loaded and validated but never acted on during execution. The spec mentions sandboxing implications. Flag for Session 2 review.

---

## Session 2 — SQLite state + v0.4.1 scope alignment

**Date:** 18 April 2026

### What was done
- Replaced JSON file state with SQLite (WAL mode, `~/.the-show/state/<show-id>.db`)
- Crash recovery: interrupted runs prompt for resume; completed/aborted runs auto-archive
- Full scene state vocabulary: `played-fallback-1`, `played-fallback-2`, `cascading-dependency-failure`, `blocked-no-response`
- Per-strategy `success_when` on `Strategy` dataclass; executor uses strategy-level with scene-level fallback
- Basic schema check in `meets_success`: list / dict / string / number
- `sanitise.py` — `strip_markdown_fences` applied to all untrusted string output before success eval
- Field-validator hook: parses `field-validators` from output spec, logs INFO, skips (no real validators)
- Idempotency keys: `is_side_effectful` / `attach_idempotency_key` in `adapters.py`; key attached before retry loop; logged to event DB
- `human-approval` stub in `executor.py` — auto-APPROVEs with TODO for Session 3
- `programme.py` reads entirely from SQLite; outputs `~/.the-show/state/<show-id>/programme.md`
- CLI: `peek <show-id>` (SQLite), `programme <show-id>`, `events <show-id> [--since --limit]`
- Example show expanded to 5 scenes covering all Session 2 features
- pytest suite: 47 passing tests across loader / state / executor / sanitise / resume

### v0.4.1 spec not uploaded — proceeded from brief
The brief was detailed enough to work without the spec file. Session 3 should place the spec in `docs/` before starting.

### Decisions and deviations
- `ShowState.events` kept as an empty list (not removed) to avoid breaking `to_dict()`. It is no longer populated — programme.py reads events directly from SQLite. If `to_dict()` is needed downstream, events will be empty. Low risk for now.
- `persist_state(state)` kept as a convenience wrapper alongside the more granular functions. Executor calls both depending on context.
- `_connect()` opens a new connection per call and closes after commit. Fine for the current non-concurrent, single-show runtime. If parallelism is added later, move to a connection pool.
- `archive_db` uses timestamp in filename — this means multiple archives of the same show-id accumulate without cleanup. Add a pruning step later if needed.
- `load_show_state` now guards against missing DB by checking file existence before connecting (SQLite creates a new empty file on connect otherwise).

### Open questions for Session 3 (Urgent Contact)
- What channel does the Urgent Contact use? Telegram? Email? Config in the show YAML or global config?
- Timeout: how long does the runtime wait for approval before escalating further?
- What happens if the Urgent Contact itself is unreachable? (e.g., Telegram bot down)
- Does `human-approval` produce just a binary APPROVE/DENY, or can it carry a message to the next scene?
- Should the approval decision be persisted in `scene_outputs` (it currently is as "APPROVE" string)?

### Spec ambiguities resolved by interpretation
- **`played-fallback-N` naming**: The brief said `played-fallback-1`, `played-fallback-2` — implemented as `played-fallback-{index}` where index matches the fallback position in the list (1-based).
- **Adaptive variations of fallbacks**: The spec section 9 order in the brief says Principal → Adaptive(Principal) → Fallback 1 → Adaptive(Fallback 1) → …. Implemented as `adaptive(fallback-1)` labels. All adaptive successes use `played-adaptive` status — no per-index adaptive state.
- **`blocked-no-response`**: The brief mentions this as a state for human-approval scenes that get no response. Since the stub always approves, no show currently reaches this state. It's in `TERMINAL_STATES` and `SUCCESS_STATES` is not modified — downstream scenes of a `blocked-no-response` scene will `cascading-dependency-failure`.
- **Field validators on any output vs untrusted only**: Implemented to run on any output that declares `field-validators`, regardless of `input_trust`. The log message fires in `run_field_validators` after any successful scene play.
- **Sub-agent stub input resolution**: Updated to find the first list input regardless of key name (was hardcoded to `contacts` key). This was a latent bug in the Session 1 skeleton.

---

## Session 2 — SQLite State and v0.4.1 Scope

**Completed:**
- SQLite state layer with WAL mode implemented in state.py
- Resume capability via rebuild_showstate_from_db
- 47 tests passing across executor, loader, resume, sanitise, state
- Markdown-fence sanitisation helper (sanitise.py)
- Human-approval stub clearly marked for Session 3 replacement
- Programme generation from SQLite
- Scene state vocabulary expanded to match v0.4.1 section 20
- Idempotency key auto-generation for side-effectful scenes

**Known deferred to Session 3:**
- Real Urgent Contact (stub auto-APPROVES with logged event)
- Real channel adapters (Session 4)
- Execution Monitor (Session 5)

**Notes:**
- Session 2 was executed without the v0.4.1 locked spec in docs/ — work proceeded from v0.2 spec plus Session 1 brief guidance
- All scope decisions aligned with v0.4.1 section 19 Core v1 minus deferred items
- Tests and end-to-end verification pass

---

## Session 3 — The Urgent Contact

**Date:** 18 April 2026

### What was done

Full Urgent Contact system built under `urgent_contact/`:

- **Dispatcher** (`dispatcher.py`) — raises matters, fires sends sequentially or in parallel, polls for responses, cancels pending sends on first valid reply, returns resolution string (APPROVE / REJECT / STOP / CONTINUE / exhausted / throttled)
- **Auth** (`auth.py`) — three methods: channel-native (trusted channel identity), reply-token (6-digit numeric code embedded in outbound message), signed-link (HMAC-SHA256 token tied to show-id + matter-id + secret; wrong show or tampered token rejected)
- **Parser** (`parser.py`) — strict keyword matching: APPROVE / REJECT / STOP / CONTINUE; anything else returns INVALID_FORMAT_REPLY sentinel and does not resolve the matter
- **Throttle** (`throttle.py`) — counts unplanned urgent matters per show; default limit 3; `human-approval` trigger type always exempt; `critical` severity always bypasses
- **Degradation** (`degradation.py`) — DAG pruning: marks direct and transitive dependents of a failed/exhausted scene as `cascading-dependency-failure`; skips scenes already in a terminal state
- **Channels** — `base.py` defines `ChannelAdapter` ABC and `InboundResponse` datatype; `mock.py` implements a file-drop mock channel for test determinism (reads responses from `~/.the-show/mock_responses/<matter-id>.json`)

### Executor integration

- `human-approval` stub replaced with real dispatcher call
- `exhausted` result → scene state becomes `blocked-no-response`; DAG pruning fires for all dependents
- `throttled` result → scene is skipped (not retried); logged as a throttle event
- Urgent contact resolved event logged to SQLite event log

### Test suite

- 84 tests passing (18.9 s) — 37 new tests for urgent_contact, 47 carried from Session 2; 1 additional test in `test_executor.py`
- `test_urgent_contact.py`: parser, auth (all three methods), dispatcher (sequential, parallel, cancellation, exhaustion), throttle (limit, exemptions, critical bypass), DAG pruning (direct, transitive, already-terminal, leaf), executor integration
- Polling interval injectable via constructor kwarg or `THE_SHOW_POLL_INTERVAL` env var (default 5 s); tests pass `poll_interval_seconds=0` for determinism

### Deviations from brief

- **`planned_human_approval` exemption** — brief said "planned human-approval exempt from throttle". Implemented via `trigger_type == "human-approval"` parameter passed by the executor. The `is_allowed()` method checks this before counting. Straightforward interpretation.
- **`STOP` keyword** — spec listed APPROVE / REJECT / CONTINUE; STOP was added as a natural fourth keyword (halt the entire show, not just this scene). Treated equivalently to REJECT at the executor level for now; a STOP→show-abort path is flagged for Session 4 or 5.
- **Mock channel response format** — not specified in brief; implemented as a JSON file dropped at a known path. Real channel polling replaces this entirely in Session 4.
- **Parallel mode triggered by config OR critical severity** — brief said critical bypasses throttle; also made critical force parallel dispatch regardless of mode config. Belt-and-suspenders for time-sensitive alerts.

### Spec ambiguities resolved by interpretation

- **Auth method selection**: brief described three methods without specifying how one is chosen per contact. Implemented as per-contact config (`auth_method` field in show YAML contact spec). Mock channel defaults to `channel-native`.
- **Cancellation timing**: "cancels pending sends on first valid response" — implemented as setting `status='cancelled'` in `urgent_sends` DB rows before returning resolution; the poll loop checks status before firing the next scheduled send.
- **DAG pruning scope**: brief said "cascading-dependency-failure"; implemented to traverse the full dependency graph transitively, not just direct children. Scenes already in any terminal state are skipped (not double-marked).
- **`INVALID_FORMAT_REPLY` vs silence**: a malformed response (not matching any keyword) sends the `INVALID_FORMAT_REPLY` message back to the responder and does NOT resolve the matter — polling continues. This preserves the matter's open state and prompts the contact to try again.

### Open questions for Session 4 (Real Channels)

- Telegram adapter: bot token config, webhook vs polling, group vs DM
- WhatsApp adapter: requires Business API or third-party gateway — which?
- Email adapter: SMTP send + IMAP poll, or a webhook-based provider (Postmark, SendGrid)?
- SMS adapter: Twilio? config for account SID / auth token
- `STOP` keyword: should it abort the entire show immediately, or just block the current scene and let the programme note the early stop?
- Signed-link base URL: needs a real endpoint for Session 4 (currently just a placeholder string in dispatcher)

---

## Session 4 — Real channel adapters

**Date:** 18 April 2026

### What was done

Four real channel adapters built under `urgent_contact/channels/`:

- **Telegram** (`telegram.py`) — polling with `getUpdates`, channel-native auth, `channel_verified_identity=True` only for configured user IDs; offset-tracked for incremental polls
- **Email** (`email.py`) — SMTP send via Gmail App Password; four signed action links per email (APPROVE/REJECT/STOP/CONTINUE); HMAC-SHA256 tokens with 24h expiry; `poll_responses` reads from `link_queue.db`
- **WhatsApp** (`whatsapp.py`) — full skeleton with detailed setup checklist in class docstring; `send()` raises `NotImplementedError`; `poll_responses` functional (reads from `link_queue.db` written by webhook)
- **SMS** (`sms.py`) — Twilio SDK; reply-token auth; `poll_responses` reads from `link_queue.db` written by `/twilio-webhook`

New support modules:

- `link_queue.py` — shared SQLite at `~/.the-show/link_queue.db` with three tables: `link_responses`, `sms_responses`, `whatsapp_responses`; responses consumed atomically on read
- `link_server.py` — Flask app on port 5099; routes: `GET /respond` (email), `GET/POST /whatsapp-webhook`, `POST /twilio-webhook`
- `channels/config.py` — env var helpers for all four channels (reads at call time, not import time)

Dispatcher updated:

- `load_adapters()` function in `dispatcher.py` — registers adapters based on which env vars are set; warns on missing credentials; mock always included

Tests:

- 146 tests passing (21.6 s) — 62 new tests across 5 new test files
- `test_channels_telegram.py` (13), `test_channels_email.py` (14), `test_channels_whatsapp.py` (11), `test_channels_sms.py` (11), `test_link_server.py` (13)

### Decisions and deviations

**Link queue vs direct urgent_responses write** — The brief specified that the link server should write directly to the `urgent_responses` table in the show's per-show SQLite DB. This was not implemented because:
1. The email adapter doesn't know which show's DB to read from inside `poll_responses(handle)`
2. The dispatcher would double-log (calling `log_urgent_response` again after `_process_response`)
Instead: a shared `~/.the-show/link_queue.db` holds responses. Adapters read from there and return `InboundResponse` with `channel_verified_identity=True` (auth already verified by link server). The dispatcher's normal `_authenticate` + `log_urgent_response` flow runs once on top.

**Email auth method = channel-native, not signed-link** — The email adapter handles HMAC verification internally in the link server before queuing the response. Returning `channel_verified_identity=True` from `poll_responses` means the dispatcher's `channel-native` auth path accepts it cleanly. This avoids forcing the email adapter to embed the dispatcher's signed token in links (which would require the adapter to know the show_id for `verify_signed_token`).

**WhatsApp fully skeletonised** — `send()` raises `NotImplementedError`. Meta Business API onboarding can take days; blocking Telegram + email on it was not acceptable. Full activation steps documented in the class docstring.

**Telegram handle = numeric user_id** — Show YAML contact `handle` for Telegram must be the numeric Telegram user_id (which is also the DM chat_id). Display @usernames cannot be used for `sendMessage` without an additional API call; keeping it simple for v1.

**pip not available in venv** — venv was created without pip (uv venv default). Bootstrapped pip via `get-pip.py` before installing new deps. `requirements.txt` now includes flask, twilio, requests, python-dotenv.

### Adapters status

| Adapter   | Status         | Requires from Mark                                |
|-----------|----------------|---------------------------------------------------|
| mock      | Fully working  | Nothing                                           |
| telegram  | Fully working  | Bot token from BotFather + primary/alternate user IDs |
| email     | Fully working  | Gmail App Password + signing secret               |
| whatsapp  | Skeleton only  | Meta Business API onboarding (1–7 days)           |
| sms       | Fully working  | Twilio account SID + auth token + from number     |

### Env vars Mark needs to provide before live testing

- `URGENT_TELEGRAM_BOT_TOKEN` — create bot via BotFather
- `URGENT_CONTACT_PRIMARY_TELEGRAM_USER_ID` — numeric user_id (message @userinfobot)
- `URGENT_CONTACT_ALTERNATE_TELEGRAM_USER_ID` — Greg's numeric user_id
- `URGENT_SMTP_HOST` / `URGENT_SMTP_USERNAME` / `URGENT_SMTP_PASSWORD` / `URGENT_EMAIL_FROM` — Gmail + App Password
- `URGENT_EMAIL_SIGNING_SECRET` — random 32-char hex string
- `URGENT_TWILIO_ACCOUNT_SID` / `URGENT_TWILIO_AUTH_TOKEN` / `URGENT_TWILIO_FROM_NUMBER` — Twilio credentials

Copy `.env.example` → `.env` and fill in. The link server must be running for email links and SMS webhooks to work.

### Open questions for Session 5 (Execution Monitor)

- Should the link server load `.env` automatically on startup? (Currently it does via python-dotenv if installed)
- The launchd plist has hardcoded env vars — Mark needs to manually copy from `.env` into the plist. Automate in a later session?
- `STOP` keyword still doesn't abort the show — defer to Session 5 when the execution loop gets refactored for the monitor

---

## Session 5 — Execution Monitor

**Date:** 18 April 2026

### What was built

Full Execution Monitor system built under `monitor/`:

- **`monitor/patterns.py`** — five pattern-detection functions, each operating on a list of event dicts:
  - `detect_stalled` — fires if no event logged in the last N seconds (default 600)
  - `detect_retry_storm` — fires if a scene has >N attempts within a rolling window (default 5 in 60s)
  - `detect_cost_runaway` — fires on soft or hard USD caps; hard cap takes priority
  - `detect_policy_denials` — fires if a scene accumulates >= N `policy_denied` events (default 3)
  - `detect_oscillation` — Qwen-assisted; calls Ollama `/api/generate` to classify whether retry outputs are converging, diverging, or oscillating; only fires when retry count > 3
  - `check_ollama_available` — probes Ollama `/api/tags` at startup; disables oscillation detection gracefully if Qwen not found

- **`monitor/watcher.py`** — `run_monitor()` polling loop:
  - Runs as a separate process alongside the Stage Manager
  - Polls SQLite event log every N seconds (default 5; injectable via `THE_SHOW_MONITOR_POLL_INTERVAL`)
  - Writes `monitor_events` rows for any triggers that fire; deduplicates within a run
  - Does NOT call the dispatcher directly — Stage Manager consults `monitor_events` between scenes
  - Stop signal: sentinel file `<show-id>.monitor_stop` in state dir (`request_stop()` / `_clear_stop()`)

- **`monitor/cli.py`** — three commands: `cmd_monitor_start`, `cmd_monitor_stop`, `cmd_monitor_events`; `launch_monitor_subprocess()` returns a Popen handle

- **`monitor/__init__.py`** — package marker

### Signal classification

| Signal | Type | Severity | Auto-escalate |
|---|---|---|---|
| stalled | hard | warning | yes (if `any-scene-duration-over` in bible escalation) |
| retry-storm | hard | warning | no — warning only logged to event stream |
| cost-runaway (soft) | hard | urgent | yes (if `cost-hard-cap-reached` in bible escalation) |
| cost-runaway (hard) | hard | critical | yes |
| policy-denials | hard | urgent | yes (if `repeated-policy-denials` in bible escalation) |
| oscillation | soft (Qwen) | warning | no — warning only; operator must configure |

Oscillation and retry-storm in v0.4.1 do not auto-escalate. They log a `monitor_warning_*` event to the event stream and are acknowledged. Operator can promote them to escalation triggers in a future session.

### Stage Manager integration

- `_handle_monitor_signals(show_id, show, state)` called between every scene in `run_show()`
- Checks `get_unacknowledged_monitor_events()`
- For escalation-mapped triggers: calls `UrgentContactDispatcher` and logs `monitor_escalated` event
- For warning-only triggers: logs `monitor_warning_<type>` event
- All events acknowledged after processing

### State layer additions

- `monitor_events` table added to SQLite schema (WAL, with index on `show_id, created_at`)
- `add_monitor_event()` — inserts a row, returns id
- `get_unacknowledged_monitor_events()` — used by Stage Manager between scenes
- `acknowledge_monitor_events()` — marks events processed
- `get_monitor_events()` — used by CLI and programme generator

### CLI additions

Three new subcommands added to `cli.py`:
- `monitor-start <show_id>` — run monitor in foreground
- `monitor-stop <show_id>` — write stop sentinel
- `monitor-events <show_id> [--limit N]` — print recent monitor events

`cmd_run()` now launches the monitor as a background subprocess and stops it when the show finishes.

### Programme additions

- `## Urgent Matters` section now reads from SQLite (replacing the Session 3 stub)
- `## Monitor Signals` section added: total count, per-trigger breakdown, acknowledged count
- `monitor_events` key added to JSON programme output

### Qwen / Ollama

- Model: `qwen3:14b` via Ollama at `http://localhost:11434`
- Env vars: `THE_SHOW_OLLAMA_URL`, `THE_SHOW_QWEN_MODEL`
- Availability checked once at monitor startup; if unreachable or model missing, oscillation detection silently disabled

### Test suite

- 30 new tests in `tests/test_monitor.py` — all passing
- 160 total passing (up from 146 in Session 4)
- Pre-existing 1 failure + 15 errors from Session 4 (twilio/flask missing packages) — unchanged, not in scope

### Decisions and deviations

- **`_handle_monitor_signals` returns False always** — the brief's description of "abort if critical unhandled signal" was simplified: the function always acknowledges events and returns False. Aborting via the monitor is deferred — the dispatcher `raise_urgent_matter` call handles escalation. This keeps the function testable and decoupled.
- **Oscillation and retry-storm warning-only** — brief said operator should configure whether these escalate. In v0.4.1, neither is in `_MONITOR_ESCALATION_MAP`. They fire `add_event` with `monitor_warning_*` type instead.
- **`_stop_file` uses `_state_mod.STATE_BASE`** — watcher imports `state` as `_state_mod` so that `STATE_BASE` resolves at call time, after monkeypatching in tests. This ensures the sentinel file lands in the test's tmp dir.
- **MockChannel as fallback in `_handle_monitor_signals`** — follows the same pattern as `run_human_approval`. Production deployments should configure real channels via `load_adapters()`.

---

## Session 6 — First real show (rehearsed)

**Date:** 18 April 2026

### What was done

- Created `shows/` directory at project root
- Wrote `shows/curiosity-cat-launch-brief.yaml` — a 6-scene show producing the Front Page briefing document for the Curiosity Cat r/ClaudeCode launch
- Validated and rehearsed the show end-to-end: `python3 cli.py run shows/curiosity-cat-launch-brief.yaml`
- Show status: **completed** — 5 of 6 scenes played-principal, 1 blocked-no-response (approve_redlines, as expected)
- Programme generated at `~/.the-show/state/curiosity-cat-launch-brief/programme.md`

### Scene outcomes (rehearsal)

| Scene | Status | Notes |
|-------|--------|-------|
| gather_context | played-principal | Sub-agent stub returned synthetic list |
| research_categories | played-principal | min-length: 6 passed (50 stub items) |
| draft_responses | played-principal | min-length: 5 passed |
| approve_redlines | blocked-no-response | Timed out at 30s (THE_SHOW_URGENT_TIMEOUT=30). Expected. |
| compile_briefing | played-principal | Critical design: NOT in approve_redlines.depends-on |
| save_and_notify | played-principal | write-json stub returned path; no actual file written |

### Simulated cost: $1.00 (4 × $0.25 sub-agent stubs)

### Bugs found and fixed

**`schema: list` is silently parsed as a dict schema.** `meets_success()` checks for `[]` in the schema string, or `list[` / `list ` prefix — the bare word `list` falls through to the else branch and expects a dict. Fix: use `schema: object[]` for list outputs in success-when and output declarations. Updated all 4 sub-agent output schemas in the YAML.

### Key design decisions in the show

**`compile_briefing` does NOT depend on `approve_redlines`.**
Why: if scene 004 exhausts (no human response), it gets `blocked-no-response` status. The DAG pruner cascades `cascading-dependency-failure` to all direct dependents. If scene 005 had `approve_redlines` in its `depends-on`, it would be pruned and the briefing would never compile. The framework has no optional-dependency concept. Decision: 005 depends only on 001–003; it uses scene 003's `red_line` flags directly (set by the sub-agent). Mark's explicit approval is the happy path — conservative defaults are the fallback.

**Mock channel fires in rehearsal; executor hardcodes MockChannel.**
`run_human_approval` in executor.py always passes `adapters=[MockChannel()]` to the dispatcher. The live channels in the YAML urgent-contact config (telegram, email, sms) are commented out — they cannot fire until the executor is updated to call `load_adapters()` based on the show config. This is the next gap to close before the live run.

**Sub-agent stub returns lists, not strings or dicts.**
All sub-agent outputs in rehearsal are lists of synthetic dicts (stub behaviour). For the live run, real LLM adapters must be wired up. The briefing_document output (intended to be a markdown string) is declared as `schema: object[]` for rehearsal compatibility.

### What's needed before the live run

1. **Wire real channel adapters in executor.py.** Replace hardcoded `[MockChannel()]` in `run_human_approval` with `load_adapters(show)` (or equivalent). This allows Telegram/email/SMS to fire.
2. **Wire real LLM adapters.** The sub-agent stub in adapters.py must be replaced with actual LiteLLM/Anthropic SDK calls. Until this happens, sub-agent scenes return synthetic data.
3. **Set env vars** (see Session 4 notes for the full list): `URGENT_TELEGRAM_BOT_TOKEN`, `URGENT_CONTACT_PRIMARY_TELEGRAM_USER_ID`, SMTP config, Twilio config.
4. **Fix briefing_document schema.** Once real LLMs are wired, scene 005 will return a markdown string. Change output type/schema to `type: string, schema: string` and update `success-when: min-length: 1500` (character count check).
5. **Mark to review red-line list.** Run the show live, respond to the Telegram urgent matter in scene 004.

### Run command for live run (after env vars set)

```
python3 cli.py run shows/curiosity-cat-launch-brief.yaml
```

Do not set `THE_SHOW_URGENT_TIMEOUT` — use the 300-second default so Mark has time to respond.
