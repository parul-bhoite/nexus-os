# NEXUS OS — Decisions Required Before / During Build

Per doc 07 §1: *"If the spec is ambiguous or two documents disagree, stop and ask. Do not invent a resolution and proceed."*

I have invented no resolutions. Conflicts that the precedence rule settles are listed in `ARCHITECTURE-HLD.md` §2 and need no answer from you — only the items below do.

**Only §1 and §2 block M0.** Everything in §3 blocks a later milestone and can be answered when we reach it.

---

## 1. Environment blockers — M0 cannot complete without these

These are not spec questions; they are missing prerequisites on this machine. M0's done-when is *"`docker compose up` gives a running web and API"*, which is currently impossible.

### ~~E1 — Docker is not installed~~ · RESOLVED (ADR 0001, then ADR 0006/0007)

Settled: Docker Engine in WSL2 serves pgvector; Docker Desktop is ruled out. Original text kept below.
`docker` is not on PATH and Docker Desktop is not present at the default location. Doc 07 §3 requires Postgres + pgvector + object storage via Compose, and M0's acceptance is a working `docker compose up`.

**Options:** (a) install Docker Desktop — matches the spec exactly; (b) run Postgres+pgvector natively on Windows and drop Compose — diverges from doc 07 §3 and M0's acceptance criterion.
**My recommendation:** (a).

### E2 — Python is 3.10.11; doc 07 §3 requires 3.12
Only `3.10-64` is registered. Several things I would otherwise use freely (PEP 695 generics, `TypeVar` defaults, the 3.12 `asyncio` improvements) are unavailable, and more importantly the spec names 3.12.

**Options:** (a) install Python 3.12 locally; (b) develop entirely inside the Docker image, which pins 3.12 regardless of the host — this makes E2 moot if E1 is resolved.
**My recommendation:** (b), with (a) as a convenience for editor tooling.

### E3 — `D:\Projects\NEXUS_OS` is not a git repository
Doc 07 §5.5 requires small commits with clear messages. There is no repo, so there is no commit history to make.

**Ask:** confirm I should `git init` at `D:\Projects\NEXUS_OS` and make the first commit contain `/doc` plus these three planning artifacts. Also confirm whether a remote exists that I should push to, or local-only for now.

---

## 2. Decision blocking M0

### D1 — Embedding model provider
No source document names one. This is needed in M0 because the `embedding` column's dimension is fixed in the first migration that creates it, and changing it later means a re-embed of every chunk.

| Option | Dimensions | Notes |
|---|---|---|
| **Voyage** (`voyage-3`) | 1024 | Anthropic's recommended pairing; strong retrieval quality; adds a second vendor |
| **OpenAI** (`text-embedding-3-large`) | 3072 (truncatable) | Reintroduces OpenAI, which doc 06 §12 flags as an open question (see D11) |
| **Local** (`bge-m3` / `e5`) | 1024 | No per-token cost, no data leaving infrastructure — relevant to the doc 01 §6 residency commitment; needs GPU or tolerable CPU latency |

**My recommendation:** Voyage `voyage-3` at 1024 dimensions. Best quality-per-cost for RAG, and it keeps the retrieval path on one vendor family. I will store the model id and dimension on every chunk row so a future migration is possible without guesswork.

---

## 3. Decisions blocking later milestones

### D2 — DataForSEO account *(blocks M7)*
Doc 05 §3.7 requires real keyword volumes and forbids estimating them; doc 06 §1.2 requires it be post-verification only. ~$50/month per doc 03. **Do you have credentials, or should keyword data render Locked until you do?**

### D3 — Google API credentials *(blocks M2 partially, M10 fully)*
PageSpeed Insights (M2), plus GA4 and Search Console OAuth (M10) need a Google Cloud project with a client id/secret and an authorised redirect URI. PageSpeed works keyless at low volume but is rate-limited — acceptable for M2 dev, not for M10.

### D4 — Production email provider *(blocks M3)*
M3 needs verification email. Dev uses mailpit in Compose, so this only blocks a real deployment. Doc 03 names SendGrid/Postmark as Phase 2. **Which, and do you have an account?**

### ~~D5 — Contributor L3 subset~~ · RESOLVED (ADR 0005)

Ratified as proposed and shipped in M4. `decide_l3_access` implements it and `test_contributor_scope.py` proves it. Doc 06 §11.5 asks for a per-department definition with a design partner, so this is the default to revisit, not the final word. **Original text kept below for that revisit.**

