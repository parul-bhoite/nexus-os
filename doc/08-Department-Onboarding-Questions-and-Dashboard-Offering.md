# NEXUS OS — Department Onboarding Questions & Dashboard Offering

Version 1.0 · 18 August 2026 · Parul Bhoite

**What this is.** For each of the seven departments: the questions onboarding asks,
the configuration options behind each one, what NEXUS deliberately *does not* ask
because a connector answers it, and what that department's dashboard offers.

**Where it sits.** Doc 04 argued about what should be asked versus inferred. Doc 05
specified the full offering for each director. This document records **what is
actually asked and actually shown**, as built in `prototype/nexus-os-prototype.html`.
Where the two differ, §11 says so — doc 05 remains the target scope and this is the
current cut of it.

**Provenance.** Every question, option, tile and section below was extracted from the
prototype source rather than retyped, so this document cannot drift from the build
without the extraction failing. The sample values shown are illustrative.

---

## 0. How to read this

### The two rules that decide whether a question exists

**1 — Only ask what cannot be fetched.** A question whose answer sits in a
connected system is a question that wastes the customer's time and, worse, invites
a typed guess that NEXUS will then treat as fact and rank alongside a measurement.
Each department section therefore has a *"Not asked — fetched instead"* table. That
table is shown to the customer during onboarding, because demonstrating what the
product refuses to ask is more persuasive than asking would be.

**2 — Ask what only this person knows.** Thresholds, definitions and intent exist
in no API. *"What counts as a lead"* and *"after how many days of silence should a
deal be flagged"* change every downstream number, and no crawl will ever supply
them. These are the questions that earn their place.

### Question types

| Type | Control | Notes |
|---|---|---|
| `select` | Single-choice dropdown | Options are exhaustive and include an honest "not yet" or "no formal X" where that is a real answer |
| `input` | Single-line text | Free text; validated only for length |
| `textarea` | Multi-line text | Used where the answer is a definition or a judgement, not a value |

Every answer is stored as an L1 or L2 fact in the Company Brain and cited whenever a
recommendation depends on it. A `select` answer that later contradicts measured data
is surfaced as a conflict rather than silently overridden.

### Who answers what

The workspace owner selects which departments the company runs and answers those
departments' questions. **An invited team member answers only their own
department's set** — a Sales Executive is never asked when the financial year ends.

### Widget states

Unchanged from doc 05 §0: *Live · Partial · Locked · Warming · Self-reported*. Never
a zero, never a blank, and self-reported values never silently mixed with fetched
ones.

---

## 1. Asked once, company-wide

Asked before any department block, because they are true of the company regardless
of who is filling the form in.

| # | Question | Type | Options / sample | Why it is asked | What it changes |
|---|---|---|---|---|---|
| 1.1 | What does the business sell? | `input` | *Industrial supplies & distribution* | The crawl infers a category imprecisely; the customer's own words anchor every generated artefact | Content generation, competitor matching, opportunity relevance |
| 1.2 | Who is the typical customer? | `input` | *Contractors and facilities teams in Muscat, Sohar and Salalah* | Segment and geography cannot be reliably read from a website | Enquiry qualification, market sizing, regional analysis |
| 1.3 | Reporting currency | `select` | OMR — Omani rial · AED — UAE dirham · SAR — Saudi riyal | No source states it unambiguously | Every monetary figure, every threshold, all formatting |
| 1.4 | Roughly how many people? | `select` | Under 10 · 10–50 · 50–200 · Over 200 | Sizes the People department and the plan tier | Per-person metrics, benchmark selection |

### 1.5 Purpose — why are you here?

One choice. It changes what each dashboard leads with, not what it contains.

| Value | Label | Effect on the product |
|---|---|---|
| `diagnose` | Find out what is quietly broken | Leads with risks and anomalies |
| `consolidate` | Get one place for the numbers | Leads with the scoreboard and its sources |
| `time` | Free up my own time | Leads with the work NEXUS can do for you |
| `grow` | Prepare for growth or funding | Leads with trend, margin and capacity |

### 1.6 Departments — what are you responsible for?

Multi-select across the seven below. Selecting one produces 9 fields in total;
selecting all seven produces 39. At least one is required.

### 1.7 Role, set per invited person

Not a question the owner answers about themselves — set when inviting each person.
This table is the security model and is reproduced from `app/domain/scopes.py`.

