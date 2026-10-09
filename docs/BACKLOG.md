# Backlog

Dependency-ordered. Tiers: **T1** required to submit · **T2** required to compete · **T3** cut first.

Tickets with a file in `docs/tickets/` are ready to start. Tickets without one have a one-line spec here only — **ask Kehinde to expand it before starting**, because a ticket without a brief has not been thought through yet.

Update the **Status** column when a ticket moves. Statuses: `todo`, `wip`, `done`, `blocked`, `cut`.

---

## Phase 0 · Foundation — days 1–3
*Ships: a seeded match that regenerates byte-identically and replays at any speed.*

| ID | Ticket | Est | Deps | Tier | Status | Brief |
|---|---|---|---|---|---|---|
| F1 | Repo skeleton, module boundaries, config loading | 0.5 | — | T1 | done | ✅ |
| F2 | Match-record models: Match, Team, Player, Event, Frame | 1 | F1 | T1 | done | ✅ |
| F3 | Seeded simulator: frames + ~1,800 events, one archetype | 2 | F2 | T1 | todo | ✅ |
| F4 | Replay harness: load a match, step the clock, variable speed | 0.5 | F3 | T1 | todo | ✅ |

## Phase 1 · Walking skeleton — days 3–5
*Ships: all modules present, mostly stubbed. One hardcoded moment flows source → delivery → browser. **Deployed.***

| ID | Ticket | Est | Deps | Tier | Status | Brief |
|---|---|---|---|---|---|---|
| S1 | Thirteen module stubs with typed interfaces | 0.5 | F1 | T1 | todo | ✅ |
| S2 | Ingest: frame window, event intake, **frame boundary test** | 1 | F3, S1 | T1 | todo | ✅ |
| S3 | SSE endpoint, ViewerSession, page showing clock and score | 1 | S1 | T1 | todo | ✅ |
| S4 | One hardcoded moment → rendition → SSE → card on screen | 0.5 | S2, S3 | T1 | todo | ✅ |
| S5 | Bicep, Container Apps, ACR, GitHub Actions with OIDC | 1.5 | S4 | T1 | todo | ✅ |
| S6 | App Insights, one trace per moment across the agents | 0.5 | S5 | T2 | todo | ✅ |

## Phase 2 · Understanding — days 5–8
*Ships: five signals producing readings with baselines and z-scores.*

| ID | Ticket | Est | Deps | Tier | Status | Brief |
|---|---|---|---|---|---|---|
| U1 | Possession sequencing from events | 0.5 | S2 | T1 | todo | — |
| U2 | ShotValue hand-calibrated lookup | 0.5 | S2 | T1 | todo | — |
| U3 | Five signal functions emitting SignalReading | 2 | U1, U2 | T1 | todo | — |
| U4 | Rolling baselines, shrinkage blend, `z_match` and `z_prior` | 1 | U3, R1 | T1 | todo | — |
| U5 | Epoch detection on goal, red card, half time | 0.5 | S2 | T1 | todo | — |
| U6 | Debug page plotting signals and z-scores over the match | 0.5 | U4 | T2 | todo | — |

**U1** — possession records with pass counts and zone progression; stopped time excluded.
**U2** — every shot carries a 0–1 value with distance and angle kept. Named `shot_quality`, never xG.
**U3** — territory, possession control, pressing intensity, chance quality, line height. `confidence` low on thin samples. Line height and compactness come from the frame window; the other four from events.
**U4** — `w = n/(n+k)`, k ≈ 15 min. At minute 4 the prior dominates; by minute 30 the match baseline does. No z-score flood in the opening minutes. Under **D15**, `n` also resets at every epoch boundary, so this same shrinkage handles the mini cold start after a goal. **Blocked on O9** — what the thin post-break window blends against.
**U5** — readings carry `epoch_id`; a baseline never averages across a structural break. **Unblocked:** D15 clamps the window to the epoch start, so `epoch_id` is unambiguous and no straddling case exists. Implement `window_start = max(clock - nominal_window, epoch.start_clock_ms)`. **D16 also made this possible at all** — `red_card` and `half_time` were epoch triggers that nothing emitted until the match events were added to `Action`. `score_state` and `player_counts` derive from the same log.
**U6** — worth it for your own calibration work, not for judges.

## Reference data — offline, runs in parallel

