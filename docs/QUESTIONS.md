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

## Q28 · Should the team lens speak the score before the scorer?  [ticket: L6]  [blocking: no]

**What I need to know:** Whether a team lens hears a goal's claims in a different order from the match lenses.

D31's framing landed in the headline and body rows: *"Riverside Athletic concede"*, *"Redfern United have scored against Riverside Athletic."* The consequence the brief asks for — *where that leaves the side* — is in the score claim, and the team preset is `detail_level: standard`, which speaks **one** claim, the first in L7's order. For a goal that is the scorer, so on the demo match the team lens never says *"Riverside Athletic trail 1–2"*. The score is read from the focus side correctly; it is just never reached. An analyst lens (`full`) does say it.

**Why I cannot decide it:** it changes what a viewer sees, and L7's order is D30's, written for "a lens that speaks only some of them".

**Options as I see them:**
- A: leave it. The headline carries for-or-against; the score waits for `full` detail.
- B: at team scope, Rendering speaks a comparative claim between the two sides first. The claim set is unchanged; only which one `standard` reaches moves. Costs: Rendering takes a scope-dependent ordering rule, and D30's single order stops being the only one.
- C: change the team preset's `detail_level` to `full`. A data change, no code. Costs: it speaks the build-up and shot quality too, and stops being visibly between casual and analyst in how much it says.

**What I would do if forced:** B, because it is the one that makes the card say what the moment means for the side. I have not done it.

**Answer:** B (24 Oct). A lens with a `focus_team` speaks a comparison between the two sides before any other claim; otherwise the explainer's order holds. A 1–0 still says the scorer, because it has no score claim to bring forward (Q26 2a).

## Q27 · S6's "stage spans add up to the end-to-end latency" fails once the stages do real work  [ticket: L7, S6]  [blocking: no, but the suite is red]

**What I need to know:** How S6 should count the time a moment waits behind the other moments fired by the same stream item.

**What happens:** `Spotter.consider` fires every moment an item produces in one call, and each moment's root `spotting` span opens and closes there. The pipeline then runs each moment's editorial stages in turn. A moment's end-to-end therefore includes the wait for the moments before it, which no span covers. With the S4 stubs that wait was well under 5 ms, so `test_stage_durations_add_up_to_the_end_to_end_latency` passed most runs (it already failed about 1 in 3 before L7). With L7's builder the worst wait on seed 1 is 29 ms (a moment at 73:00 behind its siblings) and the test fails about 4 runs in 5. The test's own note expects this: "the slack is absolute until real agents land". A2's agent would make it far larger.

L7 already makes `Pipeline.process` hand each moment's cards on as soon as that moment is done, rather than after all of the item's moments. That removed the wait after a moment's work, but not the wait before it.

**Why I cannot decide it:** S6 is yours (🧑), and so is what its trace is meant to show.

**Options as I see them:**
- A: A `spotting.queued` span from the root's end to the moment's first editorial span, so the wait is visible in the trace as Spotting's output queue. The test passes as written. Costs: one more span per moment; the stage sum then includes waiting, which is honest about latency but not about work.
- B: Measure end to end from the moment's first editorial span rather than from the root. Costs: a change to the test, and a viewer's real latency includes the wait.
- C: Spotting opens each moment's span when that moment's editorial starts, not when it fires. Costs: the spotting span stops meaning "when the spotter decided".

**What I would do if forced:** A. I have not done it, and I have not touched the test.

**Answer:** A (23 Oct). Done in L7 as a `queued` span from the moment's spotting span ending to its turn. Named `queued`, not `spotting.queued`: the test counts a stage once through its outermost span, so a `spotting.*` child of the root would fold into Spotting and leave the wait uncounted. The test passes 6 of 6 on its own and failed 1 of 2 full-suite runs, against an absolute 5 ms slack.

## Q26 · Three of D30's rules need facts no claim can carry  [ticket: L7]  [blocking: yes]

**What I need to know:** How to carry three things D30 asks for, given that Rendering only sees a claim's operands (`subject`, `metric`, `window`, `value`, `evidence_ids`), plus `threshold` on an interpretive claim. It never sees the record.