| Role | Max sensitivity | Departments | Workspace they get |
|---|---|---|---|
| Owner | L3 Department | All | Composite view and admin portal |
| Executive | L3 Department | All | Composite view and admin portal |
| Department manager | L3 Department | Own | Everything in their department |
| Contributor | L3 Department | Own | **Their own records only — no department totals** |
| Viewer | L2 Company internal | None | Company-internal summaries only |
| External | *Nothing by role* | None | Only items shared with them explicitly |

**L4 Restricted is absent from this table on purpose.** No role reaches it,
including the Owner's. It is reached only by being named on the item.

---

## 2. Marketing — *Marketing Director*

### 2A. Questions asked — 5

| # | Question | Type | Options / sample | What it changes |
|---|---|---|---|---|
| 2.1 | What counts as a lead worth passing to Sales? | `textarea` | *A named contact at a company with a live project and a budget holder identified* | **The denominator of every conversion figure.** Without it, "conversion rate" is a number with no agreed meaning |
| 2.2 | Which channels do you actively run? | `select` | Search and referrals · Search, paid and social · Trade shows and referrals · Everything | Which channel rows appear, and which absent channels are reported as *not run* rather than *zero* |
| 2.3 | Monthly budget you are willing to spend on acquisition? | `input` | *OMR 1,500* | Budget-vs-actual, and the Growth Plan's allocation must sum to this |
| 2.4 | Who do you most often lose to? | `input` | *Two regional distributors on price* | Seeds competitor tracking before discovery runs |
| 2.5 | Is Arabic-language content in scope this year? | `select` | Not yet · Planned · Already publishing | Whether the Arabic-language gap is reported as an opportunity or suppressed as out of scope |

### 2B. Not asked — fetched instead

| What | Source |
|---|---|
| Sessions, sources and conversion rate | Google Analytics |
| Keyword positions and impressions | Search Console |
| Ad spend and cost per click | Google Ads |

### 2C. Dashboard offering — 5 sections

| Section | What it offers |
|---|---|
| **Overview** | Four tiles: Website sessions · Enquiries · Enquiry conversion · Cost per enquiry. Plus a 12-week sessions trend. Each tile opens to its method, inputs and arithmetic |
| **Channels** | Table over 30 days: Channel · Sessions · Enquiries · Conversion · Spend · Cost per enquiry. Conversion and cost are computed per row from the columns beside them; a dash means no spend to divide by, not zero cost |
| **Content & pages** | Top pages by impression change: Page · Impressions · Prior period · Change · Average position. Plus a *"Gap NEXUS found"* panel — currently the Arabic-language mismatch |
| **Campaigns** | Per campaign: status, days running, spend, enquiries, cost per enquiry. Draft campaigns show dashes rather than zeros |
| **Enquiries** | Last 7 days: When · Source · Region · Passed to · Status. **No deal-value column, deliberately** — Marketing needs to know an enquiry converted; the amount is Sales' to hold |

### 2D. Locked until connected

| Tile | Needs |
|---|---|
| Social reach | Connect LinkedIn |

### 2E. Assistant answers

- Where did this month's enquiries come from?
- What is working best right now?
- Should I cut the paid budget? *(answers, but flags that Google Ads has not synced for three days and the figure is stale)*
- What are we missing?

---

## 3. Sales — *Sales Director*

### 3A. Questions asked — 5

| # | Question | Type | Options / sample | What it changes |
|---|---|---|---|---|
| 3.1 | What are your pipeline stages, in order? | `input` | *Enquiry → Qualified → Proposal → Negotiation → Won* | The board columns, and the stage-conversion rates the forecast is built from |
| 3.2 | After how many days of silence should NEXUS flag a deal? | `select` | 7 days · 10 days · 14 days · **Use my median cycle** | The stale-deal threshold. "Use my median cycle" derives it from their own history rather than a generic 30-day rule |
| 3.3 | How are new leads assigned? | `select` | Round robin · By region · By product · Manager assigns | Whether unassigned leads are an error state or normal |
| 3.4 | What is the quota period? | `select` | Monthly · Quarterly · Annual · No formal quota | The attainment window. "No formal quota" suppresses attainment entirely rather than inventing a target |
| 3.5 | What disqualifies a deal outright? | `textarea` | *No budget holder, or a required lead time under two weeks* | Which deals are excluded from the forecast rather than weighted low |

### 3B. Not asked — fetched instead

| What | Source |
|---|---|
| Deals, values, stages and activity dates | CRM |
| Win rate and median cycle length | CRM history |
| Quota attainment per person | CRM |

