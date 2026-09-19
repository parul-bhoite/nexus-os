# 17 — Adopting the scoping wireframe

**Source:** `doc/prototype/nexus-os-scoping-wireframe/` — a 56-screen Claude
Design scoping wireframe ("NEXUS OS prototype scoping"), imported 18 September
2026. Visual language only (cream/terracotta, Schibsted Grotesk) — the shipped
token system (ink/bone/gold/steel, Tailwind) stays authoritative. Structure and
copy are the useful part; the CSS is not implemented as-is.

**Explicitly rejected, not adopted:** the wireframe's 13-step wizard onboarding
(S10–S22) and its seven separate director dashboards (S40–S46) both contradict
decisions already made and shipped — ADR 0027 (guided-conversation onboarding
replaced the questionnaire) and ADR 0029–0032 (one command surface replaced the
per-director pages). Kept as-is; not reopened by this document.

Everything else in the wireframe is either new (no existing decision to
contradict) or a refinement of existing copy/numbers. This file orders that
remainder into phases, one at a time, per the standing process rule.

## Phases

### Phase 1 — Instant Gap Analysis scanner
Public, no-login, rate-limited website scan (wireframe S02/S03) that returns
three sourced gaps before asking for signup. New marketing-site surface; no
backend dependency on P10/P11. Highest funnel leverage of anything in the
wireframe.

> ⚠ **Corrected 18 September 2026.** "No backend dependency" was right; **"new"
> was wrong.** This screen is the pre-signup Preview audit that `doc/11` Q1/D18
> deliberately removed and `doc/12` Phase 2 deleted, and ADR 0016's
> `test_no_unauthenticated_crawl.py` fails the build on any anonymous route that
> can reach the crawler. `doc/11` D9 — *"void, nothing is retained"* — also
> contradicts the screen's own *"cached for 7 days"*. And the wireframe's three
> sample gaps are not sourceable: two need DataForSEO (D2, blocked) and
> Instagram/Meta data for a domain we do not own; the third needs a calculator
> that does not exist.
>
> Phase 1 remains first and is now deliverable. **Three ADRs carry the
> conflicts — 0046 (a narrow anonymous crawl surface), 0047 (gaps come from the
> crawl only), 0048 (seven-day domain-keyed retention) — and ADR 0045 carries the
> correction to its own premise.** The ordered, one-PR-per-step sequence is
> `doc/18-GAP-ANALYSIS-BUILD-PLAN.md`; build from that, not from this paragraph.
>
> The copy changes with it. The three gaps are the top three failed checks from
> `calculators/audit.py`'s 23, in that calculator's own words — not the
> wireframe's rankings, Instagram or service-page claims — and the screen reports
> **one page read**, not 124, because `build_preview_audit` scores one page.

### Phase 2 — OMR pricing + generation-quota model
Replace the current $49/"Let's talk" copy in `lib/content.ts` and
`components/sections/Pricing.tsx` with the 3-tier OMR/seats/generation-quota
model (wireframe S04). Copy and small UI change; no schema or API shape change
unless quota enforcement is scoped in — that would need its own ADR and is out
of scope for this phase.

### Phase 3 — Bilingual PDPL / Legal page
New `/legal` surface (wireframe S07): Arabic as the stated reference version,
English alongside, DPA template download. Isolated; no dependency on anything
else.

### Phase 4+ — Deferred, not scheduled
Decision Intelligence, Competitor War Room, Business Simulator, NEXUS Labs,
Proposal Studio, CRM surfaces (wireframe S50–S82). `CONTINUE-HERE.md` and
`BUILD-STATUS.md` §0 are explicit that the calculators and connector spine
these would sit on (P10/P11, `ops_layer`) are not built yet. Building the
screen first would be UI over a capability that doesn't exist — the exact trap
`BUILD-STATUS.md` already names. Revisit once P10/P11 close.

## Process

One phase at a time. Each phase stops at the end for validation before the
next starts — per the standing rule at the top of `CLAUDE.md`. No phase here
reopens ADR 0027 or ADR 0029–0032.
