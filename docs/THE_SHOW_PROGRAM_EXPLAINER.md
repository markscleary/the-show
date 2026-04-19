---

# The Show

*An orchestration framework for structured agent work with human red-line approval.*

**S+S Agential — Program Explainer — 19 April 2026**

## Origin

The Show was born from a practical problem. Short+Sweet International runs six AI agents on a Mac Mini in Thirroul — Quin, Deep Dive, Front Page, Production Manager, Greg and Principal. Each agent is competent at its own work. The ecosystem they sit inside is more complex than any single agent can handle alone.

Curiosity Cat, the first S+S product to go public, will land on Reddit and Hacker News. The launch needs first-response triage — someone reading early comments, categorising them, drafting replies in Mark's voice, flagging anything that needs a human decision, and packaging the whole thing as a briefing before the operator wakes up. No single agent does all of that. The work is a sequence — gather, research, draft, approve, compile, deliver. Each step has inputs from the one before. Each step can fail in ways the next step needs to know about. Some steps need a human to say yes or no before the rest can proceed.

Every agent framework on the market gets this wrong in one of two ways. Frameworks that assume full autonomy run brilliantly until they do something expensive or embarrassing, and by then it is too late to stop them. Frameworks that require human approval on every step exhaust the operator within an afternoon. The middle path — agent drives, human approves red-lines, everything else runs — did not exist in a form we could use.

The Show is that middle path. Built over 26 hours on 18 April 2026. Spec locked at v0.4.1. Runtime passing 160 tests. First rehearsal clean. Named for the theatrical metaphor that made it possible to design.

## What it is

The Show runs programmes. A programme is a YAML file declaring a sequence of scenes. The Stage Manager executes scenes in dependency order, persists state to SQLite with two-phase commit, routes urgent matters to the operator through Telegram, email, SMS or WhatsApp, and watches for stalls, retry-storms, cost-runaways and policy-denials through the Execution Monitor.

Every theatrical metaphor is load-bearing. The programme is the show. Each scene is a task. The Stage Manager is the runtime. The Execution Monitor is stage management — the person in the booth watching for things that should not be happening. Urgent Contact is the house manager who finds the director in the audience when something genuinely needs a human decision. The operator is the director. The metaphor is not decorative. It maps directly to how the system actually works, and it earns its place because it gives everyone — Mark, the agents, the next instance reading this — a shared mental model of what is happening and why.

### The anatomy of a scene

Each scene in a programme declares:

- A task — the agent work to be performed
- A schema — what the output must look like when the scene succeeds
- A depends-on clause — which earlier scenes must complete before this one starts
- A must-complete flag — whether the programme can proceed if this scene fails to reach a terminal state
- A human-approval flag — whether the operator must review and approve the output before downstream scenes see it
- An urgent-contact flag — whether this scene can interrupt the operator mid-execution when something goes wrong

This small set of flags carries most of the safety. A scene marked must-complete blocks the programme if it cannot finish. A scene marked human-approval pauses and routes a red-line request to the operator. A scene marked urgent-contact can reach the operator through any of four channels, with signed response links and authentication on the reply. Scenes without any of these flags run quietly and never bother anyone.

### What the Stage Manager does

The Stage Manager is the deterministic core. It reads the programme, builds the dependency graph, runs each scene in order, persists state at every transition, and handles failures by the rules declared in the programme itself. It does not improvise. It does not interpret. If the programme says retry three times, it retries three times. If the programme says escalate to urgent contact on the second failure, that is what happens.

State is persisted to SQLite using two-phase commit. Every side effect — a message sent, an API called, a file written — gets an idempotency key written before the side effect fires. On crash recovery, the Stage Manager scans for keys in preparing-side-effect state and runs verification probes: did this actually happen? Route accordingly. This discipline exists because the alternative is double-sending, double-charging, or lying to the operator about what the system did while it was alive.

### What the Execution Monitor does

The Execution Monitor runs alongside the Stage Manager with its own polling loop. It watches for four hard signals — stalls, retry-storms, cost-runaways and policy-denials — using deterministic arithmetic on the event log. When a hard signal fires, it can signal a cancellation event that interrupts whatever scene is currently executing, even if the scene is mid-flight on an LLM network call.

The Monitor also uses Qwen 3 14B locally for one specific thing — oscillation detection. Pattern recognition is what language models are good at, and oscillation (the system bouncing between two states without making progress) is a pattern. The Monitor is still deterministic where it matters. The ML-assisted detection is an optional layer that only fires when hard signals have not already handled the case.

### What Urgent Contact does

Urgent Contact is how The Show reaches a human. It works through four channels: Telegram (the default, lowest latency), email (with signed response links), SMS (for when email is too slow), and WhatsApp (pending Meta onboarding). Every urgent request includes a severity level, a throttle to prevent spam, and strict parsing of the reply — only declared response formats are accepted, authentication tokens are required, and malformed replies trigger a follow-up clarification rather than being silently ignored.

