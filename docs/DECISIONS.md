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

## D13 · Keep Frames, drop the frame rate — PROPOSED 9 Oct, awaiting confirmation

Frames survive the loss of player scope, because **defensive line height is positional** — events only say where the ball-actor was. So are block width, compactness and average positions, which several analyst cards and two of three casual phase explainers lean on.

But 10 Hz existed for run detection, which needs sub-second resolution to measure separation at peak. Line height needs 1–2 Hz.

**Proposal:** 2 Hz. ~10,800 frames per match instead of ~54,000. The generator no longer needs smooth motion for 22 players, just formations that drift sensibly. It is a generator parameter, not a schema change, so raising it back to 10 Hz for player scope later costs nothing.

Do not implement until Kehinde confirms. If unconfirmed when F3 starts, **ask**.

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

# OPEN — Kehinde decides

## O9 · After a break, blend the thin window against what?

Falls out of D15 and I under-specified it when proposing option D. The reset makes a post-break reading thin, so it gets blended — but with which reference?

- **(a) The offline `SignalPrior`**, treating a break as a fresh cold start. Simple, reuses the kickoff path exactly.
- **(b) The pre-break match baseline**, discounted. Arguably better: the teams, the pitch and the general tempo have not changed just because the score did. Falling back to a league-wide prior would say this match is a blank slate, which it is not.

My read is **(b)**, keeping the offline prior for genuine kickoff only — but it is a behaviour choice, not a tuning knob, so it is yours.

Either way `k` is a tuning parameter and `k ≈ 15 min` was fitted for kickoff. A post-break `k` may want to be smaller. Keep it configurable as `baseline_k_minutes_after_break`.

Blocking `U4`, not `U5`.

## O1 · Cosmos DB or Postgres

Blocking `S5` (day 4). Cosmos has the better free tier and native TTL and partition keys; Postgres is the more familiar query model for the aggregate reads `U4` needs. Default to Cosmos on the free tier if forced.

## O3 · Team lens register — supporter-voiced or supporter-oriented

Blocking `L6`. The prototype uses supporter-**voiced** ("we are level", "that saved us"). The Features page previously listed a club-allegiance lens under *explicitly not building*, and that objection was outweighed rather than answered: a platform may not want to ship something that sounds like it takes a side.

## O4 · Audit as an Azure Function or in-process

Not blocking. Default in-process; split only if `S5` lands early.

## O5 · Three signals or five

Decide by 16 Oct. Shipping three (territory, possession control, chance quality) saves ~0.8 days and weakens the orthogonal-basis claim.

## O6 · Drop to T0 — no agents at all

**Decide by 20 Oct.** That is the last day `A2` and `A3` could start and land. Saves 5 days, costs the Multi-Agent prize, keeps the product thesis because the thesis lives at L1.
