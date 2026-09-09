"""Marketing's first real numbers: the audit scores, with their evidence.

`doc/12` P16. These are the first capabilities to flip `delivered` to true, and
what makes them safe to ship is that every one is arithmetic over something
observed on a page somebody can open.

**The scores are per-category and stay that way.** Brand and technical SEO are
never combined, and neither becomes a Marketing score — `calculators/audit.py`
says so in its own docstring and `tests/test_marketing_scoreability.py` makes it
a test. They measure the *website*: whether the title tags are sensible, whether
the pages load. Marketing performance is whether anybody arrived and what they
did, and a company with an immaculate site and no visitors would otherwise score
well on a metric named for the thing it is failing at.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from app.calculators.audit import CategoryScore
from app.domain.dashboards import Source, WidgetState
from app.domain.registry import CAPABILITIES
from app.domain.scopes import Department

# The Marketing offerings that are real once a crawl has happened. Both read
# only crawl signals, which is why they need no connector — and why they are the
# first two capabilities in the product that can honestly say `live`.
#
# **Derived, not written down.** This was a third hand-maintained set beside
# `dashboards.DELIVERED` and `registry.Capability.delivered`, and the three of
# them disagreed: this one said `3.7` and `3.8` were live while the other two
# rendered them planned. `domain/registry.py` now holds the one answer.
#
# It reads `implemented` rather than `reachable` on purpose. The calculation
# behind these two exists — that is what this module is about — and the route
# that would serve it does not, which is what `reachable` records. When the
# wiring lands, `marketing_state` becomes reachable through
# `state_for` and this function goes away.
DELIVERED_MARKETING: Final[frozenset[str]] = frozenset(
    c.doc05_id
    for c in CAPABILITIES
    if c.implemented and c.department is Department.MARKETING and c.doc05_id
)

# The keyword half of SEO Intelligence stays Locked until D2 (Q53). Recording it
# as a named absence rather than omitting the section: a founder who expects
# keyword data should see that we know it is missing and why, not a page that
# never mentions it.
KEYWORDS_LOCKED_REASON: Final = (
    "Keyword data needs a search-console connection we have not built yet. "
    "Nothing here is estimated in its place."
)


@dataclass(frozen=True, slots=True)
class ScoredCategory:
    """One audit score, its evidence, and the page it came from."""

    category: str
    score: CategoryScore
    source_url: str
    """The crawled page. A score whose page cannot be opened is a number nobody
    can check, which is the same as a number we made up."""

    @property
    def evidence_count(self) -> int:
        return len(self.score.checks)


def marketing_state(
    offering_id: str, *, crawled: bool, connected: frozenset[Source]
) -> WidgetState:
    """What a Marketing tile renders as.

    `3.1` to `3.3` are traffic, conversion and channel performance: all of them
    need GA4 and none of them can be approximated from a crawl. They render
    `LOCKED` rather than `PARTIAL`, because partial implies some of the answer is
    already there and none of it is.
    """
    if offering_id not in DELIVERED_MARKETING:
        return WidgetState.PLANNED

    if not crawled:
        # Built, and nothing has been read yet. `LOCKED` names the missing
        # input, which for these two is the crawl rather than a connector.
        return WidgetState.LOCKED

    if Source.GA4 in connected:
        return WidgetState.LIVE

    # The crawl-derived audits are complete on their own terms. They are not
    # partial versions of a GA4-backed number — they are a different number,
    # and calling them `PARTIAL` would imply GA4 would improve them.
    return WidgetState.LIVE