Doc 06 §2.3 says a Contributor gets *"own department, restricted subset — excludes department-wide financial aggregates and other people's records."* That is a principle, not a specification, and M4's acceptance is *"a Contributor cannot reach L3 aggregates"* — which I cannot test without the per-department definition.

**My proposed default, for you to ratify or correct:** a Contributor sees (i) records where they are the owner or assignee, (ii) records they created, (iii) department reference data (stages, services, price list); and is denied (iv) any aggregate over the department, (v) any record owned by another user, (vi) any field marked `sensitivity: financial` on a record they do not own. Doc 06 §11.5 says define it per department with a design partner — so I would ship this default and revisit.

### D6 — A Department Manager sees six directors, not seven *(blocks M4)*
Doc 06 §2.4 restricts the Executive surface to Owner and Executive at MVP, which removes the Chief of Staff page, the Morning Brief and the composite score for everyone else. Doc 05 §1 promises "seven equal AI directors" with a consistent surface. Doc 06 records this as an unresolved contradiction and recommends the restriction anyway.

**Confirm:** ship the six-director experience for Department Managers, Contributors and Viewers? This is product-visible, so I do not want to assume it.

### ~~D7 — Which departments are actually in MVP?~~ · RESOLVED (ADR 0010)

**Your decision: all seven directors get a dashboard.** Recorded in ADR 0010, which also records what it costs.

The good news, which the original framing of this question got wrong: **six of the seven have real content on day one, with no integrations at all.** Doc 04 §3's truth table and doc 05's widget lists say so directly.

| Director | Works with website + documents only |
|---|---|
| **Marketing** | Growth Planner, Content Studio, SEO Intelligence, Brand audit, competitor discovery |
| **Sales** | Lead Intelligence (4.5, *"works with no CRM connected"*), Proposal Studio (4.7, same, needs an uploaded price list), outreach drafting |
| **HR / People** | Policy library and generator (7.3, pure generation), JD generator, onboarding checklists, team directory from the onboarding roster |
| **Strategy** | Market position (8.1) from competitor data, crawl and SEO share |
| **Operations** | Everything, once the customer creates their first project — it is the first-party layer |
| **Chief of Staff** | Company Brain status (2.8); Health Score as soon as one department is scoreable; **Baseline, not Morning Brief, in week 1** |
| **Finance** | **Nothing.** See below. |

**Finance is the single genuine exception, and it still needs an answer from you.** Every widget in doc 05 §5 requires the accounting API, which doc 07 §8 excludes from scope. Two partial paths exist:

- **5.2 Revenue trend** can use CRM closed-won as a *weaker proxy*, which doc 05 requires be labelled as such.
- **5.7 Pricing recommendations** needs a price list and margin data, so it partly works once documents are uploaded.

Three options, and I do not think this one should be defaulted:

1. **Ship Finance as structure plus named unlocks.** Honest, consistent with I10, and the page teaches the customer exactly which connection turns it on. But a director page that does nothing on day one is a weak first impression for the department owners care most about.
2. **Bring accounting into MVP scope.** Makes Finance real, and unlocks 5.3 margin, 5.4 runway and 5.9 the Simulator. It is a new integration, a new provider decision (Xero? QuickBooks? Zoho? Tally?), and it is the single point of failure doc 05 §10 already flags.
3. **Allow manual entry, visibly labelled self-reported.** Doc 04 §7 already sanctions exactly this — *"Manual entry: ruled out → allowed at MVP, visibly labelled as self-reported"* — and doc 04 §6 rule 4 requires self-reported figures never be silently mixed with API-sourced ones. This makes Finance usable on day one without a new integration.

**My recommendation: (3) now, (2) later.** Manual entry gets a working Finance page immediately under a rule the documents already established, and does not commit you to an accounting vendor before you know which one your design partners use. The label is doing real work here — a margin the owner typed is a different claim from a margin fetched from Xero, and the product's whole position rests on not blurring that.

**Still open, and now the only part of D7 left: which of the three above?**

---

### D8 — Capability count: 21 or 24? *(blocks M9)*
Doc 04 §6 specifies the completeness meter as *"6 of 21 capabilities"*; doc 05 §0 says *"8 of 24"*. Doc 06 §12 records this as needing reconciliation. The meter is in the global shell, so M9 needs the canonical number.

**My recommendation:** build a capability registry as data — each capability declaring its required sources — and derive the denominator from it. Then the number is computed rather than asserted, and it self-corrects as scope changes. I would still want you to ratify the registry contents at M9.

### ~~D9 — Preview data TTL~~ — **void, 3 September 2026 (Phase 2)**
This asked you to ratify a retention period for crawl data held about a domain whose owner has no account and never consented, and flagged that the deletion-request path doc 06 §10 requires did not exist.

