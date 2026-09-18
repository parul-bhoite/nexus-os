# NEXUS OS — Solution Architecture

> A Next.js BFF over a single FastAPI process over one Neon Postgres with forced row-level security. Seven directors read one Company Brain; every number is computed by deterministic Python, and the model is only ever allowed to phrase it.
> **Interactive version:** `nexus-os-architecture.html` — six linked views; hover anything to light everything it touches, `/` to search, `1`–`6` to move between views.
> **Sources:** the repository, read directly — `app/main.py`, `app/routes/`, `app/retrieval/scoped.py`, `app/domain/dashboards.py`, `migrations/versions/`, `app/jobs/scheduler.py`, `apps/web/lib/auth-proxy.ts`, `db/bootstrap.sql`, `docker-compose.yml`, `AZURE-DEPLOYMENT-PLAN.md`.
> **Status:** as-built · **Date:** 18 September 2026 · **Audience:** the delivery team.

---

## 1 · What this is

NEXUS OS is an AI business operating system for companies in Oman and the wider GCC that cannot afford a full executive team. Seven AI directors read one shared Company Brain, and the product's claim is not *"what happened"* but *"what should I do about it"*. The architecture exists to make one sentence structurally true: **the model interprets and phrases; it never produces a number.**

That sentence is the reason for the layering, and almost every other decision falls out of it. Numbers come from `app/calculators/`, which is pure, has no clock, no randomness and no model. Workspace data comes from `app/retrieval/`, whose public callables are forbidden — by a test that walks every signature — from accepting a `user_id`. Authority is a `ScopedSession` resolved server-side per request and passed explicitly, so the model layer physically cannot go around the permission boundary rather than merely being asked not to.

**The one decision that explains the rest of this document** is that scope is never an argument a caller can supply. `scoped_connection` takes resolved authority and has deliberately no `workspace_id` parameter; the value reaches Postgres as a transaction-local GUC, read by a `FORCE ROW LEVEL SECURITY` policy that treats an unset variable as matching nothing. Default-deny is the schema's behaviour, not a code path's discipline.

This document is drawn from the code. Where the code and the repository's own documents disagree, the code wins — a decision taken on 18 September 2026. `ARCHITECTURE-HLD.md` §3 says *"layer 3 is a stub and layer 4 does not exist"*; `app/retrieval/` is eight built modules and `app/agents/` is five stale `.pyc` files. See §10, question 1.

---

## 2 · System shape

Seven bands, in the direction dependency flows. Two deployables — a Next.js app and a FastAPI process — and one database.

**L1 · Presentation** — `apps/web`, Next.js 14 App Router. The browser never reaches the API directly: 72 route files proxy it, forwarding exactly two headers by allowlist. Cross-origin would force `SameSite=None`, and `SameSite=Lax` is the protection the API relies on.

**L2 · Interface** — `services/api`, FastAPI, one process. 15 route modules. This layer decides whether 403 or 404 is the honest answer; a manager reading another department's dashboard gets a 404, and the director list carries no count of what was removed.

**L3 · Scoped data access** — the only path to workspace data.

**L3b · Deterministic maths** — pure. Every figure in the product originates here.

**L4 · Model** — skills as files on disk, not prompts buried in Python. `route → command → skill → LlmProvider`, with the answer validated against the skill's schema and the rest refused.

**IN · Ingestion & integration** — writes normalised read-models into Postgres. The model layer never calls it; that is asserted as an import graph, not by review.

**PL · Platform** — composition, config, the two infrastructure drivers, and the worker entrypoint (the same image as the API, a different command).

