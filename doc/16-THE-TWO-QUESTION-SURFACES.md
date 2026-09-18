# 16 — The two question surfaces, and how they are bridged

**Status** Decided, not built. The three decisions in §11 were Parul's and are
**answered** (18 September 2026); §11 now records what was chosen and why, and
§10 is unblocked. **The final shape requires no migration** — see §11.4.
**Narrows** `doc/08` §12 item 1, which names this gap and defers it here.
**Governed by** ADR 0020 (the bank), ADR 0021 (a generated question names a
declared field), ADR 0030 (coverage is counted by who is blocking).
**Decided in** ADR 0044.

---

## 0. The problem, in one paragraph

Two surfaces collect the same operating facts from the same person and write them
to two tables in two key spaces. The dashboard's *"unanswered questions"* counter
reads one of them and, since one recent change, half-reads the other. The
capabilities that actually consume those answers read only the first. So a founder
can answer every operational threshold in the chat interview, watch the counter
fall to zero, and the tile that needed the threshold still has nothing — with
nothing on any screen saying so.

**This document is about the join between two catalogues, not about a new
feature.** No new question is asked and no new number is shown.

---

## 1. The two surfaces, as data

| | **Bank surface** | **Interview surface** |
|---|---|---|
| Catalogue | `domain/question_bank.py` — 29 `Question`s, 5 per department × 6 | `ai/runtime/fields.py` — 35 `FieldSpec`s (7 brain, 6 persona, 22 fact) |
| Renderer | The department block (`routes/spine.py`), the settings portal | The agentic interview (`domain/onboarding_agent.py`, `routes/onboarding_agent.py`) |
| Key space | Bare bank key — `approval_threshold` | Dotted catalogue key — `fact.finance.approval_threshold` |
| Writes to | `onboarding_answer` | `fact`, via `domain/onboarding_promotion._record_facts` |
| Carries department | Yes — `onboarding_answer.department` | No column. Only `FieldSpec.department`, in code |
| Carries scope | Yes — `onboarding_answer.scope` (`L2`/`L3`/`L4`) | No column. Only `FieldSpec.scope`, in code |
| Carries review state | Yes — `answer_state` ∈ {`bound`, `proposed`} | No column. Every row is implicitly binding |
| Supersession | A new row; `company_brain.build` reads in `created_at` order | `fact.superseded_by_id` + `brain_version` |
| Who may write | `may_answer_department_question` (Q30/D16) + `state_for_answer` (Q31/D22) | **Today:** any authenticated member — the routes carry `CurrentScope` and CSRF and **no role check**. **After step 5:** `may_answer_department_question` for `fact.*` targets only (§11.3) |
| Declares its consumer | Yes — `Question.consumed_by`, validated against the registry | No |

The "who may write" row is the only line in this table that step 5 changes. Every
other asymmetry — the key space, the missing `department`, `scope` and review-state
columns on `fact` — **stays exactly as it is**, because the chosen design filters at
read time and gates at write time rather than adding columns. See §11.4.

Both are *correct in isolation*. The bank was built for a form where every
question exists before anyone answers; the catalogue was built so a model-worded
question has a scope that does not come from the model (ADR 0021). Neither was
built to be the other's index.

---

## 2. What is already bridged, and it is exactly one place

`routes/dashboards.py::answered_questions` reads both tables and translates:

- `_ANSWERED_SQL` → `(department, question_key)` pairs from `onboarding_answer`,
  filtered by `BINDING_ONLY_SQL`.
- `_PROMOTED_SQL` → live `fact` keys on the current `brain_version`, each looked
  up in `FIELD_CATALOGUE` and added as `(spec.department, spec.question_key)`.

Every counter in that module — `DirectorSummary.unanswered_questions`,
`DirectorRowOut.unanswered`, `open_questions.compose` — takes that one frozen set
as a dependency, so within `dashboards.py` the two surfaces already agree.

**The join lives on `FieldSpec.question_key`, not in a mapping table.** That is
right and this document does not reopen it: a third table is a third thing to
keep in step with two that already drift.

---

## 3. What is not bridged — four read sites in the same key space problem

The bridge answers *"has this been answered?"*. Nothing answers *"what was the
answer?"* across the boundary.

