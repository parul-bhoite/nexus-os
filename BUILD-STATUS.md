# NEXUS OS — Build Status

**Pending work list regenerated:** 19 September 2026.
**Method:** every row in §6 and §7 was checked against the code, the live Neon
database, or a command that was actually run. Where a row was wrong, the wrong
clause is named rather than quietly replaced — the point of this file is to be
trustworthy, and a register that silently corrects itself teaches nobody why it
drifted.

> ⚠ **What this regeneration covers, and what it does not.**
>
> **Regenerated and verified:** §6 (what needs Parul) and §7 (the pending work
> list) — all 59 rows, by reading the code and querying the database rather than
> re-reading the register.
>
> **Left as historical record, not re-verified:** §0–§5. They describe work at
> the end of Phase 3 and through P18 and remain accurate *as an account of what
> happened then*. Their present-tense claims should not be trusted; §7 is now the
> current state.
>
> **Why this mattered.** Before this pass the list was wrong in both directions,
> and expensively so. Two rows marked absent described things that existed and
> were shipped (`C11` Dockerfiles, `H8` the whole frontend test suite). One stale
> row — `M31` — was taken at face value by a planning agent, which concluded the
> token budget had no production caller and costed a phase against it. Two rows
> described work already finished (`M17`, `M18`), so a QA pass re-reported closed
> gaps as open. **Of the rows checked, roughly half were wrong.**

**Current state, measured 19 September 2026:**

| | |
|---|---|
| Backend tests | **1,751 collected** across 137 files |
| Frontend tests | **271 passing** across 33 files, plus 2 Playwright specs |
| Last full backend run | **1,873 passed / 4 failed in 2:09:44** (20 September). Three were the assistant not being registered in the guards that enumerate skills and settings — `.env.example`, `test_every_skill_has_a_caller`, and the scripted fixtures — all fixed. The fourth is **M22**, now localised to `test_onboarding_agent_e2e.py` |
| Migrations | **40 on disk, head `0040`; Neon is at `0040`** — in sync. `0040` is `generation_citation` (ADR 0056), applied, reversed and re-applied 20 September |
| ADRs | **60.** 0052–0059 are the assistant: what it answers from, the numeral rule, the refusal vocabulary split, the taint boundary, citations as rows, the scope a generation inherits, the budget, and the route module |
| End-to-end walkthrough | `scripts/goal_walkthrough.py` — **64 passed, 0 failed** against a running API and Neon |
| Gate | `ruff`, `mypy --strict` (161 files), `tsc`, `next lint` all clean |

---

## 0. Latest work — the common command surface (17 September 2026)

> **Historical, not re-verified in the 19 September regeneration.** §7 is the
> current state.

**One dashboard for everybody, no department tab rail.** `doc/14`, ADR 0029–0032,
on `feature/dashboard-command-surface`. Eight of eleven steps shipped, one
commit each; the remaining three are blocked on decisions, not effort.

`/dashboard` was a redirect that read a caller's membership and forwarded them
into a director page. It is now the product's front door: a left panel for
navigation, a thin header, and six regions composed from what the reader's
`ScopedSession` can reach.

| Region | What it says |
|---|---|
| Morning brief | Eight checks failed, ranked by points lost. Computed in code — no model, no cost, cannot refuse |
| Where the product is | 2 measuring · 10 reading your answers back · 77 not built yet, of 89 |
| Measured today | The two audit tiles, byte-identical to the director page |
| Open on your side | Of 29 open questions, exactly one changes a figure today |
| The seven directors | The tab rail, demoted to a summary |
| Company Brain | The founder's own words, and what NEXUS assumed |

**Every number on it was derived, and the first draft's were not.** Designing the
region produced four estimated figures and all four were wrong: the denominator
counted the one `RULE`, and a band called *unlockable by answering* held seven
where the registry says **zero** — every fact-consuming tile also needs a source,
so answering a question changes what a tile counts and never whether it exists.

**The largest blocker is not a connector.** `ops_layer` blocks 23 tiles, more
than accounting, and is a feature NEXUS contains rather than anything a customer
connects. Connecting every source in existence would move the figure-producing
count from 2 to 2, because 77 capabilities have no calculator. Both facts are now
said on the dashboard rather than only in a document.

**The connector spine is built and cannot be used yet.** ADR 0031 makes MCP a
transport for fetches made from code — the model never sees a provider, because a
director that called a CRM's MCP server would be *fetching* and I1 would be gone
while every answer stayed plausible. Asserted as an import graph, not by review.
It holds a token and there is nowhere to put one: see **D27** and ADR 0032.

Corrections the build forced on the design, each recorded in its commit: check
labels are used verbatim rather than negated; collapsed findings carry both
halves, because "137 characters" identifies nothing; the directors block is
ordered by state rather than by an enum value that only looks alphabetical; and
`/settings` and `/account` lost their `h1` when the shell took their chrome —
found by an audit, not by a test, and now guarded by one.

**Verified in the browser against the live Prosoft workspace** at every step, and
the brief's arithmetic was derived by hand first and matched exactly: 8 of 18
checks failed, 50 of 135 points not held, two at ten and six at five.

---

## 0b. Before that — the onboarding redesign (15 September 2026)

**Three sections over eight phases. ADR 0027.** The guided onboarding drew a
seven-step rail that mirrored the server's `Phase` enum; four of those steps are
one continuous conversation, `assembling` had no step at all, and the tools step
rendered under the entire transcript. The screen now groups the phases into
**Conversation · Your tools · Summary**.

**The phases did not change, and that is the load-bearing part.**
`ck_onboarding_session_phase`, `Phase` and `test_constraint_enum_parity` are
untouched, so there is no migration and no in-flight session is disturbed. The
grouping is a lookup in the client; every request still takes its stage from the
session row.

What shipped with it:

- The interview count moved from the rail into the current section — "Question 3
  of 5" over the real ceiling, and **named** stages where nothing is countable.
  Reading a website has no denominator (I1).
- `assembling` draws the three stages the server actually commits, instead of a
  greyed-out confirmation card and one line of grey text.