| Component | Id | Layer | Status | Responsible for | Depends on |
|---|---|---|---|---|---|
| Web pages | `web-pages` | L1 | Built | Landing, auth, onboarding, dashboard, work, settings | BffProxy |
| BFF proxy | `web-bff` | L1 | Built | 72 proxy routes; keeps the session cookie first-party | ApiBase |
| Routes | `routes` | L2 | Built | 15 modules, ~90 endpoints; the 403-vs-404 decision | scoped_connection · PipelineCalculator · Command · ObjectStore · LlmProvider |
| Auth & tenancy | `auth` | L2 | Built | argon2, sessions, CSRF, invitations, domain claims | Mailer · scoped_connection |
| Health | `health` | L2 | Built | `/health`, `/health/ready`; absence reported as a supported state | ObjectStore · LlmProvider · Embedder · scoped_connection |
| Retrieval | `retrieval` | L3 | **Partial** | The only path to workspace data | scoped_connection |
| Domain | `domain` | L3 | **Partial** | Seven directors as data, departments, scope, membership, brain | scoped_connection |
| Calculators | `calculators` | L3b | **Partial** | Every number, pure and boundary-safe | — |
| Grounding | `grounding` | L3b | Built | Capability→calculator map, pipeline, ledger | PipelineCalculator · scoped_connection |
| AI runtime | `ai-runtime` | L4 | Built | Commands, skill runner, field catalogue, hooks | LlmProvider · SkillManifest |
| Skills | `ai-skills` | L4 | Built | 8 skills, each `SKILL.md` + `manifest.toml` + `schema.json` | — |
| Model boundary | `ai` | L4 | Built | The only package that names the vendor | — |
| Agents | `agents` | L4 | **Removed** | Nothing — sources deleted, `.pyc` only | — |
| Documents | `documents` | IN | **Partial** | Parse, chunk, classify (fails closed), embed | ObjectStore · Embedder · scoped_connection |
| Research | `research` | IN | Built | Crawl a public website behind an SSRF guard | scoped_connection · direct fetch |
| Connectors | `connectors` | IN | **Partial** | OAuth, sealing, revocation — the fetch never runs | OAuth exchange · Transport · SourceAdapter · Session · scoped_connection · direct fetch |
| Embeddings | `embeddings` | IN | Built | The only package naming an embedding library | — |
| Jobs | `jobs` | IN | Built | Three interval jobs, in-process | jobs_session · Embedder · scoped_connection |
| Platform | `platform` | PL | Built | App factory, engine, drivers, middleware, worker | — |

Status reads: **Built** — reachable from a request or a job. **Partial** — some of it runs, some of it does not. **Removed** — source deleted, stale bytecode remains.

---

## 3 · Boundaries

**Inside:** the Next.js app, the FastAPI process, the worker running the same image, and one Neon Postgres reached through two logins.

**Outside:** Anthropic, HubSpot, the open web, public DNS, and — in the target topology — an object store and a mail provider.

**What crosses, and how it is controlled:**

- **Nothing external is trusted as instruction.** Every byte from a crawl, an upload or a connector is data (I7). The wrapper that enforces this, and the action gate behind it, are not built.
- **Untrusted fetches are guarded, not seamed.** The crawl and the DNS check reach the internet over `httpx` directly, behind `ssrf.py` (89 test cases) with redirects off, because a redirect is a second URL nobody validated. This is deliberate — and it means those two reaches have no adapter to swap.
- **The model layer cannot reach a connector.** Asserted as an import graph. A director that called a CRM's MCP server would be *fetching*, and I1 would be gone while every answer stayed plausible.

**What bypasses a boundary, deliberately:**

| Bypass | Why it exists | Consequence |
|---|---|---|
| `direct fetch` — crawler and domain check | The guard is the SSRF module, not a port | No adapter seam; these reaches cannot be substituted in a test or a region |
| `OAuth exchange` — authorise and token swap | Written before the `Transport` seam existed | The working half of the connector is the half with no port |
| `apps/web` has **no** `middleware.ts` | Protection lives in the API, which is the only thing holding data | A signed-out visitor renders the shell skeleton before the 401 handler bounces them |

---

## 4 · Seams and contracts

Seventeen seams across seven groups. The grouping matters: seams provided by a component rather than by infrastructure reach no external service at all, and drawing them into the infrastructure tier would be a lie.

