# doc 18 — The Instant Gap Analysis build plan

**Narrows:** `doc/17` Phase 1 into a sequence.
**Depends on:** ADR 0046 (a narrow anonymous crawl surface), ADR 0047 (the gaps
come from the crawl only), ADR 0048 (seven-day domain-keyed retention). ADR 0045
carries the correction to its own Phase 1 premise; `doc/11` Q1/D18/D9 and §3.1a
carry the two-way links.
**Does not supersede `doc/12`** — that still owns the product's phase numbering.
This is Phase 1's own ordering, and every step is written to `CLAUDE.md`'s rule:
one at a time, and a step is done when its acceptance test has run green against a
real Postgres, driven through the application rather than around it.

**Order is fixed by two rules and they do not bend:** the boundary test is written
and merged **before** the thing it guards (doc 07 §5.3 — *write the test that
proves the invariant before the feature*), and **schema before endpoints before
UI**.

---

## 0. What is being built

One public screen. A visitor types a domain, we fetch **one page** of it, score it
with the calculator that already exists, and show the **three highest-cost failed
checks** in the calculator's own words. Then we ask them to sign up.

```
  /scan                    the form            one field, no email
    │
    ▼  POST /public/scans
  app/scan/                the only module     rate limit → SSRF guard → one fetch
    │                      permitted to        → extract → 23 checks → rank → top 3
    ▼                      fetch anonymously
  public_scan              check results       7 days · domain-keyed · deletable
    │                      only, no page
    ▼                      content
  /scan/{id}               the three gaps      + "delete this result"
```

### What this is not

- **Not `POST /preview` restored.** That endpoint stays deleted and
  `test_the_preview_endpoint_is_gone` still asserts it 404s (ADR 0046).
- **Not a crawl.** One page. `build_preview_audit` takes one `PageSignals`, so a
  second page buys nothing and costs the scanned site a request.
- **Not the wireframe's copy.** All three of its sample gaps are unsourceable
  (ADR 0047), and *"124 pages read"* describes a function we do not have.
- **Not a carry into onboarding.** The stage-2 crawl still runs in full. §6.

---

## 1. What already exists, and is being reused

Nothing in this plan writes a crawler, a guard, a scorer or a ranker. All four
are in the tree.

| Reused | Where | Note |
|---|---|---|
| SSRF guard | `app/research/ssrf.py` | 89 test cases. Already the one exemption in ADR 0016's rule |
| One-page fetch | `app/research/crawler.py:fetch_page` | Already takes `max_bytes`, `timeout_seconds`, `max_redirects` as arguments, so the scan's caps are parameters rather than a fork |
| HTML → signals | `app/research/extract.py:extract_signals` | |
| The signals shape | `app/domain/page_signals.py` | And its `SIGNALS_NOT_STORED` precedent — ADR 0048 rule 1 |
| **23 checks** | `app/calculators/audit.py` | `score_brand` 9 · `score_technical_seo` 9 · `score_performance` 5. Pure, tested, no IO, no model |
| The ranking | `app/domain/brief.py:compose` | Points lost descending, tie-broken by `check_id`. ADR 0029, `doc/14` S3 |
| Rate limiting | `app/connectors/rate_limit.py` | `check_and_increment`, `hash_bucket_key`, `purge_expired`, and the `rate_limit_counter` table — all survived P2 |

**The count is 23, not 27.** Anything downstream that says 27 is wrong; the
figure is derived in G3's test rather than typed anywhere.

### What is being written

`app/scan/` (four modules), `app/routes/scan.py`, migration `0037`,
`app/calculators/gaps.py`, two BFF route files, one page, and three tests that
exist to fail the build.

---

## 2. The boundary, restated

ADR 0046 carries the argument. The shape, because every step below refers to it:

**The general rule** (`tests/test_no_unauthenticated_crawl.py`, rewritten in G0) —
no route that declares no session dependency may reach, at any import depth:

```
app.connectors.*        except rate_limit          credentials, OAuth, provider adapters
app.ai.*                                           metered (ADR 0011)
app.embeddings.*                                   ~2GB of weights
app.retrieval.*                                    takes a ScopedSession — a tenancy failure
app.research.runner
app.research.worker_loop                           the budgeted 20-page run (D20)
```

**The scan's own rule** (`tests/test_scan_boundary.py`, new in G1) — `app.scan.*`
may import **only**:

```
app.scan.*  ·  app.research.ssrf  ·  app.research.crawler  ·  app.research.extract
app.calculators.*  ·  app.domain.page_signals  ·  app.config  ·  app.logging
app.connectors.rate_limit  ·  app.db
```

An allowlist rather than a denylist, because it fails on things nobody thought of.

