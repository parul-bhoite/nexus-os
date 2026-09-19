# NEXUS OS — High-Level Design

**Version:** 1.0 · 25 August 2026 · supersedes `doc/archive/ARCHITECTURE.md`
**Scope:** what the system is, its boundaries, and why it is shaped this way
**Companion:** `ARCHITECTURE-LLD.md` for modules, schema, endpoints and sequences

Legend used throughout: **● built** · **◐ partial** · **○ not built**

---

## 1. System context

```mermaid
graph TB
    subgraph actors[" "]
        V["Visitor<br/>no account"]
        O["Owner / Executive"]
        M["Dept Manager"]
        C["Contributor / Viewer"]
        A["NEXUS internal<br/>support"]
    end

    NX["<b>NEXUS OS</b><br/>seven AI directors over one Company Brain"]

    subgraph ext["External systems"]
        WEB["Customer website<br/>● crawled"]
        GA["GA4 / Search Console<br/>○ M10"]
        CRM["CRM — Zoho or HubSpot<br/>○ M10, D10"]
        DFS["DataForSEO<br/>○ M7, D2"]
        PSI["PageSpeed Insights<br/>○ D3"]
        LLM["Anthropic API<br/>◐ boundary only"]
        MAIL["Email provider<br/>○ D4"]
        DNS["Public DNS<br/>● TXT verification"]
    end

    V -->|"URL → Preview audit"| NX
    O --> NX
    M --> NX
    C --> NX
    A -.->|"time-boxed, logged<br/>○ M13"| NX

    NX -->|"SSRF-guarded, pinned"| WEB
    NX -->|"OAuth, read-only"| GA
    NX -->|"read-model + normalisation"| CRM
    NX --> DFS
    NX --> PSI
    NX -->|"interprets, never computes"| LLM
    NX --> MAIL
    NX --> DNS
```

**The one-line boundary statement:** everything crossing into NEXUS from the right
of this diagram is **untrusted data, never instruction** (I7), and everything
crossing out to a user has passed a permission predicate that was part of the
query, not applied afterwards (I3).

---

## 2. How the specification is read

Precedence, per `VISION-AND-PLAN.md` §7: **VISION-AND-PLAN** (plan) > **doc 07 §2/§8**
(invariants, out-of-scope) > **doc 06** > **doc 05** > **doc 04** > **doc 03/01**.

Conflicts already settled by that rule — recorded so they can be objected to, not
re-litigated:

| # | Conflict | Resolution |
|---|---|---|
| 1 | Doc 03 §1: *"the AI layer never talks directly to source systems"* | Replaced by doc 06 §8.3 — **the AI cannot produce a number and cannot reach data outside the caller's scope.** It reaches data only through scoped tools wrapping the same calculators the pipeline uses |
| 2 | Backend language open (doc 03 §9) | Python 3.12 + FastAPI (doc 07 §3) |
| 3 | Vector schema has no scope columns (doc 03 §2) | Scope fields are **columns on the chunk row**, so the predicate is part of the ANN query |
| 4 | Onboarding: 11 steps / 7 stages / 6 stages | Doc 06 §0, with Pass 1 and Pass 2 questions per §2.5 — **subject to D17** |
| 5 | Data states: four (doc 05 §0) | **Seven** (doc 06 §7.1) |
| 6 | Cross-department interlocks vs allowlists | Scoped calculators (doc 06 §4.13) |
| 7 | Per-person capacity vs k-anonymity | Role-gating (doc 06 §4.14) |
| 8 | Built-in CRM (doc 01 M5) | External CRM read-model + canonical normalisation (doc 05 §0, §9) |

Anything not settled this way is in `DECISIONS-REQUIRED.md`. **Fifteen decisions
are open**; D14, D17, D4, D13 block current work.

---

## 3. The shape of the system

Four layers. The property that matters is that **layer 3 is the only path to
data, and layer 4 cannot reach past it.**

