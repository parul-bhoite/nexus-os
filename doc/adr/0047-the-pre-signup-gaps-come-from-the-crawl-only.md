# 0047. The pre-signup scan's three gaps come from the crawl and nothing else

- **Status:** Accepted
- **Date:** 2026-09-18
- **Deciders:** Parul
- **Depends on:** ADR 0046 (the anonymous surface exists at all)
- **Affects:** `doc/18-GAP-ANALYSIS-BUILD-PLAN.md`, `ARCHITECTURE-LLD.md` §5.5

## Context

The wireframe screen this implements (`doc/prototype/nexus-os-scoping-wireframe/
NEXUS OS Prototype.dc.html`, S-02 / S-03) promises *"Three real gaps in about 90
seconds"* and shows three specific ones. Read against what the codebase can
actually source, all three are unsourceable as written:

| # | Wireframe copy | Where it would have to come from | Status |
|---|---|---|---|
| 1 | *"You rank #14 for 'construction company muscat' — your competitors rank #3 and #5. 880 searches a month (DataForSEO)."* | DataForSEO | **Blocked** — D2 has no credentials, and doc 06 §1.2 forbids a metered API on an unauthenticated path. ADR 0046 forbids it structurally |
| 2 | *"Your Instagram has not posted in 47 days... Meta Ads Library shows Gulf Modern Construction running 6 active villa-renovation ads."* | Instagram Graph API, Meta Ads Library | **Not obtainable at all.** Instagram insights for an account we do not own and have no token for; and neither is connectable pre-signup by definition |
| 3 | *"Your site lists 7 services but no prices, cases or proof for 5 of them."* | A per-service-page content audit | **Does not exist.** `calculators/audit.py` has no service-page check. It scores one page's HTML |

The screen also claims *"Scan complete — 124 pages read"*. `build_preview_audit`
takes exactly one `PageSignals` — one page — so 124 is not merely optimistic, it
describes a different function.

What *does* exist is `app/calculators/audit.py`: **23 checks** across three
categories — `score_brand` (9), `score_technical_seo` (9), `score_performance` (5)
— each carrying an `id`, a human `label`, a `weight` and an `evidence` string
that states what was observed. It is pure, has no IO and no model (I1), is
already tested, and `app/domain/brief.py` already ranks its failures for the
authenticated morning brief under ADR 0029.

The product's central claim is that it never invents a number. `CLAUDE.md`'s
content rule extends that to the marketing site: *"no invented customers, logos,
testimonials or results."* Three gaps citing a vendor we have no contract with
and a social account we cannot read would be the most visible possible violation
of the thing being sold.

## Options considered

### A. Ship the wireframe's three gaps, sourced from somewhere
Requires DataForSEO credentials (D2, external and open), a Meta integration that
cannot exist pre-signup, and a service-page calculator nobody has written. Not
available, and two of the three are not available at any price.

### B. Ship the wireframe's three gaps as illustrative, labelled
`CLAUDE.md` permits a product mock carrying a visible `Illustrative` tag. But this
is not a mock — it is a live result about the visitor's own domain, arriving
after a real scan of it. A fabricated finding does not become true because it is
labelled; the label stays on the screen and the screenshot does not.

### C. Wait for D2, build the scan afterwards
Honest, and indefinite. D2 has been open since `doc/11` was ratified, is external,
and gates nothing else in the current plan. And D2 closing would not help: doc 06
§1.2 and ADR 0046 both forbid a metered call on an anonymous path regardless of
whether the credentials exist.

### D. Crawl-only — the three gaps are the top three failed checks
Take the 23 checks the calculator already computes, rank the failures, show the
top three, each carrying the `evidence` string the calculator produced. Zero new
vendors, zero new cost, nothing new to source. The copy changes from the
wireframe's.

## Decision

Option D. **Every gap shown to an anonymous visitor is a failed check from
`calculators/audit.py`, carrying that check's own label and its own evidence
string.**

Specifically:

- **The ranking is points lost, descending, tie-broken by `check_id`** — the same
  ordering `app/domain/brief.py` already uses. It is extracted into a pure
  `app/calculators/gaps.py` so both surfaces read one implementation, and a test
  asserts the two orderings are identical over the same checks.
- **The check's own `label` is used verbatim, never negated.** ADR 0029 and
  `doc/14` S3 already settled this and the reason generalises: negating
  *"Page has a title"* produces *"Not Page has a title"*.
- **The detail line is `Check.evidence`, which is what was observed and never
  advice.** *"0 characters"*, *"3 script tags"*, *"no Open Graph tags"*. The scan
  may say what a check was **worth**, because the weight is a number in the code.
