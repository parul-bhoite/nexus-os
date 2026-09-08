# NEXUS OS — client demo prototype

**`nexus-os-prototype.html`** — one file, the whole journey. No build step, no
server, no network. Double-click to open; send the file to share it.

It lives in `prototype/`, deliberately outside `apps/web/`, and must stay there.

---

## 1. The journey it covers

```
Landing page  →  preview audit  →  sign up  →  the agent takes over
              →  reads the site, briefs you, interviews you, builds a persona
              →  choose an account  →  that person's own workspace  →  admin
```

Every workspace also carries a **scoped assistant**, docked bottom-right.

Deep links via the hash: `#landing`, `#signup`, `#onboarding`, `#signin`, or a
person's id — `#layla`, `#omar`, `#huda`, `#yousuf`, `#mariam`, `#fatma`,
`#salim`, `#nadia`.

---

## 2. The idea it exists to explain

**The dashboard is the person.** You sign in as somebody and their department is
the entire application — their navigation, their layout, their vocabulary. A
Sales manager has no Finance entry greyed out in the sidebar, because Finance was
never part of their product. Navigation is assembled per user, not filtered per
user.

Two consequences worth pointing at:

- **Each department workspace is structurally different**, not one grid with the
  labels swapped. Sales gets a pipeline board. Finance gets ageing buckets and an
  approvals queue. Operations gets a dispatch lane board. They share the metric
  tile and almost nothing else.
- **A Contributor gets a genuinely smaller product** — "my day, my deals, my
  accounts, my targets" — rather than a manager's page with holes cut in it. That
  is what `contributor_restricted` in `scopes.py` actually means, and it reads as
  a deliberate design rather than a punishment.

---

## 3. Onboarding is a conversation, and the agent goes first

Five phases, none numbered on screen: **read → brief → you → persona → ready**.

The old flow was seven steps and it asked the person to supply. This one asks them
to *adjudicate*. The agent reads `nakhla-trading.om` first, states what it found,
and every screen after that is the user correcting it. That inversion is the whole
design, and it is the honest shape too, because the product's claim is that it
reads before it asks.

**There is no "verify your email" step, and its absence is the spec, not a
shortcut.** D19 (`doc/09` §4.1) made verification non-blocking: it gates exactly
two acts — connecting a tool that holds company data, and inviting a member. So it
appears at those two moments, inline in the conversation rather than as a modal,
because a modal *is* a block and would contradict the decision it implements. The
line to read out is the one on screen: *"Nothing else is waiting on this."*

**Domain ownership is still taken from the sign-up address**, not a DNS record.
The manual path (`/domains`, `/domains/{id}/check`) still exists in the API and is
still needed for a free-mail or agency sign-up; it has no UI here.

### What makes it not a form

- **The opening question is the router.** *"If the next twelve months went badly,
  what would have gone wrong?"* Negative framing gets specifics where "what are
  your goals" gets platitudes — and the answer selects the branch, so the
  department set is derived from a sentence instead of ticked in a grid. The grid
  was a form however it was phrased, and it asked a founder to translate her own
  business into our taxonomy.
- **Follow-ups quote her literal words**, escaped, never paraphrased.
- **The scan names artefacts and one step visibly fails.** The Google Business
  Profile line returns nothing. A scan where everything succeeds reads as theatre;
  the one clean failure is what makes the other seven believable. The log stays in
  the transcript as the receipt, and it ends by naming its own ignorance — which
  reframes the interview as the agent's shortfall rather than the user's homework.
- **The three practical asks are folded in**, each raised at the moment the
  agent's own answer is blocked by it. Skipping never says "less value"; it names
  the artefacts and counts them, and leaves a visible `waiting on you` scar in the
  panel.

### The two catalogues, and why they are separate

ADR 0019 is the governing decision: the model chooses *how* to ask — phrasing,
order, follow-ups, and what to skip — and **never introduces a question that is
not in the catalogue**, because a generated question has no scope tag and its
answer has nowhere honest to go.

So `DEPT_QUESTIONS` says what must be known and `OB_GRAPH` says only how it is
asked. Every `ask` entry now carries a fourth element, a stable key such as
`'sales.stale_days'`, and a graph node references that key rather than an array
index. **`obCoverage()` in the console reports it:**

