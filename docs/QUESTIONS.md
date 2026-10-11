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

**Answer:**

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
