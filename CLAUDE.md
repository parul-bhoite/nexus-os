# NEXUS OS — working notes

## Shell — read this before writing any command for the user

The user runs **macOS with zsh**. Commands are copied and pasted, so write
POSIX shell and nothing else. The PowerShell 5.1 rules that used to live here
are archived at the bottom of this section — the repo still carries a
Windows-only `scripts/` tree, and the machine cannot run any of it.

Ordinary POSIX is correct: `&&`, `||`, `export VAR=x`, `VAR=x cmd`,
`rm -rf`, real `curl` with real flags. Four things still worth stating:

| Watch for | Because |
|---|---|
| `cd X && cmd` | Works, but the prompt is already at the repo root — prefer a bare `cmd`, or an absolute path |
| Backslash paths (`scripts\ci.ps1`) | Every path in this file below the Commands section is still Windows-shaped. Translate to `/` before pasting one into a command |
| A `.env` line in a shell block | Still never runnable. Say "add this line to `.env`" |
| `python3` vs the venv | Bare `python3` is Homebrew's 3.14 with no project dependencies. The API's interpreter is `services/api/.venv/bin/python` |

### Nothing in `scripts/` runs on this machine

Every script is `.ps1`, there is **no `.sh` equivalent**, and `pwsh` is not
installed. So the standing advice to "hand over a script rather than a command"
is currently dead: there is no `scripts/ci.sh` to hand over. Until there is,
give the underlying command.

`docker` and `psql` are also absent, which removes two more things this file
recommends:

- **`scripts/db-ci.ps1` cannot build the throwaway gate database.** No Docker.
  Tests run against **Neon**, from `.env` — the slow path, ~5 minutes for the
  onboarding suite, because every statement is a round trip to `us-east-2`.
  That is expected here, not a hang. It also means the drift warning in the
  Neon section applies to every local run, not just to CI.
- **No `psql`.** For a one-off query, use the venv's SQLAlchemy against
  `tests/dburl.database_url()`, and remember `nexus_app` is `NOBYPASSRLS`: a
  query with no `nexus.workspace_id` set returns **zero rows rather than an
  error**, which reads as an empty table. Set it first, or the answer is a
  silent lie.

### What to write instead

```bash
npm run dev --prefix apps/web
```

```bash
services/api/.venv/bin/python -m uvicorn app.main:app --port 8001 --app-dir services/api --reload
```

```bash
services/api/.venv/bin/python -m pytest services/api/tests -q --no-cov
```

**For the whole suite, export the jobs URL first or three tests always fail:**

```bash
export NEXUS_JOBS_DATABASE_URL="$(grep -E '^NEXUS_JOBS_DATABASE_URL=' .env | cut -d= -f2-)" && services/api/.venv/bin/python -m pytest services/api/tests -q
```

```bash
apps/web/node_modules/.bin/tsc --noEmit -p apps/web/tsconfig.json
```

```bash
apps/web/node_modules/.bin/vitest run --root apps/web
```

These were all got wrong on the first attempt, so they are spelled out rather
than shortened:

- **`services/api/tests`, not `tests/`.** pytest is run from the repo root but
  the suite lives under the service. `tests/` there is "file or directory not
  found", collecting nothing and exiting 1 — which looks like a failing run
  rather than a mistyped path.
- **`apps/web/node_modules/.bin/tsc`, not `npx tsc`.** From the root, npx does
  not find the workspace's TypeScript and offers to fetch a different one
  ("This is not the tsc command you are looking for"). `npx` is fine *inside*
  `apps/web`; from the root, call the binary.
- **`--no-cov` on a partial pytest run.** `pyproject.toml` sets a 75% coverage
  gate, so running one file fails on coverage after every test in it passed.
  Leave it off only when running the whole suite.
- **`NEXUS_JOBS_DATABASE_URL` has to be *exported*, not merely present in
  `.env`.** Without it the three `test_domain_claim_isolation` tests that use
  the `nexus_jobs` role fail on `assert JOBS_URL is not None`, so the bare
  command above can never be green on this machine — and it looks like a
  defect in the maintenance role rather than a missing shell variable.

  This is deliberate and must not be "fixed" by adding a `.env` fallback.
  `tests/dburl.jobs_database_url` reads the environment *only*, and its own
  docstring says why: the suites that use it assert what `nexus_jobs`
  **cannot** reach, and silently falling back to `nexus_app` would make every
  one of them pass while proving the opposite. The three tests hard-assert
  rather than skip because ADR 0018 makes the role non-optional.

  It is the inverse of the drift lesson at the bottom of this file — red
  locally, green in CI, for a reason that reads as broken code. Twenty minutes
  were spent on it once.

