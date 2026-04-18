# The Show: A Framework for Running Agents Unattended

**Version:** 0.4.1 (LOCKED — Section 11 patched, spec frozen for build)
**Date:** 18 April 2026
**Authors:** Mark Cleary (framework, theatre grounding, the urgent contact concept), Claude Opus 4.7 (drafting), with structural input from iterative review.
**Previous versions:** v0.1, v0.2, v0.3, v0.4

---

## Purpose of this document

This is v0.4.1. It is the final locked spec. It incorporates six patches to Section 11 surfaced through iterative structural review of v0.4. Nothing else has been touched.

**Changes from v0.4 (all in Section 11):**
- 11.3: authentication block added to the urgent contact declaration
- 11.5: strict response format specified (keywords, structured payloads, free-text dropped)
- 11.5: explicit cancellation rule on first valid response
- 11.6: DAG pruning made explicit for blocked-no-response
- 11.7: severity levels added (urgent default, critical option); auto throttle option added
- 11.8: channel adapter authentication requirements specified

**The spec is frozen.** No more structural changes. The next work happens in code.

v0.4.1 is what we build.

**The spine has not moved.** The Show lets operators run agents unattended, without the approval-tap problem, with a framework that knows how to find them when a real decision is needed.

**The most important rule in theatre is that there are no rules. Do what works. The audience will be the judge.**

---

## 1. What this is, in one paragraph

The Show lets you run agents on a task — or a sequence of tasks — without tapping approve between every step. You write the task as if it's a production: a running order of scenes, each with its own fallback plans. The system runs the show unattended. If it needs your input, it reaches you across every channel you've authorised until you respond. When it's done, you get a programme describing what happened.

It's for people who already trust their agents and want the agents to get on with it.

## 2. Who this is for

Small-fleet operators. Five agents, twenty agents, whatever sits on a desktop or a small server. Founders. Creative directors. Researchers. Festival producers. People who have real work to do and are tired of 93% of their approval taps being "yes, obviously" — and who need to trust that when the remaining 7% matters, the framework will reach them.

Not for enterprise compliance teams. Not for Python developers building custom agent pipelines. Not for anyone who needs a full org chart, budget governance, or a dashboard with twelve gauges.

## 3. The theatre frame — honestly

The Show borrows from theatre because theatre has worked out, over four centuries, how to get complex live work from an idea to an audience reliably. The borrowing is honest in places and decorative in others.

**Where theatre is load-bearing:**
- *Bounded run* — a show opens and closes. Not a daemon.
- *Rehearsals* — the show gets walked through before it runs live.
- *Previews* — the first public runs are caveated, iterative, and expected to be imperfect.
- *Opening night* — the first run treated as the real thing.
- *The prompt book* — what the stage manager actually works from.
- *The programme* — the written record of what happened.
- *Improvisation as its own stream* — not a behaviour of the stage manager, but a named creative form we permit operators to invoke deliberately.

**Where theatre was decorative and is not part of v1:**
- Understudy vs Swing (collapsed to ordered fallbacks — v0.2)
- Notes as mid-run rewriting (replaced with bounded adaptation — v0.2)
- Touring, revivals, full production lifecycle (deferred to roadmap — v0.3)
- Stage manager as improvisational craft (runtime is deterministic — v0.2)

## 4. Vocabulary

| Term | Meaning |
|---|---|
| Show | A task or group of tasks written in The Show's format |
| Prompt Book | Standing orders for this show — strategy, cost intent, escalation, urgent contact |
| Running order | The sequence of scenes |
| Scene | One unit of work |
| Principal | The primary strategy for a scene |
| Fallbacks | Up to two alternative strategies if principal fails |
| Adaptive | Bounded parameter variation within declared limits |
| Cut | What to do when principal, fallbacks, and adaptive all fail |
| Stage manager | The runtime that executes the show (deterministic, no LLM calls) |
| Director | Separate pre-show tool for drafting or revising a show |
| Execution monitor | Process that detects stall, oscillation, runaway |
| Urgent Contact | Mechanism to reach the operator across declared channels when human input is needed |
| Primary | The operator — first person the urgent contact tries |
| Alternate | A second authorised human the urgent contact can try |
| Rehearsal mode | A run with side effects mocked |
| Programme | The report after the show ends |
| Risk slider | What the agent can touch |
| Exploration slider | How far the agent can roam in method |

