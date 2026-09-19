# 0046. A narrow anonymous surface may crawl, and may reach nothing metered

- **Status:** Accepted
- **Date:** 2026-09-18
- **Deciders:** Parul
- **Supersedes:** the pre-signup-crawl portion of `doc/11-FLOW-DECISIONS.md` Q1 / D18,
  and narrows ADR 0016
- **Affects:** `ARCHITECTURE-HLD.md` §4.7, `ARCHITECTURE-LLD.md` §5.5,
  `doc/18-GAP-ANALYSIS-BUILD-PLAN.md`

## Context

`doc/17-WIREFRAME-ADOPTION-PLAN.md` Phase 1 — the Instant Gap Analysis scanner —
is a pre-signup, no-login website scan on the marketing site. ADR 0045 phased it
first on the stated premise that it "contradicts nothing" and has "no conflict".
That premise is wrong, and this ADR exists because of what it collides with:

1. **`doc/11` Q1 / D18** removed the pre-signup Preview audit from the product
   outright: *"No URL capture on the landing page. The pre-signup Preview audit is
   removed from the product."*
2. **`doc/12` Phase 2** executed that: `app/routes/preview.py`, the hero URL form,
   `preview_session` (migration `0011`), the IP and domain rate-limit buckets and
   `apps/web/lib/client-address.ts` were all deleted.
3. **ADR 0016** replaced the deleted endpoint's test with a structural one,
   `services/api/tests/test_no_unauthenticated_crawl.py`, whose rule is absolute:
   *a route that does not require an authenticated session must not be able to
   reach `app.research`* — checked by an `ast` walk over the import graph, at any
   depth, with `app.research.ssrf` the single narrow exemption because it is the
   guard rather than the fetch.

So Phase 1 as written cannot be built. It needs a route that crawls and has no
session, and that route is exactly what (3) fails the build on.

The reason behind (1) and (3) is still correct and is not in dispute. Doc 06 §1.2:
*"metered APIs must never sit on an unauthenticated path... Without this, a script
exhausts a paid quota and degrades the product for paying tenants."* ADR 0016's
own framing is the sharper one: the dangerous version is not a route that crawls
on purpose, it is a helper imported for one innocent function that drags the
crawler in behind it.

What is in dispute is the *scope* of the rule. ADR 0016 forbids the whole
`app/research` package from an anonymous path. But the package holds two
different kinds of thing: a first-party HTTP GET of a page the visitor named,
which costs us bandwidth and nothing else, and the budgeted 20-page research run
(`research/runner.py`, `research/worker_loop.py`) that feeds a workspace. Neither
is metered today, and neither holds a credential — but the connectors do
(`connectors/credentials.py`, `connectors/oauth.py`, `connectors/hubspot.py`),
the language model does (`app/ai/`, ADR 0011), and DataForSEO would if D2 ever
closed. The rule names the package that happens to be dangerous today rather than
the property that makes anything dangerous.

**The tension, stated plainly:** the funnel wants first value before signup, and
the trust model wants no unauthenticated server-side fetch. `doc/11` §3.1 already
recorded the cost of resolving it the other way: *"the audit was the product's
first-value moment at minute seven. With it gone, the review gate at ~minute
twenty is the only first-value moment."*

## Options considered

### A. Leave Q1/D18 and ADR 0016 as they are; drop Phase 1
No new exposure, no new code, and the trust boundary stays a single sentence
anyone can hold in their head. Costs the first-value moment `doc/11` §3.1 already
named as the price of the last decision, and makes ADR 0045's Phase 1 undeliverable.

### B. Reverse Q1/D18 — restore `POST /preview` as it was
Fastest to describe, and wrong. It brings back the whole retired surface —
`preview_session` with its third-party retention obligation, the deleted rate
limit buckets, the `X-Forwarded-For` trust chain — and it deletes ADR 0016's test
rather than replacing it, leaving nothing structural in its place.

### C. Put the scan behind signup
Keeps every rule intact. But a scan behind signup is not a scan; it is the
onboarding crawl that already exists at stage 2 (`doc/11` Q12/Q13), and building
a second copy of it with a marketing page in front achieves nothing.

