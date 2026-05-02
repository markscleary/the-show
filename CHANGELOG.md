# Changelog

## v1.1.1 — 3 May 2026

Per-scene channel routing — patch fix for a documented behaviour that the v1.1.0 runtime silently dropped.

- `principal.channels` and `principal.to` on a human-approval scene now actually route the urgent matter to a subset of `urgent-contact.contacts`. Both fields are optional; programmes without them fall back to the v1.1.0 fanout, so this release is backward compatible.
- Loader now parses both fields onto `Strategy`, the dispatcher filters contacts before creating send rows, and the executor forwards them through. Bare-string `to:` is normalised to a list internally.
- `the-show validate` cross-references `principal.channels` and `principal.to` against `urgent-contact.contacts` and fails at load time if a scene refers to a channel or handle no contact provides.
- `examples/festival-heat-coordination.yaml` updated to use the new fields — director scene routes to Telegram, technical scene routes to email.
- 14 new tests in `test_per_scene_routing.py`. 245 passing tests in total.

## v1.1.0 — 25 April 2026

Proper packaging, PyPI publication, install path fixed.

- `pyproject.toml` (PEP 621, hatchling backend) – the v1.0 install path routed around missing packaging metadata with `uv pip install -r requirements.txt`. v1.1 ships with a real package, a `the-show` console script, and `pip install the-show` works.
- Source restructured into a proper `the_show/` package – top-level modules and the `monitor` and `urgent_contact` sub-packages now live under `the_show/`. Imports across source and tests rewritten accordingly. Tests still 231 passing.
- Published to PyPI as `the-show`. `pip install the-show` from any Python 3.11+ environment.
- `--version` flag added to the CLI – `the-show --version` returns the installed version.
- `sqlalchemy>=2.0,<3.0` declared as a direct dependency – previously pulled in transitively via alembic.
- QUICKSTART and README install sections updated to the standard `pip install` path. Source path retained for contributors.

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
