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

### S10.1 — Projects and tasks
The two everything else hangs off. `operations.projects_board` and
`operations.task_queue`, both `ops_layer`-only, both counts rather than rates — so they
are the one pair that can ship **before D29 is answered**, because a count of what was
recorded is true whether or not it is complete.
**Acceptance:** a founder creates a project and a task through the app; both tiles render
from the database; a second member of the workspace sees them and a member of another
workspace does not.

### S10.2 — Completeness, per D29
The answer, applied to the two tiles that already exist. Nothing else should be built until
this is settled, because every later capability is a rate.

### S10.3 — Milestones and issues
`operations.milestone_timeline`, `operations.issue_register`. Both hang off a project.

### S10.4 — Dispatches
`operations.on_time_dispatch` — the first ops **rate**, and the first to need onboarding
answers (`promised_lead_time`, `late_definition`). D29 must be answered before it.

### S10.5 — Stock and suppliers
`operations.stock_levels`, `operations.supplier_risk`. Each consumes a fact.

### S10.6 — Deals-lite, per D30

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
