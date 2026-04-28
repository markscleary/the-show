# Examples

These are real programmes that run on The Show. They start small and grow more involved. If you're new to the runtime, work through them in order — each one introduces something the previous didn't.

Every programme here can be validated with `the-show validate <programme>.yaml` and dry-run with `SHOW_REHEARSAL=1 the-show run <programme>.yaml` before running live.

## hello.yaml

The smallest possible programme. One scene, no dependencies, no LLM, no channels. Exists to prove the runtime works on a fresh install.

```
the-show validate hello.yaml
the-show run hello.yaml
```

What it demonstrates: scene execution, state DB creation, programme markdown generation. Five seconds end to end.

## curiosity-cat-launch-announcement.yaml

The first real programme that ran on The Show, dispatched April 2026 to launch the Curiosity Cat security framework across S+S Agential.

What it demonstrates: multi-language content generation (English, Arabic, Mandarin, Hindi, Tamil — each in its own scene), human approval gates, sub-agent orchestration via Gemini, dispatch to a real channel (Telegram).

Real-world note: this programme generated the launch announcement copy that actually went out. The runtime did the work; the operator (Mark) approved at the gates; the dispatch was real. This is what creative work running on a runtime looks like.

## build-v1.0-release.yaml

The programme that built The Show's v1.0 release. Nine scenes, real code commits, real human approval gates with eight-hour timeouts, real test runs, real git tag at the end.

What it demonstrates: long-running multi-scene programmes, dependency chains, sub-agent dispatch to Claude Code for actual code work, must-complete scene semantics, crash seam recovery (one scene timed out at 4am because of a bad default — the runtime recovered, the operator fixed the default, the build continued).

This is the programme that gives the project its dog-food story. The runtime that built itself is real. It's in the repo alongside the runtime it built.

## dubai-gala-night-of-show.yaml

A theatrical example programme for orchestrating a festival gala final. Loads the running order, generates host introductions, drafts sponsor acknowledgements, drafts post-show announcements, dispatches via approval gates to the festival director.

What it demonstrates: a programme only a theatre person would think to build. The kind of work The Show is actually for — coordinating a live event with creative content generation and human-approval checkpoints.

This programme was rehearsed but not run live for v1.0 — it's in the repo as a reference for how a real-world S+S programme might look. The actual Dubai gala in May 2026 may run this programme or an evolution of it. The rehearsal log lives in `outputs/dubai-gala-rehearsal.log`.

## What's not here yet

Examples that demonstrate features The Show has but no programme above exercises end-to-end:

- Multi-operator coordination across different channels (one operator on Telegram, another on email)
- External-data integration (fetching from APIs or filesystems before generating content)
- Loop and retry behaviour (scenes that retry on validation failure with bounded iteration)

These are coming. If you've got a use case that would make a good example, open an issue or a pull request.

## How to write your own

Start by copying `hello.yaml` and adding one scene at a time. Validate after each addition. Rehearse in dry-run mode before running live. The operator guide walks through every concept the runtime supports; the YAML schema documents every field.

The programmes here should feel familiar to anyone who's worked in a venue. If something doesn't, that's a documentation problem — let us know.