## 5. Core principles

Eight principles. Not negotiable without changing what the product is.

**Spine first.** Everything serves the goal of running agents unattended without approval fatigue.

**The stage manager is deterministic.** The runtime never calls a language model to make a decision. All intelligence happens in the Director.

**Every scene declares what it produces and what it needs.** Explicit inputs, explicit outputs, named references. No implicit shared state.

**Side effects are idempotent by enforcement.** Framework generates idempotency keys automatically for any side-effectful scene.

**Agent outputs are data, not instructions.** Every scene declares whether its output is trusted or untrusted. Untrusted output is schema-validated and cannot trigger tool execution based on its content.

**Policy lives outside the show.** The show describes intent. Policy lives in C-Cat or equivalent. The show compiles against policy at load time; policy wins.

**The run is bounded.** Every show has max duration, max scene count, and must-complete requirement.

**When the show needs a human, it finds one.** The framework reaches across the operator's declared channels, escalating until someone responds or channels exhaust. If nobody responds, the show degrades gracefully.

## 6. The lifecycle — four states

Four states, ending at Opening Night. After that, the show is in production and the framework does not impose further structure. Roadmap versions may add more as operator needs clarify.

**Draft.** Written but never run. No validation beyond syntax. Anyone edits anything.

**Rehearsals.** Walked through and iterated. Scene-by-scene walkthroughs, full run-throughs with mocked side effects, operator-present iteration. Prompt Book gets refined. Frequent editing normal.

**Previews.** Runs against live services with real side effects, but operator knows it isn't finished. Changes between runs expected. Typically reduced scope.

**Opening Night.** First canonical performance. After Opening Night, in production.

**Lifecycle table:**

| State | Can edit show? | Can run? | Real side effects? |
|---|---|---|---|
| Draft | Yes, anyone | No | No |
| Rehearsals | Yes, operator | Yes | Operator's choice |
| Previews | Only between runs | Yes | Yes, caveated scope |
| Opening Night | No, frozen for the run | Once | Yes |
| In production (post-Opening) | Requires new version | On schedule or on demand | Yes |

The operator authorises every transition. The framework signals readiness but does not advance automatically.

## 7. The Prompt Book

Short by design. Contains what the stage manager needs to know during the run. Does not contain security policy (C-Cat). Does not contain secrets (referenced by name).

```yaml
prompt-book:
  strategy:
    purpose: "Enrich 50 outreach contacts for Dubai festival"
    priority: quality-over-speed
    cost-intent:
      per-scene-soft-cap: 1.00
      per-show-hard-cap: 25.00
  
  bounds:
    max-duration: 2h
    max-scenes: 50
    must-complete: true
  
  escalation:
    escalate-when:
      - blocked-scenes-consecutive: 3
      - cost-hard-cap-reached: true
      - critical-scene-failed: true
      - any-scene-duration-over: 600
      - repeated-policy-denials: 5
  
  sliders:
    risk: streetcat
    exploration: edge-of-the-world
  
  stage-manager:
    mode: deterministic
    idempotency: enforced
  
  policy-layer:
    source: c-cat
    compile-on-load: true
  
  reporting:
    programme-format: [markdown, json]
    deliver-to: [disk, email]
  
  urgent-contact:
    # Full specification in section 11
    auth:
      require-verification: true
      methods: [reply-token, signed-link]
    primary:
      name: Mark
      channels:
        - type: telegram
          handle: "@markinsydney"
          escalation-delay: 0m
        - type: whatsapp
          handle: "+61 468 857 482"
          escalation-delay: 5m
        - type: email
          handle: "mark@shortandsweet.org"
          escalation-delay: 15m
        - type: sms
          handle: "+61 468 857 482"
          escalation-delay: 30m
    alternate:
      name: Greg
      channels:
        - type: whatsapp
          handle: "+XX XXX XXX XXX"
          escalation-delay: 0m
        - type: email
          handle: "greg@shortandsweet.org"
          escalation-delay: 10m
    mode: sequential
    alternate-invoke-after: primary-exhausted
    frequency-throttle:
      max-per-show: 3       # or: auto
      after-threshold: degrade-gracefully
    channel-culture:
      default-language: en-AU
      default-register: direct
```