```mermaid
graph TB
    subgraph L1["1 · PRESENTATION — apps/web (Next.js App Router)"]
        direction LR
        L1a["● landing + Preview<br/>● auth + onboarding<br/>◐ dashboards (no widgets)"]
        L1b["○ review gate<br/>○ assistant panel<br/>○ workspace admin"]
    end

    subgraph L2["2 · APPLICATION — services/api (FastAPI)"]
        direction LR
        L2a["● auth · tenancy · RBAC<br/>● ScopedSession construction<br/>● rate limits (public path)"]
        L2b["○ widget resolvers<br/>○ schema validation<br/>○ generation logging · cost · kill switches"]
    end

    subgraph L3["3 · SCOPED DATA ACCESS — retrieval/ · THE ONLY PATH"]
        L3a["◐ scoped_connection sets the GUCs<br/>○ no vector or relational retrieval exists yet<br/>pre-filtered · citations inherit permission"]
    end

    subgraph L3b["3b · DETERMINISTIC MATHS — calculators/"]
        L3c["◐ audit.py only<br/>pure · no IO · no clock · no random<br/>every number originates here"]
    end

    subgraph L4["4 · MODEL — agents/ (Claude Agent SDK)"]
        L4a["○ pipeline · bounded agentic · open agentic<br/>tools constructed PER REQUEST, identity bound<br/>no shell · no connector access · cannot emit a number"]
    end

    CONN["connectors/ — ● crawler · ○ GA4 · ○ GSC · ○ PageSpeed · ○ CRM<br/>write normalised read-models into Postgres. Agents never call them"]
    DB[("PostgreSQL 18.4 + pgvector 0.8.6<br/>● 16 tables · 8 FORCE RLS · 11 policies")]

    L1 --> L2
    L2 --> L3
    L2 --> L3b
    L3 --> L4
    L3b --> L4
    CONN --> DB
    L3 --> DB
```

### Why this shape

The invariants are not features layered on top — they are the reason for the
layering.

- **I1** holds because layer 3b is the only producer of numbers and it contains no model.
- **I2 / I3** hold because layer 3 is the only reader, it takes a `ScopedSession`
  rather than an identity argument, and layer 4 physically cannot bypass it.
- **I8** holds because layer 4 has no shell tool, and `connectors/` lives in layer
  3's dependency graph rather than layer 4's.

**The current gap in one sentence:** layers 1, 2 and 3b exist in part; **layer 3 is
a stub and layer 4 does not exist**, which is why no dashboard shows a number.

---

## 4. The trust model

This is the part of the architecture that is hardest to retrofit, so it is
specified before anything reads data.

### 4.1 The resolved scope set

Everything hangs off one server-computed object. It is never supplied by the
client and never appears in a model context.

```
ScopedSession
├── user_id, workspace_id, tenant_id   ← workspace resolved server-side per request
├── role                                ← from membership, re-validated every request
├── departments      frozenset          ← L3 reach
├── max_scope        L1..L5             ← ceiling
├── contributor_restricted  bool        ← excludes dept aggregates + others' records
├── named_l4_item_ids       frozenset   ← L4 is reachable ONLY by being named
├── is_executive_surface    bool
└── cache_key()                         ← I5: every cache keyed by this, not by tenant
```

Constructed once per request in a FastAPI dependency, passed explicitly into
every retrieval call and every widget resolver. **No function in `retrieval/`
accepts a `user_id`** — a test walks every public callable and fails the build on
an identity argument.

### 4.2 The scope lattice

Five levels, monotonic, plus a separate executive surface.

| Level | Meaning | Reachable by |
|---|---|---|
| **L1** | Company public — material that leaves the company | everyone with a membership |
| **L2** | Company internal | everyone with a membership |
| **L3** | Department | that department's members, per role |
| **L4** | Restricted | **only by being named on the item** — never role-reachable |
| **L5** | Uploader-only | the owner, and nobody else |

L0 is deliberately absent: it is the model's parametric knowledge, never
retrieved content, and therefore never a value on a row.

### 4.3 Role → scope, as data

