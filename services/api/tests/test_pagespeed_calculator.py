"""The PageSpeed calculator reads a score; it never invents one (I1).

`calculators/pagespeed.py` is pure: a recorded Lighthouse payload in, an integer
0..100 out, and a raise — never a guess — when the shape it needs is absent. A
performance score fabricated from a missing field is the exact failure I1 forbids,
so the malformed cases assert a raise rather than a fallback number.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from app.calculators.pagespeed import PERFORMANCE_SCORE, PageSpeedShapeError, performance_score

FIXTURE = Path(__file__).parent / "fixtures" / "pagespeed" / "acme_mobile.json"


def test_the_metric_key_is_stable() -> None:
    """The store, the calculator and the dashboard all key on this one string."""
    assert PERFORMANCE_SCORE == "performance_score"


def test_a_recorded_payload_yields_the_lighthouse_score() -> None:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    # 0.88 on Lighthouse's 0..1 scale is the 88 Google itself shows.
    assert performance_score(payload) == 88


def test_a_zero_point_zero_four_rounds_the_way_google_shows_it() -> None:
    assert (
        performance_score({"lighthouseResult": {"categories": {"performance": {"score": 0.045}}}})
        == 4
    )


def test_a_missing_performance_category_raises() -> None:
    with pytest.raises(PageSpeedShapeError):
        performance_score({"lighthouseResult": {"categories": {}}})


def test_a_null_score_raises_rather_than_becoming_zero() -> None:
    """A null score is "could not measure", not "measured zero" — and zero would
    render as a real, terrible grade."""
    with pytest.raises(PageSpeedShapeError):
        performance_score({"lighthouseResult": {"categories": {"performance": {"score": None}}}})


def test_a_non_numeric_score_raises() -> None:
    with pytest.raises(PageSpeedShapeError):
        performance_score({"lighthouseResult": {"categories": {"performance": {"score": "fast"}}}})


def test_an_empty_payload_raises() -> None:
    with pytest.raises(PageSpeedShapeError):
        performance_score({})
