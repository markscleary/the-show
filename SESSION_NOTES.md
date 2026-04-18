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