| Role | L1 | L2 | L3 | L4 | L5 | Executive surface |
|---|---|---|---|---|---|---|
| Owner | ✓ | ✓ | all depts | named only | own | ✓ |
| Executive / GM | ✓ | ✓ | all depts | named only | own | ✓ |
| Department Manager | ✓ | ✓ | **own dept** | named only | own | ✗ |
| Contributor | ✓ | ✓ | **own dept, restricted** | ✗ | own | ✗ |
| Viewer | ✓ | ✓ | **✗** | ✗ | own | ✗ |
| External / Client | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ |

A frozen Python mapping asserted row by row against doc 06 §2.3 — not scattered
conditionals. **●** Built and tested.

> **Consequence, acknowledged rather than discovered:** a Department Manager's
> portal is **six directors, not seven** — no Chief of Staff page, no Morning
> Brief, no composite score. Doc 05 §1's "seven equal directors" is wrong for
> every non-executive user. Tracked as **D6**.

### 4.4 Three enforcement layers, and what each is for

```mermaid
graph LR
    R["Request"] --> API["<b>1 · API layer</b><br/>deps_scope: enforce_department<br/>403 exec-only · 404 wrong dept<br/>● built"]
    API --> RET["<b>2 · Query predicate</b><br/>scope + department in the WHERE<br/>vector AND relational<br/>○ not built"]
    RET --> RLS["<b>3 · Row-level security</b><br/>FORCE RLS on 8 tables<br/>tenant + workspace only<br/>● built and proved"]
    RLS --> DB[("data")]
```

**Each layer catches a different mistake, and none is sufficient alone.** RLS
gives tenant and workspace isolation; it does **not** give department isolation —
that is what layer 2 is for, and it is the layer that does not exist yet. The API
layer is the one that decides whether a 404 or a 403 is the honest answer.

### 4.5 Capability existence vs record existence

Encoded as two distinct response types so it cannot be got wrong by accident:

- **`Locked(capability, required_source, required_role)`** — disclosable, and a call
  to action. *"Requires Finance access."* / *"Connect GA4."*
- **Filtered results** — return nothing. Never counts, never titles, never metadata.
  *"There are 3 documents you cannot see"* is a leak.

The distinction is already honoured at the API layer: a Sales manager asking for
`/dashboards/finance` gets a **404**, and the director list carries no count of
what was removed.

### 4.6 Caches and derived artifacts

- **I5** — generations, health scores, `score_history` and scheduled briefs are keyed
  by `cache_key()`. Without it, *"role changes take effect immediately"* is false
  for every cached surface.

  **Scope-keyed caching stands. The invalidate-on-workspace-switch half of I5 is
  void** (P3, `doc/11` §3.2). Doc 06 §2.1 required a switch to tear down agent
  sessions and drop every scope-keyed cache entry, because one identity could
  hold memberships in several client workspaces and a cache entry crossing that
  boundary would be a tenant leak. A NEXUS account now belongs to **one**
  company: `POST /auth/workspace` is deleted, `_teardown_on_switch` with it, and
  there is no switch to invalidate on.

  What remains is the requirement that actually bites — **role change is still
  immediate** (doc 06 §4.15), and a Contributor promoted to Manager must not be
  served a cache entry computed at the narrower scope, nor the reverse after a
  demotion. That is what `cache_key()` is for, and it is unaffected.

  The membership schema stays many-to-many (`app/domain/membership.py` explains
  why), so if doc 06 §2.1's agency case is ever revived, this paragraph is the
  one to reverse — and the teardown seam will have to come back with it.
- **I6** — an artifact's scope is `max(scope of every input)`, with inputs recorded.
  Declassification is an explicit logged act with a named actor, never a side
  effect of sharing.
- The morning brief is **generated per recipient**, never once and broadcast.

### 4.7 The narrow anonymous surface ○ — ADR 0046

*Added 18 September 2026.* Everything above §4.6 describes callers who have a
`ScopedSession`. There is now one surface that has none, and it is drawn here
rather than left implicit, because the whole value of §4.1–§4.6 is that a reader
can tell from this document what may reach what.

