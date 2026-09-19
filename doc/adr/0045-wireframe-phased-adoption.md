# 0045. The scoping wireframe is adopted in four ordered phases, not as one feature

- **Status:** Accepted
- **Date:** 2026-09-18
- **Deciders:** Parul
- **Corrected:** 2026-09-18 — a factual premise about Phase 1 was wrong. The
  decision stands; see [Correction](#correction--18-september-2026) at the end.
  Nothing above it has been edited.

## Context

A 56-screen Claude Design scoping wireframe ("NEXUS OS prototype scoping") was
imported this session — `doc/prototype/nexus-os-scoping-wireframe/`. It covers
the public site, a 13-step onboarding wizard, and 40+ workspace screens
(per-director dashboards, CRM, a business simulator, decision intelligence,
etc.), in a visual language (cream/terracotta, Schibsted Grotesk) unrelated to
the shipped token system (ADR 0043).

Two structural pieces of the wireframe directly contradict decisions already
shipped: its wizard onboarding contradicts ADR 0027 (guided-conversation
onboarding replaced the questionnaire), and its seven per-director dashboards
contradict ADR 0029–0032 (one command surface replaced the per-department
pages). The remaining screens split into things with no calculator or
connector to back them yet (`BUILD-STATUS.md` §0: 77 of 89 capabilities not
built; `CONTINUE-HERE.md`: P10/P11 retrieval core still open) and things that
are genuinely new and independent of any open backend work.

A single "implement the wireframe" instruction, taken literally, would mean
reopening two closed decisions and building UI on top of calculators that
don't exist — the exact trap `BUILD-STATUS.md` already names for connectors.

## Options considered

### A. Implement the wireframe as given, screen for screen
Fastest to describe. Reopens ADR 0027 and ADR 0029–0032 without a stated
reason to, and produces UI (Decision Intelligence, Business Simulator, War
Room) with no data behind it.

### B. Discard the wireframe except for copy inspiration
Safest against conflict, but throws away the Instant Gap Analysis scanner and
the OMR pricing model, which have no conflict and no missing dependency —
plausibly the highest-leverage ideas in the document.

### C. Adopt in four ordered phases; keep the two contested pieces as rejected; defer the backend-blocked pieces
Splits the wireframe into: new-and-buildable (Phases 1–3), contested-and-kept-
as-is (not phased, explicitly rejected), and new-but-blocked (Phase 4+,
deferred until its dependency closes).

## Decision

Option C, recorded in `doc/17-WIREFRAME-ADOPTION-PLAN.md`:

1. **Phase 1** — Instant Gap Analysis scanner (public, no-login, no backend
   dependency).
2. **Phase 2** — OMR pricing + generation-quota copy/UI (no schema change).
3. **Phase 3** — Bilingual PDPL/Legal page (isolated).
4. **Phase 4+** — Decision Intelligence, War Room, Business Simulator, NEXUS
   Labs, Proposal Studio, CRM surfaces. Deferred, not scheduled, pending
   P10/P11.

The wireframe's wizard onboarding and per-director dashboards are not adopted
in any phase; ADR 0027 and ADR 0029–0032 stand as written.

## Reasoning

The wireframe is a scoping artefact, not a design system to install wholesale
— its own project name says "scoping". Treating each screen as an independent
proposal, rather than one bundle, let the two contested pieces be rejected
without touching the rest, and let the backend-blocked pieces be named and
deferred instead of silently built on nothing. Phase order follows leverage
and dependency, not wireframe screen order: the scanner ships a working
funnel improvement with zero backend risk; pricing/legal are copy-shaped and
low-risk; everything behind P10/P11 waits because building it now repeats a
mistake already documented in `BUILD-STATUS.md`.

Option B was close — it's the safer default — but discarding the scanner and
pricing model along with the contested screens would have thrown away the two
best ideas in the document to avoid a conflict neither of them causes.

## Consequences

Phases 1–3 can proceed independently, one at a time, each stopping for
validation per the standing process rule. Phase 4+ work is explicitly not
scheduled — anyone picking up Decision Intelligence, the Simulator, or the War
Room screens should read this ADR and `CONTINUE-HERE.md` first, not start from
the wireframe. The wireframe file itself stays in `doc/prototype/` as
reference; nothing here deletes or supersedes it.

## Revisit trigger

If P10/P11 (retrieval core) and the `ops_layer` connector spine close, Phase
4+ becomes schedulable and should be re-split into its own ordered plan. If
someone wants to genuinely reopen onboarding shape or per-director dashboards,
that needs its own ADR superseding 0027 or 0029–0032 — not a re-reading of
this one.

---

## Correction — 18 September 2026

**Nothing above this line has been edited.** This section is appended, and the
status stays `Accepted`, because the decision recorded above is not the thing
that was wrong.

### What was wrong

Two claims about **Phase 1** are false:

- Options B and C above say the Instant Gap Analysis scanner has *"no conflict
  and no missing dependency"*.
- The Decision section calls it *"public, no-login, no backend dependency"*.

Phase 1 collides with three decisions that were already shipped:

1. **`doc/11` Q1 / D18** — *"No URL capture on the landing page. The pre-signup
   Preview audit is removed from the product."* Phase 1 is that audit.
2. **`doc/12` Phase 2** executed the removal: `app/routes/preview.py`, the hero
   URL form, `preview_session` (migration `0011`), the IP and domain rate-limit
   buckets and `apps/web/lib/client-address.ts` were deleted.
3. **ADR 0016** and `services/api/tests/test_no_unauthenticated_crawl.py` — a
   structural `ast` test asserting that no route without `current_session` or
   `current_scope` can reach `app.research` at any depth. Phase 1 as described
   cannot compile past it.

`doc/11` D9 is a fourth: it reads *"✅ Void — no preview data is retained"*, and
the wireframe screen states *"Results are cached for 7 days"* on its face.

Separately, the wireframe's own three sample gaps (S-02/S-03) are not sourceable
— two require DataForSEO (D2, blocked) and Instagram/Meta data for a domain we do
not own, and the third needs a calculator that does not exist. That was never
claimed above, but it is the second reason Phase 1 was not the cheap phase it
looked like.

### Why the decision above still stands

The false premise was about **one phase's dependencies**, not about the shape of
the adoption. Option C — adopt in ordered phases, reject the wizard onboarding
and the seven per-director dashboards, defer everything behind P10/P11 — is
unaffected by it, and Phases 2, 3 and 4+ are untouched. Superseding this ADR
would mean restating four phases in order to correct a sentence about one of
them, and would bury the fact that the premise was ever believed. That fact is
worth keeping visible: *"no conflict"* was written after reading the wireframe
and before reading `doc/11`, which is the specific mistake this project's own
process rule exists to prevent.

The repo's rule — never edit an accepted ADR to change a decision, write a new
one and mark the old superseded — is about a decision changing. No decision has
changed here, so the more conservative resolution is an appended, dated
correction that deletes nothing, over a supersession that would retire a decision
still in force.

### What carries the conflict

Phase 1 is still first, and it is now deliverable, because three new ADRs resolve
each collision deliberately rather than by not noticing it:

| ADR | Resolves |
|---|---|
| **0046** — a narrow anonymous crawl surface | Q1/D18 and ADR 0016. Partially supersedes the pre-signup-crawl portion of Q1/D18; rewrites the boundary rule from *"no anonymous route may reach `app.research`"* to *"no anonymous route may reach a metered or credentialed fetch"*, and pins the new module with a second allowlist test |
| **0047** — the gaps come from the crawl only | The unsourceable sample gaps. All three wireframe gap texts are replaced by the top three failed checks from `calculators/audit.py`'s 23 |
| **0048** — seven-day domain-keyed retention | D9. Reopened and narrowed: computed check results only, seven days, with a deletion control |

The ordered build sequence is `doc/18-GAP-ANALYSIS-BUILD-PLAN.md`.
`doc/17-WIREFRAME-ADOPTION-PLAN.md` §Phase 1 is corrected in place.

### The generalisable lesson

Phase 1 was ordered first partly *because* it looked dependency-free. It was the
only phase whose subject had previously been deliberately deleted, which is the
opposite of dependency-free and was discoverable by one grep of `doc/11`. **A
wireframe screen that the product already tried and removed is the most expensive
kind to phase first, and the removal is the thing to check for before the
dependency.**