- **Fewer than three failures shows fewer than three gaps**, and zero failures
  shows a state that says so — with its own limits stated in the same breath, the
  way `BriefState.ALL_HELD` already does. Never a padded third item, never a zero
  (I10).
- **The page count shown is the page count fetched**, which is one. The copy says
  which page.
- **The wireframe's *"What NEXUS would do"* blocks are dropped in v1.** They
  describe a 90-day content calendar, a bilingual posting calendar and grounded
  proposal generation — three of the 77 capabilities `BUILD-STATUS.md` §0 records
  as not built. A promise about an unbuilt capability is the same invention as a
  fabricated number, one step removed.
- **The wireframe's *"carries into onboarding — we won't ask twice"* is dropped.**
  ADR 0048 stores computed check results, not page content, so the stage-2
  onboarding crawl still runs in full. Claiming otherwise would be a claim about
  our own behaviour rather than the customer's, which makes it worse rather than
  better.

D2 stays locked. No DataForSEO, no Instagram, no Meta Ads, no PageSpeed (D3) on
this path in v1.

## Reasoning

**The decisive constraint is I1, and it is the product.** Everything else here is
downstream of one fact: the thing being sold is that NEXUS does not make numbers
up. A landing page that makes one up to sell that is not a marketing compromise,
it is the product contradicting itself on the first screen a stranger sees.

**Option A was never separable from ADR 0046.** Even with credentials in hand,
the anonymous path may not call a metered API — so A requires reversing doc 06
§1.2 as well as unblocking D2. Two decisions to buy one screen.

**Option B was the close one**, because `CLAUDE.md` genuinely does permit
illustrative content and the wireframe copy is much stronger than ours will be.
What separated them is the position on the page: an `Illustrative` tag on a
product screenshot in a marketing section is a reader understanding they are
looking at a picture. The same tag under *"we scanned abc-construction.om"* asks
the reader to hold two contradictory ideas about the same sentence, and the one
they will keep is the specific number.

**The cost is real and is not hidden.** *"Meta description is a usable length —
0 characters"* is a weaker hook than *"you rank #14 while your competitors rank
#3"*. This decision trades conversion for truthfulness knowingly. The mitigation
available is presentation — the weight, the ranking, and what the check is worth
— not content.

**Reusing `brief.py`'s ranking rather than inventing one** costs an extraction and
buys a guarantee: the gap a stranger is shown on the landing page and the item
that appears at the top of their morning brief after signup are the same finding,
in the same order, in the same words. Two rankings would eventually disagree, and
the disagreement would land exactly at the moment a new customer compares them.

## Consequences

**Good:**
- No new dependency, no new vendor, no new cost, no new credential. The whole
  feature reads from a pure calculator that is already tested.
- The scan cannot be blocked by D2 or D3 closing or not closing.
- A gap shown pre-signup is traceable to a check id and an observation, so
  *"why are you telling me this?"* has the same answer here as everywhere (I9).

**Bad, and accepted:**
- **The hook is weaker than the wireframe's, and there is no mitigation.** A
  well-built site may fail only trivial checks — *"no Open Graph tags"*, *"1
  stylesheet over the threshold"* — and the screen will then promise three gaps
  and deliver three small ones. The copy must not oversell what the ranking
  returns, which means the headline cannot say *"costing you real work"*.
- Only one page is read, so the scan says nothing about a site's depth, its
  service pages or its content. That is a true limitation and has to be stated on
  the screen rather than glossed.
- `calculators/gaps.py` and `domain/brief.py` are two callers of one rule, held
  together by a parity test rather than by one of them calling the other. If the
  extraction in `doc/18` G3 is skipped, this becomes two rankings and the test is
  the only thing that would notice.
- The 23 checks were written for a first-party audit of your own site, where
  every check is actionable by the reader. Shown to a stranger about a domain
  they may not own, some read oddly. No check is removed for v1; if any turn out
  to read badly, that is copy work on the screen and not a change to the
  calculator.

## Revisit trigger

- **D2 closes and DataForSEO credentials exist.** Keyword gaps then become
  available *after* signup, on the authenticated path, where the metered rule
  permits them. Whether any of them belongs pre-signup is a new decision and
  requires reopening ADR 0046, not this one.
- **A service-page or multi-page content calculator is built.** Gap 3's wireframe
  shape becomes sourceable, and the one-page budget in ADR 0046 becomes the
  binding constraint rather than the calculator.
- **Measured conversion on the scan screen is poor enough to matter.** The answer
  is presentation or a different pre-signup offer entirely — it is not permission
  to invent a finding, and this ADR should be cited when that is proposed.