| ID | Ticket | Est | Deps | Tier | Status | Brief |
|---|---|---|---|---|---|---|
| R1 | SignalPrior from a generated sample | 1 (0.25 lite) | U3 | T1 | todo | — |
| R2 | Four MatchArchetype parameter sets | 0.5 | F3 | T1 | todo | — |

**R1** — mean and stddev per signal with `generator_version`. **Take the lite version:** 20 matches, not 200. Enough to stop the cold-start flood.
**R2** — comeback, one-sided, tight, scrappy, each producing recognisably different matches. P4 needs four to test against.

## Phase 3 · Spotting — days 8–10
*Ships: real moments, scored for importance, firing at times you can defend.*

| ID | Ticket | Est | Deps | Tier | Status | Brief |
|---|---|---|---|---|---|---|
| M1 | Spotter: thresholds, importance scoring, trigger citation | 1.5 | U4, U5 | T1 | todo | — |
| M2 | Suppression: cooldown and duplicate detection | 0.5 | M1 | T1 | todo | — |
| M3 | ~~Run detector from frames~~ | 2 | S2 | T3 | cut | — |
| M4 | ~~Off-ball-run moments and running counts~~ | 1 | M3, M1 | T3 | cut | — |

**M1** — 30–60 moments per match, each citing the readings and events that fired it.
**M2** — the same tactical shift does not fire three times in four minutes.
**M3/M4** — **not built in v1.** Player scope deferred, see D1.

## Phase 4 · Lenses ⭐ — days 10–12
*Ships: three panels on one clock, one visibly silent while the others fire. **The thesis is demonstrable here, with no LLM.***

| ID | Ticket | Est | Deps | Tier | Status | Brief |
|---|---|---|---|---|---|---|
| L1 | Lens entity and three presets as config rows | 0.5 | F1 | T1 | todo | — |
| L2 | Personalizer: scope dispatch, threshold, rate limit | 1.5 | M1, L1 | T1 | todo | — |
| L3 | Template renditions per depth — no LLM | 1 | L2 | T1 | todo | — |
| L4 | Three-panel UI on one clock, silent lens visibly idle | 1 | L3, S3 | T1 | todo | — |
| L5 | Lens switching mid-match | 0.5 | L4 | T1 | todo | — |
| L6 | Team scope: importance reweight + partisan framing | 0.5 | L2, L3 | T1 | todo | — |

**L1** — adding a lens is inserting a row. No hardcoded lens names anywhere.
**L2** — a moment above the analyst threshold and below the casual one produces a `suppressed` rendition for casual (V3). **Scope dispatches to two code paths** — see D2.
**L3** — each lens produces text at its own register from the same claim set, deterministically.
**L4** — an idle lens reads as deliberately quiet, not broken (J3, P1).
**L5** — switch takes effect on the next card, no reload, showing what that lens *would* have shown (V6).
**L6** — needs **no new entities**. Opponent moments still appear; neutral curiosities drop; text states consequence for the chosen side. Switching sides reframes later cards without changing which events exist (V11). **Blocked on O3.**

## Phase 5 · Delivery — days 12–13

| ID | Ticket | Est | Deps | Tier | Status | Brief |
|---|---|---|---|---|---|---|
| D1 | `stream_offset_ms` and the per-session release queue | 1.5 | L3, S3 | T1 | todo | — |
| D2 | Two sessions on different offsets, both correct | 0.5 | D1 | T1 | todo | — |
| D3 | Speed control for the judge path | 0.5 | D1, F4 | T1 | todo | — |
| D4 | Catch-up on join, per lens, verified claims only | 1 | D1, M1 | T2 | todo | — |
| D5 | OverlayPacket endpoint | 0.5 | L3 | T2 | todo | — |

**D1** — release while `display_at_clock <= match_clock_now - stream_offset_ms`. **Delay only, never anticipate** (V8).
**D2** — a 45s-behind viewer and a 5s-behind viewer each get the card at the right point in their own stream. Fold into D1 if cutting.
**D3** — full match end to end in under five minutes, ordering and relative timing intact (J1).
**D4** — a 68th-minute joiner gets only what their lens would have shown; a team-lens joiner is caught up from their side's point of view (V9).
**D5** — machine-readable packets on `display_at_clock`. The broadcast-ready claim, demonstrable.

## Phase 6 · Agents — days 13–16
*Layered over working L1. Never on the critical path.*

