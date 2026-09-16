# ADR 0028 — A narration is asked for, and sits beside the figure it explains

**Status** Accepted
**Date** 16 September 2026
**Decided by** The narration slice, implementing `doc/13` §6's metric block. Recorded
here rather than left in code comments because it fixes both an API contract and what a
tile costs to look at.

## Context

Two marketing tiles now carry a real computed figure — `marketing.seo_gaps` and
`marketing.brand_intelligence`, scored by `calculators/audit.py` from a crawled page.
A figure with no sentence beside it is checkable but not readable: `30 / 65 points · 4 of
9 checks passed` is exactly what was computed and says nothing about whether that is bad.

The `narrate-metric` skill has existed since the skill layer was built and had **no
production caller**. Wiring it raised three questions that had never been settled, and
each of them is a question about money or about honesty rather than about layout:

1. A narration is a model call. **When does the customer pay for it?**
2. It is prose about a number. **Where on the tile does prose go?**
3. It is stored. **What happens when the number it describes moves?**

The third is answered in code by `domain/narration.describes` and is not in dispute. The
first two are decisions, and both were made in a direction that is not the obvious one.

## Decision

**A narration is written only when somebody presses a button, the request is a `POST`
carrying CSRF, and the sentence renders between the figure and the tile's consequence.**

    SEO Intelligence                                    PARTIAL
    30 / 65   points · 4 of 9 checks passed
    Technical SEO. Nine checks on the one page we fetched…
    Measured 2026-09-16 from http://prosoftinformatics.com

    SEO Intelligence scored 30 out of 65 (46%) on the page as      <- the narration
    fetched on 2026-09-16, passing four of nine checks, with
    nothing to compare against yet.
    Explain again

    Needs keyword data.                                            <- the consequence

    + why this number

### Reasoning

**Why `POST`, not `GET`.** `require_csrf` exempts safe methods, and that exemption rests
on a promise: a safe method does not change state. A `GET` that spends tokens breaks the
promise in the act of relying on it, and the route would then be forgeable — a `POST`
worth forging is exactly one that costs money. The reasons compound rather than merely
coexist: the method has to be unsafe for the CSRF check to apply, and the operation has
to carry the CSRF check because it is unsafe.

**Why a button, not automatic on load.** Seven directors' worth of tiles narrating
themselves on arrival would spend a founder's daily allowance on figures nobody looked
at, on a page they may have opened by accident. The cost is per tile and the value is
per tile, so the decision should be per tile too — and the person best placed to make it
is the one reading the number. `Budgets.exhausted` binds either way; the difference is
whether the allowance is spent on what was read or on what was rendered.

**Why beside the figure, not below the consequence.** `BlockCard` already draws a line:
the figure sits above the consequence because the number is what the tile is for, and
"needs keyword data" qualifies it and reads as a footnote to it — where the reverse order
reads as an error with a number attached. A narration is a **gloss on the number**, so it
belongs on the number's side of that line. Below the consequence it becomes a footnote to
a footnote. Inside the working drawer it would be wrong in a different way: the drawer is
the arithmetic, the sentence is a reading of the arithmetic, and a reader who wants one
rarely wants the other.

**Why the prose is a sibling of `figure`, not a field on it.** `FigureOut`'s docstring
says every field there is either the calculator's output or the provenance that makes it
checkable. Prose is neither — it is a model's output *about* that output — and nesting it
would make the figure object partly generated, which is the conflation invariant I1
exists to prevent. The two also have different lifetimes: the figure is recomputed on
every page load, the sentence is stored and can be absent while the figure is present.

**Why a refusal is a `200` with a reason, and never a thrown error.** There is a real,
correct number on screen beside it. A 4xx pushes the client into an error path and tempts
it to render an error state over a figure that is perfectly good — which would make a
missing API key look like a broken score. Per ADR 0011, no model is a *supported* state,
so the copy for `model_unavailable` says the score is unaffected and the button is hidden
rather than disabled: a disabled button reads as broken, an absent one beside an
unchanged score reads as "this deployment does not do that".

**Why no per-tile quota.** `Budgets.exhausted` already binds, is counted from the
`generation` rows themselves in the workspace's report timezone, and returns a named
reason. A per-tile counter would be a second source of truth about spending, and the one
thing worse than an overspend is an overspend nobody can reconstruct.

## Consequences

- **`POST /dashboards/{department}/narrate` is the only route in the codebase that takes
  a capability id from the caller.** Every other surface derives it from the path or the
  registry. That makes the body's capability a new attack surface with no precedent to
  inherit: without a check that the key belongs to the department in the path, a
  Marketing-only manager narrates Finance under a Marketing permission.
  `test_dashboard_narration_scope.py` exists for this and nothing else would catch it.
- **Narration is the first production writer of `generation` rows.** The ledger, its
  budget and its day boundary were previously exercised only by tests — which is why a
  four-hour hole in daily budget enforcement (M33) went unnoticed until a suite happened
  to run at 22:13 UTC.
- **The proxy needs a longer timeout than the rest of the dashboard.** A narration is up
  to two model calls plus a ledger write; on the 30-second default the BFF would abort a
  request the API is still working on and tell the founder we could not reach a service
  that was busy answering them.
- **The sentence is dropped, never labelled, when the figure moves.** To a reader,
  "superseded" and "never explained" both render as the button, and surfacing the
  difference invites showing the old sentence anyway.

## Revisit trigger

Reconsider when any of these becomes true:

- **A tile is narrated on more than half the page loads it gets.** At that point the
  button is friction rather than consent, and a narration written once per new
  measurement — at crawl time, on the worker, charged the same way — costs less than the
  ones a reader asks for. This needs the `generation` row count per module against page
  views, which is available today and nothing reads.
- **Re-crawling lands (M32).** A real `delta` changes what the sentence is *for*: "down
  four points since last week" is worth reading unprompted in a way that "30 out of 65"
  is not, and that is the strongest case for narrating automatically on a schedule rather
  than on a click.
- **A narrated capability consumes a department-scoped fact.** The workspace-wide
  read-back is honest only because the narrator is sent no facts and the reader never
  selects `input_snapshot`. A third capability with an L3 `consumes_facts` would make
  placement the least of the questions and forces the read to be scoped — which in turn
  means an Owner and a department manager can no longer share one stored sentence.
- **Cost stops being effectively free.** `cost_micros` is still 0 and
  `tokens_left_today` is the honest number. If narration becomes a material line item,
  "one button press, one sentence, stored until the figure moves" is the cheap design and
  should be compared against caching or batching rather than assumed.