**Neither question survives.** D18 removed the pre-signup audit; Phase 2 deleted `POST /preview`, and migration 0011 dropped `preview_session`. Nothing now crawls a website until a workspace has claimed the domain, so no data is held about a third party — there is no TTL to ratify and no deletion request to answer.

Worth stating plainly, because it is the rare case where a decision is retired by being made unnecessary rather than by being made: **the strongest answer to "how long do we keep a stranger's data and how do they ask us to delete it" turned out to be not collecting it.** `tests/test_no_unauthenticated_crawl.py` is what keeps that answer true — it walks the import graph and fails if any route without a session can reach the crawler.

Finding #14 in `AUDIT-FINDINGS.md` is narrowed to re-verification alone for the same reason.

### D10 — Which CRM connector? *(blocks M10)*
Doc 05 §9 names Zoho and HubSpot as a *working assumption on expected GCC SME prevalence*, explicitly flags that no source contains regional market-share data, and says confirm with design partners rather than building on the guess. Doc 07 M10 narrows it to **one** connector and doc 07 §8 puts a second out of scope.
**Which one?** This also determines whether `last_activity_at` is reliably populated, which decides whether stale-deal detection exists at all.

### D11 — Is any non-Claude model needed? *(blocks M12)*
Doc 03 §9 routes images and voice to GPT. Doc 07 §8 puts Voice out of scope; ad-creative generation is doc 05 Phase 2 and therefore also out. So MVP appears to need **no OpenAI dependency at all** — unless D1 selects OpenAI embeddings.
**My recommendation:** Claude-only for MVP. Confirm.

### D12 — Deals-lite: in or out? *(blocks M10/M11 scope)*
Doc 05 §4.12 proposes a minimal deal tracker inside the Ops layer so the Sales Director is not permanently empty for customers with no CRM — and doc 05 §0 flags the underlying premise (that many GCC SMEs run sales on WhatsApp and spreadsheets) as *an assumption, not a measured figure.* Doc 07 neither includes it in a milestone nor excludes it in §8.
**My reading:** out of MVP, since no milestone carries it. Confirm — if it is in, it belongs in M11 alongside the Ops entities.

### D13 — Anthropic API access *(blocks M12)*
The Agent SDK needs an API key and a decision on which model tier backs each execution mode. Also relevant to doc 06 §8.4's cheap-model routing, which is only permitted where that module's evals pass.

### ~~D14 — Login rate limiting~~ — **answered** (`doc/11` §5.2), built in Phase 4

**The answer was the recommendation below**: per-IP *and* per-email counters,
exponential backoff rather than a lock, an identical 401 in every case with the
delay applied silently. The question is kept for the reasoning, because the
third part of it is the one that shapes the code.

**Raised by ADR 0009.** `POST /auth/login` accepts unlimited attempts. `rate_limit.py` covers only the Preview path, so nothing bounds password guessing. argon2id and the dummy-hash timing equalisation defeat offline cracking and the timing oracle; **online guessing against a weak password is unmitigated.**

Now urgent because a sign-in form exists, where before this required deliberate API calls.

Three questions, and the third is why this is not a default I can pick:

1. **Key by IP, by email, or both?** Per-IP alone is defeated by a botnet; per-email alone is defeated by rotating targets.
2. **What is the response** — 429 with `Retry-After` (consistent with Preview), or a silent delay? A 429 keyed by email confirms the address exists, which would undo M1's account-enumeration work.
3. **Lock the account after N failures?** A per-account lock is a **denial-of-service vector against a named user**: anyone who knows an Owner's email can lock them out at will. The usual answer is exponential backoff rather than a lock, but "the Owner cannot get in during an incident" is a business call, not a technical one.

My recommendation if you want one: per-IP *and* per-email counters, exponential backoff instead of a lock, and an identical 401 in every case with the delay applied silently — so nothing observable distinguishes a rate-limited known address from an unknown one. That preserves the enumeration guarantee, which is the property most easily lost here.

### D15 — Department-branched onboarding for invited members *(new scope; would extend M4)*

**Raised by you**, and it is not in any source document — which is why it is here rather than being built.

Onboarding today is a **company setup flow, run once by the founder**. Doc 04 §5 redesigns it as six stages — audit, justified questions, connections, documents, team last — and there is no "select your department" step, because the person running it is configuring the whole company.

`Question.department` exists on the catalogue but means something different from what the name suggests: it records **which department owns the answer as an L3 fact**, so `average_deal_size` is L3 Sales and `monthly_marketing_budget` is L3 Finance. Doc 06 §2.5 is explicit — *"Tag them at capture"* — it is a scope classification, not a routing rule. Only 2 of the 14 questions carry one; the other 12 are company-wide.

