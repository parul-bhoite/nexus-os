# NEXUS OS — The Dashboard, the Settings Portal, and the Agents

**Status:** design, awaiting Parul's ratification · **Version:** 2.0 · 9 September 2026
**Governs:** everything reached after onboarding — the seven director surfaces, the
settings portal, the tool ledger, and the agents that narrate all of it.
**Sits under:** `doc/12` P14–P21. This document says *what the screens and the agents
are*; `doc/12` says *in what order they get built*. Sequence conflicts resolve to
`doc/12`; shape conflicts resolve here.
**Narrows:** `doc/05` (target scope) to `doc/08`'s cut, and states what `doc/08` left open.
**Reference implementation:** `doc/prototype/nexus-os-prototype.html` — the sections,
the tile chrome, the working drawer and the admin portal are drawn there with invented
numbers. This document is the plan to make the same screens true.
**Tool source:** `doc/prototype/NEXUS OS Dashboard Tools.xlsx` — 28 modules with a free
and a paid option each, plus 30 candidate features with market notes. Part IV is that
sheet turned into a ledger the product can enforce.

**What version 2 adds to version 1:** Part III (the settings portal), Part IV (every
tool and what it actually unlocks), Part V (every agent running on a skill). Parts I,
II and VI are version 1, corrected where the new parts changed an answer.

**Four decisions were taken on 9 September** and are folded in below: **ADR 0023**
GA4 and Search Console first · **ADR 0024** directors may act within thresholds ·
**ADR 0025** fixed per-tile windows · **ADR 0026** multi-entity workspaces at MVP,
reversing Q9/D17. ADR 0026 is the one that changes this document's shape rather than
its sequence — see §4.1.

---

# Part I — The frame

## 1. The question this answers, and its honest answer

> *"How do we design the dashboard and show every insight for every domain?"*

Onboarding is finished, so the workspace holds four sources and no others: the
**crawl**, the **onboarding answers**, the **uploaded documents** and the **roster**.
No CRM, no accounting system, no GA4, no operations records.

Counted against `app/domain/dashboards.py`, six of the seven directors therefore have
**not one measurable number** between them. A design that promises "every insight for
every domain" and then renders fifty locked tiles has not shown every insight; it has
shown every absence.

So the commitment is narrower and, done properly, better:

> **Every insight is present in every domain the caller can reach — as a catalogue
> entry with an honest state, its named unlock, and, where we already have it, its own
> value. What varies between domains on day one is not which insights exist but which
> of them carry a measurement.**

Three things follow, and they are the whole design:

1. **The catalogue is complete and visible.** Inside a department you hold, nothing is
   hidden. A locked tile is a call to action (`doc/04` §6 rule 1).
2. **The self-reported layer is a first-class insight surface, not configuration.** The
   founder has just typed what a lead is, what "late" means, which supplier they are
   exposed to, what decision they keep putting off. Read back with provenance and with
   the measurement that will later confirm or refute it, that is day-one value in all
   six departments — and it is what makes unlocking the rest worth doing.
3. **Settings is not a side screen.** It holds the currency, the fiscal year, the
   reporting week and the windows that every number on every tile is computed against
   (`doc/05` §1). A wrong setting is a wrong number. Part III treats it as part of the
   dashboard, because it is.

## 2. What exists today, verified against the code

| Piece | Where | State |
|---|---|---|
| Seven directors, ~60 offerings, source map | `app/domain/dashboards.py` | Real, as data, from `doc/05` |
| Seven render states + `state_for` ordering | `app/domain/dashboards.py` | Real, and only `PLANNED` is reachable |
| **The capability table, one id space** | `app/domain/registry.py` | **Built (step A).** 80 capabilities, dotted ids, doc 05 numbers as provenance, `consumes_facts` inverted from the bank, validated at import |
| Derived denominators and the completeness meter | `app/domain/registry.py` | Real, in the same module as the table — separating them is what let them drift |
| **The source ledger** | `app/domain/sources.py` | **Built (step A).** One row per `Source`, `unlocks` derived, `PROVIDER_SOURCES` joining it to the nine declarable providers |
| **Reporting settings** | `app/domain/reporting.py` · migration 0027 · `GET/PUT /companies/current/reporting` · `ReportingCard.tsx` | **Built (step A).** Fiscal year, reporting week, report timezone, scale, decimals, and the restate stamp |
| Question bank, 29 questions, each naming its consumer | `app/domain/question_bank.py` | Real |
| Fact layer (department rules), brain, persona | migration 0022 · `ai/runtime/fields.py` | Real, and the Setup section reads it |
| One company page, segregated by omission | `GET /dashboards/company` | Real, 59 checks green (`GOAL-STATUS.md`) |
| Director page + offering tiles | `apps/web/components/dashboard/` | Real, flat list, no sections, no values |
| **Skill runtime** — manifest + `SKILL.md` + `schema.json`, loaded and validated at startup | `app/ai/runtime/skills.py`, `runner.py` | **Real, and good.** Seven skills exist |
| **Director agents** | `app/ai/agents/` | **Empty.** Part V fills it |
| Grounding pipeline, `generation` rows | `app/grounding/pipeline.py` | Stub — `doc/12` P14 |
| Connector state | `routes/dashboards.py::connected_sources` | Returns `frozenset()`, honestly, and takes no workspace |
| **Settings** | `apps/web/app/settings/page.tsx` | **Three panels: domain, invitations and reporting.** The rest of Part III is owed |
| `disabled_ai_skills` kill switch | `config.py` → `anthropic_provider.py:104` | **Enforced.** No surface to set it, and `pipeline.py`'s docstring says otherwise |

**Nothing in the product is dishonest today.** Everything below adds value without
adding a claim.

## 3. The one rule the design turns on

Two axes decide what a person sees, and **they are never mixed**:

| Axis | Question | Consequence |
|---|---|---|
| **Reach** | May this person see this thing at all? | It is **absent** — not listed, not locked, not counted (`doc/06` §4.5) |
| **Readiness** | Does the workspace have what this insight needs? | It is **present**, in one of seven states, naming its unlock |

Reach is about the company's organisation, which is itself a fact about the company; a
greyed-out Finance tab tells a warehouse supervisor that a Finance department exists.
Readiness is about our own data, and hiding it would waste the only conversion lever
the cold start gives us.

**This rule governs the settings portal and the tool ledger identically.** A Department
Manager's settings portal does not contain a disabled "Billing" panel, and the tool
ledger shows a manager the tools that feed *their* department, not the company's whole
integration estate.

---

# Part II — The dashboard

## 4. Information architecture

```
/dashboard                       the company page — one URL, content by caller
  ├─ readiness strip             score+denominator · capabilities · sources · brain
  ├─ your departments first      the one you work in leads
  └─ landing redirect            Owner/Executive → Chief of Staff; others → their own

/dashboard/[department]          one director
  ├─ header                      director, remit, score or "not scored — why"
  ├─ section rail                4–6 sections, from the registry
  ├─ data ribbon                 sources feeding this department + freshness
  ├─ section body                blocks (§6)
  ├─ gap banner                  "connect X to unlock N more here"
  └─ assistant                   docked — the director's own skill (Part V)

/settings                        the portal — two halves, You and Your company (Part III)

/group                           the roll-up, only for a caller holding two or more (§4.1)
```

**The shell carries an entity switcher** (ADR 0026). One login may hold membership in
several workspaces, so the company name in the top bar is a control rather than a label
— and switching is the most dangerous action in the product (§4.1, consequence 2).

**Sections, not a flat tile list.** `doc/08` specifies 4–6 named sections per department
and the prototype renders exactly those. The current UI is one `<ul>` of every offering,
which cannot express "Dispatch board" or "Receivables ageing" and does not survive sixty
tiles. The section is the unit of navigation; the block is the unit of rendering; the
capability is the unit of truth.

**Every department gets two sections that are not in `doc/08`**, and they are the reason
a day-one dashboard is not a wall of locks:

- **Setup** — this department's own answers, as cited facts, each with who said it and
  when, each naming the insight that will read it. Always available. Editable, and an
  edit goes through §10's restate rule.
- **Watchlist** — the founder's stated risks turned into watch items (§9).

