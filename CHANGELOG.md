# Changelog

## v1.0.0 — 23 April 2026

First tagged release. The Show runs programmes. Programmes are sequences of scenes with dependencies. Scenes can request human approval via signed-link urgent contact across Telegram, email, SMS, or WhatsApp. The Stage Manager persists state through SQLAlchemy Core with two-phase commit crash-seam recovery. The Execution Monitor watches for stalls, retry-storms, cost-runaways, and policy-denials. Rehearsal mode lets programmes dry-run without burning tokens or hitting real channels.

v1.0.0 was built by running The Show on itself — scenes 1-7 of `examples/build-v1.0-release.yaml` produced the SQLAlchemy migration, dependency skip semantics, v0.4.2 patch completion, adapter contract formalisation, the Dubai Gala example programme, and the operator guide. The programme that built The Show is in the repo alongside the show it built.

231 passing tests.

Included:
- SQLAlchemy Core + Alembic state persistence
- Dependency-aware scene execution with skip propagation
- Must-complete terminal semantics
- Formalised AbstractChannelAdapter protocol (Telegram, email, Gemini)
- Rehearsal mode — programmes run against canned responses, no real channels, no token spend
- Approval gates default to 7-day timeouts with sub-24-hour declarations flagged as warnings
- Two example programmes — Curiosity Cat launch announcement, Dubai Gala night-of-show
- Operator guide
