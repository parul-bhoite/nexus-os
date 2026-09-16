"""The morning brief's rules, asserted against the real calculator.

ADR 0029. Hermetic — `compose` is pure and the signals are built here, so the
whole file runs in milliseconds and needs no database. That matters beyond
speed: the brief renders at the top of every page load, so the thing most worth
proving is that it costs nothing and cannot refuse.

The failures these guard against all render as a perfectly plausible screen:

- a brief that ranks by something other than what a check cost
- one that turns an observation into advice
- one that says "nothing needs you" from eighteen checks on one web page
- one where an audit that never ran looks like an audit that found nothing
- one that reorders itself on every reload while saying the same thing
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

from app.domain.brief import Brief, BriefState, ItemKind, compose
from app.domain.page_signals import PageSignals
from app.grounding.compute import Computation, compute_from_crawl
from app.retrieval.crawl import CrawlSnapshot

MEASURED_AT = datetime(2026, 9, 16, 14, 31, tzinfo=UTC)

# A page that fails a spread of checks at both weights, so the ranking has
# something to rank. Modelled on the real Prosoft crawl.
POOR = PageSignals(
    url="http://example.om/",
    title="A title that is far too long to be useful for a search result page listing",
    title_length=76,
    meta_description="x" * 168,
    meta_description_length=168,
    h1_texts=("one", "two"),
    h2_texts=("a", "b"),
    word_count=1178,
    is_https=False,
    has_canonical=True,
    canonical_url="https://example.om/",
    has_structured_data=False,
    declared_language=None,
    robots_blocks_indexing=False,
    has_open_graph=False,
    has_viewport_meta=True,
    has_robots_meta=False,
    image_count=37,
    images_with_alt=0,
    internal_link_count=51,
    external_link_count=29,
    script_count=10,
    stylesheet_count=4,
    inline_style_count=2,
    html_bytes=63762,
    emails=("hello@example.om",),
    has_phone=True,
    social_profiles=("facebook",),
)

PERFECT = replace(
    POOR,
    title="A usable page title",
    title_length=19,
    meta_description="y" * 120,
    meta_description_length=120,
    h1_texts=("the one heading",),
    is_https=True,
    has_structured_data=True,
    declared_language="en",
    has_open_graph=True,
    images_with_alt=37,
)

AUDITS = ("marketing.seo_gaps", "marketing.brand_intelligence")
EXPECTED = frozenset(AUDITS)


def _computations(signals: PageSignals, ids: tuple[str, ...] = AUDITS) -> tuple[Computation, ...]:
    # `pages_captured` is context for the figure rather than an input to it —
    # the calculators score a single page — so three is as arbitrary as any
    # other number and nothing below reads it.
    snapshot = CrawlSnapshot(
        url=signals.url, captured_at=MEASURED_AT, signals=signals, pages_captured=3
    )
    return tuple(
        computation
        for capability_id in ids
        if (computation := compute_from_crawl(capability_id, snapshot)) is not None
    )


def _brief(signals: PageSignals, ids: tuple[str, ...] = AUDITS, unobserved: int = 77) -> Brief:
    return compose(_computations(signals, ids), expected=EXPECTED, unobserved=unobserved)


# ── The ranking ───────────────────────────────────────────────


def test_items_are_ranked_by_what_the_check_cost() -> None:
    """The one rule the whole region rests on. Anything else — alphabetical,
    registry order, whatever the calculator happened to emit — is a brief that
    leads with the cheapest thing on the page."""
    costs = [item.cost for item in _brief(POOR).items if item.kind is ItemKind.CHECK_FAILED]

    assert costs == sorted(costs, reverse=True)
    assert costs[0] == 10, "the heaviest failing check is worth ten points"


def test_a_tie_is_broken_the_same_way_every_time() -> None:
    """Six checks fail at five points each. Without a second sort key the order
    follows whatever the set iterated as, and the brief looks rewritten on every
    reload while saying exactly the same thing."""
    first = [item.check_id for item in _brief(POOR).items]
    again = [item.check_id for item in _brief(POOR).items]

    assert first == again
    ties = [i.check_id for i in _brief(POOR).items if i.cost == 5]
    assert ties == sorted(ties)


def test_every_failing_check_is_listed_and_no_passing_one_is() -> None:
    brief = _brief(POOR)
    failed = {item.check_id for item in brief.items if item.kind is ItemKind.CHECK_FAILED}
    passing = {
        check.id
        for computation in _computations(POOR)
        for check in computation.score.checks
        if check.passed
    }

    assert failed and not (failed & passing)
    assert len(failed) == brief.checks_total - brief.checks_passed


# ── Observation, never advice ─────────────────────────────────


def test_the_detail_is_the_calculators_evidence_verbatim() -> None:
    """`Check.evidence` is specified as what was observed. Rewriting it here is
    how "0/37 images" becomes "add alt text" — guidance nobody computed, on the
    most-read surface in the product."""
    evidence = {
        check.id: check.evidence
        for computation in _computations(POOR)
        for check in computation.score.checks
    }

    for item in _brief(POOR).items:
        if item.kind is ItemKind.CHECK_FAILED:
            assert item.detail == evidence[item.check_id]


def test_the_headline_is_the_checks_own_label_and_is_never_negated() -> None:
    """**The correction found while building.** The design wrote "Not served
    over HTTPS" for `seo.https`, which reads well and generalises to nothing:
    the same transformation turns "Page has a title" into "Not Page has a
    title". The label states the check and the item states that it failed."""
    labels = {
        check.id: check.label
        for computation in _computations(POOR)
        for check in computation.score.checks
    }

    for item in _brief(POOR).items:
        if item.kind is ItemKind.CHECK_FAILED:
            assert item.headline == labels[item.check_id]


