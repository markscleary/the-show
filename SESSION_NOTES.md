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