| Contract | Group | Provided by | Adapter | Reaches | Identity |
|---|---|---|---|---|---|
| `LlmProvider` | Infrastructure ports | `ai` | Anthropic · Unavailable · Scripted | Anthropic API | API key |
| `Embedder` | Infrastructure ports | `embeddings` | FastEmbed · Unavailable · Deterministic | fastembed, in-process | none — local model |
| `ObjectStore` | Infrastructure ports | `platform` | FilesystemObjectStore | `.storage/`, *(cloud: none)* | HMAC-signed URL, 300 s |
| `Mailer` | Infrastructure ports | `platform` | FileMailer · SmtpMailer | `.mail/`, *(SMTP: unset)* | SMTP username + password |
| `scoped_connection` | Data access | `retrieval` | `retrieval/scoped.py` | Neon · `nexus_app` | workspace + user, as transaction-local GUCs |
| `jobs_session` | Data access | `platform` | `db.get_jobs_engine` | Neon · `nexus_jobs` | a second database login |
| `Transport` | Connector spine | `connectors` | McpTransport · RestTransport | HubSpot MCP | OAuth bearer |
| `SourceAdapter` | Connector spine | `connectors` | HubSpotDeals | HubSpot MCP | OAuth bearer, Fernet-sealed |
| `Session` | Connector spine | `connectors` | `open_session` | HubSpot MCP | OAuth bearer |
| `OAuth exchange` | **Unported** | *nothing* | `connectors/oauth.py`, httpx | HubSpot OAuth | client id + secret |
| `direct fetch` | **Unported** | *nothing* | `crawler.py`, `domain_check.py` | Customer websites · Public DNS | none — unauthenticated |
| `Command` | Model seams | `ai-runtime` | 6 onboarding commands | *(in-process)* | the caller's ScopedSession |
| `SkillManifest` | Model seams | `ai-skills` | `manifest.toml` + `schema.json` | *(in-process)* | — |
| `PipelineCalculator` | Internal seams | `calculators` | plain functions, structurally | *(in-process)* | — |
| `Row protocols` | Internal seams | `retrieval` | Dispatch · Stocked · Dated · Graded · Supplied · Overdue | *(in-process)* | — |
| `ApiBase` | Process seam | `routes` | `NEXUS_API_BASE_URL` | FastAPI process | the caller's session cookie, forwarded |
| `BffProxy` | Process seam | `web-bff` | `app/api/**/route.ts` | *(in-process)* | browser cookie + double-submit CSRF |

### Seams nobody consumes

Three, all in the connector spine, and together they are one finding rather than three:

- **`Session`** — `open_session` has **zero references anywhere**: application, tests or evals.
- **`SourceAdapter`** — one implementer, `HubSpotDeals`. Its only consumer, `registry.adapter_over()`, is called from a test and from nothing else.
- **`Transport`** — two implementers; `RestTransport` has no consumer outside its test.

The connector spine is complete up to and including the fetch, and the fetch is never executed. A workspace can authorise HubSpot today, the token is sealed with Fernet and a rotatable key id, and **no row will ever arrive**. `crm_deal` exists, is RLS-protected, and has no writer.

### Seams with no driver

- **`ObjectStore`** — five abstract methods, one filesystem implementation. The ABC exists specifically to allow a cloud driver that was never written.
- **`Mailer`** — `SmtpMailer` is written and wired to no provider, and config refuses to start on the file backend outside development.

These two are the deployment blockers, and neither is a redesign.

---

## 5 · External dependencies

| Service | Plane | Used by | Via | Identity |
|---|---|---|---|---|
| Neon · `nexus_app` | Data plane | retrieval, routes, auth, domain, grounding, documents, research, health, jobs | `scoped_connection` | DSN; the role is `NOBYPASSRLS`, asserted fatally at bootstrap |
| Neon · `nexus_jobs` | Data plane | jobs | `jobs_session` | a second login with role-targeted policies on exactly two tables |
| FastAPI process | Own runtime | web-bff | `ApiBase` | the caller's session cookie, forwarded |
| `.storage/` | Local substitute | documents, routes, health | `ObjectStore` | HMAC-signed URL, 300 s TTL |
| `.mail/` | Local substitute | auth | `Mailer` | — (218 `.eml` written to date) |
| fastembed | Local substitute | documents, jobs, health | `Embedder` | none — the model is local, ~2 GB resident |
| Anthropic API | External | ai-runtime, routes, health | `LlmProvider` | API key; **absent is a supported state**, not a degraded one |
| HubSpot OAuth | External | connectors | `OAuth exchange` — no port | client id + secret |
| HubSpot MCP | External | connectors | `Transport` / `SourceAdapter` / `Session` | OAuth bearer — **never actually called** |
| Customer websites | External | research | `direct fetch` — no port | none; SSRF-guarded, redirects off |
| Public DNS | External | connectors | `direct fetch` — no port | none |
| SMTP provider | **Target only** | auth | `Mailer` | unset — D4 |
| Cloud object store | **Target only** | documents | `ObjectStore` | no driver written |