- `unbacked` — nodes asking something the catalogue does not contain. **Must be
  empty.** It is currently `[]`, and it is the only check this file can make
  against ADR 0019.
- `notDemoed` — bank questions no branch reaches. Currently **21 of 35**, and that
  is expected: the graph walks three questions per branch plus two shared, and
  marketing, People and Strategy have no branch. In the real product that list is
  the coverage gap, and P7 owes it a test.

Two rules still shape the bank itself:

- **Only ask what cannot be fetched.** The *"here is what I am not going to ask
  you"* beat now lands mid-conversation, straight after the first effortful
  answer, where it reads as reciprocation. At the end of a block it read as an
  apology. The chips are `DEPT_QUESTIONS[dept].fetched`, and hovering one lights
  the locked panel row it would fill.
- **Ask what only this person knows.** Thresholds, definitions and intent are in
  no API.

### The live panel

Two cards, both editable, because a fact the person cannot correct is a fact they
cannot trust. Company Brain is keyed to the real `company_brain` columns
(migration 0019); the persona card holds five rows and matches the real `persona`
columns (migration 0002).

Statuses are `read` / `inferred` / `from you` / `needs you`, which map onto the
fact layer's `source_kind`, and that order is its precedence — rendered as a mono
line at the card foot. An inferred row is dashed-underlined so it is not accepted
by default. A pending row is locked with the step that unlocks it, never blank and
never a zero.

**Progress is the fact tally growing and locked rows converting. There is no
percentage**, because its denominator would be a guess at how much there is to
know about a company — the invented number the product exists to refuse.

### Persona is not authorisation

`persona_chat.py` carries `never_asked = ("seniority", "role", "departments")`,
because `doc/06` §2.6 says conflating presentation preference with authorisation
is how access-control bugs get written. The UI expresses the same absence:

- Role sits **outside both cards**, in an account strip, with **no edit control**.
  The missing pencil where every other row has one is the argument.
- The agent says the boundary out loud once, at the moment breaking it would be
  tempting: *"If you told me you were the CFO, I would write down that finance
  matters to you. I would not give you the ledger."*
- Responsibilities are recorded as **interests** — `Wants first: deals at risk,
  then margin` — not as departments.

A greyed, lock-iconed `Role` row inside the persona card was rejected: a disabled
field still teaches that role is a persona field, more emphatically.

### No model is a supported state

The `MODEL ON` chip in the header toggles it, mid-conversation, keeping every
answer. Only the wording changes — branching is a lookup, not a model — and the
no-model renderer asks the catalogue's questions verbatim. That is ADR 0011 and
"two renderers, one catalogue" demonstrated rather than asserted; if a flip ever
loses an answer, the catalogues have diverged.

---

## 4. Every workspace has a scoped assistant

Docked bottom-right, closed by default, and it is the department's director
rather than a generic bot — Yousuf talks to the Sales Director, Fatma to the
Finance Director. Three behaviours matter more than the answers:

1. **Every answer cites its source and shows its working**, the same discipline
   as the tiles. An assistant that produces a confident unsourced number is worse
   than none, because it launders a guess into an answer.
2. **It refuses out of scope, and says why.** This is the thing to demo. Verified
   behaviour:

   | Person asks | Result |
   |---|---|
   | Yousuf → "what is the total pipeline" | Answered, sourced to CRM |
   | Mariam → the same question | **Refused** — "Department-wide totals sit with Yousuf" |
   | Huda → "how much cash do we have" | **Refused** — "Finance sits outside Marketing" |
   | Nadia → "what is in the pipeline" | **Refused** |
   | Layla (Owner) → "how much cash" | Answered |
   | Layla (Owner) → "what are the salaries" | **Refused** — L4 is not reachable by role, including hers |

3. **It reads by default.** The footer states that anything with an outside
   effect is offered as a confirmation first.

The thread is cleared whenever the account changes — carrying one person's
conversation into another's workspace would leak exactly what the scoping
prevents.

There is no model behind it. Answers are canned and matched on keywords, and when
nothing matches it says it has no grounded answer rather than improvising. That
happens to be the correct product behaviour too.

