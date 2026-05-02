# The Show — Operator Guide

The Short+Sweet Dubai selection panel runs sixty submissions through a five-stage process: initial read, dramaturgical notes, director shortlist, producer approval, final offer. In 2024, an agent did the first three stages unattended overnight. By 3am it had stalled on a rate limit, retried itself into a loop, and by morning had sent the same draft notes to seventeen plays it had only half-read. No one knew until the director shortlist came back nonsensical. The agent had no Stage Manager. There was no one watching from the booth, no crash seam, no way for the system to reach the operator when it first went wrong. There was only an agent doing its best with no programme to follow and no one to call.

The Show is what that night needed. It is a Stage Manager for unattended agent work — a runtime that reads a programme, calls each cue in order, saves state after every scene, and reaches you when the show genuinely needs you. Not on every step. Only on the ones that matter.

## The Cast

Every production has a Director — the person who designs the programme. In The Show, the Director is whoever writes the YAML. They decide the running order, the fallback strategies, the red-line conditions, the budget, the escalation rules. The Director does not run the show. They hand the programme to the Stage Manager and go home.

The Stage Manager is the runtime — `executor.py`. It reads the programme the Director wrote, builds the dependency graph, and calls each scene in sequence. It persists state to SQLite after every transition. It handles failures by the rules the Director declared. It does not improvise. If the programme says retry three times with exponential backoff, it retries three times with exponential backoff. If it says escalate on consecutive failures, it escalates. The Stage Manager is deterministic because that is what makes it trustworthy. You can read the programme and know exactly what will happen.

The House Manager watches from the wings — that is the monitor, a separate process that runs alongside the Stage Manager. It watches the event log for four hard signals: cost-runaways, stalls, retry-storms and policy-denials. It uses arithmetic, not inference. When a signal fires, the House Manager can interrupt a scene mid-flight and raise an urgent matter. The operator never configures the House Manager directly — they configure the escalation rules in the bible, and the House Manager acts accordingly.

The cast of a programme is made up of scenes. Each scene is a discrete unit of work with a single declared output. Scenes that call sub-agents — sending a brief to Gemini, Claude or another model — are the most common type. A scene that asks a human for a decision is an approval gate: it pauses the show, contacts the operator, and waits. Every scene declares what success looks like, what to do on failure, and which earlier scenes it depends on. The dependency declarations form a graph — the Stage Manager resolves that graph so that parallel scenes run in the right order and downstream scenes only start when their inputs are ready.

## Writing Your Programme

A programme is a YAML file. It starts with a `show` block containing identity and settings, then a `bible` declaring the objective and escalation rules, then a `running-order` listing every scene in sequence.

```yaml
show:
  id: my-programme-001
  title: "A descriptive title"
  max-duration-seconds: 3600
  max-scenes: 20

  sliders:
    risk: housecat        # housecat | tiger
    improvisation: script # script | standard | jazz

  bible:
    objective: "What this programme is trying to accomplish"
    escalation:
      blocked-scenes-consecutive: 2
      budget-consumed-percentage: 80

  urgent-contact:
    mode: sequential
    max-per-show: 5
    contacts:
      - role: operator
        channel: telegram
        handle: "your-telegram-id"
        auth: channel-native

  running-order:
    - scene: scene_one
      title: "First scene"
      outputs:
        result:
          type: object
      principal:
        method: sub-agent
        agent: gemini
        brief: "What you want the agent to do"
        params:
          model: gemini-flash
      success-when:
        schema: object
      cut:
        condition: escalate
        reason: "Why this scene cannot be skipped"
```

The `sliders` block sets two dials. `risk` controls how conservative the Stage Manager is — `housecat` treats every unexpected outcome as a reason to pause, `tiger` lets it push through ambiguity. `improvisation` controls whether the runtime adapts strategy parameters when a scene struggles — `script` means no adaptation, `standard` allows measured adjustment, `jazz` gives the Stage Manager latitude to halve batch sizes and try variations.

