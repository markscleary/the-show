# The Show — Spec v0.4.2 Patch
*Patch to v0.4.1 LOCKED — 19 April 2026*

## Purpose
Four ship-blocker fixes identified after structural review of v0.4.1. These are the minimum changes required to move The Show from "shippable as a private build" to "commercially defensible." All four affect cross-process state consistency, mid-flight responsiveness, lifecycle terminal-state semantics, and delivery state separation.

This is a patch, not a rewrite. v0.4.1 LOCKED remains the base document. The changes below apply on top of it.

## Patch 1 — Crash-seam and two-phase commit consistency
[Priority: ship-blocker]

**Problem.** State transitions that span processes (Stage Manager → Monitor, Stage Manager → Urgent Contact, Stage Manager → Programme Delivery) have no explicit recovery semantics when a process dies mid-transition. Idempotency keys are currently written AFTER the side effect fires. On crash between the side effect and the key write, the rebooted system has no way to distinguish "never tried" from "tried and succeeded" — leading to potential double-send, double-charge, or loss of truth about what happened.

**Fix.**
- Every state transition that spans processes MUST use two-phase commit:
  1. Write the idempotency key to SQLite with state `preparing_side_effect` BEFORE the network call fires
  2. Fire the side effect
  3. On success, update the key to state `completed` with the response artefact
  4. On failure, update to `failed` with error context
- On startup, every process MUST scan for keys in state `preparing_side_effect` older than a configurable grace window (default 60s) and run a verification probe: did the side effect actually happen? Route accordingly.
- Specify recovery rules for each cross-process transition explicitly — not as implementation guidance but as normative spec.

## Patch 2 — Mid-flight monitor interrupts with cancellation semantics
[Priority: ship-blocker]

**Problem.** The Execution Monitor currently fires between scenes. A cost-runaway detected two minutes into a fifteen-minute scene is useless if the Monitor can only signal at scene boundaries. The spec implies async interruption is the intent but never specifies the mechanism.

**Fix.**
- `play_scene` MUST accept a cancellation token as a parameter.
- The Stage Manager MUST pass a cancellation event into every scene execution.
- The Monitor MUST be able to signal the cancellation event asynchronously from its own polling loop.
- The scene's main execution path (including any LLM network calls) MUST be wrapped in an async context that checks the cancellation token between awaits.
- Specify the mechanism concretely: Python `asyncio.Event` + `asyncio.wait_for` wrapping network calls, or equivalent in other runtimes.
- On cancellation, the scene MUST persist its partial state before returning, so recovery is possible.

## Patch 3 — Must-complete / paused terminal-state semantics
[Priority: ship-blocker]

**Problem.** v0.4.1 contains a contradiction: scenes marked `must_complete: true` are required to complete, but the spec also permits `paused` as a legitimate scene state (awaiting operator input). A must-complete scene that reaches paused violates its own contract.

**Fix.**
- Redefine `must_complete` as: "must reach a declared terminal state."
- Enumerate terminal states explicitly: `completed`, `paused_awaiting_operator`, `aborted_by_operator`, `exhausted_degraded`.
- `paused_awaiting_operator` is a first-class terminal state with its own recovery semantics — not a hidden contract violation.
- Specify, for each terminal state: what triggers it, what downstream scenes do (block, proceed, branch), and what the programme delivery step reports.

## Patch 4 — Programme / report delivery state separation
[Priority: ship-blocker]

**Problem.** v0.4.1 treats "all scenes completed" as equivalent to "programme completed." But a scene finishing and a report being delivered to its recipients are separate events. A crash between scene completion and report delivery leaves the system claiming the programme is done when the operator has received nothing.

**Fix.**
- Introduce a new lifecycle stage: `delivering`, between scene completion and `completed`.
- Programme state MUST persist both execution state (`scenes_complete`) and delivery state (`delivered`, `delivery_failed`, `delivery_pending`) independently.
- A programme is only `completed` when delivery has been confirmed by the channel adapter.
- Delivery failures MUST trigger a retry with backoff (configurable) and, after exhaustion, route to Urgent Contact.

## What is NOT in this patch

The following structural observations from the second-round review are deferred to v0.5 because they are refactoring work, not fixes:

- **Decision as a first-class abstraction.** Currently "the system needs a human to decide" appears as human-approval scenes, Monitor escalation, and cut:escalate with different behaviour each time. A unified Decision concept would collapse duplication.
- **DAG semantics formalisation.** The implicit DAG semantics work for current cases but are under-specified against the load they're bearing.

Commercial gaps also deferred to v0.5 (product-shape work, not technical debt):
- Privacy / consent model for Urgent Contact messages
- Multi-operator teams
- Telemetry boundaries
- Marketplace story
- Cost model for hosted SaaS

## Implementation order

Patch 1 (crash-seam) MUST land first. If state consistency is wrong, everything downstream is built on sand. Patches 2, 3, 4 can land in any order after Patch 1 is stable.