And one panel, from `doc/08` §2B–§8B: **"What NEXUS will not ask you"** — the figures we
fetch rather than ask for, with the source each needs, and a link straight into the tool
ledger. Showing the customer what we refuse to ask them is a product surface, not an
internal rule, and it is the highest-intent place in the app to put a Connect button.

### 4.1 The group view, and the read path it needs

ADR 0026 reverses Q9/D17: one login may now hold several entities, each with its own
Brain, tools, departments and directors, rolling up to a group view. `membership` was
always many-to-many, so this needs **no migration** — but the roll-up is a cross-tenant
read, and everything in this product is built so that cannot happen.

**So the group view is not `retrieval/` with the predicate loosened.** It is a separate,
named path:

1. Resolve the caller's memberships first, through `membership_own_rows`.
2. Open **one scoped session per workspace**, and compute each entity's figures inside
   its own `nexus.workspace_id`.
3. Aggregate **outside** the database, in `calculators/`, which is pure.
4. Render per-entity provenance, so any group number breaks back down into the entities
   it came from.

Three rules the surface must hold:

- **The denominator travels, at group level too.** *"Four entities, three scored"* — and
  it names the unscored one and what it needs. Never an average that hides an absence.
- **Departments are per entity, not per person.** Somebody may be Finance at one entity
  and Operations at another, so `scope.departments` resolves per active workspace and is
  **never cached across a switch**. This is where consequence 2 of ADR 0026 — I5's
  cache-invalidation-on-switch, retired with `_teardown_on_switch` and now needed again —
  will actually bite. Entity A's numbers under entity B's name is the worst failure this
  product can have.
- **The group view is a property of memberships, never of a role.** An invitation names
  one entity. Being an Owner of one company grants nothing at another.

## 5. The registry is the spine — and it currently has a break in it

Everything above requires one question to be answerable in code: *given a capability,
what does it need, what do we have, and what did the founder tell us?* It is not
answerable today, because there are **two capability id spaces and no join between
them**:

| | Ids | Populated by |
|---|---|---|
| `dashboards.py` offerings → `registry.REGISTRY` | `doc/05` numbering — `3.2`, `4.5`, `5.8` | ~60 entries, `consumes_facts=()` for all |
| `question_bank.py` `consumed_by` | `doc/08` dotted names — `marketing.conversion_funnel` | 29 questions naming 40-odd capabilities |

Neither set of strings resolves in the other. So:

- **Q33's guard is vacuous where it matters.** `test_question_bank.py` proves every
  question names *a string*; nothing proves the string names a capability that exists.
  The whole justification for asking a founder 29 questions is that something reads
  each answer.
- **`consumers_of(fact_key)` always returns `()`**, so the review gate's impact ranking
  (Q59) ranks everything equally.
- **No tile can say "you told me X"** — which is the entire day-one design.
- **No tool can honestly say what it unlocks**, which is the entire tool ledger.

### The fix, and it is small

One capability table in `domain/registry.py`, keyed by the **dotted name** (`doc/08`'s space, because it is the
newer, narrower cut and is already what the question bank declares), with the `doc/05`
id retained for provenance:

```python
@dataclass(frozen=True, slots=True)
class Capability:
    id: str                            # "operations.on_time_dispatch"
    doc05_id: str                      # "6.2" — traceable to the paragraph
    department: Department
    section: str                       # "dispatch" — drives the rail
    block: Block                       # metric | trend | table | board | … (§6)
    name: str
    shows: str
    required_sources: tuple[Source, ...]
    consumes_facts: tuple[str, ...]    # question keys, inverted from the bank
    narrated_by: str                   # the skill that phrases it (Part V)
    scoreable: bool
    reach: Reach                       # DEPARTMENT_TOTAL | OWN_RECORDS
    delivered: bool = False
```

Four tests make it hold, and they are owed first:

- `test_every_consumed_by_names_a_capability_in_the_registry` — the missing half of Q33.
- `test_every_capability_declares_a_source_or_a_fact`.
- `test_every_narrated_by_names_a_loaded_skill` — Part V's equivalent guard.
- `test_no_literal_capability_count_exists_in_the_codebase` — already planned in P15.

**And `DELIVERED` must die in the same change.** `state_for` gates on the `DELIVERED`
frozenset (`dashboards.py:772`) while `registry.py` documents `delivered` as having
replaced it. Two mechanisms for one fact is how a shipped widget renders as "not built
yet" — or worse, the reverse.

## 6. The block vocabulary

Eight kinds. Seven directors × five sections is thirty-five screens if each is
hand-built, and eight components if the registry says which block to render.

| Block | Renders | Every-state rule |
|---|---|---|
| `metric` | Value, unit, delta with its basis, source chips, working drawer | Never a `0`; never a self-reported figure (§7) |
| `trend` | 12-week / 12-month series | Needs `HISTORY`; below warm-up it states the date of the first comparison |
| `table` | Rows with computed columns | A dash where there is nothing to divide by, never a zero |
| `board` | Lanes with named items | Refuses to state a percentage it cannot itemise |
| `cards` | Ranked items each with its evidence | An item with no evidence trail is not shown at all |
| `queue` | Requests awaiting a person, with age | Empty is a sentence, not a blank |
| `facts` | Quoted answers with attribution and date | Always available; never styled as measurement |
| `panel` | A named finding or explanation | Carries its inputs |

### The tile contract — `+ why this number`

Every `metric` opens to **method · inputs · arithmetic**, read from the P14 `generation`
row's `input_snapshot` and `calculation_trace`. The prototype's `trail` is the shape:

```
Enquiry conversion   2.8 %   +0.4pp        [GA4]
  Method       submissions ÷ sessions
  Numerator    236
  Denominator  8,420
  Window       19 Jul – 17 Aug
  Settings     fiscal week starts Sunday · OMR · rounded to 0.1
```

