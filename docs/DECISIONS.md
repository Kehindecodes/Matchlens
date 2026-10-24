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

**D24 deferred line height**, so the rationale above no longer holds — frames have no consumer in v1. They are kept for the reasons D24 gives, not for this one.

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

## D23 · v1 deploys one container: the pipeline runs inside the delivery app — SETTLED 18 Oct

`ARCHITECTURE.md` names two deployable units, the pipeline app and the delivery app, with Service Bus between them, and S5 asks both to scale to zero. Those two conflict: the pipeline gets no HTTP traffic, so at zero it never starts and no match plays.

**Settled for v1: one container.** The delivery app runs the seeded replay and the pipeline in its own process, as it does locally since S4 (`run_local_feed`). A viewer's request wakes the container, which starts the match.

### Consequences

- S5 builds one image with one entrypoint, `apps.delivery`. The image can still carry the pipeline entrypoint for the split later.
- Service Bus is not on the path in v1, so `azure-servicebus` is not needed yet. The two-container split, and Service Bus with it, is a later decision.
- A cold start regenerates the match from kickoff. The first-load delay goes in the README, as S5 already asks.
- The components, the `Card` bus contract (`publish`, `CardRouter.receive`) and the module boundaries do not change. Splitting later swaps the in-process `publish` for a Service Bus sender.

---

## D24 · Four signals for v1 — line height is deferred — SETTLED 20 Oct

O5 asked three signals or five. **Four:** `territory`, `possession_control`, `pressing_intensity`, `chance_quality`. `line_height` is **deferred, not cancelled.**

### Why not the three O5 proposed

O5's three were territory, possession control and chance quality — the *cheapest* three, not the best three. Those three move together almost by definition: the team with the ball is in the opponent's half taking shots. **Pressing intensity is the signal that dissociates** — a side can press hard without possession — so it is the one carrying D10's orthogonal-basis claim. Cutting it saves ~0.3 day and costs the claim the basis rests on.

It also matters competitively. Sofascore's AI Insights already publishes possession, final-third entries, big chances and duels. Pressing intensity and line height were the two signals that read as *analysis* rather than counting, so keeping pressing is what stops the analyst lens becoming a stats recap of something already free.

### What dropping line height costs

**One class of read: a team deciding to defend.** No other signal sees a back line drop off. Territory and possession show the consequence — the other side has the ball in your half — not the decision. A 1–0 where the leading side sits in for thirty minutes, a common shape and one of the four archetypes, gets described as *"B are dominating territory"* rather than *"A have decided to protect this."*

By lens: `match × casual` loses nothing, since line height would rarely clear the importance threshold at that depth; `team × engaged` loses some framing; **`match × analyst` takes nearly all of it.**

**The thesis is untouched.** Lens divergence comes from selection, thresholds and framing, not from signal count. Four signals means fewer candidate moments, not less difference between lenses.

### Why this signal rather than another

Line height is the one most exposed to the circularity this design exists to avoid. It reads the simulator's positions, and F3's plausibility bar required building *"a defensive line with a coherent height that can move"* into the generator — so it partly reads back a parameter, where territory and possession emerge from event sequences. In the real world a dropping line is emergent; in the demo it is configured. That makes it the weakest of the five **as evidence**, whatever its value as a read.

### Consequence: nothing reads a `Frame` in v1

All four remaining signals are event-derived, so `FrameWindow`, `FrameAccess` and F3's 2 Hz generation have **no consumer in v1**.

They stay — all three are built, and the frame boundary test is the structural demonstration of invariant 1. But be precise about it in the pitch: **the invariant is enforced on a path nothing currently walks.** "Frames never reach an LLM" is true and tested; it is not load-bearing until line height or player scope lands.

**This undercuts D13's stated rationale.** D13 kept frames *because* line height is positional, and that reason is now deferred along with the signal. Keeping them stands on different ground: they are already built, the boundary test has pitch value, and reinstating line height later is then a function rather than a re-architecture.