**One module, `app/scan/`, may perform a server-side fetch from a route with no
session** — the pre-signup Instant Gap Analysis scan (`doc/17` Phase 1,
`doc/18`). It fetches **one page** of a domain a visitor typed, scores it with
`calculators/audit.py`, and shows the three highest-cost failed checks.

This is a deliberate, partial reversal of `doc/11` Q1/D18, which had removed the
pre-signup audit from the product. `POST /preview`, `preview_session` and the hero
URL form stay deleted; what comes back is the crawl, narrowed.

**The rule that replaced the old one.** ADR 0016 forbade any anonymous route from
reaching `app.research` at all. That rule named the package that was dangerous in
2026 rather than the property that makes anything dangerous, and the two have since
diverged — `app/connectors/` now holds provider credentials (ADR 0032) and
`app/ai/` a metered key, and neither was covered. The rule is now:

> **No anonymous route may reach a metered or credentialed fetch.**
> Forbidden at any import depth: `app.connectors.*` (except `rate_limit`),
> `app.ai.*`, `app.embeddings.*`, `app.retrieval.*` — it takes a `ScopedSession`,
> so an anonymous route reaching it is a tenancy failure whatever it costs — and
> `app.research.runner` / `app.research.worker_loop`, the budgeted 20-page run
> that belongs to a workspace.

Broader than the old rule in the direction that matters, and strictly weaker about
crawling, which was the old rule's subject. **Two tests, because of that trade:**

| Test | Asserts |
|---|---|
| `tests/test_no_unauthenticated_crawl.py` | the rule above, over every route the app serves, by `ast` walk |
| `tests/test_scan_boundary.py` | an **allowlist** for `app.scan.*` — it may import the SSRF guard, the fetcher, the extractor, the calculators, `page_signals`, config, logging and the rate limiter, and nothing else. Plus: exactly one anonymous route module may reach the crawler, and it is `app.routes.scan`, by name |

An allowlist rather than a denylist for the second, because it fails on things
nobody thought of. The general rule catches the mistake ADR 0016 was written for;
the allowlist catches the mistake this decision creates the room for.

**What crosses the boundary in each direction.**

| Direction | Carries | Never carries |
|---|---|---|
| In | a URL the visitor typed | a session, a cookie, a tenant id, an email |
| Out (to the site) | one GET, SSRF-validated at every redirect hop, capped at 1 page / 1 MB / 10 s / 3 hops | anything authenticated, anything metered |
| Out (to storage) | computed `Check` results and category totals, domain-keyed, 7 days (ADR 0048) | HTML, page text, scraped addresses, a `workspace_id` |
| Out (to the visitor) | up to three failed checks, in the calculator's own words | anything the calculator did not compute (ADR 0047) |

**Three things this surface deliberately does not have**, each because the rest of
the trust model depends on them being scarce:

- **No tenant.** `public_scan` has no `workspace_id`, so no RLS policy can be
  written for it. It is protected by being reachable through exactly one named
  module rather than by the database — a convention, and the second table in the
  system in that position after `domain_claim` (tracked as `H7`).
- **No identity.** No cookie is set and none is read, which is also why CSRF does
  not apply: a cross-site POST here achieves nothing the caller could not do
  directly.
- **No second module.** Two modules with anonymous fetch is not "narrow"; ADR 0046's
  first revisit trigger is a second one being proposed.

The residual risk, stated because there is no mitigation for it: a caller rotating
addresses across many target domains stays under every per-key rate limit while our
user agent touches many third-party sites. The global daily ceiling bounds the load;
nothing bounds the reputational exposure.

---

## 5. The untrusted-content boundary (I7)

Every byte from a crawl, a document, a connector payload or screen context passes
through one function before it can reach a model context.