| # | Read site | Reads | Consequence |
|---|---|---|---|
| 1 | `grounding/context.py::facts_for` | `Capability.consumes_facts` holds **bank keys**, inverted from the bank at import. Promoted facts land in `CompanyContext.facts` under **catalogue keys** | **No `consumes_facts` key can ever match a promoted fact.** The tile cannot say *"you told us a lead is X"* |
| 2 | `routes/dashboards.py::director_setup` → `_facts_for` | `context.department_facts`, built from `onboarding_answer` only | The Setup tab shows the department's answers and silently omits every interview answer |
| 3 | `routes/spine.py` department block | `onboarding_answer` only | The block re-asks a question the interview answered — while the counter on the same page says it is done |
| 4 | `domain/company_brain.build` | `onboarding_answer` only | Interview department answers never reach the built Brain by this path |

**Read site 1 is the one that matters.** `facts_for` omits a missing key rather
than defaulting it — deliberately, and correctly, because "substituting a
plausible value here is exactly how an unanswered question turns into a confident
number". So the capability computes without the threshold, quietly, and the
counter has already stopped naming the founder as the blocker.

Measured against ADR 0030's rule — *coverage is counted by who is blocking* — the
current state reports the founder as not blocking a fact that is, from the
consumer's side, still missing. **That is a worse failure than the one the bridge
fixed, because the old one was visible and this one is not.**

---

## 4. Are they asking about the same facts? Partly. The split is the design.

Not a full bridge. Three classes, and the numbers are the point:

**A — 19 bank questions with a `fact.*` counterpart.** Bridgeable, and already
declared: finance 3, sales 3, operations 3, marketing 2, HR 5, strategy 3.

**B — 10 bank questions with no catalogue counterpart.** `acquisition_budget`,
`lost_to`, `arabic_in_scope`, `lead_assignment`, `quota_period`, `payment_terms`,
`common_delay_cause`, `stock_posture`, `success_in_twelve_months`,
`watched_competitors`. The interview cannot answer these, so they stay
outstanding, which is correct — nothing has answered them.

Three of the ten are worth naming separately, because they *look* bridgeable and
are not: `lost_to` and `watched_competitors` are the same fact as
`brain.competitors`, and `success_in_twelve_months` is the same fact as
`brain.goals` — the wording in `fields.py` is lifted verbatim from the bank. They
cannot be bridged by `question_key` as it stands, because brain fields promote to
`company_brain` **columns**, not to `fact` rows, so `_PROMOTED_SQL` would never
see them. Bridging them is a different mechanism and is out of scope here (§9).

**C — 3 catalogue fields with no bank question.** `fact.executive.*`. The bank has
six departments and no executive block (ADR 0020), which `doc/13` defect 26
already records as an open design question. These must never mark a bank question
answered.

**19 of 29 is the ceiling of this design, and the doc should say so rather than
imply parity.** A reader who assumes full coverage will read ten correct
"outstanding" lines as a bug.

---

## 5. Three findings that change the shape of the fix

### 5.1 The consumer-side gap (§3, read site 1)

Already stated. It is the reason the fix cannot be "add more of what
`answered_questions` does" — the counter is not where the value is needed.

### 5.2 An L3 answer is stored with no scope, in a table with workspace-only RLS

`fact` (migration 0022) has `workspace_id`, `key`, `value`, provenance,
confidence, precedence, confirmation and supersession — and **no `department`
column and no `scope` column**. Its RLS policy is workspace isolation only.

`FieldSpec.scope = 3` for every `fact.*` department field, and ADR 0021 calls the
catalogue *"a security-relevant file"* whose scope *"deserves the same review as a
migration"*. That scope is enforced when the question is asked and is lost the
moment the answer is written. `context.assemble` then places every `fact` row in
the workspace-wide `facts` group, which `_reachable_departments` does not filter.

Today this is unreachable **by accident**: the key-space mismatch in §3 means no
capability can name a `fact.*` key. So the missing bridge is currently the only
thing preventing a cross-department read of L3 interview answers. **Closing the
bridge naively opens that read.** Any design that joins the two spaces has to
decide where the department filter goes before it joins them, not after.

### 5.3 The interview routes around the review gate (Q31/D22)

`BINDING_ONLY_SQL` exists because "a proposed answer that is merely *flagged* is
not protected: the flag only works if nothing reading facts can see it, and one
caller forgetting the filter would silently let a Contributor bind a fact for
their whole department."

