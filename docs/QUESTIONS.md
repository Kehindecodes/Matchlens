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

## Q46 · Card wording: variants, the mirrored possession shift, and a Remontada-shaped demo match  [ticket: none, 26 Oct]  [blocking: no]

**What changed, so you can reverse it:** Kehinde asked for all of it on 26 Oct, so this is a record, not a request.
- Template rows carry `variants`, picked from the card's own id (`templates.variant_for`), so a repeat of a moment type does not repeat its words and the seed still says the same thing. Bodies no longer restate their headline. `MODEL_VERSION` is `templates-4`.
- The writer prompt says each fact once, bans the stock openings, and has an example per depth. `PROMPT_VERSION` is `writer-5`.
- `Suppression` fires one tactical shift for a pair of possession-share readings on the same clock, because possession is zero-sum and both sides' cards said the same thing.
- `REMONTADA` is the demo archetype (`DEMO`), the default of `simulate` and `Replay.from_seed`. `ARCHETYPES` is unchanged, so every test that names an archetype reads what it did. Seed 1 now plays Redfern United 2–0 up, Riverside Athletic pulling one back at 57:59, levelling at 76:41 and winning it at 89:18 on a quick attack won by an interception (8 passes, 20 s). Teams and players stay invented.

- The casual lens's `detail_level` is now `standard`, not `minimal`: it speaks one fact after the opening line (a scorer, a goal count, a quick attack), in words and never a number. This is Q25 part 2, which D30 listed as still open: Kehinde answered it on 26 Oct, that casual viewers get facts too. `full` is a one-word change in `lenses.json` if one fact is too few. Casual still allows only descriptive and interpretive claims, so it hears no score comparison.

- The spotter's moment band is now 25–60, not 30–60. The mirror rule removes 5–7 moments a match (comeback 52→46, one_sided 50→45, scrappy 32→27, tight 44→37), and scrappy fell under the old floor. Kehinde chose to keep the rule and lower the floor on 26 Oct.
- **A card says what the viewer cannot see, not what they are watching (26 Oct).** A goal is headlined by what it did to the score (`opener`, `took_lead`, `equaliser`, `extended`, `pulled_back`), read in `rendering/state.py` from the verified score claim and the scorer, so it adds no fact a claim does not already hold. A run of three big chances is headlined as a run. Those headlines replace the template's opening line, which is gone from every card: no card says "scored" or carries a time any more (the overlay has its own `clock`). A card that has no state falls back to the old rows.
- **Cards are short.** A lens at `full` detail speaks two claims (`claims_spoken_full`), not all of them; catch-up still speaks them all. The claims are heard in the order that says most: a goal's build-up, then the score (the score first for a lens that follows a side); a shift's judgement, then against the other side, then against itself earlier. The earlier-window comparison no longer names its boundary ("before 63:00" is "was 58%"), which weakens D30's "names the boundary" wording rule.
- **New match-state claim:** a chance moment also claims the run of big chances set against the other side's over the same window, when both had one (`claims-3`). It is said only for a clear edge (`wording_chance_edge_ratio`, 2×) and from the side with more.
- **Casual hears comparisons now.** `match_casual` allows `comparative` claims, so it can be told what a goal did to the score, in words and with no number. This reverses a preset that tests pinned ("casual drops comparative claims"); `test_lenses` and `test_selection` now say every depth hears them.
- **A goal's importance follows the score it leaves** (`goal_magnitude`): opening, levelling or taking the lead is full, a two-goal lead or a goal that only trims a gap is 0.7, a lead of three or more is 0.4. Casual's threshold is 0.45, so it leaves out a goal that makes a rout worse; on this match nothing is left out.
- **Prompts:** `writer-6` asks for at most 20 words, never says that the goal or shot happened, and says each fact once. `claims-3` changes the explainer's digest, so its cache misses too.
- **Cards read alone, in one line (26 Oct, second pass).** The page now runs the headline in to the body as one paragraph; the headline is the card's first clause and carries the news. A tactical shift has no separate headline: its first fact is the headline, then one line against the other side. The label-and-number pairs that repeated a label are gone.
- **How a goal or a chance came about, from the log (`claims-4`).** Three new metrics, each recounted by the verifier from `understanding/buildup.py`, the same function the builder uses: `ball_won_third` (1–3 from the winner's own third), `ball_lost` (the player whose event gave the ball away: a turnover possession's last on-ball event, recounted over the whole record because the loss is only one once the other side takes the ball), and `shot_distance` (metres). All 139 claims on the demo pass A3. Casual is told one thing, rotating with the moment (where it was won, or how far out); the analyst is told where it was won, how fast, how far out (`claims_spoken_full` is now 3); a lens that follows a side is told only where its side stands. Catch-up still speaks every claim.
- **Territory shifts are mirrored too** (`_MIRRORED`): both teams' territory shifts on the same minute are one fact. Scrappy falls to 22 moments, so the moment band is now **20–60**. Kehinde asked for the card changes; the band floor moved with them and is his to put back.
- **A chance's importance now counts a run** (`chance_run_magnitude`, 0.6 when it is the third big chance in ten minutes) and `team_engaged`'s threshold is 0.35, so a chance that is only a chance no longer earns the supporter a card.
- **Not built:** substitution and red-card before/after comparisons ("since", never "because"). They need a moment type that fires after the change and a new before/after metric with its verifier recount; that is the next piece of work.
- **The team card tells a supporter who (27 Oct).** `team_engaged` is now `full` detail (three claims). For a goal it speaks the score, then who scored, who set it up (`assist`), and who gave the ball away (`ball_lost`). For a chance it speaks the run and who saved or blocked it (`shot_saved_by`, `shot_blocked_by`), told as "Saved by X" for the side that shot and "X makes the save" for the side that kept it out. Four new metrics, all recounted by the verifier from the log; the demo's claims all pass A3 (`claims-5`).
- **A stopped shot is spotted when it is stopped.** A saved or blocked big chance now fires its moment on the keeper's save or the defender's block, a second or so after the shot, citing both, because who stopped it is not in the log until then (invariant 6). Its moment id is still the shot's. One shot in 188 across the seeds tried, a save at the end of a half with no save event, no longer fires.
- **Names, never positions.** Every sentence names the player and no card says "keeper" or "goalkeeper". A keeper's loss is still its own metric (`ball_lost_by_keeper`, recounted against the roster's `GK`); only the wording is the same as an outfield player's. Say so if you want it said.
- **Four mechanisms from the event log (27 Oct), `claims-6`.** A switch of play (`switch_of_play`, a completed pass that crossed 35 m or more of the pitch's width in the move), an immediate regain (`regain`, the side lost the ball and won it back within 8 s, the other side's possession between), a pressured loss (`pressured_loss`, `ball_lost` on an event the log marks under pressure) and a quick combination (`combination`, two completed passes and the shot between three different players inside 4 s). Each is recounted by the verifier from the log, and all pass on the demo. They say what happened and in what order, never why: the log has no movement, so none claims a run or a cause. Told to a supporter only for their own side's attack. Settings: `claim_switch_min_m`, `claim_regain_max_ms`, `claim_combination_max_ms`.
- **Writer prompt `writer-8`:** a cached answer was an empty passage for a one-sentence prompt; the prompt now says never to answer empty and to return a short natural sentence as it is.