The `bible` is the Prompt Book — the Director's standing instructions. The `objective` is a plain-language statement of what the programme exists to accomplish. The `escalation` block sets the thresholds at which the House Manager wakes the operator: how many consecutive blocked scenes trigger an interrupt, what percentage of budget consumed triggers a warning.

The `running-order` is the heart of the programme. Each scene needs a unique `scene` ID, a `title`, at least one declared output, a `principal` strategy (the primary method), and a `cut` rule declaring what happens if all strategies fail. Scenes that use outputs from earlier scenes declare `depends-on` and `inputs` — the Stage Manager resolves these bindings automatically.

## Running the Show

Starting a show is one command.

```
python3 cli.py run examples/my-programme.yaml
```

The Stage Manager validates the YAML, initialises state, launches the monitor, and begins executing scenes. If the show has run before and was interrupted, the CLI asks whether to resume from the last clean scene or archive the previous run and start fresh. You choose. The show does the rest.

While the show is running, `peek` is the Stage Manager's callsheet — a live snapshot of every scene's status, the current total cost, and any urgent matters raised.

```
python3 cli.py peek my-programme-001
```

It shows each scene ID with its current status — `played-principal`, `running`, `skipped`, `blocked` — and the last five events from the log. If the show has raised urgent matters, they appear with their severity and resolution status. `peek` is what you run when you want to know what is happening without stopping anything.

After the show completes, `programme` generates the full programme report — a structured record of every scene played, every strategy selected, cost and timing, and final status.

```
python3 cli.py programme my-programme-001
```

The report writes to disk in both Markdown and JSON. It is the artefact you hand to anyone who needs to know what the show did and why.

## The Green Room

Before a show opens, the cast rehearses. The Show has a rehearsal mode for exactly this purpose.

```
python3 cli.py run examples/my-programme.yaml --rehearsal
```

In rehearsal, the Stage Manager makes no real LLM calls. No channels are contacted. Approval gates resolve synthetically — the runtime generates a plausible decision and carries on. The full programme runs from start to finish, writing state to the database as though it were live, and exits with a scene-by-scene status report.

Rehearsal finds blocking problems. A scene that has the wrong `depends-on` declaration, an input binding that references an output that does not exist, a cut condition that would abort the show before it reaches the critical scene — all of these surface in rehearsal. The show does not lie in the Green Room. The exit code is non-zero if any scene failed. The scene-by-scene status tells you exactly which ones and why.

Rehearse every programme before opening night. The 30 seconds it takes to run `--rehearsal` is nothing compared to discovering a broken dependency binding after the live show has spent $40 on LLM calls and woken you up at 2am asking for a decision about a scene that was already doomed to fail.

The environment variable `SHOW_REHEARSAL=1` overrides the YAML `rehearsal` flag, which is useful for CI pipelines and automated testing. The flag in the YAML serves the same purpose for programmes you intend to lock in rehearsal mode until you are ready to open.

## Urgent Contact

The Stage Manager cannot leave the booth mid-show. When it needs to reach you, it uses Urgent Contact — the mechanism for raising a matter that requires a human decision before the show can continue.

Declare the contact details in your programme's `urgent-contact` block:

```yaml
urgent-contact:
  mode: sequential
  max-per-show: 5
  send-interval-seconds: 15
  contacts:
    - role: operator
      channel: telegram
      handle: "your-telegram-user-id"
      auth: channel-native
    - role: operator
      channel: email
      handle: "operator@example.com"
      auth: signed-link
```

`mode: sequential` means the Stage Manager tries contacts in order, moving to the next only if the first does not respond within the configured window. `max-per-show` is the total number of urgent matters the Stage Manager raises across the entire run — it protects your attention from a programme that has gone wrong in a way that keeps triggering escalations.

By default, an approval gate dispatches to every contact in `urgent-contact.contacts`. From v1.1.1 onward a scene's `principal` may declare two optional fields that filter the contact list per scene: `channels` (a list of channel types) and `to` (a handle, or a list of handles). Both are optional and compose with AND semantics — an unspecified field is unfiltered. Use them when different scenes should reach different operators or when one scene wants only one channel even though the programme declares several.