`_PROMOTED_SQL` has no equivalent filter and cannot have one — `fact` has no
`answer_state`. The interview routes carry no role check. So a Contributor who
runs the interview writes `fact` rows at `user_confirmed`, precedence-ranked above
a connected system, and the bridge counts them as binding answers to that
department's questions. The department block would have held the same answer as
`proposed` and waited for a Manager.

This is live today for the counter, and would extend to the *value* the moment
read site 1 is bridged. It is a change to who may bind a department fact, so it was
not this document's to decide. **It is decided in §11.3: the interview routes are
gated, rather than `fact` learning a review state.** The consequence of that
direction is that `_FACTS_SQL` still needs no `BINDING_ONLY_SQL` equivalent — not
because proposed facts are filtered out, but because after step 5 **a proposed
`fact` row is never written in the first place.** A caller who may not answer for
the department is refused at the route; nothing lands to be filtered.

---

## 6. The decision

Recorded in **ADR 0044**, in short: `question_key` stays where it is and becomes a
**validated, bidirectional link**, and the translation between the two key spaces
moves out of `routes/dashboards.py` into one domain module that both the counter
and the grounding context call. Promoted facts are surfaced to capabilities under
their **bank** key, inside `department_facts[spec.department]`, so
`Capability.consumes_facts` resolves unchanged and the existing
`_reachable_departments` filter does the department scoping that §5.2 says is
missing.

Three alternatives were rejected on their merits: dual-writing the interview into
`onboarding_answer`; collapsing the two catalogues into one; and leaving the
counter reading `onboarding_answer` only. A fourth — promoting a Contributor's
interview facts as *proposed* and holding them at the review gate — was rejected
for a **different reason**: it is a defensible design that requires an
`answer_state` column on `fact`, and the migration it implies was declined
(§11.1). The reasoning and what would reopen each is in the ADR.

**No migration is part of the decision, not an accident of it.** All three
answers in §11 were chosen on the no-migration side, and §11.4 states what that
costs.

---

## 7. Invariants this design must not break

1. **`stated_department` never authorises anything.** The bridge reads
   `FieldSpec.department`, which is a structural property of the field, never the
   answerer's self-reported department. `askable_fields(department)` keeps
   steering *what is offered*; it must not start deciding what is readable.
2. **I2/I3 — `retrieval/`, and here `grounding/context.assemble`, is the only path
   to data and never takes a `workspace_id`.** The new module does key translation
   and nothing else. It issues no SQL.
3. **A missing fact is omitted, never defaulted** (`facts_for`). The bridge may add
   a key; it may never add a value.
4. **One catalogue, two renderers** (ADR 0019, as amended by ADR 0021). The bridge
   must not become a third catalogue.
5. **`consumed_by` stays validated against the registry.** A bridged question whose
   consumer was dropped is still a form field.
6. **Nothing outside `app/ai/` names the vendor** — the new module lives in
   `domain/`, and importing `FIELD_CATALOGUE` from `app.ai.runtime.fields` is an
   import of a data structure, not of a provider. `test_ai_boundary.py` governs;
   `routes/dashboards.py` and `domain/onboarding_promotion.py` already do it.

---

## 8. Blast radius

The `code-review-graph` MCP tools were **not available in this session**, so this
is derived by reading the modules named below rather than from the graph. Re-run
`get_impact_radius_tool` on `FieldSpec` and on `question_bank.BY_DEPARTMENT`
before starting step 1 and reconcile against this table.

