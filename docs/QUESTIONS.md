# Questions for Kehinde

Append here when you hit something you are not allowed to decide (see the escalation rule in `CLAUDE.md`). Then **stop work on that ticket** and say so — do not pick a default and continue.

Newest at the top. Kehinde answers inline and moves the resolved ones to `docs/DECISIONS.md`.

## Template

```
## Q<n> · <one-line question>  [ticket: <ID>]  [blocking: yes/no]

**What I need to know:** ...

**Why I cannot decide it:** which rule in CLAUDE.md this falls under.

**Options as I see them:**
- A: ... — costs ...
- B: ... — costs ...

**What I would do if forced:** ... (state it, but do not do it)

**Answer:**
```

---

## Q15 · What U3's calibration assumed  [ticket: U3]  [blocking: no]

**What I need to know:** Whether these readings of the brief's one-line definitions are the ones you want. Each is one function in `matchlens/understanding/signals.py`, so any of them is a small change.

- **Window:** `(start, end]`. The event at the reading's clock counts. The event that opens an epoch (a goal, a red card) belongs to the epoch before, because the window starts at the epoch's start and leaves it out. This is the convention `frame_window` already uses, so line height can return without a second one.
- **`territory`:** of the possessions in the window that ended in a final third, the share that were this team's. 0–1, 0.5 even. Five-minute windows hold about 6 of these, so it often reads 0 or 1.
- **`possession_control`:** this team's share of the passes made inside possessions. That is "stringing passes together", not time on the ball (DATA-MODEL). Possession counts would sit near 50/50 because they alternate.
- **`pressing_intensity`:** PPDA. The opponent's passes from its own defensive and middle thirds, divided by this team's tackles, interceptions and fouls in those thirds. **Lower means a harder press.** With no defensive action, the value is the pass count, as though there had been one. Whatever words a renderer uses later will need to know that lower means harder.
- **`chance_quality`:** the sum of this team's shot values. 0 upwards.
- **`n`:** possessions (`territory`: those reaching a final third; `possession_control`: all), passes plus actions (`pressing_intensity`), and shots (`chance_quality`).
- **`confidence`:** `n / (n + 8)`, with `signal_confidence_k = 8` in settings. One k for all four, though their `n` count different things: `chance_quality` sits near 0.1 most of the time because shots are rare. That is accurate, but U4's shrinkage will treat it as always thin.
- **Cadence:** one reading per team per signal every match minute (`signal_cadence_ms = 60_000`). That is 752 measurements for seed 1.

**Why I cannot decide it:** the brief asks that calibration assumptions be noted here. None of them changes an entity or what a viewer sees yet.

**Options as I see them:** keep them, or name the ones to change.

**What I did, so you can reverse it:** all of the above, in `signals.py` and `settings.py`.

**Answer:**

## Q14 · Does a goal's epoch show the score with that goal, or before it?  [ticket: U5]  [blocking: yes, one criterion]

**What I need to know:** U5's criterion says `score_state` at each epoch start matches "an independent count of goals **strictly before** that clock". A goal epoch starts at the goal's own clock, so a strictly-before count leaves out the goal that started it: the epoch after home's opener would say 0–0.

**Why I cannot decide it:** it is an acceptance criterion, and it decides what `Epoch.score_state` means (CLAUDE.md).

**Options as I see them:**
- A: Count goals **up to and including** the epoch's start clock. The epoch after a goal shows the new score, which is the game state that epoch exists to hold. The criterion's wording changes from "strictly before" to "at or before".
- B: Keep "strictly before" and start a goal's epoch 1 ms after the goal. The criterion stands as written, but `start_clock_ms` no longer matches the event that triggered it, which every reading's clamped window reads.

**What I did, so you can reverse it:** A, in `epochs.py` and in `test_the_score_at_each_epoch_counts_the_goals_up_to_its_start`. Red cards are counted the same way, so the red card's epoch already shows ten players. Under B both change.

**Answer:** A. Kehinde, 20 Oct: count goals up to and including the epoch's start clock; red cards the same way.

## Q13 · Possessions cover 90.5% of in-play time, not "within a small tolerance"  [ticket: U1]  [blocking: yes]

**What I need to know:** Which to change, the criterion or what `end_clock_ms` means. In seed 1, possessions cover 3,174 s of the 3,508.5 s of `in_play` frames. The missing 334.5 s is ball-in-flight time that belongs to no team:
- 225 s between a possession's last touch and the other team's first. There are 205 such gaps, with a median of 1 s and a maximum of 3 s: the ball is travelling and nobody has it yet.
- 110 s after the last touch of a possession that ends with the ball going out or a shot, while the ball runs out or into the net and the frames are still `in_play`.

