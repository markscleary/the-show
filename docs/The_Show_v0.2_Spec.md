# The Show: A Performing-Arts Framework for Agent Task Orchestration

**Version:** 0.2  
**Date:** 18 April 2026  
**Status:** Tightened after structural review  
**Author:** Drafted for Mark Cleary

## 1. Positioning

The Show is not a general-purpose workflow engine and not a replacement for agent frameworks such as OpenClaw, LangGraph, CrewAI, or Claude Code. It is a **contract system for safe unattended execution**.

Its purpose is simple:

- let an operator pre-authorise a bounded run
- define explicit fallbacks
- execute against probabilistic agents without constant approval taps
- produce a clear audit trail and post-run report

The Show sits between:
- a **policy layer** that enforces permissions and side-effect controls
- one or more **agent runtimes** that actually perform work

The Show governs **how a task run is structured and completed**. It does not decide who gets hired, how an organisation chart works, or what framework the operator must use.

## 2. Core thesis

Operators running small fleets of AI agents do not mainly need “smarter agents.” They need:

- fewer approval interruptions
- safer unattended execution
- explicit fallback paths
- deterministic data flow between steps
- a readable report at the end

The Show addresses those needs through a bounded execution unit called a **show**.

## 3. Design principles

1. **Bounded runs only.** A show opens and closes. No infinite loops.
2. **Explicit contracts.** Scenes exchange declared inputs and outputs.
3. **Deterministic by default.** The runtime should not silently improvise.
4. **Fallbacks are declared, not invented.**
5. **Policy is separate from strategy.**
6. **All side effects require idempotency protection.**
7. **Untrusted outputs never directly trigger powerful actions.**
8. **Every transition is logged.**

## 4. Core objects

### 4.1 Show
A complete bounded run: metadata, bible, running order, and settings.

### 4.2 Bible
Standing orders specific to this show: goals, escalation rules, reporting preferences, adaptation bounds.  
The bible is **not** the main enforcement layer for security policy.

### 4.3 Policy Layer
External capability and enforcement layer:
- tool allow/deny rules
- secrets handling
- side-effect controls
- sandboxing
- credential brokering

The Show may integrate with Curiosity Cat or a proxy such as an MCP policy interceptor.

### 4.4 Scene
A single unit of work in the running order, with:
- declared inputs
- declared outputs
- one primary strategy
- zero or more fallback strategies
- success criteria
- timeout and retry rules

### 4.5 Stage Manager
The runtime that executes the show.

### 4.6 Programme
The post-run report and machine-readable execution log.

## 5. Vocabulary

| Term | Meaning |
|---|---|
| Show | A bounded execution unit |
| Bible | Standing orders for this show |
| Running order | Ordered list of scenes |
| Scene | One unit of work |
| Principal | Primary strategy for a scene |
| Fallback | Backup strategy for a scene |
| Cut | Skip or stop rule |
| Stage manager | Runtime that executes the show |
| Rehearsal | Dry run with side effects mocked |
| Programme | Output report after the show |
| Risk slider | Strictness of allowed capabilities |
| Improvisation slider | Amount of bounded adaptation allowed |

## 6. Architectural correction from v0.1

v0.1 overloaded the bible and left scene-to-scene data passing ambiguous. v0.2 makes three hard changes:

1. **Policy is separated from the bible**
2. **Inter-scene data passing is explicit**
3. **“Notes” is removed as a free-form rewriting layer**

Instead of free-form revision, v0.2 supports **bounded adaptation** within operator-declared limits.

## 7. Show structure (YAML)