### Mechanics

- `Signal.LINE_HEIGHT` **stays in the enum**, not built in v1 — the same treatment as `RefKind.RUN`, so the closed set still matches the data model. Add the comment when U3 is built.
- **U3 drops from 2 days to 1.5**, saving ~0.5 day. Most of its cost was line height: the frame window, the interval conversion and the retention check.
- `SignalPrior` (R1) covers four signals, not five.
- The further cut to three stays on the ladder, but it costs the analyst lens its only tactical content. Take it last.

---

## D25 · `archetype_id` and `seed` are provenance, and nothing downstream may read them — SETTLED 20 Oct

Archetypes are a property of the **Match Source alone.** In production that component is a provider feed and archetypes do not exist — they are a generator input, never runtime configuration.

But `Match` carries `archetype_id` and `seed`, which are facts about how the record was *produced* rather than about the football. A real feed can fill neither.

**Settled:**

1. Both fields are **nullable provenance**. A real feed leaves them empty; the synthetic source fills them. They stay on `Match` rather than moving to a separate provenance row — F2 and S2 are built, and the move would cost more than it returns.
2. **No component downstream of Match Source may read either one.** Enforced by a test that walks the tree, the same shape as the existing `test_nothing_outside_config_reads_os_environ`: nothing outside `matchlens/source/` and `tests/` imports `archetypes` or reads those two fields.

### Why the rule needs teeth rather than good intentions

`archetypes.py` already says it *"never says what is interesting"*, and that instinct is right. What it does not prevent is subtler: if Spotting ever thresholds differently for a scrappy match, or Selection reweights for a one-sided one, the system becomes untransferable to a real feed **and every existing test still passes.** Nothing looks broken until a provider feed arrives with a null archetype and the behaviour quietly changes.

### Replay is where the temptation lives

In replay the whole match is in hand, so its shape *could* be classified and used. That is reasoning from the future — invariant 6, the same failure as the explainer seeing past the current clock, wearing a different hat. Which is why the rule is **never read it**, not "do not read it live".

### The legitimate inversion

Archetype as **input** is cheating. Archetype as **output** is a product feature: *"this has turned into a siege"* is an interpretive claim, computable progressively from the frozen log, and good analyst-lens content. Same word, opposite direction — one is configuration leaking in, the other is the system doing its job.

Not v1. Worth keeping for the pitch's "what's next", because it reframes archetypes from demo scaffolding into something MatchLens could detect.

### So what are archetypes for

They do not run in production. They are the **test fixture that justifies the claim that the signals would work on a real feed** — P4's archetype regression is the evidence the signals generalise rather than fitting one match shape. That is the argument a platform actually wants, and it is why R2 is T1 rather than a nicety.

---

## D26 · After a break, a thin window blends against the offline prior — SETTLED 21 Oct

**Resolves O9.** Under D15, `n` resets at every epoch boundary, so the first minutes after a goal, red card or half time are a cold start. That thin post-break reading blends against the **offline `SignalPrior`**, exactly as at kickoff.

- An epoch boundary is treated as a fresh kickoff. The post-break path is the kickoff path, with no second reference and no carried-over match baseline.
- The pre-break match baseline is **not** used as the fallback.
- `z_match` in the minutes after a break therefore means the same thing it means in the opening minutes: deviation from a baseline that is still mostly the prior.

`k` stays a tuning parameter. `k ≈ 15 min` was fitted for kickoff, and a post-break `k` may want to be smaller; keep it configurable as `baseline_k_minutes_after_break`.

---

## D27 · M1 splits into M1a and M1b — SETTLED 22 Oct

M1 spanned two components, which the component rule treats as a smell. Making `understanding.observe()` emit real readings is a **streaming** problem inside Understanding; making `Spotter.consider()` judge them is **thresholds and scoring** inside Spotting. Different inputs, different failure modes, different tests.