**The one thing this cannot demonstrate:** refusing in the client is not a
permission boundary. The real assistant must be scoped on the server, and the
subagent return path must be filtered against the *end user's* scope rather than
the parent agent's. Both are M12 work.

---

## 5. What this is not

Not the application. No API, no database, no authentication, no permission
enforcement. Nothing typed into it is saved or sent. Signing in as a persona is a
demo device; real scoping happens in Postgres row-level security and
`retrieval/`, none of which is involved here.

---

## 6. Every number in it is invented — and it no longer says so

Nakhla Trading LLC does not exist. Every figure in this file — every score, every
currency amount, every percentage, every person — was written by hand to look
plausible. Nothing was measured, computed, fetched or sourced.

**The visible markers have been removed.** The banner across the top and the
`ILLUSTRATIVE` chip on all 48 tiles are gone, at the owner's request, so the
screens read as the finished product.

This is a deliberate departure from the content rule in `CLAUDE.md`:

> The landing page and every mock is held to it too: no invented customers,
> logos, testimonials or results. Product mocks carry a visible `Illustrative`
> tag.

What replaced forty markers is one: a quiet **`SAMPLE DATA`** chip in the
application top bar, and the same chip in the landing-page footer. Both explain
themselves on hover. They are findable rather than loud.

**The consequence, stated plainly.** A screenshot of any screen in this file is
now indistinguishable from a real result. So:

- do not put figures from this file into a proposal, a deck or a pitch
- do not send screenshots without saying what they are
- do not let this file drift into `apps/web`

The full record lives in the comment at the top of the HTML, where a client will
never see it but the next developer will.

If you want the last chip gone too, say so and it is a one-line change — the
`illus()` helper was left in place as a no-op rather than deleted, so restoring
the original markers everywhere is also one line.

---

## 7. The eight people

| Person | Role | Their application | Never sees |
|---|---|---|---|
| Layla Al-Amri | Owner | Chief of Staff: morning brief, business health, all departments, decisions, Company Brain, admin | L4 items she is not named on |
| Omar Al-Balushi | Executive | Strategy: opportunities, competitors, market signals, strategic bets, plus cross-department read | L4 items he is not named on |
| Huda Al-Kindi | Dept manager | Marketing: overview, channels, content, campaigns, enquiries | Every other department. Her Enquiries table has no deal-value column, on purpose |
| Yousuf Al-Harthy | Dept manager | Sales: overview, pipeline board, accounts, my team, forecast | Every other department |
| Mariam Al-Saidi | Contributor | Sales, her own slice: my day, my deals, my accounts, my targets | Any department total, and every other department |
| Fatma Al-Zadjali | Dept manager | Finance: overview, cash, receivables, payables, approvals | Every other department. Salary detail stays L4 even for her |
| Salim Al-Rawahi | Dept manager | Operations: overview, dispatch board, stock, suppliers | Every other department. No revenue, no margins |
| Nadia Al-Busaidi | Dept manager | People: overview, hiring, people, leave | Individual salaries — she manages People and still cannot open one |

---

## 8. Suggested walkthrough