## 8. The running order

A sequence of scenes. Each does one thing. Data flows through declared outputs and inputs.

Five scene methods in v1: `prompt`, `tool-call`, `sub-agent`, `human-approval`, `scheduled`.

Example scene with urgent contact triggered on human-approval:

```yaml
- scene: 003
  title: "Operator approval before sending"
  depends-on: [002]
  
  inputs:
    to-send: from(002.enriched)
  
  principal:
    method: human-approval
    severity: urgent              # urgent | critical
    deadline: 4h
    prompt: |
      {{ to-send | length }} enriched contacts ready to send.
      Sample: {{ to-send | first(3) }}
      Reply APPROVE to proceed, REJECT to revise, STOP to halt.
  
  cut:
    condition: blocked-no-response
    continue-remaining: true
  
  outputs:
    approved:
      type: boolean
```

## 9. Fallbacks, adaptive, cut — execution order

Every scene has a principal. Up to two fallbacks. Execution order:

1. Principal
2. Principal with adaptive variation (if adaptive is allowed and exploration is not Home)
3. Fallback 1
4. Fallback 1 with adaptive variation
5. Fallback 2
6. Fallback 2 with adaptive variation
7. Cut

**Success is evaluated per strategy.** Each strategy has its own `success-when` criteria. Adaptive variations use the parent strategy's criteria. **First success terminates evaluation.**

**Cut conditions:**
- `escalate` — halt the show, raise an urgent matter
- `continue` — skip, mark cut, move on
- `continue-with-partial` — if partial output meets declared minimum, accept and continue
- `blocked-no-response` — used with `human-approval` scenes when urgent contact exhausts

## 10. The Exploration and Risk sliders

Two axes. Not equivalent. Not parallel.

**Risk slider — what the agent can touch.**

- **Housecat** — local agents only, no external calls unless per-scene authorised
- **Streetcat** — local and external agents per C-Cat policy
- **Alley Cat** — any capability C-Cat permits

**Exploration slider — how far the agent can roam in method.**

- **Home** — stay in known territory, try the declared method
- **Edge of the World** — go to the charted boundary. Adaptive retries within bounds. Default.
- **Here Be Dragons** — go past the edge. Authorised to try genuinely different approaches within policy.

Per-scene override permitted. C-Cat has final say. Operators can configure display names; underlying values stay the same.

## 11. The Urgent Contact

The feature that makes unattended operation genuine. When the framework needs a human decision and the operator isn't at their screen, it reaches across every channel they've authorised — escalating channel by channel, trying the alternate human if the primary doesn't respond, in language calibrated to the receiving channel.

### 11.1 Purpose and principle

Every other agent framework stops and waits when it needs a human. The Show doesn't. It has a job to finish and a chain of authorised humans who can unblock it.

The register is **urgent** — not emergency. An agent calling a Mexican hotel on behalf of a travelling operator says "I have an urgent business matter for Mr Smith in Room 412" — not "I have an emergency." Culture-appropriate, language-appropriate, calibrated to not inflame.

### 11.2 When urgent contact is invoked