1. **"On the break" needs the move's start zone.** D30: *started in the defensive or middle third and reached the shot in ≤ 20 s*. A `build_up_passes` operand carries the passes (`value`) and the duration (`window`), but not where the move started. On seed 1, 23 of the 43 moves that ended in a shot started in the final third, so leaving the zone out would call quick moves after winning the ball high "breaks".
2. **"The score after it" cannot be cited when the other side has not scored.** Every operand needs at least one piece of evidence (invariant 5), and a team on 0 goals has no goal event to cite. So "puts them 1–0 up" asserts something nothing backs. Two of seed 1's three goals are like this.
3. **An interpretive claim has no direction.** "Pressing much harder" and "pressing much less" both need `|z_match|` ≥ 2.0. The claim's `threshold` says how strong the word is but not which way. The comparative claims carry direction, but casual's `allowed_claim_types` is descriptive and interpretive only, so casual never gets them.

**Why I cannot decide it:** each answer either adds a field to `Claim`/`Operand` or changes a D30 rule, and the `Claim` schema is yours (CLAUDE.md: a change to what an entity means; the `Claim` schema is reserved).

**Options as I see them:**
- (1a) Drop the zone from the rule: "on the break" = shot within 20 s of winning the ball, whatever third. Costs: some fast high turnovers called breaks.
- (1b) Add `start_zone: Zone | None` to `Operand`, set only for `build_up_passes`. Costs: a schema field that one metric uses.
- (2a) Cite only what can be cited: "Riverside's first goal", "the scorer's second", and a score line ("2–1") only when both sides have scored. Costs: the most natural casual line, "they're 1–0 up", is never said. The scoreboard still shows the score once the score fold lands.
- (2b) Allow `period_start` as evidence for a zero count: "nothing in this window since kickoff". Costs: evidence that proves an absence by citing something else; A3 would have to recount it as "no goal events between these".
- (3a) A signed `threshold`: −2.0 means the wording implies `z_match` ≤ −2. No new field, but it changes what `threshold` means from "how strong" to "how strong and which way".
- (3b) Let casual's lens allow comparative claims. Costs: a change to a lens row (L1), and comparative claims carry two numbers that casual templates must not say.

**What I would do if forced:** 1a, 2a, 3a. No new field, nothing cited that is not there, and the one change of meaning is the smallest. I have not started building.

**Answer:** 1a, 2a, 3a (23 Oct). Recorded in D30.

## Q25 · What should a casual viewer know, and where does the "why" come from before A2?  [ticket: L1, L3, A2]  [blocking: no, but the demo video is thin until it is answered]

**What I need to know:** Three things, seen on the L4 screen (`docs/screenshots/L4-silent-panel.jpg`). By 51:38 on seed 1 the casual panel has shown two cards, both "Goal!" with a body that only names the team. No panel explains *why* anything happened.

1. **Which moments casual sees.** `match_casual` is at `importance_threshold` 0.45 and `max_cards_per_10min` 3. On seed 1 that admits 6 of 52 moments, which so far are only the goals. The quiet panel is the thesis, but "quiet by choice" should mean casual skipped the analyst detail, not that casual cannot tell why the game turned.
2. **Whether `minimal` speaks a claim.** `_CLAIMS_SPOKEN` in `matchlens/rendering/__init__.py` is `MINIMAL: 0, STANDARD: 1, FULL: all`. So even with real claims, a casual card would carry headline and team name only. A casual "why" would be one claim in plain words, with no numbers (`test_the_casual_cards_carry_no_numbers_and_the_analyst_cards_do` already holds casual to that).
3. **Where real claims come from on the L1 path.** The only claim today is the S4 stub's `metric="triggers"`, `value` = how many readings and events fired the moment. That is where every analyst card's "Cited triggers: 1." comes from. No claim names the scorer, the signal that moved, or what changed. The build-order rule says L1 (templates, no LLM) carries the thesis, so the "why" cannot wait for A2's agent.

