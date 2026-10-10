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

## Q2 · F3's "one event every 3–4 s of in-play time" contradicts its own other numbers  [ticket: F3]  [blocking: no]

**What I need to know:** Which reading of the event-rate criterion you meant. The F3 brief asks for all three of: ~1,800 events, one every 3–4 seconds of in-play time, and 55–65 in-play minutes of a 90-minute match. They cannot all hold: 1,800 events over ~60 in-play minutes is one every ~2 s, and one every 3–4 s over 55–65 in-play minutes is only 825–1,300 events.

**Why I cannot decide it:** it is a criterion in the ticket, and reconciling it is a judgement about the data volume everything downstream calibrates against (CLAUDE.md: any cut or change to a criterion).

**Options as I see them:**
- A: Read "3–4 s" as elapsed match time (~96 min / 1,800 = ~3.2 s). Keeps the 1,800 and the 55–65 in-play minutes. Costs nothing, but the in-play rate is really ~2 s.
- B: Hold the in-play rate at 3–4 s. Gives ~900–1,200 events, which fails "~1,800" and thins the denominators the verifier recomputes from.

**What I did, so you can reverse it:** A. The generated matches land at ~1,800–1,900 events, ~56–60 in-play minutes and ~3.2 s per event over elapsed match time. `test_one_event_every_three_to_four_seconds_of_match_time` encodes this reading.

**Answer:**

