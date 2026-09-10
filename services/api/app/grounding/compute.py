"""Which capability a calculator answers, and the figure it produces.

**The first code in this product to put a computed number on a path that ends
at a screen.** Everything until now either computed nothing or computed it in a
test.

It lives in `grounding/` because that is where I1's boundary is drawn — beside
`pipeline.Computed`, `context.assemble` and `answer.narrate`. Two other homes
were considered and rejected: `domain/marketing.py`, because one department's
module cannot own the product's dispatch, and `calculators/`, because that
package is pure arithmetic over a `PageSignals` and must never learn that
capability ids exist.

**Pure, and asserted pure.** It takes a snapshot, not a session, which mirrors
the shape `routes/dashboards.py::director_setup` already uses — read once,
then shape. A dispatch that took a session would have to be awaited per tile,
turning one round trip into one per capability.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final

from app.calculators.audit import CategoryScore, score_brand, score_technical_seo
from app.domain.page_signals import PageSignals
from app.grounding.pipeline import Computed
from app.retrieval.crawl import CrawlSnapshot

Calculator = Callable[[PageSignals], CategoryScore]


@dataclass(frozen=True, slots=True)
class Audit:
    """One crawl-backed calculator, and what it is honest to call its output."""

    calculator: Calculator

    label: str
    """What was measured — deliberately **not** the capability's name.

    `marketing.seo_gaps` is presented as "SEO Intelligence" and this measures
    its technical half; `marketing.brand_intelligence` is presented as "Brand
    Intelligence" and this measures whether the site is legible, not how it
    writes. A figure carrying the capability's name would answer a question
    nobody asked.
    """

    measures: str
    """One sentence naming exactly what was counted, **and what was not.**

    This field is the whole defence against the worst thing this slice could
    ship: a correctly-computed number under a headline that misdescribes it.
    That is not an I1 violation in the letter — the arithmetic is real — but it
    is one in spirit, and it is the failure a reader would never detect.
    `tests/test_grounding_compute.py` asserts the sentence exists, exceeds a
    length, and contains a "Not …" clause.
    """


CRAWL_AUDITS: Final[dict[str, Audit]] = {
    "marketing.seo_gaps": Audit(
        calculator=score_technical_seo,
        label="Technical SEO",
        measures=(
            "Nine checks on the one page we fetched: HTTPS, whether search engines "
            "are allowed to index it, a canonical link, description length, "
            "structured data, a declared language, image alt text, internal links "
            "and subheadings. Not keyword volumes, difficulty or rankings — those "
            "need a keyword data source this workspace has not got."
        ),
    ),
    "marketing.brand_intelligence": Audit(
        calculator=score_brand,
        label="Site legibility",
        measures=(
            "Nine checks on whether a first-time visitor can tell what you do: a "
            "title and its length, a description, exactly one h1, enough words to "
            "read, contact details, social links and Open Graph tags. Not voice "
            "consistency, positioning or messaging gaps — reading how you write "
            "needs your own documents and a language model."
        ),
    ),
}
"""The dispatch. Two entries, and both capabilities were already in the
registry's `_IMPLEMENTED` before this module existed — which was true and
useless, because nothing could call the calculators.

`tests/test_grounding_compute.py` guards this dict against the registry in
**both** directions. A calculator wired to an unreachable capability is dead
code that reads as live; a reachable capability with no calculator renders a
figure state with no figure, which is a blank space where a number belongs.
"""


@dataclass(frozen=True, slots=True)
class Computation:
    """A figure, the numbers behind it, and the working. All three or none.

    `computed` and `trace` are exactly the pair `answer.narrate` takes, down to
    the key names, so slice 2 is wiring rather than reshaping.
    """

    capability_id: str
    score: CategoryScore
    source_url: str
    measured_at: datetime
    label: str
    measures: str
    computed: Computed
    trace: dict[str, Any]

    @property
    def checks_passed(self) -> int:
        return sum(1 for check in self.score.checks if check.passed)


def computes(capability_id: str) -> bool:
    """Whether anything can put a number on this capability's tile."""
    return capability_id in CRAWL_AUDITS


def compute_from_crawl(capability_id: str, snapshot: CrawlSnapshot) -> Computation | None:
    """Score one page for one capability, or `None` if nothing scores it.

    `None`, never a zero-scored `Computation`. I10: a zero would say this
    company scored nothing, where the truth is that nobody has written the
    calculation — and the two must not be the same object, because the tile
    renders them differently and a reader reads them differently.
    """
    audit = CRAWL_AUDITS.get(capability_id)
    if audit is None:
        return None

    score = audit.calculator(snapshot.signals)

    # **Every number, and only these numbers.** `answer._permitted` treats
    # everything in `values` as a figure the model may write, so an extra key
    # here would be a licence to state something no calculator produced.
    computed = Computed(
        values={
            "score": float(score.score),
            "max_score": float(score.max_score),
            "percentage": float(score.percentage),
        }
    )

    trace: dict[str, Any] = {
        "method": f"calculators.audit.{audit.calculator.__name__}",
        "capability": capability_id,
        "category": score.category,
        "measures": audit.measures,
        "numerator": score.score,
        "denominator": score.max_score,
        "percentage": score.percentage,
        "page": snapshot.url,
        "pages_captured": snapshot.pages_captured,
        "window": f"the page as fetched on {snapshot.captured_at.date().isoformat()}",
        # The working, in the calculator's own words. `Check.evidence` is
        # specified as an observation rather than advice, and this carries it
        # through unrestated — a summary here would be a second account of
        # arithmetic that happened somewhere else.
        "checks": [
            {
                "id": check.id,
                "label": check.label,
                "passed": check.passed,
                "weight": check.weight,
                "evidence": check.evidence,
            }
            for check in score.checks
        ],
    }

    return Computation(
        capability_id=capability_id,
        score=score,
        source_url=snapshot.url,
        measured_at=snapshot.captured_at,
        label=audit.label,
        measures=audit.measures,
        computed=computed,
        trace=trace,
    )