**What you appear to want is a second flow**: when a Sales Manager accepts an invitation, ask them Sales-specific questions. That is reasonable and no document rules it out. It is also genuinely new work, and it raises three questions worth deciding before it is built:

1. **Does a member's answer bind the department, or only themselves?** If an invited Sales Manager states the average deal size, that becomes an L3 Sales fact the whole department reads. Two managers can disagree. The Brain's conflict precedence (M7 task 7.4) puts user-confirmed above crawl, but not one user above another.
2. **Who may answer department-scoped questions?** A Contributor is denied department aggregates by ADR 0005. Letting one *write* a department-wide fact through an onboarding form would route around that boundary.
3. **What happens when someone changes department?** Their answers stay tagged to the old one unless something re-classifies them, which is the same problem M5 task 5.10 solves for superseded documents.

**My recommendation:** build the founder flow first (task 4.10) and treat member onboarding as a follow-on. Restrict department-scoped questions to the Owner, Executive and that department's Manager, and have Contributors confirm rather than assert. But this is your product call, and answering (1) is what unblocks the design.

### D16 — Who may administer a workspace *(raised by task 4.10; a default is in place)*

Task 4.10 needed an answer to *"who may save an onboarding answer, and who may invite people?"* and **no source document names either**. Doc 06 §2.2 says the inviter sets the role; it never says who is allowed to be an inviter. Doc 04 §5 describes the founder running the flow, which is a description of the common case rather than a rule.

So the code takes the default-deny reading (I4) and **restricts both to Owner and Executive**, expressed once as `may_administer` in `app/domain/invitations.py` — the roles that already hold every department and the executive surface. It is one predicate to widen.

Two things are built alongside it so widening cannot quietly open a hole:

- **No inviter may grant a role above their own.** `outranks` compares `RoleGrant` on every axis rather than on the scope ceiling alone, because a Department Manager and a Contributor share a ceiling and differ only in `contributor_restricted`.
- **An L3 answer requires reaching that department's aggregate**, decided by `decide_l3_access`. Redundant today, since only Owner and Executive get past the first gate — and it is exactly D15's second open question, so it is written and tested now rather than remembered later.

**What is genuinely open:** should a Department Manager be able to invite a Contributor into their own department? It is a plausible product answer and it is what most teams expect. If yes, `may_administer` widens and the two checks above start doing real work. If it also implies a Manager may answer their own department's L3 questions, that is D15 (1) as well, and the two should be settled together.

**My recommendation:** leave it at Owner and Executive until a design partner asks for more. Delegated invitation is a feature; accidentally delegated *classification* is a boundary, and they widen through the same predicate.

### D17 — Where doc 08 sits in the precedence order *(blocking any further onboarding work)*

`doc/08-Department-Onboarding-Questions-and-Dashboard-Offering.md` appeared while task 4.10 was being built. It specifies an onboarding flow that **differs from the one 4.10 implements**, and CLAUDE.md's precedence rule (07 > 06 > 05 > 04 > 03/01) does not place it — so this is a ruling only you can make, not something to resolve by picking the newer file.

Three differences, in order of how much they cost to change:

1. **The company-wide question set.** Doc 08 §1 asks what the business sells, who the typical customer is, reporting currency, headcount, a single `purpose` choice, and a departments multi-select. The catalogue built from doc 06 §2.5 asks role, department, purpose and URL, then goals, challenges, ideal customer, deal size, budget, brand terms, currency and fiscal year. These overlap but are not the same list.
2. **Role and department as owner-answered questions.** Doc 08 §1.7 is explicit that role is *"not a question the owner answers about themselves — set when inviting each person."* Doc 06 §2.5 lists both in Pass 1. The invitation half already matches doc 08; the two Pass 1 questions do not, and they are the two the catalogue is careful to mark as stated facts rather than grants.
3. **Per-department question sets.** Doc 08 §1.6 and §2–8 specify 9 fields per department, up to 39 — which is **D15**, now with a specification behind it. D15's three questions still need answering before it is built, and doc 08 answers one of them: §0 says an invited member answers only their own department's set.

Doc 08 describes itself as extracted from `prototype/nexus-os-prototype.html` and says *"doc 05 remains the target scope and this is the current cut of it"* — which reads as a record of the prototype rather than a specification that outranks doc 06. If that reading is right, nothing changes and doc 08 becomes input to D15. If it is wrong and doc 08 is the intended spec, the catalogue in `app/domain/onboarding.py` is rewritten and the wizard follows it without structural change, because the wizard renders from the catalogue rather than from hand-written forms.

