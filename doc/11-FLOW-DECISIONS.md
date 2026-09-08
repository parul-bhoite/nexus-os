# NEXUS OS — Flow Decisions

**The authoritative answer record for `doc/10-FLOW-QUESTIONS.md`.**
**Decided by:** Parul · 25 August 2026 · **Status:** ratified except the four items in §5

Legend: **★ Parul decided explicitly** · **✓ recommendation accepted** ("rest of the
questions you are good") · **⚠ needs one line of clarification**

---

## 1. Stage 0 — Landing page

| # | Decision | Notes |
|---|---|---|
| 1 | ★ **No URL capture on the landing page.** | The pre-signup Preview audit is **removed from the product.** The landing page becomes marketing with one action: sign up. The crawl now starts at stage 2, when the company's website URL is given. **D18 resolved.** See §3.1 for exactly what this deletes and what survives |
| 2 | ★ **No plan or pricing selection before signup.** | A company gets a trial for a fixed period; **functionality during the trial is identical to paid.** At expiry a renewal step appears. Renewal and billing are **not built now** — the workspace carries a trial-expiry date and nothing gates on it yet. Treat the plan as "active" for MVP |
| 3 | ★ **Privacy and Terms must exist before public signup.** | Both pages, and the footer links restored. Not required for a design partner behind a link |
| 4 | ★ **Trim the landing page to the seven pillars — and keep a note of the 35 capabilities.** | The full list is preserved in §4 below so nothing is lost when `lib/content.ts` is trimmed |
| 5 | ★ **No public demo or sandbox workspace.** | "Currently, no" |

## 2. Stage 1 — Sign up and log in

| # | Decision | Notes |
|---|---|---|
| 6 | ★ **Email and password at MVP. Google sign-in comes after.** | So password reset is genuinely required at MVP (Q10) |
| 7 | ★ **Verification email goes to the person signing up, sent over SMTP.** | **D4 resolved: SMTP, not a provider API.** `Mailer` gains an `SmtpMailer` driver beside `FileMailer`; `FileMailer` stays for local development. ⚠ Whether verification *blocks* the flow is still open — see §5.1 |
| 8 | ★ **Offer "request to join".** | When the email domain already has a workspace, the primary action is a join request; "create a separate company" is secondary. The request needs an approval surface for that workspace's Owner |
| 9 | ★ ~~**No — one person belongs to one company.**~~ **Superseded by ADR 0026** | Reversed doc 07 M1's agency case; ADR 0026 reverses it back and builds multi-entity at MVP. Consequences in §3.2's banner |
| 10 | ★ **Password reset is in MVP.** | Same token machinery as verification |
| 11 | ⚠ Session length — see §5.2 | "Forty-five days" was said; it is unclear whether that referred to the session or the trial |

## 3. Stage 2 — Register the company

| # | Decision | Notes |
|---|---|---|
| 12 | ★ **Five fields**, industry inferred from the crawl and confirmed at the review gate | Name · website · country · reporting currency · ⚠ *headcount band or headquarters* — see §5.3 |
| 13 | ★ **The website URL is mandatory. No escape hatch.** | A company with no website cannot onboard. Accepted deliberately; the risk is noted in §3.4 |
| 14 | ★ **Gate the exclusive domain claim, invitations and company-data tools — not workspace existence.** | **D19 resolved.** The workspace is created immediately, unverified. `create_workspace_for_claim` splits into `create_workspace` + `attach_verified_claim` |
| 15 | ★ **Allow a mismatch between website domain and signup email domain.** | They lose the EMAIL verification method; DNS TXT or file-at-path only |
| 16 | ★ **One registered domain per company — the company's main URL.** | Additional URLs **may be added** and are crawled as part of research, but they are not identity and cannot be verified. So: `workspace.domain` stays singular and verifiable; a separate `workspace_url` list feeds the crawler |
| 17 | ✓ ~~**No — a user cannot create more than one company.**~~ **Superseded by ADR 0026** | *Recommendation reversed by Q9, then reinstated:* multi-entity is built at MVP. See §3.2's banner |
| 18 | ✓ Trial then read-only, nothing deleted | ⚠ Length pending §5.2 |

## Stages 3–10 and cross-cutting — recommendations accepted

Parul: *"Rest question you are good."* Every recommendation in `doc/10` §4–§12 is
adopted as written, with the two corrections noted above (Q17) and below.

**The decisions this ratifies, restated for the record:**

**Stage 3 — company questions.** Five questions only, and only ones a crawl cannot
answer: what you sell · ideal customer · top three goals · biggest challenges ·
fiscal year start. **Crawl-then-confirm** is the default posture: unknowns appear at
the review gate as facts to correct, never as blank fields. Departments are chosen
from the **fixed seven**; Chief of Staff is automatic and never in the list. Three
to five departments recommended, any number allowed. Single reporting currency.

**Stage 4 — department questions.** The founder answers **their own department now**
and defers the rest; each unanswered block appears on its director as the thing that
turns it on, and an invited manager can answer it instead. Blocks are skippable and
resumable. A **Department Manager may answer and binds the department; a Contributor
proposes** and the proposal surfaces at the review gate. Answers stay tagged to the
department they were given for. **D16 widened to Department Managers. D22 resolved.**

**Stage 5 — documents.** Not required, strongly guided: **three named asks per
selected department.** 25 MB per file, 20 files at onboarding, 500 MB per workspace.
PDF, DOCX, PPTX, XLSX **and CSV**. No images, no OCR at MVP — scanned PDFs fail
visibly and we count how often that happens. **The founder never clears a review
queue mid-onboarding**: their own uploads are already uploader-only, so the queue
exists only for what becomes workspace-visible, and it is reviewed at stage 8.
Consent wording needs legal sign-off before public signup.

**Stage 6 — tools.** Four at MVP: **GA4 · Search Console · one CRM · accounting**
(the last only if D7 brings it in — Q65 says it does not). **Zoho** as the CRM on the
stated GCC-prevalence assumption, to be confirmed with the first design partner.
**Nothing is shown that cannot actually connect** — if nothing connects, the stage
never renders. Connecting requires a verified domain. Read-only scope. Connections
belong to the workspace, not the person. **D10 provisionally resolved.**

**Stage 7 — research.** 20 pages, 5-minute soft cap, hard stop at 10. Resumable
across sessions. A JavaScript-rendered site is **detected and declared**, then we
fall back to questions and documents. Competitors: up to three asked at the review
gate, pre-filled from discovery. **Keyword data stays Locked until DataForSEO
credentials exist — never estimated.** Weekly crawl, three manual re-runs a month.
Total research failure still reaches the dashboard. Progress is shown **per source**
with each one's outcome. **D20 resolved; D2 stays Locked.**

**Stage 8 — review gate.** Not mandatory, but the default landing. 6–8 themes,
~20 highest-impact facts, expandable. Bulk-accept **per theme after expanding it**,
never one global accept. Unreviewed facts are used but **labelled inferred**, with
one-click confirm where they appear. Facts can be deleted with a reason and are not
silently re-inferred.

**Stage 9 — dashboard.** **Department selection restricts which directors exist**,
with an explicit "add a department" action. **The composite score's denominator is
derived from a capability registry, not asserted** — each capability declares its
required sources, and both the score denominator and the completeness meter are
computed from it. **Finance ships with manual entry, visibly labelled
self-reported.** Landing view: Chief of Staff for Owner and Executive, own
department for everyone else. **The assistant panel is reserved in the layout from
the first dashboard**, rendering an honest empty state. **D21 resolved. D7 resolved.
D8 resolved as a derived registry.**

**Stage 10 — members.** Department Managers may invite into their own department
only. A member's onboarding does not block their dashboard. Up to three departments
per member. When a member leaves, the Owner is offered a **logged transfer** of that
member's uploader-only documents — never silent reassignment or deletion.

**Cross-cutting.** Settings has five sections: company profile · domain verification ·
connected tools · members and roles · data export. Export at MVP; full deletion
fan-out at M13. Three emails: verification, invitation, weekly digest — no daily
email until the Brief is real. Responsive everywhere, with a dedicated mobile
capture view for Operations at M11. English only, **but no hardcoded strings in
components**, so Arabic is a translation job rather than a rewrite. A minimal
internal admin console at Phase 3: workspaces, research-run status, error rates.
Target signup-to-review-gate: **twenty minutes.** A first design partner is named
before Phase 2.

---

## 3. Consequences that change the build

### 3.1 Removing the landing URL capture — what dies, what lives

**Deleted from the product:**

| What | Where |
|---|---|
| `POST /preview` — the whole unauthenticated endpoint | `app/routes/preview.py` (339 lines) |
| The landing hero's URL form and the audit result panel | `components/preview/PreviewForm.tsx`, `PreviewResult.tsx`, `app/api/preview/route.ts` |
| The preview cache and its TTL sweep | `_fresh_preview_for`, `jobs/expiry.py:expire_previews` |
| `preview_session` table, `preview_ttl_hours`, and the third-party retention obligation it existed to honour | migration 0004, `config.py` |
| The unauthenticated-path rate limits keyed by IP and domain | `connectors/rate_limit.py` — **the module survives, re-keyed per workspace** |
| `client-address.ts` and the `X-Forwarded-For` trust chain | `apps/web/lib`, `trusted_proxy_ips` |
| **D9 in its entirety** — preview TTL and the third-party deletion path | No third-party data is retained, so there is nothing to expire or delete |

**Survives and becomes load-bearing in research:**
`connectors/ssrf.py` (89 test cases) · `connectors/crawler.py` (extended to
multi-page) · `connectors/extract.py` · `calculators/audit.py` — the brand, SEO and
performance scores become the dashboard's **first real numbers** ·
`connectors/rate_limit.py`, re-keyed to the workspace.

**Net effect:** roughly 700 lines of route, UI and table work is retired, and about
1,100 lines of guard, crawler, extractor and calculator move behind authentication.
The strongest asset in the codebase is kept; only its entry point changes.

**One thing to be aware of:** the audit was the product's first-value moment at
minute seven. With it gone, **the review gate at ~minute twenty is the only
first-value moment.** That raises the stakes on stage 7 finishing quickly, which is
why the crawl starts at stage 2 and documents parse as they upload.

### 3.2 One person, one company — the M:N reversal

> ⚠ **Superseded on 9 September 2026 by ADR 0026** — multi-entity workspaces are built
> at MVP after all. Q9, Q17 and this section's post-MVP deferral are reversed. The
> schema decision below still holds and is what makes the reversal affordable:
> `membership` was kept many-to-many, so nothing needs migrating. What comes back is the
> switcher, `POST /auth/workspace`, work item H6 — and **I5's
> cache-invalidation-on-switch**, which the deletion below retired. Read ADR 0026 before
> acting on anything in this section.

Q9 reverses doc 07 M1's *"many-to-many user↔workspace (agency case)"*.

**Keep the schema, constrain the product.** `membership` stays many-to-many —
it is already built, tested and proved under RLS, and narrowing the table would mean
a migration that buys nothing. The product enforces one live membership per user in
`app/domain/`, with a test asserting it.

| Work this cancels | |
|---|---|
| The workspace switcher UI | never build it |
| `POST /auth/workspace` | delete the route |
| `_teardown_on_switch` | delete the stub; **I5's cache-invalidation-on-switch requirement disappears with it** |
| `membership_own_rows` policy (migration 0003) | keep — login still lists your own membership to find it |
| Old work item `H6` in `BUILD-STATUS.md` | cancelled, ~2 days saved |

**Two consequences worth deciding later, not now.** What happens when a person at
one company is invited to another — today the answer is "they need a second account
on a different email address". And an agency managing several clients cannot use the
product as one login. Both are post-MVP.

### 3.3 SMTP as the mail transport

`app/mail.py` gains `SmtpMailer` beside `FileMailer`, selected by the
`mailer_backend` setting that is currently declared and read by nothing. New
configuration: host, port, username, password, from-address, TLS mode — all
required in a deployed environment, and all fed through `Settings.require()` so they
fail loudly rather than silently not sending.

This also means **C10's email wiring is unblocked now.** It was waiting on D4.

### 3.4 A mandatory website URL

Accepted as decided. The consequence to watch: a GCC SME running entirely on
Instagram or WhatsApp cannot complete signup. If the first design partner hits this,
the escape hatch from Q13 is a small change — the Brain builds from documents and
questions, and the dashboard names what the missing site costs. Recorded here so it
is a known trade rather than a surprise.

### 3.5 Trial as a flag with an expiry

`workspace.trial_ends_at` already exists in migration 0002 and is written by
nothing. Stage 2 sets it. **Nothing gates on it at MVP** — functionality is
identical during the trial, and the renewal step is a later phase. What is needed
now is only that the date is set and visible in Settings.

---

## 4. Preserved — the 35 capabilities, before trimming

Kept per Q4 so the trim loses nothing. Currently in `apps/web/lib/content.ts`
`pillars.list`; **the seven pillar titles and promises stay on the landing page, the
five items under each are removed.**

| Pillar | The five named capabilities |
|---|---|
| **Executive Command** — *know what changed, why it matters, and what to do next* | CEO Morning Brief · Company Health Score · Opportunity Radar · Decision Assistant · Business Simulator |
| **Growth & Marketing** — *plan, launch and optimise growth from one workspace* | AI Marketing Director · Content & Campaign Calendar · SEO Intelligence · Brand Intelligence · Pricing Intelligence |
| **Sales & Revenue** — *find the right opportunities and move them toward revenue* | Lead Intelligence · Sales Workspace & CRM · Proposal Studio · Communication Intelligence · Revenue Forecasting |
| **Competitive Intelligence** — *know who your competitors are and how to respond* | Competitor Discovery · Advertisement Tracking · SEO Gap Analysis · Alerts · Market Positioning |
| **Customers & Retention** — *identify customers at risk before the revenue disappears* | Customer Health · Churn Prediction · Review Monitoring · Retention Campaigns · Revenue at Risk |
| **People & Operations** — *preserve knowledge and keep the company running consistently* | Company Brain · SOP Builder · Workflow Automation · Team Capacity · Company Memory |
| **Finance & Strategic Decisions** — *test major decisions before committing money* | Financial Health · Margin Analysis · Pricing & Expansion Simulator · Scenario Planning · Risk Register |

**Note for later:** five of these are explicitly out of scope per doc 07 §8 —
Business Simulator, Decision Assistant, Opportunity Radar, Pricing & Expansion
Simulator and Scenario Planning. They should not return to the landing page without
also returning to the plan.

---

## 5. The four items still open

### 5.1 Does email verification block the flow? *(Q7)*

Decided: the email is sent, over SMTP, to the person signing up. Not decided:
whether they can proceed to stage 2 before clicking it.

**Recommendation: non-blocking.** They register the company and build the Brain
unverified; verification is required to invite members or connect a tool — the same
gate Q14 puts the domain behind. Blocking means the user sits waiting for an inbox
at the highest-drop-off moment of the flow.

### 5.2 Is forty-five days the session or the trial? *(Q11, Q18)*

"Make it forty-five days" was said while answering the session-length question, then
partly withdrawn.

- **If it is the trial:** 45 days, then read-only, nothing deleted. Sensible, and it
  fits Q2's "trial for a few days, then renewal".
- **If it is the session:** a 45-day session cookie is a long-lived credential on a
  product holding company financials. **I would not recommend it.** 12 hours with a
  rolling refresh on activity keeps someone signed in through a working day and for
  as long as they keep using it.

**Recommendation: trial 45 days, session 12 hours with rolling refresh.**

### 5.3 Is the fifth company field headcount or headquarters? *(Q12)*

"Headquarters" was said; the recommendation being agreed to was "headcount band".
Country is already field three, so a headquarters *city* is close to redundant.
Headcount sizes the People department and the plan tier, and doc 08 §1.4 asks for it.

**Recommendation: headcount band.** If you want the HQ city as well, it is a sixth
field and cheap — but say so, because five was deliberate.

### 5.4 The five business calls *(B1–B5)*

Not answered, and I cannot guess at them. Three genuinely shape the build:

- **B2 — do you onboard the first customers yourself, or is it self-serve from day
  one?** If assisted, stage 3–6 can be rougher for longer and the internal admin
  console matters more than polish.
- **B3 — the target segment for the first ten customers.** This chooses the CRM
  (Q43 is currently a guess) and which department to build first.
- **B5 — is there a launch date or event this is building towards?** It decides
  whether the phase plan optimises for a demo or for a foundation.

B1 (pricing) and B4 (cost per customer) can wait, but B1 will be needed before the
renewal step in Q2 is built.

---

## 6. Decision register — after this session

| Decision | State |
|---|---|
| D2 — DataForSEO | **Locked until credentials.** Keyword data renders Locked; never estimated |
| D3 — Google credentials | Still needed for GA4, Search Console and Google sign-in |
| D4 — email provider | ✅ **SMTP** |
| D6 — six directors for non-executives | ✅ Superseded by Q63 — directors follow department selection, and Chief of Staff stays Owner/Executive only |
| D7 — Finance | ✅ **Manual entry, visibly labelled self-reported** |
| D8 — capability count | ✅ **Derived from a capability registry** |
| D9 — preview TTL and third-party deletion | ✅ **Void** — no preview data is retained |
| D10 — which CRM | ⚠ **Zoho, provisional** — confirm with the first design partner |
| D11 — non-Claude model | ✅ Claude only |
| D12 — deals-lite | Out of MVP |
| D13 — Anthropic access | Still needed before Phase 7 |
| D14 — login rate limiting | ✅ Per-IP **and** per-email counters, exponential backoff not a lock, identical 401 in every case |
| D15 — member onboarding | ✅ Per-department, for invited members |
| D16 — who may administer | ✅ Widened to Department Managers, own department only |
| D17 — doc 08's precedence | ✅ **Doc 08 outranks doc 06 §2.5** on the question set and the department model |
| D18 — pre-signup audit | ✅ **Removed** |
| D19 — where verification gates | ✅ **Exclusive claim, invitations, company-data tools** |
| D20 — research budget | ✅ 20 pages, 5-minute soft cap, hard stop at 10 |
| D21 — department selection | ✅ **Restricts which directors exist** |
| D22 — whose answer binds | ✅ **Manager binds, Contributor proposes** |

**Three decisions remain open, all external: D3, D10 (confirmation), D13.** Plus the
four items in §5 and a git remote.
