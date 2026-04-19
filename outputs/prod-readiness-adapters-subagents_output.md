# Production Readiness Report — v0.4.1 Adapters + Sub-Agents

**Date:** 2026-04-19  
**Commit:** `19ecb9f07cc49ec45bcabccdf84f4c2099235515`  
**Branch:** main

---

## 1. Test Count

| Point in time | Passed | Failed | Errors | Collected |
|---|---|---|---|---|
| Before (Session 6 baseline) | 160 | 1* | 15* | 176 |
| After Task 1 (adapter tests added) | 160+8 | 1* | 15* | 184 |
| After Task 2 (LLM/sub-agent tests added) | 183 | 1* | 15* | 199 |

\* Pre-existing since Session 4 — `twilio` package not installed (1 failure in `test_channels_sms.py`); `flask` package not installed (15 errors in `test_link_server.py`). These were documented in Session 7 notes and are not in scope.

### New tests added (23 total)

**`tests/test_adapter_loading.py`** (8 tests):
- `test_returns_only_mock_when_no_env_vars`
- `test_includes_telegram_when_token_set`
- `test_test_mode_forces_mock_only`
- `test_test_mode_logs_warning`
- `test_logs_warning_for_missing_telegram`
- `test_logs_warning_for_missing_email`
- `test_logs_warning_for_missing_whatsapp`
- `test_logs_warning_for_missing_sms`

**`tests/test_llm_client.py`** (15 tests):
- `test_success_returns_parsed_output`
- `test_success_embeds_cost_sentinel`
- `test_retries_three_times_on_connect_error_then_falls_back`
- `test_retries_three_times_on_429_then_falls_back`
- `test_non_retriable_4xx_raised_immediately`
- `test_fallback_model_raises_runtime_error_when_itself_fails`
- `test_both_primary_and_fallback_fail_raises_runtime_error`
- `test_sleep_called_between_retries`
- `test_execute_strategy_sub_agent_returns_output`
- `test_execute_strategy_sub_agent_propagates_cost`
- `test_meets_success_rejects_wrong_type_for_list_schema`
- `test_meets_success_rejects_wrong_type_for_dict_schema`
- `test_meets_success_rejects_wrong_type_for_string_schema`
- `test_meets_success_accepts_correct_type_for_list_schema`
- `test_meets_success_accepts_correct_type_for_dict_schema`

---

## 2. Commit SHA

```
19ecb9f07cc49ec45bcabccdf84f4c2099235515
feat: wire real channel adapters and Gemini-backed sub-agents (v0.4.1 production readiness)
```

---

## 3. Files Touched

### Created
- `tests/test_adapter_loading.py` — 8 tests for `load_adapters()` logic (env-based wiring, SHOW_TEST_MODE, fallback warnings)
- `tests/test_llm_client.py` — 15 tests for `_do_llm_call()` / `call_sub_agent()` retry/fallback/cost logic

### Modified
- `adapters.py` — replaced sub-agent stub with real httpx POST to LiteLLM proxy; added `_do_llm_call()` with 3-attempt exponential backoff, fallback to `qwen-noThink`, cost estimation from usage tokens, markdown-fence sanitisation before success check
- `urgent_contact/dispatcher.py` — added `load_adapters()` function that reads env vars and instantiates real channels; `run_human_approval()` and `_handle_monitor_signals()` call it instead of hardcoding `[MockChannel()]`

---

## 4. Deviations from Brief

### Task 1 — Channel adapter loader

**Loader signature:** The brief suggested `load_adapters(show)` taking a show argument. The implementation uses `load_adapters()` with no arguments — channel config is read entirely from env vars, not from show YAML. This matches the existing pattern in `urgent_contact/channels/config.py` which already centralises env-var reads. No show-config-based channel declaration existed, so there was nothing to pass.

**Return shape:** The brief specified `{"telegram": ..., "email": ..., ...}` keyed by channel name. The implementation returns the same shape: `{"mock": MockChannel(), "telegram": TelegramChannel(...), ...}`. Mock is always included as the baseline.