```mermaid
graph LR
    subgraph src["Untrusted sources"]
        S1["crawled page"]
        S2["uploaded document"]
        S3["CRM field"]
        S4["screen context"]
    end
    S1 & S2 & S3 & S4 --> W["<b>wrap_untrusted()</b><br/>→ UntrustedBlock<br/>labelled delimiter + provenance id"]
    W --> CTX["Model context<br/><i>tainted turn</i>"]
    CTX --> READ["Read / draft<br/>allowed"]
    CTX --> ACT{"External action?<br/>email · WhatsApp<br/>CRM write · publish · share"}
    ACT -->|"taint set"| CONF["<b>Human confirmation</b><br/>showing the exact payload"]
    ACT -->|"clean"| GO["execute"]
    CONF --> GO
```

**Action gating is a hard rule, not a setting.** Read tools and write tools are
separate sets; the assistant defaults to read + draft, and send is a distinct
capability. Screen context gets the same treatment — a tile label may name an
entity the caller cannot open.

**Detection:** provenance logged per context block, instruction-like patterns
flagged, any turn attempting an action inconsistent with its department alerts,
repeatedly-flagged documents quarantined.

**Status ○** — nothing here is built. `/evals/injection` is written before it, in
Phase 9.

---

## 6. Execution modes

Three, not two. A binary split does not survive doc 05's surface.

| | **Pipeline** | **Bounded agentic** | **Open agentic** |
|---|---|---|---|
| Used for | Known input list: traffic trend, SEO table, scores, KPI tiles | Variable retrieval: Morning Brief, Proposal Studio, win/loss, bottleneck | Assistant, department directors |
| Shape | fetch → compute → one model call → schema-validate → render | fixed tool set, capped turns and tokens, schema-validated, cached | full loop, per-user rate limited |
| Audit | one `generation` row | one row + every tool call logged | per-turn logging + session record |

**Guaranteed:** every *number* is code-computed and reproducible. Prose is not
bit-reproducible at any temperature, and the product does not claim it is.

### Agent SDK mapping

- **Pipeline modules are not skills.** They are prompt templates called directly —
  pipeline mode forbids the nondeterministic description-matching that makes a
  skill a skill.
- **Calculators are MCP tools or direct backend calls, never skill-bundled
  scripts.** Skill scripts execute via Bash, and granting Bash voids every
  allowlist (**I8**).
- **Tools are constructed per request** with identity closed over (**I2**).
  Allowlists are a coarse second layer, not the boundary.
- **Subagent returns are filtered against the end user's scope**, not the parent
  agent's. A Finance subagent returning *"margin 34%"* into a Chief of Staff
  context is a leak unless filtered on the return path.
- **Hooks are defence in depth only.** Schema validation, retry and cost accounting
  live in the application layer, because a hook is per-process and any scheduled
  job or retry worker would bypass it.

---

## 7. Render states — never a zero, never a blank (I10)

Seven states. A missing input renders one of them; it never renders `0`, an empty
tile, or an estimate.

| State | Meaning |
|---|---|
| **Live** | All inputs present and fresh |
| **Partial** | Some inputs; scope reduced and labelled — *"4 of 6 scored"* |
| **Locked** | Source not connected; names the unlock and is a call to action |
| **Warming** | Connected, insufficient history — *"available from [date]"* |
| **Self-reported** | Typed by a user; persistently marked; never silently mixed with API-sourced |
| **Stale** | Was Live, source stopped updating — *"was 78, no data for 11 days"* |
| **Unavailable** | Schema validation failed after retry, kill switch, or provider down |

The composite score always shows its denominator — six scoreable departments,
never seven. Chief of Staff and Strategy are synthesis layers and are never
scored.

> **Open discrepancy:** the data carries **five** scoreable directors while the copy
> says six, because doc 05 counts Customers as a scoreable department living
> inside Sales. One of the two must become authoritative — tracked as `M14` in
> `BUILD-STATUS.md`, alongside **D8**.

**Status ◐** — the state machine exists and is tested; two states (`Warming`,
`Self-reported`) are unreachable because no code path produces them, and all 67
tiles currently render a sixth state, `planned` ("Not built yet"), which is
deliberately distinct from `Locked`. *Not built* and *locked* are different
promises and only one of them is true today.

---

## 8. Data architecture