```yaml
show:
  id: outreach-enrichment-001
  title: "Outreach enrichment run"
  rehearsal: false
  max-duration-seconds: 7200
  max-scenes: 20

  sliders:
    risk: housecat        # housecat | streetcat | alleycat
    improvisation: script # script | standard | jazz

  stage-manager:
    mode: deterministic   # deterministic | assisted

  bible:
    objective: "Load targets, enrich contacts, write clean output, report results"
    escalation:
      blocked-scenes-consecutive: 2
      budget-consumed-percentage: 75
      unexpected-credential-request: true
      any-scene-duration-over-seconds: 900
    reporting:
      programme-format: [markdown, json]
      deliver-to: [disk]
    adaptation-bounds:
      batch-size:
        min: 2
        max: 20
      retry-attempts:
        min: 1
        max: 3

  running-order:
    - scene: load_targets
      title: "Load outreach targets"

      outputs:
        contacts:
          type: list
          schema: contact[]

      principal:
        method: tool-call
        agent: deep-dive
        action: read-csv
        params:
          path: /Users/mark/S+S/outreach/targets.csv

      fallbacks:
        - label: backup-file
          method: tool-call
          agent: deep-dive
          action: read-csv
          params:
            path: /Users/mark/S+S/outreach/targets-backup.csv

      success-when:
        schema: contact[]
        min-length: 50

      retry-policy:
        max-attempts: 2
        backoff: exponential
        base-delay-seconds: 1
        jitter: true
        retriable-errors: [rate-limit, timeout, io-error]

      timeout-seconds: 60

      cut:
        condition: escalate
        reason: "Cannot proceed without contacts"

    - scene: enrich_contacts
      title: "Enrich contacts"
      depends-on: [load_targets]

      inputs:
        contacts: from(load_targets.contacts)

      outputs:
        enriched_contacts:
          type: list
          schema: enriched_contact[]

      principal:
        method: sub-agent
        agent: deep-dive
        brief: |
          Enrich each contact with current title, website, and LinkedIn URL.
        params:
          batch-size: 10

      fallbacks:
        - label: alternative-agent
          method: sub-agent
          agent: quin
          brief: |
            Enrich each contact with current title, website, and LinkedIn URL.
          params:
            batch-size: 5

      adaptive:
        allowed: true
        bounds:
          batch-size:
            min: 3
            max: 10

      success-when:
        schema: enriched_contact[]
        min-length: 30

      retry-policy:
        max-attempts: 3
        backoff: exponential
        base-delay-seconds: 1
        jitter: true
        retriable-errors: [rate-limit, timeout, 5xx]

      timeout-seconds: 600

      cut:
        condition: continue-with-partial
        minimum-acceptable: 30
```

## 8. Explicit data contracts

This is mandatory.

Scenes must declare:
- **outputs**
- **inputs**
- the source binding for each input

No shared hidden scratchpad is relied on for execution correctness.

### 8.1 Why
This enables:
- deterministic replay
- schema validation
- partial output handling
- safer parallel execution
- observability
- lower prompt-injection risk

### 8.2 Rules
- a scene may only reference outputs from completed dependency scenes
- all input bindings must be resolvable at load time
- missing inputs cause scene validation failure before execution

## 9. Fallback model

v0.1 distinguished between understudy and swing. v0.2 collapses these into a single concept: **fallbacks**.

Reason:
- easier for operators to write
- easier to debug
- avoids ambiguous theatre-to-software translation

### 9.1 Scene fallback order
1. principal
2. fallback 1
3. fallback 2
4. bounded adaptation if allowed
5. cut rule

## 10. Bounded adaptation

v0.1 used “notes” as a free-form revision layer. v0.2 removes that.

Instead, a scene may include:

```yaml
adaptive:
  allowed: true
  bounds:
    batch-size:
      min: 3
      max: 10
```

The stage manager may vary only explicitly permitted parameters inside declared bounds.

### 10.1 Why
This preserves:
- limited flexibility
- deterministic boundaries
- operator trust

It avoids:
- silent task rewriting
- meta-agent drift
- hidden strategy changes

## 11. Sliders

### 11.1 Risk slider

- **Housecat**: local-first, explicit allow-list only, side effects blocked unless scene explicitly permitted by policy layer
- **Streetcat**: external services allowed per policy, bounded side effects
- **Alley Cat**: full capability use within policy layer and show bounds

### 11.2 Improvisation slider

- **Script**: execute declared strategies only; no adaptation
- **Standard**: bounded adaptation allowed where declared
- **Jazz**: bounded adaptation plus permitted reordering of scenes that have no unresolved dependencies