**What I need:** one sentence placing doc 08 in the order. I have not changed anything on the strength of it.

---

## 4. Assumptions I have made — object if any is wrong

| # | Assumption | Basis |
|---|---|---|
| A1 | Repo root is `D:\Projects\NEXUS_OS`; the landing page moves `nexus_os_application/web` → `apps/web` | `/doc` is at that root and doc 07 §4 shows `/apps/web` as a sibling |
| A2 | MFA / SSO / SCIM are out of MVP | Doc 06 §10 flags them absent from every document; doc 07 neither includes nor excludes them |
| A3 | Trial is a flag set at workspace creation; no paywall | Doc 07 §8 — "billing beyond a trial flag" is out of scope |
| A4 | k-anonymity threshold = 3, configurable | Doc 06 §4.14 — "3 is conventional; confirm against real team sizes" |
| A5 | CRM connector is read-only at MVP | Doc 05 §4.6 — write scope is "much heavier, ask separately, later" |
| A6 | Opportunity Radar / tender feed is out of MVP | Doc 05 §2.5 — no provider identified in any source document; no milestone covers it |
| A7 | No OCR — scanned PDFs fail visibly | Doc 07 M5 requires the failure be visible, not silent; no OCR dependency is named anywhere |

---

## 5. What I need from you to start M0

*Historical — all four were answered and M0 shipped. Kept because the ADRs that
resolved them cite this list.*

1. ~~**E1 / E2**~~ — resolved as ADR 0001, then ADR 0006/0007
2. ~~**E3**~~ — `git init` done, and the remote now exists
   (`github.com/parul-bhoite/nexus-os`), so Phase 0's one external prerequisite
   is met
3. ~~**D1**~~ — resolved as ADR 0003: local `multilingual-e5-large`, 1024d
4. ~~Approval of `ARCHITECTURE.md` and `TASKS.md`~~ — both retired to `doc/archive/`
   and replaced by `ARCHITECTURE-HLD.md`, `ARCHITECTURE-LLD.md` and
   `VISION-AND-PLAN.md`

---

## 5b. Raised by the new application flow (doc 09), 25 August 2026

Parul's flow sketch of 25 August answers two long-open decisions and raises five
new ones. Full analysis in `doc/09-NEW-APPLICATION-FLOW.md`.

### Answered by the sketch, pending ratification

- **D15** — member onboarding is **per-department**, for invited members. The
  sketch places invitations after the dashboard, which also settles what happens
  on a department change: the flow is re-run per member rather than once per company.
- **D17** — **doc 08 outranks doc 06 §2.5** on the question set and the department
  model. The sketch matches doc 08 §0 almost word for word: the owner selects which
  departments the company runs, and an invited member answers only their own set.

### D18 — Does the pre-signup Preview audit survive? *(blocks the landing page and doc 09 stage 0)*

The new flow starts at sign-up, so the unauthenticated audit has no place in it.
That audit is 90% of a finished feature — the SSRF guard with 89 cases, the pinned
crawler, the extractor, three scoring calculators, the Postgres rate limiter, the
preview cache — and it is the only flow that works end to end today.

**The engine survives either way**, because "do a full Research" needs all of it.
What is in question is only the unauthenticated entry point.

**My recommendation was a signup lead-in** — keep the URL field, start the crawl
on entry, show the audit after registration.

**You decided otherwise** (`doc/11` Q1): no URL capture at all. The landing page
is marketing with one action, sign up, and the crawl starts at stage 2 once a
company's website is given by someone with an account.

**Delivered in Phase 2, 3 September 2026.** The route, the two components, the
proxy, the `X-Forwarded-For` trust chain and the `preview_session` table are
gone; the guard, crawler, extractor and calculators moved behind authentication
into `app/research/`. **D9 went void with it** — see above. One consequence is
worth carrying forward: `doc/11` §3.1 notes the audit was the product's
first-value moment at minute seven, and with it removed the review gate at
minute twenty is the only one left.

### D19 — Where exactly does domain verification gate? *(blocks doc 09 stage 2)*

You confirmed that a verified domain still gates workspace creation. The sketch
creates the company immediately after register. `auth/domains.py:229` makes these
mutually exclusive, and DNS TXT propagation takes minutes to hours — so as drawn,
the user stops mid-flow and returns tomorrow.