Four triggers:

- A `human-approval` scene runs and reaches its `deadline`
- Execution Monitor detects a condition in the Prompt Book's escalation list
- A scene's `cut: escalate` condition fires
- A scene declares `severity: critical` and runs

The urgent contact is not used for programme delivery, informational updates, or any non-blocking notification.

### 11.3 The chain — with authentication

The operator declares a primary and optionally an alternate. Each has channels with escalation delays.

**Authentication is required.** Unauthenticated responses cannot control agent execution. This is non-negotiable — without it, a spoofed SMS could authorise destructive actions.

```yaml
urgent-contact:
  auth:
    require-verification: true       # default true, cannot be false in production
    methods: [reply-token, signed-link]
  primary:
    name: Mark
    channels:
      - type: telegram
        handle: "@markinsydney"
        escalation-delay: 0m
        auth-method: channel-native   # Telegram bot API verifies user_id
      - type: whatsapp
        handle: "+61 468 857 482"
        escalation-delay: 5m
        auth-method: reply-token
      - type: email
        handle: "mark@shortandsweet.org"
        escalation-delay: 15m
        auth-method: signed-link
      - type: sms
        handle: "+61 468 857 482"
        escalation-delay: 30m
        auth-method: reply-token
  alternate:
    name: Greg
    channels:
      - type: whatsapp
        handle: "+XX XXX XXX XXX"
        escalation-delay: 0m
        auth-method: reply-token
      - type: email
        handle: "greg@shortandsweet.org"
        escalation-delay: 10m
        auth-method: signed-link
  mode: sequential
  alternate-invoke-after: primary-exhausted
```

**Authentication methods:**

- **channel-native** — the channel's own API verifies sender identity (Telegram bot checking user_id, Signal's verified sender, authenticated WhatsApp Business). Use where the channel supports it.
- **reply-token** — framework generates a 6-digit token, includes it in the message, response must include the token to be valid. For SMS, WhatsApp, and other text channels.
- **signed-link** — framework sends a one-time signed magic link; clicking the link registers the response. For email primarily.

If a channel adapter cannot support any authentication method, it carries a warning flag in the programme and may be configured as trusted-channel-only (operator acknowledges the risk).

### 11.4 Invocation modes

Three modes, operator-declared.

**Sequential** (default). Primary's channels fire in their declared order with declared delays. If primary exhausts without response, alternate's chain starts.

**Parallel.** Primary and alternate both start at the same time. Both chains run independently. Use when the alternate is equally authorised and speed matters.

**Alternate-first.** Alternate's chain runs first, primary's is fallback. Use when the operator is deliberately unreachable.

### 11.5 Response resolution — strict format, first-response-wins

**The stage manager does not parse intent.** Responses must be exact matches or structured payloads.

**Accepted responses:**

- **Strict keywords** — case-insensitive exact match: `APPROVE`, `REJECT`, `STOP`, `CONTINUE`. (Channels without button support use these.)
- **Structured payloads** — Telegram inline buttons, email action buttons, webhook callbacks. (Channels with button support present these and treat the button click as the response.)
- **Tokens** — when `auth-method: reply-token`, the response must include the system-generated token alongside the keyword or button payload.

**Free-text responses** ("yep", "call me", "go ahead but only for half") are not valid. The channel adapter replies once with "Invalid format. Reply APPROVE, REJECT, or STOP." The escalation timer continues unaffected.

**First valid response wins.** The moment a valid, authenticated response is recorded in the SQLite state, the urgent matter flips to `resolved`. The escalation scheduler is terminated. **All pending scheduled channel sends are cancelled immediately.** Channels already in flight cannot be recalled, but no further escalation occurs. The operator will not receive a single ping after they have successfully replied.

### 11.6 Graceful degradation — with explicit DAG pruning

If every channel in both chains exhausts without a valid response, the urgent matter is marked `exhausted`.

