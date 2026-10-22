# M1b · Spotter: thresholds, importance scoring, trigger citation

**Tier** T1 · **Est** 0.5 day · **Depends on** M1a · **Phase** 3 Spotting
Split from M1 by **D27**. The readings it consumes come from **M1a**.

## Goal

30–60 moments per match, each scored for importance and citing the readings and events that fired it.

## ⚠️ Two product decisions. Do not pick them quietly.

**1. Which z-score fires a moment?** Both are on the reading. `z_match` is "something changed in this match"; `z_prior` is "this match is unusual" — and under D24 and R1, unusual *for this generator*, not for football. The obvious shape is **fire on `z_match`, let `z_prior` raise importance**, but that changes what a viewer sees and is therefore Kehinde's call.

**2. What fires each `MomentType`?** The enum has five members and the spotter must choose between them:

| Type | Plausible trigger | Confidence |
|---|---|---|
| `goal` | an event with `Outcome.GOAL` | clear |
| `chance` | a high `ShotValue` that was not a goal | clear |
| `tactical_shift` | a signal's `z_match` crossing a threshold | clear |
| `milestone` | a running count crossing a round number | **undefined anywhere** |
| `pattern` | — | **undefined anywhere** |

Emitting three types and leaving two unused is fine, and more honest than inventing a trigger to fill an enum. Either way it is a decision, not an implementation detail.

## What to build

Real `Spotter.consider(readings, item) -> SpotterResult | None` in `matchlens/spotting/__init__.py`, replacing the stub that fires once at 67:12.

- **Threshold on z-scores, never on raw values.** A possession share of 60% means nothing alone; that it sits 2.4σ above this match's own baseline means something. This is the entire reason U4 exists, and thresholding a raw value would make the readings decorative.
- **`confidence` gates firing.** A large z on a thin window is noise, and D26 guarantees thin windows right after every goal — exactly when a naive spotter floods. A floor on `confidence`, in config.
- **Importance scoring** combining magnitude, confidence and type. One formula in one place in config, not thresholds scattered per signal.
- **Trigger citation.** `trigger_reading_ids` and `trigger_event_ids`. The `Moment` validator already refuses a moment citing neither (invariant 4). Cite what fired it, not everything in the window.
- `subject` is a team in v1; player scope is deferred and the validator accepts either.
- Keep the existing trace span and the `SpotterResult` shape — S6 depends on both.

## Acceptance criteria

- [ ] **30–60 moments on the demo match**, asserted across all four archetypes rather than the comeback alone. This is the calibration criterion and the one most likely to fail first
- [ ] No moment fires below the confidence floor — construct a high-z thin-window reading and assert silence
- [ ] **No flood in the opening minutes, and none in the two minutes after a goal.** Assert both directly
- [ ] Every moment cites the readings or events that fired it, and the citation is the trigger rather than the whole window
- [ ] Importance is comparable across signals: a 3σ territory shift and a 3σ pressing shift score similarly. If one signal dominates the ordering, the formula is wrong
- [ ] Only defined moment types are emitted; the spotter never invents one to fill the enum
- [ ] `model` and `model_version` set on every moment (invariant 7)
- [ ] The S4 hardcoded path is gone, and `calltrace.entered("Spotting")` still fires
- [ ] Deterministic on a fixed seed

## Definition of done

Criteria pass, green, status updated.

**The 0.5-day estimate assumes calibration behaves.** The 30–60 band is where this ticket will fight back; if it does, say so rather than widening the band to fit what the code produces.

## Do not

- Do not write prose, text, or any viewer-facing string. A moment is the judgement that something is worth saying — not what to say.
- Do not read lens configuration. The spotter is lens-agnostic; per-lens relevance is Selection (D17).
- Do not add a signal or a scenario detector. D10: an orthogonal basis, not a library of named situations.
- Do not implement cooldown or duplicate suppression — that is M2.
- Do not read `Match.archetype_id` to tune a threshold (D25). It would pass every test and make the system untransferable.