| Touched | How | Risk |
|---|---|---|
| `ai/runtime/fields.py` | Read-only, plus possibly new `question_key` values (step 4) | Low. A security-relevant file — a `question_key` edit is not a scope edit, but the file's review bar applies |
| `domain/question_bank.py` | Read-only | None |
| `domain/registry.py` | Read-only. `consumes_facts` keeps holding bare bank keys | None if the bridge translates *into* bank keys, as decided. Inverting the other way would need every `consumed_by` rewritten |
| `grounding/context.py` | `assemble` gains a second source for `department_facts` | **Highest.** It is the single grounding path; every capability and every narration reads it |
| `routes/dashboards.py` | `answered_questions` delegates to the new module | Medium. Behaviour-preserving if the tests in step 2 are written first |
| `routes/spine.py` | The department block learns what the interview answered, and `BlockQuestionOut` gains the two fields the pre-fill state needs | Medium, and it is a *visible* product change — §11.2 |
| `routes/onboarding_agent.py` | **New.** `_ask_next` and `submit_answer` gain the `may_answer_department_question` gate for `fact.*` targets (§11.3) | **High, and it is a behaviour change to who can finish onboarding.** The gate is one pure call, but it sits on the first screen of a customer's life in the product |
| `domain/onboarding_commands.py` | **New.** The candidate set handed to the generator is narrowed by the authorising pair as well as by `askable_fields` | Medium. Without it the gate dead-ends — see §10 step 5 |
| `domain/department_answers.py` | Read-only. `may_answer_department_question` is called from a second place; its signature does not change | None |
| `domain/sections.py` | `WATCH_ITEMS` are keyed by bank key; three of four (`lost_to`, `supplier_concentration`, `people_risk`, `binding_constraint`) become answerable via the interview | Low, falls out of `context.assemble` |
| `apps/web` | **Corrected — not "none planned".** §11.2 needs a pre-filled-and-editable state the department block does not have today, and §11.3 needs the interview to render a refusal. Both are additive fields on existing responses | Medium. Confirm the BFF route exists per path — a missing `route.ts` is a 404 neither suite sees |
| Migrations | **None.** No step in §10 adds, alters or backfills a column | — |
| `tests/` | New tests in step 2; `test_onboarding_agent_e2e.py::test_every_bank_mapping_names_a_real_question` is extended, not replaced; `test_department_answers.py` gains the interview-side cases | — |

---

## 9. Explicitly out of scope

- **Bridging the three brain-backed questions** (`lost_to`, `watched_competitors`,
  `success_in_twelve_months`). Different mechanism, different table, and
  `company_brain` has its own precedence and correction path.
- **Adding an executive block to the bank.** `doc/13` defect 26 owns that.
- **Any change to `askable_fields` itself**, or to the question gates
  (`question_elicits`, `is_compound`). **Amended by the §11.3 answer:** *what the
  interview asks* is no longer wholly out of scope. Gating the write without
  narrowing the ask produces a dead end — the model words a Finance question, the
  person types an answer, and the route refuses it. So step 5 adds a second
  restraint **on top of** `askable_fields` in `domain/onboarding_commands.py`,
  filtering the candidate set by the authorising pair. `askable_fields` keeps its
  signature and keeps narrowing on `stated_department`; it is not taught about
  roles, because that is the exact thing
  `assert_persona_is_not_authorisation` exists to prevent.
- **Any change to `Capability.consumed_by` / `consumes_facts` key spaces.**
- **Conflict handling** — `doc/08` §12 item 3. If the block and the interview hold
  different answers to the same question, this design lets the reader see both
  keys resolve; deciding which one a tile shows is a separate decision and step 6
  stops short of it.

---

## 10. Work breakdown

Ordered. Each item is one PR. **Nothing is blocked — §11 is answered.** Read §11.4
before starting: every step below is schema-free, and a step that finds itself
wanting a column has misread the decision rather than found a gap in it.

**Step 0 — Decisions. Done.** §11.1, §11.2 and §11.3 answered on 18 September 2026
and folded into ADR 0044, which is Accepted. *Acceptance: met — the ADR names a
chosen option per question with its own reasoning, and records the review-gate
option as rejected for a reason that is not the other three alternatives' reason.*

**Step 1 — `domain/question_surfaces.py`: the translation, and only the
translation.** Pure functions over `FIELD_CATALOGUE` and `BY_DEPARTMENT`, no SQL,
no session. `bank_key_for(catalogue_key) -> (Department, str) | None` and its
inverse. `FieldSpec.department` is a `str | None`, not a `Department` — this module
owns that conversion so no caller does it inline. All seven catalogue department
values, `executive` included, are members of `Department`, so the conversion is
total and needs no fallback. Depends on: step 0.
*Acceptance: `test_question_surfaces.py` proves all three classes from §4 — the 19
resolve both ways, the 10 unmapped bank keys resolve to `None`, and the 3
`fact.executive.*` keys resolve to `None`. The counts are asserted as numbers, so
adding a field without a `question_key` fails the suite.*

**Step 2 — `answered_questions` delegates; behaviour unchanged.** Move the
`FIELD_CATALOGUE` lookup out of `routes/dashboards.py` into step 1's module.
Depends on: 1.
*Acceptance: a database test that promotes a fact and asserts the counter falls,
written against the endpoint, passing identically before and after the move. If it
does not pass before, the move was not behaviour-preserving and something else
changed.*