- **M1a · Readings on the live path** — 1 day, deps U4 and U5. Incremental epoch detection, per-`(epoch_id, signal, team)` history held between calls, `priors.load()` at startup, `judge()` per reading on each cadence boundary.
- **M1b · Spotter** — 0.5 day, deps M1a. Thresholds on z-scores, confidence gating, importance scoring, moment-type mapping, trigger citation.

**M2's dependency moves from M1 to M1b.**

The total stays **1.5 ticket-days** — splitting adds no work. What it buys is a finished and tested first half before the second starts, and a clean place to stop if the remaining days run out: **M1a alone leaves the pipeline emitting real readings with S4's hardcoded moment still firing** — a worse demo than the plan, but a working one. M1 as a single ticket had no such halfway point, which at four days left was the deciding argument.

**M1b's 0.5 assumes calibration behaves.** The 30–60 moments band is the criterion most likely to fight back, and if it does, M1b grows rather than M1a.

---

## D28 · An empty window is a placeholder, except for chance quality — SETTLED 22 Oct

A measurement with `n == 0` saw nothing. For territory, possession control and pressing, its value is a stand-in (an even share, no presses) that says nothing about the match. For chance quality it is 0, and **"no chances in five minutes" is a real reading**: on seed 1 it is 57% of minutes.

R1 left every empty measurement out of the prior, and U4 kept every one in the match history. For chance quality the two references then measured different things, "quality when shooting" against "quality over all minutes", so its baseline drifted as `w` grew without anything changing in the game.

**Settled:** one rule, used by both. `signals.is_placeholder` is true for an empty measurement of any signal except chance quality.

- R1 leaves placeholders out of the prior and keeps empty chance-quality windows. Rebuilt: chance quality's mean moved from 0.411 to 0.138, the other three are unchanged, and doubling the sample still moves every mean by under 0.1 sd.
- U4 judges a placeholder (every measurement still becomes a reading) but never adds it to the history.
- A spell with no chances can now register against the baseline as a real deviation.

---

## D29 · Reserved tickets hand over; the learning moves to written walkthroughs — SETTLED 24 Oct

**Every 🧑 and 🤝 marker is released.** Claude Code implements all remaining tickets, including the tests that were reserved. In exchange, each handed-over ticket ships a **walkthrough** at `docs/walkthroughs/<ID>.md`, written as the ticket's last step.

### Why now

Two build days remain against roughly 15 T1 ticket-days, and **8.5 of those were waiting on one person's hours** — S6, D1, D2, A1, A2, A3, A5, P4. Reserving tickets to protect the learning was the right call on 9 October, when the constraint was ambition. The constraint is now the calendar, and protecting the learning this way would cost the submission the tickets it most needs: D1 is the release queue the delivery model rests on, and A2 is what makes the brief's words *"AI insights engine"* true.

### What this does not change

**Decision rights do not move.** The "Stop and ask" list in `CLAUDE.md` stands exactly as written: anything OPEN, any invariant, any new entity, anything changing what a viewer sees, any cut. Claude Code is being handed **implementation**, not judgement, and a product question answered quietly is still the failure this project has guarded against from the start.

### Why a walkthrough and not comments

The finished code already says *what* was built. What disappears when a ticket closes is the part worth learning:

- the options that were live, and why the losing ones lost
- what was built first, broke, and got replaced
- the thing a reader of the final code would reasonably get wrong
- where state lives and **why it resets where it does**

`docs/walkthroughs/TEMPLATE.md` is prescriptive about this and bans restating the diff. A walkthrough that paraphrases the code is worse than none, because it looks like the thing was explained.

### The cost, stated rather than waved away

**Reading an explanation is not writing the code.** Kehinde will get the concepts and not the reflexes — the hour lost to a state reset that fires one call too late teaches something a paragraph about it cannot. That cost is accepted, not avoided.

The cheap recovery, after the 27th: take **one** walkthrough, delete its implementation, and rebuild it from the walkthrough alone. **D1** or **A3** — each carries one first-time skill. That is a day, it is not under deadline, and it recovers most of what reading loses.

