# MatchLens

A personalization layer for streaming platforms. One live football match is understood **once** and rendered as three genuinely different viewing experiences. Built for the viewer, sold to streaming platforms.

Solo entry to the Microsoft Premier League Hackathon ("Inside the Game").
**Submission closes 27 October 2026.** Judging runs to 10 November — the deployed URL must stay up until then.

---

## Read these before writing code

| File | What it holds |
|---|---|
| `docs/ARCHITECTURE.md` | The 13 components, their one-sentence responsibilities, how data moves |
| `docs/DATA-MODEL.md` | All 22 entities and their attributes |
| `docs/RELATIONSHIPS.md` | How they connect, with cardinalities. Several enforce an invariant below — read it before modelling |
| `docs/DECISIONS.md` | Settled decisions and the reasoning. **Do not relitigate these.** |
| `docs/BACKLOG.md` | Every ticket, with tier, dependencies and acceptance criteria |
| `docs/tickets/<ID>.md` | The full brief for one ticket. Read this before starting it. |
| `docs/QUESTIONS.md` | Where you write anything you are not allowed to decide |

---

## Who decides what

This project is a learning exercise for its author as much as a build. **Kehinde makes the product and architecture decisions.** You make the implementation decisions. Getting this split wrong is worse than being slow.

### Stop and ask. Do not pick a default and continue.

Write the question into `docs/QUESTIONS.md` with the ticket ID and what you need to know, then stop and say so.

- Anything marked **OPEN** in `docs/DECISIONS.md`
- Any change to an **invariant** below
- A new entity, or a change to what an existing entity means
- Anything that changes what a viewer sees or when they see it
- A ticket that turns out to need more than 2 days
- Any cut — dropping a criterion, a signal, a check, a lens
- A library not in the pinned stack below
- Anything where the honest answer is "I guessed"

### Decide yourself. Do not ask.

- File and function layout inside a module
- Function signatures, type hints, docstrings
- Test structure and fixtures
- Variable and local naming
- How to make a failing test pass
- Refactoring that changes no behaviour

---

## Invariants

These are not preferences. Breaking one breaks the product's central claim, which is that nothing it says is unverifiable.

1. **Frames never reach an LLM.** Agents read events, possessions, signal readings and above. Enforce this in the data access layer with a test that fails if an agent-facing read touches `Frame` — not by convention, not by code review.
2. **Groups A and B are append-only.** Nothing in the match record or derived understanding is edited after emission. Ever.
3. **Corrections are new events, not edits.** A VAR reversal is a football event. Derived state is recomputed; the narrative log is not rewritten.
4. **Everything has an ID, and every derived object cites its inputs.** Runs cite frames. Readings cite events. Claims cite readings and events.
5. **A claim with no citable evidence is dropped at source.** It is not softened, hedged or passed through. Verification fails closed.
6. **The explainer only ever sees a log frozen at the current match clock.** It must be structurally impossible for it to reason from the future. Test this.
7. **Model and version travel with every AI-produced record** — `Moment`, `Claim`, `Verification`.
8. **Delivery delays, never anticipates.** No card may reach a viewer before they have seen the thing it describes. The release rule is `queue.head.display_at_clock <= match_clock_now - stream_offset_ms`.
9. **Seeded means deterministic.** The same seed produces a byte-identical match. Tests and the demo video depend on this.
10. **Lens configuration is data, never code.** Adding a lens is inserting a row. No hardcoded checks for a lens name anywhere.
11. **A suppressed rendition is a record, not an absence.** When a lens deliberately shows nothing, store a `Rendition` with `suppressed=true`. Silence is the product's proof; it must be observable.
12. **Never call shot quality "xG".** It is a hand-calibrated lookup over invented data. In code, in the UI, in comments: `shot_quality`.

---

## The build order rule

**Build L1 before L0.** The degradation ladder is also the build ladder, climbed in reverse.

```
L3  score + clock only          -> a deployed URL that does something
L2  deterministic events        -> real signal maths, moments at defensible times
L1  template prose, no LLM      -> THE WHOLE PRODUCT THESIS
L0  full agent generation       -> an upgrade on working software
```

The differentiator is **selection**, not prose. Three lenses diverge correctly with zero model calls. So the template renderer (`L3` ticket) ships before the explainer agent (`A2`), and the agents are never on the critical path to a working demo.