**Triggered by `human-approval` scene:**

- The scene's cut condition fires.
- If cut is `blocked-no-response`, the show continues executing any downstream scene that does not depend on this scene's output.
- **DAG pruning is explicit:** any scene whose input depends on a `blocked-no-response` output is automatically cut with reason `cascading-dependency-failure`. Parallel scenes without that dependency run to completion.
- At end of show, the programme reports what ran, what was blocked, and what needs the operator's attention.

**Triggered by Execution Monitor escalation:** show pauses in `awaiting-operator` state. No further urgent contacts raised. Programme generated and delivered to `reporting.deliver-to` channels.

**Triggered by scene `cut: escalate`:** same as Monitor escalation.

### 11.7 Frequency throttle and severity levels

**Severity has two levels:**

- **Urgent** (default) — standard escalation, respects frequency throttle
- **Critical** — bypasses frequency throttle, defaults to parallel invocation mode, uses stronger language in the message. Use for genuine show-stoppers the operator must respond to regardless of earlier activity.

Scene declarations include `severity: urgent | critical` (default urgent).

**Frequency throttle** prevents a broken show from spamming channels.

```yaml
frequency-throttle:
  max-per-show: 3           # integer, or auto, or per-duration rule
  after-threshold: degrade-gracefully
  rule: per-10-scenes: 1    # optional, when max-per-show is auto
```

**Options for `max-per-show`:**

- Integer (default: 3) — hard cap on unplanned escalations per show
- `auto` — scales with scene count using the `rule` declaration
- Per-show override in individual Prompt Books

**Planned `human-approval` scenes are exempt from the throttle.** They're expected, not broken. The throttle targets unplanned escalations from the Monitor or scene failures.

When the threshold triggers, `urgent` severity escalations are suppressed for the remainder of the show. **`critical` severity bypasses the throttle entirely.** The programme flags the throttle trigger prominently.

### 11.8 Channel adapters — authentication requirement

The core framework ships with adapters for Telegram, WhatsApp, email, and SMS. These cover most operators.

**Every adapter must support at least one authentication method** (channel-native, reply-token, or signed-link). Adapters that cannot support any authentication method can be configured as trusted-channel-only, but this carries a warning flag in every programme from any show using them. The framework refuses to ship adapters that silently bypass authentication.

Any channel can be added via a small adapter meeting the minimum contract: accept a message with context, support at least one auth method, report delivery status, capture a reply. Examples: Signal, LINE, WeChat, Slack DM, Discord DM, Microsoft Teams, Matrix, phone alarm triggers, voice calls through AI phone assistants, future robot-home integrations.

Channel-culture configuration (language, register, formality) can be set at the urgent-contact level or per channel.

### 11.9 Programme reporting on urgent contact use

The programme includes a dedicated section for urgent matters raised during the run:

- How many raised, and at what severity
- What triggered each
- Which channels fired and with what auth method
- Which channel got the response (if any) and on what timeline
- Whether the frequency throttle triggered
- Any channels flagged as trusted-channel-only

Over time this data helps operators tune their escalation schedule and identify shows that generate too many urgent matters.

### 11.10 Programme delivery when urgent contact triggered

When an urgent matter is raised during a run, the programme is delivered via the operator's declared `reporting.deliver-to` channels — including email by default. An operator who was out of reach during the run won't check their disk; email arrival is how they learn the show completed (or paused) and what needs their attention.

## 12. The Director — adjacent, not core

Separate pre-show tool. Not part of stage manager. Uses language models. Budget separate from show's budget.

Two modes in v1: prose-to-running-order, rehearsal-review.

Adjacent — core framework runs without it.

## 13. The Execution Monitor — core

Process that watches show execution for patterns the stage manager can't see from inside its own loop.

**Watches for:**
- Oscillation
- Stalled progress
- Retry storms
- Cost runaway
- Repeated policy denials