**The named-route rule** (same file) — exactly one anonymous route module may
reach `app.research.crawler`, and it is `app.routes.scan`, asserted by name.

---

## 3. Decisions taken inside the ADRs, recorded here so a step does not re-open them

| | |
|---|---|
| Pages fetched | **1**, the domain's home page after redirects. `pages_read` is stored, never assumed |
| Caps | 1 page · 3 redirect hops · 1 MB · 10 s total. Separate constants from D20's 20-page / 5-min / 10-min research budget |
| Rate limits | per-IP · per-domain · global daily. All three, because each stops a different abuse (ADR 0046) |
| Gap count | up to 3. Fewer failures shows fewer gaps; zero shows its own state. Never padded, never a zero (I10) |
| Gap wording | `Check.label` verbatim, never negated. Detail is `Check.evidence` — observed, never advice |
| Retained | `Check[]` and category totals. Never HTML, `text_sample`, `PageSignals` or an email address |
| TTL | 7 days, written as `expires_at` at insert, enforced in the read query |
| Deletion | `DELETE /public/scans/{id}`, unauthenticated, soft, rate-limited |
| CSRF | not applicable — no cookie is set and no session is read. Stated in the route docstring so nobody adds one by analogy |

---

## 4. The steps

Each has one acceptance test. Nothing starts until the previous has run green.
**G0 and G1 are test-only and contain no feature.** That is deliberate: the rule
change and the thing it permits must be reviewable separately, or a reviewer sees
a diff that both widens a boundary and walks through it.

### G0 — Rewrite the anonymous-fetch rule ✅ (18 September 2026)

`tests/test_no_unauthenticated_crawl.py` only. Replaced *"no anonymous route may
reach `app.research`"* with the metered-or-credentialed set in §2. Kept the `ast`
walk and `test_the_preview_endpoint_is_gone` unchanged; rewrote the module
docstring, which argued for the old rule.

**What actually happened, corrected against this section's original text (ADR
0046's own Correction, 18 September 2026, has the full account):**

- Grouping by **module** rather than by **route** was itself a latent
  coarseness in the old test, invisible only because nothing legitimate ever
  reached `app.research`. The broadened rule made it visible immediately —
  `read_preferences` (properly `CurrentScope`) shared a file with `/auth/login`
  and got charged with its imports. The walk was rewritten to trace the
  specific endpoint function (and everything it calls, same module or not),
  falling back to the old whole-module check only for a name it cannot resolve
  to a function's own source — a class, a constant, or a module with no
  source file.