Identity is the line most often left blank in an architecture document, so it is a column here. Two facts in it are load-bearing: the application role cannot bypass row-level security and the bootstrap script raises if it can, and the only credential with real blast radius — a connector's refresh token — is sealed at rest with a key id so it can be rotated.

---

## 6 · The end-to-end journey

Twelve stages. **The product stops dead at nine.**

| # | Stage | What happens | Who | Component | Seams crossed | Leaves behind |
|---|---|---|---|---|---|---|
| 1 | Register | argon2, 12-char floor, a 256-bit token stored only as its SHA-256 | Founder | `auth` | Mailer | an unverified `app_user`, and an `.eml` on disk |
| 2 | Verify & claim | Email, then the domain — DNS TXT, a hosted file, or an address on the company domain | Founder | `auth` | direct fetch | a verified `domain_claim` |
| 3 | Create the company | One company per account; the workspace switch was deleted, not deferred | Founder | `auth` | scoped_connection | a workspace, and a role that resolves to a scope |
| 4 | Be interviewed | Eight phases over three sections; every request takes its stage from the session row | AI runtime | `ai-runtime` | Command · SkillManifest · LlmProvider | `onboarding_turn` rows; answers carrying their questions |
| 5 | Read the site | Queued, drained one run a tick; SSRF-guarded, redirects off | Research | `research` | direct fetch · scoped_connection | `research_source`, `page_signals` |
| 6 | Upload | Parse → chunk → classify; anything that fails becomes L5 and enters review | Founder | `documents` | ObjectStore · scoped_connection | chunks with a scope and a department |
| 7 | Embed | A local 1024d model, five minutes later — the text never leaves to be embedded | Scheduler | `jobs` | Embedder · scoped_connection | `chunk.embedding`, with the provenance the constraint insists on |
| 8 | Assemble | `generated_by = 'answers'` — it invents nothing and names a source for every line | Domain | `domain` | scoped_connection | a versioned brain, every claim traceable |
| 9 | **Connect a tool** | OAuth to HubSpot; authorise, exchange, seal, record the key id | Founder | `connectors` | OAuth exchange · scoped_connection | **a sealed token, and nothing that spends it** |
| 10 | Open the dashboard | One URL for everybody; a department you cannot reach is absent, not greyed out | Routes | `routes` | scoped_connection · PipelineCalculator | a surface composed of what this reader can reach |
| 11 | Compute | Pure calculators; a missing input renders one of seven named states and never a zero | Calculators | `calculators` | PipelineCalculator · Row protocols | a figure, with its working |
| 12 | Narrate | One skill, `narrate-metric`, whose manifest declares `writes = []` | AI runtime | `ai-runtime` | LlmProvider · SkillManifest | a sentence around a number the model did not produce |

**Stage 9 is where the journey breaks.** Everything before it is proved end to end against a real workspace on Neon. Everything after it runs on what the founder typed and what the crawler read — never on what a connected tool would have returned.

**A consequence worth stating plainly:** connecting every source in existence would move the figure-producing capability count from 2 to 2, because the blockers are calculators, not connections. The largest single blocker is the ops layer, which gates 23 tiles and is a feature NEXUS contains rather than anything a customer connects.

---

## 7 · Data and state

One Postgres, 38 live tables across 36 linear migrations, plus three filesystem stores standing in for cloud services.