**Step 3 — Gate the interview's `fact.*` writes (§11.3).** **Before step 4, not
after.** The asymmetry in §5.3 is live today for the counter; step 4 extends it to
the *value*, so the gate has to be in place before the value path opens, or the PR
that opens it is the PR that widens the hole. Two halves, one PR:

- **Refuse the write.** In `routes/onboarding_agent.py::submit_answer`, the target
  is already resolved server-side from the agent's last turn. For a `fact.*` target,
  call `may_answer_department_question(role=scope.role,
  caller_departments=scope.departments, department=Department(spec.department))`
  and refuse when it is false. `CurrentScope` is a `ScopedSession`, which carries
  `role` and `departments`; the third argument comes from the catalogue. **Nothing
  new is read, stored or migrated — it is a pure function over values the handler
  already holds.** `brain.*` and `persona.*` targets skip the gate entirely, which
  is what "leaving brain and persona fields open to everyone" means in code, and is
  why `/describe` and `/brief` are untouched.
- **Stop asking the question.** In `domain/onboarding_commands.py`, drop `fact.*`
  specs the caller may not answer from the candidate set before the generator sees
  it, using the same predicate. Without this the person is asked a Finance question,
  types an answer, and is refused — see §9 for why this narrowing is an amendment to
  the scope rather than something that was always in it.

Depends on: 1 (for the key→department resolution).
*Acceptance: a Contributor with no department-question permission runs the
interview and is **never asked** a `fact.*` question; a hand-built `POST /answer`
against a `fact.*` target returns the refusal rather than writing a row. And the
positive: an Owner is asked and answered exactly as today, so the gate has not
closed the ordinary path. Assert on `fact` row count, not on the response body — the
thing being prevented is a durable write.*
*Also asserted, because it is the stated consequence rather than a side effect: the
Contributor still completes onboarding. The journey ends with brain and persona
answers and no `fact.*` rows, and the department's bank questions stay outstanding —
which is correct, because nobody who may answer them has.*

**Step 4 — `context.assemble` surfaces promoted facts under their bank key,
inside the answering department.** The gap in §3, built the §11.1 option (i) way:
each promoted `fact` row whose spec has a `question_key` is added to
`department_facts[spec.department]` under its **bank** key. **No column is added to
`fact` and `_FACTS_SQL` is not re-filtered** — the row is placed into a group that
`_reachable_departments` already gates, and a row for a department the caller
cannot reach is never put in the dict at all. Depends on: 1, 3.
*Acceptance: a capability declaring `consumes_facts=("late_definition",)` is
grounded in an interview answer to `fact.operations.late_rule` —
`facts_for` returns it with a `source_ref` that opens the session. And: a
Contributor in Sales assembling context does **not** receive the Operations fact.
That second assertion is the one that must be written before the first.*
*Also asserted: the `fact.executive.*` rows (class C) reach `department_facts`
under no bank key, because they have none — they must not silently land in the
workspace-wide `facts` group under a bank name that does not exist.*

**Step 5 — The reverse tripwire.** Extend
`test_every_bank_mapping_names_a_real_question` with the direction it does not
cover: a `fact.*` field whose department has a bank question of the same
substance and no `question_key` set. Depends on: 1.
*Acceptance: the test fails when `question_key` is deleted from
`fact.operations.late_rule`, and the failure message names the bank question that
lost its writer. Prove it by breaking it, per this repo's practice.*

**Step 6 — The department block pre-fills instead of re-asking (§11.2 option ii).**
`routes/spine.py` reads the bridged set. **This is the step that costs a UI state
the block does not have today**, and it is the reason this step is larger than its
one-line description suggests. The block has `answered`, `proposed` and `answer`;
option (ii) needs a third condition — *answered elsewhere, shown filled, still
editable here* — which is neither of the two it has. Concretely:

- `BlockQuestionOut` gains `answered_in_interview: bool` and a `source_ref`. Both
  are **additive fields on an existing response**, so no `/v2` (`api-design`). The
  value itself already has a home in `answer`.
- `apps/web` gains the matching state: a field rendered filled, labelled as coming
  from the conversation, with the source openable and the input live rather than
  read-only. This corrects the §8 line that said no web work was planned.
- Editing in place writes to `onboarding_answer` exactly as it does today, through
  the existing `may_answer_department_question` / `state_for_answer` pair. The
  pre-fill does **not** change who may answer, and it does not write anything on
  render — a pre-filled field nobody touches stores no row.