**Why I cannot decide it:** (1) and (2) change what a viewer sees and when (CLAUDE.md). (3) is the `Claim` metric vocabulary, which is reserved for you before A2 and was kept with you in Q23.

**Options as I see them:**
- (1a) Lower casual's threshold so its biggest non-goal moments get through, for example the largest tactical shift of each epoch. It stays sparse, still the quietest panel, and is re-calibrated on seed 1 as L1 was. Costs: fewer seconds where casual is quiet and another panel fires; the shot still exists, but more rarely.
- (1b) Keep casual at goals only, and let the catch-up summary (D4) carry the context. Costs: casual reads as a goal alert until D4 exists.
- (2a) `MINIMAL: 1`: casual speaks one claim, with a casual-register fact template per metric and no numbers. Costs: one fact row per metric per depth.
- (2b) Keep `MINIMAL: 0`; the "why" goes into the casual headline/body templates themselves, keyed on metric. Costs: templates key on the claim's metric even when no claim is spoken.
- (3a) You design the metric vocabulary now, and a deterministic claim builder (not the agent) produces those claims from the frozen log. A2 later replaces or extends it, so the agent stays off the critical path. Costs: your schema time before 27 Oct.
- (3b) Ship the demo with stub claims and accept thin text. Costs: every lens's "why" is missing on the video; the panels differ in volume more than in substance.

**What I would do if forced:** 3a first, since it is what all three lenses lack. Then 2a and 1a, so casual gets an occasional plain-words turning point and stays the quietest panel. I have not done any of it.

**Answer:** Part 3: 3a, settled as D30 (23 Oct): eight metrics, the scorer named, comparisons both ways. Parts 1 and 2 still open.

## Q24 · Are the three L4 panels fed by three sessions or by one session carrying three lenses?  [ticket: L4]  [blocking: yes]

**What I need to know:** Which shape the ticket's "⚠️ Decide how the three panels are fed" lands on. P1 (producer view, "build once") inherits it.