| Store | Kind | Tables | Row-level security | Written by |
|---|---|---|---|---|
| Tenancy | Postgres | 7 — `tenant`, `app_user`, `workspace`, `membership`, `user_session`, `persona`, `audit_log` | workspace + user GUC | auth, domain |
| Auth & verification | Postgres | 4 — `email_verification`, `domain_claim`, `password_reset`, `rate_limit_counter` | `domain_claim` only | auth, jobs |
| Onboarding | Postgres | 7 — `onboarding_answer`, `invitation`, `onboarding_progress`, `workspace_department`, `onboarding_session`, `onboarding_turn`, `join_request` | workspace + token-hash GUC | routes, ai-runtime |
| Knowledge | Postgres | 2 — `document`, `chunk` | workspace | documents |
| Research & brain | Postgres | 7 — `workspace_url`, `research_run`, `research_source`, `company_brain`, `brain_version`, `fact`, `page_signals` | workspace + worker policies | research, domain |
| Generation | Postgres | 1 — `generation` | workspace | grounding |
| Connectors | Postgres | 2 — `workspace_connection`, `crm_deal` | workspace | connectors |
| Ops | Postgres | 8 — `ops_project`, `ops_task`, `ops_completeness`, `ops_milestone`, `ops_issue`, `ops_dispatch`, `ops_stock_item`, `ops_supplier` | workspace | routes |
| Document bytes | Filesystem | `.storage/ws/<uuid>/documents/` | path by workspace uuid | documents |
| Outbound mail | Filesystem | `.mail/<ts>-<hash>.eml` | — | auth |
| Model cache | Filesystem | `NEXUS_MODEL_CACHE_DIR` | — | embeddings |

**Source of truth.** The row. Nothing here is a projection and nothing is cached — which is also why `cache_key()` exists but has no cache to key yet.

**Three session variables, not one.**

- `nexus.workspace_id` — the tenant boundary, on ~25 tables.
- `nexus.user_id` — person-scoped policies on `membership`, `workspace` and `domain_claim`. These must be readable *before* any workspace is known, which is how a session resolves into one.
- `nexus.invitation_token_hash` — the narrowest. Someone accepting an invitation is in no workspace yet; the policy grants exactly the row whose hash they hold, and the GUC is the hash, so the database never sees the secret.

All four setters use `set_config(..., local=true)`. A session-scoped setting would survive the connection's return to the pool and leak the previous caller's workspace to whoever picked it up next. All four live in one file, consolidated out of ten modules that each used to spell it out.

**Vectors.** One vector column, `chunk.embedding`, 1024 dimensions — the same width as a paid provider on purpose, so moving is a re-embed rather than a schema change. HNSW, cosine, `m=16`, `ef_construction=64`. Plain HNSW gives 5% recall at Contributor selectivity; `hnsw.iterative_scan` is mandatory and **is not yet set in any application query**. `count()` counts through the same permission predicate deliberately — counting everything and subtracting turns a count into an oracle.

**Personal and regulated data.** `app_user` (email, phone), `persona`, uploaded document bytes, and chunk text. Document text never leaves the infrastructure to be embedded, which makes the residency commitment structurally true for that path and not only contractually. `generation.input_snapshot` will be a second copy of customer content and inherits its inputs' scope and retention.

**Written by nothing:** `audit_log` (a policy, no writer — I9 has no trail behind it), `crm_deal` (no fetch runs), and `chunk` is written on every upload and read back by no route.

---

## 8 · Cross-cutting

**Identity.** Session cookie, httponly, `SameSite=Lax`, 12 h; only its SHA-256 is stored. Double-submit CSRF, the second cookie JS-readable on purpose. No `middleware.ts` — nothing gates a page before it renders, and the 401 handler in `AppShell` is the boundary for the four signed-in trees.

**Authorisation.** `ScopedSession` built once per request, never supplied by the client, never in a model context. Role → scope is a frozen mapping asserted row by row rather than scattered conditionals. L1–L5 monotonic; L4 is reachable only by being named on the item, never by role. Capability existence and record existence are separate response types, so *"there are 3 documents you cannot see"* cannot be leaked by accident.

**Tenant isolation.** `FORCE ROW LEVEL SECURITY`, not merely `ENABLE` — migrations run as the table owner, and an owner bypasses an enabled policy. Two logins, neither with `BYPASSRLS`; the isolation suite asserts `rolbypassrls` is false *before* it asserts anything else, because a green suite against a bypassing role would pass while proving nothing.