- Three pre-existing, already-shipped, already-anonymous features collided
  with the broadened set and needed named, symbol-level exemptions:
  `app.connectors.domain_check` (onboarding's domain-ownership check),
  `app.retrieval.scoped.apply_user_scope`/`apply_workspace_scope` (setting the
  *just-verified* caller's own scope, not reading another tenant's), and
  `app.ai.registry.provider_status`/`app.embeddings.registry.embedder_status`
  (config introspection, ADR 0011). None were anticipated when ADR 0046 named
  `app.connectors.*`/`app.retrieval.*` wholesale.
- **The last acceptance claim in this section's original text was wrong and
  is removed.** Planting `from app.research.crawler import fetch_page` in an
  anonymous route module does **not** fail under G0 alone — verified by hand,
  not assumed. ADR 0046 decision item 2 is explicit that this file no longer
  forbids `app.research.crawler`/`extract` at all; that responsibility is
  entirely `test_scan_boundary.py`'s (G1), which does not exist yet. **Until
  G1 lands, no anonymous route reaching the crawler through a module other
  than the one this plan builds would be caught by anything.** G1 is next for
  exactly this reason — it was already first in the queue, not reprioritised
  by this finding.

**Acceptance, as it actually ran:** `pytest services/api/tests/test_no_unauthenticated_crawl.py`
green, zero test-file-external code changed. Planting
`from app.ai.registry import ...` in an anonymous route module (`app/health.py`,
verified by hand) fails the test; the same in an authenticated route does not.
`ruff`/`mypy` clean on the file.

### G1 — `app/scan/` exists, and is pinned before it does anything ✅ (19 September 2026)

The package, with `budget.py` holding nothing but the caps from §3 as constants
(`MAX_PAGES = 1`, `MAX_REDIRECTS = 3`, `MAX_BYTES = 1_000_000`,
`TIMEOUT_SECONDS = 10` — separate from `app.research.site`'s D20 constants, as
decided), and `tests/test_scan_boundary.py` holding the allowlist and the
named-route assertion from §2. No fetch, no route, no schema — matches plan.

`test_scan_boundary.py` reuses `_import_graph`/`_reachable_from`/`_imports_of`/
`_module_name`/`_anonymous_routes` from `test_no_unauthenticated_crawl.py`
rather than duplicating the AST walk; `tests/__init__.py` already makes `tests`
a real package, so the cross-import is ordinary Python, not a new pattern.

**Acceptance, as it actually ran:** `test_scan_boundary.py` passes (3 tests)
over a package containing only constants. Verified by hand, not assumed:
planting `from app.ai import registry` in `app/scan/budget.py` fails
`test_app_scan_imports_only_the_allowlist`; planting
`from app.research.crawler import fetch_page` in the same file passes. Both
plants reverted before committing. `ruff`/`mypy` clean on `app/scan/` and the
new test file.

### G2 — Migration `0037`: `public_scan` ✅ (19 September 2026)

Head is `0036`. One logical change, reversible, additive. The shape is in ADR 0048
and is not re-decided here. No RLS, and the migration's docstring says why: the
row has no `workspace_id`, so the isolation predicate every other policy uses
cannot be written for it, and an inert policy is worse than a named absence.

```
id · domain · scanned_url · checks jsonb · scores jsonb · pages_read
created_at · expires_at · deleted_at
ix_public_scan__domain_created (domain, created_at DESC)
ix_public_scan__expires_at (expires_at) WHERE deleted_at IS NULL
```

`gen_random_uuid()` server default, following `0031`–`0036`. `timestamptz`
throughout.

**Acceptance, as it actually ran:** previewed with `alembic upgrade 0036:head
--sql` first — one `CREATE TABLE`, two `CREATE INDEX`, no `DROP`, no `ALTER` on
any existing table. Applied against Neon, then `downgrade -1` then
`upgrade head`; `alembic current` confirms `0037 (head)`.
`test_the_schema_is_migrated_to_head` green.
`tests/test_public_scan_schema.py` (4 tests, new): a raw insert naming only
the required columns gets `expires_at` seven days past `created_at` from the
column's own server default, not application code (G7 does not exist yet);
`public_scan` has `relrowsecurity = false` **and** no `workspace_id` or
`tenant_id` column to scope by, so the RLS absence is structural, not an
oversight a later migration could quietly "fix"; the column set is asserted
exactly, so an `ALTER TABLE ADD COLUMN raw_html` would fail this test rather
than silently widening what a tenantless table may hold. `ruff`/`mypy` clean.

**`expires_at`'s default lives in the database, not in this section's
original plan.** `server_default = now() + interval '7 days'`, decided during
implementation so the seven-day TTL is enforced by the schema itself — a
caller cannot forget to set it — and so the acceptance test above could prove
the number without G7's application code existing yet. This narrows ADR
0048's retention decision (which fixed the *value*, seven days) without
reopening it.

> `CLAUDE.md`: read `alembic upgrade <cur>:head --sql` before running anything.
> The `0011` incident is why a destructive step is the user's to run; this one
> was additive, previewed and verified, so it was not.

### G3 — `app/calculators/gaps.py`: the ranker, extracted ✅ (19 September 2026)

Pure, no IO, no model (I1). Takes `tuple[CategoryScore, ...]`, returns failed
checks ranked by points lost descending, tie-broken by `check_id`, and a `top(n)`.
This is the ordering `domain/brief.py:compose` already computes inline.

**Acceptance, as it actually ran:** `tests/test_gaps_ranking.py`, 5 tests.
`test_gaps_rank_matches_brief_compose` builds one `PageSignals`, scores it with
`build_preview_audit`, and asserts `gaps.rank(...)` and `brief.compose(...)`
produce the same check ids in the same order. **One narrowing found while
writing it:** `score_performance` is not wired to a capability id in
`app/grounding/compute.py:CRAWL_AUDITS` — a pre-existing gap in the brief
pipeline, not introduced here — so full parity is proven over the two
categories (`brand`, `technical_seo`) both systems can actually rank, not all
three `build_preview_audit` produces. `test_the_check_count_is_derived_not_typed`
asserts the count is `23`, computed, not typed.
`test_no_literal_check_count_is_hardcoded_in_the_scan_surface` greps
`app/scan/` (and `apps/web/app/scan/`, once G9 creates it) for a bare `23` or
`27` — verified by hand: planting `CHECK_COUNT = 23` in `app/scan/budget.py`
failed it and named the exact line; reverting passed it again. `ruff`/`mypy`
clean.

> Whether `brief.py` is refactored to *call* `gaps.py` rather than be checked
> against it is left open. The parity test is what makes deferring that safe; if
> it is ever deleted, this is two rankings.

### G4 — `app/scan/engine.py`: one page, scored ✅ (19 September 2026)

Validate → `fetch_page` with the scan's caps → `extract_signals` →
`build_preview_audit` → `gaps.top(3)`. Returns `ScanResult`. No route, no
database, no rate limiting — callable from a test and from nothing else.

Failure paths are part of the step: unreachable, timeout, not-HTML, redirect
loop, SSRF-refused all relayed as `ScanRefusedError` carrying `FetchError`'s
own safe reason and `blocked` flag, unmodified. *Page fetched but thin*
(`js_rendered`) is not a failure — `ScanResult(gap_checks=(), js_rendered=True)`.

**A real gap found while building this, not anticipated by ADR 0046 or
`doc/18` §2:** the allowlist never named `app.research.site`, but
`looks_javascript_rendered` (Q51's JS-shell detection) is the one thing G4
legitimately needs from that module, reused rather than reimplemented for the
same reason `gaps.py` was extracted instead of re-ranking independently.
Added to `test_scan_boundary.py`'s `ALLOWED_EXACT`, named and reasoned in a
comment there. **A second, unrelated bug the same test run surfaced:** the
allowlist's own prefix check missed the *bare* package form
(`from app.scan import budget` names both `app.scan.budget` and
`app.scan` — `startswith("app.scan.")` catches only the first). Fixed in the
same edit; verified by hand that a genuinely forbidden bare import
(`from app import ai`) still fails afterward.

**Acceptance, as it actually ran:** `tests/test_scan_engine.py`, 6 tests, DNS
scripted and the transport mocked — the same convention
`test_crawler_redirects.py` already uses, not a socket-bound fixture server.
One page in, ranked gaps out with labels/evidence coming straight from the
calculator; a JS shell yields zero gaps and no error; an SSRF refusal and an
unreachable host both relay `FetchError`'s reason unmodified, and the refusal
never contains the private address it was actually blocking. **The byte-cap
test was rewritten mid-build:** the original design fed a genuine 2 MB
string through `extract_signals`, which hung at ~100% CPU for minutes —
BeautifulSoup/regex on a multi-megabyte single-run string, not a bug in this
change. Rewritten to assert `engine.scan` calls `fetch_page` with
`budget.MAX_BYTES` via monkeypatch instead, since `fetch_page`'s own
truncation is already proven in `test_crawler_redirects.py`; re-proving it
here at 2 MB was slow and redundant, not more correct. `ruff`/`mypy` clean.

**One flaky, unrelated failure surfaced by the full suite, not this change:**
`test_onboarding_agent_e2e.py::test_a_failed_assembly_stage_does_not_claim_nothing_was_saved`
failed once during a ~2-hour full-suite run that overlapped with a manual
onboarding walkthrough exercising the same scripted-model pipeline
concurrently — passed clean in isolation (89s) immediately after. No code
path connects `app/scan/`, `app/calculators/gaps.py` or migration `0037` to
onboarding's assembly stage; treated as environmental, not investigated
further as part of this step.

### G5 — `app/scan/robots.py`: honour the target's `robots.txt` ✅ (19 September 2026, confirmed by Parul before building)

The authenticated crawl fetches a site the workspace has claimed. This one fetches
a site a stranger named, which is a different relationship and arguably a different
obligation. Fetches `/robots.txt` first, honours a `Disallow` for our user agent on
the path, and refuses with an honest message via `ScanRefusedError` (same shape as
every other refusal `app/scan/engine.py` produces).

**Cost:** one extra request per scan and a slower first result. **Benefit:** the
single cheapest answer to an abuse complaint, and the thing we would be asked for
first.

**A real bug found while proving the acceptance test, not a hypothetical one:**
`urllib.robotparser.Entry.applies_to` truncates the useragent string it is *given*
at `can_fetch()` time to the part before its first `/`, then compares that
truncated token against the *entry's* useragent literally, uncut. Passing the full
`USER_AGENT` string (`"NexusOS-Audit/0.1 (+https://nexusos.example/crawler)"`) to
`can_fetch` therefore never matched a `robots.txt` written the normal way —
`User-agent: NexusOS-Audit` — because the entry's full string was never a
substring of the truncated `"nexusos-audit"` token. Verified by hand: the first
version of the disallow test silently passed with everything permitted. Fixed by
introducing `USER_AGENT_TOKEN` (`USER_AGENT.split("/", 1)[0]`) and passing that to
`can_fetch` instead — the bare product token a real `robots.txt` would actually
name.

**Acceptance, as it actually ran:** `tests/test_scan_robots.py`, 4 tests, same
mocked-transport/scripted-DNS convention as `test_crawler_redirects.py` and
`test_scan_engine.py`. A fixture serving `Disallow: /` for our token is refused
and the page path is never requested (asserted on the fixture's own recorded
request list — exactly one request, to `/robots.txt`); a fixture serving no
`robots.txt` (404) scans normally; a `robots.txt` fetch that fails for any reason
(here, DNS not resolving — the same `FetchError` path a timeout takes) does not
block the scan; a `Disallow` on an unrelated path permits the one being scanned.
`ruff`/`mypy` clean; `test_crawler_redirects.py` (18 tests) still green,
unaffected.

### G6 — The anonymous rate limits, and the address they are keyed on ✅ (19 September 2026)

Three buckets in `connectors/rate_limit.py`, beside the existing ones and in the
same style, each with the comment saying which abuse it stops:

```
SCAN_PER_IP       one client hammering the endpoint
SCAN_PER_DOMAIN   many clients pointed at one victim — the reflected-DoS shape
SCAN_GLOBAL_DAILY the ceiling. The only one that bounds the total load we generate
```

IP keyed through `hash_bucket_key` — counting somebody does not require naming
them, and the docstring for that function already says so. Restore
`apps/web/lib/client-address.ts` and `trusted_proxy_ips`, deriving the address
from `request.ip` / `x-real-ip` **only**.

**Acceptance, as it actually ran:** git history had the exact original
implementation (`dc287dd~1`, deleted at P2) — restored rather than reinvented:
`apps/web/lib/client-address.ts`'s `clientAddress()` verbatim,
`app/scan/client_address.py`'s `client_ip()` verbatim (import path updated from
`app.routes.preview`), `trusted_proxy_ips`/`trusted_proxies` in `config.py`
verbatim, and `tests/test_client_ip.py` restored as
`tests/test_scan_client_address.py` (9 tests, all passing unchanged) — it
already covered the exact defect `AUDIT-FINDINGS.md` records, including the
"twenty spoofed headers collapse to one key" case. `tests/test_scan_rate_limits.py`
(5 tests, real Postgres): the *n+1*th request is refused with a computed
`Retry-After`; per-domain refuses a second caller from a different address
pointed at the same domain; `rate_limit_counter` holds no plaintext address,
asserted against the table. New this time, since the original restoration had
no test for it: `apps/web/lib/__tests__/client-address.test.ts` (5 tests) —
`clientAddress()` itself had zero coverage when first written (`8fedbb1`).
`ruff`/`mypy`/`tsc`/`next lint` all clean.

### G7 — `app/scan/store.py` and `app/routes/scan.py` ✅ (19 September 2026)

The store is the **only** module that opens an unscoped connection for
`public_scan` (ADR 0048 rule 2), named so `grep -r public_scan` is short and
reviewable. Read is "freshest row for this domain where `expires_at > now()` and
`deleted_at IS NULL`".

| | | |
|---|---|---|
| `POST` | `/public/scans` | `{ url }` → **201** when crawled (with `Location`), **200** when served from cache, **429** when limited, **422** when the URL is malformed or refused |
| `GET` | `/public/scans/{id}` | **200**, or **404** when expired, deleted or unknown — one code for all three, so the id is not an oracle for whether a domain was ever scanned |
| `DELETE` | `/public/scans/{id}` | **204**, idempotent. Soft (`deleted_at`) |

Errors use the repo's existing envelope. The route declares no session dependency
and says so in its docstring, with the reason CSRF does not apply.

**A real gap found while designing the store, not planned:** the schema had no
way to distinguish a JavaScript-rendered page (`gap_checks=()` because nothing
could be scored) from a genuinely perfect one (`gap_checks=()` because every
check held) — both serialise to an empty `checks` array. Migration `0038`
(additive, reversible) adds `public_scan.js_rendered boolean not null default
false` to carry that distinction; `engine.ScanResult` gained a matching
`category_scores` field so `store.insert` has something to put in the `scores`
column at all.

**Three real bugs found and fixed while proving the acceptance test — not
hypothetical, each caught by actually running it:**

1. **JSONB bind failure.** `store.insert` originally passed raw Python
   `list`/`dict` objects as `text()` bind parameters for `checks`/`scores`.
   asyncpg's JSONB encoder expects an already-encoded string
   (`_jsonb_encoder` calls `str_value.encode()`), so every insert raised
   `'list' object has no attribute 'encode'`. Fixed the way
   `app/domain/onboarding_sessions.py` already does it: `json.dumps()` before
   binding, `CAST(:x AS jsonb)` in the SQL (`::jsonb` would read as a second
   bind parameter to `text()`), `json.loads()` on the way back guarded by
   `isinstance(value, str)`.
2. **Deprecated status constant.** `app/routes/scan.py` used
   `status.HTTP_422_UNPROCESSABLE_ENTITY`, deprecated in this Starlette
   version in favour of `HTTP_422_UNPROCESSABLE_CONTENT` — and this project's
   pytest config turns warnings into errors, so referencing it failed every
   test that hit a 422 path. `app/routes/ops.py` already carries a comment
   explaining exactly this; `app/routes/auth.py` still has the old form
   (pre-existing, out of scope here — not touched).
3. **Test-only: cross-event-loop asyncpg connection.** The rate-limit-refusal
   test originally exhausted `SCAN_PER_DOMAIN` via `anyio.run()` calling the
   real async `check_and_increment` from inside a sync `TestClient` test —
   `anyio.run()` spins its own fresh event loop, separate from the one
   `TestClient`'s engine/pool is bound to, so asyncpg raised "attached to a
   different loop". Rewritten to use a plain sync connection for setup
   (`test_scan_rate_limits.py`'s `consume()` shape), which then needed its
   window-boundary arithmetic to match `_window_start`'s exactly — a first
   attempt using `date_trunc('hour', now())` landed in a different bucket
   than the app's actual epoch-modulo formula (day-aligned for a 24-hour
   window, not hour-aligned) and the route saw an empty bucket.
4. **Test-only: `TestClient`'s fixed peer address pools every test's per-IP
   budget together.** `request.client.host` under `TestClient` is a constant
   ("testclient"), so every test in the file — and every prior run of the
   file within the same real wall-clock hour, since `rate_limit_counter`
   persists in Neon between runs — increments the *same* `SCAN_PER_IP`
   bucket. Running the file twice in a row surfaced it: the second run's
   first test got a 429 unrelated to what it was testing. Fixed with an
   autouse fixture that gives each test a fresh synthetic address
   (`client_address.client_ip` monkeypatched to a random UUID per test),
   the same way each test already uses a fresh random domain for its own
   per-domain budget.

**Acceptance, as it actually ran:** `tests/test_scan_route_e2e.py`, 5 tests,
driven through the real FastAPI app (`TestClient`) against Neon, network
mocked. POST a fixture domain → 201 and a body; POST again → 200 and the
**same** `id`, asserted on the fixture's own recorded request count (unchanged)
rather than by timing; DELETE → 204, twice (idempotent); GET after delete →
404; GET an unknown id → also 404, same code; POST again for the same
(now-deleted) domain → 201 and a **new** id. A malformed url → 422. An
SSRF-refused target → 422, and the domain name does not appear in the response
body. **The one that matters most:** the serialised `checks` payload is
asserted to contain no `@`, no `<`, and none of the fixture page's actual body
text — the `page_signals.py` precedent, applied to a table with weaker
protection. A domain whose `SCAN_PER_DOMAIN` bucket is pre-exhausted is refused
with 429 and a `Retry-After`, without reaching `engine.scan` at all.
`ruff`/`mypy` clean. Full accumulated suite (G0–G7, ~30 tests across nine
files) green.

### G8 — The BFF routes ✅ (19 September 2026)

`apps/web/app/api/public/scans/route.ts` (POST) and
`apps/web/app/api/public/scans/[scanId]/route.ts` (GET, DELETE).

**Two files, not one.** Next.js App Router resolves a route handler per path
segment: a missing `route.ts` is a 404 that neither the Python suite nor the
Vitest suite can see, because one never reaches the web app and the other never
makes a request. Body field-allowlisted, like every other handler.

**`lib/auth-proxy.ts` gained one new, additive capability: `ProxyOptions.headers`.**
Every existing proxy relies on the session cookie; this route has none, and the
API's per-IP limit needs `clientAddress(request)`'s resolved address forwarded
somehow. `upstreamHeaders` now accepts an optional `extra` map, applied after
`Cookie`/`X-CSRF-Token` so a route cannot use it to override either — no
existing call site passes it, so nothing else changed behaviour.
`lib/__tests__/auth-proxy.test.ts` (10 tests) still green, unaffected.

**Acceptance, as it actually ran:** `e2e/scan.spec.ts` (Playwright, `request`
fixture — no browser page), driven against the real running dev server and
API (not `proxyToApi` in isolation, not mocked), scanning the real
IANA-reserved `example.com`: POST → 200/201 with an `id` and a `checks` array;
GET that id → 200, same id; DELETE → 204; GET after delete → 404; GET an
unknown id → 404. **Verified by hand, not assumed:** moved
`[scanId]/route.ts` aside and reran — the GET assertion failed with a real 404
where 200 was expected, exactly as the acceptance criterion requires; restored
and reran clean. `tsc`/`next lint` clean on both new route files and the
`auth-proxy.ts` change.

### G9 — `/scan`: the form and the three gaps ✅ (19 September 2026)

One field, no email. Shipped token system (ink/bone/gold/steel/clay, Tailwind),
**not** the wireframe's cream/terracotta — `doc/17` is explicit that the CSS is
not adopted. `lib/scan-client.ts` mirrors `auth-client.ts`'s `post`/`AuthError`
shape (`ScanError`, carrying `retryAfterSeconds` for the limited state).

**A fifth state, not named in this section's original plan.** The four listed
here — findings, all held, refused, limited — miss the one G7 found designing
the store: a JavaScript-rendered page (Q51) also has an empty `checks` array,
identical to "all held" unless `js_rendered` is checked. `ScanForm` renders it
as its own message, distinct from "every check held", using the field
migration `0038` added for exactly this.

The footer states the two things ADR 0048 put on a public page: results are
cached for seven days, and there is a control to delete this one. Both are
static policy text, not values the response computed — deliberately excluded
from the "no invented number" check below, which is about *derived* figures.

**Acceptance, as it actually ran:** `tsc`/`next lint` clean.
`components/scan/__tests__/ScanForm.test.tsx`, 6 tests (Vitest + RTL): all
five states render with distinct, correct copy; `pages_read` renders as what
the API sent and "page"/"pages" is not hard-coded. **The numeral-provenance
test needed rescoping once run for real:** grepping the whole rendered
document caught the footer's static "7 days", which is policy text, not a
derived figure — narrowed to the findings container specifically
(`data-testid="scan-findings"`), matching this section's own words ("the
findings state"). **Verified live, not only under test:** scanned the real
`example.com` through the running dev server + API — three genuine, correct
gaps rendered (no contact info found, empty meta description, 21 words of
body copy) — then deleted the result through the UI and confirmed the
"deleted" state. Zero console errors.

> Drive this with DOM clicks and React's native value setter when testing through
> the browser pane; injected input events do not reach React.

### G10 — The landing-page entry point ✅ (19 September 2026)

A `Button variant="quiet"` link to `/scan` under the hero's existing two buttons
and note — not a field, and not the retired hero URL form
(`components/sections/Hero.tsx`'s old form and `components/preview/`, deleted
at `doc/11` §3.1). Sign-up (`/register`) stays the one primary action; `quiet`
is the variant this design system already reserves for "reachable, must not
compete" (`components/ui/Button.tsx`'s own comment on it).

**Acceptance, as it actually ran:** `headings.test.tsx` and the full Vitest
suite (30 files, 253 tests) green — one earlier run failed with an `ENOENT`
on `nexus-os/app/dashboard` (missing the `apps/web/` segment), traced to
running `vitest --root apps/web` from the wrong working directory, unrelated
to this change; rerun from `apps/web/` passed clean. `tsc`/`next lint` clean.
**Verified live:** the link renders below the fold (as intended — it does not
compete above it), and clicking it in the running browser navigates to
`/scan`.

### G11 — `jobs/expiry.py:expire_public_scans` and its schedule ✅ (19 September 2026)

`expire_previews` was deleted in P2. This is its replacement and it is **not**
optional: without it, the read query keeps returning nothing while the table grows
forever, which is a silent failure in the direction that looks fine.

Hard-deletes rows past `expires_at` and soft-deleted rows past a short grace.
Registered in `jobs/scheduler.py` in the same commit.

**Acceptance:** against a real Postgres, a row with `expires_at` in the past is
hard-deleted by one sweep and a live row is not. **And the sweep is asserted to be
registered** — a test reading the scheduler's registry, not the sweep function.
An unregistered sweep is the defect, and a test of the function alone cannot see
it.

**Acceptance, as it actually ran:** `expire_public_scans(db, *, now=None)` added
to `app/jobs/expiry.py` — hard-deletes `public_scan` rows where `expires_at <=
now` OR (`deleted_at IS NOT NULL AND deleted_at <= now - PUBLIC_SCAN_DELETE_GRACE`),
`PUBLIC_SCAN_DELETE_GRACE = timedelta(days=1)`. Wired into the existing
`run_expiry_sweep`, which already ran on scheduler job id `"expiry_sweep"` —
**no new job registration was needed**, since reusing the existing job id means
`test_scheduler.py::test_the_expiry_sweep_is_registered` (pre-existing, unchanged)
already covers the "asserted to be registered" half of this step's acceptance
criterion. `ExpiryReport` gained a `public_scans_expired: int` field; confirmed by
grep that nothing else constructs `ExpiryReport` positionally in a way the new
field would break.

Four new tests in `tests/test_expiry.py`, run against real Neon (not the CI
container): a row past `expires_at` is hard-deleted; a live row (future
`expires_at`, not soft-deleted) survives; a soft-deleted row past the one-day
grace is hard-deleted; a soft-deleted row still inside the grace survives. A
fifth test drives the real `expire_public_scans` function itself (not a second
copy of its SQL) against a real async session, per the same principle
`test_rate_limit.py` states its own module docstring for. All 7 tests in the file
(including the two pre-existing domain-claim tests) passed clean; `ruff` and
`mypy` clean on both `app/jobs/expiry.py` and `tests/test_expiry.py`.

One correction made in passing: the module docstring's inherited claim that "D9
is void" was narrowed — ADR 0046/0048 reopened a scoped version of D9 for
`public_scan`, so the docstring now says so instead of repeating a premise this
step falsifies.

G0–G11, the full original build plan, is now complete.

---

## 5. What each step needs from whom

| Step | Agent | Blocked by |
|---|---|---|
| G0, G1 | backend | — |
| G2 | backend (schema) | G1 |
| G3 | backend | G2 |
| G4 | backend | G3 |
| G5 | backend | G4, **and a confirmation from Parul** |
| G6 | backend + web (the address helper) | G4 |
| G7 | backend (API contract) | G2, G4, G6 |
| G8 | web (BFF) | G7 |
| G9, G10 | web (UI) | G8 |
| G11 | backend (jobs) | G2 |

G6 and G5 are independent of each other and could run in either order; everything
else is a chain.

---

## 6. Deferred, and named rather than forgotten

**Carry the scan into onboarding.** The wireframe's *"we won't ask twice"*. ADR
0048 stores check results, not `PageSignals`, so the stage-2 crawl runs in full
regardless — the row cannot seed it. Making it seed onboarding means storing the
signals, which is the option ADR 0048 rejected and would need a new ADR. Until
then the copy stays off the screen.

**Multi-page scanning.** `build_preview_audit` scores one page. A multi-page
anonymous scan needs a calculator that does not exist (ADR 0047), and would
multiply the load we generate against a site that did not ask for it.

**Anything metered.** DataForSEO (D2), PageSpeed (D3), a language model. ADR 0046's
rule forbids all three on this path structurally, and G0's test is what makes the
forbidding real rather than remembered.

**A published crawler policy page.** A `User-Agent` string already points at
`https://nexusos.example/crawler`, which does not resolve. If G5 ships, this is
the natural companion and it belongs with `doc/17` Phase 3's legal work.

---

## 7. Risks

Carried from the ADRs so they are visible in the plan someone builds from.

| Risk | Mitigation | Residual |
|---|---|---|
| An unauthenticated server-side fetch is back | SSRF guard (89 cases), three rate-limit buckets, two boundary tests | **Real.** A caller rotating addresses across many target domains stays under every per-key limit while our UA touches many sites. The global ceiling bounds the load; nothing bounds the reputational exposure |
| The boundary rule got weaker about crawling | `test_scan_boundary.py`'s allowlist is stricter than the rule it sits under | The two tests can drift apart and the build stays green over the gap. Held by convention, not structure |
| `X-Forwarded-For` defect returns | G6's acceptance test asserts a browser-supplied header lands in the same bucket | Low, and only if that assertion is dropped |
| Third-party data retained without consent | 7 days, no page content, a deletion control | **No mitigation** for the fact the domain owner will usually never know the row existed. This is the finding a data-protection review would land on |
| The three gaps are trivial and the hook is weak | Presentation: the weight, the ranking, what a check is worth | **No mitigation.** ADR 0047 trades conversion for truthfulness knowingly; the copy must not oversell what the ranking returns |
| A scan is domain-keyed, so one visitor may see another's result | Intended — it is what bounds the fetching | The screen must not imply the result is private to whoever asked |
| `ARCHITECTURE-LLD.md` is stale | §8 below | It documents migrations `0001–0009` against a head of `0036`, and `POST /preview` as *"the one complete flow"*. Anyone reading it to plan this work will be misled on both |

---

## 8. A note on the LLD

`ARCHITECTURE-LLD.md` says it is *"reconciled against the working tree, not against
intent"*. It is not, currently. §4.1's migration chain stops at `0009` against a
head of `0036`; §1's repository layout still shows `connectors/ ssrf · crawler ·
extract` and `routes/ … preview`; §5.1 lists `POST /preview` as *"the most complete
endpoint"*; §6.1 diagrams the preview flow as *"the one complete flow ●"*.

This plan's edits to that file are **targeted additions plus dated correction
notes** at each of those four places — not a rewrite, which is its own piece of
work and should not be smuggled into a feature. Anyone building from §6.1's
diagram will otherwise reimplement the endpoint ADR 0046 explicitly does not
restore, because the new flow looks very like the old one.