- A composing indicator in the shape of a bubble, where the next bubble will be,
  carrying `role="status"` so the escalating label is announced. The words stay
  under `prefers-reduced-motion`; motion is never the only signal.
- The tools step became a screen: selectable cards, and a panel that names what
  the current selection unlocks as it is chosen. The checkbox is still a real
  `input`, so role, keyboard behaviour and announcement survived the restyling.
  **It still does not connect** — `connectable` is false for all nine and the
  honest sentence is rendered from it (ADR 0023, `doc/11` §73).

**Evidence.** `vitest run --root apps/web` — **17 files, 146 tests, all green**
(140 before, six added for the section model). `tsc --noEmit` clean;
`next lint` clean. The six new tests were proved able to fail: splitting the
conversation back into two rail steps turned **four** of them red, and they went
green again on restore.

**Verified live**, against Neon and a configured `claude-sonnet-5`, at
`localhost:3100` with the API on `:8001`:

- `/health/ready` — database `ok`, pgvector `ok`, language model `ok`,
  embeddings `unconfigured` (a supported state, ADR 0003).
- A completed onboarding lands on `/dashboard`, and the dashboard renders: seven
  directors, section rails, honest per-capability states carrying their registry
  ids, and the assistant panel reserved rather than faked.
- Marketing draws **real computed figures** — `marketing.seo_gaps` at 30/65
  (4 of 9 checks) and `marketing.brand_intelligence` at 55/70 (6 of 9), each
  measured from the crawled site and each opening its own working. The department
  shows **no composite**, stating why, rather than averaging two of nine.
- No console errors on either screen.

**The backend gate, run in full for the first time on this machine.** 1,317
passed, **8 failed**, 66 minutes against Neon (the ~5 minutes quoted elsewhere in
this file is the onboarding suite alone, not the whole run). Six of the eight
were the suite being unable to run rather than the code being wrong, and are
fixed:

- **One real breach.** `grounding/answer.py` named the vendor in a comment,
  added by `5683098`. `test_ai_boundary` reads prose as well as imports. That
  commit was red when it landed — worth knowing when deciding what to do with
  the revert that was staged over it.
- **Four guards could not run on Windows**: `read_text()` with no encoding
  decodes UTF-8 as cp1252 and dies on the first em-dash. Two had a second fault
  underneath, visible only once they could read: paths keyed with `str()` rather
  than `as_posix()`, which made the containment ratchet report
  `retrieval\scoped.py` as an unlisted tenancy violation *and* as missing from
  the sanctioned set in the same run. Neither was true.
  `test_deployment_env` also *wrote* without an encoding, so regenerating
  `doc/DEPLOYMENT-ENV.md` here would have committed mojibake.

**Two remain open, diagnosed rather than guessed at:**

- 🟠 `test_db_timeouts::test_pre_ping_can_be_turned_off_but_defaults_on` — the
  local `.env` carries `NEXUS_DB_POOL_PRE_PING=false` and `hermetic_settings`
  does not pin it, so the fallback leaks into a test asserting the default. Red
  locally, green in CI — the same shape as the `NEXUS_JOBS_DATABASE_URL` lesson,
  inverted. A question about which variables `conftest.py` pins.
- 🟠 `test_upload_limits::test_the_phase_acceptance_three_files_in_one_go` — the
  refusal renders `26112 KB` where the test expects the `25 MB` the product
  promises. **Pre-existing since `98a532e`**, so a phase acceptance test has been
  red for four commits. The fix is a formatter that picks its unit, because the
  same middleware guards 64–256 KB JSON bodies too — that is product copy and
  wants a decision.

**Not verified, and why.** A logged-in walkthrough of the *new* onboarding
sections was not possible: the only workspace on this account has completed
onboarding, so `/onboarding/agent` correctly redirects. Seeing the new sections
live needs a fresh workspace, which needs a signup. The boot screen was confirmed
rendering in the browser; everything past it rests on the test suite.

---

## 1. Where this stands

> **Historical, not re-verified in the 19 September regeneration.** §7 is the
> current state.

**~33% of the product.** Three phases in, and the percentage has gone *down*.
That is the honest reading and not a rounding artefact: Phase 2 deleted a
feature that worked. Phase 0 made the suite capable of proving something, Phase 1
used it to make the repository's existing claims true, and Phase 2 removed the
one thing a stranger could use — because what they could use it for was an
analysis of a company they do not own.

| | Before Phase 0 | Now |
|---|---|---|
| Database tests in CI | **94 skipped, exit 0** | 667 executed, exit 0 — and **actually executed**: until Phase 2 the pytest step never ran at all, see §3 |
| Row-level security proved automatically | no | yes — 12 isolation tests, executed |
| Migrations ever run in reverse | no | yes, every run: `upgrade → downgrade base → upgrade` |
| `mypy --strict` over `tests/` | no | yes, 105 files clean — and passing on a *clean runner*, which it had not been doing |
| Coverage measured | no | 76.43% branch in CI, with a floor that only rises |
| A skipped database test | invisible | fails the build, by name |
| Document upload against Postgres | **rolled back, every time** | writes, and reaches the review queue |
| Superseding a document | **raised** | retires the earlier row |
| A deployed env with no secrets | booted | refuses to start, naming the variable |
| A missing `NEXUS_ENV` | insecure cookies, public `/docs` | refuses to start |
| An unhandled exception | uncorrelatable 500 | carries the `x-request-id` in the log |
| Database timeouts | none set | four, and proved live **on Neon** as well as in CI — §4.7 |
| A server-side fetch without a session | `POST /preview`, open to anyone | none, and an import-graph test fails the build if one returns |
| Data held about a company with no account | retained under a TTL and a sweep | **not collected** — D9 void |

Two of the three 🔴 defects are cleared. The engineering foundation is now
genuinely strong, and almost none of the product is still reachable by a user —
that split is unchanged, and Phase 5 is where it starts to close.