No in-play stretch is lost to a missing possession. The coverage test found a real bug (a save turned behind for a corner was counted as a turnover), which is now fixed.

**Why I cannot decide it:** one option changes an acceptance criterion; the other changes what an existing attribute means (CLAUDE.md).

**Options as I see them:**
- A: `end_clock_ms` stays the clock of the last cited event, so a possession's span is a pure function of its `event_ids`, like `pass_count`. The criterion becomes: possessions cover at least 85% of in-play time, and every gap between a turnover and the next possession is at most 3 s. `DATA-MODEL.md` already says possession control is measured in sequences, not time, so nothing downstream reads possession time as the denominator.
- B: A possession runs until the other team's first touch, so `end_clock_ms` is the next possession's start. Coverage rises to about 97%, but the clock is no longer recomputable from the possession's own citations, and the 110 s of ball running out remains.

**What I would do if forced:** A.

**Answer:** A. Kehinde, 20 Oct: `end_clock_ms` stays the last cited event's clock; possessions cover at least 85% of in-play time, and no turnover gap exceeds 3 s.

## Q12 · Which outcome does a possession get when the half ends during it?  [ticket: U1]  [blocking: yes]

**What I need to know:** In seed 1, both halves end with a team on the ball (46:25 `away pass` then `period_end`; 94:44 `home aerial_duel` then `period_end`). `PossessionOutcome` has `shot`, `turnover`, `foul` and `out_of_play`, and none of them describes it.

**Why I cannot decide it:** every option changes what a `Possession` means or adds an enum value (CLAUDE.md: a change to what an existing entity means).

**Options as I see them:**
- A: Add `PossessionOutcome.PERIOD_END`. Honest, and the `period_end` event is the citation. Costs one enum value and a line in `DATA-MODEL.md`.
- B: Drop the unfinished possession. Nothing new, but in-play time before the whistle belongs to nobody, and the coverage criterion needs a tolerance for it.
- C: Call it `out_of_play`. Nothing new, but it is false.

**What I would do if forced:** A.

**Answer:** A. Kehinde, 20 Oct: add `PossessionOutcome.PERIOD_END`; the `period_end` event is the possession's last cited event.

## Q11 · Which possession does the defender's foul belong to?  [ticket: U1]  [blocking: yes]

**What I need to know:** In the generator, every foul is committed by the side without the ball: `home carry` → `away foul` → stoppage → `home free_kick`. So the possession that ends with `outcome = foul` belongs to one team, and the event that ended it belongs to the other.

**Why I cannot decide it:** it decides what `event_ids` on a `Possession` contains, which is what the verifier cites (CLAUDE.md: what an existing entity means).

**Options as I see them:**
- A: The foul goes in the fouled team's possession, as its last event. The outcome is cited by an event in `event_ids` (invariant 4), at the cost of one opponent event inside a "sequence of consecutive events by one team". Possession-share signals would count events by `event.team`, not by possession.
- B: The foul belongs to no possession, like the stoppage after it. Every possession holds only its own team's events, but `outcome = foul` is then read from an event the possession does not cite.

**What I would do if forced:** A, because the outcome would otherwise be uncited. Turnovers are not affected: the interception or tackle that wins the ball starts the other team's possession, and in both options the outcome is read from it.

**Answer:** A. Kehinde, 20 Oct: the foul is the last event of the fouled team's possession.

## Q10 · Does the restart belong to the possession it starts?  [ticket: U1]  [blocking: yes]

**What I need to know:** `Event` has no `phase`; only `Frame` does. In seed 1, every on-ball event's frame is `in_play` except the 100 restarts: throw-ins, free kicks, corners, goal kicks and kick-offs. Their frames are `set_piece`, because the event is emitted at the moment the restart is taken. The `stopped` time sits between the event that stopped play and the restart, so no event is ever in it.

The brief asks that every event in a possession be `Phase.IN_PLAY`, and that U1 not read frames. Taken literally, both mean every throw-in and free kick is in no possession, and a possession could only start on the pass after the restart.

**Why I cannot decide it:** it changes an acceptance criterion and what a possession contains (CLAUDE.md).