**Secrets.** `.env` only, in both topologies — there is no secret manager. Fernet for connector tokens with a key id for rotation; HMAC for signed download URLs. `NEXUS_ENV` falls back to `local`, which serves public API docs and sets `secure=False` on both cookies.

**Observability.** structlog JSON, a request id on every line, secret redaction, and a hard refusal to log customer content. One global exception handler; `HTTPException` is deliberately *not* routed through it, because sending a deliberate 403 through a generic 500 would hide the thing the permission tests exist to prove. No metrics, no tracing, no alerting.

**Governance.** `audit_log` exists, has a policy, and is written by nothing. Every generation is meant to carry its inputs; the table landed in migration 0023 and the ledger that writes it is in `grounding/`.

**Asserted as tests, not as review.** No retrieval callable may take a `user_id`. No module outside `app/ai/` may name the model vendor, and none outside `app/embeddings/` may name the embedding library — one such test caught a vendor name in a docstring. The connector spine may not be reachable from the model layer. The gate is ruff, `mypy --strict`, pytest, `tsc`, lint and build in one command: 1,317 backend tests, 146 web tests.

**Delivery.** PowerShell scripts on a Windows developer machine. Six Compose services are defined — `db`, `migrate`, `api`, `worker`, `web`, `proxy` — with migrations already modelled as a job that must exit 0 before `api` and `worker` start. Both Dockerfiles exist. There is no deploy pipeline.

---

## 9 · What is built, what is not

| Area | Status | Evidence |
|---|---|---|
| Tenant isolation | **Proved** | 36 migrations, three GUCs, two roles, a suite that asserts the role cannot bypass before asserting anything else |
| Default-deny classification (I4) | **Proved** | `_withhold` is the single failure outcome; `ck_chunk_l5_has_owner` and `ck_chunk_l3_has_department` put it in the schema |
| Role → scope as data | **Proved** | A frozen mapping asserted row by row |
| Never a zero, never a blank (I10) | **Proved** | Seven render states, tested |
| Auth, tenancy, onboarding | Built | Two real companies, two founders, invitation flow and cross-workspace 404s verified through HTTP |
| Guided onboarding | Built | Eight phases, resumable, verified live against Neon and a configured `claude-sonnet-5` |
| The Company Brain | Built | `generated_by = 'answers'`; assembling is not generating |
| Dashboards | Built, thinly fed | Two capabilities produce a figure; 77 of 89 have no calculator |
| Ops write surface | Built | The only tables a customer writes directly; fails on adoption, not on an API |
| Connector spine | **Half** | OAuth, sealing and revocation work. The fetch is never executed |
| Vector retrieval | **Dormant** | Chunks embedded and indexed on every upload; `retrieval/chunks.py` is eval-only |
| Cloud object store | **Not built** | ABC plus one filesystem driver |
| Mail provider | **Not built** | `SmtpMailer` written, wired to nothing — D4 |
| Audit trail (I9) | **Not built** | Table and policy exist; nothing writes |
| Untrusted-content boundary (I7) | **Not built** | `/evals/injection` is written before it |
| `app/agents/` | **Removed** | Sources deleted; five `.pyc` files, last compiled 20 August |
| Deploy pipeline, TLS, secret manager | **Not built** | — |

**Written, tested, and called by nothing** — these are findings, not omissions, and the interactive version draws each in red:

`connectors/session.open_session` · `connectors/registry.adapter_over` · `connectors/rest.RestTransport` · `retrieval/chunks.py` · `calculators/deltas.py` · `documents/rules.py` · and nine modules under `app/domain/` (`sources`, `capabilities`, `artifacts`, `assembly`, `untrusted`, `group`, `content`, `field_scope`, `membership_removal`).

Two more are invisible rather than dead: `domain/onboarding_commands.py` and `domain/onboarding_hooks.py` are bound by a lazy import inside a getter, so a static import graph cannot see them.

---

## 10 · Open questions

Eight, all raised on 18 September 2026, none of them cosmetic.