| Area | Complete | Basis |
|---|---|---|
| Foundation — repo, config, logging, health, CI, migrations | **100%** | Real Postgres in CI both directions; config fails closed; correlated 500s; four database timeouts, live on Neon as well as CI. Briefly 95% — §4.7 was open between its discovery and its fix |
| Tenancy, RLS, auth, sessions, roles→scope | **90%** | Proved in CI. Cookies `Secure` outside local. Verification and password reset work end to end, and one account belongs to one company. Gaps: no login rate limit, no audit trail written — both P4 |
| ~~Preview audit (unauthenticated)~~ | **retired** | Deleted in Phase 2 (`doc/11` Q1). The entry point is gone; the engine moved to `app/research/` |
| Research engine (`app/research/`) | **35%** | Guard, single-page crawler and extractor, all behind authentication and all passing from the new location. No job model, no multi-page crawl, no callers — P11 |
| Domain verification (backend) | **70%** | DNS + file work. EMAIL method structurally dead; no transfer; no UI |
| Onboarding + invitations | **70%** | Wizard and API real. Verification is delivered; **invitations are still a copy-pasted URL** (M17) |
| Documents / classification / indexing | **45%** | Upload, chunking, withholding and the review queue all work against Postgres. Gaps: no classifier, no UI |
| Scoped retrieval layer (the security core) | **5%** | `scoped_connection` exists; no retrieval query of any kind |
| Company Brain + review gate | **0%** | Not started |
| Grounding + calculators | **8%** | One calculator, and since Phase 2 it is wired to nothing. It survives because P11 needs it — `doc/11` §3.1 calls its scores the dashboard's first real numbers |
| Dashboards / seven directors | **12%** | Shell + 67 offering specs as data. Zero widgets, zero numbers |

---

## 2. Phase status against `doc/12-IMPLEMENTATION-PLAN.md`

> **Historical, not re-verified in the 19 September regeneration.** §7 is the
> current state.