Depends on: 2, 4.
*Acceptance: a founder who answered `late_definition` in the interview opens the
Operations block and the question is shown as answered, with the interview's own
value and a source that names the session — not blank, and not re-asked. They then
change the value in place and it is stored as a block answer, and the tile follows
the new one. And the negative: opening the block and closing it again writes no row.*

**Step 7 — `doc/08` §12 item 1 and `doc/13` are updated to the built state.** The
19/10/3 split stated where a reader of either will find it, plus the §11.3 change to
who can complete onboarding, which is a support-facing fact rather than an internal
one. Depends on: 6.
*Acceptance: `doc/08` §12 item 1 marked resolved with a pointer to ADR 0044, the ten
permanently-unbridged questions listed by name rather than described, and the
Contributor consequence written where someone answering a support ticket will find
it.*

Agent routing: steps 1–5 are backend (`services/api`). Step 6 is backend **and**
frontend and should be split at the wire if it does not fit one PR. Step 7 is
documentation. **No step is an Alembic step.** The earlier note here said a
migration would be inserted between steps 0 and 1 if §11.1 were answered with option
(ii); it was answered with option (i), so there is no such step and no Alembic work
anywhere in this breakdown.

---

## 11. The three decisions — answered

Parul answered all three on 18 September 2026. The options are kept below so the
record shows what was *not* chosen; the chosen option is marked and the reasoning
is Parul's, recorded rather than reconstructed.

### 11.1 Where the department filter goes when the key spaces join (§5.2)

**Chosen: (i) — route promoted facts through `department_facts[spec.department]`.
No migration.**

- **(i) Route promoted facts through `department_facts[spec.department]`. ← CHOSEN.**
  No migration. The department comes from the catalogue, which is code under review,
  and `_reachable_departments` — already load-bearing and already tested — does the
  filtering at read time. Weakness, accepted knowingly: the scope is enforced at read
  time by one module rather than at rest by the database.
- **(ii) Add `department` and `scope` columns to `fact`, plus an RLS predicate.**
  Rejected. Enforced where it cannot be bypassed, but it costs a migration, a
  backfill of existing rows from the catalogue, and a change to a table whose RLS is
  currently the simplest in the schema — three migrations if `NOT NULL`.
- **(iii) Leave `fact` workspace-wide and bridge anyway.** Rejected. Cheapest, and it
  widens who can read an L3 answer.

**What this binds elsewhere:** `fact` gains no column, so anything that would have
relied on one is off the table — including the review-state column §11.3 option (i)
needed. That is the conflict recorded in §11.3.

### 11.2 Does an interview answer close the department block's question, or pre-fill it?

**Chosen: (ii) — pre-filled, shown as answered, editable in place.**

- **(i) Closed.** Rejected. The counter and the block agree and nobody is asked
  twice, but the founder never gets to confirm or correct a value the model bound on
  their behalf.
- **(ii) Pre-filled, shown as answered, editable in place. ← CHOSEN.** Honest about
  where the value came from and gives a correction path — the same posture `doc/13`
  §10 takes on restatement, and the only option that leaves the founder a way to
  disagree with an answer they gave in conversation.

**The cost is real and is carried in step 6, not waved at.** The block today has
`answered`, `proposed` and `answer`, and none of those three is
*answered-elsewhere-and-still-editable-here*. That is a new UI state plus two
additive wire fields, and it is why step 6 is the only step in §10 that touches
`apps/web`. §8's `apps/web` row has been corrected accordingly.

### 11.3 May an answer given in the interview bind a department fact? (§5.3)

**Chosen: (ii) — gate the interview routes with `may_answer_department_question`
for `fact.*` targets, leaving brain and persona fields open to everyone. No
migration.**

This one was not a clean pick from three, and the record should say so. The
document's original option (i) was the better fit for the existing review gate — it
reuses `state_for_answer`, which the department block already applies, rather than
inventing a second posture for the same act. But it **requires an `answer_state`
equivalent on `fact`**, which is a schema change, which is §11.1 option (ii) — the
option Parul had just declined. The two answers could not both stand.

Put that conflict explicitly, the choice was to **keep the no-migration path and
drop the review-gate option.** So:

- **(i) Apply `state_for_answer` to promotion.** **Rejected because it implies a
  migration that was declined**, not because it is the weaker design. See the ADR's
  alternatives section, which records this separately for that reason.