**What I did not do, and it is yours to decide:** the five near-identical chance cards in the My team column come from `max_cards_per_10min` (5) in `lenses.json`, not from wording. Collapsing them, or lowering that number, changes what a viewer sees.

**Cost you will meet:** the explainer cache is keyed on the prompt, so the new match, the new sentences and the new writer prompt all miss it. Rebuild with `python -m matchlens.explanation.cache 1` before the demo, or the delivery app falls back to template words at 25x.

**Answer:**

## Q47 · What a visitor sees after the final whistle, and whether min-1 may go live before that is settled  [ticket: X4]  [blocking: yes]

**What I need to know:** two things. Min replicas 1 is sized and fits the budget (`infra/README.md`), but it changes what almost every visitor sees, which the ticket's cost question does not cover.

1. **What does a visitor see when they arrive after the match has ended?** The container plays the one match in the 3 min 47 s after it boots (measured on the live URL, 26 Oct). With scale-to-zero, the first visitor wakes it and gets that match from kickoff, after a cold start of 27.8 s. With min-1 it boots once, at deploy, and **every later visitor arrives to a finished match.** I loaded the page that way (a fresh tab, long after the whistle) and read the code:
   - The header says `RIV 2 – 1 RED · 94:44 · 2nd half`, with a green "live · 3 of 3 lenses". Nothing says full time.
   - Each panel says `0 cards` and "Watching · nothing worth saying yet · 94:44". Above that is the catch-up (D4) with the three goals, headed **"THE MATCH SO FAR · TO 137:22"**. That number is the live clock, which keeps running after the whistle at the replay speed. At 25× it reads 1,500:00 an hour after boot and about **576,000:00** by 10 November.
   - The only way to see the match in motion is "Watch from kickoff". I checked it on the live URL: it works, restarts that visitor from 0:00, and nobody else is disturbed (D33).
   So with min-1 the ticket's *"a cold browser reaches a working match with no explanation"* fails for nearly everyone, and the default experience gets worse than scale-to-zero, not better.
2. **Running `main.bicep` against the live stack also turns the producer view on.** The running app has no `MATCHLENS_PRODUCER_VIEW`, so `/producer` and its mute controls are off. The file's default is `'true'`, so applying it for min-1 makes `/producer`, `/producer/mute` and `/producer/unmute` public to anyone with the URL. Is that wanted for judging?

**Why I cannot decide it:** Part 1 changes what a viewer sees and when (CLAUDE.md, "stop and ask"), and one option changes the page for a whole class of visitor. Part 2 is a product decision about a control that mutes a lens for every viewer.

**Options as I see them:**

*Part 1, arrival after full time*
- A: **Leave it, min-1 on.** Costs: the failure above for nearly every visitor, and the heading number climbs all window. README would have to tell visitors to press "Watch from kickoff".
- B: **A, plus wording only.** The catch-up stops at the final whistle ("to 94:44") and the header says "Full time" when the last state is the end. Costs: still no match in motion; changes what a visitor reads.
- C: **A page that arrives after the final whistle starts "Watching from kickoff" by itself**, per viewer, with the sessions D33 already makes (the page does what the button does). A visitor arriving mid-match is live as now. The server would say whether the match has ended (a field on `/playback`), and B's wording applies. Costs: a late visitor never sees "live", and replays take 3 min 47 s at 25×.
- D: **The match restarts itself** after it has been over for some minutes with no stream open, which is what scale-to-zero gives for free. Costs: every singleton (hub, router, queues, pipeline) must be rebuilt, and D33 rejected restarting for everyone. Large for a day before submission.
- E: **Do not set min-1.** Scale-to-zero stays and the 28 s first load is documented, as the ticket allows. Costs: a judge who finds a warm container after another visitor still meets a finished match, so C is wanted anyway.

*Part 2, producer view*
- A: leave the default `'true'`; the controls are public for judging.
- B: keep the live setting (off) by running Bicep with `-p producerView=false`, or changing the default.

**What does not need you** (it changes nothing a viewer sees; done on `ticket/X4-judging-hardening`):
- Per-client rate limits, a cap on open streams and on sessions, and a `429`/`503` with `Retry-After` when a limit is hit. Measured: an open stream costs 0.43% of a core while the match plays at 25× (1.6% with none, 44.5% with 100, 98.9% with 300), so the stream cap is 40. A session is 2.8 KiB, so the ceiling is 10,000. They are settings, changeable on the running app without a rebuild.
- `minReplicas` as a Bicep parameter, default 1. It only applies when someone runs the file, not on deploy.
- Measured cold start and full replay in the README, the cost table and the checks of 26 Oct in `infra/README.md`.

**What I would do if forced:** C, and Part 2 B. C is the only option that gives a judge a match from kickoff with no wait and no explanation, and it fixes the warm-container case under scale-to-zero as well. Until it is answered I would not run `main.bicep`. The repo default of `minReplicas` is 1, which the ticket asks for, and the Deploy workflow never applies it, so merging changes nothing live. I have not done C.

**Answer:** Kehinde, 26 Oct: closed for now, not needed for the demo. Nothing was built for Part 1 (arrival after the final whistle) or Part 2 (the producer view). What stands is what is committed on `ticket/X4-judging-hardening`: `minReplicas` defaults to 1 and `producerView` to `'true'` in `main.bicep`, and neither reaches the live app until someone runs the file against it. Not moved to `DECISIONS.md`.

---

## Q46 · What a full-time recap says, where it is shown, and whether it is a new entity  [ticket: X1]  [blocking: yes]

**What I need to know:** three things. X1's brief and Q30's answer disagree, and the brief does not say where a recap appears.

