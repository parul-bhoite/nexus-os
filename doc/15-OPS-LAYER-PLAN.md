# doc 15 — The ops layer

**Narrows:** `doc/14` step 10, which named this and deferred it.
**Depends on:** ADR 0030 (coverage), ADR 0033 (a figure that is not a score).
**Blocks:** 23 capabilities — more than accounting, and the largest single dependency in
the registry.

---

## 0. What it is, and the sentence that shapes everything below

`domain/sources.py` already says the important thing, in the entry's own
`cannot_answer`:

> *"anything nobody recorded — **this one fails on adoption, not on an API**"*

Every other source fails on integration: a missing key, a revoked token, a provider that
does not answer. Those are our problems and they have technical fixes. The ops layer fails
when a founder does not type anything into it, which no amount of engineering repairs.

**That is not a reason to build it carefully later. It is the design constraint now**,
because the failure mode is not an empty screen. It is a half-full one.

### The half-adoption problem

A founder records three of their twelve projects. `operations.projects_board` shows three,
which is true. `operations.on_time_dispatch` then computes *"67% on time"* over a third of
reality — a **wrong number with a plausible denominator**, which is precisely the failure
this product exists to prevent, arriving from our own feature rather than from a model.

Crawl and CRM do not have this problem: a crawl reads the page that exists, and a CRM is
authoritative about its own deals by construction. The ops layer is the first source where
**we cannot tell a complete record from a partial one** without asking.

So the first thing this plan needs is not a projects table. It is an answer to *how does
the ops layer know whether it holds everything?* — **D29**, below.

---

## 1. `ops_layer` is not one thing

The ten capabilities that need **only** `ops_layer` — no connector at all — describe at
least seven distinct record types:

| Capability | Needs | Also consumes |
|---|---|---|
| `operations.projects_board` | **projects** — status, progress, at-risk | |
| `operations.task_queue` | **tasks** — assignee, due, overdue | |
| `operations.milestone_timeline` | **milestones** on projects | |
| `operations.issue_register` | **issues** — severity, owner | |
| `operations.on_time_dispatch` | **dispatches** against a promised lead time | `promised_lead_time`, `late_definition` |
| `operations.stock_levels` | **stock items** — on hand against minimum | `stock_posture` |
| `operations.supplier_risk` | **suppliers** — concentration, on-time rate | `supplier_concentration` |
| `sales.deals_lite` | **deals**, "for customers with no CRM" | |
| `operations.score_drivers` | a composite over the above | |
| `executive.todays_priorities` | a ranking across all of it | |

The thirteen others pair `ops_layer` with `accounting`, `crm`, `roster`, `history` or a
tender feed, so none of them can be reached by this work alone.

**Building "the ops layer" as one step is the mistake `doc/14` deferred this to avoid.**
Seven entities, three of which also need onboarding answers, one of which overlaps a table
that already exists, and two of which are composites over the rest.

---

## 2. What changes architecturally

**NEXUS becomes a system of record.** Every source to date is read: a crawl we perform, a
provider we query, answers a founder gave once during onboarding. The ops layer is the
first place a customer **writes into NEXUS and expects it back**, which brings surface this
codebase has never needed:

- Write endpoints with validation, and an audit trail for who changed what — `audit.py`
  exists and has never had to cover customer records.
- `SourceEntry.read_only` is `True` for every connector, and A5 makes write scope a
  separate, heavier ask. That rule is about *other people's systems*; this is about ours,
  and the distinction should be written down rather than assumed.
- Concurrent editing. Two people in one workspace updating the same project is ordinary,
  and the cheap answer — last write wins — silently discards somebody's work.

None of that is hard. All of it is new, and it is why this is a plan rather than a step.

---

## 3. The decisions this surfaces

**D29 — How does the ops layer know it holds everything?** *(blocks every figure)*
Without an answer, a partial record produces a complete-looking percentage. Options: ask
(*"is this all of them?"* per entity, with a date), infer from staleness (nothing added in
N days means we stop computing rates), compute only counts and never rates until the
customer confirms completeness, or mark every ops figure `self_reported` — `doc/05` §0
already has that state, and it exists precisely so a number somebody typed never looks like
one we measured. **My recommendation: `self_reported` plus an explicit completeness
question per entity**, because the two answer different halves — the state says where the
number came from, the question says whether it covers everything.

