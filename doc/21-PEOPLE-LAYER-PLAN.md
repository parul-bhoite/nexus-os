# 21. The people layer

**What this narrows:** `doc/13` §People, and the six `people.*` capabilities the
registry lists as unreachable. `doc/12` still owns product-wide phase numbering.

**Status:** plan only. Nothing here is built.

---

## 0. The sentence that shapes everything below

`domain/sources.py` already says the important thing, in the roster's own
`cannot_answer`:

> *"headcount — **the roster is who uses NEXUS, not who works here**"*

That line was written as a limit on a source. It is really a statement that a
whole entity is missing. `Source.ROSTER` is `Origin.OURS` and sits in `DAY_ONE`,
so every tile that needs it reads as available from the first login — and six
capabilities are declared against it that it cannot answer:

| Capability | What it shows | What the roster holds |
|---|---|---|
| `people.directory` | People, roles, **reporting lines** | no reporting line |
| `people.leave_liability` | What **accrued leave** is worth | no leave |
| `people.document_expiry` | What **expires when** — visas, licences | no documents |
| `people.review_calendar` | When **reviews** are due | no cycle |
| `people.requisition_routing` | Where a **new-hire request** goes | no requisition |
| `people.capacity_utilisation` | **Load per person** | no allocation |

`membership` has ten columns — `role`, `departments`, `designation`,
`stated_department`, the invitation trail — and **not one of them is an
employment record.** A workspace with four NEXUS accounts and forty staff has a
roster of four. Every figure above computed over that roster is wrong by
thirty-six, with a denominator that looks deliberate.

**So this plan is the same shape as `doc/15`, and that is the argument for it.**
The ops layer shipped in seven slices because the entity it needed did not exist
and was built. This is the second one. `Origin.OURS`, the same failure mode:

> *"this one fails on adoption, not on an API"*

### The half-adoption problem, sharper here than in ops

`doc/15` §0 names it: a founder records three of twelve projects and
`on_time_dispatch` computes *"67% on time"* over a third of reality — a wrong
number with a plausible denominator, arriving from our own feature rather than
from a model.

People is worse in two specific ways.

1. **The denominator is a legal quantity.** Accrued leave liability is a number
   a founder may put in front of an auditor. Computed over eleven of forty
   staff it is not merely wrong, it is wrong in a document somebody signs.
2. **The gap is invisible from inside.** A missing project shows as a short
   board. A missing *person* shows as nothing at all — there is no empty row
   where an unrecorded employee would be, so nothing on the screen suggests the
   list is partial.

**D29's answer (ADR 0035) already exists and must be reused, not reinvented.**
`ops_completeness` records a human confirmation per entity, and
`ck_ops_completeness_entity` has been widened three times already — `0033` for
the first entities, `0034` to four, `0036` to seven. A fourth widening is the
cheap, proven move. A parallel `people_completeness` table would be a second
answer to a question already settled.

---

## 1. Two entities, and they are not the same person

The distinction this whole plan rests on:

- **`app_user` + `membership`** — *who can sign in.* Authorising. Set by the
  inviter. Already exists, already governs every permission check.
- **`person`** (new) — *who works here.* Descriptive. Recorded by whoever keeps
  the staff list. Most people in it will have no NEXUS account at all.

They are joined **optionally and in one direction**: a `person` may carry a
nullable `app_user_id`. A `membership` never points at a `person`.

**Why the direction matters.** `CLAUDE.md` is explicit that
`membership.designation` and `stated_department` are what the user typed about
themselves, that they steer what the agent asks and reach nothing, and that
`persona.department` as a field key fails `assert_persona_is_not_authorisation`
at import — by design. A `person` row is the same class of thing, at greater
volume and with more tempting fields. *"Aisha is the Finance Manager"* in a
staff list must never widen what Aisha can read.

**The rule, and it wants its own import-time assertion:** nothing under
`app/domain/access.py`, `session.py` or `retrieval/` may import the people
module. `tests/test_assistant_boundary.py` is the working model for the shape.

---

## 2. What changes architecturally

**The scope lattice gets its hardest test so far.** Every other layer has been
L2 or L3. People is the first where a single table spans three scopes, and where
getting it wrong is a disclosure about a named colleague rather than about the
company:

| Field | Scope | Why |
|---|---|---|
| name, role, department, reporting line | **L2** | a directory everybody may read |
| salary, bank details | **L4** | `sources.py`: *"salaries, which stay L4 whoever is asking"* |
| passport and visa scans, medical, next of kin | **L4 or L5** | see D34 |

`sources.py` already commits to the salary line. It is quoted here because it is
a promise the schema now has to keep rather than a sentence in a ledger.

**Nothing about I2/I3 changes.** People rows are read through `retrieval/`, the
predicate stays in the query, and no function gains a `user_id` argument. What
is new is that a single **row** carries fields at different scopes, which the
chunk-level lattice has not had to express before. **This is D33, and it is the
decision that blocks the schema.**

---

## 3. The decisions this surfaces

Four, and the first two block the first slice. **None should be invented** —
`CLAUDE.md`'s rule, and the reason `DECISIONS-REQUIRED.md` exists.

