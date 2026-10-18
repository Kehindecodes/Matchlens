# Decisions

Settled calls and why. **Do not reopen a SETTLED decision without asking Kehinde** — each one cost a conversation, and several were reversals of an earlier position.

Status is `SETTLED` or `OPEN`. An OPEN decision is Kehinde's to make; see the escalation rule in `CLAUDE.md`.

---

## D1 · Three lenses: match×casual, match×analyst, team×engaged — SETTLED 9 Oct

Not the two options originally posed (three-with-player-scope, or two).

The two match-scope presets differ **by depth alone**, which is what produces the silent panel. The team preset differs **by scope**. Both axes are visible from three panels without a fourth.

Player scope was deferred because it is the only lens needing the `Run` entity (2 days for a detector, or 1.5 days for the cheap path). Team scope reaches the same axis for the cost of a rendering register, because every signal is already per-team.

**Cost accepted:** off-ball runs were the most visually distinctive material in the product and the one thing in it no consumer platform offers.

## D2 · Scope is two mechanisms, not one — SETTLED 9 Oct

This surprised us late and it changes the personalizer.

- **`player` scope is a true subject filter.** A moment about another player is genuinely irrelevant. Drop it, except `breakthrough_types`.
- **`team` scope is a reweight plus a framing transform.** A moment about the *opponent* is maximally relevant to a supporter. It drops almost nothing by subject. It boosts moments affecting the result, drops neutral tactical curiosities, and tells everything as consequence-for-us rather than mechanism.

Implement as **two code paths dispatched off `scope`**, not one filter taking different arguments. `breakthrough_types` is load-bearing only for `player`.

## D3 · The degradation ladder is the build ladder, climbed in reverse — SETTLED 8 Oct

L1 (template prose) before L0 (agents). See `CLAUDE.md`. The agents are an upgrade on working software, never a dependency.

## D4 · Corrections are new events — SETTLED 8 Oct

A VAR reversal is a football event, not a pipeline failure. Append a new event; recompute derived state; do not rewrite the narrative log. This works *better* with stream-offset delivery, because release-on-viewer-clock gets the ordering right for every viewer automatically.

## D5 · SSE, not WebSocket — SETTLED 8 Oct

Nothing the viewer sends needs a duplex connection. SSE gives reconnection and `Last-Event-ID` free, and `Last-Event-ID` maps onto the release buffer.

## D6 · Per-card producer approval was dropped — SETTLED

