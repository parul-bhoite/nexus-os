# NEXUS OS — Build Status

**Regenerated:** 3 September 2026, at the end of **Phase 3** of
`doc/12-IMPLEMENTATION-PLAN.md`.
**Method:** every claim below was run, not read. Where a figure is quoted, the
command that produced it is named.

---

## 1. Where this stands

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

### 4.4 🔴 There is no classifier

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

| # | What | Blocks |
|---|---|---|
| **The Actions run** | ✅ **Green in Phase 2** — run [33730363386](https://github.com/xi-4206pbhoite/nexus-os/actions/runs/33730363386), 667 tests executed on a remote runner. Phase 0's claim that this was already true was wrong; see §2 | — |
| **Push access** | This machine authenticates as `xi-4206pbhoite` and is **denied on `upstream` (`parul-bhoite/nexus-os`)**, which is what `dev` tracks. Phase 2 was pushed to `origin` (`xi-4206pbhoite/nexus-os`) instead, and CI ran there. The two remotes have now diverged and only you can reconcile them | Landing Phase 2 on the canonical repository |
| ~~**D23**~~ | ✅ Answered and done — Neon reset to the repository's head, schema recorded first in `doc/archive/` | — |
| **D3** | Google API credentials | P18 (GA4, Search Console), Google sign-in |
| **D10** | Confirm Zoho as the CRM with the first design partner | P18, P19 |
| **D13** | Anthropic access and model tier per execution mode | P14, P20 |
| **`doc/11` §5.4** | The five business calls — B2, B3 and B5 shape the build | P16 onward |
| **Neon is two migrations behind** | It is at `0009`; head is `0011`. `alembic upgrade head` applies Phase 1's `0010` and Phase 2's `0011`, and **0011 drops `preview_session`** — so it is a data-destroying step on your database and was deliberately left for you | Running the suite locally |

Everything else `doc/11` settled. Nothing in Phase 3 is blocked.

---

## 7. Pending work list

Cleared in Phase 0: **C5** (Postgres in CI, fail on skip), **C6** (Alembic both
directions), **M9** (coverage, `--strict-markers`, type-check `tests/`).

Cleared in Phase 1: **C1** (`review_state`), **C2** (`'superseded'`), **C7** (the
no-op validator), **C8** (`NEXUS_ENV` fails closed), **H10** (correlated
exception handler), and **M6** (constraint drift detection, as
`test_constraint_enum_parity.py`). **C12** (database timeouts) was reopened
between Phase 2's discovery of finding #15 and its fix, and is closed again —
the three server-side timeouts now apply on Neon, not only in CI.

Cleared in Phase 4 so far: **C9** (credential rate limiting, argon2 off the
event loop) and **H5** (the audit trail). Findings **#1, #2, #3, #9, #10 and
#11** close with them; **#5 is re-deferred** with a reason rather than left
looking open-but-forgotten.

Cleared in Phase 3: **C10** (wire email delivery) and **M7** (the four config
settings held back until email existed). `POST /auth/workspace` and
`_teardown_on_switch` are deleted.

Cleared in Phase 2: the preview retirement itself, which had no work-item ID —
it is `doc/12` §Phase 2 in full. **H9** shrank rather than closed: of its three
test mirrors,
`expire_previews`' died with the code it mirrored, and `check_and_increment` and
`scoped_connection` remain.

**Nothing critical fails at runtime.** Every 🔴 below is a feature that does not
exist yet.

### 🔴 Critical — blocks the application from being usable

| P | ID | Task | Phase | Current status | Dependencies | Effort |
|---|---|---|---|---|---|---|
| 🔴 | C4 | End-to-end test of the real signup journey against Postgres | P9 | Does not exist | C1, C2, C3 | 2 d |
| 🔴 | C11 | API and web container images + a runnable stack | P9 | No Dockerfile anywhere | none | 2 d |

### 🟠 High — required for a complete, production-ready application

| P | ID | Task | Phase | Current status | Dependencies | Effort |
|---|---|---|---|---|---|---|
| 🟠 | H1 | The scoped retrieval layer | P10 | 5% — `scoped_connection` only | embeddings | 8 d |
| 🟠 | H2 | `/evals/permissions` as executable red-team specs, written before H1 | P10 | Absent | — | 3 d |
| 🟠 | H3 | A real classifier behind the gate | P12 | §4.4 — hardcoded failure. The gate and the queue now work, so this is the missing *suggestion*, not the missing guarantee | D13 if model-backed | 4 d |
| 🟠 | H4 | Document upload + review-queue UI | P8 | Absent. The API behind it now works end to end | C3 | 4 d |
| 🟠 | H5 | Write the audit trail | P4 | `audit_log` is dead schema | none | 2 d |
| 🟠 | H7 | RLS on `domain_claim` | P4 | No policy, 12 SQL sites | none | 1 d |
| 🟠 | H8 | Frontend test harness — Vitest + Playwright | P9 | Zero tests, no framework | C11 | 3 d |
| 🟠 | H9 | Retire the `check_and_increment` test mirror | P5 | **One of three left.** `expire_previews`' mirror died with the preview product; `test_tenant_isolation.py`'s hand-set GUCs are **deliberately kept** and now guarded against drift (see that file). The remaining one is `consume` in `test_rate_limit.py`, a synchronous copy of the limiter's upsert. Attempted in P4 and reverted: driving the real async function from a sync test needs an engine per call, which turned a 30-second module into a ten-minute one against Neon. The fix is a module-scoped loop and engine, or making the module async | C5 ✅ | 0.5 d |
| 🟠 | H11 | Privacy and Terms pages | P16 | Deliberately absent; signups are live | content | 1 d |
| 🟠 | H12 | Grounding pipeline + `generation` table | P14 | 8% — one calculator | H1, D13 | 8 d |
| 🟠 | H13 | Close the 14 open items in `AUDIT-FINDINGS.md` | P4 | Open and scheduled | C9 for three | 3 d |
| 🟠 | H14 | Behavioural tests for the four untested modules | P3, P5 | `routes/onboarding.py`, `auth/domains.py`, `domain/invitations.py`, `retrieval/scoped.py`. `test_document_upload_db.py` is the pattern to copy | C5 ✅ | 3 d |
| 🟠 | H15 | Reconcile the landing page with what exists | P16 | 35 capabilities named as product | none | 0.5 d |
| 🟠 | H16 | Fix the skip link and the reduced-motion regression | P16 | Broken on 8 of 9 pages | none | 1 d |

**H6 (workspace switcher) is cancelled** — `doc/11` Q9 makes it one person, one
company. ~2 days saved.

### 🟡 Medium — important, not blocking

| P | ID | Task | Phase | Dependencies | Effort |
|---|---|---|---|---|---|
| 🟡 | M1 | Dashboard shell + first real widgets. **Step A of `doc/13` is done** — the capability table is one id space, the source ledger is data, and the Reporting panel exists (migration 0027). The sections, the blocks and the seven render states are what remain | P15, P16 | H1, H12, D7 ✅, D8 ✅ | 8 d |
| 🟡 | M3 | Domain claim lifecycle — recheck job, ownership transfer, revocation | P3 | none | 2 d |
| 🟡 | M4 | Document list + signed download | P8 | H4 | 1.5 d |
| 🟡 | M5 | Persona: use it or drop it. The lost migrations had chosen *use it* — three columns and a check, recorded in `doc/archive/neon-schema-before-the-d23-reset.md` §3 | P4 | none | 1 d |
| 🟡 | ~~M6~~ | ✅ **Done** — `test_constraint_enum_parity.py`, and it requires every value-list constraint to be registered, not only the ones somebody remembered | P1 | — | — |
| 🟡 | M7 | Config hygiene — `session_secret` deleted and `.env.example` drift now fails the build; four settings (`signed_url_ttl_seconds`, `mailer_backend`, `mail_root`, `model_cache_dir`) are still unread and deliberately kept until P3 wires email | P3 | C10 | 0.25 d |
| 🟡 | M8 | One scoping primitive — route the five implementations through `retrieval/scoped.py` | P10 | H1 | 1 d |
| 🟡 | M10 | Validate API responses at the web boundary — four blind `as` casts | P5 | none | 1 d |
| 🟡 | M11 | `auth-proxy` hardening | P4 | C9 | 0.5 d |
| 🟡 | M12 | Real state handling in `TeamStep` | P17 | none | 0.5 d |
| 🟡 | M13 | `loading.tsx` / `global-error.tsx` | P16 | none | 0.5 d |
| 🟡 | ~~M14~~ | ✅ **Done** — the data was right and the docstring was stale. `score_denominator` returns six because Customers is a unit without a page (finding #27), and the sentence saying five went with the table's move into `domain/registry.py` | P15 | — | — |
| 🟠 | M18 | **Two connectors turn nothing on, and one is promised during onboarding.** No capability requires `SEARCH_CONSOLE`, and the tools step tells the customer it will show *"which searches you already rank for"*. ADR 0023 makes it one of the first two connectors to build. `PAGESPEED` is the same shape without the promise. Asserted in `tests/test_source_ledger.py` | P16, P18 | ADR 0023 | 1 d |
| 🟠 | M25 | **The audit log is readable by an Executive and `doc/08` §8C says Owner-only.** `GET /audit-log` gates on `require_executive_surface`. Also shows no actor: it stores `actor_user_id` and returns the UUID, and resolving it needs a join the route does not make | P4, P21 | none | 0.5 d |
| 🟡 | M26 | **The Brain panel is read-only and `doc/13` §14 asks for more.** Per-item sensitivity and passage counts need the `fact` table exposed; the delete needs P21's fan-out to passages, embeddings, cached answers and derivations. Read-only is the honest cut until both exist | P15, P21 | none | 1.5 d |
| 🟢 | M27 | **The settings screen makes eight independent requests** — but no longer eight *after* a ninth. The screen used to gate every panel on `fetchCompany` + `fetchState`, so the six prop-less panels did not even begin loading until those resolved; they now mount immediately and fetch in parallel (defect 47), which removes a serial round trip to `us-east-2` from every visit. What remains of this item is the eight requests themselves: per-panel loading is deliberate, so the fix is a shared cache or an optimistic render, not one endpoint | P15 | none | 0.25 d |
| 🟠 | M24 | **Two questions still feed capabilities with no section**, and step D softened rather than closed it. `acquisition_budget` and `people_risk` now appear in Setup, so the answer is visible — but the Growth Plan and the Executive risk register still have nowhere on any screen to *act* on them. ADR 0020's rule for a question nothing consumes is cut it; this needs the same decision. `test_sections.py` holds the pair | P15 | Parul | — |
| 🟠 | M28 | **The group roll-up screen is the last of ADR 0026.** `read_across_entities` is the read path and it is generic over the value on purpose; the screen `doc/13` §4.1 describes — *"four entities, three scored"* — needs a figure each entity can compute, and none is reachable yet (M23). The switcher, panel 4b and the switch endpoints are done | P15, P17 | M23 | 1 d |
| 🟡 | M29 | **`PUT /companies/current/reporting` now requires `currency` and `country`**, so a caller that omits either gets a 422 where it used to get a 200. Deliberate — the panel always sends every field, and treating an absent currency as "keep the existing one" would make a clear-vs-keep decision silently, on the one setting that relabels every figure in the product. Recorded because it is the only breaking change in the settings API | P15 | none | — |
| 🟢 | M30 | **Step F's full-suite run: 1,229 passed, 4 failed, 1 error** — and none of the five is step F's. Three are the standing M20–M22. The fourth was a real *test* defect and is **fixed**: `test_the_limit_actually_bites` maxed one rate-limit bucket where `_window_start` floors to the hour, so six attempts straddling `14:00` split across two rows and neither reached six — it now sums the `login_email` rows, which a fresh address makes exact. The error was `SSL SYSCALL error: No route to host` against Neon 40 minutes into an 86-minute run; `test_auth_flow.py` passes 10/10 on its own. Nothing here blocks step G | P4 | none | done |
| ✅ | M33 | **The daily token budget was unenforced for four hours a day** — found at 22:13 UTC by a full-suite run, and **fixed**. `_SPENT_SQL` compared `created_at` (timestamptz) against `date_trunc('day', now() AT TIME ZONE :tz)`, which is **naive**; Postgres reinterpreted it in the session timezone (GMT), so local midnight in Muscat became midnight UTC. Between 20:00 and 24:00 UTC the cutoff sat in the future, the query summed nothing, both budgets read zero and `exhausted` could not become true. The window moved with each workspace's own reporting timezone. Fix is a second `AT TIME ZONE :tz`; the new `test_the_day_boundary_is_the_workspaces_midnight_not_utc` pins it against explicit timestamps and was **verified to fail with the fix reverted**, at any hour | P14 | none | done |
| ✅ | S1 | **Slice 1: the first computed numbers on a tile.** `marketing.seo_gaps` and `marketing.brand_intelligence` now render a real score, its denominator, what it measures, the page it came from, the date, and a drawer onto the nine checks that produced it. Verified end to end in a browser against a live crawl: `45 / 65 points · 6 of 9 checks`, and the drawer's arithmetic sums. **The blocker was that the crawl threw away the HTML** — `extract_signals` and `calculators/audit.py` were both written, pure and tested with **zero callers** for a year, because nothing kept a page long enough to feed them. Migration 0028's `page_signals` closes it. Both tiles are pinned to `partial` by construction and neither can drift to `live` | P16 | none | done |
| 🟡 | M31 | **Slice 2: narration, as an explicit user action.** `narrate`, `pipeline.run` and `ledger.record` still have no production caller, and `Computation` was built to carry exactly the `(Computed, trace)` pair `narrate` takes — down to the `window` and `checks` keys — so this is wiring rather than reshaping. Deliberately **not** on the dashboard render path: a model call per tile would mean a missing API key turns a computable 45/65 into `unavailable`, which ADR 0011 makes a regression in honesty, and reloads would hit `BUDGET_EXHAUSTED` on a number already in the database | P16 | S1 | 1 d |
| 🟡 | M32 | **Re-crawl cadence is an open question, and `stale` stays unreachable until it is answered.** Passing `age_days` to `state_from_sources` looks free and is not: `STALE_AFTER_DAYS` is 7 and **nothing re-crawls** — the background run is queued at registration or on explicit request, and `routes/research.py` counts requests against a quota because queueing belongs to the founder who asked (Q55). So deriving staleness would mark every audit tile "out of date" eight days after signup, permanently. The figure serves `measured_at` and renders it beside the number instead | P16 | none | 0.5 d |
| 🟠 | M23 | **P14 was built and never joined, and step B joined it.** `grounding/context.py`, `grounding/ledger.py` and `grounding/answer.py` are the seam; `narrate-metric` is the first skill that phrases a figure without producing one. What remains of the phase: `calculators/deltas.py` is still uncalled by any capability, and no route serves a narrated tile — the first one lands with the sections (step C/D) | P14 | M1 | 1 d |
| 🟠 | M19 | **P16's Marketing numbers are not reachable.** `calculators/audit.py` scores brand and technical SEO and `marketing_state` decides their state, but nothing calls it — so no user can open either tile. `implemented` and `reachable` are separate flags because of this, and `test_capability_registry` asserts the gap | P16 | M1 | 1 d |
| 🟡 | M20 | **The upload refusal is phrased in KB and the test asserts MB.** `http_limits.py` writes *"over the {limit // 1024} KB limit"*; `test_upload_limits.py` asserts `"25 MB"` is in the detail — and the detail is a dict, so the membership test reads its keys either way. `doc/11` stage 5 says 25 MB, so the message is the half to fix | P8 | none | 0.25 d |
| 🟡 | M21 | **`test_pre_ping_can_be_turned_off_but_defaults_on` reads `pool._pre_ping`**, which is False on the resolved SQLAlchemy. Either the attribute moved or the default did, and the test cannot tell you which — exactly the drift M16's absent lockfile predicts | P1 | M16 | 0.25 d |
| 🟢 | M22 | `test_onboarding_agent_e2e` fails only in a full run, with `ExceptionGroup("multiple unraisable exception warnings")`, and passes alone in ~80s. The asyncpg-transport-on-a-closed-loop shape `test_document_upload_db.py`'s fixture docstring already describes, surfacing as a failure of whichever test ran next. **Do not chase the test name: it moves.** The step-F run blamed `test_a_failed_assembly_stage_does_not_claim_nothing_was_saved`; the slice-1 run blamed `test_a_finished_journey_writes_the_brain_the_facts_and_the_persona`, which then passed 1/1 alone. A name that changes between runs is the diagnostic — a real defect would keep failing on the same test | P9 | none | 0.5 d |
| 🟡 | M15 | Move the embedding pass out of the API process | P9 | C11 | 1.5 d |
| 🟡 | M16 | Pin the dependency set — a lockfile and `pip-sync` in CI | P4 | Finding #16. No lockfile today, so every CI run resolves fresh. Two defects landed from this in Phase 2 alone, and the first hid the second | none | 0.5 d |
| 🟡 | M17 | Send invitations by email | P5 | The inviter copy-pastes a raw token URL. `invitations.issue` returns the token and `build_mailer` exists since P3, so this is a caller and a template — the same gap registration had, and the same fix | none | 0.5 d |

**M2 (preview deletion path) is void, and now actually so** — Phase 2 deleted
`POST /preview` and migration 0011 dropped `preview_session`, so no data about a
company without an account is collected and there is nothing to expire or
delete. **D9 is marked void in `DECISIONS-REQUIRED.md`**, and finding #14 in
`AUDIT-FINDINGS.md` narrows to re-verification alone.

### 🟢 Low — polish

| P | ID | Task | Effort |
|---|---|---|---|
| 🟢 | L1 | Delete the ten dead functions and components, or add the callers they were built for | 0.5 d |
| 🟢 | L2 | Drop or use the dead columns `chunk.is_dept_aggregate`, `document.retention_until`, `audit_log.impersonated_user_id` | 0.5 d |
| 🟢 | L3 | Make `WidgetState.WARMING` / `SELF_REPORTED` reachable, or remove them from both layers | 0.25 d |
| 🟢 | L4 | Link or remove the four orphaned landing sections | 0.25 d |
| 🟢 | L5 | Assert `config.embedding_dim` equals the migration's `EMBEDDING_DIM` | 0.1 d |
| 🟢 | L6 | Use the `pgvector` SQLAlchemy type instead of the string literal in `embed.py` | 0.25 d |
| 🟢 | L8 | Unused component props — use or remove | 0.25 d |

**L7 is done** — the untracked planning documents in `doc/` are committed.

---

## 8. The gate

```powershell
.\scripts\db-ci.ps1 -RunGate
.\scripts\db-ci.ps1
.\scripts\ci.ps1
.\scripts\db-ci.ps1 -Action down
```

`ci.ps1` runs: scripts parse · ruff check · ruff format · mypy strict over `app`
and `tests` · pytest with the coverage floor · tsc · next lint · next build.

**It needs a database.** Without one, `test_a_database_is_configured` fails and
the skip guard names every database test that did not run. That is deliberate —
see ADR 0013.

**It needs `NEXUS_ENV` too**, since Phase 1. `.env` supplies it locally and the
workflow sets it in CI; a missing one is now a startup error rather than a
silent `local` (ADR 0015).

**Stop the web dev server first.** Both it and `next build` write
`apps\web\.next`.

---

## 9. Next

**Phase 4 — The security surface, continued.** Three of five items are done.

**Done and green in CI:**

- **C9.** Login and register rate limited on per-IP *and* per-email counters,
  exponential backoff, an identical 401 in every case — never a 429, which keyed
  by email announces that an address has an account, and never a lock, which is a
  denial-of-service vector against a named user. argon2 runs on a worker thread.
- **H5, the audit trail.** Eight of nine actions write a row inside the same
  transaction as the action. `role_changed` has no writer because the product has
  no way to change a role; it is `UNWIRED` with P17 named, and two tests keep that
  exemption honest. Owner and Executive read it, through the same
  `require_executive_surface` the rest of the executive surface uses.
- **Four of the five named findings** — #3, #9, #10, #11.

**Remaining:**

| Item | Note |
|---|---|
| ~~Session refresh~~ | **Done.** One `UPDATE ... RETURNING` that resolves and refreshes together, extending only once the window is more than half spent |
| ~~Finding #5~~ | **Re-deferred, not skipped.** `validate_url` is synchronous and called from six places including the 89-case SSRF suite; making it `async` ripples through all of them, and `run_in_executor` inside a sync function needs a loop it cannot assume. Its reach shrank in P2 and P4 put a counter in front of the one path that reaches it. Take it with P5's work on those routes |

**Account-level auditing is a gap this phase created and named.** `audit_log` is
workspace-scoped, so registering, verifying an email, resetting a password and
signing in with no membership leave no trail anywhere. It needs its own stream
and is not in any phase's brief yet.