**Options as I see them:**
- A: The restart starts the possession. The criterion becomes "no possession spans `stopped` time": the test checks, from the frames, that no `stopped` frame falls between a possession's first and last event. U1 itself stays event-only and never reads a frame.
- B: Restarts belong to no possession. This matches the criterion as written, but the pass count and start zone of every set-piece possession drop the restart, and a goal straight from a free kick is a shot with no possession.

**What I would do if forced:** A. In football, a throw-in or a free kick is the start of a possession.

**Answer:** A. Kehinde, 20 Oct: the restart starts the possession; the test checks that no `stopped` frame falls inside a possession.

## Q9 · S6's last criterion tests a Service Bus hop that v1 does not have  [ticket: S6]  [blocking: no]

**What I need to know:** What "the trace survives the Service Bus hop between the two container apps" should test in v1. D23 runs the pipeline inside the delivery app, so there is one container and no broker. `publish(card)` is an in-process call, and `Card` has nowhere to carry a `traceparent`.

**Why I cannot decide it:** dropping or deferring a criterion is a cut, and giving the bus contract a slot for trace context changes the `Card` contract D23 says stays fixed (CLAUDE.md).

**Options as I see them:**
- A: Defer the criterion to the ticket that splits the containers. S6 ships with four criteria. Costs the propagation lesson until then.
- B: Make the in-process seam behave like a broker now. `publish` takes the card plus a properties dict, and the test serialises both and calls `CardRouter.receive` from an empty context. Costs a change to the bus contract before there is a bus.
- C: Test propagation in isolation: inject into a dict, extract in a fresh context, assert the same trace. Proves the mechanism and touches no contract, but proves nothing about this app's path.

**What I would do if forced:** B, because it is the one that fails if the pipeline forgets to inject. Not done: `tests/test_tracing.py` covers criteria 1 to 4 only.

**Answer:**

---

## Q8 · What carries a rendition's clock across the bus?  [ticket: S4]  [blocking: no]

**What I need to know:** Where `display_at_clock` lives for a card on its way to Delivery. The release rule (invariant 8) and the page's card both need the match clock a rendition describes, but `Rendition` has no clock. The only entity with `display_at_clock` is `OverlayPacket`, which the data model describes as a rendition formatted for a graphics system.

**Why I cannot decide it:** it is either a new message on the stream or a change to what an entity means (CLAUDE.md), and D1 builds on whichever it is.

**Options as I see them:**
- A: A `Card` stream message, `rendition` plus `display_at_clock`, sent and never stored. The same pattern as `MatchState`. No entity changes.
- B: Add `display_at_clock` to `Rendition`. One fewer type, but it changes an entity, and a suppressed rendition would carry a clock nobody releases.
- C: Send `OverlayPacket` to the web page as well. Reuses an entity that already has the field, but stretches its meaning from graphics systems to every viewer.

**What I did, so you can reverse it:** A. `matchlens/rendering/card.py`; `CardRouter.receive` takes a `Card`, and `ReleaseQueues` holds `Card`s.

**Answer:**

## Q7 · Should the page clock read like a football clock?  [ticket: S3]  [blocking: no]

**What I need to know:** How the page shows the match clock. The simulator's `clock_ms` runs continuously across both halves, so the second half kicks off at 46:25 on the raw clock and the match ends at 94:44. A football viewer expects the second half to start at 45:00 and stoppage time to read as 45+2 or 90+3.

**Why I cannot decide it:** it changes what a viewer sees (CLAUDE.md).

**Options as I see them:**
- A: Keep the raw clock. Nothing to build, but 46:25 at the second-half kickoff looks wrong to anyone who watches football.
- B: A football clock: each half counts from its own start (0:00, then 45:00), with stoppage shown as 45+N and 90+N once the regulation time has passed. Needs each period's start clock and length on `MatchState`, both derivable from the `period_start` events.
- C: B without the stoppage notation: 45:00 onwards in the second half, running past 90:00 into stoppage.

**What I did, so you can reverse it:** A. The page shows `clock_ms` as mm:ss, plus "1st half" or "2nd half".

**Answer:**

## Q6 · S2 asks for a `frozen_log` test, but the frozen-log reader is A1, which is yours  [ticket: S2]  [blocking: no]

**What I need to know:** Whether S2 should build `frozen_log(clock_ms)` at all. S2's last criterion is "a test asserts `frozen_log(clock_ms)` returns nothing with `clock_ms` greater than the argument — the groundwork A1 builds on". But A1 is 🧑 ("Frozen-log reader: events strictly before clock X"), and `docs/LEARNING-PLAN.md` says the as-of read is exactly the lesson of A1. Writing `frozen_log` in S2 would write A1 for you.