| # | Do this | The point to make |
|---|---|---|
| 1 | Landing → **Analyse my business** | A reduced audit arrives before any account exists. The score reads **69 across 3 of 10 categories** — never a whole-business number built from part of the evidence. |
| 2 | The seven locked tiles beneath it | Missing data is shown as *locked with the step that unlocks it*, never as a zero. A zero would read as a real, bad result. |
| 3 | **Claim this audit** → sign up → **the agent takes over** | Nothing to fill in on the first frame. It reads the site and narrates what it finds, including the one lookup that fails. It ends by naming what it could not get — which is why the interview exists. |
| 3b | The **brief**, then *"If the next twelve months went badly…"* | Correct a line and watch the agent notice in the conversation. Then answer the opening question: it picks the branch, so the departments come from a sentence rather than a grid of tick boxes. |
| 3c | Two answers in, the **"what I am not going to ask you"** beat | Hover a chip and the locked row it would fill lights up in the panel. Then the connector ask lands — connecting now reads as avoiding work, not doing it. |
| 3d | **Skip the connector** | It names what stays locked and counts it, and the panel row changes to `waiting on you`. Skipping leaves a visible scar rather than silently degrading. |
| 3e | Toggle **MODEL ON → NO MODEL CONFIGURED** mid-conversation | Every answer survives; the questions become the catalogue's own wording. ADR 0011, demonstrated. |
| 4 | The **invite** ask | One role, not six — six rows at that moment is a form, one row is a decision. Expand it and point out L4 is absent: no role reaches it, not even the Owner's. |
| 4b | The **persona card**, and the account strip above it | Five rows, and no Role row. Role sits outside with no edit control. This is the subtle one: persona changes what you see first, never what you may see. |
| 4c | The **finale** | Same question asked of a generic assistant and of hers. The third row is the one that lands — the generic column produces a plausible statistic, and hers refuses to. |
| 5 | Finish → lands in **Layla's** Chief of Staff | The morning brief says what changed, what it means, what to do — each with its source named. This is the product; the tiles below are supporting evidence. |
| 6 | Any tile → **"+ why this number"** | Opens the method, the inputs and the arithmetic. This is what "every number is auditable" means in practice. |
| 7 | **Switch person** (sidebar, bottom left) → **Yousuf** → Pipeline | A sales tool. Clay edge on anything silent longer than *their own* median cycle — not a generic 30-day rule. |
| 8 | Switch person → **Mariam** | The strongest moment. Same department, completely different application: a day list, her five accounts, her own target. No lock icons, no gaps — plus a card explaining *why* there is no pipeline total. |
| 9 | Switch to **Salim** → Dispatch board | Nothing like either sales screen. Four lanes, two late orders named. NEXUS will not report "88% on time" unless it can also say which 12% were not. |
| 10 | Switch to **Nadia** → People | She manages People and the compensation column is still L4. A job title does not name you on an item. |
| 10b | As **Mariam**, open the assistant and ask *"what is the total pipeline"* | It refuses and names the reason. Then ask *"which of my deals is most at risk"* and it answers with a source. Same agent, scoped to the person. |
| 10c | As **Layla**, ask the assistant *"what are the salaries"* | The Owner is refused too. L4 is reached by being named on an item, never by role. |
| 11 | Back to **Layla** → Admin portal → Audit log | Refusals are logged as well as successes, and the log is Owner-only — a log everyone can read is a second copy of the data it audits. |

---

## 9. What it gets right about the real model

Faithful to what is actually built, and the reason this is a teaching tool rather
than a pretty picture:

- **Scores carry their denominator.** `across 3 of 10`, `across 5 of 6`.
- **Locked ≠ zero.** Every unavailable category names its unlock.
- **Composite only over full coverage**, and the copy says so.
- **Contributor is not Manager.** No department-wide aggregate appears anywhere
  in Mariam's application — correction #2 in `scopes.py`.
- **L4 by naming, not by role.** No persona reaches an L4 item, including the
  Owner and including the People manager on salaries.
- **Cross-department separation**, verified by walking all 38 sections across all
  eight personas: no department persona's screens contain another department's
  headline figures.
- **Honest states.** No blank panels, and no zeros standing in for "not
  connected" or "you may not see this".
- **Stale is stale.** A connector that has not synced is labelled, not silently
  reused.

### Verified in-browser

Landing, preview audit, sign-up, all five onboarding phases across all four
branches, the persona picker, and
38 sections across 8 personas. Plus both exit paths, and a stale `#app` deep link
with nobody signed in, which falls back to the picker rather than dead-ending.
Console clean throughout.

---

## 10. Milestone debt this deliberately runs ahead of

`CLAUDE.md` says one milestone at a time, stop and wait for validation. This
prototype spans M4 through M13 and stops at none of them. That is a conscious
trade for a client conversation, not a change of plan. **Nothing here counts as
progress against doc 07**, and none of it should be lifted into `apps/web`
without the work below.