**D30 — Does `sales.deals_lite` reuse `crm_deal`?** It is described as *"a minimal deal
tracker for customers with no CRM"*, and `crm_deal` already exists with a `provider`
column. Writing them as `provider = 'nexus'` would make `calculators/pipeline.py` work for
both with no new code — and would also mean a hand-typed deal and a synced one sit in one
table, which the `self_reported` distinction says they should not. **Recommendation: reuse
the table, carry the provenance in `provider`, and let the figure's kind differ.** Worth
disagreeing with.

**D31 — Is `operations.score_drivers` a composite, and is it allowed?** It shows *"Score,
delta"* for a department. ADR 0029 and 0030 both refuse a composite over thin coverage at
company level; the same argument applies one level down, and this is the first department
score the product would draw.

---

## 4. Slices

Each delivers a tile a founder can open. None is "build the ops layer".

### S10.1 — Projects and tasks ✅ *shipped 17 September 2026*
The two everything else hangs off. `operations.projects_board` and
`operations.task_queue`, both `ops_layer`-only, both counts rather than rates — so they
are the one pair that can ship **before D29 is answered**, because a count of what was
recorded is true whether or not it is complete.
**Acceptance:** a founder creates a project and a task through the app; both tiles render
from the database; a second member of the workspace sees them and a member of another
workspace does not.

**Asserted by `scripts/ops_walkthrough.py`** — the whole sentence in order, over HTTP,
against Neon: 26 checks, green. Migration `0032` (`ops_project`, `ops_task`, RLS forced);
`retrieval/ops.py`, `calculators/ops.py`, `routes/ops.py`, `/work` and its five BFF
routes. ADR 0034 adds the **count** figure kind, because a count is neither a score nor
an amount and rendering it as either would have put a money shape with no money, or a
denominator, on a tile that has neither. `OPS_LAYER` joins `connected_sources` when rows
exist, which makes these the first capabilities in the product that can reach `live`.

Four things this slice found that were not about the ops layer at all:

- **The Morning Brief called a figured tile unmeasured.** Only a scored audit yields a
  `Computation`, so `sales.pipeline_board` had been announced as *"This could not be
  measured"* above the tile showing its number since ADR 0033. `compose` now takes
  `also_measured`.
- **`coverage` was injected with one dispatch.** The route and its test both passed
  `CRAWL_AUDITS`, so they agreed with each other and not with the product;
  `grounding.compute.MEASURABLE` is now the single set both use.
- **Three standfirsts promised a denominator** the amount and count kinds do not have.
- **The BFF had no `/api/ops` route**, so the page said "Could not read what you have
  recorded" while the whole layer worked end to end. Neither suite can see this — vitest
  mocks `fetch` and pytest calls the API directly. The browser found it.

### S10.2 — Completeness, per D29 ✅ *shipped 17 September 2026*
The answer, applied to the two tiles that already exist. Nothing else should be built until
this is settled, because every later capability is a rate.

**D29 is decided — both halves (ADR 0035).** A completeness question per entity, stored
with a date and append-only, plus self-reported provenance on every ops figure.
Migration `0033` adds `ops_completeness` (RLS forced); `/work` asks *"Is this all of your
projects?"* per entity and the tile turns the answer into a sentence — either *"You
confirmed this is all of them, as of 11 September"* or *"You have not said whether this is
all of them, so this counts the record rather than the company."*

`calculators/completeness.may_compute_a_rate` is the gate, written now though the first
ops rate is S10.4: a rule added after the code it governs is one added after somebody has
already shipped around it.

One correction to the wording of D29's recommendation, argued in ADR 0035: the provenance
travels **on the figure**, not as `WidgetState.SELF_REPORTED`. That state renders quoted
text and no figure (`doc/13` §7, and `hasFigure` returns `false` for it), so setting it
would have blanked the counts S10.1 shipped — and it needs to keep its meaning for D7.

