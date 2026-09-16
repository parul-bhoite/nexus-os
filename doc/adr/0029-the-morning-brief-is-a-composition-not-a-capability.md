# ADR 0029 — The morning brief is a composition, not a capability

**Status** Accepted
**Date** 16 September 2026
**Decided by** Parul, answering D26 — *"go with A, keep them separate"*. Recorded before
implementation because it settles who can see the top of the dashboard, which is an
authorisation question and not a layout one.

## Context

The dashboard is being redrawn as **one common surface with no department tab rail** —
the seven directors become a summary row two-thirds down the page rather than the
navigation that gates it. The first region on that surface is a morning brief.

Three facts collide there:

1. **`executive.morning_brief` already exists** in the registry — `doc/05` §2.1,
   `Block.CARDS`, section `brief` (`app/domain/sections.py:179`). It has never been built.
2. **`/dashboards/executive` is gated to Owner or Executive.** `reachable_director`
   returns a `403` carrying "Owner or Executive" for everyone else, and
   `test_dashboard_narration_scope.py` asserts it.
3. **The brief's material today is workspace-wide and L1** — eighteen checks from
   `calculators/audit.py` over `page_signals`, which is the company's own public website.

So if the common surface's brief *is* `executive.morning_brief`, a Marketing contributor
gets a 403 at the top of their own dashboard, and "common for all" fails at the first
region. And if it is workspace-wide because everything in it happens to be L1 today, it
becomes a cross-department leak the first time a Finance finding enters it — with no code
change to mark the moment.

## Decision

**The morning brief is a composition over the capabilities the reader can reach, assembled
in code, with no model call and no capability id of its own.** `executive.morning_brief`
remains a separate Owner-and-Executive capability for the cross-department version.

    Morning brief                         MEASURED · page audit · 16 Sep 2026
    Eight checks failed                          50 of 135 points not held

    Not served over HTTPS                                      10 POINTS
    prosoftinformatics.com answered on http only. Tied for the
    heaviest check either score can lose.
    seo.https · score_technical_seo · fetched 16 Sep 2026

    Meta description is outside the usable range               10 POINTS
    168 characters. The check passes between 50 and 160…
    seo.description · score_technical_seo · fetched 16 Sep 2026

    Six more checks failed                                5 POINTS EACH
    [title is 137 characters] [10 h1 elements] [no Open Graph tags] …

    Ten checks passed, holding 85 points — the page is indexable, has a
    canonical URL, 51 internal links, a title, a description…

### Reasoning

**Why it cannot be `executive.morning_brief`.** That capability sits behind a department
gate, and the whole point of the redraw is that the surface is common. Widening the gate
is the alternative and it is worse: `executive` is the one department whose remit is
*reading every other department*, so relaxing its guard to let a contributor see a brief
would relax it for everything else the executive surface ever carries. The gate is doing
its job; the brief simply does not belong behind it.

**Why scoped from day one, when everything in it is L1 today.** The narration read-back
is the precedent and the warning. `current_narrations` deliberately has no `scope_key`
filter, and that is honest only because of two much narrower properties — the narrator is
sent no facts, and the query never selects `input_snapshot`. Both had to be written down
and asserted, because neither is visible at the call site. A brief assembled
workspace-wide "because the audit is public" would inherit the same fragility without the
same guards: the day a Finance capability produces a finding, an L3 figure appears at the
top of every contributor's dashboard and nothing in the diff says so. Composing per
`ScopedSession` now costs nothing — today every reader reaches the same two capabilities —
and it is the only version of this that stays correct by construction.

**Why computed in code, and never narrated.** ADR 0011 makes a missing API key a
*supported* state, not a degraded one. The brief sits at the top of every page load for
every workspace, so a model-backed brief means the first thing a founder sees can be
empty, refused, or billed — on a page they may have opened by accident. ADR 0028 put
narration behind a button for exactly that reason, and a brief cannot be behind a button
without ceasing to be a brief. The trade is real and accepted: the copy is templated and
will read more mechanically than a written sentence would.

**Why a ranking, and never a recommendation.** Order is points lost, descending, which is
arithmetic the calculator already produced. `Check.evidence` is specified as *what was
observed* and never as advice — `BlockCard` makes the same argument about its drawer, and
the brief is the highest-traffic place that temptation appears. "0 of 37 images" is a
finding; "add alt text" is guidance nobody computed. The brief may say what a check is
**worth**, because the weight is a number in the code; it may not say what to do about it.

**Why two tiers rather than a top three.** Prosoft's eight failures are two at ten points
and six at five. A "top 3" would cut arbitrarily through a six-way tie; the tiers follow
the weights, so the boundary is in the data rather than in the design.

**Why it says "found" and never "changed".** Nothing re-crawls (M32), so there is no
baseline. A brief headed with a date range, or an item reading "new this week", claims a
comparison that was not made — the same failure `SKILL.md` forbids when it says never to
call a delta flat.

## Consequences

- **Two things are called "morning brief".** The composition on the common surface and
  the capability in the registry. That is a naming hazard in code review and in
  conversation, and the composition should be named something else in code —
  `domain/brief.py` composing `BriefItem`s, not `MorningBrief`.
- **The brief writes no `generation` row**, because no model runs. Its provenance is the
  check ids, which are stable, already rendered, and traceable to `calculators/audit.py`
  without a ledger. This is a *narrower* audit trail than a narrated tile has, and that is
  the right trade for something nobody paid for.
- **The brief has three states, and two of them must not be mistakable.** *Checks failed*
  is the ranking. *All held* states full marks **and its own limits in the same breath** —
  a brief reading "nothing needs you" would be a claim about the business drawn from
  eighteen checks on one web page, which is the category error the composite score is
  already refused for. *Not measured* is the third, and it exists because an audit that
  never ran must not read as an audit that found nothing: the region is never hidden and
  never shows a zero, per I10.
- **A fourth item kind outranks every failure:** *could not measure*, for a capability that
  should hold a figure and does not. It sorts above the ranking rather than into it,
  because a missing measurement qualifies every number beneath it and a low score does
  not.
- **The coverage counts are not yet computed.** "7 unlockable by answering" and "81
  awaiting a source" are tagged `Example` in the design and need a real derivation from
  the registry before they ship.

## Revisit trigger

Reconsider when any of these becomes true:

- **A brief item would come from a department-scoped fact.** The composition is scoped, so
  this does not break — but it does mean two readers of the same workspace see different
  briefs on the same morning, and whether that is obvious enough on screen is then a real
  question.
- **Re-crawling lands (M32).** "Down four points since Tuesday" is worth reading
  unprompted in a way "30 of 65" is not. That is the strongest case for a narrated brief,
  and it should be re-argued against ADR 0011 rather than assumed to have been settled
  here.
- **The brief routinely exceeds about eight items.** At that point ranking by points stops
  being enough and the brief needs a notion of what the reader has already seen — which is
  state, and state is a different design.
- **`executive.morning_brief` is built.** Two briefs in one product need a stated
  relationship, or the cross-department one becomes the same list with more rows.