```yaml
- scene: director_approval
  principal:
    method: human-approval
    channels: [telegram]            # only contacts whose channel is "telegram"
    to: ["8406661245"]              # ...AND whose handle is this Telegram user

- scene: technical_approval
  principal:
    method: human-approval
    channels: [email]               # routes to the email contact only
```

`the-show validate` cross-references `principal.channels` and `principal.to` against `urgent-contact.contacts`. If a scene refers to a channel or handle that no contact provides, validation fails at load time so the show never opens with broken routing.

Urgent Contact fires in three situations. First, an approval gate — a scene with `method: human-approval` — pauses the show and sends you a message with the context you need to decide. Second, the House Manager raises an alert when a hard signal fires: cost past the threshold, scenes stalling, repeated denials. Third, a scene with `cut: condition: escalate` exhausts all its strategies and calls for a human decision rather than aborting or continuing silently.

The Telegram message includes a signed link. You click it, select your response — APPROVE, REJECT, CONTINUE or STOP — and the show resumes. The signed-link mechanism means the Stage Manager only accepts replies that carry a valid authentication token. An unsigned reply, a malformed response or an expired token triggers a follow-up clarification rather than being acted on.

Email contacts receive the same signed link by a different channel. The link is the response mechanism — you do not reply to the email, you click the link. The show does not resume until you do, or until the timeout expires and the cut condition handles the stalled scene.

## When Things Go Wrong

The Show saves state after every scene. If the process is interrupted — power cut, network failure, you killed it — nothing is lost. The next time you run the same programme file, the CLI detects the previous run and asks whether to resume. Say yes, and the Stage Manager picks up from the last scene that completed cleanly.

Cut conditions are how the Director declares failure handling at the scene level. Every scene needs one. There are three:

`cut: condition: escalate` halts the show and raises an urgent matter. The operator decides what happens next. This is the right choice for scenes the programme cannot proceed without — a drafting scene that must produce content for downstream scenes to use, an approval gate where silence is not a valid answer. When you do not know what the right cut condition is, declare `escalate` and let the Stage Manager ask.

`cut: condition: continue` marks the scene as cut and carries on. Downstream scenes that depended on this scene's output are skipped. The show reaches the end in a degraded state rather than a stopped one. This is appropriate for scenes that are genuinely optional — reporting scenes, secondary delivery steps, anything whose failure does not prevent the core work from completing.

`cut: condition: abort` stops the show immediately and marks the run as aborted. Use this when continued execution after a failure would cause harm — a scene that guards sensitive data release, a scene whose output is the precondition for a side effect you cannot roll back. Abort is a clean stop. The state is preserved. The programme report records exactly which scene triggered the abort and why.

The `must-complete` flag is separate from cut conditions. A scene marked `must-complete: true` pauses the show in a `paused` state if it cannot reach a terminal status — not aborted, not failed, waiting. On the next `python3 cli.py run` invocation, the show resumes and retries the scene. This is for scenes where the answer to failure is not a different strategy but simply waiting: an approval gate that has not yet received a response, an external dependency that will eventually come online.

Cascading failures are handled automatically. If a scene ends in `blocked-no-response` — the operator did not reply within the timeout and no graceful degradation was declared — the Stage Manager marks all scenes that depended on it as `cascading-dependency-failure` and continues with the remainder of the programme. The show does not abort. It finishes what it can and reports exactly what it could not.

---

The Show exists because the operator's attention is the scarce resource. A festival director does not stand in the wings approving every lighting cue. They design the production, brief the Stage Manager, and are called when something genuinely requires an artistic decision. Every other cue runs. The work of designing The Show — writing the programme, declaring the red-lines, setting the escalation thresholds — is the work of a Director. Once the programme is written and rehearsed and handed over, the Stage Manager runs the show. You sleep. The scenes play. The programme report is waiting when you wake.

This is not a task runner. It is a Stage Manager. Treat it like one.
