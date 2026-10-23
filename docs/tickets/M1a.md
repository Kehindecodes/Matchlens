# M1a · Readings on the live path

**Tier** T1 · **Est** 1 day · **Depends on** U4, U5 · **Phase** 3 Spotting
Split from M1 by **D27**. The spotter itself is **M1b**.

## Goal

`understanding.observe()` emits real `SignalReading`s as the stream arrives, so the spotter has something to judge.

## Why this is the harder half

Everything U3 and U4 built is **batch**. The live path is not:

| Built | Shape | What the live path needs |
|---|---|---|
| `epochs.detect(reader)` | Whole finished log → all epochs | A new epoch the moment a goal or red card arrives |
| `signals.cadence(epochs, end_ms)` | Whole match → every reading clock | Noticing a cadence boundary as the clock crosses it |
| `baseline.read(...)` | A whole list of measurements | `baseline.judge(...)` per reading, against history kept between calls |

`observe(item)` therefore has to hold state across calls: the per-`(epoch_id, signal, team)` history that `reference()` reads, the epochs discovered so far, and the last cadence clock emitted. That state is in-process and legitimate — it is not a group A or B row — but it is the first place in the build where a wrong reset is invisible rather than loud.

## What to build

- Real `observe(item: StreamItem) -> list[SignalReading]` in `matchlens/understanding/__init__.py`, replacing the stub that returns `[]`.
- **Incremental epoch detection.** An `Outcome.GOAL` event, an `Action.RED_CARD`, or a period boundary starts a new epoch at that clock. `score_state` and `player_counts` still derive from the log so far (D16) — the reader holds everything up to now, so they need no state of their own.
- **Per-`(epoch_id, signal, team)` history** kept between calls, feeding `baseline.reference()`.
- **The reset is the bug that will bite.** D15 clamps the window to the epoch start and `n` restarts at every boundary. A history that survives a boundary silently averages across a structural break, and D26's post-break behaviour — blending against the offline prior — never happens. Nothing crashes; the z-scores are just quietly wrong for the minutes right after every goal, which is exactly when the best moments fire.
- `priors.load()` at startup. It raises `StalePrior` on a generator mismatch — **let it raise.** A stale prior makes every `z_prior` wrong while nothing looks broken.
- On each cadence boundary: `measure()` for that clock, then `judge()` per measurement, returning the readings.

## Acceptance criteria

- [ ] `observe()` returns real readings, and a full replay produces them at every cadence clock, for both teams and all four signals
- [ ] **Batch and streaming agree.** Replaying a whole match through `observe()` produces the same readings as `baseline.read()` over `measure()` for that match. **This is the criterion that matters most** — two code paths over one definition is how they drift, and this is the only test that catches it
- [ ] History resets at every epoch boundary: `n` and `window_ms` drop at the boundary, and the baseline does not carry across it. Test with a match whose second epoch sits at a visibly different level
- [ ] A reading immediately after a goal has low `confidence` and blends against the prior (D26)
- [ ] `priors.load()` failure is fatal at startup, with a test on the refusal rather than only the happy path
- [ ] No reading cites a `Frame`, and no frame influences a value — all four v1 signals are event-derived (D24, invariant 1)
- [ ] Deterministic: same seed, identical reading sequence
- [ ] `calltrace.entered("Understanding")` still fires

## Definition of done

Criteria pass, `ruff` and `pytest` green, status updated in `docs/BACKLOG.md`.

**This is a usable stopping point.** With M1a done and M1b not, the pipeline emits real readings while S4's hardcoded moment still fires — a worse demo than the plan, but a working one. That halfway point is the reason D27 split the ticket.

## Do not

- Do not judge, threshold or score anything. Deciding which readings matter is **M1b**.
- Do not change what `judge()`, `reference()` or `measure()` compute. This ticket changes *when* they are called, not what they produce — which is what makes the batch-and-streaming test meaningful.
- Do not read frames.
- Do not read `Match.archetype_id` (D25).