| Phase | State | Note |
|---|---|---|
| **P0 — CI and the remote** | ✅ complete, with one claim withdrawn | The workflow, the Postgres service and the skip guard are all real and all working. But **"confirmed green on the remote" was wrong**: the run it referred to was red, and every run since has been, because `mypy` failed on an undeclared `bs4` before pytest was reached. The isolation tests were confirmed executed *locally*. They first ran on a remote runner in Phase 2 |
| **P1 — Correctness** | ✅ **complete** | Migration 0010, a real config validator, a correlated exception handler and a constraint-versus-enum test. The fourth item — four database timeouts — was correct in code and green in CI while doing nothing on Neon; that gap (finding #15) is closed, so the phase's claims now all hold where it matters |
| **P2 — Retire the preview product** | ✅ complete, green in CI | Run [33730363386](https://github.com/xi-4206pbhoite/nexus-os/actions/runs/33730363386) — 667 passed, migrations both directions, coverage 76.43%. `POST /preview`, the hero URL form, both components, the BFF proxy, `client-address.ts`, three test modules and the `preview_session` table are gone. The guard, crawler and extractor moved to `app/research/`; the rate limiter is re-keyed to `(workspace, global)`. See §3 |
| **P3 — Identity** | ✅ **complete** | Registration sends; password reset end to end; one person to one company; `POST /auth/workspace` and `_teardown_on_switch` deleted; `SmtpMailer` behind `mailer_backend`, with a deployed environment refusing to boot on the file backend. Migration 0012. See §3 |
| **P4 — The security surface** | ✅ **complete** | Run [33749908728](https://github.com/xi-4206pbhoite/nexus-os/actions/runs/33749908728) — 713 passed, migration 0013 both directions. Credential rate limiting, argon2 off the loop, the audit trail, session refresh, RLS on `domain_claim` with the `nexus_jobs` role (D24 → ADR 0018), and four of the five named findings. #5 and half of H9 are re-deferred with reasons |
| **P5 — Company registration** | ✅ **complete** | Run [33763536577](https://github.com/xi-4206pbhoite/nexus-os/actions/runs/33763536577) — 722 passed. `POST /companies`, join requests, `/register-company`, verification moved to Settings, migrations 0014–0015. **C3 closes**: the authenticated product has a front door |
| **P6 — The onboarding spine** | ✅ **complete** | Resumable multi-stage flow, five company questions with assumptions instead of nulls, department selection driving the director list. Migrations 0016–0017 |
| **P7 — Department question blocks** | ✅ **complete** | Authority model (Q30/D16, Q31/D22, migration 0018) **and the question bank** — 29 questions, each declaring the capability that reads it, with the Q33 guard that fails on one that declares none. ADR 0020 records the cut. **Routes and Q27 done too** — `GET/POST /onboarding/departments/{d}/block`, and each director carries `unanswered_questions`. The block UI too — reached from its director, which carries the count |
| P5–P9 — the onboarding spine | pending | |
| P10–P13 — the Brain | pending | |
| P14–P17 — product surface | pending | |
| P18–P21 — completion | pending | |

---

## 3. What Phase 3 built

**The product can now be signed up for by a stranger, unaided.** That is the
difference this phase makes, and it is smaller than it sounds only because the
pieces were nearly all present: the token machinery, the mailer, the routes. What
was missing was a caller.

**Registration sends.** `send_verification` had **zero callers for two
milestones**, so `email_verified_at` could never be set and the EMAIL
domain-verification method was structurally dead — a whole branch of
`domain_check.py` unreachable because nothing upstream of it ever ran. A
duplicate registration still answers identically and now deliberately sends
nothing: a second email would confirm to whoever triggered it that the first
account exists.

**Password reset**, in its own table (migration 0012) rather than a `purpose`
column on `email_verification`. A stolen verification token confirms an address;
a stolen reset token *is* the account, and a shared table invites the query that
forgets to filter. One hour rather than twenty-four, superseding any outstanding
token, revoking every live session on confirm.

**One person, one company** — `doc/11` §3.2, in `app/domain/membership.py`,
called from the two paths that write a `membership` row rather than from the
routes. The table stays many-to-many: doc 06 §2.1's agency case is deferred
rather than deleted, and the rule is about *live* memberships, which a unique
index cannot express without becoming a partial index that has to agree with
application code anyway.

`POST /auth/workspace` and `_teardown_on_switch` are deleted with it, and **I5's
invalidate-on-switch half is void** (`ARCHITECTURE-HLD.md` §4.6). Scope-keyed
caching stays, because role change is still immediate.

**The web surface**: `/verify-email`, `/forgot-password` and `/reset-password`,
three BFF proxies, a forgot-password link on the sign-in form, and a post-reset
confirmation on it — without which a reset dumps you at a sign-in page with no
explanation, which reads as failure. `AccountPanel` shows one company instead of
a list.

### What Phase 3 proved, and how

| Claim | Evidence |
|---|---|
| **Registering writes an email to disk with a working token** | `test_registration_sends_verification` — reads the `.eml`, extracts the token, spends it, and asserts `email_verified_at` moves from NULL. Then asserts the same token fails the second time |
| **Registering twice sends once and answers identically** | `test_registering_a_known_address_still_answers_identically` — delivery must not reintroduce the enumeration oracle registration already closed |
| **Reset is byte-identical for a known and an unknown address** | `test_password_reset_does_not_reveal_whether_an_account_exists` — `.content` compared directly, headers compared minus the three that vary per request. Plus the asymmetry a body cannot show: only one produced an email |
| **A reset token works once and ends every session** | `test_a_reset_token_changes_the_password_once` and `test_a_reset_revokes_every_live_session` |
| **One live membership per user** | `test_one_live_membership_per_user`, calling the real guard on the application's own session — not a synchronous re-implementation, which is what the first draft did and would have made a fourth entry on H9's list |
| **"Live" excludes revoked** | `test_the_guard_ignores_a_revoked_membership`. Someone who left a company must be able to join another; counting every row ever written locks them out permanently |
| **Your own workspace does not count against you** | `test_the_guard_ignores_the_users_own_workspace` |
| **A deployed environment cannot ship unable to send** | Four refusals in `test_config_gates.py`: the file backend, SMTP without a host, SMTP without TLS, and a plaintext `public_base_url` |
| **No auth route builds a link from the request** | `test_the_link_base_is_configuration_and_never_the_request_host` — `Host` is attacker-controlled, and a verification link built from it is a working account-takeover primitive |
| The suite is green in CI | **688 passed**, coverage **78.49%** against a floor of 75 |

### What the tests found that the plan did not anticipate

- **The one-company guard refused re-accepting your own invitation.** Accepting
  is idempotent by design — `ON CONFLICT DO NOTHING`, so a second click keeps the
  role you hold rather than resetting it (doc 06 §4.15: a role change is not an
  invitation). The first guard counted every live membership, so the second click
  answered "you are already part of a company": true, useless, and refusing the
  one case built to be safe. `test_an_existing_member_keeps_the_role_they_already
  _hold` caught it in CI on the first run.
- **The fix silently did nothing on the first attempt.** `ruff format` had
  collapsed the SQL onto one line, so a string replacement found no anchor and the
  tests failed identically. Worth stating because the symptom of an edit that did
  not apply is indistinguishable from an edit that did not work.
- **Two Phase 2 misses surfaced here.** `scripts\smoke.ps1` still called
  `POST /preview` — so the smoke walk had been broken since that endpoint was
  deleted — and `AccountPanel.tsx` still offered a "free audit" that no longer
  exists. Both fixed. A grep for the deleted route would have caught the first;
  Phase 2 checked the API and the web app and did not check the scripts.

## 4. What is still broken

> **Historical (Phase 2–3), not re-verified in the 19 September regeneration —
> with one exception noted at §4.4, which is now false.** §7 is the current
> state.

Five of the seven are cleared. The two that remain are both *absent features*
rather than broken ones — nothing here fails at runtime; it simply does not exist
yet, and each has a phase. §4.7 was both found and fixed inside Phase 2: it
failed silently, in production only, where CI could not see it.

### 4.1 ✅ ~~Every document upload fails at the chunk INSERT~~ — fixed

`ReviewState` now carries the column's own vocabulary, `review_state_code()` is
the single write path, and `test_constraint_enum_parity.py` asserts the two are
set-equal in both directions on every run. Proved by an upload reaching Postgres
and appearing in the review queue.

### 4.2 ✅ ~~The supersede path raises a CheckViolation~~ — fixed

Migration 0010 permits `'superseded'` and retires `'parsing'`/`'parsed'`, which
nothing had ever written. `DocumentStatus` is the enum the constraint had never
had. Proved by superseding a document and reading the earlier row's status back.

### 4.3 ✅ ~~A new customer cannot create a workspace through the web app~~ — fixed

**Phase 5.** `POST /domains/{claim_id}/workspace` is the only path that inserts
a workspace, and there is no `apps/web/app/api/domains/` directory, no claim
page, and no client function. After registering and signing in, a real user has
no workspace, so `current_scope` answers 403, so every `CurrentScope` endpoint —
onboarding, dashboards, documents, invitations — is unreachable from the UI. The
authenticated product still has no working entry point, and this is now the
largest single thing standing between the code and a user.

### 4.4 ✅ ~~There is no classifier~~ — **false since 19 September 2026**

**Corrected in the regeneration.** There *was* a classifier the whole time:
`app/documents/rules.py:propose`, calibrated, with a 42-sample labelled set in
`tests/test_classifier_calibration.py` — and no production caller. The hardcoded
`classifier_failed=True` described below was the *call site*, not an absent
classifier. ADR 0051 connected it; `classify_chunk` was not touched, so the only
auto-approving path is L3 with an identified department, non-sensitive, at ≥0.85
confidence. Measured precision 1.00 across seven departments, recall 0.93, with
operations at 0.50. The model-backed half remains, planned as `doc/19` K0–K13.

The original text follows, as the record of what was believed:



**Phase 12.** `_classify_all` hardcodes `suggested_scope=L5_PERSONAL`,
`confidence=0.0`, `classifier_failed=True`. `classify_chunk` is the *gate* that
decides whether to believe a suggestion; nothing produces one. So 100% of
content is withheld and `chunks_indexed` is structurally always 0.

Worth being precise now that the path works: this is I4 behaving correctly, not
a bug. Every upload lands in the review queue because the absence of a
classifier is a reason to deny, and the review queue is where a human decides.
What is missing is the suggestion, not the gate.

### 4.5 ✅ ~~No email is ever sent~~ — fixed

`POST /auth/register` calls `send_verification`, `build_mailer` selects the
transport, and `SmtpMailer` sends where `FileMailer` writes. `email_verified_at`
can be set, so the EMAIL domain-verification method is reachable for the first
time.

**Invitations are still delivered by copy-pasting a token URL.** That half is
untouched: the invitation flow has its own screen and its own token, and
`doc/12` §Phase 3's build list does not include it. It is not blocked by
anything — `invitations.issue` returns the token and the mailer now exists — so
it is a small, deliberate omission rather than a dependency. Recorded as **M17**.

### 4.6 ✅ ~~Non-secure cookies and public API docs from one unset variable~~ — fixed

`NEXUS_ENV` is required, the validator refuses to boot without the secrets a
deployed environment needs, and `is_local` is replaced by `cookies_secure` and
`docs_enabled`, which differ on `ci`. ADR 0015.

### 4.7 ✅ ~~Three of the four database timeouts do not exist in production~~ — fixed

**Found in Phase 2, and it is a Phase 1 claim being withdrawn.** `app/db.py`
passes `statement_timeout`, `lock_timeout` and
`idle_in_transaction_session_timeout` in asyncpg's `server_settings`. Against
Neon, `SHOW` returns `0`, `0` and `5min` — the defaults. `application_name`, sent
in the same dictionary, arrives intact, so the connection is healthy and Neon's
proxy is filtering the startup packet to an allowlist.

The code is right, `tests/test_db_timeouts.py` is right, and **CI is green on
this because CI runs plain Postgres, where the same code works.** ADR 0008 makes
Neon the production database, so the protection C12 was written to provide is not
present where it matters. This is the same lesson as D23 in a new costume: a test
whose result depends on which Postgres it met can be green in the place nobody
deploys to and red in the place everyone does.

**Fixed.** The three are issued with `set_config(name, $n, false)` on the pool's
`connect` event — once per physical connection, so one extra round trip per
connection rather than per request. `set_config` rather than `SET` because `SET`
takes no parameters and these values come from configuration; `false` rather than
`true` because a `SET LOCAL` would be discarded by the first commit and leave
every later user of that pooled connection unprotected.

`application_name` deliberately stays in `server_settings`. It was never dropped,
and it is the control that distinguishes "the startup packet is filtered" from
"the connection is broken" if this regresses.

**Proved by planting the regression.** Putting the three back into
`server_settings` turns `test_db_timeouts.py` red against Neon — and leaves it
green against stock PostgreSQL, which is the honest shape of the problem and is
now stated in that file's docstring. No run against one database can prove a
claim about the other.

---

## 5. The developer database was five migrations ahead — D23, resolved

Found by `test_the_schema_is_migrated_to_head` on its first run:

```
the database is at ['0014'] but the migrations on disk head at ['0009']
```

The Neon instance in `.env` also held `company_brain`, `question` and
`question_choice` — no migration here creates them — and a `ck_document_status`
that already permitted `'superseded'`. Five migrations had been applied to it
from a working tree that is in no commit, no branch, no stash and no worktree;
all four were checked.

**Why it mattered beyond tidiness.** A run against that database proved something
other than what the repository contains, in both directions: a defect the repo
still has could pass — §4.2 is exactly that case — and a fix the repo had made
could fail.

**Resolved on Parul's instruction: the database was reset to the repository's
head.** Its schema was recorded first, in
`doc/archive/neon-schema-before-the-d23-reset.md`, because the work is not
throwaway — `company_brain` is Phase 13's central table and
`question`/`question_choice` are Phase 7's catalogue. `pg_dump` could not be used
(client 17.11, server 18.4), so both schemas were introspected and diffed
structurally. 241 rows went with it: 68 `app_user`, 93 `user_session`, 48
`tenant`, 17 `domain_claim`, 14 `preview_session`, and **no `workspace` or
`membership` row at all** — walkthrough residue, nothing that had ever completed
registration.

Verified after: columns, indexes, policies and row-security flags are identical
to a database built from `bootstrap.sql` and migrations 0001–0009, as are all 65
constraints once the `NOT NULL` rows Postgres 18 exposes and 17 does not are set
aside. The full suite runs green against Neon.

**Two consequences for Phase 1.** Migration numbers `0010`–`0014` are free, so
its migration is `0010` as `doc/12` assumes. And the drift was masking three
findings that are real again: **C1** never differed between the two databases and
is still broken against the Python enum; **C2** is missing once more; and **M5**
— somebody had chosen *use the persona table* and added three columns, which is a
decision for Parul rather than an inheritance.

Still open and not answerable from here: whether application code was lost with
those five migrations. Nothing in `app/` references the three tables, so if there
was code, it went with the tree.

---

## 6. What needs Parul

Verified 19 September 2026. Two rows that used to sit here are gone because they
are no longer true.

| # | What | Blocks | State |
|---|---|---|---|
| **D3** | Google API credentials | The Search Console and GA4 connectors | **Open.** Search Console is offered at signup but reads nothing; rather than leave a promise the product cannot honour, ADR 0049 moved it from `unlocks` to `records`, so the tick is collected and nothing is claimed. The connector itself still waits on this |
| **D10** | Confirm Zoho as the CRM with the first design partner | P18, P19 | **Open** |
| **D13** | Anthropic access **and** model tier per execution mode | The model-backed classifier (`doc/19`), P20 | **Half answered.** A key is configured and `/health/ready` reports `claude-sonnet-5`, so *access* is settled. **The tier-per-mode question is not**, and it is the expensive half: classification is per-chunk, and `doc/19` §7 costs a 60-page PDF at ~140 chunks. `doc/19` frames five options and deliberately does not pick |
| **`doc/11` §5.4** | The five business calls — B2, B3, B5 shape the build | P16 onward | **Open** |
| **M5** | Persona: the three extra columns, or not | — | **Decision.** The row's old framing ("use it or drop it") is stale: `persona` is read and written at `routes/auth.py:626,673`, `routes/spine.py:406,459`. What is undecided is only whether to add `department`, `role_title`, `stated_aim` — which exist in neither the database nor any migration |
| **M24** | Two questions feed capabilities with no section | — | **Decision.** `acquisition_budget` and `people_risk` are live keys (`domain/question_bank.py:101,274`) and `tests/test_sections.py:210` pins the pair. ADR 0020's rule for a question nothing consumes is to cut it; this needs the same call |
| ~~**The Actions run**~~ | — | — | ✅ Green, and CI now also builds the container images and runs the Playwright journey against the composed stack (`ci.yml:240,243,291`) |
| ~~**Neon is two migrations behind**~~ | — | — | ✅ **Stale and removed.** Neon is at `0039`, which is head. The warning described a state from Phase 2 |
| **Push access** | This machine authenticates as `xi-4206pbhoite`; `upstream` is `parul-bhoite/nexus-os` | Landing work on the canonical repository | **Open.** 8 commits sit unpushed on `app/design` |

---

## 7. Pending work list

**Every row below was verified on 19 September 2026** against the code, the live
Neon database, or a command that was run. Rows are grouped by what is actually
true now, not by the priority they were filed under.

### ✅ Closed — and wrongly listed as open

These were open in the register and are not open in the code. Several were shipped
long ago and never struck.

| ID | What the row claimed | What is true |
|---|---|---|
| **C4** 🔴 | "End-to-end test of the real signup journey — does not exist" | `apps/web/e2e/journey.spec.ts:99` walks landing → sign up → verify from the real `.eml` → register company → dashboard, run in CI (`ci.yml:291`) against the composed stack |
| **C11** 🔴 | "No Dockerfile anywhere" | `apps/web/Dockerfile`, `services/api/Dockerfile`, `docker-compose.yml`, `docker-compose.ci.yml`, plus `docker/caddy` and `docker/postgres`. CI builds and stands them up (`ci.yml:240,243`) |
| **H2** | "`/evals/permissions` — absent" | `evals/test_permissions.py`, 311 lines. `test_the_eight_permission_specs:178` runs all eight red-team specs against a real database |
| **H7** | "RLS on `domain_claim` — no policy, 12 SQL sites" | Live Neon: `relrowsecurity` and `relforcerowsecurity` both true, two policies (`domain_claim_own_rows`, `domain_claim_maintenance`) |
| **H8** | "Frontend test harness — zero tests, no framework" | 33 files, **271 tests**, plus `e2e/journey.spec.ts` and `e2e/scan.spec.ts` |
| **M8** | "One scoping primitive — route the five implementations through it" | Already true: every `set_config('nexus.*')` in the codebase is inside `retrieval/scoped.py` (lines 29, 30, 86, 103) |
| **M16** | "No lockfile today, so every CI run resolves fresh" | `services/api/requirements-dev.lock`, hashed, plus `uv.lock`; CI installs `--require-hashes` and caches on it (`ci.yml:74-96`) |
| **M19** | "Marketing numbers not reachable; nothing calls `marketing_state`" | `marketing_state` **no longer exists**. Both capabilities are listed `_IMPLEMENTED` and `_REACHABLE` (`domain/registry.py:474,521`). The row's evidence is stale in every clause |
| **M20** | "Refusal phrased in KB, test asserts MB" | `http_limits._readable:92-114` picks the unit by magnitude. The row also names the wrong file and conflates two modules |
| **M21** | "`test_pre_ping…` reads `pool._pre_ping`; SQLAlchemy drift" | Fixed, 17/17 pass. The diagnosis was also wrong: the cause was this repo's `.env`, not the library |
| **M29** | Breaking change to `PUT /companies/current/reporting` | Confirmed as described (`routes/companies.py:317,407`) |
| **M31** | "`narrate`, `pipeline.run`, `ledger.record` have no production caller" | **All three do.** `narrate` ← `routes/dashboards.py:2233`; `pipeline.run` ← `grounding/answer.py:221`; `ledger.record` ← `answer.py:241`. This row misled `doc/19` into a false conclusion about the token budget |
| **H3 · H4 · M4 · M17 · M18** | see §7.4 | Closed today — the classifier wiring, both document screens, signed download, invitation email coverage, and the Search Console promise |

### 🟠 Partly done — the row is half right

| ID | Verified state |
|---|---|
| **H1** | 🟡 **Proven working, still without a production caller (20 September 2026).** "5% — `scoped_connection` only" was wrong: `app/retrieval/` is 9 modules / 1,264 lines with ~20 production importers. The semantic half has now been **driven against real data for the first time**, end to end: a Finance document uploaded through the app, auto-approved to `L3['finance']` by the rules classifier, embedded, then retrieved — a caller holding FINANCE gets `count=1` and the passage back; a caller holding only EXECUTIVE gets `count=0` and nothing, same data, same query. **Two things that were in the way, both now known**: (a) no chunk was ever `approved` until ADR 0051 wired the classifier the day before, so `search` could never have matched anything; (b) **`run_scheduler` defaults to `False` and is unset in `.env`, so `_embedding_job` never runs on a dev machine** — every chunk sat with a NULL embedding and the failure looked like an empty index. **H1 now has its consumer (20 September 2026).** `doc/20` A0–A11 built the Nexus Assistant on top of it: `app/assistant/` (contracts, fence, grounding, budget, ask), the `assistant-answer` skill, migration `0040` (`generation_citation`), `POST /dashboards/{department}/ask` behind `assistant_enabled` (**off**), and the panel's input box. **The injection gate that this row once wrongly called open is now genuinely met**: `evals/test_injection.py` gained eight tests driving real code with a scripted model, and `evals/test_assistant_scope_leak.py` proves a refusal is byte-identical whether or not the content exists. **A12 — reading the numbers and flipping the flag — is Parul's and is not done.** `evals/test_injection.py` is 10/10 and `test_permissions.py` 2/2, but the ten are assertions over `domain/untrusted.py`'s dataclass — no model, no prompt, no retrieval. Green means the taint model is specified, not that an assistant resists injection (ADR 0052, Consequences). `doc/20` A3 builds the evals that could actually fail; A2 landed 20 September and is what A3 drives |
| **H5** | "`audit_log` is dead schema" is wrong — `audit.record` is called from 12 sites and `GET /audit-log` exists with a web BFF route. **Open:** the actor is returned as a raw UUID with no join to a name (`routes/audit.py:71`), and there is no read UI |
| **H12** | "8% — one calculator" is wrong: the `generation` table exists (migrations 0023, 0029; 16 columns live) and `app/calculators/` holds 10. Remaining scope needs restating against what is built |
| **H13** | "Close the 14 open items" — `AUDIT-FINDINGS.md` now has **6** un-struck rows (#5, #14, #17, #22, #23, #26), and #14 and #26 are each explicitly half-closed |
| **H14** | "Four untested modules" is wrong — all four now have tests. Only `domain/invitations.py` has a thin direct-import surface |
| **H15** | The two hardest landing-page claims were already reconciled (`lib/content.ts:463`). **What remains is the pillar grid alone**: 35 capabilities named with no status, against a registry of 90 with 23 implemented |
| ✅ **H16** | **Closed 20 September 2026.** Reduced-motion was already fixed in both halves (`globals.css:80-87`, `MotionProvider`). The skip link was the live half: `#main` existed in only two places, so the first control a keyboard or screen-reader user meets did nothing on **13 routes** — the 7 behind `AuthShell`, `/scan`, the OAuth callback, `/onboarding/agent`, and four added the same week by this session (`/documents`, `/review-queue`, `/privacy`, `/terms`). `id="main"` is now on all nine `<main>` elements, and `components/shell/__tests__/skip-link.test.ts` asserts it statically — every `<main>` in `app/` and `components/`, plus that the root layout still points at `#main`. Verified to fail by removing one id, and confirmed over HTTP on six routes. **`tabIndex={-1}` followed on all nine**: `id` alone moves the viewport and, in Safari and Firefox, leaves focus behind — the next Tab returns to the navigation the user just asked to skip, so the link appears to work and does not. Proved in a browser: activating the link moves `document.activeElement` to `MAIN#main`. No visual cost — the design reset already sets `outline-style: none`, so no ring is drawn around the content area |
| **M1** | Sections and blocks exist (`SectionRail`, `SetupSection`, `BlockCard`, rendered at `DirectorPage.tsx:256`). What remains is the render states (L3) and reach — 23 of 90 |
| **M3** | `revoke_claim` and `claims_due_for_recheck` exist (`auth/domains.py:430,454`) but **no job calls them**, and ownership transfer has no implementation |
| **M7** | "Four settings unread" is wrong — `mailer_backend` and `mail_root` are read at `mail.py:135-137`. **Two** are unread: `signed_url_ttl_seconds`, `model_cache_dir` |
| **M11** | `auth-proxy` already has the header allowlist, manual redirect, three timeouts, correct multi-cookie forwarding and 504/503 disambiguation, with 11 tests. The row states no acceptance criteria, which is its actual defect |
| **M23** | "No route serves a narrated tile" is wrong — `POST /{department}/narrate` exists (`routes/dashboards.py:2170`). **True:** `calculators/deltas.py` has zero callers |
| **L1** | 6 confirmed-dead Python symbols (the four in `calculators/deltas.py`, plus `revoke_claim`, `claims_due_for_recheck`). "Ten" is unproven; the frontend half was not checked |
| **L2** | `chunk.is_dept_aggregate` is **not** dead — it is in the retrieval predicate (`retrieval/chunks.py:45`). `document.retention_until` is dead; `audit_log.impersonated_user_id` is written but never non-`None` |

### 🔴 Open — confirmed

| ID | Verified state |
|---|---|
| **H9** | The `check_and_increment` mirror is still there (`tests/test_rate_limit.py:60`) |
| **H11** | 🟡 **Half closed, 20 September 2026.** `/privacy` and `/terms` now exist and are linked from the footer again, guarded by `components/sections/__tests__/footer-links.test.ts` (verified to fail by repointing a link at a missing page). **Every factual claim on them was read out of the code and cites its file** — the 12-hour rolling session, the seven-day scan retention, the five-minute download link, the keyed-hash rate limiter, embeddings computed locally while interview and document text does go to Anthropic. **What is deliberately not written is the legal half**: no controller identity, no PDPL position, no governing law, no liability, no data-request route, and no retention policy for account data. Those are listed on the pages themselves as undecided rather than filled with template prose. **A lawyer still has to write the contract half before anyone real relies on this** — and `doc/17` Phase 3's bilingual PDPL `/legal` surface, with Arabic as the stated reference version, is untouched |
| **M10** | **37** `as <Type>` casts across `apps/web/lib/*.ts`, not "four", and no runtime validator in `package.json` |
| **M13** | No `loading.tsx`, no `global-error.tsx`. `error.tsx` and `not-found.tsx` do exist, so the gap is narrower than stated |
| **M15** | The embedding pass still runs in the API process (`jobs/scheduler.py:111`, started at `main.py:91`) |
| **M22** | ✅ **Closed 21 September 2026 — ADR 0060.** A pooled asyncpg connection was created on one event loop and closed on another; the graceful close armed a timer on the dead loop, raised `RuntimeError: Event loop is closed`, and asyncpg aborted instead — which on CPython 3.12 leaves a TLS socket open. `Pool._close_connection` swallowed and logged it at DEBUG, so only a `ResourceWarning` escaped, failing **whichever test triggered GC**. Fixed by giving `test_onboarding_agent_e2e.py` a `NullPool` (D37 option C), changing the pool class and nothing else. **Verified: 34 passed, 0 warnings.** Costs **+11m39s** on that module (20:03 → 31:42, +58%; ~+9% on the full run) — considerably more than the ninety seconds estimated when it was chosen, and still far less than the hours a suite-wide `NullPool` would have cost |
| **M25** | Both halves confirmed: `GET /audit-log` is Executive-readable where `doc/08` §8C says Owner-only, and it returns a raw actor UUID |
| **M26** | `BrainCard.tsx:175` renders "Read-only here"; no delete or per-item sensitivity |
| **M27** | **10 requests on load, not eight** — every panel mounts at once and fetches, plus one per running department. The parallel-mount fix the row describes is present |
| **M28** | `read_across_entities` (`domain/group.py:126`) is called only by tests; no roll-up screen exists |
| **M32** | Accurate as written. `STALE_AFTER_DAYS = 7`, no route passes `age_days`, nothing re-crawls, so `stale` is unreachable and `measured_at` is served instead |
| **L3** | `WARMING` / `SELF_REPORTED` are returned only when `history_days` / `self_reported` are passed, and no route call site passes either |
| **L4** | Exactly four orphaned sections: `#problem`, `#moments`, `#compare`, `#faq` |
| **L5** | `config.embedding_dim` and the migration's `EMBEDDING_DIM` agree by coincidence; no test asserts it |
| **L6** | `documents/embed.py:74` still builds a vector literal by hand |

### ⚪ Void or unanswerable as written

| ID | Why |
|---|---|
| **M12** | "Real state handling in `TeamStep`" — **`TeamStep` does not exist.** `lib/onboarding-client.ts:59` records that it was deleted. The row names a deleted target |
| **L8** | "Unused component props" names no props, and `tsconfig` sets neither `noUnusedLocals` nor `noUnusedParameters`, so the compiler cannot answer it. A manual scan found none |

### 7.4 Closed today, 19 September 2026

Eight commits. Each was verified against a running stack rather than only in
tests, and two were verified by planting the regression and watching the new test
fail.

- **The anonymous scanner** (G0–G11, ADRs 0045–0048) — `/scan`, robots-respecting,
  SSRF-guarded, rate-limited, seven-day retention with a working expiry sweep.
- **ADR 0049** — a tool now carries either `unlocks` (a promise, refused unless a
  capability backs it) or `records`. Search Console stopped promising a tile.
- **Invitation email coverage** — the send existed and nothing tested it; `inviter`
  was a parameter no caller passed.
- **ADR 0050 / migration 0039** — `_write_one` raises on a discarded worker write,
  and the blanket `research_source` policies were dropped so the guard can fire on
  the role production actually uses. Found by `security-reviewer`: the first
  version of the guard was inert on the deployed path.
- **ADR 0051** — the calibrated rules classifier was connected. It had existed,
  measured, with no caller.
- **`/review-queue` and `/documents`** — H4, both halves. Withheld chunks can be
  placed; documents can be uploaded and downloaded outside onboarding.
- **M4** — signed download. The endpoints were complete; the relative `/files/…`
  URL resolved to a 404 on the web origin.
- **A defect introduced and fixed in the same day**: `/documents` and
  `/review-queue` shipped without an `AppShell` layout, so they had no nav, no
  header and no `#main` for the skip link. Found by H16's audit, fixed, verified.

---

## 8. The gate

> **`scripts/` is PowerShell and this machine is macOS with no `pwsh`, no Docker
> and no `psql`.** The commands below are what actually runs here; the `.ps1`
> equivalents are kept in git history for the Windows machine. `CLAUDE.md` has
> the full list and the traps.

```bash
export NEXUS_JOBS_DATABASE_URL="$(grep -E '^NEXUS_JOBS_DATABASE_URL=' .env | cut -d= -f2-)" && services/api/.venv/bin/python -m pytest services/api/tests -q
```

```bash
cd services/api && .venv/bin/python -m ruff check app tests && .venv/bin/python -m mypy app
```

```bash
cd apps/web && node_modules/.bin/vitest run --root . && node_modules/.bin/tsc --noEmit -p tsconfig.json && npx next lint
```

```bash
services/api/.venv/bin/python scripts/goal_walkthrough.py
```

Four things that are easy to get wrong, each of which has cost time:

- **`mypy` must run from `services/api`.** From the repo root it misses
  `pyproject.toml` and reports phantom errors — including the `apscheduler` stub
  exemption. Five false errors were chased this way on 19 September.
- **`NEXUS_JOBS_DATABASE_URL` must be *exported*,** not merely present in `.env`.
  `tests/dburl.jobs_database_url` reads the environment only, deliberately: a
  `.env` fallback would silently run the maintenance-role suites as `nexus_app`
  and prove the opposite of what they assert.
- **`--no-cov` on a partial pytest run**, or the 75% coverage gate fails after
  every test in the file passed.
- **The full backend suite takes ~2 hours against Neon**, not the ~5 minutes
  quoted elsewhere in this file — that figure was the onboarding suite alone.

**It needs a database, and refuses to run without one** (ADR 0013), **and it
needs `NEXUS_ENV`** (ADR 0015).

---

## 9. Next

Ordered by what the evidence in §7 actually supports, not by filing priority.

1. ~~**Privacy and Terms pages (H11).**~~ Done 20 September 2026, with the legal
   half explicitly unwritten — see §7. **What remains is a lawyer**, plus a
   decision on `doc/17` Phase 3's bilingual PDPL `/legal` surface.
2. ~~**The skip link (H16).**~~ Done 20 September 2026 — 13 routes fixed and a
   static guard added. See §7.
3. **The semantic half of retrieval (H1).** `chunks.search` and `chunks.count`
   are written, evaluated by the red-team specs, and called by nothing in
   production. This is the gap between 23 reachable capabilities and the rest —
   the single largest lever on what the dashboard can show.
4. **The model-backed classifier (`doc/19` K0–K13).** Now has a live rules floor
   to be measured against, which is what `doc/19` §7 recommends doing *before*
   answering D13.
5. **M22 is closed** (ADR 0060). It cost a false failure on every full
   run for weeks. A connection closed on the wrong event loop aborted
   instead of closing, leaking a TLS socket that failed an unrelated
   test. `NullPool` in the one module that crosses loops fixes it, for
   +11m39s there and about +9% on the full run.

**Two things that are decisions, not work:** D13's tier-per-mode half, and D3's
credentials. Both are named in §6.