**Where it stands.** D4 already built `catchup.summarise(lens, cards, from_clock, to_clock)`, and D34 says X1 is that function with `to_clock` at the whistle. Run on seed 1 over 0 to full time it works today, with no change. Each lens gets three goal lines in its own words (casual 6 cards shown, team 20, analyst 44; all three summarise to 18', 35' and 78'). The match ended 2–1 to Riverside Athletic, **and no line of any recap says so.**

1. **What does the recap say?** Q30 (your answer, 24 Oct) is *"every viewer should just get only goals, what caused it, how it was scored"*, and it replaced the D4 ticket's "analyst gets the shape of the half". X1's brief asks for something else: casual gets *"the goals and the result"*, the analyst *"the shape of the match in numbers"*, the team lens *"consequence for its side"*. Q30 part 2 (what grouping the analyst reads) was answered for a 68th-minute joiner and not for a whole match.
2. **Where and when is it shown?** The brief says only *"at the whistle, each lens produces a recap"*. Nothing in delivery fires at the whistle today: the last `MatchState` is the whistle, and then the hub only advances the clock for viewers who are behind. `catch_up` is the only summary message and `panel.js` shows it once, above the cards.
3. **Is it a new entity?** `DATA-MODEL.md` lists `Recap` (T3, "may not be built": `recap_id`, `match_id`, `lens_id`, `length_variant`, `body`, `moment_ids`). `CatchUp` is a stream message, "sent, never stored". Building `Recap` is a new entity (CLAUDE.md), and D38 says v1 stores nothing.

**Why I cannot decide it:** Part 1 changes what a viewer reads, and adding a result line or analyst numbers is new wording that no card has said. Part 2 changes when they see it (invariant 8 applies: a viewer 45 s behind must not see the recap before their own whistle). Part 3 is a new entity.

**Options as I see them:**

*Part 1, content*
- A: **Q30's rule unchanged.** The recap is the goal lines (or the top 3 moments with no goals). No new wording. Costs: no line states the result or that it is over, and the analyst recap is three goal cards, not "the shape in numbers". The brief's "key narratives" is three goals.
- B: **A, plus one closing line per lens stating the result**, from template rows keyed on depth and scope, never on a lens (invariant 10). Casual: "Riverside Athletic won 2–1". Team: the same told as consequence for its side (D31). Analyst: the score with the scorers' count. The score is derived from the goal events, and the line cites them. Costs: one new sentence type, and a draw and a goalless match need their own rows.
- C: **B, plus a line of match numbers for the analyst** (shots, `shot_quality`, share of the passes, from `SignalReading`s over the whole match). Costs: new wording, a choice of which numbers (Q30 part 2 again), and every figure must cite its readings. This is the only option that answers "shape of the match in numbers", and the most work.

*Part 2, surface*
- A: **A `recap` stream message in the panel**, shaped like `CatchUp`, sent once per session at that viewer's own full-time position (so 45 s behind means 45 s after the whistle). The demo page already has one panel per lens on its own session, so all three recaps appear side by side with no new page. Costs: a new SSE event name and a small `panel.js` change.
- B: **A, plus a page that lists the three recaps** from the router's kept cards, for the video. Costs: a new page, and it can show a recap before a delayed viewer's whistle, so it would be a producer view only.

*Part 3, entity*
- A: **Reuse `CatchUp`'s shape; do not build `Recap`.** Nothing stored, nothing to keep append-only. `DATA-MODEL.md` keeps `Recap` marked as not built.
- B: **Build `Recap` as a stored row.** Costs: a store D38 says does not exist, and a rule for what a re-run on the same seed does to the rows.

**What does not need you** (it changes nothing a viewer sees, so I build it once you answer):
- The full-time clock comes from the log (the last `period_end`), not a constant, so the recap and the mid-match summary stay one function with a different `to_clock` (invariant 2, D34).
- Tests that every line and every figure in a recap cites a stored moment or claim, that the same function at an earlier clock gives the mid-match summary, and that seed 1 gives a byte-identical recap twice (invariant 9). No model call.
- A lens that showed nothing gets no recap rather than an invented one. A lens that showed little gets a short one.
- No dependency on A3 (D34). The recap does not say "verified"; the claims survived Selection (Q30).
- The walkthrough at `docs/walkthroughs/X1.md` (📝).

**What I would do if forced:** 1B, 2A, 3A. It is the smallest change that makes the recap say the one thing it is missing, the result, and it does not invent a numbers rule the night before submission. It leaves "shape in numbers" for the analyst out, and I would say so in the walkthrough rather than quietly call it done. I have not done it.

**Answer:**

---

## Q45 · Where the verdicts are kept for the rejected-claims view, and which verifications it lists  [ticket: P3]  [blocking: yes]

**What I need to know:** two things P3's brief leaves open. The brief says "the data is already shaped for it" and "this view has nothing to compute; it displays what A3 already had to record". The shape is there (`Verification.checks`, `CheckResult` refusing a `FAILED` without a reason). **The recording is not.**

**What exists today:**
- A3's backlog line says "Verdicts and reasons persist as data (P3)". They do not. `Pipeline._editorial` builds the `Verification`s, uses them to pick the passing claims, hands all four lists to `audit.record(moment, claims, verifications, renditions)`, and that function is a stub that keeps nothing. After the moment, every verdict and every failure reason is gone.
- `audit.record` is already called with exactly what P3 needs, on the editorial thread, in the same process as Delivery (`apps/delivery.py` runs the pipeline in-process until S5).
- P1's report (`MomentOutcome`) carries renditions and lens importance, no claims and no verifications.
- Verifications are made in two places. On the card path, `_editorial` verifies every claim of the moment (L7's, plus A2's if it answered within its deadline). While A2 is down the ladder, `_score_shadows` verifies the answers it asked for anyway, only to score them, and drops them. A claim A2 proposes that fails the schema gate is dropped at source (invariant 5) and never gets a `Verification`, so it cannot appear in any view.
- P1 is built, so the brief's "its dependency on P1 is probably avoidable — ask" is moot: the producer page and its switch (Q43: 4B) already exist.
- A6's drawer (Q42) lists the claims a card *kept*. It does not list rejected ones, and it is built from the card, not from a store of verdicts.

**Why I cannot decide it:** (1) chooses where a derived record is stored and which component owns it, and 1B settles **O4** (Audit in-process or a Function), which DECISIONS lists as OPEN. (2) decides what the view says was checked, and leaving a rejection out of a view whose point is "rejections are not hidden" is a cut. Both are Kehinde's (CLAUDE.md: stop and ask).

**Options as I see them:**

*(1) Where the verdicts are kept*
- 1A: **A producer-only report, like P1's.** The pipeline publishes, per moment, the claims and their verifications beside `MomentOutcome`. `ProducerFeed` keeps them in memory and serves them. Audit stays a stub. Costs: a second thing the pipeline pushes out; the store lives and dies with the producer switch; P5 still has to make Audit real later, and would then hold the same data twice.
- 1B: **Make `audit.record` keep the trail, in memory, in-process.** An `Audit` object is built in `apps/delivery.py` and handed to the pipeline, as `Mutes` and `Ladder` are. It keeps each moment with its claims, verifications and renditions, append-only (invariant 2), and offers read methods. P3's route reads it; P5 reads the same store. Costs: it settles O4 as in-process by implication; Audit becomes the owner of the trail, so a later Postgres-backed one goes behind the same interface (D19); it is lost on restart, as sessions are. Smaller than it sounds, because the pipeline already makes the call.

*(2) Which verifications the page lists*
- 2A: **The ones on the card path** (what `_editorial` verifies). Every row is a claim Selection saw, so every rejection is one that could have reached a card. Costs: while A2 is down the page shows none of A2's rejections, though they were made and scored.
- 2B: **Also the shadow-scored ones**, marked "asked while the model was off the rung; never could have reached a card". Costs: a second call into Audit from `_score_shadows`, a row type to explain, and rejections that no viewer was ever exposed to.

**Decided by me, so you can reverse it:**
- **Who can reach it.** The same switch as the producer view (Q43: 4B) and the same reasoning as Q44's 4A. The route and its script exist only where `MATCHLENS_PRODUCER_VIEW` is on, and nothing on `index`, `watch` or `delay` links to it.
- **Raw values.** It is an audit surface, so it prints the record as it is, calibrated values included, on the same footing as A6's drawer (Q42: 1A). A viewer never gets it.
- **Where it sits.** A page of its own at `/producer/claims`, linked from the producer page, not a section inside it. The brief asks for "a page", and P2's uncommitted changes are in `producer.html` and `producer.js`, so a separate page keeps the two tickets from colliding.
- **No computing in the browser.** The server resolves a claim's subject and metric to labels before sending; the browser prints fields and never derives one. `NOT_APPLICABLE` gets its own label and colour, never a tick.

**What I would do if forced:** 1B and 2A. The pipeline already hands Audit these four lists, and 1B is what P5 needs, so it removes a later rewrite. It does decide O4 for you, which is why I have not done it. Not done.

**Answer:** 1B and 2A. Kehinde, 26 Oct.

---

## Q44 · Where a mute is enforced and recorded, what "later cards" means, what the viewer is told, and who can mute  [ticket: P2]  [blocking: yes]

**What I need to know:** four things P2's brief leaves open. The brief's three properties (later cards only, one lens at a time, a viewer who had cards is told) are not in doubt.

**What exists today:**
- `control.mute` raises and `control.is_muted` returns False. `CardRouter.receive` is the only caller: it asks `is_muted(lens_id, card.display_at_clock)` and drops the card.
- The pipeline never asks Control. `select`'s docstring says `muted` "belongs to Control, which decides before Selection runs", but nothing does. A card the router drops leaves **no suppressed rendition**, so invariant 11 does not hold for a mute. P1's producer view shows what the pipeline reported, so it would read **Spoke** for a muted lens whose card nobody received.
- With a model, a moment's card is published up to 10 s (writer) or 15 s (explainer) of wall time after the moment's clock: 4 to 6 match minutes at 25×. A card for a moment before a mute click can therefore arrive after it.
- There is no stream message for a notice. `last_seen_clock` is set when a card is released to the session, and is None until then.
- Nothing on the delivery app is authenticated (scope guard). The deployed demo has the producer view on (Q43: 4B), and the "Kill the model" button on `/` is public (Q41: 4A).

**Why I cannot decide it:** (1) touches invariant 11 and adds a Pipeline→Control call. (2) and (3) change what a viewer sees and when. (4) is a product and security call. All are Kehinde's (CLAUDE.md: stop and ask).

**Options as I see them:**

*(1) Where a mute is enforced, and whether it leaves a record*
- 1A: **Both.** Before Selection, the pipeline asks Control, and a muted lens gets a suppressed rendition with reason `muted` (invariant 11). The producer view then reads "a producer switched this lens off", and the lens's rate-limit count does not tick. The router's drop stays as the backstop for a card already past Selection when the click lands. Costs: the pipeline now calls Control, which `select`'s docstring already assumes. A card the backstop drops is still unrecorded; I would log it.
- 1B: **Router only**, as the brief's seam. Smallest. Costs: no `muted` rendition is ever stored, so invariant 11 is broken for mutes, and the producer view says **Spoke** for a muted lens.

*(2) What "later cards" means for a card still in flight*
- 2A: **By the moment's clock only**, as the seam is wired. A mute covers `[mute clock, unmute clock)` on the match clock, and a card is muted if its `display_at_clock` is in a window. Deterministic. Costs: a card for a moment before the click can arrive after it and still show, so the mute looks like it missed one.
- 2B: **By clock, and by arrival.** A card is muted if its moment is in a window, or if the lens is muted when the card arrives. The click stops everything not yet delivered, and a moment from inside a mute window that arrives after the unmute is still not back-filled. Costs: whether an in-flight card is muted depends on timing, so a mute mid-run is not byte-for-byte replayable. The seed is still.

*(3) What the viewer is told, and when*
- 3A: **A line in the viewer's own card list, through their release queue, both ways.** "Insights paused · from 51:09" at the mute's match clock, released when that viewer's video reaches it. It follows any cards they are still owed and respects their delay, and is kept in their log so a reconnect resumes. "Had cards" is judged at release from `last_seen_clock`. An unmute is told the same way ("Insights resumed"), only to a viewer who was told of the pause. It shows on every page that has a panel. Wording is yours. Costs: a new entry type in D1's release log and one new stream event.
- 3B: **Immediate, mute only.** Every session on the lens with a `last_seen_clock` is told the moment the producer clicks, with no resume line. Costs: a viewer 45 s behind is told "paused" before the cards they are still owed, and is never told it ended.

*(4) Who can mute, and who the actor is*
- 4A: **The same switch as the view (Q43: 4B), open when it is on.** `POST /producer/mute` and `/producer/unmute` exist only with the view. The producer page gets a Mute and an Unmute button per lens, a required reason box and an actor box (default "producer"). Actor is whatever is typed, since there are no accounts. Costs: on the deployed demo anyone with the URL can mute a lens for everyone watching, as with the kill button.
- 4B: **A second switch for controls**, off in the deployed demo. Judges can read the producer view but not touch it. A mute is shown in the video from a local run. Costs: "a mute mid-demo" cannot be clicked on the deployed URL.
- 4C: **A shared key** typed once on the page. Costs: judges need it handed to them.

**Decided by me, so you can reverse it:** mute is a `ProducerAction` with `action=suppress` and unmute `action=release`, both with a lens `Ref` as the target. RELATIONSHIPS says the target's kind is what tells muting a lens from suppressing a rendition or pinning a moment, so no enum value is added. The log is in-process like sessions, and is read at `GET /producer/actions` and shown on the producer page. P2's buttons live on P1's producer page, which is not merged, so I would branch `ticket/P2-mute-circuit-breaker` from `ticket/P1-producer-view` unless you say otherwise.

**What I would do if forced:** 1A, 2B, 3A, 4A. Not done.

**Answer:** 1A, 2B, 3A, 4A. Kehinde, 25 Oct.

---

## Q43 · Where the producer view's internals come from, what "broken" means, the rung before A5, and who can reach the page  [ticket: P1]  [blocking: yes]

**What I need to know:** four things P1's brief leaves open. Q24 settled how the cards are fed (three sessions, three `EventSource`s); none of what P1 adds on top of that exists on the delivery side today.

**What exists today:**
- A suppressed rendition never leaves `Pipeline._editorial`: with no overlay packet there is no `Card`, and `audit.record` is a stub that keeps nothing. So Delivery holds no suppression reason, no lens-judged importance (`Card.importance` is the moment's raw one; `Selection.importance` is after the lens's reweight) and no rate-limit count (`ShownCards` is private to the pipeline).
- Every lens's rendition is built in one loop inside one `_editorial` call. A lens can lack a rendition only if that call raised, and then all three lack one. With a model the call runs on the editorial thread, and the one place its exception is re-raised is `Pipeline.drain()`, which `apps/delivery.py` never calls. A failed moment today vanishes silently, which is the "looks identical to quiet" state P1 exists to tell apart.
- No rung exists anywhere in the code. A5 is todo, and its brief says it is the "one place that knows the current rung".
- There is no authentication (scope guard), so any route on the deployed URL is reachable by anyone who has the path.

**Why I cannot decide it:** (1) is a new message across the Rendering→Delivery boundary and a new HTTP surface, which is architecture. (2) defines what the ticket's "only real requirement" means, and (2B) would change what viewers get when a lens fails. (3) would drop or defer a criterion. (4) is a product and security call. All of these are Kehinde's (CLAUDE.md: stop and ask).

**Options as I see them:**

*(1) How the internals reach the page*
- 1A: **A producer-only message beside `Card`.** The pipeline publishes, per moment and lens, the rendition (suppressed or not), the importance the lens judged, the cards shown in its last ten minutes and its `max_cards_per_10min`. Delivery keeps them in memory and serves `GET /producer/stream` (SSE). The producer page is `web/producer.html`, reusing `Panel` from `panel.js` with an extra internals block, plus one fourth `EventSource`. Nothing is stored and Audit stays a stub. Costs: a second publish path out of the pipeline.
- 1B: **Make Audit real and read it.** One source of truth, also useful to P5. Costs: far more than P1's day, and it reaches into a ticket that is not this one.

*(2) What "broken" means, since that is the ticket's whole requirement*
- 2A: **Opened and never closed with an outcome.** The pipeline announces a moment with the lenses it expects, then each lens's outcome as it is rendered. `_published` catches an exception, logs it and sends a "failed" close, so nothing vanishes silently. A lens with an opened moment and no outcome is `broken`; one with a suppressed outcome is `quiet`. Viewer behaviour is unchanged: a failed moment still gives no cards.
- 2B: **2A plus per-lens isolation.** A lens whose render raises is recorded broken and the other two lenses' cards still go out. This is closer to "one lens broken, two fine", but it changes what viewers see when something fails.
- 2C: **A timeout.** Broken if no outcome arrives within N seconds of the moment opening. Needs a number I would be inventing, and a slow model reads as broken (D36 already bounds that wait).

*(3) The degradation rung, with A5 unbuilt*
- 3A: **Ship the slot, defer the live value to A5.** The producer snapshot carries a `rung` that is L0 until A5 sets it, and the page shows it only below L0. I would test the display with a constructed snapshot. Costs: the criterion cannot be seen end to end until A5 lands.
- 3B: **Hold the criterion until A5.** Same as 3A without the slot.
- 3C: **P1 keeps its own rung state.** Pre-empts A5.

*(4) Who can reach the producer page and its stream*
- 4A: **Unlinked and open.** No link from `index`, `watch` or `delay`; the URL goes in the submission materials. Anyone who guesses `/producer` sees it. Read-only, and it shows reasons and scores, not claims or ids.
- 4B: **Behind a setting** (`MATCHLENS_PRODUCER_VIEW`), routes not mounted when off. Off by default, on in the deployed demo, so for judges it is 4A with a switch.
- 4C: **A shared key in the URL.** Judges need it handed to them.

**What I would do if forced:** 1A, 2A, 3A, 4B. I have not started and have not created the branch.

**Answer:** 1A, 2A, 3A, 4B. Kehinde, 25 Oct.

**After A5 merged (25 Oct), before any code:** `origin/main` already had A5 (Q41 above), and A6 took Q42, which is why this is Q43. It changes two of the premises above, so these are how the answer was applied.
- **3A (rung).** There is a real rung now, so there is no slot to ship. The producer page shows A5's strip and `ladder` event through `panel.js`, on every rung. Nothing about the rung is held in the producer feed.
- **2A (broken).** A5 stores a Rendering failure as a suppressed `degraded` rendition, so "no rendition at all" is only a moment that fails outside Rendering. `degraded` is shown as broken too, since it is not a lens's choice, and `verification_failed` as an alarm, since DATA-MODEL calls it one. The mapping is the one dict `STATE_OF_REASON`; reverse it there.

---

## Q41 · A5: what can push the ladder below L1, whether A2 shares the rung, the drop and climb rule, and where the rung shows  [ticket: A5]  [blocking: yes]

**What is there today:** A4 already falls back card by card. A timeout, a failed call or an answer the guard rejects gives that one rendition L3's words (Q38). Nothing holds state across cards, so the next goal asks the model again and waits its 10 s. A5 adds that state: one rung for the match, a rule for dropping and a rule for climbing back. The brief leaves four things open.

**1. What can push the ladder below L1.** Under D35, a model failure cannot. L7 and L3 use no model, and "kill the model and the product still works" requires model failures to stop at L1. That leaves only non-model failures.
- A: **Model failures and queue pressure stop at L1.** The ladder goes below L1 only when Rendering itself raises on a moment. That moment's renditions are then stored `suppressed=true, suppression_reason=degraded`, and the viewer keeps the score and clock (L3). Today that same exception kills the moment silently. Costs: L2 is never a separate rung at runtime; below L1 is one state, "could not render".
- B: Also drop L1 → L2 under queue pressure, so cards go blank to catch up. Costs: cards blank under load, which the brief's "do not blank a card, ever" rules out.
- The title's "L0→L4" I read as L0→L3. The build ladder has four rungs, and L4 is the UI ticket.

**2. Is A2 on the same rung as A4?** L0 is A2's extra claims plus A4's words.
- A: **Each model gets its own up/down state, under the same rule.** The rung is the prose rung, L0 or L1, which is A4's state, as D35 says. A2's state shows next to it, "extra claims: on/off". A model that is down is neither waited for nor put on cards, so a goal's card stops waiting 15 s for a dead A2. Costs: while A2 is down, a goal's card ships up to 15 s sooner than it would have, which changes when a viewer sees it. It ships earlier, never before its due time.
- B: One shared state: an A2 failure also drops the prose to L1. Costs: good model words are lost because the other model failed.
- C: A2 is only observed. It goes on being waited for while down. Costs: a dead A2 adds 15 s to every goal card.

**3. The drop and climb rule.** A moment counts as a failure for a model when: its call times out, raises, or returns output that does not parse; A4's guard rejects any lens's text; for A2, more than half of the claims it proposed fail A3 (the brief's "verification failure rate above a bar"); or more than 2 moments are waiting for the editor (queue pressure).
- A: **One failed moment drops the rung. Two good moments in a row climb it back.** While a model is down it is still asked on every goal and chance, but its answer is only scored, never put on a card or waited for. Climbing therefore needs no extra calls, and one good answer between two bad ones does not flip the rung.
- B: Two failures in a row drop it, three good in a row climb it. Costs: the brief says one timeout drops a rung.
- C: Climb on a timer, retrying after 60 s of match time. Costs: a timer at 25× and at 1× means very different things.

**4. Where the rung shows, and how the demo kills the model.** P1 (the producer view) is not built.
- A: **On the three-panel page, which is the producer and judge view P1 will grow from.** A strip reads, for example, "Words: templates (L1), the model is not answering · Extra claims: off". It comes over the stream as a live `ladder` event: a system status, not held back to the viewer's clock. A `ladder.rung` attribute goes on each moment's rendering span. `POST /ladder` with `{"models": "off" | "on"}` makes both models fail as if unreachable, the cache included. A button on the three-panel page calls it. The viewer page `/watch` is unchanged.
- B: Also on `/watch`. Costs: the viewer is told about internals.
- C: No button; the kill is by configuration only. Costs: the forced degradation cannot be shown mid-match in the demo.

**Why I cannot decide it:** (1) chooses when a rendition is suppressed; (2) and (3) change what a viewer sees and when; (4) changes what the deployed page shows.

**What I would do if forced:** 1A, 2A, 3A, 4A. Not done.

**Answer:** Kehinde, 25 Oct: **1A, 2A, 3A, 4A.**

---

## Q40 · No calibrated value on any card; the analyst card says what an analyst can picture  [ticket: A4]  [blocking: yes]

**What I needed to know:** the analyst card printed calibrated values: "shot quality 0.13", "territory share 1", "pressing intensity 10.67", "1.25 or more standard deviations". None of them is readable without a key, and a bare 0–1 shot value invites being read as xG (invariant 12).

**Answer:** Kehinde, 25 Oct, after a brainstorm:
- **No calibrated value reaches a viewer, anywhere.** Shot quality, chance quality and standard deviations are said in words only: "a hard chance, below a big one", "creating better chances than", "pressing much harder than their norm this match". `facts.shown` returns no value for the calibrated metrics, so a row that tried to print one would not be spoken.
- **Plain ratios stay, readably.** A share is a percentage ("58% of the passes", "attacks reaching a final third: 100%"). Pressing is shown as "opponent passes allowed per defensive action", to one decimal place. The overlay stat bar shows the same strings the card said.
- **Unchanged:** goals, scores, passes, seconds, minutes, counts of big chances, the clock. Claims, verification, selection, A2 and the data model are untouched. Templates are now `templates-3`.
- **Bug found and fixed along the way:** pressing intensity is PPDA, which rises when a side presses *less*, but its phrases read the rise as "pressing harder". Every pressing card said the opposite of the record. The phrases now follow the value's direction.
- **Roadmap, not built:** how a goal came about (the giveaway, the finish), what changed after a sub or a red ("since", never "because"), then shape and style. These are written in the README as what MatchLens explains next.

---

## Q39 · A4's first cached run: a misread scorer line, and a goal card that lost its scorer  [ticket: A4]  [blocking: yes]

**What I needed to know:** two things from the first live A4 cache over seed 1.
1. The model turned "Scorer: Finn Norham, a first of the match" into "Finn Norham scored the first of the match", on the third goal. Every number and name traced, so the guard could not see it.
2. The team lens's card for the first goal dropped the scorer. An A2 territory comparison counted as "a comparison between the two sides", which Q28: B speaks first.

**Answer:** Kehinde, 25 Oct:
1. **Both fixes.** The template now reads "his first of the match" (`templates-2`), and the writer's instructions require it to keep the words that decide a fact's meaning (`writer-2`).
2. **Only the score jumps the order.** Q28: B and D31 meant the score. Any other comparison between the sides keeps the explainer's order, so a goal names its scorer unless there is a score to give.
3. **Looser analyst prose, asked for afterwards.** Loosening the instructions alone (`writer-3`, then `writer-4` with a worked example) made the model paste fragments at low reasoning effort. The writer now has its own `writer_reasoning_effort = "medium"` over the same deployment, with `writer-4`'s instructions. Cost: calls are slower live (median 2.5 s, slowest 28.5 s in the rebuild), so more of them miss the 10 s deadline and fall back to L3. The demo is served from the cache and is unaffected.

---

## Q38 · A4: what the model is given beyond claims, whether the trace check runs live, and which moments wait for it  [ticket: A4]  [blocking: yes]

**What I need to know:**

1. **The card's frame is not a claim.** L3's headline and opening line ("Redfern United scored, at 18:54") come from the moment's type, subject and clock. The brief says the prompt gets the surviving claims and nothing else. Also, the casual lens is `detail_level: minimal` and speaks **zero** claims, so under that rule it would have nothing to send.
   - A: **The template keeps the headline and opening line. The model writes only the sentences for the claims L3 would speak.** Casual never calls the model and reads exactly as at L1. Costs: casual has no L0 at all, and on the other two lenses the model rewrites only the claim sentences.
   - B: **The model writes the whole card and is also given a frame: moment type, subject name, clock.** No importance and no triggers. Costs: amends the brief's "nothing else", and the clock becomes a number the model may use that no claim backs.
2. **The trace check: a test only, or also at runtime?** Tests never call a live model, so a test can only exercise whatever check exists, plus the cached demo answers. D22 says a text-side check after Rendering "is a new decision".
   - A: **Runtime guard.** If a number, a name or "xG" in the model's text does not trace to a spoken claim (or to the frame), that rendition falls back to L3's text, and the fallback is logged. A test also covers every cached answer.
   - B: **Test only**, over the cached demo answers. Live text goes out unchecked.
3. **Which moments wait for A4, and for how long.** A4 is one call per lens, made after A2's 15 s deadline, so every enriched card ships later.
   - Which moments: goals and chances only (as with Q37), or every moment.
   - Deadline: past it, L3's text ships. Like A2, the 25× replay serves pre-computed renditions from a cache keyed on the prompt (D36 extended to A4).

**Why I cannot decide it:** (1) amends the brief and changes what a viewer sees; (2) is the check D22 left as a new decision; (3) changes when a viewer sees a card.

**What I would do if forced:** 1A, 2A, 3 goals and chances with a 10 s deadline. Not done.

**Implementation I am taking without asking:** `model` and `model_version` go on `Rendition`, as the brief's provenance criterion asks. L3 renditions carry `model="templates"`.

**Answer:** Kehinde, 25 Oct: **1A, 2A, goals and chances, 10 s.**
- The template keeps the headline and opening line. The model words only the sentences L3 would speak for the lens, so casual (minimal, no claim spoken) is never asked.
- Runtime guard. Any number, number word or name not in those sentences, the banned abbreviation, or "we/us/our" drops the text to L3's.
- Only goals and chances call A4. The deadline is 10 s from when Rendering starts on the moment, and every lens of the moment is asked at once.

---

## Q37 · Putting A2's claims on cards (D36): the deadline, which moments, and the earlier answers it replaces  [ticket: A2]  [blocking: yes]

**What I needed to know:** Kehinde chose to put A2's claims on cards behind D36's per-moment deadline (option B, 25 Oct), which replaces Q32: A (held out until A3; A3 is in) and Q34: A (off the card path). D36 leaves two things open: the deadline's value, and whether only some moments are enriched.

**Answer:** Kehinde, 25 Oct:
- **Deadline: 5 s** from when the moment fired. Past it, the moment's cards ship on L7's claims and the miss is recorded.
- **Amended, 25 Oct: 15 s for v1 and the demo.** The live model's median is 12 s, so at 5 s every live call missed. 15 s lets most land. Production latency is to be handled properly later, not by this number.
- **Selective enrichment: goals and chances only.** Tactical shifts, and any other moment type, get no model call.
- His D36 and ticket edits are committed first on the branch that implements this.

---

## Q36 · `entity` says "on the pitch across the window", but a scorer's `goals` window starts at kickoff  [ticket: A3]  [blocking: yes]

**What I need to know:** What `entity` checks for a player subject.

**The conflict:** the A3 brief says the subject *"was on the pitch across the window"*. L7's scorer claim (D30: *"his second"*) uses the window `[0, clock]`, kickoff to the goal. A substitute who scores was not on the pitch across that window, so `entity` would fail his claim, and fail-closed means the claim is dropped. **6 of the 27 goals across the 12 generated matches are scored by substitutes.**

**Why I cannot decide it:** it changes what a viewer sees, and what `entity` means.

**Options as I see them:**
- A: **On the pitch at the end of the window, and at some point inside it.** Costs: a weaker reading of "across".
- B: **Across the window, as written, and L7's scorer window becomes `[entered, clock]`.** Costs: an L7 change, and claims-1 becomes claims-2 (invariant 7).
- C: **Across the window, as written, and substitute scorers lose the claim.** Costs: 6 of 27 goals lose the scorer line.

**What I would do if forced:** B.

**Answer:** B. Kehinde, 25 Oct: across the window as written; a substitute's goals window starts when he came on.

## Q35 · `value`'s tolerance: D21 left it to you  [ticket: A3]  [blocking: yes]

**What I need to know:** How close a claimed value must be to the recomputed one. D21 lists it under *"Still open, and still Kehinde's"*: *"exact for counts, an epsilon for ratios"*.

**What the evidence says:** the recomputation calls the same functions L7 does, so L7's values match exactly. In the live run, the model copied the digest's full-precision numbers, and 67 of 72 claims matched within `1e-6` relative. A model that rounds fails anything tight.

**Options as I see them:**
- A: **Exact for counts, `1e-6` relative for the rest.**
- B: **Exact for counts, the rest within display precision.**
- C: **Exact for everything.**

**What I would do if forced:** A.

**Answer:** A. Kehinde, 25 Oct: exact for counts, `1e-6` relative for the rest.

---

## Q34 · A live model holds every card for up to 20 s, and half the calls hit that limit  [ticket: A2, A5]  [blocking: before the model goes into the deployed app, or into a local demo run]

**What I need to know:** Whether A2 may hold a moment's cards while it waits for the model, and for how long.

**What happened:** `Pipeline._editorial` calls the model inline, before Selection and Rendering. In the live run over seed 1, **24 of 52 calls timed out at 20 s** (`docs/evidence/A2-live-seed1.txt`). So with a model configured, a moment's cards leave up to 20 s later than they do without one. Because the delivery app drives the pipeline from its event loop, the replay and the scoreboard stall for that time too. The deployed app has no endpoint, so it is unaffected today. But **`.env` on this machine now has one,** so a local `apps.delivery` run is affected.

Under Q32: A, no card shows an A2 claim, so the wait currently buys the viewer nothing.

**Why I cannot decide it:** it changes when a viewer sees a card (invariant 8 territory), and how the ladder (A5) treats a slow model.

**Options as I see them:**
- A: **Take A2 off the card path.** Cards ship with L7's claims as soon as they are ready. A2 runs on its own thread, and its claims go to Verification and Audit when they arrive. Costs: once A3 lands and A2 claims are allowed onto cards, a late A2 claim misses its card, so A5 has to decide whether it waits.
- B: **Keep it inline with a short timeout,** such as 3–5 s, and try lower reasoning effort or a smaller digest to bring the latency in. Costs: still a delay on every moment, and probably fewer A2 answers.
- C: **Leave it inline at 20 s** and accept the delay as the price of A2. Costs: every moment's card waits up to 20 s, and the replay stalls.

**What I would do if forced:** A. It is the D35 logic applied to time: A2 contributing nothing should change nothing, and that includes when a card arrives.

**Answer:** A. Kehinde, 25 Oct: A2 runs off the card path; cards ship with L7's claims, the model's are verified and audited when it answers.

---

## Q33 · There is no model to call: no Foundry deployment exists, and nothing provisions one  [ticket: A2]  [blocking: yes]

**What I need to know:** Which model and deployment A2 calls, and who provisions it. `settings.model_name` and `settings.foundry_endpoint` exist, but both are empty in `.env`, and `infra/main.bicep` has no Foundry or AI Services resource. `agent-framework==1.21.0` and `azure-ai-projects==2.7.0` are pinned and install.

**Why I cannot decide it:** choosing a model is an architecture decision. Adding a resource to the Bicep changes the deployed footprint and its cost. And without a live model, the walkthrough's *"what the model got wrong before it got it right"* would be a guess.

**Options as I see them:**
- A: You create a Foundry project and a model deployment (or tell me which one), and put the endpoint and deployment name in `.env`. I add the resource to `main.bicep` so the deployed app has it too. Costs: your time in the portal today, plus model spend.
- B: I build A2 against a scripted fake client only, and the real client stays untested until you have an endpoint. Costs: the walkthrough cannot say what a real model did, and the demo shows no A2 claims.

**What I would do if forced:** B now and A as soon as an endpoint exists. Everything except the client is testable without one.

**Answer:** B for now. Kehinde, 24 Oct: build against a scripted fake; the real client waits for an endpoint. Then A, 24 Oct: `gpt-5.4-mini` (2026-03-17), GlobalStandard, `matchlens-foundry-kehinde` / project `matchlens`, uksouth. Set up by hand following `docs/FOUNDRY-SETUP.md`; not yet in the Bicep or the deployed app.

## Q32 · Does the model write the numbers, or only choose them? And can an A2 claim reach a card before A3 exists?  [ticket: A2]  [blocking: yes]

**What I need to know:** Two linked things.

1. **What the model emits.** The brief says its response is *"parsed into `Claim` objects"*, so the model writes `value` and `evidence_ids` itself, and A3 recomputes them. The other reading is that code works out the candidate operands from the frozen log (every D30 metric, for each side, over each window D30 allows), and the model only **chooses** among them: which to claim, which comparison, which threshold band. Code then builds the `Claim`.
2. **What happens before A3 lands.** `verify()` is still the stub that passes everything. `_CLAIMS_SPOKEN[FULL]` is `None`, so the analyst lens speaks every claim that passes. As things stand, any A2 claim would reach analyst cards with no one having checked its number.

**Why I cannot decide it:** both change what a viewer sees (an unverified model number on screen). The first also decides whether D35's demo shot exists: *"A3 rejecting an A2 claim while L7's claims stand."* If the model only chooses, its numbers cannot be wrong. A3 could still reject a claim on entailment or coverage, but never on value.

**Options as I see them:**
- A: **The model writes full claims.** They are schema-validated and dropped whole if non-conforming. They are **held out of Selection until A3 is in**: built, logged and audited, but never shown. Costs: A2 adds nothing visible until A3 lands, and A3 is another 2 days.
- B: **The model writes full claims, and A2 recomputes each value and drops any that does not match**, at source, before Verification. Costs: A2 runs part of A3's value check. That is two places owning one rule, which A1 just removed for time. A3 would see no wrong numbers to reject.
- C: **The model chooses among operands that code computed.** Values recompute by construction. The parsed choice is validated, and a non-conforming one produces no claims. Costs: a smaller lesson in what models get wrong, and D35's rejection shot shrinks to entailment and coverage.

**What I would do if forced:** A. It keeps the brief's contract (the model writes claims, A3 judges them) and puts no unchecked number on screen. B and C each give part of A3's job to A2.

**Answer:** A. Kehinde, 24 Oct: the model writes full claims; they are verified and audited but held out of Selection until A3 is in.

---

## Q31 · Which overlay template a card becomes, and how long it stays up  [ticket: D5]  [blocking: yes]

**What I need to know:** D5 says to map rendition shape to `lower_third`, `stat_bar` or `team_card`, and that `duration_ms` is how long the overlay stays up. It does not give a mapping or a duration. Both decide what a viewer sees on the picture and for how long.

**Why I cannot decide it:** it changes what a viewer sees and when (CLAUDE.md, "stop and ask"), and any duration I picked would be a guess.

**Options as I see them:** template by what the card says, by moment type, or always `lower_third`. Duration from reading length, fixed per template, or one fixed value.

**Answer:** Kehinde, 24 Oct: by what it says, and from reading length. A goal is a `team_card`. A card that spoke a comparison of one signal between the two sides, with both numbers, is a `stat_bar`. Anything else is a `lower_third`. Each stays up 250 ms a word, kept between 5 s and 12 s (`overlay_ms_per_word`, `overlay_min_ms`, `overlay_max_ms`). Done in D5. Building it showed that the engaged depth words a comparison without its numbers ("pressing less than ..."), so "with numbers" makes only analyst cards stat bars. The team lens's comparisons are lower thirds.

---

## Q30 · What goes into each lens's catch-up, and what it may say it survived  [ticket: D4]  [blocking: yes]

**What I need to know:** three things, and the brief settles none of them.

1. **Does the casual summary say "goals and nothing else", or "what casual showed"?** Those two are different on seed 1. Before 68:00 the casual lens showed three cards: two goals and *a big chance at 59:00*. The brief says *"a casual joiner gets the goals and nothing else"* and also *"only what their lens would have shown"*. Keeping only the goals is a new rule: a summary that drops some of a lens's own cards by moment type.
2. **What is "the tactical shape of the half" for the analyst?** Before 68:00 the analyst lens showed 27 cards: 17 tactical shifts, 8 chances and 2 goals. Listing 27 headlines is a replay with the bodies taken off, which the brief rules out. A shape means grouping, for example "Riverside Athletic: pressing harder 13:00, 29:00; less of the ball 21:00". That is new wording no card has used. Every line would still cite its moments, but the grouping rule decides what an analyst reads.
3. **O6 is still OPEN, so what does the summary say its claims survived?** A3 is a stub that passes every claim (`verification/__init__.py`), so "verified" would be false. The brief says to state the weaker criterion ("survived Selection") rather than swap it in quietly. I can only state that honestly once O6 says whether A3 is coming.

**Why I cannot decide it:** all three change what a viewer sees on joining (CLAUDE.md, "stop and ask"). Part 1 drops some of a lens's shown cards from its own summary. Part 3 depends on O6, which is OPEN.

**After D34 (24 Oct):** D34 makes the summary panel-only and makes it the same function as X1's full-time recap. It also says the merged X1 "no longer needs the verifier". I read that as: the summary does not wait for A3. Parts 1 and 2 still stand, and part 2 gets bigger. By full time the analyst lens has shown 22–57 cards in each of D30's 12 calibration matches, so the grouping rule decides the analyst recap as well as the 68th-minute catch-up. Part 3 narrows to wording only: is "from the moments this lens selected" the right thing to say while A3 is a stub?

**What does not need you** (no change to what a viewer sees, so I can build it once you answer):
- The summary is built from the cards the session's lens already produced up to its position at join, taken from the router's kept history (D33). So it holds "only what their lens would have shown" by construction. It also inherits the team lens's sided wording (D31) without new framing.
- The split happens at `CardRouter.join`, at one position: cards up to the position go to the summary, cards after it go to the queue. Nothing is summarised *and* sent as a card. Today `_catch_up` runs on first release, at a slightly later position than join, and that gap would cover the same cards twice.
- The summary goes into the session's log as its own SSE event. `Last-Event-ID` already counts that log, so a reconnect does not repeat it. A joiner at kickoff gets no summary at all.
- Built from template rows keyed on depth and moment type, never on a lens (invariant 10).

**Options as I see them:**
- A: **Summarise what the lens showed, grouped by depth's template rows.** Casual: one line per goal (the big chance stays out, because there is no casual catch-up row for chances). Team: one line per goal and per chance, sided. Analyst: goals, then chances, then tactical shifts grouped by team and signal. The template rows decide which moment types a depth summarises, so "casual gets goals only" is a data row, not code. Costs: needs the moment type on `Card` (a stream message, not an entity). Part 1 becomes "only goals" through a data row.
- B: **One line per card the lens showed, headline only, nothing dropped or grouped.** Casual gets 3 lines and analyst gets 27. No new wording. Costs: fails "summary, not replay" for the analyst, and casual gets the chance.
- C: **Cut D4** (T2, first in Phase 5 to cut, with one build day left). Costs: L5's lens switch still shows only later cards, and a late joiner gets nothing about the match so far.

**What I would do if forced:** A. For part 3, the summary would say "from the moments and claims this lens selected", with no "verified" until A3 lands. I have not done it.

**Answer:** Kehinde: *"every viewer should just get only goals, what caused it, how it was scored … if there are no goals, just key moments."* Key moments are the top 3 by importance that the lens showed (`catchup_key_moments = 3`). Done in D4. Each goal is one line from the card the lens showed, with every claim Selection kept for that lens spoken at its depth and from its side, so the casual line now says the scorer and how the move began, with no number. The ticket's "analyst gets the tactical shape of the half" is replaced by this. The summary does not say "verified".

---

## Q29 · Should the score and clock on the page be delayed by the viewer's offset too?  [ticket: D1]  [blocking: no]

**What I need to know:** Whether `MatchState` goes through the per-session delay as cards do.

D1's brief says the hub is *"unchanged for state; cards go through the queue"*, and D1 builds it that way. The consequence: a viewer at a 45 s offset sees the **scoreline change 45 s before their video shows the goal**, and the page clock runs 45 s ahead of their picture. The cards are held correctly; the score next to them spoils the goal they are being held for. `match_state.py`'s own docstring says the opposite of the brief: *"the per-session release (D1) delays the score exactly as it delays a card."*

**Why I cannot decide it:** it changes what a viewer sees and when (invariant 8 is written about cards, and this is the score), and the brief and the docstring disagree.

**Options as I see them:**
- A: leave it as the brief says. The page's score and clock are the live match. Costs: the score spoils the goal; and a panel's "just spoke" reading compares the live clock with the cards' clocks, so at a 45 s offset a card that has just arrived reads as "just spoke" for 15 s of match time, then "quiet for 1 min".
- B: delay each state per session to `clock_ms <= match_clock_now - stream_offset_ms`, sending the latest due state on each tick. The score and the page clock both follow, because they travel in one message. The hub keeps only the latest state today, so it would hold a short history (the largest offset's worth, one state per match second). Costs: the seq in a stream id becomes the seq of the state the viewer is at, not the latest; a little memory per match.
- ~~C: B, and the page shows the viewer's own position as its clock.~~ Withdrawn (24 Oct): the page reads its clock from the same `MatchState` as the score (`web/panel.js`), so B already moves the clock to the viewer's position with no page change. C was B.

**What I would do if forced:** B. It is the rule the cards already follow, and without it the offset protects the cards and not the score. I have not done it.

**Answer:** B for the demo (24 Oct). In production the platform owns the scoreboard, drawn into the video and as late as it is, so MatchLens shows no score of its own; the demo page's scoreboard stands in for it. Recorded as D32.

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