An earlier design had a producer hold or release each card. It puts a human in the delivery path (breaking V2's latency criterion) and recreates the manual production cost this product exists to remove. Prime Vision needs a control room in Los Angeles; that is precisely the thing we argue does not scale to a midweek fixture.

Replaced by: automated verification of every claim, a **circuit breaker** acting on later cards only, and automated pre-live and post-match checks.

## D7 · Delivery is a per-session scheduler, not a push — SETTLED

A stream runs tens of seconds behind the action while the data feed is sub-second. A card timed to the match clock arrives before the viewer sees the goal, and the product becomes the thing that spoils football.

Each `ViewerSession` carries `stream_offset_ms`. Delivery holds each rendition until that viewer's video reaches the moment. Delay only, never anticipate.

## D8 · The simulator is the foundation, not the schema — SETTLED 8 Oct

Working the dependency graph backward, every chain bottoms out at the seeded generator. Because the data source is synthetic, a non-deterministic generator makes every downstream test unreliable and calibrates every signal against noise. This is the inversion versus a CRUD app.

## D9 · Service Bus, not Event Hubs — SETTLED

Event Hubs is built for millions of events per second. The broker here carries claims and renditions — hundreds per match — where **ordering** and reliable delivery matter more than throughput. Frames never touch the broker at all.

## D10 · Signals are an orthogonal basis, not scenario detectors — SETTLED

Five signals: territory, possession control, pressing intensity (PPDA), chance quality, defensive line height. They are measured continuously and combined, rather than a library of named situations to pattern-match. This is what lets the system describe a match it has never seen.

## D11 · Baselines blend per-match with offline priors — SETTLED

`w = n/(n+k)`, k ≈ 15 minutes. At minute 4 the prior dominates; by minute 30 the match baseline does. Without this, a z-score against five minutes of data is noise, and that is exactly when a naive system floods the viewer with "unusual!" moments.

## D12 · Runs are derived, never emitted — SETTLED (dormant)

When player scope lands, `Run` is derived from frames by a detector, not emitted by the generator. Emitting it would be circular — the generator declaring what it already decided was interesting — and deriving is what makes the pipeline work unchanged on real tracking data.

Dormant because player scope is deferred. Recorded so it is not re-decided wrongly later.

## D13 · Keep Frames, drop the frame rate — SETTLED 9 Oct

Frames survive the loss of player scope, because **defensive line height is positional** — events only say where the ball-actor was. So are block width, compactness and average positions, which several analyst cards and two of three casual phase explainers lean on.

But 10 Hz existed for run detection, which needs sub-second resolution to measure separation at peak. Line height needs 1–2 Hz.

**Decision:** 2 Hz. ~10,800 frames per match instead of ~54,000. The generator no longer needs smooth motion for 22 players, just formations that drift sensibly. It is a generator parameter, not a schema change, so raising it back to 10 Hz for player scope later costs nothing.

Confirmed by Kehinde at the start of F3. `settings.frame_rate_hz` stays the single source of truth.

## D14 · `Rendition.suppression_reason`, and every closed set is a named enum — SETTLED 9 Oct

**`suppression_reason` added** to `Rendition`, required iff `suppressed` is true. One value, not a list, resolved by a declared evaluation order so the reason is deterministic across runs.

Seven values: `out_of_scope`, `muted`, `degraded`, `verification_failed`, `claims_filtered_out`, `below_threshold`, `rate_limited`.

**The split worth keeping:** `claims_filtered_out` and `verification_failed` have the same shape — no claims survived — and opposite meanings. The first is the product working as designed; the second is a quality alarm. One combined value would make a failing system indistinguishable from a working one in the post-match report.

**Also settled in the same pass:** every closed set in the model now has a named enumerated type, listed in `docs/DATA-MODEL.md` under "Enumerated types". Previously these lived in prose, which left F2 instructed to create enums without being told which. `language`, `model`, `model_version` and `generator_version` stay free strings, with the reasoning recorded there.

## D15 · A signal window never crosses an epoch boundary — SETTLED 9 Oct

**Resolves both O2 and O8.** The straddling problem is dissolved rather than solved: if a window can never span a structural break, there is no ambiguity about which epoch a reading belongs to.

### The rule

```
window_start = max(reading_clock_ms - nominal_window_ms, epoch.start_clock_ms)
```

After a goal at 61:04, a reading at 62:00 covers 61:04–62:00 — 56 seconds. The window grows with the epoch and reaches full nominal length at 66:04. From then on it is an ordinary 5-minute window.

### What falls out of it

- **`epoch_id` is unambiguous by construction.** Always the current epoch at the reading's clock. No overlap maths, no majority rule, no splitting.
- **`window_ms` means the *effective* window actually covered**, not the nominal configured length. The field already exists; this sharpens what it holds. Store both if the nominal value is needed for debugging.
- **`confidence` falls out on its own** — low because the sample is genuinely thin, not because anything flagged it. This is what makes O2's proposed answer automatic rather than a special case.
- **The baseline counter `n` resets at each epoch boundary**, and the existing shrinkage `w = n/(n+k)` reapplies. An epoch boundary is a miniature cold start, structurally identical to minute 4 of the match, so it reuses machinery that already has to exist. **No new concept is introduced.**

### What it costs, stated honestly

For a few minutes after every goal, red card and half time, the system knows less, says less, and says so. That is correct — the game genuinely just changed and there is not yet much to know about the new state. It also means fewer moments fire immediately after a goal, which is the opposite of the naive failure mode where a system floods the viewer precisely when the baseline is least reliable.

## D16 · `Player` is immutable; roster state is derived from events — SETTLED 9 Oct

### The problem

`Player` sits in group A, which invariant 2 says is append-only, never edited. But `on_clock_ms` / `off_clock_ms` change when a player is substituted or sent off. That is a direct contradiction, and it breaks something worse than tidiness: **if the verifier's entity check reads mutable state, verification stops being reproducible.** A claim verified at minute 60 could verify differently when P4 and P5 re-check it against stored data, so the post-match report would disagree with what actually shipped.

### The resolution

`on_clock_ms` and `off_clock_ms` **come off the entity.** They were fields pretending to be events.

- **`Player` holds identity only:** `player_id`, `team_id`, `shirt`, `name`, `position`, `is_starter`. Loaded pre-match, never touched again.
- **Who is on the pitch at clock X is derived** from the roster plus the roster-changing events in the log.
- `was_on_pitch(player, clock_ms)` is a function over the frozen event log, **not** a model helper.

```
enters  = is_starter ? 0 : clock of the substitution that brought them on (else never)
leaves  = clock of the substitution taking them off, or of their red card, or match end
```

Because it is computed from an immutable log, re-deriving it later always gives the same answer.

### Why the injury case settles it

An injury substitution, a tactical substitution and a red card are three different football events that all end a player's time on the pitch. A mutable `off_clock_ms` would be one field written by three code paths with no record of *why*. As events the reason comes for free — and a red card additionally triggers an epoch boundary, which a field write never could, because a write is not something other components can react to.

### Required changes

**0. Validated against a real feed, 10 Oct.** Screenshots of the Premier League app's live commentary — which is the Opta/Stats Perform event feed with a sentence template applied — confirm this design. Substitutions appear there as **one event naming both players**, exactly the `player_on` shape. The feed showed **three substitutions at 71' and two at 63'**, so the multi-sub-at-one-clock case is real and common, which is precisely why explicit pairing beat the same-clock convention. Yellow cards, "First Half begins" and "First Half ends, Ipswich Town 0, Fulham 0" all appear as events too.

It also surfaced one event type we were missing: **`added_time_announced`** ("Fourth official has announced 1 minutes of added time"). Added, with a nullable `added_time_ms`. It is good casual-lens material — *"five minutes added, Calder have one more push"* — and it is how a viewer knows the match is not over.

**1. `Action` gains the roster and clock events.** `EpochTrigger` already names `red_card` and `half_time`, but nothing emitted them — **epoch detection had nothing to detect from.** Add: `substitution`, `red_card`, `yellow_card`, `period_start`, `period_end`.

`Event`'s definition widens from "every on-ball action" to "every on-ball action, plus the match events that change the roster or the clock". Positional fields are null for these. A separate `MatchEvent` entity would be cleaner but it is a 23rd entity and a second stream to order against the first — not worth it at this timeline.

**2. `Event` gains `player_on`** (nullable, set only for `substitution`). `player` holds the player coming **off**.

Recommended over two paired events (`substitution_off` / `substitution_on`) because pairing would then rest on a same-clock convention, and **a double substitution at one clock is ambiguous** — which matters, since the 58:00 double change is the hinge of the demo narrative and "Boateng replaces Mensah" would be wrong half the time. `Event` already carries `receiver` as an action-specific nullable field, so this follows existing precedent. A red card is a single event with no pairing; an injury with no replacement is a substitution with `player_on` null.

**3. `Epoch.player_counts` is derived** from the same log, consistent with everything else.

**4. `Match.period_boundaries` is derived** from `period_start` / `period_end` events. It held end-of-half times including added time, which cannot be known pre-match — so it was either not pre-match data or another mutated field. Same problem, same fix.

**5. `F2` changes.** It currently asks for `was_on_pitch` as a model helper with tested boundary semantics. Under D16 it cannot live on the model. The boundary semantics still need deciding and testing — inclusive start, exclusive end — but in the module that reads the log.

### Also settled: the roster loads before the stream

`Team` and `Player` are created **before** streaming, as a pre-match setup message. Three reasons: events reference `player` and `team` by ID, so an event arriving first is a dangling reference; `Team.attack_direction_by_period` is needed to normalise coordinates and the very first frame needs it; and the verifier's entity check would fail spuriously on a roster that has not landed.

**Ingest must refuse the stream until the roster is loaded** — an acceptance criterion on `S2`, not an assumption.

---

## D17 · Personalization splits into Selection and Rendering — SETTLED 11 Oct

The component table's own rule caught this one: *"Selects **and** renders the surviving claim set for one lens"* was two jobs in one row.

**Component 7 becomes Selection — chooses which verified claims one lens shows. Component 8 becomes Rendering — turns one lens's selected claims into a rendition.** The count goes 13 → 14.

### Why this is a real split and not bookkeeping

**They fail independently.** Selection is deterministic logic over lens config: scope dispatch, `importance_threshold`, `max_cards_per_10min`, `allowed_claim_types`. Rendering turns a claim set into words — templates at L1, an agent at L0. A selection bug shows the wrong claims; a rendering bug reads badly. Different tests, different fixes.

**The backlog already built them separately.** `L2` is selection, `L3` is rendering, and `L3` depends on `L2`. The architecture doc was lagging the plan, not the other way round.

**It exposes the property that matters most to a buyer.** Trace the degradation ladder: `A4` and `A5` both depend on `L3`. Every model call lives in Rendering. **Selection is model-free by construction**, so a model outage can change how a card reads but can never change which claims a lens shows. Welded into one component, that guarantee is invisible and easy to break by accident.

### Consequences

- `S1`'s signatures become `select(moment, claims, lens) -> list[Claim]` and `render(moment, selected, lens) -> Rendition`. They compose; one `render()` doing both did not.
- The module `personalization/` becomes `selection/` and `rendering/`.
- **Selection writes nothing.** It passes a claim subset in process. `Rendition` is written once, by Rendering — so this adds a component boundary, not a storage boundary.
- A lens whose subset comes back empty **still gets a rendition**, carrying the `suppression_reason` Selection resolved. Invariant 11 is unchanged and now has an unambiguous owner.
- `L6` (team scope) spans both components — importance reweight is Selection, partisan framing is Rendering. That is fine; tickets need not map one-to-one onto components.

**Timing was the deciding factor.** No code exists yet, so the whole cost was paid in markdown. After `S1` lands this split means moving modules.

### The rule itself was restated

"No 'and' in the sentence" is a syntax rule, and a syntax rule is satisfied by deleting the word — "Produces a rendition for one lens" reads clean and hides both jobs. The rule now tests independent failure instead, and says explicitly: rewrite the sentence, do not just delete the conjunction.

**Components 2 and 3 keep their "and" under the restated rule.** Ingest's boundary enforcement is a consequence of exclusive ownership, not a second job — split it and you get a gatekeeper wrapping a buffer that can be bypassed by calling the buffer directly. Understanding's "possessions, shot quality, signal readings" is a list of objects, not verbs: one transformation over three quantities is one responsibility.

---

## D18 · Ingest is the sole writer of the raw record — SETTLED 11 Oct

The component table said Ingest *"holds the recent frame window in memory and enforces the frame access boundary"* and said nothing about persistence. Step 2 of the data flow said Ingest *"persists events."* The ownership table said `Frame` and `Event` are written by *"Match Source (via Ingest)"* — naming two components for one entity, which breaks the single-writer rule that table exists to state.

**Settled: Ingest writes `Match`, `Team`, `Player`, `Frame` and `Event`. Match Source produces a stream and writes nothing.**

### Why Ingest and not Match Source

A producer that also persists is a producer you cannot swap. The entire point of Match Source being one component is that the seeded simulator is replaced by a real provider feed later without anything downstream noticing. If Source writes, that swap drags storage concerns into the adapter.

Ingest is the intake boundary, so it is the natural single custodian of **everything raw** — whether that record is an ephemeral in-memory frame window or a durable append-only event log. Those differ in storage tier and lifetime, not in ownership.

### Consequences

- The ownership table row reads **Ingest**, and the count of writing components goes 9 → 8.
- `S2` owns event persistence. This was already true in practice; it is now written down.
- A future real-feed adapter replaces Match Source only. Nothing about persistence moves.
- This does **not** change component 2's one-sentence responsibility, which stays as written — "sole owner of the raw record" is what the existing sentence already means, and the frame access boundary is the load-bearing half.

---

## D19 · Postgres, not Cosmos DB — SETTLED 11 Oct

Resolves O1. **The database is Azure Database for PostgreSQL (Flexible Server).**

### Why Postgres

- **The reads are relational.** Events by clock range, the frozen log (`clock_ms < t`), and U4's aggregates over a window are ordinary SQL with an index on `(match_id, clock_ms)`. In Cosmos for NoSQL they are a new query model to learn under deadline.
- **Familiar ground, by design.** `docs/LEARNING-PLAN.md` puts the learning budget on event-driven systems and agent orchestration. Storage is not one of the lessons, so it should be the known tool.
- **Cosmos's advantages do not bite here.** Partition keys and multi-region are for scale this build explicitly does not have: one match, one pipeline (see Scope guards). Native TTL is not needed — groups A and B are append-only and kept.

### What was ruled out, and why

**Azure Cosmos DB for PostgreSQL** looked like the best of both, but Microsoft no longer supports it for new projects. Its successor, elastic clusters in Azure Database for PostgreSQL, is sharded Postgres, which is pointless for one match.

### Consequences

- The pinned stack in `CLAUDE.md` reads Postgres in place of Cosmos DB.
- **S2 is unchanged.** Event persistence stays behind a repository interface with an in-memory implementation. The Postgres implementation lands in S5, behind the same interface.
- The Postgres client library is not chosen here. It is a new pinned dependency, so S5 asks before adding one.
- The free tier is for new Azure accounts and lasts 12 months. Check it covers the whole judging window to 10 November before provisioning, and set the budget alert first, as S5 already says.

---

## D20 · S4 is 🤝 — Claude Code wires it, Kehinde owns the call-path assertions — SETTLED 17 Oct

The pack contradicted itself on who implements S4. `LEARNING-PLAN.md` said **"Wire S4 by hand"** — but said it under a heading reading *"Also yours, though not tickets"*, and S4 **is** a ticket; the backlog row was **unmarked**, which `CLAUDE.md` defines as Claude Code's; and the reserved list in `CLAUDE.md` omitted it. Three of the four places said delegate, one said do not.

**Settled: S4 is 🤝.** Claude Code writes `apps/pipeline.py` and the wiring. Kehinde writes two of the four acceptance criteria himself:

- all fourteen components appear in the call path
- nothing is bypassed — no direct hop from Spotting to Delivery

### Why not 🧑

The wiring is half a day of stub glue, and the heuristic in `LEARNING-PLAN.md` sends glue to Claude Code. Typing `pipeline.py` teaches little. What teaches is the assertion: *"all fourteen components were entered"* is not a test of the code, it is a test of whether **this architecture composes** — and architecture is Kehinde's side of the split in `CLAUDE.md`.

Same shape as F3 — delegate two days of football modelling, own the thirty-minute determinism test. The lesson lives in the property, not in the implementation.

### Why not leave it unmarked

Most of the walking-skeleton lesson is already reserved by *"own the debugging of anything in the event path"*. S4 failing on its first run **is** event-path debugging: `seq` out of order, state that did not reset, a card released before its clock. What was genuinely unclear was only who types the glue — and an unmarked row answered that wrongly.

### The schedule decided it

**20 October is the last day A2 and A3 can start.** S4 sits on the critical path to the deployed URL, and the remaining reserved work — the `Claim` schema, A1, A3, D1 — is where Kehinde's own hours have to go. Spending them on stub wiring while the agent gate closes is the wrong trade.


### Amended 18 Oct: the call-path tests were handed back

Kehinde asked Claude Code to write the two call-path tests after all. They are in `tests/test_walking_skeleton.py`, marked strict `xfail` until Explanation returns a claim, because Verification is entered once per claim and today there are none. Everything else in D20 stands.
---

## D21 · Entailment is one rule over operands — SETTLED 18 Oct

`entailment` and `coverage` were named in three places — the `CheckName` enum, `Verification.checks`, and A3's backlog note — and defined nowhere. This settles the first of the two.

**Entailment is a single rule, not three per-type implementations:**

> Every operand of a claim carries its own window and its own evidence. The check passes when each operand's evidence resolves to rows matching that operand's `subject` and `metric`.

Arity varies by `claim_type`, the rule does not:

| `claim_type` | Operands |
|---|---|
| `descriptive` | one |
| `comparative` | two — the subject, and the thing compared against |
| `interpretive` | one, plus a backing reading and the threshold the wording implies |

### Why one rule rather than branches

A fourth claim type later means adding an operand shape, not editing the verifier. Branching on `claim_type` inside the check puts claim-type knowledge in two places and they drift apart.

### This rules out `comparison` as a string

A comparative claim has two operands and the second one was unverifiable: `window` and `evidence_ids` cover the subject side only. If `comparison` is prose — `"up on the first half"` — the verifier has to parse English to know what to fetch, which is re-deriving meaning from a sentence: the exact failure the claims-not-prose decision exists to prevent.

**The comparison operand carries its own window, evidence and value as structured fields.**

### This rules out "unusually" as an adverb

An interpretive claim has no number to recompute, so `value` does almost nothing and entailment carries the load. It checks that the cited reading's signal is the signal the claim is about, and that its z-score clears the threshold the wording implies.

**So the threshold is a field on the claim, not a word in the text.** Otherwise the explainer can pass a prose-grade judgment through every other check untouched, and the whole structured-claims argument leaks at its weakest point.

### Division of labour with `value`

These two overlap unless the line is drawn explicitly:

- **`value` recomputes from the record**, ignoring what the claim cited. Catches *the number is wrong*.
- **`entailment` checks the claim's own evidence supports it.** Catches *the number is right but the citations have nothing to do with it*.

The second failure matters more than it sounds: `evidence_ids` is what the evidence drawer (A6) shows and what the audit trail rests on. A claim with a correct number and unrelated citations passes `value`, ships, and collapses the moment a judge clicks through it.

### Still open, and still Kehinde's

This constrains the `Claim` schema. It does not finish it. Outstanding in the reserved half-day:

- ~~the operand's own field list, and whether `subject` and `metric` are enums~~ — settled 18 Oct: `subject`, `metric`, `window`, `value`, `evidence_ids` per operand; `subject` is a `Ref`, `metric` a string until U1–U3. See `DATA-MODEL.md`
- ~~**`coverage`** — claim-side completeness or text-side~~ — settled as claim-side by **D22**
- `value`'s tolerance policy — exact for counts, an epsilon for ratios
- inclusive or strict for `temporal` — Q6's leftover, assigned to A1

### L1 note

If the pre-agent path constructs claims *from* readings rather than asserting things about them, entailment is near-vacuous at L1 and only earns its keep on the agent path. Honest to stub it there; it has to be real for A3.

---

## D22 · Coverage is claim-side completeness — SETTLED 18 Oct

Resolves the `coverage` item D21 left open.

**`coverage` passes when every trigger that fired the moment is accounted for by a claim.** A trigger is any reading in `Moment.trigger_reading_ids` or event in `Moment.trigger_event_ids`. It is accounted for when it appears in the evidence of at least one of the moment's claims.

### Why claim-side, for now

- **It runs where Verification sits.** It needs only the moment and its claims, both of which exist between Explanation and Selection. The text-side reading needs the card's words, which do not exist until Rendering.
- **It does real work at L1.** Template text is built only from claims, so a text-side check is close to automatic there. Claim-side still catches an explanation that leaves out why the moment fired.

### Not ruled out

Text-side coverage (the card asserts nothing the claims do not support) is where an AI writer can drift at L0. It is not part of this check. If it is wanted later, it is a separate check that runs after Rendering, once per lens, and that is a new decision.

---

# OPEN — Kehinde decides

## O9 · After a break, blend the thin window against what?

Falls out of D15 and I under-specified it when proposing option D. The reset makes a post-break reading thin, so it gets blended — but with which reference?

- **(a) The offline `SignalPrior`**, treating a break as a fresh cold start. Simple, reuses the kickoff path exactly.
- **(b) The pre-break match baseline**, discounted. Arguably better: the teams, the pitch and the general tempo have not changed just because the score did. Falling back to a league-wide prior would say this match is a blank slate, which it is not.

My read is **(b)**, keeping the offline prior for genuine kickoff only — but it is a behaviour choice, not a tuning knob, so it is yours.

Either way `k` is a tuning parameter and `k ≈ 15 min` was fitted for kickoff. A post-break `k` may want to be smaller. Keep it configurable as `baseline_k_minutes_after_break`.

Blocking `U4`, not `U5`.

## O3 · Team lens register — supporter-voiced or supporter-oriented

Blocking `L6`. The prototype uses supporter-**voiced** ("we are level", "that saved us"). The Features page previously listed a club-allegiance lens under *explicitly not building*, and that objection was outweighed rather than answered: a platform may not want to ship something that sounds like it takes a side.

## O4 · Audit as an Azure Function or in-process

Not blocking. Default in-process; split only if `S5` lands early.

## O5 · Three signals or five

Decide by 16 Oct. Shipping three (territory, possession control, chance quality) saves ~0.8 days and weakens the orthogonal-basis claim.

## O6 · Drop to T0 — no agents at all

**Decide by 20 Oct.** That is the last day `A2` and `A3` could start and land. Saves 5 days, costs the Multi-Agent prize, keeps the product thesis because the thesis lives at L1.



// Notes

for comparative claims , we will need to get the get the windows and the events the comparison is againnst to verify entailment while for descriptive check from the evidenceIds alone is enough