There is also a semantic question inside it, which is A1's to settle either way: **inclusive or strict.** The S2 criterion ("nothing greater than the argument") and the verifier's temporal check ("nothing cited from *after* the clock") allow an event *at* the clock, so a goal moment can cite its own goal. A1's title and `ARCHITECTURE.md` say "strictly before", which would exclude it.

**Why I cannot decide it:** it is a 🧑 ticket (CLAUDE.md: do not implement it, not even if it is blocking), and the inclusive/strict choice changes what the explainer can see.

**Options as I see them:**
- A: S2 stops at the groundwork. `RecordReader.events_between(from, to)` is a half-open clock-range read with a snapshot guarantee, and A1 builds `frozen_log` and its no-future test on top. Drop the criterion from S2.
- B: Move the criterion into A1's brief, word for word, so it is not lost.
- C: S2 builds `frozen_log` as the criterion says, and A1 shrinks to the explainer-side test. Costs the lesson the learning plan reserves.

**What I did, so you can reverse it:** A. There is no `frozen_log` anywhere. `RecordReader` has `events_between`, which returns a tuple, so a later append cannot change what a reader already holds (`test_a_range_is_a_snapshot`). S2 is marked `wip`, not `done`, until this and `test_agents_cannot_reach_frames` are settled.

**Answer:** A. Kehinde: S2 stops at the groundwork, and the criterion is dropped from S2. `frozen_log`, its no-future test and the inclusive/strict choice all belong to A1.

## Q5 · Five of the 13 architecture sentences contain "and"  [ticket: S1]  [blocking: no]

**What I need to know:** How to settle S1's criterion "each has its architecture-table sentence as its docstring, with no 'and' in it". The two halves conflict for five components, because the table they are copied from has an "and" in five sentences:

| Component | Sentence | Kind of "and" |
|---|---|---|
| Ingest | Holds the recent frame window in memory **and** enforces the frame access boundary | two verbs — two jobs? |
| Verification | Checks each claim against the untouched record **and** returns a verdict | two verbs, but returning the verdict is arguably the output of checking |
| Personalization | Selects **and** renders the surviving claim set for one lens | two verbs — two jobs? |
| Match Source | Produces a deterministic stream of frames **and** events from a seed | two nouns, one job |
| Audit | Records what was said **and** how it held up | two objects, one job |

**Why I cannot decide it:** rewording a responsibility changes what a component is for, and dropping half a criterion is a cut (CLAUDE.md). The ticket also says "if you find yourself wanting to add an 'and', the component is doing two jobs — stop and ask", and the architecture doc says the same of any component whose sentence needs one.

**Options as I see them:**
- A: Read the rule as "no 'and' joining two jobs". Match Source and Audit pass as they are. Reword or split Ingest, Verification and Personalization.
- B: Reword all five so none contains "and", e.g. Match Source "Produces a deterministic frame-and-event stream from a seed".
- C: Accept the table as written and drop the no-"and" half of the criterion.

**What I did, so you can reverse it:** docstrings are the table sentences verbatim, and `test_docstring_is_the_architecture_sentence` reads them from `docs/ARCHITECTURE.md`, so editing the table is the one place to change them. The literal criterion is `test_responsibility_has_no_and`, with these five marked `xfail(strict=True)`. Once you pick, update the table and remove the entries from `_HAS_AND` in `tests/test_components.py`.

**Answer:** Settled by D17. Personalization splits into Selection and Rendering (13 → 14 components), and the rule is restated: an "and" is a smell, tested by whether the halves fail independently, not banned. Ingest and Understanding keep theirs deliberately. In S1 the literal no-"and" test is removed and the stubs follow the new table.

## Q4 · S1's signatures need seven entity types that no ticket has modelled, and one of them is `Claim`  [ticket: S1]  [blocking: yes]