| # | Question | Why it matters | Options | Owner |
|---|---|---|---|---|
| 1 | `ARCHITECTURE-HLD` §3 and the code now describe different systems. Which is maintained? | The HLD says layer 3 is a stub and layer 4 does not exist. `retrieval/` is eight built modules; `agents/` is stale bytecode. Anyone reading the HLD is told the opposite of what runs | Regenerate the HLD from the code · Keep it as intent and mark it superseded · Retire it in favour of this document | Parul |
| 2 | When does the connector fetch path get wired, and what calls it? | A workspace can authorise HubSpot today and no row will ever arrive | A scheduler job alongside the other three · On demand from a route · Deliberately after the ops layer | Parul |
| 3 | Is chunk retrieval in scope for the next release, or dormant on purpose? | The embedding cost is paid on every upload and nothing is retrieved | Wire it behind the assistant · Wire it behind the brain · Leave dormant until the assistant exists | Parul |
| 4 | Which object store driver, and who writes it? | Nothing deploys until one exists — blocker one | Azure Blob, per the deployment plan · S3-compatible, per doc 07 §3 · Filesystem on a mounted volume | Parul |
| 5 | Which email provider settles D4? | Verification, invitation and password reset all stop at the boundary — blocker two | Azure Communication Services · A third-party API · A plain SMTP relay | Parul |
| 6 | How does the scheduler survive more than one API instance? | `scheduler.py` says it plainly: every process runs the job. Container Apps scales by default | Worker pinned to one replica · An advisory lock per job · A platform scheduler | Parul |
| 7 | What restores a single origin on Container Apps? | The cookie is `Secure` + `SameSite=Lax`; each Container App gets its own FQDN and the session layer breaks the moment they differ | Front Door or App Gateway over both · Caddy as a third container · Serve the API under the web app's domain | Parul |
| 8 | Six scoreable departments or five — and six directors or seven for a manager? | The composite shows its denominator, so whichever is wrong is wrong in public | Customers becomes its own scoreable department · Fold it into Sales and say five · Drop the composite until it is settled | Parul |

---

## 11 · Risks and consequences

**1 · The connector spine may be solving a problem that arrives differently.** It is complete, typed and tested with no caller, which means its shape has never met a real fetch. The first time `open_session` actually runs, pagination, rate limits, partial failure and incremental sync all arrive at once — and none of them is visible in a path nobody has executed. *Cost of being wrong:* a rewrite of the adapter layer, not of the schema; `crm_deal` and the sealed-credential design survive either way.

**2 · The vector path is a paid-for asset with no consumer.** Every upload is parsed, classified, embedded and HNSW-indexed. `hnsw.iterative_scan` is not set in any application query, and ADR 0012 measured plain HNSW at 5% recall under Contributor selectivity. The first product surface to read a chunk will get answers that look fine and are mostly wrong unless that setting lands with it. *Cost of being wrong:* silent, which is the expensive kind — a recall regression has no symptom a user would report.

**3 · Layer 2's department predicate does not exist.** Row-level security gives tenant and workspace isolation and is proved. It does not give department isolation. Today that is safe because almost nothing reads across departments; it stops being safe the moment a composite, a brief or an assistant reads more than one. The scope columns are already on the row so the predicate can sit inside the plan — but the predicate itself is unwritten. *Cost of being wrong:* a cross-department leak that RLS would not catch and no current test would fail on.

**4 · The session layer does not survive the move to Container Apps unchanged.** `SameSite=Lax` plus two FQDNs is a broken login, not a degraded one, and it will present as "works locally, fails in the cloud" on the first deploy. *Cost of being wrong:* hours, if it is decided before the deploy; a confusing day if it is discovered during one.

**5 · The repository's own status documents have drifted.** `BUILD-STATUS.md` declares itself stale by roughly twenty-two phases, and the HLD describes a layer 4 that was deleted. The risk is not the drift itself but that the documents are still read as current — this one included, six months from now. *Mitigation:* every claim here names the file it came from, so it can be re-derived rather than re-believed.

---

*Generated from the repository on 18 September 2026. Where this document and the code disagree, the code is right and this document is stale — re-derive it from the sources named at the top.*