When any trigger fires, the Monitor adds to the escalation list. The Stage Manager checks between scenes and raises an urgent matter if the threshold is met.

Core. Runs a small local model (Qwen 3 14B candidate).

## 14. Rehearsal mode

A show runs in rehearsal with `rehearsal: true`. In rehearsal:
- Language model calls still happen
- Side-effectful service calls are mocked and logged
- **Urgent contact is mocked** — framework logs what it would have sent rather than actually reaching the operator
- Output is a rehearsal programme, clearly marked
- Promotion to live run re-runs from scratch

## 15. The programme

**Title summary:** show name, lifecycle state, start and end time, duration, outcome summary, total cost, operator-attention items at top.

**Scene summary:** each scene with status, selected strategy, output summary, time, cost, warnings.

**Urgent matters:** section per 11.9.

**Machine log:** companion JSON with exact transitions, retries, idempotency keys, policy denials, adaptation actions, input/output bindings, urgent contact events, authentication verifications.

Progressive during show. Peek view available. Finalised on completion. Markdown primary, JSON companion, optional HTML.

## 16. Handoff between scenes — the untrusted output path

When a scene produces untrusted output:

1. Scene produces output.
2. **Sanitisation:** markdown fences stripped, JSON extracted from code blocks if present.
3. Output validated against declared schema. Schema failure → scene fails.
4. **Optional field-level validators** run if operator declared them:
   ```yaml
   outputs:
     enriched:
       type: list
       schema: enriched-contact[]
       field-validators:
         website: url-allowlist(trusted-domains.txt)
         email: regex(^[\w.-]+@[\w.-]+$)
   ```
5. Validated output written to show state.
6. Downstream scenes receive only schema-conforming fields. Free-text fields from untrusted output are tagged as untrusted.
7. If downstream scene uses untrusted text in a method that could trigger tool execution, framework refuses and marks scene failed.

## 17. Communication between the three processes

**SQLite with WAL** (Write-Ahead Logging) mode. Built into Python. Single file on disk. ACID-compliant concurrency. Queryable event log used directly for programme generation. Survives reboots and process crashes.

**Schema:** event log, scene state, show state, urgent contact state, monitor flags.

v2 may replace with message queue at scale. v1 does not need it.

## 18. Show edits during runs

Rules depend on lifecycle state:

- **Draft:** edit freely
- **Rehearsals:** edit between runs or during pauses
- **Previews:** edit between runs only, no mid-run edits
- **Opening Night and post-Opening:** any edit produces a new version; previous archived

## 19. Scope — what ships in v1

**Core v1:**

- YAML parser and schema validation
- Explicit input/output binding between scenes
- Scene execution per section 9 order
- Retry policy per scene
- Automatic idempotency key generation for side-effectful methods
- Persisted state machine (SQLite with WAL)
- Rehearsal mode with default mocks
- Programme generation (markdown + JSON)
- CLI with validate, run, peek commands
- Input-trust enforcement with markdown-fence sanitisation
- C-Cat policy compilation at load time
- Human-approval scene method
- **Urgent Contact** — primary, alternate, three modes, authentication, strict response format, frequency throttle with urgent/critical severity, graceful degradation with DAG pruning
- **Execution Monitor** — oscillation, stalled progress, retry storms, cost runaway, repeated policy denials
- Four channel adapters (Telegram, WhatsApp, email, SMS) each with authentication support

**Adjacent v1:**

- Director (prose-to-YAML, rehearsal-review)
- Additional channel adapters beyond the core four
- Field-level validators for untrusted outputs

**Roadmap:**

- Multi-show dependency analysis
- Cost forecasting in Director
- Lifecycle revisions (revivals, touring variants)
- Message-queue IPC
- UI beyond CLI
- Voice channel adapters (AI phone assistants)
- Culture/language calibration for voice channels
- Pre-emptive escalation (Monitor predicts trouble before thresholds hit)
- Computer use / vision-click as scene method