**My recommendation: move the gate, keep the guarantee.** Verification stops gating
*whether a workspace exists* and starts gating *what it may do* — the exclusive
domain claim, inviting members, and connecting any tool holding company data. That
preserves what the invariant is for (nobody occupies a domain they do not own,
nobody invites strangers into a company they do not control) and lands the gate
exactly where the sketch already puts invitations. `workspace.domain_verified_at`
is already nullable and the partial unique index already implements
first-verified-wins, so the change is small.

**If you want the strict gate instead:** keep verification before company creation
but default to same-domain email, which verifies in seconds. That needs email
delivery wired, and accepts a *weak* proof that flags `owner_claim_review`.

### D20 — What is the research budget? *(blocks doc 09 stage 7)*

Max pages crawled, max duration, and what happens when one source fails while
others succeed. This decides whether stage 7 is a brief settling step or a wall,
and it is a recurring cost line.

**My recommendation:** 20 pages, a 5-minute soft cap, every source's failure
surfaced individually, and the Brain built from whatever succeeded. The stage must
be resumable — a founder will close the tab.

### D21 — Does department selection restrict which directors exist, or only order them? *(blocks doc 09 stage 9)*

If a company does not select Finance, can anyone ever open it?

**My recommendation: restrict, with an explicit "add a department" action.** Seven
half-empty directors is precisely what the new flow exists to avoid, and ADR 0010's
"all seven get a dashboard" was about *capability*, not about forcing all seven onto
every company.

### D22 — Can a member's answer bind their whole department, or only themselves? *(blocks doc 09 stage 10)*

This is D15's first question, now live because member onboarding is in the flow.
Two Sales managers can disagree about the average deal size, and the Brain's
conflict precedence puts user-confirmed above crawl but says nothing about one user
above another.

**My recommendation:** a Department Manager binds the department; a Contributor
confirms rather than asserts. This is what `decide_l3_access` already implements,
so it is written and tested rather than remembered later.

---

### D24 — How does somebody reach a human? *(blocks two of the three pricing CTAs)*

The Growth and Enterprise tiers are priced **"Let's talk"** and their buttons read
*"Book a walkthrough"* and *"Talk to us"*. The pricing disclaimer makes the same
offer in prose: *"talk to us and it will be honest about where it stands."*

**There is no mechanism.** No booking system, no `/contact` route, no support
address anywhere in the repository. The buttons scrolled to the final section,
whose own button goes to `/register` — so the two tiers that require a
conversation led to a self-serve signup form two clicks later.

The nav and the Starter tier are fixed (they are genuinely self-serve, and now
link straight to `/register`). These two are not fixable without a fact about the
business, and the content rule forbids inventing one — an invented support
address is a worse failure than a scroll, because mail sent to it disappears.

**What I need:** one of —

1. **An address.** Anything real: `hello@…`, a personal inbox for now. The
   buttons become `mailto:` links and this closes.
2. **A form.** A `/contact` route that writes somewhere you will read. Half a
   day, and it needs a destination anyway, so it reduces to (1).
3. **A booking link.** Calendly or equivalent — an external URL, no build.
4. **Drop the promise.** Relabel both to the self-serve trial and delete the
   "talk to us" line from the disclaimer. Honest, and loses the enterprise
   conversation the tiers exist to start.

Until then both stay on `#cta`, commented in `lib/content.ts` so the next reader
does not "fix" it by inventing an address.

## 5e. Raised by Phase 5, 3 September 2026

### ~~D25 — Should onboarding be an AI questionnaire instead of a form?~~ — **answered: wrap, not replace**

**Wrap.** The `doc/08` catalogue stays the source of truth for what must be
known; the model decides how to ask it, and with no API key the plain form is the
floor. ADR 0011 is therefore unamended — a deployment without a model still
onboards customers — and each answer keeps the scope tag that decides where it is
stored. A **persona** is derived from the answers, citing the answer behind each
field. Recorded as **ADR 0019**; lands in P6/P7, not P5.

---

## 5d. Raised by Phase 4, 3 September 2026

### ~~D24 — RLS on `domain_claim`~~ — **answered: option B**, 3 September 2026

**A separate `nexus_jobs` role**, `NOSUPERUSER NOBYPASSRLS` like `nexus_app`,
with a role-targeted policy on `domain_claim` and nothing else. Not a GUC-keyed
bypass: a GUC is application state, so anything that can set one gets full read,
and the boundary moves out of the database into application code — which is
where it stops being structural. Recorded as **ADR 0018**.

The question and its costings are kept below, because the two rejected options
are the ones a later reader will be tempted by.