Important: even Jazz does **not** allow unconstrained free-form rewriting.

## 12. Stage manager modes

The stage manager may run in one of two modes:

- **deterministic**: no model calls by the stage manager itself
- **assisted**: stage manager may use a model for bounded planning or explanation tasks, and every such use is logged and billed

This avoids the hidden-meta-agent problem.

## 13. Trust model

Every scene should declare trust for external inputs where relevant.

```yaml
input-trust:
  level: trusted | untrusted
```

If `untrusted`:
- outputs must be schema-validated
- direct execution based on returned content is disallowed unless explicitly mediated
- tool access may be reduced by policy

This is the minimum prompt-injection defence line.

## 14. Retry, idempotency, and circuit breakers

### 14.1 Retry
Retries are handled per scene using explicit retry policy.

### 14.2 Idempotency
Any side-effectful action must have framework-enforced idempotency.

The operator should not be responsible for inventing this each time.

### 14.3 Circuit breakers
Repeated failures within a short window trigger cooldown and escalation.

## 15. State machine

### 15.1 Show states
- planned
- rehearsing
- running
- paused
- completed
- aborted

`reviewed` is removed from the core state machine. It can be derived from operator interaction.

### 15.2 Scene states
- queued
- running
- played-principal
- played-fallback
- played-adaptive
- played-partial
- cut
- blocked
- failed

## 16. Rehearsal mode

A rehearsal:
- executes the real control flow
- allows model calls unless separately disabled
- mocks side-effectful external actions
- produces a rehearsal programme

Promotion to live run must re-run from scratch.

## 17. Programme

The programme must include:

### Title summary
- show title
- start and end time
- duration
- outcome summary
- total cost
- operator-attention items

### Scene summary
- scene status
- principal or fallback used
- output summary
- time and cost
- warning flags

### Machine log
Companion structured JSON log:
- exact transitions
- retries
- idempotency keys
- policy denials
- adaptation actions
- input and output bindings

## 18. Observability during run

Operators should not have to wait until the end to know what is happening.

v0.2 adds the requirement for a **peek view**:
- current show state
- current scene
- completed scenes
- blocked scenes
- retry count
- accumulated spend
- pending escalations

This can be CLI-first in v1.

## 19. Execution monitor

The Show should include or integrate with an external execution monitor.

Responsibilities:
- detect oscillation
- detect no-progress runs
- detect retry storms
- detect repeated policy denials
- detect budget burn anomalies

The monitor should be external to the stage manager where possible.

## 20. Failure handling

v0.2 explicitly handles:
- dependency failure
- missing inputs
- scene timeout
- stage manager crash
- reboot recovery
- policy denial
- side-effect retry without idempotency
- retry storm
- repeated no-progress transitions
- malformed output against schema
- untrusted output attempting capability escalation

## 21. Integration positioning

### 21.1 With Curiosity Cat
Curiosity Cat provides policy and risk controls.  
The Show provides bounded execution, explicit fallback structure, and the programme.

### 21.2 With Paperclip
Paperclip handles organisation, budgets, agent allocation, and audit context.  
The Show handles scene execution, fallback strategy, rehearsal, and reporting.

### 21.3 With LangGraph, CrewAI, OpenClaw, Claude Code
These may act as agent runtimes or scene executors.  
The Show wraps them with execution discipline.

## 22. What is deliberately out of scope for v0.2

- free-form “director mode” that generates running orders from prose
- vision-click/computer-use orchestration
- collaborative editing of live shows
- rich UI beyond CLI and file-based reports
- deep marketplace integrations

## 23. Minimum v1 deliverable

A valid v1 needs:
1. YAML parser and schema validation
2. explicit input/output binding
3. scene execution with principal + fallbacks
4. retry policy
5. idempotency enforcement hooks
6. persisted state machine
7. rehearsal mode
8. programme generation
9. CLI peek view

## 24. Final judgment

The Show should be built as:
- a thin, disciplined execution contract
- not a sprawling orchestration platform
- not a magical autonomous director
- not a replacement for everything else

Its value comes from making unattended agent work **bounded, inspectable, and recoverable**.
