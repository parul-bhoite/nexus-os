"""The brief carries finish-your-setup nudges, kept apart from the findings.

ADR 0083. A nudge is an action ("Connecting HubSpot"); the findings ranking is
"a ranking, not a recommendation" (ADR 0029). These tests pin that the two never
merge, and that nudges survive in every brief state — a workspace with no crawl
(`NOT_MEASURED`) still has declared tools worth connecting.
"""

from __future__ import annotations

from app.domain.brief import BriefNudge, BriefState, ItemKind, compose
from tests.test_brief_composition import EXPECTED, POOR, _computations

NUDGES = (
    BriefNudge(headline="Connecting HubSpot", unlocks="pipeline answers from your own deals"),
    BriefNudge(headline="Connecting Xero", unlocks="actuals against your budget"),
)


def test_nudges_survive_the_not_measured_state() -> None:
    """No crawl, but declared tools — the nudges still show."""
    brief = compose((), expected=frozenset(), unobserved=0, nudges=NUDGES)
    assert brief.state is BriefState.NOT_MEASURED
    assert brief.items == ()
    assert [n.headline for n in brief.nudges] == ["Connecting HubSpot", "Connecting Xero"]
    assert all(n.href == "/settings" for n in brief.nudges)


def test_nudges_default_to_empty() -> None:
    """A caller that passes no nudges gets the old behaviour exactly."""
    brief = compose((), expected=frozenset(), unobserved=0)
    assert brief.nudges == ()


def test_a_nudge_is_never_a_finding() -> None:
    """The two live in different fields. Against a real crawl that fails checks,
    the ranking is populated and the nudges sit beside it — never inside it, which
    is the line ADR 0029 draws."""
    brief = compose(_computations(POOR), expected=EXPECTED, unobserved=0, nudges=NUDGES)
    assert brief.state is BriefState.FINDINGS
    assert brief.items, "a poor page must produce a ranking"
    # Every nudge is a BriefNudge; no finding is, and none was manufactured from a
    # nudge's text.
    assert all(isinstance(n, BriefNudge) for n in brief.nudges)
    assert not any(isinstance(i, BriefNudge) for i in brief.items)
    assert not any(i.headline.startswith("Connecting") for i in brief.items)


def test_findings_and_nudges_coexist_without_blending() -> None:
    """A real ranking and the nudges are both present, independently counted."""
    brief = compose(_computations(POOR), expected=EXPECTED, unobserved=0, nudges=NUDGES)
    assert any(i.kind is ItemKind.CHECK_FAILED for i in brief.items)
    assert len(brief.nudges) == 2