### 3C. Dashboard offering — 5 sections

| Section | What it offers |
|---|---|
| **Overview** | Four tiles: Pipeline value · Deals gone quiet · Win rate (90 days) · Average deal size. Plus a *"Needs you today"* table of stale deals with owner, value, days silent and next step |
| **Pipeline** | Kanban board by stage with per-column count and value. A clay edge marks anything silent longer than the threshold from 3.2 |
| **Accounts** | Every account in the department: Account · Stage · Owner · Open value · Last contact |
| **My team** | Per person: quota attainment bar, won against target, open deal count. Manager-only |
| **Forecast** | Weighted forecast · Best case · Committed · Median cycle, plus the stage-conversion table those weights come from — measured from their own closed deals |

### 3D. Locked until connected

None. Sales is fully scoreable once the CRM is connected.

### 3E. Assistant answers

- What is in the pipeline?
- Which deals are at risk?
- What will we actually close this quarter?
- How is the team tracking?

---

## 4. Finance — *Finance Director*

### 4A. Questions asked — 5

| # | Question | Type | Options / sample | What it changes |
|---|---|---|---|---|
| 4.1 | When does your financial year end? | `select` | 31 December · 31 March · 30 June · 30 September | Every period comparison, every year-to-date figure |
| 4.2 | Standard payment terms you offer? | `select` | On receipt · 30 days · 45 days · 60 days | The ageing buckets, and what counts as overdue |
| 4.3 | Above what amount does spend need approval? | `input` | *OMR 1,000* | Which requests enter the approvals queue at all |
| 4.4 | Who approves spend above that? | `select` | Owner only · Owner or Finance Manager · Department manager · Board | Where an approval routes |
| 4.5 | How many months of runway would worry you? | `select` | Under 3 · Under 6 · Under 9 · Under 12 | The runway alert threshold — a judgement, not a benchmark |

### 4B. Not asked — fetched instead

| What | Source |
|---|---|
| Bank balances, invoices and ledger detail | Accounting |
| Receivables ageing and payment history | Accounting |
| Gross margin and cost lines | Accounting |

### 4C. Dashboard offering — 5 sections

| Section | What it offers |
|---|---|
| **Overview** | Four tiles: Cash position · Cash runway · Gross margin · Receivables over 60 days |
| **Cash & runway** | Balances by account with cleared dates, plus a 12-month cash trend. Runway states its window so one unusual month cannot distort it unseen |
| **Receivables** | Ageing profile in four buckets computed from invoice due dates, plus the oldest open invoices with days overdue and last-chased date — including *"not yet"* where nobody has chased |
| **Payables** | Supplier · Amount · Due, with overdue flagged |
| **Approvals** | Queue of requests, each carrying who asked, what for, how much and how long it has waited |

### 4D. Locked until connected

| Tile | Needs |
|---|---|
| Budget vs actual | Upload this year's budget |
| Payroll detail by person | **L4 Restricted — not available by role, including the Finance Manager's** |

### 4E. Assistant answers

- What is our cash position?
- Who owes us and how late are they?
- Is margin holding up?
- What needs approving?

---

## 5. Operations — *Operations Director*

### 5A. Questions asked — 5

| # | Question | Type | Options / sample | What it changes |
|---|---|---|---|---|
| 5.1 | What do you promise customers as a lead time? | `input` | *3 working days within Muscat, 5 elsewhere* | The baseline on-time dispatch is measured against |
| 5.2 | What usually causes a delay? | `select` | Stock-outs · Supplier lead time · Picking capacity · Transport | Which bottleneck NEXUS checks first when dispatch slips |
| 5.3 | Do you hold stock, or order per job? | `select` | Hold stock · Order per job · Both | Whether stock levels and reorder minimums apply at all |
| 5.4 | At what point is an order officially late? | `select` | Missed promised date · One day after · Three days after | The definition of "late" — and therefore the on-time percentage |
| 5.5 | Which supplier are you most exposed to? | `input` | *One valve supplier, roughly a third of purchases* | Concentration risk, before purchase history is long enough to show it |

### 5B. Not asked — fetched instead

| What | Source |
|---|---|
| Order status, dispatch dates and lateness | Operations system |
| Stock levels against minimums | Operations system |
| Supplier on-time delivery | Purchase history |

### 5C. Dashboard offering — 4 sections

