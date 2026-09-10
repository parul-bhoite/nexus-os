"""Preview audit scoring.

Doc 07 §7: *"Every calculator has unit tests including boundary and zero-delta
cases."* These carry the highest test bar in the codebase because they produce
the numbers users are asked to believe.

Two properties matter beyond the arithmetic:

- **every score is reconstructible from its checks** (I9), so a card can answer
  "why are you telling me this?"
- **a category with no evidence is Locked, never 0** (I10)
"""

from __future__ import annotations

import pytest

from app.calculators.audit import (
    LOCKED_IN_PREVIEW,
    build_preview_audit,
    score_brand,
    score_performance,
    score_technical_seo,
)
from app.domain.page_signals import PageSignals


def signals(**overrides: object) -> PageSignals:
    base: dict[str, object] = {
        "url": "https://example.com/",
        "is_https": True,
        "title": None,
        "title_length": 0,
        "meta_description": None,
        "meta_description_length": 0,
    }
    base.update(overrides)
    return PageSignals(**base)  # type: ignore[arg-type]


def rich() -> PageSignals:
    return signals(
        title="Al Manar Fit-Out & Joinery | Muscat",
        title_length=35,
        meta_description="Commercial fit-out and bespoke joinery for developers across Oman." * 1,
        meta_description_length=66,
        h1_texts=("Commercial fit-out, delivered on programme",),
        h2_texts=("Our services", "Recent projects", "Contact"),
        has_viewport_meta=True,
        has_canonical=True,
        canonical_url="https://example.com/",
        has_structured_data=True,
        has_open_graph=True,
        declared_language="en",
        image_count=10,
        images_with_alt=9,
        internal_link_count=12,
        external_link_count=3,
        emails=("hello@example.com",),
        has_phone=True,
        social_profiles=("instagram", "linkedin"),
        word_count=600,
        html_bytes=90_000,
        script_count=8,
        stylesheet_count=3,
        inline_style_count=1,
    )


# ── Boundaries ────────────────────────────────────────────────


def test_empty_page_scores_zero_but_is_still_scored() -> None:
    """Zero is a legitimate *result* here — it is not a missing input.

    I10 forbids showing 0 for absent data. A page that genuinely fails every
    check is different: the evidence exists and it is bad.
    """
    result = score_brand(signals())
    assert result.score == 0
    assert result.max_score > 0
    assert len(result.checks) > 0


def test_a_good_page_scores_full_marks() -> None:
    result = score_brand(rich())
    assert result.score == result.max_score
    assert result.percentage == 100


@pytest.mark.parametrize(
    ("length", "expected"),
    [(9, False), (10, True), (70, True), (71, False)],
)
def test_title_length_boundaries(length: int, expected: bool) -> None:
    result = score_brand(signals(title="x" * length, title_length=length))
    check = next(c for c in result.checks if c.id == "brand.title_length")
    assert check.passed is expected


@pytest.mark.parametrize(
    ("length", "expected"),
    [(49, False), (50, True), (160, True), (161, False)],
)
def test_meta_description_length_boundaries(length: int, expected: bool) -> None:
    result = score_technical_seo(
        signals(meta_description="x" * length, meta_description_length=length)
    )
    check = next(c for c in result.checks if c.id == "seo.description")
    assert check.passed is expected


@pytest.mark.parametrize(("count", "expected"), [(0, False), (1, True), (2, False)])
def test_exactly_one_h1_is_required(count: int, expected: bool) -> None:
    result = score_brand(signals(h1_texts=tuple(f"h{i}" for i in range(count))))
    check = next(c for c in result.checks if c.id == "brand.single_h1")
    assert check.passed is expected


def test_a_page_with_no_images_is_not_penalised_for_alt_text() -> None:
    """Absence of images is not a failure to caption them.

    Dividing by zero images and scoring 0 would punish a text-only page for
    something it does not have.
    """
    result = score_technical_seo(signals(image_count=0, images_with_alt=0))
    check = next(c for c in result.checks if c.id == "seo.image_alt")
    assert check.passed is True
    assert check.evidence == "no images"


@pytest.mark.parametrize(
    ("total", "with_alt", "expected"),
    [(10, 7, False), (10, 8, True), (10, 10, True), (1, 0, False)],
)
def test_alt_text_coverage_threshold(total: int, with_alt: int, expected: bool) -> None:
    result = score_technical_seo(signals(image_count=total, images_with_alt=with_alt))
    check = next(c for c in result.checks if c.id == "seo.image_alt")
    assert check.passed is expected


def test_noindex_is_the_heaviest_seo_penalty() -> None:
    """A page excluded from the index cannot rank at all."""
    indexable = score_technical_seo(signals(robots_blocks_indexing=False))
    blocked = score_technical_seo(signals(robots_blocks_indexing=True))
    assert indexable.score - blocked.score == 15


def test_http_only_loses_the_https_check() -> None:
    assert (
        score_technical_seo(signals(is_https=True)).score
        - score_technical_seo(signals(is_https=False)).score
        == 10
    )


# ── Determinism and auditability ──────────────────────────────


def test_scoring_is_deterministic() -> None:
    """No clock, no randomness, no model — the same input always scores the same."""
    page = rich()
    assert score_brand(page) == score_brand(page)
    assert score_technical_seo(page) == score_technical_seo(page)


def test_every_score_is_reconstructible_from_its_checks() -> None:
    """I9 — the trace is the answer to 'why are you telling me this?'"""
    for result in (score_brand(rich()), score_technical_seo(rich()), score_performance(rich())):
        assert result.score == sum(c.weight for c in result.checks if c.passed)
        assert result.max_score == sum(c.weight for c in result.checks)


def test_every_check_carries_evidence() -> None:
    """A check without evidence is an assertion, not a finding."""
    for result in (score_brand(rich()), score_technical_seo(rich()), score_performance(rich())):
        for check in result.checks:
            assert check.evidence, f"{check.id} has no evidence"
            assert check.label


def test_percentage_never_divides_by_zero() -> None:
    from app.calculators.audit import CategoryScore

    assert CategoryScore("empty", 0, 0).percentage == 0


# ── Preview scope (doc 06 §1.1) ───────────────────────────────


def test_preview_scores_only_brand_performance_and_technical_seo() -> None:
    audit = build_preview_audit(rich())
    assert {c.category for c in audit.categories} == {"brand", "technical_seo", "performance"}


def test_data_dependent_categories_are_locked_not_zero() -> None:
    """I10 — a missing input renders a named state, never 0.

    Doc 05 §3.1: Marketing is not scoreable without GA4, and Brand and SEO must
    not be merged into a Marketing score to manufacture a number.
    """
    audit = build_preview_audit(rich())
    scored = {c.category for c in audit.categories}

    for category in ("marketing", "sales", "finance", "operations", "people"):
        assert category in audit.locked_categories
        assert category not in scored


def test_every_locked_category_names_its_unlock() -> None:
    """A locked tile is a call to action, not a failure (doc 04 §6)."""
    audit = build_preview_audit(rich())
    for category in audit.locked_categories:
        assert LOCKED_IN_PREVIEW[category].strip()


def test_competitor_discovery_is_locked_behind_verification() -> None:
    """Doc 06 §1.1 — the competitor list has intelligence value about third
    parties, so it sits behind domain verification, not in Preview."""
    audit = build_preview_audit(rich())
    assert "competitors" in audit.locked_categories


def test_overall_is_computed_only_over_scored_categories() -> None:
    """The denominator must be what was actually measured (doc 05 §10)."""
    audit = build_preview_audit(rich())
    assert audit.overall == 100
    assert audit.scored_count == 3
