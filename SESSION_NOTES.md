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