| Screen | Milestone | Still owed before it can ship for real |
|---|---|---|
| Sign up, sign in | M1/M3 | Session cookies, CSRF on every mutation, email verification wired to the real mailer. Backend exists; no UI. |
| Onboarding | M3/M4 | Email-domain matching as the ownership signal, the ephemeral→verified workspace transition, and claiming the preview into the workspace. Backend exists; no UI. |
| Manual domain claim | M3 | Still required for a free-mail or agency sign-up, where the email domain will not match. Backend exists; the prototype deliberately has no UI for it. |
| Document upload | M5 | Classification-default-deny passes server-side; the review queue UI does not exist. |
| All eight workspaces | M7–M9 | **No data source exists.** GA4, CRM, accounting and HRIS connectors are unbuilt, so every figure would render as a locked state today. |
| "Why this number" trails | M6 | Real calculators with real inputs. `calculators/` holds the Preview audit only. |
| Per-person navigation | M1 | The nav must be derived server-side from the session's scope. Assembling it in the client is a convenience, not a boundary. |
| Onboarding question branching | M4 | `OB_GRAPH` must live server-side and be keyed to the workspace's departments; answers must be written as cited L1/L2/L3 facts, not client state. The scope tag shown beside each question is real in the catalogue and decorative here. |
| Two renderers, one catalogue | P7 | `obCoverage().unbacked` is empty, which is the containment half of ADR 0019. The coverage half — every bank question reachable by both renderers — is a real test P7 owes, and `notDemoed` is currently 21 of 35. |
| The Company Brain panel | P13 | Rows are keyed to `company_brain` (migration 0019) but nothing writes to it. `provenance` is NOT NULL there for the reason the panel dramatises: a brain that cannot say where a claim came from is the thing this product exists not to be. |
| The persona | P6/P7 | `persona` (migration 0002) has been empty since M1. The five rows here match its columns, and the role-is-not-persona rule is enforced by layout rather than by `never_asked`. ADR 0019 says both P6 and P7 briefs need rewriting for this; that rewrite has not happened. |
| The assistant | M12 | Server-side scoping, untrusted-content boundary, action gating with the exact payload shown, and subagent return-path filtering against the end user's scope. Refusing in the client proves nothing. |
| Admin portal | M13 | Impersonation with time-boxing and reason logging, access-controlled audit log, deletion fan-out across embeddings, cache, storage and artifacts. |

### Tests owed before any of this becomes real UI

Per doc 07 §5.3, for anything touching permissions or grounding the test comes
**before** the feature:

1. A rendered dashboard must never show a composite score without its
   denominator — assert on the DOM, not the payload.
2. A locked category must never render as `0` or as an empty tile.
3. A Contributor session must not *receive* department aggregates in the API
   response, not merely have them absent from the UI. A navigation tree built in
   the client is not a permission boundary.
4. The section list returned for a session must contain only sections that
   session's scope permits — the per-person navigation needs its own test.
5. A stale connector must render as stale rather than silently reusing its last
   good value.
6. The admin audit log must 403 for every role except Owner.
7. The assistant must not *receive* out-of-scope facts, let alone decline to show
   them. Assert on the retrieval payload for a Contributor session.
8. Onboarding must not ask a question whose answer a connected source already
   provides — otherwise a typed guess becomes a stored fact that outranks the
   measurement.

---

## 11. Known cosmetic gaps

- The four-column pipeline and dispatch boards drop to two columns below 1000px
  and are cramped on a phone. Fine for a laptop demo.
- Charts are hand-rolled inline SVG so the file needs no CDN. Deliberately
  simple; the real product should use a charting library.
- Web fonts load from Google Fonts. With no internet it falls back to Georgia and
  system sans — acceptable, not identical.
- **The assistant loses focus and draft text on every render.** `askSubmit()`
  rewrites the whole of `#screens`, so anything half-typed in the assistant's box
  is lost. The onboarding solves this — `S.ob.draft` mirrors the composer on every
  keystroke without re-rendering, and `obAfterRender()` restores focus and caret —
  but the fix was deliberately **not** applied to the assistant: `viewAsk()`
  renders inside all 38 workspace sections, and that is too wide a blast radius
  for a prototype edit. Worth doing when the assistant becomes real.
- The onboarding transcript scrolls the page, not itself, so the panel beside it
  can stay sticky. It follows the conversation only when the thread grows, which
  is what stops a timer yanking someone who scrolled up to re-read.