`doc/12` §Phase 4 says: *"RLS on `domain_claim`: the predicate is `user_id`-scoped,
since claims exist before a workspace does."* That is the right instinct — a claim
has no workspace yet, so the usual workspace predicate has nothing to key on — but
written literally it **breaks two paths that exist today**, and both fail silently,
which is the shape this repository has already been bitten by twice.

**1. The expiry sweep updates nobody's rows.** `jobs/expiry.py:expire_stale_claims`
runs `UPDATE domain_claim SET state='expired' WHERE state='pending' AND expires_at
<= now()` on an unscoped session, across every user. With `FORCE ROW LEVEL
SECURITY` and a `user_id = current_setting('nexus.user_id')` predicate, and no GUC
set, that statement matches **zero rows** — and reports success. Abandoned claims
would accumulate for ever while the sweep logged a clean run. (This is the same
failure mode as the `next_run_time=None` bug in `scheduler.py`: a job that runs,
does nothing, and says nothing.)

**2. The dispute path writes to somebody else's claim.** `auth/domains.py:255` —
when a second claimant loses a race, `create_workspace_for_claim` marks *their*
claim `disputed`. The actor is the winner; the row belongs to the loser. A
`user_id` predicate refuses that write, so the loser gets no dispute record and
`DomainDisputedError` is raised over a row that was never marked — which is worse
than no policy, because the support conversation the record exists for now has no
artefact.

**Three ways out, and the choice is yours because each trades something different:**

| Option | What it costs |
|---|---|
| **A. A maintenance GUC** — a second permissive policy keyed on `nexus.maintenance`, set only by the sweep | An explicit, auditable bypass. But anything that can set a GUC gets full read of every claim, and the whole point of RLS here is that no application bug can do that |
| **B. Move the sweep and the dispute write out of the app role** — a migration-time or job-role identity with its own grants | Correct, and the most work: it needs a second database role, which `db/bootstrap.sql` and every environment must then provision |
| **C. Scope by `user_id` OR `disputes_workspace_id`, and make the sweep set-based per user** | No new role and no bypass, but the sweep becomes N statements instead of one, and the policy starts encoding business rules |

**My recommendation: B**, with A as the interim if a second role is more than you
want to provision today. The reason is the one ADR 0008 already establishes for
`neondb_owner`: the isolation guarantee is only worth what the *connecting role*
cannot do, and a GUC-keyed bypass moves that boundary from the database into
application code, which is exactly where it stops being structural.

**Until this is answered, `domain_claim` has no RLS** — any authenticated user who
can guess a claim id can read another person's claim through `_load_claim`, which
filters by `user_id` in SQL and would therefore *not* leak today. So the exposure
is bounded by that filter rather than by the database, which is the thing P4 exists
to change.

---

## 5c. Raised by Phase 0, 3 September 2026

### ~~D23 — The developer database is five migrations ahead of the repository~~ · RESOLVED 3 September 2026

**Parul: override the Neon database to match the repository.** Done, and verified
— see *What was done* at the end of this entry. Original text kept below, because
the schema record it produced is cited from `doc/archive/`.

`tests/test_ci_contract.py::test_the_schema_is_migrated_to_head`, written in Phase 0,
failed on its first run against the Neon instance in `.env`:

```
the database is at ['0014'] but the migrations on disk head at ['0009']
```

The Neon database also holds `company_brain`, `question` and `question_choice`,
which no migration in this repository creates, and its `ck_document_status`
already permits `'superseded'` — the value Phase 1's migration 0010 is scheduled
to add, and which `BUILD-STATUS.md` §5.2 records as *missing and causing a
raise*. So five migrations were applied to it from a working tree that is in no
commit, no branch, no stash and no other worktree. I checked all four.

**Why this is not cosmetic.** A local run against that database proves something
other than what the repository contains, in both directions: a defect the repo
still has can pass, and a fix the repo has made can fail. Two of the three
🔴 items in `BUILD-STATUS.md` §5 concern exactly the constraints that differ.

**Options:**

- **(a) Reset it to the repository's head.** `alembic downgrade base` then
  `upgrade head`, or drop and recreate the database. Destroys the three extra
  tables — all three are currently **empty**, and I have not checked row counts
  in the other sixteen. Cheapest, and loses the only surviving trace of those
  five migrations.
- **(b) Reconstruct `0010`–`0014` from the live schema and commit them.** Keeps
  the work, at the cost of authoring five migrations from a diff rather than from
  intent, and they would arrive with no tests and no ADRs. They also collide with
  Phase 1's migration 0010 by number.
- **(c) Leave it, and treat Neon as a scratch environment.** Nothing local is
  trustworthy, which is the state Phase 0 exists to end.

