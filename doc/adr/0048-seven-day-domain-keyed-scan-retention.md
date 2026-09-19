# 0048. A pre-signup scan is kept seven days, keyed by domain, holding no page content

- **Status:** Accepted
- **Date:** 2026-09-18
- **Deciders:** Parul
- **Depends on:** ADR 0046 (the anonymous surface), ADR 0047 (what the row holds)
- **Reopens and narrows:** `doc/11-FLOW-DECISIONS.md` D9, recorded there as
  *"✅ Void — no preview data is retained"*
- **Affects:** `ARCHITECTURE-LLD.md` §4.7, §5.5, `doc/18-GAP-ANALYSIS-BUILD-PLAN.md`

## Context

`doc/11` §3.1 deleted `preview_session` along with *"the third-party retention
obligation it existed to honour"*, and the decision register records **D9 — preview
TTL and third-party deletion** as *"✅ Void — no third-party data is retained, so
there is nothing to expire or delete"*. Migration `0011` dropped the table.

D9 was answered "void" because the premise had gone, not because the question was
settled. ADR 0046 brings the premise back: an anonymous visitor types a domain,
we fetch a page of it, and something has to be shown. The wireframe states
*"Results are cached for 7 days"* on the scan screen itself, so caching is not an
implementation detail the user can be shielded from — it is on the page.

Three facts shape what the row may be:

1. **It has no `workspace_id`.** The visitor has no account; that is the entire
   point of the surface. So the row cannot carry the column every RLS policy in
   the system predicates on, and it cannot be read through
   `retrieval/scoped.py`'s `scoped_connection`.
2. **The subject of the data is a third party who never asked.** The domain owner
   did not visit us, did not consent, and will not know the row exists. This is
   not the tenant's own data under a contract; it is an observation about somebody
   else, held by us.
3. **There is already a precedent for storing computed signals and nothing else.**
   `app/domain/page_signals.py` defines `SIGNALS_NOT_STORED = {"text_sample",
   "emails"}` with the reasoning written out: `calculators/audit.py` asks only
   `bool(signals.emails)` and `len(signals.emails)`, never an address, so a count
   is stored and `test_no_scraped_address_is_ever_stored` asserts the payload
   contains no `@`. That table is workspace-scoped and still declines to hold
   scraped addresses.

Doing nothing — recomputing on every visit — is a live option, and it is what
"void" currently implies.

## Options considered

### A. Retain nothing; re-crawl on every view
D9 stays void and there is no new table, no expiry sweep, no deletion path and
no data-protection surface. Every page reload, every back button and every shared
link re-fetches the target site — which is precisely the reflected-load problem
the per-domain rate limit exists to bound, arriving from our own UI rather than
from an attacker. It also makes a result unshareable and un-bookmarkable.

### B. Store the full crawl: HTML, `PageSignals`, text
Everything a later feature might want, including carrying genuinely into
onboarding. It is also a store of third-party page content — including
`text_sample`, which `page_signals.py` already refuses to duplicate even for a
tenant's own site — held about people who never consented, with no account to
attach a deletion request to.

### C. Store only computed check results, domain-keyed, seven days, with a deletion path
The row holds the `Check` tuples (`id`, `label`, `passed`, `weight`, `evidence`)
and the category totals. No HTML, no `PageSignals` blob, no `text_sample`, no
email addresses. Expires at seven days, swept, and deletable by anyone who can
see it.

### D. Store the same, but keyed by a cookie or a browser-held token
Ties the row to the visitor rather than the domain. Makes the deletion claim
unambiguous — the person who created it deletes it — but means two visitors
scanning the same domain both cause a fetch, and it introduces a pre-signup
identifier where the surface's whole selling point is *"one field, no email"*.

## Decision

Option C.

**Shape:**

```
public_scan
  id                uuid        PK, gen_random_uuid()
  domain            text        NOT NULL   -- lowercased host, the cache key
  scanned_url       text        NOT NULL   -- the final URL after redirects
  checks            jsonb       NOT NULL   -- Check[] only: id, label, passed, weight, evidence
  scores            jsonb       NOT NULL   -- per-category score / max_score
  pages_read        integer     NOT NULL   -- 1 today; stored, never assumed
  created_at        timestamptz NOT NULL DEFAULT now()
  expires_at        timestamptz NOT NULL   -- created_at + 7 days, written, not computed on read
  deleted_at        timestamptz NULL       -- visitor-requested erasure

  ix_public_scan__domain_created  (domain, created_at DESC)
  ix_public_scan__expires_at      (expires_at) WHERE deleted_at IS NULL
```

**Rules, each of which is a test in `doc/18`:**

1. **No page content is stored.** Not HTML, not `text_sample`, not the
   `PageSignals` object, not an email address. A test asserts the serialised
   `checks` payload contains no `@`, following
   `test_no_scraped_address_is_ever_stored`. What is stored is what is displayed:
   the check results and nothing that was not on the screen.
2. **No `workspace_id`, and therefore no RLS.** The isolation predicate
   `workspace_id = current_setting('nexus.workspace_id')` cannot be written for a
   row that has no tenant, so enabling RLS would produce a policy that is either
   inert or refuses everything. Instead, the table is read and written **only**
   through `app/scan/store.py`, which is the one module permitted to open an
   unscoped connection for it, named so that `grep -r public_scan` returns a short
   reviewable list. This is the same posture `rate_limit_counter` and
   `email_verification` already hold, and the reason is stated here rather than
   inherited.