### D. A narrow anonymous surface, with the rule re-cut around the property that matters
One named module, `app/scan/`, is permitted to fetch. The absolute rule
*"no anonymous route may reach `app.research`"* becomes *"no anonymous route may
reach a metered or credentialed fetch"*, and `app/scan/` gets a second, tighter
test of its own: an allowlist of everything it may import, so it cannot grow into
anything else.

## Decision

Option D.

**The anonymous path exists, it is one module wide, and it is bounded by two
tests rather than by one.**

1. `services/api/app/scan/` is the only package that may perform a fetch from an
   anonymous route. It carries its own budget and caps, separate from D20's
   20-page research budget.
2. `tests/test_no_unauthenticated_crawl.py`'s rule is rewritten. The forbidden set
   is no longer `app.research` but **metered or credentialed**: `app.connectors.*`
   (credentials, OAuth, provider adapters), `app.ai.*`, `app.embeddings.*`,
   `app.retrieval.*` (it takes a `ScopedSession`, so an anonymous route reaching it
   is a tenancy failure whatever it costs), and `app.research.runner` /
   `app.research.worker_loop` (the budgeted run belongs to a workspace).
3. A new test, `tests/test_scan_boundary.py`, states the **allowlist** for
   `app.scan.*`: `app.research.ssrf`, `app.research.crawler`,
   `app.research.extract`, `app.calculators.*`, `app.domain.page_signals`,
   `app.config`, `app.logging`, `app.connectors.rate_limit`, and `app.scan.*`
   itself. Anything else fails the build.
4. A third assertion names the one anonymous route module permitted to reach
   `app.research.crawler` — `app.routes.scan` — by name, so a second anonymous
   crawl path cannot appear without editing a test that says what it is doing.
5. `test_the_preview_endpoint_is_gone` stays exactly as written. The new surface
   is `/public/scans`, not `/preview`, and the retired endpoint stays retired.

**This is a partial reversal of Q1/D18, not a full one.** What comes back is one
anonymous crawl of the domain the visitor typed. What does not come back:
`POST /preview`, `preview_session`, `preview_ttl_hours`, the hero URL form, or any
claim that a metered source may be read before signup. D2 (DataForSEO) stays
locked; ADR 0047 records that the scan's content is crawl-only for exactly this
reason.

`doc/11` Q1/D18 is annotated in place with a pointer here, following the
convention Q9 and Q17 already use for ADR 0026.

## Reasoning

**The decisive constraint is cost, not reachability.** Doc 06 §1.2's rule is about
a script exhausting a paid quota. A first-party HTTP GET of one page has no quota
to exhaust; it has a bandwidth cost, which a rate limit bounds, and a reputational
cost, which is real and is named in the consequences below. ADR 0016 drew the line
at a package because at the time the package and the danger were the same set.
They have since diverged: `app/connectors/` now holds provider credentials
(migration `0030`, ADR 0032) and `app/ai/` holds a metered key, and neither is
under `app/research/`. A rule that names `app.research` in 2026 forbids the cheap
thing and permits the expensive one.

**Two tests rather than one, because the general rule got weaker.** Rewriting
ADR 0016's rule from a package to a property makes it *broader in the right
direction* — it now catches `app/ai/` and `app/connectors/`, which it never did —
but strictly weaker about crawling, which was its original subject. The second
test is what pays that back: `app/scan/` is pinned by an allowlist, which is a
stronger statement than a denylist because it fails on anything nobody thought
of. The general rule catches the mistake ADR 0016 was written for; the allowlist
catches the mistake this ADR creates the room for.

**Option A was close.** It is the conservative answer and it was live until the
first-value cost was weighed against it. What separated them was that the cost of
A is already documented and already being paid — `doc/11` §3.1 wrote it down when
the decision went the other way — while the cost of D is bounded by structure that
can be checked on every commit rather than remembered.

**Option B was rejected on the retention obligation, not on the endpoint.**
`preview_session` existed to carry a third-party deletion path (D9) and was the
table migration `0011` dropped. Restoring it wholesale would restore an obligation
nobody re-examined. ADR 0048 re-derives a much narrower version deliberately.

## Consequences

**Good:**
- Phase 1 becomes buildable without reopening ADR 0027 or ADR 0029–0032.
- The general boundary rule now covers metered and credentialed paths it never
  covered: adding `from app.ai...` or `from app.connectors.hubspot...` to an
  anonymous route now fails the build, and previously did not.