**What I need to know:** What the S1 stubs should type against for `SignalReading`, `Moment`, `Claim`, `Verification`, `Rendition`, `Lens` and `ViewerSession`. S1 asks for "a real type signature, returning the right shape", but only the group A match-record models exist (F2). No ticket in the backlog owns the pydantic models for groups B–D, and the `Claim` schema (and through it `Verification`'s checks) is reserved for you before A2.

**Why I cannot decide it:** modelling these would mean deciding what entities mean in code (CLAUDE.md: a change to what an entity means), and for `Claim` it would mean doing a reserved 🧑 task. Choosing which ticket models them is also an ownership call.

**Options as I see them:**
- A: Opaque placeholders. One `matchlens/models/placeholders.py` with seven frozen, fieldless pydantic classes named after the entities, each with a docstring saying which ticket gives it fields. The stubs type against them, so signatures are real and S4 can flow. Nothing about meaning is decided, and `Claim` stays empty for you. Costs: each owning ticket replaces a placeholder, and S4's hardcoded moment can't carry real content until `Moment`/`Rendition` get fields.
- B: Model everything except `Claim` and `Verification` from `docs/DATA-MODEL.md` now. More useful for S4, but it roughly doubles S1 past 0.5 day and decides field types the data model leaves loose.
- C: Use `typing.Any` / forward-reference strings. Fastest, but fails the "fully type-annotated" criterion in spirit.

**What I would do if forced:** A, with `Moment` and `Rendition` getting their fields in S4 (which is unmarked and needs them to put a card on screen). I have not done it.

**Answer:** B. Kehinde: the data model exists before the implementation, so model it now. Done in S1: groups B–D in `matchlens/models/` (`derived.py`, `editorial.py`, `delivery_config.py`). `Claim` and `Verification` are fieldless placeholders until you design them; `Run` and `Recap` are not built.

## Q2 · F3's "one event every 3–4 s of in-play time" contradicts its own other numbers  [ticket: F3]  [blocking: no]

**What I need to know:** Which reading of the event-rate criterion you meant. The F3 brief asks for all three of: ~1,800 events, one every 3–4 seconds of in-play time, and 55–65 in-play minutes of a 90-minute match. They cannot all hold: 1,800 events over ~60 in-play minutes is one every ~2 s, and one every 3–4 s over 55–65 in-play minutes is only 825–1,300 events.

**Why I cannot decide it:** it is a criterion in the ticket, and reconciling it is a judgement about the data volume everything downstream calibrates against (CLAUDE.md: any cut or change to a criterion).

**Options as I see them:**
- A: Read "3–4 s" as elapsed match time (~96 min / 1,800 = ~3.2 s). Keeps the 1,800 and the 55–65 in-play minutes. Costs nothing, but the in-play rate is really ~2 s.
- B: Hold the in-play rate at 3–4 s. Gives ~900–1,200 events, which fails "~1,800" and thins the denominators the verifier recomputes from.

**What I did, so you can reverse it:** A. The generated matches land at ~1,800–1,900 events, ~56–60 in-play minutes and ~3.2 s per event over elapsed match time. `test_one_event_every_three_to_four_seconds_of_match_time` encodes this reading.

**Answer:**

## Q3 · F4's "a 90-minute match replays in under 4 minutes at 20x" is arithmetically impossible  [ticket: F4]  [blocking: no]

**What I need to know:** Which way to settle the speed criterion. 90 minutes at 20x is 4.5 minutes, and a generated match runs about 95 minutes of clock, so ~4.75 minutes. "Under 4 minutes" needs at least 22.5x, or 24x for our matches. The story the ticket cites (J1) says "a full match viewable in under five minutes", which 20x does meet.

**Why I cannot decide it:** it is an acceptance criterion in the ticket, and changing or dropping one is not mine to do (CLAUDE.md: any cut, including dropping a criterion).

**Options as I see them:**
- A: Change the criterion to "under 5 minutes at 20x", matching J1. Nothing else changes.
- B: Keep "under 4 minutes" and make the fast speed 25x (the replay takes any multiplier). The ticket lists 1x, 5x and 20x as the speeds, so this changes that list instead.
- C: Keep 20x and compress stopped time. That changes what a viewer sees, so it needs its own decision and I would not do it quietly.

**What I did, so you can reverse it:** nothing to the replay, which takes any speed. `test_a_full_match_is_viewable_in_under_five_minutes_at_20x` asserts J1 and passes. The literal criterion is `test_a_match_replays_in_under_four_minutes_at_20x`, marked `xfail(strict=True)` so it stays visible and flips to a failure the moment the numbers change. Remove that marker once you pick.

**Answer:** B. Kehinde: keep "under 4 minutes" and make the fast speed 25x. Done in F4: `FAST_SPEED = 25.0` in `replay.py`, the criterion test runs at that speed, and the xfail marker is gone.
 B