If the operator does not respond within the configured window, the scene either continues in graceful-degradation mode (if the programme declares that as the fallback) or aborts with the partial state preserved. The operator's time is treated as the scarce resource. The Show wakes the operator when it genuinely needs to, and only then.

## Current status

Spec v0.4.1 was locked on 18 April 2026. Six structural review passes produced the locked version. A v0.4.2 patch document was drafted on 19 April covering four ship-blocker fixes: crash-seam two-phase commit, mid-flight cancellation tokens, must-complete terminal-state semantics, and programme-delivery state separation.

The runtime has 160 passing tests. Five build sessions committed. Real channel adapters in place for Telegram, email and SMS. WhatsApp skeleton pending Meta onboarding. The first rehearsal — Session 6, producing the launch-response briefing document for the Curiosity Cat launch — ran clean. Two gaps remain before a live production run: executor.py currently uses MockChannel rather than loading real adapters, and sub-agent stubs return synthetic content instead of real model output. Both are build-track items, not spec issues.

The Show is private infrastructure. It is not currently a commercial product. The v0.5 roadmap contemplates commercial viability — privacy and consent model for urgent messages, multi-operator teams, telemetry boundaries, marketplace story, cost model for hosted SaaS — but none of that is imminent. The Show earns its keep running S+S Agential. Commercial viability comes later if the case proves itself internally.

## Ecosystem connections

The Show sits underneath the rest of S+S Agential. Every other program in the division will run on it:

- S+S Executable — the first programme that will run on The Show at scale is a competitive creative challenge. The Show orchestrates the briefing, the creation window, the judging, the Quine issuance and the operator notifications.
- The Quine — the Ledger is updated through scenes in The Show. GENESIS-001, the first self-referential Quine, will be written by a Show programme.
- The Green Room — task dispatch between operators posting work and agents available to take it runs through The Show. The work lifecycle (posted, claimed, in progress, submitted, judged, paid) is a Show programme with urgent contact at the judge step.
- Chimera — when Chimera launches, its 60-minute creation sprints are Show programmes with timers, audience-influence scenes, and judge-notification urgent contacts.

Beyond S+S Agential, The Show will also run operations inside the broader ecosystem:

- Festival operations — the Curiosity Cat launch briefing is the first example. Any recurring operations work that follows a sequence of agent tasks with human approval at the red-lines is a candidate.
- Corporate Services — Myth Building engagements involve sequences of research, interview, synthesis, draft, review, finalise. Show programmes make the repeated choreography auditable and recoverable.
- Education — AI Driver Training course generation, assessment scoring, and report delivery are naturally programme-shaped.

## Strategic position

The Show is one of three tools S+S Agential has built from the same underlying recognition: the operator's attention is the scarce resource. The Show conserves attention during task execution — the operator is not asked for permission on every step, only on the ones that matter. A separate methodology conserves attention during spec review. A machine reflection file conserves attention during session onboarding. Three instruments, one design philosophy.

The competitive landscape is empty. Agent orchestration frameworks exist — LangGraph, CrewAI, AutoGen — but none solve the red-line approval problem as a first-class concern. They assume the human is either fully in the loop (every step) or fully out (autonomous agent). The Show occupies the middle ground where real operational work lives.

S+S is uniquely placed to build this because it has operated for 25 years at the intersection of creative direction and operational execution. Festivals are orchestrated work sequences with human red-line approval at critical points. Casting decisions, venue contracts, gala final judging — none of these run autonomously. The theatrical metaphor in The Show is not a stylistic choice. It is a direct transcription of how S+S already operates, applied to agents.

## Revenue model

Pre-revenue. The Show currently earns its keep by running S+S Agential operations internally. It replaces work that would otherwise require bespoke scripting or manual operator attention on every step.

If commercialised under the v0.5 roadmap, plausible models include hosted SaaS for agent teams (per-operator or per-programme pricing), licensing to AI agencies and small teams building agent products, and integration into larger platforms that want the red-line approval layer without building it themselves. None of these are active revenue paths. All are contingent on finishing the v0.5 work and proving commercial viability.

## Key people

- Mark Cleary — operator, spec author, architect of the theatrical metaphor.
- Claude (Opus 4.7) — primary drafter and implementer. Each session has been a single instance, with handover documents and machine reflection files providing continuity.
- Quin — the S+S creative lead agent. Quin's role in The Show is to produce the GENESIS-001 Quine by running the first full programme end-to-end.
- Front Page — the S+S publicity agent. First to run a Show programme in anger: the Curiosity Cat launch-response briefing.

---

*— The Show / S+S Agential / 19 April 2026 —*

---