### D33 — How does one row hold fields at three scopes?
**Blocks:** S11.1, and therefore everything.

- **A. One table, column-level scope in code.** Simplest schema; the predicate
  cannot express it, so a `SELECT *` anywhere leaks salary. Rejected on sight
  unless a reader can explain how RLS enforces it.
- **B. `person` at L2, `person_sensitive` at L4, one-to-one.** The predicate
  works unchanged because scope is a property of the row again. Two tables, two
  reads, and the join is the thing to get wrong.
- **C. `person` at L2 plus per-field rows in an existing scoped store.** Most
  flexible, least readable, and a salary becomes a string.

**Recommendation: B**, because it keeps the guarantee where every other table in
this product keeps it — in the row, enforced by a policy, not by remembering to
select the right columns.

### D34 — Is a passport scan L4 or L5?
L4 is *restricted, reachable by being named*. L5 is *personal, uploader-only*.
A visa scan is about an employee, held by the company, and read by whoever
handles renewals — which is L4 by the lattice's own definition and L5 by
instinct. The tile that needs it (`document_expiry`) only needs the **date**,
never the scan, which may make this narrower than it looks.

### D35 — Does the people layer answer headcount?
The roster's `cannot_answer` says no. Once `person` exists the answer becomes
*"yes, for the people somebody recorded"* — which is the half-adoption problem
wearing a number. D29's confirmation mechanism is the candidate answer; this
decides whether headcount is gated on it.

### D36 — Who may record and edit a person?
Not a role that exists today. Owner-only is safe and makes a forty-person list
one person's job; a department manager editing their own reports is the obvious
shape and is also how somebody grants themselves a reporting line.

---

## 4. Slices

Each delivers a tile a founder can open. None is "build the people layer".

### S11.1 — `person`, and the directory
**Blocked on D33, D36.**

The entity everything hangs off, and the one tile that is a **list rather than a
rate** — so it can ship before D35 is answered, for the same reason
`projects_board` could ship before D29: a list of who was recorded is true
whether or not it is complete.

`people.directory` shows people, roles and reporting lines. The reporting line
is a nullable self-reference; a cycle in it is a check constraint, not a
convention, because an org chart that loops renders forever.

**Acceptance:** a founder records three people, one of whom has a NEXUS account
and two of whom do not; the directory renders all three from the database; a
member of another workspace sees none of them; RLS read from `pg_class` as
**enabled and forced**, not inferred from the migration having run; and an
import-time assertion proves no permission module reaches the people package.

### S11.2 — Completeness, per D35
**Blocked on D35. Nothing below should be built until this is settled**, because
every later capability is a rate — exactly `doc/15` S10.2's position, and for
exactly its reason.

Widen `ck_ops_completeness_entity` a fourth time rather than adding a table.

**Acceptance:** an unconfirmed people list renders its count and refuses every
rate with the named state; confirming it releases them; the refusal names what
would change it.

### S11.3 — Document expiry
The first tile with a real deadline in it, and the one a founder in Oman will
open first — a visa that lapses stops somebody working.

Per D34 this may need only dates, in which case no scan is stored and the whole
L4/L5 question narrows to a column rather than a file.

**Acceptance:** a document with an expiry inside the window appears with its
date; one outside does not; nothing renders a **days-remaining** figure that a
calculator did not produce (I1); and a caller who may not reach the document's
scope gets the same named state as one whose workspace has no documents —
`evals/test_assistant_scope_leak.py` is the model for asserting that as
*byte-identical*, which it now has machinery for.

### S11.4 — Leave liability
**The first money figure this product computes from its own records**, and the
one with the legal denominator. Accrual is per-company policy, so the policy is
an input somebody supplies, never a default — a default accrual rate would be an
invented number with a plausible source, which is I1's exact failure.

**Acceptance:** with no accrual policy recorded the tile refuses and names the
missing input; with one, the figure traces to a `generation` row naming the
policy and the balances it used.

### S11.5 — Review calendar and requisition routing
Both are workflow rather than measurement, and both are cheap once `person`
exists. `review_calendar` shows *"nothing at all where there is no cycle"* —
which is already the honest empty state the registry promises.

### S11.6 — Capacity and utilisation
**Last, because it is the only one that needs two layers.**
`people.capacity_utilisation` and `operations.capacity_utilisation` both require
`ops_layer` **and** `roster`, so they are half-adoption squared: a rate over
recorded people and recorded tasks, wrong if either list is partial.

**Acceptance:** the tile refuses unless **both** layers are confirmed complete,
and the refusal says which one is missing.

---

## 5. Not in this plan

- **Payroll.** Computing a payslip is a regulated calculation per jurisdiction.
  Storing a salary is not running payroll, and the line is worth stating before
  somebody assumes the second follows from the first.
- **An HRIS connector.** `Origin.OURS` is the whole point: this fails on
  adoption, and importing forty people from a system the customer already uses
  is a different plan with a different failure mode.
- **Performance ratings.** `review_calendar` schedules reviews; it does not
  record their outcome. Ratings are L4 about a named person and want their own
  decision.
- **Anything that widens what a person may read.** Stated once more because it
  is the mistake this plan is most likely to invite.