## 20. State machine

**Runtime states:**
planned → running → paused → completed | aborted

**Scene states:**
queued → running → played-principal | played-fallback-1 | played-fallback-2 | played-adaptive | played-partial | cut | blocked-no-response | cascading-dependency-failure | blocked | failed

**Lifecycle states:**
draft → rehearsals → previews → opening-night → in-production

**Urgent matter states:**
raised → channel-firing → (response-received | channel-exhausted) → (resolved | exhausted-degrade | exhausted-pause)

All persisted to SQLite. Crash-recoverable.

## 21. Failure modes

- **Stage manager crashes** → state in SQLite, resumable
- **Scene timeout** → falls through per section 9
- **Circular dependency** → detected at load, rejected
- **Operator edits during Previews or later** → new version required
- **Machine reboot** → state persisted, resume prompt
- **Fallback requests C-Cat-forbidden capability** → blocked, falls through
- **Budget exceeded** → halt scene, escalate via urgent contact
- **Execution Monitor fires** → Monitor flags, stage manager raises urgent matter
- **Urgent contact exhausts** → graceful degradation per 11.6
- **Unauthenticated response received** → silently dropped, escalation continues
- **Invalid response format** → one "Invalid format" reply, escalation continues
- **Frequency throttle triggered** → urgent severity suppressed, critical still fires, programme flags
- **Untrusted output fails schema** → scene fails
- **Untrusted text routed into tool-execution method** → blocked
- **Infinite loop in adaptive retries** → hard cap at three retries per variation
- **Director produces invalid YAML** → caught at load validation

## 22. Core loop pseudocode

```python
def run_show(show):
    validate(show)
    compile_against_policy(show, c_cat)
    start_execution_monitor(show)
    open_sqlite_state(show)
    
    show.state = 'running'
    persist(show)
    
    for scene in show.running_order:
        if not check_dependencies(scene, show):
            if any_dep_blocked_no_response(scene, show):
                scene.state = 'cascading-dependency-failure'
                persist(scene)
                continue
            handle_dep_failure(scene)
            continue
        
        inputs = resolve_inputs(scene, show.state.outputs)
        
        scene.state = 'running'
        persist(scene)
        
        result = play_scene(scene, inputs, show.prompt_book, show.sliders)
        
        scene.state = result.status
        if result.outputs:
            validated = validate_outputs(result.outputs, scene)
            show.state.outputs[scene.id] = validated
        persist(scene, show)
        
        check_monitor_signals(show)
        if monitor_flagged_escalation(show):
            if throttle_exceeded(show) and monitor_severity(show) != 'critical':
                set_degrade_mode(show)
            else:
                resolution = raise_urgent_matter(
                    show, 
                    reason=monitor_reason(show),
                    severity=monitor_severity(show)
                )
                if resolution == 'stop':
                    show.state = 'aborted'
                    break
                if resolution == 'exhausted':
                    show.state = 'paused'
                    break
        
        if result.status in ('blocked', 'failed'):
            handle_exit(show, scene, result)
            return
    
    show.state = 'completed' if show.state == 'running' else show.state
    persist(show)
    programme = finalise_programme(show)
    deliver_programme(programme, show.prompt_book.reporting)


def play_scene(scene, inputs, prompt_book, sliders):
    strategies = [scene.principal] + (scene.fallbacks or [])
    
    for i, strategy in enumerate(strategies):
        if not risk_allows(strategy, sliders.risk, c_cat_policy):
            continue
        
        if is_side_effectful(strategy):
            strategy = attach_idempotency_key(strategy)
        
        if strategy.method == 'human-approval':
            resolution = raise_urgent_matter(
                scene, 
                prompt=strategy.prompt,
                deadline=strategy.deadline,
                severity=strategy.severity or 'urgent',
                prompt_book=prompt_book
            )
            if resolution == 'APPROVE':
                return PlayResult(status='played-principal', outputs={'approved': True})
            if resolution == 'REJECT':
                return PlayResult(status='played-principal', outputs={'approved': False})
            if resolution == 'STOP':
                return PlayResult(status='blocked')
            if resolution == 'exhausted':
                return handle_cut(scene)
        
        result = execute_with_retry(strategy, inputs, scene.retry_policy)
        if meets_success(result, strategy.success_when):
            return PlayResult(
                status='played-principal' if i == 0 else f'played-fallback-{i}',
                outputs=result.outputs
            )
        
        if scene.adaptive.allowed and sliders.exploration != 'home':
            for variation in bounded_variations(strategy, scene.adaptive.bounds):
                result = execute_with_retry(variation, inputs, scene.retry_policy)
                if meets_success(result, strategy.success_when):
                    return PlayResult(
                        status='played-adaptive',
                        outputs=result.outputs
                    )
    
    return handle_cut(scene)


def raise_urgent_matter(scene_or_show, prompt, deadline, severity, prompt_book):
    """Pseudocode for urgent contact invocation.
    
    Authentication, cancellation, and DAG-pruning rules from section 11 apply.
    """
    urgent = create_urgent_matter(
        reason=scene_or_show,
        prompt=prompt,
        deadline=deadline,
        severity=severity,
        auth=prompt_book.urgent_contact.auth
    )
    
    if severity == 'critical':
        mode = 'parallel'
    else:
        mode = prompt_book.urgent_contact.mode
    
    fire_chains(urgent, mode, prompt_book.urgent_contact)
    
    while not urgent.resolved and not urgent.exhausted:
        response = poll_for_valid_authenticated_response(urgent)
        if response:
            cancel_all_pending_sends(urgent)
            urgent.resolved = True
            return response.action  # APPROVE, REJECT, STOP
        if all_channels_exhausted(urgent):
            urgent.exhausted = True
            return 'exhausted'
    
    return urgent.resolution
```