```mermaid
erDiagram
    TENANT ||--o{ WORKSPACE : owns
    WORKSPACE ||--o{ MEMBERSHIP : has
    APP_USER ||--o{ MEMBERSHIP : joins
    WORKSPACE ||--o{ DOMAIN_CLAIM : "verified by"
    WORKSPACE ||--o{ ONBOARDING_ANSWER : "scope-tagged"
    WORKSPACE ||--o{ INVITATION : issues
    WORKSPACE ||--o{ DOCUMENT : stores
    DOCUMENT ||--o{ CHUNK : "parsed into"
    WORKSPACE ||--o{ PERSONA : "per user"
    WORKSPACE ||--o{ AUDIT_LOG : records
    WORKSPACE ||--o{ BRAIN_VERSION : "○ M7"
    BRAIN_VERSION ||--o{ FACT : "○ M7"
    WORKSPACE ||--o{ GENERATION : "○ M8"
    WORKSPACE ||--o{ PROJECT : "○ M11"
    WORKSPACE ||--o{ INTEGRATION : "○ M10"
    WORKSPACE ||--o{ ARTIFACT : "○ M13"
```

**Two tables carry disproportionate weight.** `generation` is what lets any card
answer *"why are you telling me this?"* (I9) — it does not exist yet. `chunk` is
where a classification mistake becomes a permanent silent breach — hence I4
default-deny, which is built and tested.

`generation.input_snapshot` will be a second copy of customer content. It
inherits its inputs' scope tag and retention, and is included in export and
deletion.

**Many-to-many from day one.** `membership` is `(workspace × user × role ×
departments)` with a unique constraint on the pair — the agency case, where one
person works across several client workspaces, is supported by construction
rather than bolted on.

Full schema, constraints, RLS policies and the two known constraint violations
are in `ARCHITECTURE-LLD.md` §4.

---

## 9. Deployment topology

### Today — development only

```mermaid
graph LR
    DEV["Developer machine<br/>Windows + PowerShell 5.1"]
    DEV --> WEB["next dev :3000"]
    DEV --> API["uvicorn :8000<br/>+ in-process APScheduler"]
    WEB -->|"server-side fetch"| API
    API --> NEON[("Neon Postgres 18.4<br/>us-east-2 · pgvector 0.8.6")]
    API --> FS["filesystem<br/>.storage/ · .mail/"]
    DKR["Docker in WSL2<br/>pgvector:pg17 — offline fallback"] -.-> API
```

### Target — Phase 4

```mermaid
graph TB
    U["User"] -->|HTTPS| PX["Reverse proxy<br/>TLS termination<br/><b>○ absent</b>"]
    PX --> WEBC["web container<br/>next standalone<br/><b>○ no Dockerfile</b>"]
    PX --> APIC["api container<br/>uvicorn, non-root<br/><b>○ no Dockerfile</b>"]
    WEBC -->|"BFF, server-side"| APIC
    APIC --> PG[("managed Postgres<br/>+ pgvector")]
    APIC --> S3["S3-compatible<br/>signed URLs only"]
    APIC --> SMTP["email provider · D4"]
    WORKER["embedding + jobs worker<br/><b>○ M15 — today in-process</b>"] --> PG
    MIG["migrations as a deploy step<br/><b>○ absent</b>"] --> PG
    SEC["secret manager<br/><b>○ absent — .env only</b>"] -.-> APIC
```

**Five things stand between here and a deployment**, all in Phase 4: no container
image for either app, no deploy pipeline, no migrations-on-deploy, no TLS, and no
secret management. A sixth is a config default — `NEXUS_ENV` falls back to `local`,
which serves public API docs and sets `secure=False` on both cookies.

### Interface substitution

ADR 0001 replaced each Compose service with a driver behind an interface, so the
production shape survives the local one:

| Production | Local today | Interface |
|---|---|---|
| PostgreSQL + pgvector | Neon (primary) or `pgvector/pgvector:pg17` in WSL2 | `DATABASE_URL` |
| S3-compatible object storage | filesystem under `.storage/` | `ObjectStore` |
| Email | `.eml` files under `.mail/` | `Mailer` — **never instantiated; nothing sends** |