- **(ii) Gate the interview routes. ← CHOSEN.** `may_answer_department_question` on
  `fact.*` targets only. Narrower, no migration.
- **(iii) Accept it and record why.** Rejected. Defensible only if the interview is
  only ever run by the registering Owner, and nothing in the routes enforces that
  while ADR 0026 puts more than one person in a workspace.

**Verified wireable without a migration.** `may_answer_department_question` exists in
`domain/department_answers.py` and is a pure function of `(role,
caller_departments, department)`. `CurrentScope` on every interview route is a
`ScopedSession`, which carries `role` and `departments`. The third argument is
`FieldSpec.department`, a catalogue string, and every one of its seven values —
`executive` included — is a member of `Department`, so the conversion is total.
`routes/spine.py` already calls the function with exactly this shape. Nothing new is
stored and nothing is read that the handler does not already hold.

**The stated consequence, which is a behaviour change and not a bug fix.** A
Contributor without department-question permission **can no longer submit `fact.*`
answers through the interview.** Today they can, and their answers bind. After step 3
they are not asked those questions and a hand-built request is refused. This is the
point of the decision rather than a side effect of it — but it means the set of
people who can complete a *full* onboarding narrows, and it should be discovered by
reading this line rather than by a customer finding a shorter interview. They still
complete onboarding: brain and persona questions are unaffected, the journey ends
normally, and the department's bank questions stay outstanding for someone who may
answer them.

### 11.4 The shape that falls out: zero migrations

All three answers landed on the no-migration side, and the combination is
deliberate rather than coincidental. Stated once here so no step has to infer it:

| | Chosen | Schema change |
|---|---|---|
| §11.1 department filter | Read-time, via `department_facts` | **None** |
| §11.2 block behaviour | Pre-fill, editable | **None** — two additive response fields |
| §11.3 who may bind | Route gate on `fact.*` | **None** |

`fact` ends this work with exactly the columns migration 0022 gave it: no
`department`, no `scope`, no `answer_state`. Any language anywhere in this document
or in ADR 0044 that assumes otherwise is wrong and has been corrected. In particular
**there is no `answer_state` on `fact` and there will not be one**, so `_FACTS_SQL`
needs no `BINDING_ONLY_SQL` companion — the protection moved to the write side
(§5.3).

**What this costs, said plainly:** the L3 scope of an interview answer is enforced by
one module at read time and by one predicate at write time, not by the database. Both
are code, both are testable, and neither is a constraint. The ADR's revisit trigger
names the signal that should reopen it — a second reader of `fact.*` rows outside
`grounding/context.assemble`.

---

## 12. Risks, including the ones with no mitigation

- **`context.assemble` is the single grounding path.** Step 3 edits the function
  every capability and every narration reads. A defect there is company-wide and
  shows up as wrong prose beside a right number. Mitigation: the negative
  assertion (cross-department) is written before the positive one.
- **No mitigation: the two catalogues still drift.** This bridges them; it does not
  merge them. Step 4's tripwire catches a missing `question_key` on a field that
  has a bank counterpart — it cannot catch a bank question added with no
  counterpart anyone intended, because that is indistinguishable from class B.
- **No mitigation: `doc/08` §2–7 and `question_bank.py` can still disagree.** ADR
  0020 recorded this and it is unchanged. The doc is prose; the module is data.
- **Conflicting answers are now reachable.** Once both spaces resolve, a block
  answer and an interview answer to the same question can differ. `doc/08` §12 item
  3 says nothing decides which a tile shows. Step 6 stops before this; it will
  arrive as a support question before it arrives as a design one.
- **Neon round-trip cost.** Step 3 adds no query — `assemble` already reads `fact`
  — so this should be neutral. It is worth measuring rather than assuming, given
  ADR 0039's history of a page that stopped loading.

---

## 13. Confidence

**High** on the mechanics: the key spaces, the four unbridged read sites, the
19/10/3 split and the absent columns on `fact` were read from the source, not
inferred.

**Medium** on §5.3's severity. Whether a Contributor ever reaches the interview in
practice depends on the product's invitation flow, which I did not trace end to
end. If they do not, it is a latent hole rather than a live one — but the routes
carry no check either way, so it should not rest on that.

**Unknown, and not invented:** how many facts a workspace holds, how often the
interview is re-run, and whether any of this has a latency budget. No number in
this document is a target because none was given.
