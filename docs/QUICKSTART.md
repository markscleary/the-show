# Quickstart

In 5 minutes you'll install The Show, run a small programme that writes a file and confirms it ran, and see the result logged in the SQLite state store. From there you can write your own programmes or read the operator guide.

---

## Prerequisites

- Python 3.11 or later
- [uv](https://github.com/astral-sh/uv) — the fastest way to manage the virtualenv (`pip install uv` or `brew install uv`)
- Git

No LLM keys. No Telegram. No email account. The quickstart programme uses a built-in stub adapter — nothing leaves your machine.

---

## Install

There's no PyPI package yet. Clone the repo and install dependencies into a local virtualenv:

```bash
git clone https://github.com/markscleary/the-show.git
cd the-show
uv venv --python 3.11 .venv
uv pip install -r requirements.txt
```

Verify it's working:

```bash
uv run python cli.py --help
```

You should see the list of commands: `validate`, `run`, `peek`, `programme`, `events`.

---

## The hello programme

Create a file called `examples/hello.yaml` — or use the one already in the repo:

```yaml
show:
  id: hello-001
  title: "Hello, The Show"
  max-duration-seconds: 60
  max-scenes: 5

  sliders:
    risk: housecat
    improvisation: script

  bible:
    objective: "Write a greeting to a file and confirm it was written"

  running-order:

    - scene: write_greeting
      title: "Write greeting"
      outputs:
        path: {type: string, schema: string}
      principal:
        method: tool-call
        agent: stage-manager
        action: write-json
        params:
          path: /tmp/hello-from-the-show.json
      success-when:
        schema: string
      cut:
        condition: continue
        reason: "Write failed — continuing anyway"
```

One scene. No dependencies. No LLM call. No approval gate. It writes a path string to the state store and exits.

---

## Run it

```bash
uv run python cli.py validate examples/hello.yaml
uv run python cli.py run examples/hello.yaml
```

Expected output:

```
VALID: hello-001 - Hello, The Show
Scenes: 1

[INFO] Basic schema check for 'string' — OK

Show finished: completed
Total cost: $0.0000
State DB: /Users/<you>/.the-show/state/hello-001.db
```

The show status will show as `delivered` — meaning the programme ran and the state was persisted cleanly.

---

## See what happened

```bash
uv run python cli.py peek hello-001
```

Output:

```
Show: Hello, The Show (hello-001)
Status: delivered
Total cost: $0.0000
Scenes (1):
  write_greeting: played-principal — principal
```

To query the state directly:

```bash
sqlite3 ~/.the-show/state/hello-001.db \
  "SELECT show_id, title, status FROM show_state;"
```

Output:

```
hello-001|Hello, The Show|delivered
```

Every show gets its own SQLite database at `~/.the-show/state/<show-id>.db`. The events table records every scene transition, cost and timing. The programme report (markdown and JSON) writes to `~/.the-show/state/<show-id>/programme.md`.

---

## Where next

- Read [`docs/OPERATOR_GUIDE.md`](OPERATOR_GUIDE.md) for the full picture — scenes, the Stage Manager, approval gates, the Urgent Contact system.
- Look at [`examples/dubai-gala-night-of-show.yaml`](../examples/dubai-gala-night-of-show.yaml) for a real programme that ran against live agents.
- To try a programme with a human approval gate, configure a Telegram bot — `URGENT_TELEGRAM_BOT_TOKEN` and a user ID in `.env`. The channel configuration section in the README covers the setup.