No language model is called inside `play_scene` or `raise_urgent_matter`. The Stage Manager does not make decisions with LLMs.

## 23. Integration with other tools

**C-Cat.** Compiles against policy at load time. Runtime consults C-Cat synchronously before any tool call. C-Cat is the house manager.

**Paperclip.** A show can run inside Paperclip. Paperclip owns org chart, budgets, hiring. The Show owns scene structure, fallbacks, rehearsal, programme, urgent contact.

**Agent runtimes** (LangGraph, CrewAI, OpenClaw, Claude Code, Nanobot). Act as scene executors via minimal contract.

**Channel providers.** Pluggable adapters with mandatory authentication support.

## 24. What this spec does not specify

- Wire protocol between stage manager and execution monitor (SQLite is the medium; protocol is evolving)
- Full C-Cat integration API (separate spec)
- Full default mock set for rehearsal
- Director's prompt templates
- Post-Opening workflows
- Multi-user operation
- Cloud deployment
- Voice channel adapters (roadmap)
- Culture-aware language templates per channel (roadmap)

## 25. Attribution

The framework was developed by Mark Cleary in conversation with Claude Opus 4.7. The theatrical grounding, the lifecycle trim to Opening Night, the Exploration slider naming (Home / Edge of the World / Here Be Dragons), the Urgent Contact concept (including the graceful degradation pattern and the register correction from "emergency" to "urgent"), and the insistence throughout that the framework enable rather than prescribe — these come from Mark directly.

The spec was refined across multiple structural review passes and the final version reflects that iterative process.

The Show is part of a larger project by Short+Sweet International to build infrastructure for creative and operational autonomy. S+S itself began in 1998 because writers in Australia had no platform. Operators setting their agents loose today are in a similar position. The Show is one of the frames we're offering.

---

**End of spec. v0.4.1 is locked.**

No more structural changes. The next work happens in code.

Curtain up.