- `app/research/ssrf.py` (89 test cases) becomes load-bearing on an anonymous path
  again — it is the strongest asset in the codebase and it will be exercised.

**Bad, and accepted:**
- We again perform a server-side fetch against a host a stranger named. The SSRF
  guard, the per-domain bucket and the global ceiling bound this; they do not
  eliminate it. A distributed caller rotating addresses across many target domains
  stays under the per-IP and per-domain limits while our user agent touches many
  sites. The global daily ceiling bounds the bill; **nothing bounds the
  reputational exposure**, and there is no mitigation in this decision for it.
- `apps/web/lib/client-address.ts` and `trusted_proxy_ips` come back, and with
  them the defect class `AUDIT-FINDINGS.md` records: the first implementation
  forwarded the browser's own `X-Forwarded-For` verbatim and made the per-IP
  bucket bypassable. The restored version derives the address from `request.ip` /
  `x-real-ip` only.
- The trust model is no longer one sentence. `ARCHITECTURE-HLD.md` §4 gains a
  seventh subsection, and any reviewer now has to know that `app/scan/` is
  special.
- Two boundary tests can disagree with each other. If the allowlist in
  `test_scan_boundary.py` is widened without widening the general rule, or the
  reverse, the build stays green over a gap. The mitigation is that both live in
  `tests/` and both name the other in their docstring; that is a convention, not
  a structure.

## Revisit trigger

Reopen if **any** of these happen:

- A second module wants anonymous fetch. Two modules is not "narrow", and the
  allowlist test should be refactored into a registry before a third appears.
- The scan is asked to read anything with a per-call cost — DataForSEO (D2),
  PageSpeed Insights (D3), or a language model. That is ADR 0047's subject and
  this ADR's rule would forbid it; changing that forbidding is a new ADR, not an
  edit to the allowlist.
- The global daily ceiling is hit by real traffic rather than by abuse. It means
  the scan is working and the budget was set for a product nobody was using.
- Abuse reports arrive from scanned domains. The mitigation would be honouring
  `robots.txt` (already a step in `doc/18`), a published user-agent policy page,
  or removing the surface — and which of those is right depends on the shape of
  the abuse, so it is not pre-decided here.

## Correction — 18 September 2026

**Nothing above this line has been edited.** G0's rewrite of
`tests/test_no_unauthenticated_crawl.py` (decision item 2) failed immediately
against real code: forbidding `app.connectors.*` and `app.retrieval.*` wholesale,
as written above, broke three pre-existing, already-shipped, already-anonymous
features this ADR did not consider when it named those packages:

1. **`app.connectors.domain_check`** — the onboarding domain-ownership
   verification (`/domains`, `/domains/{id}/check`), anonymous by design and
   already fine under ADR 0016's old rule (it is not under `app.research`).
   Forbidding all of `app.connectors.*` forbids it for the first time, with no
   reasoning above that considered it.
2. **`app.retrieval.scoped.apply_user_scope` / `apply_workspace_scope`** — called
   directly by login, registration and onboarding to set the scope of the
   identity they have *just* verified. There is no session yet to declare as a
   dependency at exactly the route whose job is to create one; forbidding all of
   `app.retrieval.*` catches this as a "tenancy failure" indistinguishable from
   reading a stranger's data, which it is not.
3. **`app.ai.registry.provider_status` / `app.embeddings.registry.embedder_status`**
   — `/health/ready`'s config introspection (ADR 0011), never a call to the
   provider itself.

None of these are a reason to weaken the rule this ADR decided on — the property
(metered or credentialed) is still the right one, and the scanner still gets its
narrow anonymous surface exactly as decided above. They are three named,
symbol-level exemptions inside that forbidden set, documented in
`tests/test_no_unauthenticated_crawl.py`'s own module docstring rather than here,
because the exemptions are a property of the *implementation* of the rule, not
of the decision to draw the boundary where this ADR drew it.

**Why this is a correction, not a fifth option or a supersession.** The
decision — re-cut the rule around metered-or-credentialed, one module may fetch,
two tests bound it — is unaffected: nothing above named these three cases, so
nothing above is contradicted by exempting them. `test_the_preview_endpoint_is_gone`
still passes unedited; no anonymous route gained access to anything actually
metered or credentialed. This is the same shape as ADR 0045's correction: a
decision made before running the acceptance test for real, corrected once running
it for real named what the decision's own reasoning had not considered.