---

## 10. Cross-cutting concerns

| Concern | Position | Status |
|---|---|---|
| **Optional dependencies** | The language model and the embedder are **optional extras**. No key and no model are *supported states*, reported at `/health/ready`, not degraded ones. No provider fabricates output — there is no demo mode, because a hash-derived embedding ranks confidently and shows no symptom | ● |
| **Vendor isolation** | Nothing outside `app/ai/` names the model vendor; nothing outside `app/embeddings/` names the embedding library. Import-graph tests assert both, and one caught a vendor name in a docstring | ● |
| **Observability** | structlog JSON with a request id, secret redaction, and a hard refusal to log customer content | ● logging · ○ metrics, tracing, alerting |
| **Error correlation** | `x-request-id` is issued but dropped on the error path, and there is no global exception handler — every 500 is uncorrelatable | ○ Phase 3 |
| **Auditability** | `audit_log` exists with an RLS policy and is **written by nothing** | ○ Phase 3 |
| **Rate limiting** | Postgres-backed counters per IP, per domain, global daily — on the public path only. `/auth/login` is unbounded | ◐ Phase 3 |
| **Cost control** | Per-tenant and per-user daily token budgets exist in config and are enforced nowhere; per-skill kill switch is declared | ○ Phase 7 |
| **Data residency** | ADR 0003 chose a **local** embedding model so document text never leaves the infrastructure to be embedded — making the residency commitment structurally true for that path, not only contractually | ● |

---

## 11. Architecture decisions of record

| ADR | Decision | Consequence |
|---|---|---|
| 0001 | Native stack, no Docker for the app | Each Compose service became a driver behind an interface |
| 0003 | Local embedding model, 1024d | No per-token cost, no data egress; ~2 GB resident, needs its own worker |
| 0004 | pgvector required from M5, not M0 | Migration 0007 is where absence becomes fatal |
| 0005 | Contributor L3 subset defined | Shipped as a default to revisit with a design partner |
| 0006/0007 | pgvector via Docker Engine in WSL2 | Offline fallback; ~8 s suite vs ~5 min against Neon |
| 0008 | **Neon as the primary database** | RLS proved against the backend that will serve production. Never connect as `neondb_owner` — it has `rolbypassrls` |
| 0010 | All seven directors get a dashboard | Six have real content with nothing connected; Finance is the exception |
| 0011 | **The language model is optional** | No key is a supported state; `anthropic_api_key` bypasses `require()` |
| 0012 | One HNSW index with `iterative_scan` | Plain HNSW gives **5% recall** at Contributor selectivity; `ef_search` does not fix it. **Not yet set in any application query** |
| 0016 | No server-side fetch without a session | **Narrowed by 0046** — the rule is now *metered or credentialed*, not *`app.research`* |
| 0046 | **A narrow anonymous crawl surface** | §4.7. Partially supersedes `doc/11` Q1/D18. One module may fetch anonymously; two tests bound it |
| 0047 | Pre-signup gaps come from the crawl only | The three gaps are the top failed checks of `calculators/audit.py`'s 23. No DataForSEO, no Meta, no new vendor — and a weaker hook, accepted |
| 0048 | Seven-day domain-keyed scan retention | Reopens `doc/11` D9. `public_scan` holds computed check results only: no tenant, no RLS, no page content |

*Rows 0013–0045 are not in this table; it has never been complete. `doc/adr/` is
the record.*

---

## 12. What is deliberately not being built

Business Simulator · Decision Intelligence · Voice · Board Packs · Meta publishing ·
a second CRM connector · accounting integration · Arabic localisation · billing
beyond a trial flag · anything Phase 2 or 3 in doc 05.

**The consequence worth stating plainly:** accounting being out of scope means the
Finance Director has no inputs at all. Doc 05 §5 gates every one of its widgets on
that one connection. **D7** is the choice between shipping Finance as structure
plus named unlocks, bringing accounting in, or allowing manual entry visibly
labelled self-reported — which doc 04 §7 already sanctions.