**Why I cannot decide it:** the ticket marks it as a decision, and it sets the shape P1 is built on (CLAUDE.md: architecture decisions are Kehinde's). Option B would also change what `ViewerSession` means (CLAUDE.md: a change to what an existing entity means).

**What exists today:** `POST /session` already takes `lens_id`, `CardRouter` already fans each card out to every session on its lens, and `/stream` is one SSE connection per session. Suppressed renditions never reach a card: `apps/pipeline.py` drops them before the bus.

**Options as I see them:**
- A: **Three sessions, three `EventSource`s.** The page creates one session per lens preset and opens three streams. No server change at all. It exercises the release queue three times over, so when D1 lands each panel is held by its own queue, as production would be. Costs: three copies of `match_state` per tick (small), three session ids kept in `sessionStorage`, and the shared clock spine has to be driven by one of the three streams (I'd use the first; they come from the same hub). Three SSE connections fit under the browser's six-per-origin HTTP/1.1 limit, though P1 adding more panels would get close.
- B: **One session, three lenses.** `ViewerSession.lens_id` becomes a list, or a new demo-only stream endpoint fans out across lenses. One connection and one clock by construction. Costs: either an entity change or a second stream path production never uses, and D1's release rule then runs once for three lenses, so the demo would not show per-session release.

**What I would do if forced:** A. It needs nothing new on the server, it matches production, and P1 becomes "the same page with internal fields shown". I have not started.

**Answer:** A. Kehinde: three sessions, three `EventSource`s.

## Q23 · What do the L3 templates key on, when no claim says which signal or what was measured?  [ticket: L3]  [blocking: yes]

**What I need to know:** L3 asks for templates "keyed on moment type, signal and depth", with every number traced to a claim's value. Today Rendering cannot see two of those three:

- **Signal.** A `Claim` carries `metric` as a free string (D21: "a string until U1–U3 define what the verifier can recount; then an enum"). The only claim that exists is the stub explainer's: `metric="triggers"`, `value` = how many readings and events fired the moment. Neither `Moment` nor `Claim` names a signal. The reading id does contain it (`{epoch}-{signal}-{team}-{clock}`), but parsing an id is not something to build on.
- **Names.** A claim's subject is a team id such as `m-1-home`. The team's name is on `Match`, which Rendering has no path to.

The `Rendition` question in the brief (what goes in `headline` and `body` when suppressed) is already settled by the model: both are `None` when `suppressed`, enforced by a validator. I am treating that as answered.

**Why I cannot decide it:** the metric vocabulary is the `Claim` schema, which is reserved for you before A2 (CLAUDE.md), and a closed set of metrics is a new enum. Choosing one here would also decide what a viewer reads.

**Options as I see them:**
- A: build L3 over what exists. Templates are a data file keyed on moment type, metric and depth, with `triggers` and a per-type default as the only metric. Team names come in from the pipeline as a lookup. The three registers differ in detail and layout, but the analyst's number is the stub's trigger count, and a tactical shift cannot name its signal. Rows for real metrics are added to the file once A2's vocabulary exists. Costs: demo text is thin until then.
- B: I propose the metric vocabulary (for example one metric per signal, plus `goals` and `shot_quality`) and extend the stub explainer to emit those claims from the frozen log. Costs: it pre-empts your `Claim` schema work and A2.
- C: pause L3 until you have designed the `Claim` schema.

**What I would do if forced:** A. It finishes every mechanical criterion (determinism, selected claims only, numbers from claims, suppressed path, no lens ids, no "xG") and leaves the vocabulary to you.

**Answer:** A (23 Oct). Build L3 over what exists; metric vocabulary stays Kehinde's.

## Q22 · What does the team lens's reweight boost and damp, and can a goal be rate-limited?  [ticket: L2]  [blocking: yes]

**What I need to know:** Two things L2's brief leaves open.

1. **The reweight rule.** The brief says team scope "boosts moments affecting the result and drops neutral tactical curiosities", and keeps opponent moments. It does not say which `MomentType`s count as result-affecting, whether the subject (focus team or opponent) matters, or by how much. `Moment.importance` is a bare float, and the three types sit at different places on the demo match (goals 1.0, chances 0.21–0.55, shifts 0.10–0.37), against `team_engaged`'s threshold of 0.3.
2. **Rate limit and goals.** The brief says a lens at `max_cards_per_10min` suppresses with `rate_limited` even when the moment clears the threshold. Taken literally a goal can be rate-limited, because `breakthrough_types` only bypasses the *scope* filter. Whether a viewer can miss a goal because of a burst of cards before it is a viewer-facing call.

**Why I cannot decide it:** both change what a viewer sees (CLAUDE.md, "stop and ask"). The numbers I would pick are a guess.

**Options as I see them:**
- 1A: reweight by type only, subject-blind. `goal` and `chance` are result-affecting, so importance is multiplied by a boost and clamped to 1.0. `tactical_shift` is multiplied by a damp below 1, so most fall under the threshold and come back as `below_threshold`, not `out_of_scope`. Opponent moments are kept by construction. Both factors go in `settings`. Costs: a shift that hurts the focus team is treated like a neutral one.
- 1B: as 1A, but a shift whose subject is the opponent is not damped. Costs: "this shift is against us" needs the reading's direction, which the moment does not carry, so Selection would have to read the cited reading.
- 1C: drop shifts outright for the team lens with `out_of_scope`. Costs: that is a subject/type filter, which is the mechanism D2 says team scope is not.
- 2A: a goal is never rate-limited, because it is the one moment no one should miss. Costs: the rule gets a special case for a moment type, and the type has to come from data, not a name in code, so it would reuse `breakthrough_types`.
- 2B: rate-limit everything, as the brief reads. Costs: with `max_cards_per_10min` at 3, a goal after three shifts is `rate_limited` for casual.

**What I would do if forced:** 1A with a boost of 1.25 and a damp of 0.5, and 2A through `breakthrough_types`. I would also say so in the L2 status. I have not done any of it.

**Answer:** 1B for the reweight (23 Oct): a shift whose subject is the opponent is not damped, and a shift whose subject is the focus team is, by 0.5; goals and chances get a 1.25 boost, clamped to 1.0. 2A for the rate limit (23 Oct): a type listed in the lens's `breakthrough_types` is never rate-limited, though it still counts towards the limit.

## Q21 · The 30–60 moments band only holds on seed 1, at a low threshold  [ticket: M1b]  [blocking: no]

**What I need to know:** Whether to accept how M1b hit the band, or change the band, the generator or the rule. It holds for all four archetypes on the demo match (seed 1), and not generally:

| Moments, seeds 1 / 2 / 3 | comeback | one_sided | tight | scrappy |
|---|---|---|---|---|
| goal + chance + tactical_shift | 57 / 53 / 61 | 52 / 56 / 66 | 52 / 46 / 54 | 32 / 24 / 32 |

- **Tactical shifts are most of them** (25–45 of each match), and they fire at `|z_match| >= 1.25`. At 1.5 scrappy drops to 15–19 and at 2.0 to 10–13. A 1.25σ "shift" is a modest bar.
- **Low-event archetypes have few goals and chances** (scrappy: 2 goals, 2–5 chances), so the count rests on shifts, and no single setting puts all four archetypes inside 30–60 on every seed.
- **M2 only removes moments.** Cooldown and duplicate detection will take every archetype that is near 30 below it, and scrappy is already at 32.
- **Territory `z_match` never exceeds about 1.5**, because its prior spread (0.384) is wide for a 0–1 share, so at a higher threshold it would stop firing altogether.
- **Confidence does not make a post-goal window thin.** `possession_control` has about 0.6 confidence on a one-minute window, so D26's "thin window, low confidence" does not hold for it. I added a minimum window (`spotter_min_window_ms`, 120 s) so the opening minutes and the two minutes after a goal are silent by construction.

**Why I cannot decide it:** the band is yours, and a lower bar for a "shift" changes what a viewer sees.

**Options as I see them:**
- A: keep it as is; the band holds on the demo match, which is what the video and the judges see.
- B: assert the band for seeds 1–3 as well and widen it for the quiet archetypes — I would not do this unasked.
- C: raise the generator's event rate for `scrappy` and `tight` (F3/R2), so the band holds without a 1.25σ bar.

**What I would do if forced:** A, and revisit if M2 pushes scrappy under 30.

**Answer:**

## Q20 · What fires each `MomentType`?  [ticket: M1b]  [blocking: yes]

**What I need to know:** Which of the five `MomentType`s the spotter emits, and what triggers each. The ticket brief's table has three with a clear trigger and two with none:

| Type | Trigger |
|---|---|
| `goal` | an event with `Outcome.GOAL` |
| `chance` | a high `ShotValue` on a shot that was not a goal |
| `tactical_shift` | a signal's `z_match` crossing a threshold |
| `milestone` | **undefined anywhere** |
| `pattern` | **undefined anywhere** |

**Why I cannot decide it:** it changes what a viewer sees (CLAUDE.md, "stop and ask"), and a trigger invented to fill an enum member is a product decision.

**Options as I see them:**
- A: emit `goal`, `chance` and `tactical_shift` only; `milestone` and `pattern` stay in the enum and are never emitted — costs nothing; `Lens.breakthrough_types` can still list them.
- B: define `milestone` (for example a running shot or goal count crossing a round number) as well — costs a trigger definition from you, and it reads event counts, not readings.
- C: define `pattern` as well (for example the same `tactical_shift` repeating) — overlaps M2's duplicate detection, so I would not start here.

**What I would do if forced:** A. The brief calls it "more honest than inventing a trigger".

**Answer:** A (22 Oct). Emit `goal`, `chance` and `tactical_shift` only.

## Q19 · Which z-score fires a moment?  [ticket: M1b]  [blocking: yes]

**What I need to know:** Whether a `tactical_shift` fires on `z_match`, on `z_prior`, or on both. `z_match` is "something changed in this match"; `z_prior` is "this match is unusual", and under D24 and R1 that means unusual *for this generator*, not for football.

**Why I cannot decide it:** it decides which moments a viewer ever sees (CLAUDE.md, "stop and ask").

**Options as I see them:**
- A: fire on `z_match`, let `z_prior` raise importance — the brief's obvious shape. Right after a break `z_match` equals `z_prior` (D26), so the two agree there.
- B: fire on `z_prior` — moments are the match being unusual, so a team that is steadily dominant keeps firing; nothing "changed".
- C: fire on `z_match` and require `z_prior` to point the same way — fewer moments; it may fight the 30–60 band.

**What I would do if forced:** A.

**Answer:** A (22 Oct). Fire on `z_match`; `z_prior` raises importance.

## Q18 · What R1's priors assumed  [ticket: R1]  [blocking: no]

**What I need to know:** Whether these choices in `matchlens/understanding/priors.py` and `scripts/build_priors.py` suit U4.

- **The sample:** an equal split, 5 seeds × 4 archetypes = 20 matches, recorded in `signal_priors.json`. Every measurement for both teams, every match minute, goes in: about 3,600 values per signal, and 1,269 for `chance_quality`.
- **A measurement with `n == 0` is left out.** It saw nothing, so its value is a placeholder: an even share, or no shots. That makes `chance_quality`'s prior the mean of windows that had at least one shot (0.411), not of all windows. U4 should know that a 0.0 reading has no direct comparison in the prior. **Superseded by D28:** empty chance-quality windows are now kept as real zeros.
- **`territory` and `possession_control` have means of exactly 0.500,** because each is a share and both teams are pooled. Their spread (0.384 and 0.163) is the informative part. A per-team prior would need a home/away split, which says nothing about football.
- **`pressing_intensity` is skewed:** mean 5.81, sd 4.06, so a z-score of −1 means about 1.8 passes per action, close to the floor. U4 may want to z-score its logarithm instead. That is your call.
- **Stability:** doubling the sample to 40 moved every mean by less than 0.1 sd. `chance_quality` moved by **0.099**, only just inside the tolerance I set before running it. 20 matches is enough for three signals and borderline for the fourth.
- **`GENERATOR_VERSION = "generator-1"`** in `simulator.py`, pinned by a test beside a digest of what each archetype generates on seed 1. Change the generator and that test fails until the version is bumped and the priors rebuilt. Loading priors from another version raises `StalePrior`.

**Why I cannot decide it:** the brief asks for calibration assumptions to be noted, and U4 is yours.

**Options as I see them:** keep them, or name what U4 needs different.

**What I did, so you can reverse it:** all of the above.

**Answer:**

## Q17 · Retention fixed possession, but no archetype can produce low possession with a high press  [ticket: R2]  [blocking: yes]

**What I need to know:** Which evidence to accept for D10's dissociation claim. Q16's retention parameter is in, and it works for what it does: with `home_retention = 0.8`, home has 59–65% of the passes on seeds 1–3, and `COMEBACK` is byte-identical (digest `2381af553adb82aa` before and after). But the criterion behind Q16 still fails on every seed:

| What I tried, seeds 1–3 | longest spell: away < 40% of passes and pressing harder |
|---|---|
| Brief's shape: away press 0.8, home retention 0.5 / 0.8 / 1.0 | 1–5 min, never 5 on more than one seed |
| Away presses high and cannot keep the ball (away retention −0.5 to −0.8) | 1–5 min |
| Swapped: home on top, pressing high, poor retention; away keeps it | 1 min |
| Brief's shape, counting defensive actions anywhere, not just high up | 0–1 min |

Two reasons, both in how F3 models a match rather than in U3:
- **PPDA counts only actions in the opponent's two-thirds.** In the generator, momentum decides where play happens, so a dominated side's tackles are in its own third and do not count. A side that sits deep reads as passive by definition, which is what PPDA is for.
- **A defensive action is a turnover.** Every tackle and interception by a team starts that team's possession. So a team with less of the ball has, almost by construction, won it back less often, wherever you count.

**Why I cannot decide it:** the options either change an acceptance criterion or change how the simulator models turnovers (CLAUDE.md), and the claim at stake is D10's.

**Options as I see them:**
- A: Keep retention (it gives `ONE_SIDED` real possession dominance). Replace the "sustained spell" criterion with what the generator can honestly show: within each archetype, `possession_control` and `pressing_intensity` correlate weakly (|r| < 0.6) for both teams. U3 already shows r = −0.39 and −0.27 on the comeback. The pitch then says "pressing is measured separately and does not simply track possession", not "a side can press hard without the ball".
- B: Change the turnover model so winning the ball and keeping it are separate. For example, a hard press wins the ball but makes the presser's next pass more hurried, with a parameter defaulting to 0 so `COMEBACK` stays byte-identical. About 0.5 day, and it is a modelling choice made so that the pattern can appear, which should be said plainly.
- C: Keep the criterion and leave it failing, marked as unproven. The claim goes in the pitch as untested.

**What I would do if forced:** A. It claims only what the data shows, and it costs nothing.

**Answer:** A. Kehinde, 20 Oct: keep retention; the criterion becomes a weak correlation (|r| < 0.6) between `possession_control` and `pressing_intensity` for both teams in every archetype, and the pitch claims only that.

## Q16 · The generator cannot make a dominant side keep the ball, so R2 cannot honestly pair low possession with a high press  [ticket: R2]  [blocking: yes]

**What I need to know:** Whether to give archetypes a ball-retention parameter. R2 asks one archetype to sustain low possession with a high press for the same team, which is the evidence for D10's orthogonal basis.

In F3's simulator, momentum and press do different jobs. Momentum steers direction: forward passing, territory, shots. **Who keeps the ball is set mostly by the other side's press**: pass completion is `0.90 − 0.12 × opponent press + 0.06 × momentum`, and a carry is lost at `0.12 + 0.20 × opponent press − 0.06 × momentum`. So pressing hard *wins* possession, and momentum barely holds it. On seed 1:

| `ONE_SIDED` variant | home pass share | shots | away < 40% of passes and pressing harder |
|---|---|---|---|
| momentum 0.75, home press 0.5, away 0.8 (as written) | 0.48 | 19–0 | longest spell 1 min |
| momentum 0.9, home 0.3, away 0.7 | 0.50 | 24–0 | 0 min |
| momentum 0.9, home 0.4, away 0.6 | 0.52 | 32–0 | 5 min |
| momentum 1.0, home 0.25, away 0.6 | 0.49 | 47–0 | 3 min |
| momentum 1.0, home 0.2, away 0.45 | 0.58 | 38–0 | 5 min |

Even fully one-sided, home has about half the passes, and dominance shows only in shots, where away gets none at all. The criterion can just be met on one seed by searching settings, but that is tuning an archetype until the test passes, which R2's brief rules out.

**Why I cannot decide it:** every way out changes the generator or a criterion (CLAUDE.md), and one would change the demo match.

**Options as I see them:**
- A: Add `home_retention` / `away_retention` schedules to `ArchetypeParams`, defaulting to 0, that shift that side's pass completion and carry security. With 0, the code path is unchanged, so `COMEBACK` and the demo seed stay byte-identical (a test asserts it). `ONE_SIDED` then gives home a retention edge, so home holds the ball while away presses high. Costs a generator parameter and ~0.25 day.
- B: Keep the generator, and take variant "momentum 0.9, home 0.4, away 0.6". The criterion passes on seed 1 with a 5-minute spell, and the multi-seed slow tests decide whether it holds. Costs nothing now, but the D10 evidence rests on a borderline spell.
- C: Make momentum count more towards keeping the ball, for every archetype. The most football-like fix, but it changes `COMEBACK`'s bytes, and with them the demo seed and video.

**What I would do if forced:** A. It makes the dissociation a property of how the match is driven, which is the archetype's job, rather than something found by searching settings.

**Answer:** A. Kehinde, 20 Oct: add per-side retention schedules defaulting to 0, with `COMEBACK` byte-identical.

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

**Answer:** A (22 Oct). No Service Bus for now; everything runs in one container. The criterion is deferred to the ticket that splits the containers.

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