| Section | What it offers |
|---|---|
| **Overview** | Four tiles: On-time dispatch · Open orders · Warehouse utilisation · Stock-outs this month. Plus a 12-week dispatch trend and a *Bottleneck* panel naming the slowest stage with its mean hours |
| **Dispatch board** | Four lanes — Awaiting pick · Picking · Ready · Late — with every order named. NEXUS will not report "88% on time" unless it can also say which 12% were not |
| **Stock** | Watch list: SKU · On hand · Minimum · Status, with a reorder action. Items are ordered by consequence, not alphabetically |
| **Suppliers** | Per supplier: on-time percentage and lead time, so the combination that caused a stock-out is visible |

### 5D. Locked until connected

None in the current cut. Operations is first-party data (doc 05 §6), so its
availability depends on adoption rather than on a connector.

### 5E. Assistant answers

- Why are we shipping late?
- What is about to run out?
- Which supplier is causing problems?
- What is on the floor today?

---

## 6. People — *People Director*

### 6A. Questions asked — 5

| # | Question | Type | Options / sample | What it changes |
|---|---|---|---|---|
| 6.1 | Is leave accrued monthly or granted annually? | `select` | Accrued monthly · Granted annually · Mixed by contract | How the leave liability is computed — a different formula, not a different label |
| 6.2 | Who signs off a new hire? | `select` | Owner only · Owner and department manager · Department manager | Where a requisition routes |
| 6.3 | What is your biggest people risk right now? | `textarea` | *One warehouse supervisor vacancy is holding back dispatch* | Seeds the cross-department link between a vacancy and its operational impact |
| 6.4 | Do you run performance reviews on a cycle? | `select` | No formal cycle · Annual · Twice a year · Quarterly | Whether review timing appears at all |
| 6.5 | Should NEXUS track visa and document expiry? | `select` | Yes · No · Not yet | A GCC-specific capability, opt-in because it involves sensitive documents |

### 6B. Not asked — fetched instead

| What | Source |
|---|---|
| Headcount, start dates and contract types | HRIS |
| Leave balances and accruals | HRIS |
| Open requisitions and time to hire | HRIS |

### 6C. Dashboard offering — 4 sections

| Section | What it offers |
|---|---|
| **Overview** | Four tiles: Headcount · Open roles · Attrition (12 months) · Accrued leave liability |
| **Hiring** | Candidate pipeline across Applied → Screened → Interviewed → Offer, plus open roles with days open, furthest stage, and a **Measured impact** column filled only where a real measurement moved — *"No measured impact yet"* is a valid answer |
| **People** | Person · Department · Started · Type · Compensation, where compensation shows as **L4** for every row |
| **Leave** | Upcoming leave with a Cover column that flags where leave overlaps an open vacancy |

### 6D. Locked until connected

| Tile | Needs |
|---|---|
| Engagement | Run the first pulse survey |
| Individual salaries | **L4 Restricted — not available by role, including the People Manager's** |

### 6E. Assistant answers

- What is our headcount?
- Where are we on hiring?
- Any leave I should worry about?
- Is attrition a problem?

---

## 7. Strategy — *Strategy Director*

### 7A. Questions asked — 5

| # | Question | Type | Options / sample | What it changes |
|---|---|---|---|---|
| 7.1 | What would make the next twelve months a success? | `textarea` | *Two annual supply contracts signed and on-time dispatch back above 95%* | What every opportunity is ranked against |
| 7.2 | Which competitors should NEXUS watch? | `input` | *The two regional distributors we lose to on price* | Seeds the tracked set before discovery |
| 7.3 | Which market or segment are you trying to enter? | `input` | *Sohar industrial estate* | Whether a regional signal is an opportunity or noise |
| 7.4 | What is the binding constraint today? | `select` | Cash · People · Stock · Demand · Time | Which recommendations are suppressed as unactionable |
| 7.5 | What are you deliberately not doing? | `textarea` | *No retail counter, no direct import* | **Prevents NEXUS recommending something already ruled out** — the question that most improves perceived intelligence |

### 7B. Not asked — fetched instead

| What | Source |
|---|---|
| Competitor pages and observed changes | Web crawl |
| Share of search against a tracked set | Search Console |
| Category search volume | Search data |

### 7C. Dashboard offering — 4 sections

| Section | What it offers |
|---|---|
| **Opportunities** | Ranked cards, each with the evidence that produced it, an estimated size, and a stated confidence. An opportunity with no evidence trail is not shown at all |
| **Competitors** | Observed movement per competitor with a Watching flag. Competitors are **labelled, not named**, until the customer confirms the match — NEXUS will not attach an observed price change to a company on inference alone |
| **Market signals** | Share of search · Category search volume · Brand searches · Competitor branch openings, plus a 12-month share-of-search trend |
| **Strategic bets** | Each bet with status, owner and the evidence behind it |