Asserted by `scripts/ops_walkthrough.py`: 34 checks, green, including that confirming
projects does not vouch for tasks and that a confirmation adds no rate to the figure.

### S10.3 — Milestones and issues ✅ *shipped 17 September 2026*
`operations.milestone_timeline`, `operations.issue_register`. Both hang off a project.

Migration `0034` adds `ops_milestone` and `ops_issue` (RLS forced on both) and widens
`ck_ops_completeness_entity` to four entities, so D29's question is now asked of these two
as well.

**`project_id` differs between them, and that is not an oversight.** A milestone's is
`NOT NULL` — a milestone is a point in a project's plan, and one without a project is not
a milestone, it is a date. An issue's is nullable, for `ops_task`'s reason: requiring one
would make somebody invent a project to record a snag, and an invented project then counts
on `projects_board`.

**`planned_on` is `NOT NULL`**, the only required date in the layer. doc/05 6.3 is
*"milestones with planned dates"*, and a milestone with no date is the one thing a
timeline cannot draw — it would silently join the `undated` count on a tile whose whole
subject is when things happen. There is deliberately **no `missed` status**: a missed
milestone is a planned date in the past that nobody marked done, which the calculator
already works out, and storing it too would let the two disagree.

**The issue register is the first figure with a breakdown** — open issues per severity,
worst first. Still a count: ADR 0034 forbids dividing, not grouping, and three counts side
by side say what to look at first without implying a proportion. Every band is rendered
even at zero, because *"no high-severity issues"* is the reassuring thing a reader came
for and an absent row makes them count the list to be sure. The order is the server's;
sorting in the browser would put "high" between "low" and "medium".

Asserted by `scripts/ops_walkthrough.py`: 49 checks, green.

### S10.4 — Dispatches ✅ *shipped 17 September 2026*
`operations.on_time_dispatch` — the first ops **rate**, and the first to need onboarding
answers (`promised_lead_time`, `late_definition`). D29 must be answered before it.

**The onboarding answers turned out to be unusable, and that is D32 (ADR 0036).** Both
facts are collected as free prose — `late_definition` is typed `SINGLE_CHOICE` with no
choices defined, and `AnswerShape.DURATION` is only a *cue* that helps the agent phrase
the question. There is no parser anywhere, and writing one would be inventing a threshold
from somebody's sentence. So the rule is asked for as a **number**:
`workspace.dispatch_grace_days`, nullable with **no server default** — a `DEFAULT 0`
would be a threshold we set for every workspace, silently, producing a confident
percentage under a rule the customer never agreed to.

**Two gates, refusing for different reasons**, and the tile says which: nobody has vouched
the record is complete (ADR 0035), or nobody has said what late means (D32). A third state,
`nothing_sent`, is named separately because the customer has done everything asked and
there is still nothing to divide. **No percentage is served under any of them, and neither
is half a fraction** — half a fraction is an invitation to finish it.

**The counts ship under every refusal.** Orders outstanding and past the promise are true
without either gate, and withholding them along with the rate would tell a founder nothing
when we can honestly tell them something.

`RateFigureOut` is the union's fourth arm (score, amount, count, rate). The denominator is
**what actually went out**, never what was recorded: dividing by the latter reports a
backlog as lateness.

**Still not narratable, and this one is a bounded gap rather than a principle.** A rate has
exactly `narrate-metric`'s vocabulary. What stops it is `domain.narration.describes`, which
is typed to `Computation` and compares a `page` a rate has no equivalent of — and that
comparison is the only thing keeping prose about last week's number beside this week's.

Asserted by `scripts/ops_walkthrough.py`: 67 checks, green, including both gates refusing
in turn and the figure moving when the founder widens the grace.

### S10.5 — Stock and suppliers ✅ *shipped 17 September 2026*
`operations.stock_levels`, `operations.supplier_risk`. Each consumes a fact.

Migration `0036` adds `ops_stock_item` and `ops_supplier` (RLS forced) and widens
`ck_ops_completeness_entity` to the **seven** entities this plan always implied.