def test_nothing_in_the_brief_tells_the_reader_what_to_do() -> None:
    brief = _brief(POOR)
    prose = " ".join([brief.message, *(f"{i.headline} {i.detail}" for i in brief.items)]).lower()

    for instruction in ("you should", "add ", "fix ", "we recommend", "consider "):
        assert instruction not in prose, f"the brief is giving advice: {instruction!r}"


def test_it_reports_what_was_found_and_never_what_changed() -> None:
    """Nothing re-crawls (M32), so a brief claiming movement would be claiming a
    comparison nobody made."""
    prose = _brief(POOR).message.lower()

    for comparison in ("this week", "since", "new ", "up ", "down ", "improved", "worse"):
        assert comparison not in prose, f"the brief is claiming a comparison: {comparison!r}"


# ── The three states ──────────────────────────────────────────


def test_a_page_with_failures_is_the_findings_state() -> None:
    brief = _brief(POOR)

    assert brief.state is BriefState.FINDINGS
    assert brief.points_lost > 0
    assert brief.measured_on == "2026-09-16"


def test_all_held_states_its_own_limits_in_the_same_breath() -> None:
    """A brief reading "nothing needs you" would be a claim about a business
    drawn from checks on one web page — the category error the composite score
    is already refused for."""
    brief = _brief(PERFECT)

    assert brief.state is BriefState.ALL_HELD
    assert brief.points_held == brief.points_total
    assert not [i for i in brief.items if i.kind is ItemKind.CHECK_FAILED]
    assert "not a clean bill of health" in brief.message
    assert "77" in brief.message, "the limits sentence must name what is unobserved"


def test_nothing_measured_is_not_the_same_object_as_nothing_wrong() -> None:
    """I10. An audit that never ran must not read as an audit that found
    nothing — the region is never hidden and never shows a zero score."""
    brief = compose((), expected=EXPECTED, unobserved=77)

    assert brief.state is BriefState.NOT_MEASURED
    assert brief.items == ()
    assert brief.measured_on == "", "a date on an unmeasured brief is the clearest lie here"
    assert "not the same as nothing being wrong" in brief.message


def test_an_unmeasured_capability_sorts_above_every_failure() -> None:
    """A missing measurement qualifies every number beneath it; a low score
    qualifies nothing. So it leads, whatever the points."""
    brief = _brief(POOR, ids=("marketing.seo_gaps",))
    kinds = [item.kind for item in brief.items]

    assert kinds[0] is ItemKind.UNMEASURED
    assert ItemKind.UNMEASURED not in kinds[1:]
    assert brief.items[0].capability_id == "marketing.brand_intelligence"
    assert brief.items[0].cost == 0, "nothing was scored, so a cost would be invented"


# ── Provenance and totals ─────────────────────────────────────


def test_every_item_names_the_calculator_that_weighed_it() -> None:
    for item in _brief(POOR).items:
        if item.kind is ItemKind.CHECK_FAILED:
            assert item.method.startswith("calculators.audit.")
            assert item.capability_id in EXPECTED


def test_the_totals_are_the_calculators_and_not_recounted() -> None:
    computations = _computations(POOR)
    brief = _brief(POOR)

    assert brief.points_total == sum(c.score.max_score for c in computations)
    assert brief.points_held == sum(c.score.score for c in computations)
    assert brief.points_lost == sum(i.cost for i in brief.items)