**A tile that cannot open its working does not ship.** This is `doc/08` 8.2 ("which
number do you not currently trust?") answered structurally, and it is cheap only if it
is built into the block from the first widget rather than retrofitted to sixty. The
`Settings` line is version 2's addition: a number is only checkable if the assumptions
under it are on the same screen as the arithmetic.

## 7. The seven states, as copy and as treatment

| State | Copy rule | Treatment | Who resolves it |
|---|---|---|---|
| `LIVE` | Value, delta with basis, source chips | Full tile, working drawer | — |
| `PARTIAL` | Names the *missing* source only | Full tile, reduced scope stated | Customer connects one thing |
| `LOCKED` | The label, the reason, **one named unlock** | No value area at all | Customer connects one thing |
| `WARMING` | *"First comparison on 12 October"* — a date | Full tile, no delta | Nobody. Wait |
| `SELF_REPORTED` | The founder's words + *"You, 8 September"* | **`facts` block, never a metric slot** | Connect the source that measures it |
| `STALE` | The number **and its age** | Full tile, aged marker | Reconnect / refresh |
| `UNAVAILABLE` | The reason, and what to do about it | Full tile, no value | Us, usually |
| `PLANNED` | *"Not built yet"* — no call to action | Dimmed, no unlock sentence | Us |

Three rules that are easy to lose:

- **`WARMING` never asks for a connection.** Telling somebody to connect what they
  already connected is how a product loses trust in its own instructions.
- **`SELF_REPORTED` is a different block, not a badge.** `doc/05` §0 requires that a
  number they typed and a number we measured never look identical. A badge on an
  otherwise identical tile fails that at a glance and in a screenshot. A self-reported
  value renders as quoted text with an attribution line, and never occupies a metric
  slot beside measured tiles.
- **`LOCKED` names one unlock, not a list.** Where an offering needs three sources, name
  the one that unblocks the most and put the rest in the drawer.

## 8. Day one, per domain, with zero connectors

`connected = {CRAWL, ONBOARDING, DOCUMENTS, ROSTER}` (+ `LANGUAGE_MODEL` if keyed).

| Domain | Measured now | Self-reported now | Locked, one unlock |
|---|---|---|---|
| **Marketing** | Brand · technical SEO · performance scores from `calculators/audit.py`, each with its evidence and the crawled page it came from | Lead definition · active channels · acquisition budget · Arabic scope | Sessions, enquiries, conversion, cost per enquiry, channels, pages, campaigns → **GA4** |
| **Sales** | — | Pipeline stages · stale threshold · assignment rule · quota period · disqualifiers | Everything → **CRM** |
| **Finance** | — | Payment terms · approval threshold · approver · runway alert level | Everything → **accounting** |
| **Operations** | — | Promised lead time · usual delay cause · stock posture · lateness definition · supplier exposure | Everything → **create your first project** (adoption, not a connector) |
| **People** | — | Leave basis · hiring sign-off · people risk · review cycle · document-expiry opt-in | Everything → **HRIS**. Directory arrives with members (P17) |
| **Strategy** | Competitor set, named by the founder then discovered by the crawl | Success definition · target segment · binding constraint · what you are deliberately not doing | Share of search → **Search Console**; sizing, pricing → confirm segments, add price list |
| **Chief of Staff** | Brain contents (items, kinds, sensitivity, updated) · capability readiness · unanswered questions per department · **the decision from 8.3, seeded as a real queue item** | What you check first · the number you don't trust · interruption cadence | Composite → **any one scoreable department** |

**Headcount is the trap.** The roster is who has been invited into NEXUS, not who works
at the company. Rendering `Headcount 3` from `membership` would be a false number on the
People overview on day one. It stays locked on HRIS, or renders self-reported from the
company-stage headcount band — never measured.

**Marketing's audit scores must not become a Marketing score.** They measure the
website, not the marketing. `REQUIRED_FOR_SCORING[MARKETING] = (GA4,)` already encodes
this; the screen must not undo it by averaging three audit scores into a headline.

## 9. The Watchlist — the block that makes day one worth opening

Five onboarding answers are not thresholds. They are the founder naming, in their own
words, what is currently wrong:

| Answer | Department | Becomes |
|---|---|---|
| 2.4 who do you lose to | Marketing / Strategy | A tracked competitor, then observed movement |
| 5.5 supplier you are most exposed to | Operations | A concentration risk, before purchase history exists |
| 6.3 biggest people risk | People | A vacancy watched against the operation it holds back |
| 7.4 binding constraint | Strategy | The filter that suppresses unactionable recommendations |
| 8.3 the decision you keep putting off | Executive | A real item in the decision queue on day one |

Each renders as a card carrying three things: **what you told us and when**, **what we
will measure to confirm or refute it**, and **what that measurement needs**. That is the
bridge from self-report to measurement, in every domain, with no connector — and when
the connector lands, the card does not disappear, it resolves (§11).

`doc/05` §11's interlocks are the same mechanism a level up — delivery slip → revenue
risk, capacity → bid decision. Each needs both sides live, so none is day one, but each
should be a registry entry from the start so the screen can say what it is waiting for.

## 10. Scores, deltas, windows — and the restate rule

- **The composite is out of `scoreable_units`, derived** — five departments with a page
  plus Customers inside Sales (ADR 0010, finding #27). Never a literal.
- **Day one there is no score at all.** `score: None`, never `0`. *"No scoreable
  department yet"* is a named state (P19), and on the Chief of Staff it renders as a
  **Baseline**: what was captured, what will be measured, and the date the first
  comparison becomes possible. A Baseline is a screen, not an empty state.
- **Every delta carries its basis** — *"+9.2% vs July"*, not *"+9.2%"*. A zero delta
  reads **"unchanged"** (P14 eval).
- **Windows are fixed per tile and stated in the working — decided, ADR 0025.** No
  7/30/90 selector at MVP: a 90-day option in week two offers a comparison the data
  cannot support. The window is derived from settings panel 5, so changing the fiscal
  year or the reporting week moves it, which triggers the restate rule below.
- **The restate rule (new in v2).** Changing a setting or an answer that a number is
  computed against — fiscal year start, reporting week, currency, "late means three days
  after", the stale-deal threshold — **marks every affected tile stale and re-derives
  it, and the change is logged with who made it.** Numbers are never silently restated
  under a founder who has already acted on them, and history is never rewritten in
  place: the old derivation stays, superseded, with its own window.

`score_denominator`'s docstring says the number "is five and not six" while its body
returns `len(scoreable_units(...))`, which is six once Sales is selected. The body is
right, the docstring is stale, and M14 ("data says five, copy says six") is that line.

## 11. Findings — when the founder and the measurement disagree

`doc/08` open item 3, and it deserves a primitive rather than a branch. The founder
promised a three-day lead time; the operations data shows a six-day median. That is not
an error, and it is not a reason to overwrite either number.

**A `finding` is a first-class object**: two named sources, both values, both dates, and
a question for whoever owns the department — *which is right?* Answering updates the
fact **with provenance**, and the finding is retained with its resolution. It is never
resolved silently, and the measured value never quietly replaces the stated one, because
the stated one is what their customers were promised.

This is the payoff of the self-reported layer and the most defensible "insight" the
product will produce in its first year. The schema reserves for it in P14; the surface
lands with the first connector in P18.

## 12. The Contributor surface

Not the manager's page with tiles removed — a different section set, which is why
`Capability.reach` is in the registry rather than in a permission check:

| | Manager | Contributor |
|---|---|---|
| Sections | Overview · Pipeline · Accounts · My team · Forecast | My day · My deals · My accounts · My targets |
| Totals | Pipeline value, win rate, average deal size, department score | **Absent, with no lock icon** — never part of this application |
| Leaderboard | Team attainment | **Nowhere.** Comparison against colleagues is a management tool |
| Settings | Their department's question block, their own account | **Their own account only** — thresholds are their manager's to set (`doc/08` §10B) |
| Explanation | — | One card on *My day*: department totals belong to their manager |

`doc/08` §10 works the example only for Sales. The other five departments need the same
treatment before a Contributor is invited into them — see §24.

---

# Part III — The settings portal

## 13. Why settings is load-bearing, not administrative

`doc/05` §1: *"Global assumptions required before any dashboard renders: company profile
complete · currency · fiscal year start · timezone · reporting week definition · primary
language · user role and department visibility."*

**Four of those seven have no home in the product today.** There is no reporting panel,
no fiscal year start after registration, no reporting-week definition, no report
timezone. Every window in every drawer in §6 is therefore currently unstateable, and
`doc/08`'s "windows are fixed and stated in the working" cannot be honoured until they
exist.

So the framing this document commits to:

> **Settings holds the denominators.** Every panel states, in the same voice the question
> bank uses, *what it changes* — and how many tiles move when you change it. A setting
> that moves numbers triggers §10's restate rule.

Example copy, and it is the pattern for the whole portal:

> **Reporting week starts** — Sunday
> *Moves 14 tiles across Marketing, Sales and Operations. Changing it re-derives this
> week's figures and marks last week's as superseded rather than editing them.*

## 14. The portal — two halves, fourteen panels

One login belongs to one company (Q9/D17), so the portal is not a tenant switcher. It is
**You** and **Your company**, and the second half is reach-filtered by §3.

### You

| Panel | Holds | Reach |
|---|---|---|
| **1 · Account** | Name, email, password, active sessions and sign-out-everywhere | Everyone (exists at `/account`) |
| **2 · How NEXUS talks to you** | Language, timezone, detail level, **interruption cadence (answer 8.4)**, dictation on/off, default landing screen | Everyone. All `persona.*` fields — **presentation only, never authorisation** (`fields.py` asserts this at import) |
| **3 · Your department block** | The 4–5 questions for each department you hold, editable, each showing the insight that reads it and the date you answered | Manager and above. A Contributor sees this panel **read-only with an explanation**, not absent — the thresholds govern their own numbers, so hiding them would be worse than showing they are not theirs to set |

### Your company

| Panel | Holds | Reach |
|---|---|---|
| **4 · Company** | Name, website, **additional URLs** (crawled, never identity — D16), country, currency, headcount band, industry (inferred at the crawl, confirmed at the review gate). **Per entity** (ADR 0026) | Owner, Executive |
| **4b · Entities** ⚠ **new, ADR 0026** | The entities this login holds, which is active, create another, and what the group view covers. Every other panel below is scoped to the active entity | Owner of each entity. The list is exactly their memberships and no more |
| **5 · Reporting** ⚠ **new, and blocking** | Fiscal year start, reporting week definition, period windows, units and rounding (`184.6 K OMR`), report timezone | Owner, Executive |
| **6 · Domain** | The claim, the DNS/file/email method, verification state, and what verification gates | Owner (exists) |
| **7 · Departments** | Which departments the company runs. Adding one creates its director and its question block; removing one is a scope change and names its consequences before it happens | Owner, Executive. **Today this is onboarding-only and has no post-onboarding home** |
| **8 · People and roles** | List, role, departments (≤3), pending join requests, removal **with the logged document transfer** (Q71) | Owner; a Manager sees and invites within their own department only (D16) |
| **9 · Tools and connections** | The ledger (Part IV): what is connected, what it unlocks, what it cannot answer, scopes granted, last sync, field-completeness result, revoke | Owner. Verification-gated (D19). A Manager sees the tools feeding **their** department, read-only |
| **10 · Company Brain** | Every item: kind, sensitivity, passages, updated. Edit a fact (with provenance), delete an item — and deletion **fans out** to passages, embeddings, cached answers and derivations | Owner, Executive |
| **11 · AI and agents** ⚠ **new** | Which skills are enabled (`disabled_ai_skills` — enforced at the provider today, with no surface to set it), model availability, per-tenant and per-user token budgets, **autonomy level per agent**, approval thresholds, spend caps, kill switch | Owner |
| **12 · Audit log** | Who did what, and **the refusals as well as the successes** — plus an **entity column** and every agent action taken under a threshold (ADR 0024, 0026) | Owner only, and the log is itself access-controlled (P21) |
| **13 · Data** | Export the workspace, delete it, retention, document ownership | Owner |

**Absent at MVP, and said so rather than stubbed:** billing, seat limits and plans (P17
explicitly excludes them). A panel that exists and does nothing is worse than a sentence
saying it is not built.

**Panels 5, 7, 4b and 11 are the ones that do not exist and are needed soonest**: 5
because every window depends on it (ADR 0025), 7 because a company that hires into a new
department cannot currently add one, 4b because ADR 0026 makes the active entity the
scope of every other panel, and 11 because ADR 0024 makes it the gate on any agent
action at all.

## 15. What the settings portal must never be

- **Never a place authority is granted.** Panel 2 is `persona.*` and cannot widen
  access — the same rule the persona interview enforces by refusing "I'm the CFO".
- **Never a silent restatement.** §10's restate rule, logged, every time.
- **Never a greyed-out panel.** Reach decides presence here exactly as on the dashboard.
- **Never the only home for a department's questions.** The director carries
  `unanswered_questions` and links here; both entry points exist, one list behind them.

---

# Part IV — Every tool, and what it actually unlocks

## 16. The tool ledger

`doc/prototype/NEXUS OS Dashboard Tools.xlsx` lists a free and a paid option for 28
modules. That sheet answers *"what could we buy?"*. The product needs the inverse:
**for each tool, what does connecting it turn on, what does it still not answer, and
what breaks if a field is missing?** That is the ledger, and it is data next to the
registry so the connect screen and the locked tiles read from one source.

```python
@dataclass(frozen=True, slots=True)
class Tool:
    source: Source                     # the Source enum entry it satisfies
    name: str                          # "Google Analytics 4"
    free_option: str                   # from the tools sheet
    paid_option: str
    unlocks: tuple[str, ...]           # capability ids — derived, never typed twice
    cannot_answer: tuple[str, ...]     # the honest half
    required_fields: tuple[str, ...]   # what must be mapped, checked at connect
    scopes: tuple[str, ...]            # read-only at MVP (A5)
    verification_gated: bool = True    # D19
```

`unlocks` is **derived** by inverting `Capability.required_sources`, so a tool cannot
advertise a capability that is not `delivered`, and adding a capability updates the
connect screen with no second edit.

| Tool | Unlocks | Cannot answer | Free / paid | Priority |
|---|---|---|---|---|
| **Crawl** (built) | Brand · technical SEO · performance scores · competitor pages · tech landscape | Anything about visitors, money or people | Ours | **Live** |
| **Documents** (built) | Price list → Proposal Studio (**every price cited to a page**) · budget → budget-vs-actual · policies → HR library | Anything not in a file you uploaded | Ours | **Live** |
| **Roster** (P17) | People directory | **Headcount** — the roster is who uses NEXUS | Ours | P17 |
| **GA4** | 4 Marketing capabilities, and Marketing scoreability | Enquiry **value** — that is Sales' to hold. Offline leads | Free | **First** |
| **Search Console** | ⚠ **Nothing, today.** No capability requires it — see §26 defect 10 | Anything about sessions or conversion | Free | **First** |
| **PageSpeed** | ⚠ **Nothing, today.** The audit computes a performance score and no capability holds it — §26 defect 10 | Anything about traffic | Free | Live |
| **CRM** (Zoho / HubSpot) | 6 by itself; feeds 12 in all — pipeline, forecast, stale deals, routing, attainment, and the **Customers** unit with accounting beside it | Marketing attribution before the enquiry. Cash | HubSpot free tier / Salesforce | **Second** |
| **Accounting** (Xero / QuickBooks / Zoho) | 7 by itself; feeds 20 in all — cash, runway, ageing, budget-versus-actual, approvals, and project profitability with Ops | Anything about pipeline or delivery | Wave free / QuickBooks | **Second** |
| **Ads** (Google / Meta) | Spend, CPC, cost per enquiry, campaign rows | Organic anything | Native free | Third |
| **LinkedIn** | Social reach — `doc/08`'s single locked Marketing tile | Paid social on other networks | Native free | Third |
| **HRIS** | Headcount, start dates, contract types, leave balances, requisitions, attrition; **visa and document expiry** (opt-in, answer 6.5) | Utilisation — that needs Ops | Manatal-class | Fourth |
| **Ops layer** (first-party, **not a connector**) | All of Operations, plus HR utilisation and project profitability | Nothing — but **it fails on adoption, not on an API** (`doc/05` §6c) | Ours | Decision (§25) |
| **DataForSEO** | Keyword table, difficulty, content gaps | Your own site's traffic | Metered, paid | Post-verification (D2) |
| **Enrichment** (Apollo / Clay) | Lead Intelligence, scoring against an ICP | Whether they will buy | Hunter free tier | Phase 2 |
| **Reviews** (Google Business Profile) | Customer satisfaction into the Customers unit; review responder | Why they left | Native free | Phase 2 |
| **Meeting bot** (Otter / Fireflies) | Decisions and action items into the Executive queue; "what was decided" as retrieval over transcripts | Anything nobody said out loud | Otter free tier | Phase 2 |
| **Tender feed** | Opportunity Radar | — | **No provider identified** (`doc/05` §12) | Blocked, and it is a decision (§25) |
| **Visitor identification** (RB2B / Warmly) | Who is on your site now, feeding Sales | Individuals, reliably, under GCC privacy expectations | Free to 500/mo | Needs a privacy decision |
| **Voice** (Retell / Vapi / ElevenLabs) | Voice CEO (owner talks to NEXUS) and, separately, outbound AI calls | — | Whisper self-host / Retell | Labs, and gated by §19 |

**Every count in that table is now computed**, by inverting `required_sources`
against what a workspace already has. Two of the numbers in this document's
first version were hand-written and wrong: GA4 turns on **four** Marketing
capabilities rather than six, and none on Strategy — `strategy.market_position`
needs the crawl and keyword data, not analytics. That is exactly the failure the
derivation exists to prevent, and it was found by writing the derivation.

**A tool "unlocks" only what it completes on its own.** A CRM *feeds* twelve
capabilities and *turns on* six; the other six also need accounting or history.
The connect screen may only ever promise the second number, or a founder
connects two systems and finds the tile still locked.

### Three rules the ledger enforces

1. **Every row states what it cannot answer.** Half a tool ledger is a sales sheet. The
   second column is what stops "connect everything" from ending in disappointment, and
   it is the same honesty that makes `doc/08` §2B a product surface.
2. **Field-completeness is checked at connect, not discovered in an empty widget**
   (`doc/05` §9, P18). A CRM with no `last_activity_at` **disables stale-deal detection
   at connect, with the reason on screen** — and the Sales tile then reads Locked on a
   field, not Live on a lie.
3. **Revocation degrades to `STALE` with a date, never to zero** (P18 acceptance).

## 17. The connect screen, and why it lives in two places

`doc/09` §3's finding: connecting GA4 from a locked Marketing tile means the customer
connects nothing, because they have not yet seen why it matters. So the tool appears in
two places and both carry the same sentence:

- **Settings → Tools**, as the ledger, grouped by what each unlocks: *"Google Analytics —
  turns on 6 Marketing capabilities and 1 Strategy capability. Free."*
- **On the locked tile itself**, as the named unlock, one click from connecting.

Only tools that **genuinely connect** appear (Q44). Connections belong to the workspace,
not the person who authorised them (Q48), and every token is encrypted at rest and never
logged (P18).

## 18. Build versus buy, stated once

The tools sheet's real finding is that most of these categories already have a product
in them. NEXUS is not competing with Ahrefs or QuickBooks; it is the layer that reads
them together and says what to do. So the ledger's default answer for any new capability
is **connect the tool, do not rebuild it** — and the two exceptions are deliberate:

- **The Operations layer**, because no affordable tool holds a GCC distributor's dispatch
  floor in a shape a director can read (`doc/05` §6).
- **The Company Brain and the grounding pipeline**, because that is the moat.

## 19. Autonomous tools need a governance layer before any of them ship

The tools sheet's newer rows — AI Ad Manager, autonomous outreach, voice agents,
dynamic pricing, AR/AP chasing — **act on the world**. Its own market note says the
category has no dominant governance product and that vendors ship their own guardrails.

ADR 0024 decided that directors **may** act within customer-set thresholds — and that
**no agent takes one external action until all six of its preconditions are green**.
Panel 11 and the five injection evals therefore move ahead of the first acting
capability rather than sitting behind six directors in P20. Choosing `act` did not make
agents act sooner; it made the governance layer MVP-blocking. `propose` — everything
drafted, nothing sent — is the honest interim state, and most of the demo lives there.

The rule is `doc/12` P20's, stated here as a product rule rather than a security one:

> An externally visible action requires an approval threshold, a spend cap, a
> do-not-contact list, and an audit row — and a turn that has read untrusted content
> cannot take one at all without a human confirming the **exact payload**.

That is not a setting a customer can switch off. The threshold is theirs; the
confirmation is not.

---

# Part V — Every agent runs on a skill

## 20. The contract

The runtime is already right. `app/ai/runtime/skills.py` loads a directory of three
files — `manifest.toml`, `SKILL.md`, `schema.json` — validates `writes` against the
field catalogue at **startup**, and refuses to persist a value outside it. Seven
onboarding skills use it. **`app/ai/agents/` is empty, and the seven directors have no
skill at all.**

So: **an agent *is* a skill.** A director is not Python that happens to call a model; it
is a directory a non-programmer can edit, whose blast radius is declared in its
manifest. The manifest needs five additions:

```toml
name = "sales-director"
version = "1"
description = "The Sales Director. Narrates computed sales figures and refuses the rest."
model = "claude-sonnet-5"
effort = "high"

department = "sales"          # NEW — the runner binds a ScopedSession for it (I2/I3)
reads_capabilities = [         # NEW — the computed objects it may narrate
  "sales.pipeline_board", "sales.forecast", "sales.stale_deal_alert",
  "sales.quota_attainment", "sales.lead_routing",
]
tools = ["retrieval.search", "dashboard.read_tile"]   # NEW — read tools only
actions = []                   # NEW — empty means it cannot change anything
autonomy = "read"              # NEW — read | propose | act (ADR 0024); `act` needs all six preconditions

requires_grounding = ["tiles", "facts", "brain", "scope"]
writes = []
tags = ["director", "sales"]
```

Five rules, each of which is an existing invariant made mechanical:

1. **No skill produces a number (I1).** `requires_grounding` names every figure it may
   mention. The schema forbids free numerals in prose, and the runner rejects a response
   whose narrative contains a numeral absent from the grounding — P14's *"a
   model-produced number is rejected"* eval, enforced at decode time rather than asked
   for in a prompt.
2. **A director never queries.** It receives computed tiles. `retrieval/` remains the
   only path to data and takes a `ScopedSession`, never a `user_id` (I2/I3).
3. **Same skill, different scope.** The Sales Director serves the manager and the
   Contributor from one `SKILL.md`; `reach` filters the grounding and the refusal copy
   lives in the skill (`doc/08` §10A). Two prompts would drift into two products.
4. **No shell tool in any allowlist, ever** (I8), asserted by a test.
5. **Untrusted content is wrapped** (`wrap_untrusted`), a turn containing it is tainted,
   and a tainted turn takes no external action without payload-level confirmation (P20).

## 21. The skill inventory

**Seven directors** — each with its remit, the `doc/08` §xE question list as its declared
competence, its refusal copy, and its citation contract:

`chief-of-staff` · `marketing-director` · `sales-director` · `finance-director` ·
`operations-director` · `people-director` · `strategy-director`

**Shared skills the directors invoke** — one job each, so a change to how a number is
phrased is one file:

| Skill | Job | Writes |
|---|---|---|
| `narrate-metric` | Turns a computed tile + its trace into one sentence | Nothing |
| `explain-refusal` | The honest refusal, naming the reason and the unlock | Nothing |
| `baseline-writer` | Week-one Baseline instead of a Morning Brief | Nothing |
| `morning-brief` | Six items, each with what changed, what it means, what to do | Nothing |
| `finding-writer` | §11's conflict, both sides named | `finding.*` |
| `growth-planner` | Audience, positioning, channels, budget split summing to answer 2.3 | `artifact.*` |
| `content-studio` | Blog, ad, email, captions — honouring `preferred_terms` / `forbidden_terms` | `artifact.*` |
| `proposal-writer` | Proposals, **every price cited to a document page** | `artifact.*` |
| `policy-writer` · `jd-writer` · `sop-interviewer` | People's generation surface | `artifact.*` |
| `competitor-watch` | Observed movement, **labelled not named** until confirmed | `fact.*` |

**Seven onboarding skills stay as they are.** They are the working proof the pattern
holds.

## 22. What this buys, and what it costs

**Buys:** the wording of every director is editable without a deploy; `disabled_ai_skills`
becomes a real per-director kill switch; the schema-failure rate per skill is the
leading indicator of prompt drift (P21's console); and a director's blast radius is
readable in twelve lines of TOML by someone who does not read Python.

**Costs:** twenty-odd new directories, each needing its schema and its eval. That is the
right cost — the alternative is seven prompts inside seven route handlers, which is the
thing `skills.py`'s docstring was written to prevent.

---

# Part VI — Delivery

## 23. Build sequence, against `doc/12`

| Step | Lands in | Work | Days |
|---|---|---|---|
| ~~**A**~~ | **done, 9 Sep** | **Registry unification (§5)** · the source ledger (§16) · **settings panel 5, Reporting** with migration 0027 and the restate stamp. Five defects fixed, five more found and recorded (§26). 1,171 API tests and 54 web tests green; 3 pre-existing failures unrelated to it, logged as M20–M22 | 4 |
| **B** | **P14** | Grounding, `generation` rows, the working drawer's backing, **the numeral guard (§20 rule 1)**, `narrate-metric`. Extend `calculators/`: deltas, weighting, composite. Reserve the finding schema | 8 (planned) |
| **C** | **P15** | Sections + rail · the eight blocks · all seven states with a component test each · derived denominators · gap banner · assistant panel reserved | 6 (planned) |
| ~~**D**~~ | **done, 9 Sep** | **Setup · Watchlist · "what we will not ask you"**, all six departments with a question block. The first ten capabilities a person can open, so the completeness meter stops reading zero. `FACTS` — the last unused block kind — is what Setup renders as | 3 |
| ~~**E**~~ | **done, 9 Sep** | **All five panels.** 2 preferences · 3 the department block, where the restate rule is actually triggered by a person · 7 departments, with its own endpoint · 10 the Brain, read-only · 12 the audit log. Plus the restate rule extended to a department answer, naming the capabilities that read it | 3 |
| ~~**F**~~ | **done, 9 Sep** | **ADR 0026, end to end.** The constraint lifted (a deletion, no migration) · `GET /auth/workspaces` and `POST /auth/workspace` · `domain/group.py`'s per-entity read path · panel 4b · the shell switcher, which **reloads rather than re-renders** · nine guard tests. Two companies on one login, verified in a browser | 3 of 6 |
| **G** | **P16** | Marketing end to end, and **`marketing-director` as the first director on a skill**. Its data is ADR 0023's, so this now depends on H | 8 (planned) |
| **H** | **P18, pulled early** | **GA4 + Search Console + PageSpeed** (ADR 0023) · OAuth and token encryption · **field-completeness at connect** · revocation → `STALE`. D3 is the blocker | 4 of the planned 10 |
| **I** | **P17** | Members · People directory from the roster · settings panel 8 | 5 (planned) |
| **J** | **P20, pulled ahead of the directors** | **ADR 0024's preconditions** — the five injection evals first, read/write tool separation, tainted-turn payload confirmation, the action audit row, **settings panel 11** | **6 of the planned 12, moved earlier** |
| **K** | **P19** | The remaining six directors and their six skills · the Contributor surface · the Baseline · WCAG 2.1 AA | 12 (planned) |
| **L** | **P18/19** | The rest of the connectors — CRM, accounting, ads, HRIS — and the finding surface (§11) | 6 + **+2, new** |
| **M** | **P20** | The assistant on every director · `propose` on all seven · the first `act` capability behind panel 11 | the remaining 6 |

**The two decisions that moved the sequence.** ADR 0023 pulls the free Google connectors
(H) in front of the first director (G), because a director built against a fixture and a
director built against a real property are not the same work. ADR 0024 pulls the
governance half of P20 (J) in front of the six remaining directors (K), because a
director that ships at `read` and is promoted later is cheap, and one retrofitted with
approval thresholds after it can already act is not.

**Additions to `doc/12`, named rather than smuggled in:** A (registry + ledger +
reporting), D (day-one sections), E (settings panels), **F (multi-entity, 6 days)**, and
the findings half of L. **Eighteen days of new work**, plus twelve days of P20 resequenced
rather than added. A, D and F are the ones that change what the product is; the rest
change what it can prove.

## 24. Tests owed, before the features they guard

- `test_every_consumed_by_names_a_capability_in_the_registry` — Q33's missing half.
- `test_every_capability_declares_a_source_or_a_fact`.
- `test_every_narrated_by_names_a_loaded_skill`.
- `test_delivered_has_exactly_one_source_of_truth`.
- `test_tool_unlocks_are_derived_and_never_advertise_an_undelivered_capability`.
- `test_connect_reports_what_cannot_be_calculated` (P18, planned).
- `test_a_skill_response_containing_a_numeral_absent_from_grounding_is_rejected`.
- `test_no_skill_manifest_declares_a_shell_tool`.
- `test_no_director_skill_declares_a_write_outside_the_field_catalogue`.
- `test_autonomy_above_read_requires_an_enabled_setting_and_a_threshold`.
- `test_changing_the_fiscal_year_marks_affected_tiles_stale_and_logs_it`.
- `test_the_group_path_never_queries_without_a_workspace_guc_set` — ADR 0026's first guard.
- `test_the_group_view_covers_exactly_the_callers_memberships_and_no_more`.
- `test_switching_entity_invalidates_every_cache_keyed_below_the_workspace` — I5, back from the dead.
- `test_departments_are_resolved_per_active_entity_and_never_cached_across_a_switch`.
- `test_an_invitation_to_a_second_entity_grants_no_group_view`.
- `test_persona_settings_never_widen_retrieval` — panel 2, the existing import assert as a route test.
- `test_self_reported_never_renders_in_a_metric_slot`.
- `test_headcount_is_never_computed_from_membership`.
- `test_audit_scores_do_not_contribute_to_a_marketing_score`.
- `test_no_scoreable_department_yet_renders_a_baseline_not_an_empty_state`.
- `test_no_tile_renders_a_zero_for_a_missing_input` (P15, planned).
- Seven component tests, one per state; eight, one per block.

## 25. Decisions — four taken, nine still owed

### Taken on 9 September

| ADR | Decision | What it changed here |
|---|---|---|
| **0023** | **GA4 + Search Console are the first connectors.** Free, need only D3, and they are what makes Marketing scoreable | Step H moves in front of step G |
| **0024** | **Directors may act within customer-set thresholds** — and no agent acts until all six preconditions are green | Step J moves in front of the six remaining directors. `propose` is the interim state |
| **0025** | **Fixed per-tile windows**, stated in every working drawer. No period selector at MVP | §10, and the `Settings` line in every drawer (§6) |
| **0026** | **Multi-entity workspaces at MVP**, reversing Q9/D17 | §4.1 (the group read path), settings panel 4b, step F, and I5 comes back |

**`doc/11` should carry a pointer to ADR 0026** from where Q9 and Q17 are recorded, so
the reversal is visible from the original decision rather than only from here.

### Still owed — for `DECISIONS-REQUIRED.md`, not for me

| # | Decision | Recommendation |
|---|---|---|
| 1 | **D3 — Google credentials.** ADR 0023 makes this the only thing standing between the shell and a working director | Blocking. Nothing else in P18 is needed first |
| 2 | **Which id space is canonical** — `doc/05` numbers or `doc/08` dotted names | **Dotted names**, `doc05_id` retained. ADR 0020 already namespaced them and tested it, so this is close to settled |
| 3 | **The Operations first-party layer** — build at MVP, or leave Operations self-reported until an ops tool connects? | **Build it.** The only department no affordable tool covers, and `doc/05` §6c's adoption risk is a reason to design for it, not to skip it |
| 4 | **Does the Setup section count toward the completeness meter?** | **No.** The meter counts capabilities; answered questions are their own number |
| 5 | **The Arabic-gap capability** (`doc/08` open item 5) | Build it off the crawl, or drop question 2.5. Asking and not using it is the one option to refuse |
| 6 | **The Contributor surface for the five non-Sales departments** | Specify all five here before any Contributor is invited (step I) |
| 7 | **Who arbitrates a finding** (§11) | The **department manager** — it is their department's fact. Escalate only where two departments disagree. **ADR 0026 adds a second question: who arbitrates a finding that spans two entities?** |
| 8 | **Visitor identification** under GCC privacy expectations | Defer. The one tool whose value and whose risk are both about identifying people who did not ask to be identified |
| 9 | **Tender feed provider** (`doc/05` §12, still unidentified) | Leave Opportunity Radar `PLANNED`, not `LOCKED`. There is nothing to connect |
| 10 | **`doc/11` §5.3** — headcount band or headquarters as the fifth company field | Headcount band, so People has a self-reported figure rather than a locked tile |
| 11 | **Group-level billing and seats**, now that one login holds several entities | Out of scope at MVP with billing itself, but ADR 0026 makes it a question that will arrive with the first paying multi-entity customer |

## 26. Defects — five closed by step A, and five it found

### Closed by step A (9 September)

| | Defect | How |
|---|---|---|
| 1 | `consumed_by` strings resolved to no capability, so Q33's guard proved only that a string exists | One id space in `domain/registry.py`, keyed by the bank's own dotted names, **validated at import**. `test_capability_ids.py` holds both directions and proves the guard by breaking it |
| 2 | `consumes_facts=()` for every entry, so `consumers_of()` always returned empty and the review gate's impact ranking (Q59) was inert | Inverted from the question bank at import. `consumers_of("stale_deal_days")` now answers, and a People question feeding an Executive capability is asserted |
| 3 | **Three** delivery mechanisms, not two, and they disagreed: `marketing.py` rendered 3.7/3.8 **live** while `state_for` said **planned** and `completeness()` reported **0 delivered** | One flag pair on the capability, `dashboards.DELIVERED` deleted, `state_for` takes `reachable` as an argument. `marketing.DELIVERED_MARKETING` derives from it |
| 4 | `score_denominator`'s docstring said five where its body returns six (M14) | Rewritten when the table and the counting were brought into one module |
| 5 | Four of `doc/05` §1's seven required global assumptions had no home, so no drawer could state its window | Migration 0027, `domain/reporting.py`, the endpoint and the panel. Each field states what it changes and **how many of this company's tiles move**, derived |

### Found while building it, and open

| | Defect | Where |
|---|---|---|
| 6 | **`implemented` and `reachable` are not the same thing, and Marketing is the proof.** `calculators/audit.py` scores brand and technical SEO and `marketing_state` decides their state — but `marketing_state` is called **from its own test and nowhere else**. P16's "first real dashboard numbers" are not reachable by any user | `domain/marketing.py` ↔ `routes/dashboards.py`. Asserted in `test_capability_registry.py` so closing it is deliberate |
| 7 | **`state_for` and `marketing_state` disagree about 3.7.** SEO Intelligence needs `dataforseo` **and** `crawl`, so the generic function says `PARTIAL` on a crawl alone while Marketing's says `LIVE`. Both are defensible and only one can be on screen. The likely fix is splitting the market half from the keyword half into two capabilities — P16 already describes them as separable | `domain/marketing.py` |
| 8 | **A third capability namespace existed in `connectors.py`** — `stale_deals`, `pipeline_value`, `loss_analysis`, `conversion` — so the connect screen said *"Stale deal detection is unsupported"* about a tile called *"Stale and at-risk deals"*. Two names for one thing reads as two features, one broken. **Fixed in step A**: `FieldRequirement` is keyed by capability id and reads the tile's own name | was `domain/connectors.py` |
| 9 | **`connections.Tool` and the ledger's row were two classes called the same thing for different concepts** — a *provider* you connect (nine, DB-constrained) versus a *source* a capability requires (sixteen). Four CRMs collapse to one source. **Fixed in step A** by naming them apart and adding `PROVIDER_SOURCES` as the join | `domain/sources.py` |
| 10 | ⚠ **Two connectors turn nothing on, and one of them is promised to the customer during onboarding.** No capability requires `SEARCH_CONSOLE`, and onboarding's tools step shows *"Telling you which searches you already rank for, from your own data."* **ADR 0023 makes it one of the first two connectors to build.** `PAGESPEED` is the same shape without the promise: the audit computes a performance score and no capability holds it. Either `marketing.content_pages` and `marketing.site_performance` arrive with step D, or ADR 0023 is GA4 alone | asserted in `test_source_ledger.py` |
| 11 | **Stripe is mapped to accounting because there is no payments source.** *"Revenue as it lands"* is honourable against a ledger, but payments and bookkeeping are not the same system and no capability distinguishes them | `PROVIDER_SOURCES` |
| 12 | `connected_sources()` takes no workspace, so per-workspace connection state is not expressible — and `workspace_connection` rows already exist to read. P18 must change the signature before any tile reads it | `routes/dashboards.py:58` |
| 13 | The `disabled_ai_skills` kill switch **is** enforced (`anthropic_provider.py:104`), but `grounding/pipeline.py:52` still documents it as never consulted, and there is no surface to set it | `pipeline.py:52` · settings panel 11 |
| 14 | Department selection has no post-onboarding home, so a company that adds a department cannot add its director | settings panel 7 |
| 15 | `doc/08` asks Finance 4.1 (financial year end); ADR 0020 cut it because the company stage asks when the year *starts*. `doc/08` §4C still leans on it — and 0027 now stores the start on the workspace, which is where a window can actually read it | `doc/08` §4A |

### Found in step B

The pattern in all of these is one thing: **P14 was built and never joined.** The
pipeline, the numeral guard, eleven evals and four calculators were all real,
and nothing called any of them. That is a harder failure to see than an absent
feature, because every test passes and the phase reads as done.

| | Defect | Where |
|---|---|---|
| 16 | **`pipeline.run` had no callers.** The guard that makes I1 testable was a pure function nothing invoked, so the phase's central claim held in eleven evals and nowhere a customer could reach | `grounding/pipeline.py` |
| 17 | **`generation` had zero rows**, two indexes and three check constraints. One of those indexes carries the comment *"the daily budget reads this"* — and nothing read it | migration 0023 |
| 18 | **Both token budgets were still unread.** `tenant_daily_token_budget` and `user_daily_token_budget` have been in `config.py` since M0, and the pipeline took a `Budgets` value object that nothing built | `config.py` ↔ `pipeline.py` |
| 19 | **The runner and the pipeline each retried once.** Composed at their defaults that is **four** provider calls where P14 specifies two, and the second pair is indistinguishable from the first in the log. `invoke` now takes `attempts`, and the narrator passes 1 | `ai/runtime/runner.py` |
| 20 | **`UnavailableReason` had no member for an absent API key.** ADR 0011 makes that a first-class supported state, so it would have rendered as `SCHEMA_INVALID` — *"the model wrote something malformed"* shown for *"the product is misconfigured"*, on the one screen where somebody is deciding whether to trust us. `MODEL_UNAVAILABLE` and `PROVIDER_FAILED` are the two states that were missing | `grounding/pipeline.py` |
| 21 | **There was no Company Context assembler.** P14's *"the single path, no widget builds its own context"* was a sentence in a plan rather than a module anything had to go through | `grounding/context.py` |
| 22 | `test_every_skill_is_reachable_from_a_command` assumed a command is the only thing that can call a skill. True until one was called from a dashboard instead of from onboarding — widened by importing `NARRATOR` rather than by adding a string exception | `tests/test_skill_runtime.py` |
| 23 | **`calculators/deltas.py` is written and uncalled.** Delta, weighted, exposure and composite are pure and tested, and no capability computes with them yet. They are what `narrate` takes as `computed`; the first tile closes it (M23) | `calculators/deltas.py` |

### Found in step D

| | Defect | Where |
|---|---|---|
| 24 | ⚠ **`context.assemble` read the membership where it should have read the reach.** An Owner reaches every department by role and has none on their membership, so a founder who had just registered opened Finance and Setup told them nobody had answered anything — with three answers in the table. The page was right about their access and wrong about their data. **Found in the browser**, invisible to every test because each one constructed a scope with the department already on it | `grounding/context.py` |
| 25 | **An Owner's snapshot was tagged `L3:finance`** while their context held seven departments' answers. Understating a snapshot's scope is the direction that matters, and the retention and export queries read that column | `context.scope_key` |
| 26 | **`doc/13` §9's Watchlist describes five cards and four exist.** The fifth reads question 8.3 — *"what decision have you been putting off?"* — which `doc/08` §8A asks and **the question bank never did**: ADR 0020 cut it to six departments with a block, and the Chief of Staff asks nothing of its own. Either the bank gains an executive block or the card leaves the design | `sections.WATCH_ITEMS` |
| 27 | **The Setup tab was `locked` on *"needs your setup answers"*** when it declared `ONBOARDING` as a required source — an instruction to supply the very thing it exists to show back. It needs no source: it computes nothing, and an empty Setup is a fact about the answers rather than about our access | fixed in `_our_sections` |
| 28 | `connected_sources()` returns an empty set while `sources.DAY_ONE` says a workspace holds four sources before it connects anything. The two disagree because the first cannot see a workspace (defect 12) — so no first-party source can currently be reported as present | `routes/dashboards.py` ↔ `domain/sources.py` |

### Found in step E

| | Defect | Where |
|---|---|---|
| 29 | **The department-block answer route audited nothing.** The *company* questions have been audited since P4; correcting a department threshold — the stale-deal window, what counts as late — wrote a row and left no trace. Fixed, and the audit row **names the capabilities that read the answer** rather than counting them: "three tiles were affected" is a number nobody can check | `routes/spine.py` |
| 30 | **`POST /onboarding/departments` calls `complete_stage`**, so it cannot serve a settings screen — pointing panel 7 at it would re-advance a finished spine every time somebody changed their mind, and the change would read as onboarding progress in the audit trail. Panel 7 has its own endpoint | `routes/companies.py` |
| 31 | ⚠ **The audit log is readable by an Executive.** `GET /audit-log` gates on `require_executive_surface`; `doc/08` §8C says the log is **Owner-visible only**. Narrowing a permission belongs where the permission is decided, and P21 owns making the log access-controlled in its own right — so this is recorded rather than changed | `routes/audit.py` |
| 32 | **The audit log shows no actor.** It stores `actor_user_id` and the endpoint returns the UUID; resolving it to a person needs a join the route does not make. A UUID is useless to a human, so the panel names the gap rather than printing one | `routes/audit.py` |
| 33 | **The settings screen now fans out to eight independent endpoints**, each with its own round trip to `us-east-2`, and the slowest decides when the page is complete. Measured in the browser: the Departments and Brain panels were still loading twenty seconds after the rest had rendered. Finding #23's shape on a new screen — and the reason each panel loads on its own is that a combined endpoint would put a view's shape into the API | `components/settings/` |
| 34 | **`doc/13` §14 asks the Brain panel for per-item sensitivity, passage counts and a delete, and it has none of the three.** `GET /onboarding/brain` serves the assembled brain with its provenance; the per-fact view is the `fact` table, which no endpoint exposes. Deletion is P21's and must not be approximated — a button that removed the row and left the embeddings would say a fact was gone while it stayed retrievable | `BrainCard.tsx` |

### Found in step F

The headline is what was **not** found. ADR 0026 predicted the reversal would be
affordable because `membership` was left many-to-many and the scoping
consolidation had just landed, and that held: lifting one-person-one-company was
a deletion of one function and three call sites, with **no migration**.

| | Defect | Where |
|---|---|---|
| 35 | **The guard was already inert at two of its three sites.** `assert_no_live_membership`'s docstring said it was *"called by `create_workspace_for_claim` and by `invitations.accept`"*; it was in fact called from `auth/companies.py`, `auth/domains.py` and `auth/invitations.py`, and the docstring named neither of the first two. A guard whose own comment cannot locate its callers is one nobody could have reasoned about before changing | was `domain/membership.py` |
| 36 | **I5's cache-invalidation requirement is currently satisfied by there being nothing to invalidate.** Every `lru_cache` in the application is keyed by the *process* — settings, three engines, the provider, the embedder — and `current_scope` rebuilds the scope and its departments per request. So the guard is a census: `test_nothing_is_cached_across_an_entity_switch` walks the AST for every cache decorator and compares it against that list. **Writing it found a sixth I had missed** (`get_embedder`), which is the argument for a census over a hand-kept list |
| 37 | **Three tests in `test_identity_flow.py` asserted the rule ADR 0026 reversed.** Replaced rather than deleted: `test_multi_entity.py` holds the four guards that matter now, and what stays in the identity file is the one claim it is the right home for — that `membership` is unique on `(workspace_id, user_id)` and never on `user_id` alone, read from the live catalogue rather than from migration `0002` | `tests/test_identity_flow.py` |
| 38 | ⚠ **Nothing yet aggregates a group figure.** `read_across_entities` is the read path and it is generic over the value on purpose — deciding what an entity's figure *is* would make it a second place numbers come from. The group composite that `doc/13` §4.1 describes (*"four entities, three scored"*) needs a capability to compute per entity first, and none is reachable yet | `domain/group.py` |

### Found finishing step F

Three of these came from a browser and none from a test, which is the pattern
worth noticing: every one is about what happens *between* two entities, and a
test that constructs one scope cannot see between anything.

| | Defect | Where |
|---|---|---|
| 39 | ⚠ **The switch reply named the entity being left.** `CurrentSession` resolves at the start of the request, so after the `UPDATE` its `active_workspace_id` still held the old workspace — and the route returned the list computed against it. The write landed and the audit row proved it; the reply said it had not happened. Every test asserted the write or the refusal; **none asserted the flag a client actually reads** | `routes/auth.py::_workspaces_for` |
| 40 | ⚠ **Login left a two-entity account with no active company**, and `current_scope` answers that with *"No workspace selected"* — which the dashboard read as a dead session and bounced to sign in. A loop. The existing comment is right that picking one of several risks acting in the wrong client's workspace, so the fix is not to pick: login now **resumes** the pointer from that person's most recent session, filtered against live memberships, which is what the sign-in screen already promises. A genuine first sign-in gets a chooser | `routes/auth.py` · `DirectorPage` |
| 41 | **The switcher vanished when its own fetch failed.** The first version caught the error and set `[]`, which renders nothing — so a 503 under load left somebody holding two companies with no way to move and nothing saying why. It now falls back to a route into panel 4b, which reports its own errors properly. Found when the proxy timed out while the suite was running | `EntitySwitcher.tsx` |
| 42 | **`/dashboard` redirects an Owner to `/dashboard/executive`**, so a switch that navigates to `/dashboard` appears to leave the URL unchanged. Not a defect — but it made a browser check read as a failed switch for several minutes, and the next person to verify this deserves the sentence |  |
| 43 | **The reporting panel could not set the currency or the country**, so every figure in the product rendered in the `OMR` fallback `context.assemble` hard-codes — for a Dubai or a Riyadh company, a wrong unit on a correct number. Both are now on `ReportingIn`/`ReportingOut` and both are **audited**, because relabelling every figure is a restatement of the record even though it recomputes nothing. Note the currency is the third `Consequence` case: it restates and moves **zero** tiles, and a screen that only knew "restates ⇒ moves N tiles" would have said *"moves 0 tiles"* | `routes/companies.py` · `domain/reporting.py` · `ReportingCard.tsx` |
| 44 | **Not one auth or company field was marked `required`**, so a screen reader announced every one of them as optional and the browser's own pre-submit prompt never fired — the first feedback on an empty email was a round trip to `us-east-2` and a red box. `Field` now takes `required` and sets both the attribute and `aria-required` on the input and the select | `components/auth/Field.tsx` and its five forms |
| 45 | **The landing page's one concrete promise was the one thing the product cannot do.** *"Seven minutes from now, you could be reading an honest audit of your own business"*, a `Minute 7 — The audit` moment, a pricing bullet and an FAQ answer all promised the onboarding audit; `calculators/audit.py` scores a crawl and **no route serves it** (M19). All four now describe the Brain and the per-tile honesty — which is built, and is the better promise: the audit is a number, and the gap-instead-of-a-guess is the argument | `lib/content.ts` |
| 46 | **The primary CTA did not convert.** *"Start free"* in the nav — desktop and mobile — and *"Start free trial"* on the Starter tier all pointed at `#cta`, an anchor further down the same page whose own button then goes to `/register`. Two clicks to sign up and the first only scrolled. Destination is per-tier data now, because the three tiers genuinely differ: Starter is self-serve at a stated price, and the other two are priced *"Let's talk"* with **no channel to talk through** — no booking system, no `/contact`, no address in the repo. Those two stay on the scroll and the missing channel is **D24**, because inventing a support address is inventing a fact about the business | `Nav.tsx` · `Pricing.tsx` · `lib/content.ts` |
| 47 | **Settings gated all eight panels on a fetch six of them did not need.** The screen blocked on `fetchCompany` + `fetchState`, and only then did the six prop-less panels mount and start their own requests — one serial round trip to `us-east-2` in front of everything, which is what made the audit log still be loading after 10s. Only the identity line, the domain card, the invite form and the per-department blocks need that data; the rest now mount immediately and fetch in parallel. **Reduces M27 rather than closing it** — it is still eight requests, but they are no longer eight-after-one | `SettingsPanel.tsx` |
| 48 | ⚠ **My own regression, caught in a browser within a minute.** Scoping the company failure to its own region meant a dead API rendered *seven* identical red boxes where the old full-screen gate had said it once — and the first fix was wrong too, because it keyed on `401/403/0` while `auth-proxy.ts` returns **503** for "could not reach the API". Every panel proxies through that same BFF, so 503 is as global as a 401. The takeover now covers refusal *and* unreachability; anything else stays scoped, since the other six read different endpoints | `SettingsPanel.tsx` |
| 49 | **A switch had no visible outcome.** `/dashboard` redirects an Owner to `/dashboard/executive`, so switching *from* a dashboard navigated to the address already on screen — same URL, same layout, and the only changed pixels were which pill was dark (defect 42, which I had recorded as "not a defect but worth a sentence"). It is worse than cosmetic for a screen reader, which a same-URL navigation tells nothing at all. Both switchers now carry `?switched=1` — the only channel that survives a hard navigation — and announce **which** company is now active via `role="status"`, named from the session-backed list rather than from the URL, then strip the flag so a refresh does not re-announce it | `EntitySwitcher.tsx` · `EntitiesCard.tsx` |