3. **Seven days, written as `expires_at` at insert.** Not computed from
   `created_at` at read time, so shortening the TTL later does not retroactively
   change what an already-stored row promised. A row past `expires_at` is never
   served, whether or not the sweep has run yet — expiry is enforced in the read
   query, and the sweep only reclaims space.
4. **Deletion is unauthenticated and keyed by the scan id**, exposed as
   `DELETE /public/scans/{id}` and offered on the result screen as a visible
   control. It is a soft delete (`deleted_at`), so a re-scan of the same domain
   creates a new row rather than resurrecting one, and the sweep hard-deletes.
   Rate-limited per address like every other route on this surface.
5. **No unique constraint on `domain`.** The freshest live row wins, found by
   `(domain, created_at DESC)` with `expires_at > now() AND deleted_at IS NULL` in
   the predicate. A partial unique index cannot express "unexpired" because `now()`
   is not immutable, and a plain unique on `domain` would collide the moment an
   expired row outlived the sweep.
6. **Nothing carries into onboarding in v1.** The row holds check results, not
   signals, so it cannot seed `page_signals` and the stage-2 crawl runs in full.
   ADR 0047 drops the wireframe's *"we won't ask twice"* copy for this reason.

**D9 is no longer void.** It is reopened, and its answer is now: seven days, a
visible deletion control, and a row that holds no page content. `doc/11` is
annotated at D9 and at §3.1 with a pointer here.

## Reasoning

**The decisive question was whose data it is.** Everything else follows from the
answer being *"a third party who never asked"*. That is why the retention is short
rather than convenient, why the deletion control is unauthenticated rather than
tied to whoever created the row, and why the content is narrowed to what was
displayed rather than to what a future feature might want.

**The deletion path deliberately has no token, and that choice is the one worth
arguing with.** The person with the strongest claim to have the row removed is
the domain owner, who was never the visitor and can never hold a token the
visitor was given. Making deletion possible for anyone holding the scan id means
the domain owner can act on a link they were sent, and the cost of abuse is
bounded: deleting a cached scan forces a re-scan, which the rate limits already
bound. A token would protect a cache entry at the price of making the
strongest-claim holder unable to use the control. **This is the one shape decision
in this ADR that was made rather than derived, and it should be confirmed.**

**Option A was close and lost on the fetch it causes, not on the feature it
lacks.** Re-crawling per view means our own UI generates the exact load pattern
the per-domain bucket exists to refuse, and a shared result link becomes a fresh
fetch of a stranger's server every time anyone opens it. Caching is the
politer behaviour towards the site being scanned, which is the one party in this
transaction with no say in it.

**Option B was rejected on a precedent we already set.** `page_signals.py`
declines to store `text_sample` and `emails` for a workspace's **own** site, under
a contract, behind RLS. Storing more than that about a site we have no
relationship with would be a strictly weaker posture applied to strictly weaker
grounds.

**Option D's identifier is the thing the surface is selling against.** *"One
field. No email."* A cookie set before signup to key a cache is a small thing that
undermines a large claim, and it does not actually solve the deletion-claim
problem — it just moves it to the wrong holder more explicitly.

## Consequences

**Good:**
- A result is shareable and reloadable without touching the scanned site again.
- The scanned domain's owner has a control they can use, on a page they can be
  sent, without an account.
- The stored payload is a strict subset of what was on the screen, so there is no
  category of data held that a reader has not already seen.

**Bad, and accepted:**
- **A new class of retained data exists: computed observations about third parties
  who did not consent.** Seven days and a deletion control are mitigations, not an
  answer. There is **no mitigation at all** for the fact that a domain owner will
  usually never learn the row existed. If a data-protection review of this
  product happens, this row is the thing it will find.
- The first table in the system with no tenant column and no RLS that holds
  anything derived from the outside world. `domain_claim`'s lack of a policy is
  already tracked as a known problem (`H7`); this adds a second table whose
  protection is a module convention rather than a database guarantee.
- An expiry sweep comes back. `jobs/expiry.py:expire_previews` was deleted in P2
  and its replacement has to be written, tested, and actually scheduled — an
  unscheduled sweep is a table that grows forever while the read query quietly
  keeps returning nothing.
- The "cached 7 days" promise is now on a public page, so shortening or lengthening
  it is a copy change as well as a config change, and the two can drift.
- A scan is keyed by domain, so two different visitors scanning the same domain
  see the same result — including one visitor seeing a result produced by
  somebody else's scan. That is intended (it is what bounds the fetching) and it
  means the result is not private to whoever asked for it. The screen must not
  imply otherwise.

## Revisit trigger

- **A domain owner asks us to delete a scan, or objects to having been scanned.**
  The deletion control and the seven-day window are the whole of the current
  answer; a second request means the answer needs to be a policy and probably a
  contact route, not a button.
- **Anything wants to carry the scan into onboarding.** That needs stored signals
  rather than stored check results, which is Option B's shape and changes what is
  retained — a new ADR, not a widening of this one.
- **A second tenantless table is proposed.** Two is a pattern, and the
  module-convention protection in rule 2 should become something structural
  before a third.
- **PDPL / Phase 3's legal page is written** (`doc/17` Phase 3). Whatever it says
  about retention has to match this row, and if it cannot, this row changes.
