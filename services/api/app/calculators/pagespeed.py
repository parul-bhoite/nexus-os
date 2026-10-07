"""PageSpeed Insights payload → a performance score. Pure, no I/O (I1).

`calculators/` contains no model and no fetch; this takes the raw Lighthouse
payload a connector already retrieved and reads the one number out of it. It
raises rather than guessing when the field it needs is absent or null: a
performance score invented from a missing field — or a null read as zero — is the
exact failure invariant I1 exists to forbid, and zero would render as a real,
terrible grade for a site that was never measured.

The score Lighthouse returns is 0..1; the integer 0..100 this produces is the
number Google itself shows, so the figure a founder sees matches the one they can
check against PageSpeed directly.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

PERFORMANCE_SCORE: Final = "performance_score"
"""The canonical metric key — shared by the store, this calculator and the tile,
so the three cannot drift into three names for one number."""


class PageSpeedShapeError(ValueError):
    """The payload did not carry the score this calculator needs.

    A raise, not a default: the caller (`domain/pagespeed.py`) turns it into
    "stored nothing", which is honest, rather than a fabricated figure, which is
    not.
    """


def performance_score(payload: Mapping[str, Any]) -> int:
    """The Lighthouse performance score as an integer 0..100.

    Raises `PageSpeedShapeError` when the category is missing, the score is null
    (Lighthouse's "could not measure"), or it is not a number.
    """
    try:
        raw = payload["lighthouseResult"]["categories"]["performance"]["score"]
    except (KeyError, TypeError) as missing:
        raise PageSpeedShapeError(
            "PageSpeed payload carries no lighthouseResult.categories.performance.score"
        ) from missing

    if raw is None:
        raise PageSpeedShapeError(
            "PageSpeed returned a null performance score — could not measure, not measured zero"
        )
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        raise PageSpeedShapeError(
            f"PageSpeed performance score was not a number: {type(raw).__name__}"
        )

    return round(float(raw) * 100)