### 7D. Locked until connected

| Tile | Needs |
|---|---|
| Market sizing | Confirm your served segments |
| Pricing position | Add your price list |

### 7E. Assistant answers

- What is the biggest opportunity?
- What are competitors doing?
- Are we gaining or losing ground?
- What is holding us back?

---

## 8. Chief of Staff — *Executive*

Cross-department. Available to Owner and Executive roles only, because it combines
every department and therefore sits above departmental scope rather than inside it.

### 8A. Questions asked — 5

| # | Question | Type | Options / sample | What it changes |
|---|---|---|---|---|
| 8.1 | What do you check first, most mornings? | `select` | Cash · Pipeline · Orders going out · Nothing regular | What the Morning Brief leads with |
| 8.2 | Which number do you not currently trust? | `input` | *Gross margin by product line* | Which figure gets its full working shown by default rather than on request |
| 8.3 | What decision have you been putting off? | `textarea` | *Whether to open a stock point in Sohar* | Seeds the decision queue with something real on day one |
| 8.4 | How would you like to be interrupted? | `select` | One brief each morning · Only when something breaks · Weekly summary | Notification cadence |
| 8.5 | Who should see company-wide figures? | `select` | Me only · Me and one other · All managers | Who else gets the Executive surface |

### 8B. Not asked — fetched instead

| What | Source |
|---|---|
| Every department score and the composite | All connected sources |
| What changed since yesterday | Change detection |
| Decisions waiting on you | Your managers |

### 8C. Dashboard offering — 6 sections

| Section | What it offers |
|---|---|
| **Morning brief** | Each item states what changed, what it means and what to do, with its source named. Plus a 12-month health trend and a *From your managers* decision list |
| **Business health** | The composite with its denominator, Revenue MTD, Cash position, Cash runway — and a panel explaining *why the composite is shown at all*: it is only displayed because all seven departments are scored |
| **All departments** | Every department's score, coverage and the manager who owns it. Read-only — each manager owns their own workspace |
| **Decisions** | Each decision with who raised it, why, what it costs, and Approve / Ask for more |
| **Company Brain** | Every item NEXUS holds: Item · Kind · Sensitivity · Passages · Updated. Deleting an item removes its passages, embeddings, cached answers and derivations |
| **Admin portal** | Users and the workspace each one gets · roles and max sensitivity · the audit log, which records refusals as well as successes and is Owner-visible only |

### 8D. Locked until connected

None. The composite is suppressed rather than locked if coverage is incomplete —
it reports the departments it has and says so.

### 8E. Assistant answers

- Why is business health 72 and not higher?
- What should worry me most this week?
- How long is our runway?
- What is waiting on a decision from me?
- Why has dispatch slipped?

---

## 9. Present in every workspace

| Element | Detail |
|---|---|
| **Top bar** | Company, verified domain, live source count, sources needing attention, the workspace name, the person |
| **Metric tile** | Value, unit, delta, source chips, and *"+ why this number"* opening the method, the inputs and the arithmetic |
| **Locked tile** | The label, the reason, and the named unlock. Never a zero, never an empty box |
| **Scoped assistant** | Docked bottom-right. The department's director. Cites every answer, refuses out of scope with a reason, reads by default and offers a confirmation before anything with an outside effect |
| **Navigation** | Assembled from the person's own department. There is no list of other departments to grey out |

---

## 10. The Contributor variant

A Contributor does not get their manager's workspace with tiles removed. They get a
smaller product, and the difference is structural. Worked example — a Sales
Executive:

| Section | What it offers |
|---|---|
| **My day** | Today's actions in priority order, each with the reason it is ranked there, plus their own five accounts |
| **My deals** | The same board the manager uses, containing only their accounts |
| **My accounts** | Their assigned accounts with next step |
| **My targets** | Won this month · Still to close · Their open deals · Their median cycle, plus progress to target |

**Withheld, and not as gaps:** pipeline value, win rate, average deal size, the
team leaderboard, the department score and the department-wide funnel. There is no
lock icon on any of them, because they were never part of this application. A card
on *My day* explains that department totals belong to their manager.

**No leaderboard appears anywhere in a Contributor workspace.** A comparison
against colleagues is a management tool, and this is not a management view.

### 10A. Their assistant