### Mechanics

- `📝` in `docs/BACKLOG.md` replaces 🧑 and 🤝 on the eight open tickets: **implement it, and write the walkthrough.** The walkthrough is an acceptance criterion, not a courtesy.
- Markers on **already-finished** tickets are left as they are. F3, S2, S4, M1a and M2 record what actually happened, and rewriting them would falsify the history.
- **M1a is the exception worth considering.** It is built, it carries the streaming lesson, and it has no walkthrough. A retroactive one is probably the single highest-value page in the set — Kehinde's call whether it is worth twenty minutes before the 27th.

---

# OPEN — Kehinde decides

## D30 · The claim metric vocabulary: eight metrics, the scorer named, both comparisons — SETTLED 23 Oct

Answers Q25 part 3. Replaces the S4 stub's `triggers`, and closes D21's "a string until U1–U3 define what the verifier can recount": `Operand.metric` becomes a closed `Metric` enum (D14: every closed set is a named enum).

### The eight

| Metric | Value | Evidence |
|---|---|---|
| `goals` | a team's goals from kickoff to the clock | the goal events |
| `shot_quality` | one shot's quality, 0–1 | the shot event |
| `chances` | shots above a quality bar in a recent window | the shot events |
| `build_up_passes` | passes in the possession that ended in the shot | that possession's events |
| `territory` | the signal reading's value | the reading |
| `possession_control` | the signal reading's value | the reading |
| `pressing_intensity` | the signal reading's value | the reading |
| `chance_quality` | the signal reading's value | the reading |

Four event metrics plus D24's four signals. Every value is recountable from cited rows, so A3 can recompute it.

### Settled with it