**The pair makes the layer's dividing line visible.** Stock is a *count* — "3 of 12 below
their minimum" is true whether or not the record is complete, so the tile works from the
first row. Concentration is a *share*, so it stands behind D29's gate exactly as the
on-time figure does: three of ten suppliers recorded would otherwise report one of them as
60% of the company's exposure.

**Neither fact is consumed, and the records answer them instead.** `stock_posture` ("do
you hold stock, or order per job?") and `supplier_concentration` ("which supplier are you
most exposed to?") are both free prose, like D32's pair. Recording a stock line *is* the
answer to the first; the second asks for a judgement NEXUS now computes, which is the
better way round.

**Ordered by consequence means the shortfall, not the ratio.** Two items each one unit
short — one with a minimum of two, one of two hundred — are the same order to place. A
ratio would also divide by a minimum of zero, a legitimate value meaning "hold none of
this", and rank an item nobody wants above everything else.

**Nothing suggests a reorder quantity**, which would need lead times and consumption this
layer does not hold, and **nothing grades the exposure**: whether 40% with one supplier is
dangerous depends on how replaceable they are, which nobody has told us.

Two shapes had to generalise, both mine from S10.4 — recorded as **ADR 0037**, which
amends ADR 0036's description of the rate figure: `RateComputation` held the dispatch
calculator's own type, and `CountFigureOut` hard-coded "still open" — wrong for stock,
where the same field counts lines under a level. They now carry `RateParts` and an
`open_label`.

Asserted by `scripts/ops_walkthrough.py`: 83 checks, green.

### S10.6 — Deals-lite, per D30 ✅ *shipped 17 September 2026*

**D30 decided: reuse `crm_deal`, partitioned by provenance (ADR 0038).** Hand-typed deals
are `provider = 'nexus'` rows. **No migration** — the column exists, carries no CHECK, and
the unique key already includes it — and `calculators/pipeline.py` is untouched, which was
the whole argument for reuse.

**The partition is what makes reuse safe, and it is the part that was easy to skip.**
`current_deals` previously selected *every* `crm_deal` row and labelled it `provider="crm"`.
Adding typed rows without touching that query would have fed somebody's own typing into
`sales.pipeline_board` as though a CRM had reported it — silently, with no symptom. So
`current_deals` reads `provider <> 'nexus'` and `current_typed_deals` reads the rest.

**The kind is the same and the standing differs.** Both figures are amounts;
`AmountFigureOut.self_reported` decides whether the tile says "Read from your CRM" or
"Counted from what you recorded". Splitting the union again would spend its one mechanism
on something that is not a new kind.

Asserted by `scripts/ops_walkthrough.py`: 91 checks, green, including that the CRM tile
does not see the typed deals at all.

**⚠️ This slice tipped `/dashboards/surface` past the BFF's 30-second timeout on the
development machine.** Measured directly against the API: **31–37 s** for the surface and
**13 s** for `/ops`. The cause is round-trip count, not any one query — the surface now
makes roughly fourteen sequential statements, nine of them `current_ops`, against a Neon
instance this machine reaches in ~2 s per statement. S10.5 rendered; S10.6 added one read
and crossed the line. Co-located with the database this would be well under a second, but
fourteen sequential round trips for one page is a design problem regardless of where the
database sits. **Fixed immediately after, in ADR 0039**: `current_ops` is now one statement with nine
`json_agg` subqueries instead of nine statements, which brought the surface to 17–20 s and
`/ops` to 7–9 s — under the timeout, and still not fast. Five round trips remain on the
surface and the same argument applies to them.

### S10.7 — The composites, per D31
`operations.score_drivers` and `executive.todays_priorities`. Last, because a ranking
across departments is only honest once the things it ranks exist.

---

## 5. Not in this plan

- **The thirteen capabilities that pair `ops_layer` with a connector.** They need
  `doc/14` S11 as well and are not unblocked by this work.
- **Importing projects from anywhere.** An ops layer that could import from Asana or
  Monday would be a connector, and a different plan; this is for customers who have
  nothing.
- **Notifications, assignment workflows, comments.** A project-management product is not
  what the 23 capabilities need — they need records to compute from, and every feature
  beyond that is one more thing to adopt before any figure appears.