Same director — a Contributor still talks to the Sales Director — but a different
question set, scoped to their own work:

- What should I do first today?
- Which of my deals is most at risk?
- Am I going to hit my target?
- What is outstanding on *[a named account of theirs]*?

Asked for a department total, it refuses and names the reason rather than
returning an empty result. The refusal is the honest answer: *"Department-wide
totals sit with your manager. Your workspace is built from your own accounts, so
there is nothing here to hide from you — the totals were never part of it."*

### 10B. Onboarding for a Contributor

A Contributor answers **no department configuration questions at all**. Thresholds,
definitions and approval routes are their manager's to set, and a Contributor
answering them would let a junior redefine the numbers their own performance is
measured against.

---

## 11. Where this narrows doc 05

Doc 05 remains the target scope. This cut is narrower, and the gaps are deliberate
rather than forgotten:

| Doc 05 offering | Status in this cut |
|---|---|
| Marketing: Growth Plan, Content Studio, Content Calendar, ad-creative generation, social publishing | **Not present.** All are generation features; none blocked by data |
| Marketing: SEO Intelligence keyword table | **Not present** — needs DataForSEO, which is metered and post-verification |
| Marketing: Competitor War Room | **Not present** — doc 05 dates it Phase 2 |
| Sales: Deals-lite manual entry | **Not present.** The cut assumes a connected CRM |
| Finance: budget vs actual | **Locked**, with upload as the named unlock |
| All: period selector (7/30/90/custom) | **Not present.** Windows are fixed per tile and stated in the working |
| All: global data-completeness meter | **Not present.** Per-tile locked states carry the same information less prominently |
| All: action queue with accept/dismiss | **Partial** — Executive has a decision queue; department directors do not |

**Two additions this cut makes that doc 05 does not specify:**

1. **The per-department question bank and its branching** (§2A–§8A). Doc 04 argued
   the principle; the actual questions and options are new here.
2. **The *"Not asked — fetched instead"* disclosure** (§2B–§8B). Showing the
   customer what NEXUS refuses to ask them is a product surface, not just an
   internal rule.

---

## 12. Open items

1. ~~**Where the question bank lives.**~~ **Resolved.** `question_bank.py` is the
   server-side bank this item asked for — 29 questions, `consumed_by` capability
   tracing, documented in ADR 0020. It is what the dashboard's per-department
   "unanswered questions" tile reads.

   What remains open, and is a different question: the chat interview's own
   candidate-question filter (`fields.py:askable_fields(department)`) narrows on
   the user's **self-reported** `stated_department`, not the authorising
   `membership.departments`/`role` — deliberately, since it only steers which
   questions are *offered*, never what data is *readable*. That leaves two
   question surfaces — the interview's `fact.*` answers and this bank's
   dashboard tile — with no real bridge beyond the informal
   `FieldSpec.question_key` name match. Someone can fully answer the interview
   and still see "outstanding" on their dashboard. Tracked for `doc/adr` as a
   separate decision rather than folded back into this item.
2. **Answers must be written as cited facts, not form state.** An answer to 3.2
   ("flag after N days") has to be retrievable *with its provenance* when a stale-deal
   alert cites it, otherwise the threshold becomes an unexplained constant.
3. **Conflict handling is unspecified.** If 5.1 says a 3-day lead time and the
   operations data shows a 6-day median, that is a finding, not an error — but
   nothing currently decides which one a tile shows.
4. **`select` options need an escape hatch.** Every list here is closed. At least
   4.4 (who approves) and 3.3 (lead assignment) have real-world answers not in the
   list; an "other, describe" branch is needed before pilot.
5. **The Arabic question (2.5) implies a capability that does not exist.** Asking
   whether Arabic content is in scope commits NEXUS to doing something with the
   answer. Either build the Arabic-gap analysis or remove the question.
6. **Doc 05's period selector was dropped without a decision being recorded.**
   Fixed windows are defensible — they make the working unambiguous — but the choice
   belongs in an ADR rather than in an omission.

---

## 13. Provenance

Extracted from `prototype/nexus-os-prototype.html` on 18 August 2026 — the
`DEPT_QUESTIONS`, `PURPOSES`, `ROLE_REACH`, `PEOPLE` and `ASK` structures and the
`SECTIONS` render functions.

**The sample values in the "Options / sample" columns are illustrative**, taken from
the prototype's fictional demo workspace (Nakhla Trading LLC). The questions, the
option lists and the dashboard contents are the specification; the sample answers
are not.
