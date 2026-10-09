# MatchLens

A personalization layer for streaming platforms. One live football match is understood **once** and rendered as three genuinely different viewing experiences — whole match at casual depth, whole match at analyst depth, and one side at engaged-supporter depth.

Built for the viewer, sold to streaming platforms. Solo entry to the Microsoft Premier League Hackathon ("Inside the Game"), submission 27 October 2026.

> The product's central claim is not that an AI can narrate football. That exists and it is award-winning. The claim is that **what you are told varies by who is watching**, automatically, so it works on every fixture rather than only the marquee one — and that nothing it says is unverifiable.

---

## This repo is a handover pack, not yet a codebase

No code is written yet. What exists is the design, settled decisions, and a dependency-ordered backlog.

```
CLAUDE.md               Invariants, vocabulary, stack, and who decides what. Read first.
docs/
  ARCHITECTURE.md       13 components, data flow, single-writer ownership
  DATA-MODEL.md         22 entities and their attributes
  RELATIONSHIPS.md      The ERD, cardinalities, and the ones that enforce an invariant
  DECISIONS.md          Settled decisions + the OPEN ones awaiting Kehinde
  BACKLOG.md            Every ticket: tier, dependencies, criteria, status
  QUESTIONS.md          Where Claude Code writes what it may not decide
  tickets/F1..F4        Phase 0 — ready to start
  tickets/S1..S6        Phase 1 — ready to start
```

Tickets from Phase 2 onward have a one-line spec in `BACKLOG.md` and no file yet. That is deliberate: they get expanded when they are reached, because fixing implementation detail three weeks early is how plans rot.

---

## Start here

```bash
# in Claude Code, from the repo root
```

> Read `CLAUDE.md`, then `docs/ARCHITECTURE.md`, `docs/DATA-MODEL.md` and `docs/DECISIONS.md`.
>
> Then start ticket **F1** — the brief is in `docs/tickets/F1.md`.
>
> Before you begin: `F1` defines `frame_rate_hz` in config, and **D13 in DECISIONS.md is unresolved**. Do not pick a value. Add the setting, leave the value to me, and note it in `docs/QUESTIONS.md` if it blocks you.

The build order is F1 → F2 → F3 → F4, then S1 → S2 → S3 → S4 → S5. **S4 is the milestone that matters**: one hardcoded moment travelling through all thirteen components into a browser. After that there is always something to look at.

---

## Two rules that shape everything

**1. Build L1 before L0.** The degradation ladder is also the build ladder, climbed in reverse. Template prose through three diverging lenses demonstrates the entire product thesis with zero model calls. The agents are an upgrade on working software, never a dependency. If the model stack is flaky on 24 October, the submission still works and still proves the point.

**2. Frames never reach an LLM.** Every claim must cite an `event_id` or `reading_id` — something with an ID and a recomputable value. A claim whose evidence is "I looked at the positions" cannot be verified, and unverifiable output is the thing this design exists to prevent. This boundary lives in the data access layer with a test on it, not in a comment.

---

## Working with a human in the loop

Kehinde is building this to learn, not to receive a finished system. **Product and architecture decisions are his; implementation decisions are Claude Code's.** The split is written out in `CLAUDE.md` and it is not advisory.

When Claude Code hits something it may not decide — anything marked OPEN, any invariant change, any new entity, anything changing what a viewer sees, any cut — it writes the question into `docs/QUESTIONS.md` and **stops**, rather than picking a sensible default and carrying on. A default chosen quietly is a decision taken away from someone who is trying to learn from making it.

Brainstorming, trade-offs and reversals happen in conversation with Kehinde, and the outcome lands in `docs/DECISIONS.md` before code follows it.

---

## Timing, honestly

17 build days (9–25 Oct), two for submission materials. The T1 tier is **~30 ticket-days**. This is oversubscribed by design rather than by accident — the cut ladder at the bottom of `BACKLOG.md` is live, with dates on each rung.

The two dates that matter:

- **16 Oct** — three signals or five (O5)
- **20 Oct** — the last day the explainer and verifier could still start and land. After that the fallback is to ship at L1 with no agents, which keeps the product thesis and loses the Multi-Agent prize (O6).

---

## Reference

Full design discussion, market positioning, failure modes, delivery scheduling and production scaling live in Notion under *Microsoft Premier League Hackathon*. The docs in this repo are the build-facing subset — if the two disagree, the repo is wrong and Notion is the source.
