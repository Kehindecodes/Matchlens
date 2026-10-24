# Walkthrough template

One file per handed-over ticket, at `docs/walkthroughs/<ID>.md`, written as the **last step of the ticket** — not batched at the end of the build, when the reasoning has already evaporated.

## The rule that makes these worth reading

**Do not describe what the code does.** The code is in the repo and Kehinde can read it. What the repo cannot show is everything that was true *during* the ticket and is invisible afterwards:

- the options that were live, and why the losing ones lost
- what was built first, broke, and had to be replaced
- the thing a reader of the final code would reasonably get wrong
- where mutable state lives, and why it resets exactly where it does
- which test is load-bearing, as opposed to merely present

A walkthrough that paraphrases the diff is worthless. A walkthrough that says *"the obvious approach is X, it fails because Y, so this does Z"* is the whole point.

Aim for 150–400 words. Longer is usually a sign it is restating code.

---

## Template

```markdown
# <ID> walkthrough

**What it does, in two sentences.** No more than that.

## What had to be decided

The choices that were not obvious, with the alternatives. For each: what was chosen and what it cost.

## What broke on the way

What was tried that did not work, and the reason. If nothing broke, say so — that is information too.

## What a reader of this code would get wrong

The non-obvious part. The line that looks redundant and is not, the ordering that matters, the guard that
looks defensive and is load-bearing.

## Where the state lives

Only for anything holding state between calls: what is held, keyed by what, and **when it resets**.
Say what happens if the reset is wrong, because that is the failure that hides.

## The test that matters

Which single test would catch the worst regression, and what the worst regression would be.

## If you change this later

What to read first, and the one invariant not to break.
```

---

## Depth is not uniform

Two things are firsts for Kehinde — **building an event-driven system** and **orchestrating AI agents** — so the tickets carrying those lessons get the fullest treatment:

| Lesson | Tickets |
|---|---|
| Event-driven systems | **M1a** (already built), **D1**, A1, D2 |
| Agent orchestration | **A2**, **A3**, A5 |

Everything else gets the template honestly and briefly. `S6`, `P4` and the rest do not need an essay.