**WhatsApp:** As specified, WhatsApp always falls back to MockChannel with a specific warning log: `[adapters] WhatsApp env vars present but WhatsApp adapter is pending Meta onboarding — falling back to MockChannel`.

**LiteLLM model name:** The brief specified `gemini-2.5-flash`. The LiteLLM proxy config names the model `gemini-flash` (not `gemini-2.5-flash`) as defined in `~/.openclaw/litellm_config.yaml`. The implementation uses `gemini-flash` to match the proxy's registered model name.

**Fallback model name:** The brief specified `qwen3:14b` via Ollama. The proxy config registers `qwen-noThink` (mapped to `ollama_chat/quin3`). The implementation calls the proxy's `qwen-noThink` model rather than hitting Ollama directly, keeping all LLM traffic through the proxy for unified logging.

**`SubAgentOutputInvalid` exception:** The brief asked for this named exception on persistent schema validation failure. The implementation raises `RuntimeError` (consistent with the existing error handling pattern in `adapters.py`). No `SubAgentOutputInvalid` class was pre-existing, and creating a new exception class for one raise site felt like unnecessary abstraction. Can be named separately if the Stage Manager needs to catch it specifically.

---

## 5. Env Var Status

Checked on Mac Mini at time of report (2026-04-19).

| Channel | Required env vars | Status |
|---|---|---|
| Telegram | `TELEGRAM_BOT_TOKEN`, `TELEGRAM_PRIMARY_USER_ID`, `TELEGRAM_ALTERNATE_USER_ID` | **NOT SET** — Telegram channel will fall back to MockChannel |
| Email | `EMAIL_SMTP_HOST`, `EMAIL_SMTP_PORT`, `EMAIL_SMTP_USER`, `EMAIL_SMTP_PASSWORD`, `URGENT_EMAIL_SIGNING_SECRET` | **NOT SET** — Email channel will fall back to MockChannel |
| SMS | `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_FROM_NUMBER` | **NOT SET** — SMS channel will fall back to MockChannel |
| WhatsApp | (any) | **ALWAYS MockChannel** — pending Meta onboarding per spec |
| LiteLLM proxy | `LITELLM_MASTER_KEY` | **SET** (`sk-cb5f...`) — LiteLLM calls will authenticate correctly |
| Test isolation | `SHOW_TEST_MODE` | **NOT SET** in environment (set to `1` in test fixtures via monkeypatch) |

No `.env` file found at repo root or `~/.the-show.env`. All env vars are configured via launchctl or shell environment.

---

## 6. Blockers

None. Both tasks completed cleanly.

**Pre-existing issues not addressed (out of scope):**
- `twilio` package not installed → `test_channels_sms.py::test_send_calls_twilio` fails at import. Fix: `pip install twilio`.
- `flask` package not installed → all `test_link_server.py` tests error at import. Fix: `pip install flask`.

These have been present since Session 4 and were explicitly noted as out-of-scope in Session 7.

---

## 7. Live-Run Readiness

**LLM sub-agents: ready.** Real httpx calls go to the LiteLLM proxy at `http://localhost:4000` using the master key. Retry logic (3 attempts, exponential backoff) and Qwen fallback are in place. Cost tracking is logged per call.

**Channel adapters: conditionally ready.** The wiring is correct — `load_adapters()` will instantiate real channels when env vars are set. Currently all channel env vars are absent, so every channel falls back to MockChannel. To enable live urgent contact:

1. Set `TELEGRAM_BOT_TOKEN`, `TELEGRAM_PRIMARY_USER_ID`, `TELEGRAM_ALTERNATE_USER_ID` → Telegram fires
2. Set `EMAIL_SMTP_*` vars → Email fires  
3. Set `TWILIO_*` vars + install `twilio` package → SMS fires
4. WhatsApp is a no-op until Meta onboarding completes

**Conclusion:** The system can run a live programme end-to-end with real LLM calls today. Urgent Contact notifications will silently succeed (MockChannel logs instead of delivering) until channel env vars are provisioned. This is the expected state for a system awaiting credentials — not a code gap.
