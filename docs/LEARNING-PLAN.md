# Learning plan — what Kehinde writes by hand

MatchLens is a learning project as much as a submission. Two things are firsts: **building an event-driven system**, and **orchestrating AI agents**. This file says which tickets Kehinde writes himself and why, so the learning is not accidentally delegated away.

> **For Claude Code:** a ticket marked 🧑 in `docs/BACKLOG.md` is **not yours to implement**, even if it is blocking and even if you could do it faster. Leave it. A ticket marked 🤝 is yours to implement, but Kehinde writes the test or owns the schema — read the note on that ticket. See the rule in `CLAUDE.md`.

---

## The heuristic

**Write it yourself if it involves time, state, or a boundary. Delegate it if it involves shape, glue, or presentation.**

Time, state and boundaries are where event-driven systems differ from the request/response systems Kehinde already builds professionally. Models, routes, templates and CI are already known ground — rewriting them teaches nothing.

For the agent work the equivalent rule is: **own the contract between agents, delegate the prompting inside them.**

---

## The budget, honestly

| | Ticket-days |
|---|---|
| T1 total | ~30 |
| Self-built (🧑 plus the 🤝 portions) | **~7.5** |
| As a share of T1 | **~25%** |

Not 20%. Two first-time skills will not fit in one fifth of the work, and pretending otherwise would mean learning neither properly. 25% is the honest floor for both.

---

## Spine 1 · The event-driven path

These five form one continuous path from stream intake to viewer delivery. **The point is that they connect** — hand-writing six disconnected tickets teaches six things; hand-writing a vertical slice teaches the system.

### 🧑 D1 · Per-session release queue — 1.5 days
**Write this one even if you write nothing else.**

It forces apart three clocks that beginners collapse into one:

| Clock | Meaning |
|---|---|
| Event time | when it happened in the match |
| Processing time | when the pipeline finished with it |
| Delivery time | when *this* viewer should see it |

That separation is the central mental shift from request/response to streaming, and here it is not abstract — collapsing them ships spoilers. Per-consumer edge state, delay-never-anticipate and backpressure absorption all fall out of the same queue.

### 🧑 U4 · Baselines, shrinkage, z-scores, epoch-clamped windows — 1 day
Stateful stream processing proper. You cannot query the whole dataset; you maintain state as events arrive and decide what to do before you have enough. That is the cold-start problem.

D15's clamping adds the harder half: **invalidating state on a structural event.** State reset at a boundary is what bites people in real stream jobs.

### 🧑 A1 · Frozen-log reader — 0.5 day
Small ticket, large idea: an **as-of read over an append-only log**, which is event sourcing's central read pattern. The test proving the explainer cannot see the future is what teaches you what the pattern is *for*.

### 🧑 The roster projection — 0.5 day, inside A1/U5
A **fold over the event log** to compute current state (D16). Kehinde reasoned his way to this design in conversation, so writing it cements it — and it is the smallest possible demonstration of why append-only plus projection beats mutable rows.

### 🤝 S2 · Ingest — Claude Code implements, Kehinde writes `test_agents_cannot_reach_frames`
Two lessons, one of them general rather than event-driven: **enforcing an architectural boundary with a failing test instead of a comment.** Writing that test yourself is the most transferable thirty minutes in the project.

### 🤝 M2 · Suppression and cooldown — own it if time allows
Deduplication and debouncing over a stream. Unglamorous, recurs constantly in real work. First thing to hand back if the schedule tightens.

---

## Spine 2 · Agent orchestration

### The reframe that makes this affordable

Writing A2 and A3 end to end is 4 days and much of it is prompt iteration, which is not orchestration. **The orchestration lessons are concentrated in four places**, and three of them are cheap:

1. **The contract between agents** — a typed schema, not prose
2. **One agent overruling another** — a verdict that kills a claim
3. **Failure and fallback** — what happens when an agent times out or returns garbage
4. **Observability** — being able to *see* a handoff

### 🧑 The `Claim` schema and the six checks — 0.5 day, design before any agent code
**Do this first, and do it on paper.**

This is the highest-leverage half-day in the agent work. The architecture's whole claim to being multi-agent rather than a chain of prompts rests on one decision: **the explainer emits structured claims, not sentences.** Verifying a finished sentence means re-deriving its meaning, which is the step that goes wrong. A typed schema is checkable by construction.

Design the `Claim` fields and the six check definitions yourself. Everything downstream is consequence.

### Delegate A2 · the explainer — but own its output schema
The producer side is prompt iteration: getting a model to reliably emit conforming claims. Real work, not architecture. Hand it over — you already own the schema it must satisfy.

**Sequencing:** Claude Code writes A2 first, then you write A3 against its output. You own both ends of the contract and delegate the middle, which is a good working rhythm to keep.

### 🧑 A3 · The verifier — 2 days
Where multi-agent actually lives. One agent checking another's work, with a **deterministic recompute** as the arbiter rather than a second opinion from a model. Fail-closed. Verdicts persisted as data so a rejection is inspectable.

This is also the ticket that produces the clearest evidence for the pitch: one agent visibly overruling another, with a reason.

### 🧑 A5 · Degradation ladder — 0.5 day
Operationally the most important orchestration lesson and the cheapest. What happens when a model times out, rate-limits, or returns something unusable. Mostly free because L1 was built first — but **you want the fallback logic in your own hands**, because this is the part that decides whether the demo survives a bad afternoon.

### 🧑 S6 · Tracing — 0.5 day
You cannot reason about agent handoffs you cannot see. One trace per moment across spotter → explainer → verifier → personalizer teaches you the real shape of your system, as opposed to the shape you drew.

The part that always breaks — **trace context not propagating across the broker** — is itself the distributed-systems lesson.

### 🤝 P4 · Archetype regression check — delegate, but understand it
Guards against the generator and the signals quietly co-adapting. Subtle and transferable; worth reading closely even if someone else writes the harness.

---

## Also yours, though not tickets

**Wire S4 by hand.** Pushing one hardcoded moment through all thirteen components is how you *feel* why the walking skeleton beats stage-by-stage building. Reading about it does not do that.

**🤝 Own F3's determinism test.** Delegate two days of football modelling; spend thirty minutes writing the byte-identical-match test. The lesson is in the property, not the implementation.

**🤝 Own D2's two-offset test.** Two viewers at different delays, both correct. It is how you prove D1 to yourself.

**Own the debugging of anything in the event path.** The deepest learning is in debugging, not writing — ordering bugs, state that failed to reset, a card that arrived early. Handing those over is where you would lose the most.

---

## What this split still costs

You are delegating A2, A4 and A6, so **prompt engineering for structured output stays a gap.** That is the right trade: it is the most learnable-later skill on the list, and the least transferable to the next system you build.

If the schedule collapses, hand back in this order: M2, then S6, then A5. **Keep D1 and A3 to the end** — they are the two tickets that carry one first-time skill each.