Prefer the Browser pane's `preview_start` over either server command — the root
`.claude/launch.json` already defines `nexus-web` (:3001) and `nexus-api`
(:8001), and running a dev server through Bash instead is what leaves an
orphaned process holding the port.

### Archived: the PowerShell 5.1 rules

Kept because `scripts/` is still PowerShell and someone will run this on the
Windows machine again. Do not apply these on macOS.

<details>
<summary>PowerShell 5.1 — bash-isms that broke pastes</summary>

| Never write | Write instead |
|---|---|
| `cd X && cmd` | `cd X; cmd` |
| `curl -s URL` | `Invoke-RestMethod URL` (`curl` aliases `Invoke-WebRequest`; bash flags fail) |
| `VAR=x cmd` | `$env:VAR = 'x'; cmd` |
| `export VAR=x` | `$env:VAR = 'x'` |
| `rm -rf X` | `Remove-Item -Recurse -Force X` |

- **Native stderr becomes a terminating error.** `alembic` and `psql` log INFO
  and NOTICE to stderr; with `$ErrorActionPreference='Stop'` that aborts a
  succeeding command. Set `Continue` around the call and branch on
  `$LASTEXITCODE`.
- `&&`, `||`, ternary and `??` do not exist.

</details>

## The documents, and which one to trust

| Document | What it governs |
|---|---|
| `VISION-AND-PLAN.md` | **The build contract.** Vision, invariants, the nine phases and their acceptance tests |
| `doc/09-NEW-APPLICATION-FLOW.md` | **The new flow.** The nine-stage journey. Supersedes doc 06 §0 and doc 04 §5 |
| `doc/11-FLOW-DECISIONS.md` | **Every flow decision Parul has made**, and the four still open. Answers `doc/10` |
| `doc/12-IMPLEMENTATION-PLAN.md` | **The executable plan.** Twenty-two phases, each with an acceptance test. Supersedes `VISION-AND-PLAN.md` §6 |
| `doc/13-DASHBOARD-DESIGN.md` | **The dashboard, settings and agents.** Sections, blocks, states, the day-one surface per department, the settings portal, the tool ledger, and every director as a skill. Shape only — `doc/12` still owns sequence |
| `ARCHITECTURE-HLD.md` | System shape, trust model, untrusted boundary, execution modes, deployment |
| `ARCHITECTURE-LLD.md` | Modules, schema, RLS, endpoint contracts, sequences, failure paths |
| `BUILD-STATUS.md` | Where the code actually stands, with the prioritised work list. Regenerated per phase |
| `DECISIONS-REQUIRED.md` | Open decisions, most of them now external — D3, D10, D13 |
| `AUDIT-FINDINGS.md` | What audits found and what was done about each |
| `doc/01`–`doc/08` | The specification. Read-only |
| `doc/adr/` | Every decision Parul has made |
| `doc/archive/` | Retired: `ARCHITECTURE.md`, `TASKS.md`, `MILESTONE-0…5.md`. Historical only |

## Process

`VISION-AND-PLAN.md` is the build contract. **One phase at a time; stop at the end
of each and wait for validation.**

**A phase is complete when its acceptance test has run green in CI against a real
Postgres, driven through the application rather than around it.** Not when the
code exists, and not when a unit test passes over a monkeypatched write. This rule
replaced the `MILESTONE-N.md` note, which produced six documents that agreed with
each other and disagreed with the database.

Where documents conflict: `VISION-AND-PLAN.md` (plan) > doc 07 §2/§8 (invariants,
out-of-scope) > doc 06 > doc 05 > doc 04 > doc 03/01. Conflicts settled by that
rule are listed in `ARCHITECTURE-HLD.md` §2. Anything not settled by it goes to
`DECISIONS-REQUIRED.md` — **never invent a resolution.**

Every decision the user makes is recorded in `doc/adr/NNNN-title.md`.

## Invariants

The ten in doc 07 §2 are the reason the product exists. `ARCHITECTURE-HLD.md` §3
explains how the layering makes each structurally true rather than policy-true;
`VISION-AND-PLAN.md` §3 tracks which are currently proved. **Four of ten are.**
The two that shape almost every file:

- **I1** — every number is fetched or computed in code. `calculators/` is pure
  and contains no model.
- **I2 / I3** — `retrieval/` is the only path to data, takes a `ScopedSession`,
  and never accepts a `user_id`. The permission predicate is part of the query.