Do not build the agent path before the template path works end to end.

---

## Vocabulary

Use these words exactly. Consistency here is what keeps the code readable against the docs.

- **Lens** — one viewing experience, defined as a point on two axes. Not a "mode", "profile" or "persona".
- **Scope** — `match` | `team` | `player`. Decides whether a moment is relevant and how it is framed.
- **Depth** — `casual` | `engaged` | `analyst`. Decides how much of the claim set survives into text.
- **Signal** — a definition, a function. **Reading** — one observation of a signal. Only readings are stored.
- **Moment** — something the spotter judged worth saying. The first opinionated layer.
- **Claim** — one structured, checkable assertion. The explainer emits claims, never prose.
- **Rendition** — one moment as one lens presents it. Up to three per moment; they may differ in whether they exist.
- **Epoch** — a stretch of match with constant game state, bounded by goals, red cards, half time.
- **z_match** — deviation from this match's baseline ("something changed"). **z_prior** — deviation from the offline prior ("this match is unusual").

---

## Stack

Pinned. Do not substitute without asking.

| Concern | Choice |
|---|---|
| Runtime | Python 3.12 |
| API, event stream, static serving | FastAPI + uvicorn, **Server-Sent Events** (not WebSocket) |
| Simulator, signals | NumPy |
| Agents | Microsoft Agent Framework — **pin to an exact version on day one** |
| Models | Foundry SDK |
| Schemas | Pydantic |
| Tests | pytest |
| Lint and format | ruff |
| Frontend | Plain HTML and JS. No framework, no build step. |
| Infra | Bicep, Azure Container Apps, Service Bus, Cosmos DB |

SSE rather than WebSocket because nothing the viewer sends needs duplex: lens switches, position reports and playback controls are low-frequency POSTs. SSE gives reconnection and `Last-Event-ID` for free, and `Last-Event-ID` maps onto the release buffer.

---

## Module layout

```
matchlens/
  models/            pydantic models, grouped as the data model is grouped
  source/            Match Source: seeded simulator, replay harness
  ingest/            ring buffer, frame access boundary
  understanding/     possession, shot_quality, the five signals, baselines, epochs
  spotting/          spotter, suppression
  explanation/       explainer agent (claims, never prose)
  verification/      the six checks
  personalization/   scope dispatch, thresholds, rate limits, renderers
  catchup/           late-join summary per lens
  delivery/          SSE, per-session release queue, session clock
  lenses/            registry and the three presets
  control/           mute circuit breaker, producer actions
  audit/             post-match report
apps/
  pipeline.py        entrypoint for the pipeline container
  delivery.py        entrypoint for the delivery container
web/                 plain HTML and JS
infra/               Bicep
tests/
docs/
```

One repo, one image, two entrypoints. Everything not listed as a deployable unit stays an in-process module.

---

## Working a ticket

1. Read `docs/tickets/<ID>.md`. If there is no file for it, read its block in `docs/BACKLOG.md` and **ask for the detail before starting** — a ticket without a brief has not been thought through yet.
2. Check its dependencies are done.
3. Branch: `ticket/<ID>-<short-slug>`.
4. Write the test named in the acceptance criteria first where the criterion is testable.
5. Implement.
6. `ruff check . && ruff format --check . && pytest`.
7. Update the ticket's status line in `docs/BACKLOG.md`.
8. Commit with the ticket ID in the subject: `F3: seeded simulator emitting frames and events`.

Keep the test suite under two minutes. A ten-minute suite is one you stop waiting for, and then it stops being CI.

---

## Scope guards

Not building these. If a ticket seems to need one, that is a signal to stop and ask.

- User accounts or authentication
- A mobile app
- Chat with the match
- Voice or audio output
- Real match data or real video
- More than two languages
- **Player scope, at any depth** — deferred, not cancelled. `Run` is not built in v1.
- Live multi-viewer sessions
- Multi-region, HA, failover
- AKS

---

## Timing

17 build days (9–25 Oct), two days for submission materials. The T1 tier is ~30 ticket-days, so this is oversubscribed and the cut ladder in `docs/BACKLOG.md` is live, not theoretical.

**20 October is the last day the explainer and verifier (`A2`, `A3`) could still start and land.** If they have not started by then, raise it — the fallback is to ship at L1 with no agents, which keeps the product thesis and loses the Multi-Agent prize.
