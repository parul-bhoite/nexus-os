# 0001. Deploy on Railway as two services over public URLs, against the existing Neon

- **Status:** Accepted
- **Date:** 2026-10-09
- **Deciders:** @parul-bhoite

## Context

The product needed a live, shareable deployment. A Railway project
(`confident-expression`) was already created and the `parul-bhoite/nexus-os`
repository connected, but its first build failed: Railway's auto-builder ran at
the repo root and this is a monorepo with two deployable apps, each with its own
Dockerfile:

- `services/api` — FastAPI, listens on `:8000` (uvicorn `--host 0.0.0.0`, IPv4 only)
- `apps/web` — Next.js standalone, listens on `$PORT`; it calls the API
  **server-side** through `lib/auth-proxy.ts` using `NEXUS_API_BASE_URL` (there is
  no browser→API cross-origin traffic, and no CORS middleware in `app/main.py`)

Constraints that shaped the choices:

- The app requires Postgres **with pgvector 0.8.6**. The team already runs a Neon
  instance that is migrated to head and holds the working data (see the Neon
  section of `nexus-os/CLAUDE.md`).
- `app/config.py` refuses to boot a deployed `NEXUS_ENV` (`staging`/`production`)
  without a strict secret set, an `https` `NEXUS_PUBLIC_BASE_URL`, a real SMTP
  mailer, and `NEXUS_JOBS_DATABASE_URL`.
- Railway's GitHub App was **not** connected (the repo is linked by URL), so branch
  listing, webhooks and auto-deploy were unavailable during setup.
- Railway's deploy-time security gate **blocks** images with known HIGH-severity
  CVEs; `next@14.2.18` tripped it (CVE-2025-55184, CVE-2025-67779).

## Options considered

### Database

- **A. Reuse the existing Neon Postgres.** pgvector already present, schema at head,
  data present — the app boots immediately.
- **B. Provision a new Railway Postgres.** Empty; pgvector and every migration must
  be applied before the app works; more setup and risk.

### Service-to-service networking

- **C. Web → API over each service's public `*.up.railway.app` URL.** No code
  change; traffic is TLS over the public edge.
- **D. Web → API over Railway private networking (`*.railway.internal`).** Lower
  latency/no egress, but private networking requires the server to listen on IPv6
  (`::`); the API's uvicorn binds `0.0.0.0` (IPv4 only), so this needs a Dockerfile
  change.

### Deployed environment value

- **E. `NEXUS_ENV=staging`** — deployed-grade (secure cookies, `/docs` disabled),
  appropriate for a non-production demo.
- **F. `NEXUS_ENV=production`** — identical validator requirements; no benefit here.
- **G. `NEXUS_ENV=local`** — boots with minimal config but disables secure cookies
  and serves `/docs` publicly (ADR 0015 footgun).

## Decision

- Two Railway services, each built from its subdirectory's Dockerfile
  (`services/api` → API, `apps/web` → web).
- **Database: Option A** — reuse the existing Neon Postgres via
  `NEXUS_DATABASE_URL` / `NEXUS_JOBS_DATABASE_URL`.
- **Networking: Option C** — web reaches the API via its public URL
  (`NEXUS_API_BASE_URL`); `NEXUS_PUBLIC_BASE_URL` on the API points at the web
  service's public URL (verification/reset links are built from it).
- **Environment: Option E** — `NEXUS_ENV=staging`, SMTP mailer (Gmail), filesystem
  storage backend (inherited from `.env`).

## Reasoning

**Neon (A over B)** was decisive on pgvector and data: a fresh Railway Postgres
would be empty and would need the extension plus every migration before the product
did anything, for no benefit at demo stage. The cost accepted is that the
deployment depends on an external database the Railway project does not own.

**Public URLs (C over D)** were chosen to avoid a code change on the critical path
to "live". Private networking is objectively better (no public egress, lower
latency) but is gated on the API listening on IPv6; `--host 0.0.0.0` does not, and
changing the API's start command was out of scope for getting a first link up.
Because the web talks to the API only server-side, the public hop is still
server-to-server over TLS, not browser-exposed.

**`staging` (E)** gives deployed-grade security (Secure cookies, `/docs` off) with
the same requirements as `production` but without implying this is the production
system; `local` was rejected outright because it disables cookie security over the
public internet.

Two deploy-blocking fixes were required and landed via PR (merge commits, to keep
release-please history): install the optional `anthropic` SDK in the API image
(the base install uses `--no-deps`, so the `[ai]` extra was absent), and upgrade
`next` to `14.2.35` to clear Railway's CVE gate. A `main` branch was created from
`dev` so the web service (which Railway pinned to `main`) builds the same code as
the API (which tracks `dev`).

## Consequences

- The app is live with no database migration step and immediate access to existing
  data.
- Web→API latency includes a public round trip and counts against egress; fine at
  demo scale, worth revisiting under load.
- **Auto-deploy is off.** With no GitHub App/webhook, pushes do not redeploy; a new
  commit requires reconnecting the source or recreating the service. The branch
  selector also cannot be changed in the UI.
- **Two branches to keep in sync** (`dev` for API, `main` for web) until the web
  service can be pointed at `dev`.
- **Filesystem storage is ephemeral on Railway** — uploaded files do not survive a
  restart or redeploy. Acceptable for a demo; not for real document workloads.
- A dead `meticulous-magic` service remains (first web attempt, pre-Next-fix); it
  can be deleted from the Railway UI.

## Revisit trigger

Reopen when any of these becomes true:

- The deployment moves beyond demo/staging toward real use → switch web→API to
  private networking (change the API to `--host ::`), move storage off the
  ephemeral filesystem (Railway Volume or object storage), and reconsider `staging`
  vs `production`.
- The GitHub App is connected → collapse to a single deploy branch, enable
  auto-deploy, and this ADR's two-branch and manual-redeploy consequences no longer
  apply.
- The team wants the database owned alongside the app (cost, data residency, or
  removing the external dependency) → reconsider Option B.