| ID | Ticket | Est | Deps | Tier | Status | Brief |
|---|---|---|---|---|---|---|
| A1 | Frozen-log reader: events strictly before clock X | 0.5 | S2 | T1 | todo | — |
| A2 | Explainer agent emitting structured Claims, not prose | 2 | A1, M1 | T1 | todo | — |
| A3 | Verifier: six checks, value recomputation, fails closed | 2 | A2 | T1 | todo | — |
| A4 | Lens-aware generation from each lens's surviving claim set | 1 | A3, L3 | T2 | todo | — |
| A5 | Degradation ladder with automatic fallback L0→L4 | 0.5 | A4, L3 | T1 | todo | — |
| A6 | Evidence drawer in the UI | 0.5 | A3, L4 | T2 | todo | — |

**A1** — a test proves the explainer cannot see the future (V2).
**A2** — claims carry type, metric, value, window and `evidence_ids`. A claim with no citable evidence is dropped at source.
**A3** — citation, temporal, entity, value, entailment, coverage. Verdicts and reasons persist as data (P3).
**A4** — each rendition verified against its own `surviving_claim_ids`, not the moment's full set.
**A5** — mostly free given L1 was built first. Model timeout or queue pressure drops a rung and says so.
**A6** — any card opens to show its supporting events and readings (V7). Cheap, and judges will click it.

**⚠️ 20 October is the last day A2 and A3 could start and land.** If not started by then, raise O6.

## Phase 7 · Producer and automated checks — days 16–17

| ID | Ticket | Est | Deps | Tier | Status | Brief |
|---|---|---|---|---|---|---|
| P1 | Producer view: all lenses live, idle vs broken | 1 | L4 | T2 | todo | — |
| P2 | Mute circuit breaker, ProducerAction log, viewer notice | 1 | D1 | T2 | todo | — |
| P3 | Rejected-claims view with reasons | 0.5 | A3, P1 | T2 | todo | — |
| P4 | Archetype regression check in CI | 1 | R2, U3 | T2 | todo | — |
| P5 | Post-match report, produced unasked | 0.5 | A3, P4 | T2 | todo | — |

**P1** — largely the same component as the J3 demo view. Build once.
**P2** — mute applies to later cards only and never delays what is queued; one lens mutes without the others; a viewer who had cards is told, one who had none stays quiet (P2 story).
**P3** — accepted and rejected both shown. **The clearest multi-agent evidence in the build** — one agent visibly overruling another.
**P4** — signals across four archetypes, readings asserted in range, on every commit. Catches generator/signal co-adaptation.
**P5** — same code as P4 pointed at a finished match. Fold into P4.

## Phase 8 · Submission — days 18–19

| ID | Ticket | Est | Deps | Tier | Status | Brief |
|---|---|---|---|---|---|---|
| X1 | Recap per lens | 1 | A3 | T3 | todo | — |
| X2 | Second language via LexiconEntry | 1 (0.5 lite) | A4 | T3 | todo | — |
| X3 | Demo video, README, pitch | 1.5 | all | T1 | todo | — |
| X4 | Judging-window hardening | 0.5 | S5 | T1 | todo | — |

**X3** — the silent-lens moment is the shot the video is built around.
**X4** — Delivery at min-1 replica, endpoint rate limited, demo renditions cached, budget alert live (J2).

---

## The arithmetic

| | Ticket-days |
|---|---|
| Everything here | ~44 |
| T1 + T2 | ~39 |
| **T1 only** | **~30** |
| T0 — T1 with no agents, L1 prose only | ~25 |
| T0 plus the free cuts below | ~22 |
| **Calendar days available (9–25 Oct)** | **17** |

**T1 does not fit 17 days unless almost all of them are full days.** This is not a reason to abandon the plan; it is the reason the cut ladder is live.

## Cut ladder, in order

1. ~~M3 run detector~~ — **done.** Player scope deferred.
2. **R1 lite: 20 prior matches, not 200.** −0.75. Free, take it now.
3. **P5 folded into P4.** −0.5. Free, take it now.
4. **D2 folded into D1, F4 folded into D3** — both tests rather than features. −1. Free, take it now.
5. **S5: `az containerapp up` first, Bicep later in the week.** −1 off the critical path, costs nothing in the end state.
6. **U3 ships three signals, not five.** −0.8, weakens the orthogonal-basis claim. **Decide by 16 Oct (O5).**
7. **X1 and X2 → lite or gone.** −1.5. Decide by 22 Oct.
8. **Drop to T0: no agents.** −5. Costs the Multi-Agent prize, keeps the thesis. **Decide by 20 Oct (O6).**