1. **A claim may name the scorer.** A `goals` claim may take the scoring player as its subject (`Operand.subject` already allows a player, and `Player.name` is on the record). This is a match-scope card naming a player, **not player scope**, which stays deferred: no `Run`, no player lens, no player-level selection.
2. **Comparative claims compare both ways.** Against the **same team earlier** (the second operand is that team's earlier reading or count, with its own window, for example before the epoch boundary: "since the equaliser") and against the **opponent** over the same window.
3. **All eight are kept.** `build_up_passes` stays because "on the break" versus "a patient move" is the plainest "why" a goal can carry.

### Per moment type

- **Goal:** `goals` (scorer and score), `build_up_passes`, `shot_quality`
- **Chance:** `shot_quality`, `chances`
- **Tactical shift:** the signal that fired, as a comparative claim, against earlier or against the opponent

### Standard values — the same for every match, not tuned per match

| Wording | Rule |
|---|---|
| "a big chance" | `shot_quality` ≥ 0.25, the spotter's chance bar (`spotter_chance_quality`), so a big chance is what fires a chance moment |
| "their third big chance in ten minutes" | `chances` over the last 10 min, including this one, said only at 3 or more |
| "a quick attack" (was "on the break", 23 Oct: true wherever the move started) | the possession started by winning the ball in open play (a tackle, interception or aerial duel, not a restart) and reached the shot in ≤ 20 s, in any third (Q26: 1a) |
| "a patient move" | `build_up_passes` ≥ 10 |
| (neither) | otherwise nothing is said about the build-up |
| plain interpretive ("pressing harder") | `\|z_match\|` ≥ 1.25, the spotter's shift bar (`spotter_z_threshold`) |
| strong interpretive ("much harder", "by far") | `\|z_match\|` ≥ 2.0 |

A `build_up_passes` claim cites the possession's events; its window is the possession's start to the shot, which is the duration the rule reads. A move begun by a restart gets no `build_up_passes` claim (L7): no claim carries how the move began, so the claim's existence is what keeps a corner headed in from reading as a quick attack.

**Amended by Q26 (23 Oct):**

- **No zone in "on the break" (1a).** No claim carries where a move started, so the rule reads only the duration and how the ball was won.
- **Only what can be cited (2a).** A team on 0 goals has nothing to cite, so no claim asserts it. Goal text says "their first goal" or "his second"; a score line such as "2–1" only when both sides have scored.
- **A signed `threshold` (3a).** On an interpretive claim, `threshold` is the `z_match` the wording implies, with its sign: 2.0 means `z_match` ≥ 2 ("much harder"), −2.0 means `z_match` ≤ −2 ("much less"). This changes `threshold` from "how strong" to "how strong and which way".

**Why these are standard:** shot quality is an absolute function of distance and angle, the z thresholds are relative to each match's own baseline and to priors over 20 matches across the four archetypes, and the build-up rules are football definitions. Seed 1 was a sanity check, not a calibration. Across 12 generated matches (four archetypes × seeds 1–3) casual < team < analyst in card count every time, and volume follows how eventful the match is (casual 1–11, team 4–20, analyst 22–57).

**Known limits, structural rather than seed-specific:**

- Every goal on seed 1 came from a shot of quality 0.12–0.13, below the big-chance bar, so goal templates must handle a low `shot_quality` ("from a hard chance"), not assume a good one.
- `territory`'s `|z_match|` tops out near 1.5 (its prior spread is wide for a 0–1 share, Q21), so territory never earns strong wording in any match.
- All of this is measured on generated matches only; real data is out of scope.

### Still open

- Q25 parts 1 and 2: which moments casual sees, and whether `minimal` states a claim
- ~~which ticket the deterministic claim builder belongs to~~ — a new ticket, L7 (23 Oct)

---

## D32 · The scoreboard is the platform's; the demo's stands in for it, delayed — SETTLED 24 Oct

Settles Q29.

**In production, MatchLens shows a viewer no score and no match clock.** The streaming platform's scoreboard is drawn into the video, so a viewer 45 s behind sees it 45 s late, with everything else on their screen. MatchLens's own feed is the one thing that runs ahead of the picture, and D1 delays what it adds to the screen: cards, and overlays (`OverlayPacket` carries no score).

**The demo page's scoreboard stands in for the platform's, so it is delayed by the same rule as the cards (Q29: B).** Each stream is sent the `MatchState` the viewer's video is at, `clock_ms <= match_clock_now - stream_offset_ms`. The page clock comes from the same message, so a panel's "just spoke" and "quiet for" readings are on the viewer's clock too.

**If MatchLens ever draws a scoreboard of its own in production, it follows this rule.** A live one beside delayed cards spoils the goal the cards are being held for.

---

## O3 · Team lens register — supporter-voiced or supporter-oriented

### How it lands

- Headline rows carry an optional `side`, `for` or `against`, read by any lens with a `focus_team`. Keyed on the side, never on a lens or a club (invariant 10). A sided lookup does not fall back to the match register, so a missing row fails loudly instead of looking like framing that worked.
- A comparison between the two sides is read from the focus side: *"Oakhurst lead 2–1"* is said as *"Redfern trail 1–2"*. The claim is not changed; Rendering reads a reversed copy and stores nothing.
- A comparison between the two sides is also spoken **first** (Q28: B), so a lens that speaks one claim says where the moment leaves the side — the score, not the scorer. A 1–0 has no score claim (Q26 2a) and still says the scorer. Only the spoken order moves; the claim set does not.
- No new entity, field or enum value. The same claims, a different sentence (V11).

---

# OPEN — Kehinde decides

## O4 · Audit as an Azure Function or in-process

Not blocking. Default in-process; split only if `S5` lands early.

## O6 · Drop to T0 — no agents at all

**Decide by 20 Oct.** That is the last day `A2` and `A3` could start and land. Saves 5 days, costs the Multi-Agent prize, keeps the product thesis because the thesis lives at L1.



// Notes

for comparative claims , we will need to get the get the windows and the events the comparison is againnst to verify entailment while for descriptive check from the evidenceIds alone is enough