**My recommendation: (a).** The three extra tables are empty, Phase 1 and Phase
12/13 will build that schema deliberately and with tests, and `db-ci.ps1` now
gives a reproducible database in one command so nothing depends on Neon's
contents. **But I have not done it** — resetting a database I did not create is
not mine to decide, and `.env` is your configuration. Say the word and it is one
command.

**Also worth knowing before answering:** the extra schema may indicate a parallel
session working this repository whose commits were lost, in which case there may
be application code missing too, not only migrations.

### What was done

Option (a), on Parul's instruction. In this order, so that nothing was destroyed
before it was recorded:

1. **Recorded first.** `pg_dump` was unusable — the local client is 17.11 and
   Neon runs 18.4, and it refuses to dump from a newer server — so both schemas
   were introspected and diffed structurally: columns, constraints, indexes,
   policies, row-security flags. The result is
   `doc/archive/neon-schema-before-the-d23-reset.md`, kept because the work is
   not throwaway: `company_brain` is Phase 13's central table and
   `question` / `question_choice` are Phase 7's question catalogue, and whoever
   builds them should see a prior attempt rather than design it twice.
2. **Counted what would go.** 241 rows: `app_user` 68, `user_session` 93,
   `tenant` 48, `domain_claim` 17, `preview_session` 14, everything else zero.
   **No `workspace` row and no `membership` row**, so no company had ever been
   fully registered — all of it was walkthrough and smoke-run residue.
3. **Dropped every table** in `public` with `CASCADE`, as `nexus_app`, including
   `alembic_version`. `alembic downgrade base` was not an option: there is no
   script for `0014`, so alembic cannot walk back from a revision it has never
   seen.
4. **`alembic upgrade head`** — nine migrations, exit 0.
5. **Verified.** Columns, indexes, policies and row-security flags are now
   *identical* to a database built from `db/bootstrap.sql` and the repository's
   migrations; so are all 65 constraints once the `NOT NULL` rows that Postgres
   18 exposes in `pg_constraint` and 17 does not are set aside.
   `test_the_schema_is_migrated_to_head` passes against Neon, and the full suite
   runs green there.

**Consequences.** Migration numbers `0010`–`0014` are free again, so Phase 1's
migration is `0010` as `doc/12` assumes. The three findings this drift had been
masking are back to being real defects in both databases: **C1** (`review_state`
never differed between them and is still broken against the Python enum), **C2**
(`'superseded'` is missing again, as the repository always had it), and **M5**
(somebody had chosen "use the persona table" and added three columns; that is a
decision for Parul, not an inheritance).

**Still open, and not answerable from here:** whether application code was lost
along with those five migrations. Nothing in `app/` references `company_brain`,
`question` or `question_choice`, so if there was code it went with the tree.

---

## 6. What I need from you now — Phase 0

Per `VISION-AND-PLAN.md` §6, four decisions block current work and two more block
Phase 8 planning:

| # | Decision | Blocks |
|---|---|---|
| **D14** | Login rate-limiting shape — key, response, and whether to lock | Phase 3, and a live unprotected sign-in form today |
| **D17** | Where doc 08 sits in the precedence order | Any further onboarding work |
| **D4** | Production email provider | Phase 2 reaching a real inbox (`FileMailer` unblocks development) |
| **D13** | Anthropic access and model tier per execution mode | Phase 7 entirely |
| **D7** | Finance: structure-plus-unlocks, bring accounting in, or manual entry labelled self-reported | Phase 8 planning |
| **D8** | Capability count — 21 or 24, or a derived registry | Phase 8 planning |
| **D18** | Does the pre-signup Preview audit survive, and in what form | The landing page and doc 09 stage 0 |
| **D19** | Where domain verification gates, now that the company is created immediately | doc 09 stage 2 — **the one real conflict in the new flow** |
| **D20** | The research budget: pages, duration, per-source failure | doc 09 stage 7 |
| **D21** | Whether department selection restricts the directors or only orders them | doc 09 stage 9 |
| **D22** | Whether a member's answer binds their department or only themselves | doc 09 stage 10 |
| ~~**D23**~~ | ✅ **Resolved** — the Neon instance was reset to the repository's head, its schema recorded first in `doc/archive/neon-schema-before-the-d23-reset.md` | — |

**The git remote now exists** (`github.com/parul-bhoite/nexus-os`, `origin/main`
at `ca819d3`), so Phase 0's one external prerequisite is met. What remains
external is **watching the Actions run**: `gh` is not installed on this machine,
so the workflow can be written and proved locally but its green run on the remote
has to be confirmed by you.

Everything else can wait for the phase that needs it.