For anything touching permissions or grounding, **write the test that proves the
invariant before the feature it guards** (doc 07 §5.3).

## Database — Neon is the target (ADR 0008)

```
Neon serverless Postgres 18.4    pgvector 0.8.6, direct host (not the pooler)
  app role   nexus_app           NOSUPERUSER NOBYPASSRLS  <- load-bearing for RLS
  .env holds nexus_app only      neondb_owner creds are not in the repo
```

**`neondb_owner` has `rolbypassrls = true`.** Connecting as it would leave every
RLS policy inert while the whole isolation suite kept passing. The app connects
as `nexus_app`; `db/bootstrap.sql` *verifies* both flags are false and raises if
not, because Neon rejects `ALTER ROLE … NOSUPERUSER` outright. Tolerate the
statement, prove the outcome — never assume the ALTER did anything.

`nexus_app` owns every table (that is what makes `FORCE ROW LEVEL SECURITY`
settable). It does **not** need to own the schema.

TLS spelling is per-driver: `.env` carries asyncpg's `ssl=require`;
`tests/dburl.py` rewrites it to libpq's `sslmode=require`. Each driver rejects
the other's spelling. Never add a second `_database_url()` to a test module —
import `database_url()` from `tests/dburl.py`. It resolves the URL **once, at
import**, because `conftest.py` pins `NEXUS_DATABASE_URL` to empty for
hermeticity — so a read at call time falls through to the `.env` fallback, which
exists here and never in CI, and the same code then reads Neon locally and
`None` in CI.

The suite takes **~5 minutes** against Neon versus ~25 seconds against the local
container; every statement is a round trip to `us-east-2`. That is expected, not
a hang.

**The Neon instance was found five migrations ahead of this repository** and has
been reset to its head (D23, 3 September 2026). `alembic_version` read `0014`
against a head of `0009`, with `company_brain`, `question` and `question_choice`
— tables no migration here creates — and a `ck_document_status` that already
permitted `'superseded'`, the value Phase 1 is scheduled to add. Nothing in git,
on any branch, in any stash or worktree produced that schema.

The lesson rather than the incident: **a run against a drifted database can pass
a defect the repository still has, and fail a fix it has made.**
`test_the_schema_is_migrated_to_head` now catches that on every run, and it is
the test that found this. The schema was recorded before the reset in
`doc/archive/neon-schema-before-the-d23-reset.md` — `company_brain` is Phase
13's central table and `question`/`question_choice` are Phase 7's catalogue, so
read it before designing either.

**Neon is at `0025`, which is head** (5 September 2026). `0024` added
`onboarding_session` and `onboarding_turn`; `0025` adds `app_user.phone`,
`membership.designation` and `membership.stated_department`. Both purely additive
— no `DROP` in either — previewed with `--sql` and verified rather than assumed.

**Three columns on `membership` mean three different things, and only two of them
authorise anything.** `role` and `departments` (plural, `text[]`) are the
authorising pair and are set by the inviter. `stated_department` (singular) and
`designation` are what the user typed about themselves at signup; they steer what
the agent asks and what the dashboard leads with, and reach nothing. Never wire
either into a permission check — and note that `persona.department` as a *field
key* fails `assert_persona_is_not_authorisation` at import, by design.

The rule that produced the earlier warnings here still stands and is the reason
to check the preview before running anything: **read `alembic upgrade <cur>:head
--sql` first.** The `0011` incident — a migration that dropped `preview_session`
and therefore destroyed data — is what makes a destructive step the user's to run
rather than an agent's. An additive one, previewed and verified, is not.

**Still prefer `scripts\db-ci.ps1` for the gate.** The container is ~25 seconds
against Neon's ~5 minutes, and it is rebuilt from `bootstrap.sql` every run, so
it cannot drift at all.

**But run against Neon before believing a database claim.** The container and CI
are plain Postgres; production is not. That difference is what hid finding #15
(three of the four timeouts silently discarded by Neon's proxy) through a green
Phase 1.

## Local stack (ADR 0001 native; ADR 0006/0007 Docker for the offline fallback)

**Docker lives inside WSL2 Ubuntu, not on the Windows PATH** (ADR 0007). Never
write a bare `docker …` command — route it through `scripts/lib/docker.ps1`:
`Invoke-Docker` (prints, returns exit code), `Get-DockerOutput` (returns lines),
`Get-DockerContainerHealth`. The daemon does not survive a WSL restart;
`Start-DockerDaemon` handles that.

`winget` is unusable on this machine: Delivery Optimization hangs at 0 bytes
without erroring (three occurrences). Use a direct download and **verify the
Authenticode signature before running an installer** — one 629 MB download
matched Content-Length exactly and still failed with `HashMismatch`.

## Native fallback (ADR 0001)

```
PostgreSQL 17.11   D:\PostgreSQL         loopback only, no service, no admin
  superuser pw     D:\PostgreSQL\superuser.pw
  app role         nexus_app  NOSUPERUSER NOBYPASSRLS   <- load-bearing for RLS
object storage     .storage\              filesystem driver, HMAC-signed URLs
email              .mail\                 .eml files
embeddings         local multilingual-e5-large, 1024d (ADR 0003)
```

`nexus_app` must never be superuser or `BYPASSRLS`: M1's tenant isolation rests
on row-level security, which both silently bypass. Connecting as `postgres`
would make every isolation test pass while proving nothing.

**pgvector 0.8.6 is installed** via the `pgvector/pgvector:pg17` container
(ADR 0006/0007) and reported at every `/health/ready` call. The container's
`nexus_app` role is `NOSUPERUSER NOBYPASSRLS` — the official image makes
`POSTGRES_USER` a superuser, which would bypass RLS entirely, so the app never
connects as it.

## Commands

**None of these run on the current machine** — it is macOS with no `pwsh`, no
Docker and no `psql`. They are kept for the Windows machine. See the Shell
section at the top for what to run here instead; the paths below are Windows-
shaped and the `.ps1` files have no `.sh` equivalents.

```powershell
.\scripts\setup.ps1      # one-time: venv, npm, .env
.\scripts\api.ps1        # the API; add -Reload to watch services\api\app
.\scripts\db-ci.ps1      # the database the gate needs; -RunGate to run ci.ps1 after it
.\scripts\ci.ps1         # the gate: parse, ruff, mypy --strict, pytest, tsc, lint, build
.\scripts\smoke.ps1      # every endpoint, asserting refusals as well as successes
.\scripts\verify.ps1     # gate + health probes, for milestone validation
.\scripts\db-init.ps1 -SuperPassword (Get-Content D:\PostgreSQL\superuser.pw)
```

Web: `npm run dev --prefix apps\web`

**The gate needs a database, and refuses to run without one** (ADR 0013).
Ninety-four tests assert database behaviour; before Phase 0 they skipped and CI
reported green with row-level security never exercised. Now
`tests/test_ci_contract.py` fails when no database is configured, and
`conftest.py` fails the session naming every `requires_db` test that skipped.
`requires_db` is a real marker under `--strict-markers`; the skip decision lives
in exactly one place.

**Use `db-ci.ps1` for the gate, not the URL in `.env`** (ADR 0014). It builds a
throwaway database from the CI image and this repository's own `bootstrap.sql`
and migrations, on port 55432, and points that shell at it without touching
`.env`. `-Action down` removes it. Two reasons it exists: the native cluster has
no pgvector, and the Neon instance in `.env` is five migrations ahead of the
repository (see the Neon section above).

Three WSL traps it works around, each invisible in the failure it produces: a
port published to `127.0.0.1` **inside** WSL is unreachable from Windows, while
`docker exec` connects fine — so the bootstrap succeeds and only the suite fails;
WSL shuts the distribution down when idle, taking the database with it mid-run;
and `pg_ctl start` hangs when its output is piped, because the `postgres` it
spawns inherits the pipeline's stdout handle.

**Stop the web dev server before running `ci.ps1`.** Both write `apps\web\.next`,
and a concurrent `next build` fails with `PageNotFoundError: Cannot find module
for page`. If the dev server itself starts 500ing with `Cannot find module
'./NNN.js'`, the cache is corrupt: stop it, delete `.next`, restart. The source is
fine - that is HMR, not a build error.

## The language model is optional (ADR 0011)

**No API key is a supported state, not a degraded one.** The application starts,
serves everything, and reports `language_model: unconfigured` on `/health/ready`.
To switch it on: set `NEXUS_ANTHROPIC_API_KEY`, then `pip install -e ".[ai]"` in
`services\api`.

Two rules the tests enforce:

- **Nothing outside `app/ai/` names the vendor.** `test_ai_boundary.py` asserts it,
  verified by planting a violating import and watching it fail. Depend on
  `app.ai.contracts.LlmProvider`.
- **Nothing invents content.** `UnavailableProvider` refuses when called;
  `ScriptedProvider` raises on an unscripted skill. There is no demo mode that
  returns plausible analysis - a fabricated recommendation destroys the product's
  central claim whether or not it is labelled, because the label stays on the
  screen and the screenshot does not.

`anthropic_api_key` deliberately bypasses `Settings.require()`. Every other secret
fails loudly when absent; this one must not.

## Semantic search is optional too (ADR 0003 + the ADR 0011 pattern)

**No embedding model is a supported state.** `fastembed` and the ~2GB
`multilingual-e5-large` weights are an optional extra. Without them documents
still upload, parse, classify and reach the review queue; their chunks are stored
with a NULL embedding, which migration 0007's `ck_chunk_embedding_provenance`
permits, and `/health/ready` reports `embeddings: unconfigured`. To switch it on:
`pip install -e ".[embeddings]"` in `servicespi`.

Three rules the tests enforce:

- **Nothing outside `app/embeddings/` names the library.** Depend on
  `app.embeddings.contracts.Embedder`. `test_embedding_boundary.py` asserts it -
  and caught a prose mention of the *other* vendor in a docstring, so the same
  rule applies to comments.
- **Nothing fabricates a vector.** `DeterministicEmbedder` is hash-derived, is
  never returned by the registry, and no setting can select it. This is stricter
  than the LLM rule for a reason: a scripted provider refuses and fails loudly,
  whereas a fake embedding *ranks*. It produces confident citations beside a real
  answer with no visible symptom at all.
- **`embed_documents` and `embed_query` are separate, and not interchangeable.**
  E5 is trained with `passage:` and `query:` prefixes; omitting or swapping them
  does not raise, it just retrieves worse - indistinguishable from the product
  being mediocre.

**Retrieval must set `hnsw.iterative_scan` (ADR 0012).** Measured, not assumed: a
plain HNSW index with the permission predicate as an ordinary `WHERE` returns
**5% recall** at the selectivity of a Contributor reading their own rows. Raising
`ef_search` looks like the fix and is not - it rescues a department-sized filter
and leaves narrow ones broken. Partial indexes per scope are not needed.

The embedding pass runs **in the API process** on a 5-minute interval, which is
fine only while the model is absent by default. Once `[embeddings]` is installed
in production, ~2GB of weights are resident in the process serving requests and
it belongs in a separate worker.

## Known defects

`AUDIT-FINDINGS.md` records what four audits found and what was done about each.
**Three findings are open**, reconciled against `BUILD-STATUS.md` in Phase 2 —
the register had said fourteen for a month after Phase 1 closed three of them.
The three worth knowing before touching auth, the database or deployment:

- ~~**argon2 blocks the event loop**~~ and ~~**`/auth/login` has no rate
  limit**~~ — both **fixed in P4**. The shape is D14's and worth knowing before
  touching either: **never a 429 and never a lock.** A 429 keyed by email
  confirms the address has an account, which undoes account-enumeration
  resistance in the act of adding security; a lock is a denial-of-service vector
  against a named user. Backoff, and an identical 401 whatever the counters say.
- **Never put a GUC in asyncpg's `server_settings` and assume it arrived**
  (finding #15, fixed). That dictionary becomes the connection's startup packet,
  and **Neon's proxy filters it to an allowlist** — `statement_timeout`,
  `lock_timeout` and `idle_in_transaction_session_timeout` were silently dropped
  for months while `application_name`, sent in the same dictionary, arrived. The
  three are now issued with `set_config(name, $n, false)` on the pool's `connect`
  event. `app/db.py` explains why `set_config` rather than `SET`, and why `false`
  rather than `true`.

- **The dependency set is unpinned** (finding #16). There is no lockfile, so CI
  resolves a different environment than any developer every single run. Two
  defects landed from this back to back in Phase 2: `beautifulsoup4` imported and
  never declared — which failed `mypy` on a clean runner and meant **the pytest
  step had not executed in CI since M5** — and an `anyio`/`starlette` deprecation
  that `filterwarnings = ["error"]` turned into nine collection errors. Both
  fixed; the class is not.

The last two are the same shape as the D23 incident below, and worth internalising
as one rule rather than three anecdotes: **an environment that differs from the
one you deploy to can be green in the place nobody deploys to.** It has now been
a drifted database, a proxy that filters GUCs, and an unpinned resolver.

## Content rule

The product sells on *never invent a number*. The landing page and every mock is
held to it too: no invented customers, logos, testimonials or results. Product
mocks carry a visible `Illustrative` tag.
