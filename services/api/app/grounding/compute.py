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
from datetime import date, datetime
from typing import Any, Final, Protocol

from app.calculators.audit import CategoryScore, score_brand, score_technical_seo
from app.calculators.pipeline import Deal, Pipeline, compute_pipeline
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


class PipelineCalculator(Protocol):
    """`compute_pipeline`'s shape, keyword-only `today` included.

    A `Callable[[list[Deal], date], Pipeline]` would type-check a positional
    call this function does not accept — and `today` is keyword-only precisely
    so a date can never be passed by accident in the deals slot.
    """

    def __call__(self, deals: list[Deal], *, today: date) -> Pipeline: ...


@dataclass(frozen=True, slots=True)
class Tally:
    """One rows-backed calculator, and what it is honest to call its output.

    `Audit`'s sibling for the second figure kind (ADR 0033). The fields are
    deliberately the same three: a calculator, what it measured, and what it did
    **not** — the last being the whole defence against a correct number under a
    headline that promises more.
    """

    calculator: PipelineCalculator
    label: str
    measures: str
    uncounted_label: str
    """What the total leaves out, in this calculator's words. "unpriced" for a
    pipeline; another kind of absence elsewhere."""

    method: str
    """The dotted path a reader can go and check, declared rather than derived
    from `calculator.__name__`. It goes into `calculation_trace` and is served
    in the working drawer, so it is a contract string: deriving it would let a
    rename silently change what a stored generation claims it was computed by.
    """


PIPELINE_TALLIES: Final[dict[str, Tally]] = {
    "sales.pipeline_board": Tally(
        calculator=compute_pipeline,
        label="Open pipeline",
        measures=(
            "Every deal in your CRM that is not closed won or closed lost, counted, "
            "with the priced ones totalled. Not a forecast — no probability and no "
            "weighting by stage, because that needs history this workspace has not "
            "accrued."
        ),
        uncounted_label="unpriced",
        method="calculators.pipeline.compute_pipeline",
    ),
}
"""The second dispatch. Guarded against the registry in both directions by
`test_grounding_compute.py`, exactly as `CRAWL_AUDITS` is."""

AMOUNT_CAPABILITIES: Final[frozenset[str]] = frozenset(PIPELINE_TALLIES)
"""Which capabilities produce an amount rather than a score.

Read by `routes/dashboards._narratable`, which refuses them: `narrate-metric`
speaks in numerator and denominator, so a pipeline sentence grounded in those
keys would be grounded in nothing (ADR 0033).
"""


@dataclass(frozen=True, slots=True)
class AmountComputation:
    """A counted, totalled figure and its working.

    Carries `computed` and `trace` in the same shape `Computation` does, so the
    ledger and the narration path need no second vocabulary — even though
    nothing narrates one yet.
    """

    capability_id: str
    label: str
    measures: str
    pipeline: Pipeline
    uncounted_label: str
    source: str
    measured_at: datetime
    computed: Computed
    trace: dict[str, Any]


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
    """Whether anything can put a number on this capability's tile.

    Both dispatches. The two produce different *kinds* of figure (ADR 0033) and
    the question this answers is the same for either: is there a calculation
    behind this tile at all.
    """
    return capability_id in CRAWL_AUDITS or capability_id in PIPELINE_TALLIES


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
    passed = sum(1 for check in score.checks if check.passed)
    computed = Computed(
        values={
            "score": float(score.score),
            "max_score": float(score.max_score),
            "percentage": float(score.percentage),
            # **Both of these are here so the narrator may say "6 of 9".**
            # `BlockCard` prints "6 of 9 checks passed" three lines above where
            # the sentence goes, and `pipeline._permitted` only allows numerals
            # that appear in this dict — so without them a narrator writing the
            # figure the tile is already showing was refused as
            # `INVENTED_NUMBER`, whose meaning is "the model stated a figure no
            # calculation produced". A false accusation, rendered to the
            # customer, about the most sensitive claim this product makes.
            #
            # Both are calculator outputs: a count over its own check list and
            # that list's length. The cost is that 9 and 65 become numerals the
            # prose may state in an unrelated sense, which is why this is two
            # named outputs and not everything that would be convenient.
            "checks_passed": float(passed),
            "checks_total": float(len(score.checks)),
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
        # **Named, not left empty.** `narrate` reads `trace.get("delta", "")`
        # and the runner's grounding check passes on a present-but-empty key,
        # so the model used to receive `delta: ''` and had to guess what that
        # meant. `SKILL.md` already handles the real case: "`no_baseline` —
        # there is nothing to compare against. Say so. Never call it flat,
        # which claims a comparison you did not make."
        #
        # Set here rather than defaulted in `narrate`, because it is the
        # calculator that knows it scored one snapshot. A default there would
        # let a future calculator that genuinely computed a zero delta and
        # forgot to record it silently assert we did not compare when we did —
        # the exact inverse of the rule above.
        #
        # When re-crawling lands (M32) this becomes a real phrase, and the trap
        # to remember: a delta the prose may *state* has to go into
        # `computed.values` too, or the invented-number guard rejects every
        # sentence that mentions it. `"no_baseline"` is safe precisely because
        # it contains no numeral.
        "delta": "no_baseline",
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


def compute_from_deals(
    capability_id: str, deals: list[Deal], *, today: date, source: str, fetched_at: datetime
) -> AmountComputation | None:
    """Count and total a workspace's deals, or `None` if nothing tallies this.

    `None`, never a zero-valued `AmountComputation` — `compute_from_crawl`'s
    rule, and the same reason: a zero would say this company's pipeline is worth
    nothing where the truth is that nobody has written the calculation.

    **An empty deal list is not `None`.** A workspace with a connected CRM and no
    open deals has a real, reportable pipeline of zero, and that is a different
    statement from "we could not look".
    """
    tally = PIPELINE_TALLIES.get(capability_id)
    if tally is None:
        return None

    pipeline = tally.calculator(deals, today=today)

    # **Every number the prose may state, and only these.** `answer._permitted`
    # treats everything in `values` as a figure the model is allowed to write,
    # so an extra key here widens what an invented-number check will accept.
    # Narration is refused for amount figures today (ADR 0033), and this is
    # filled in correctly anyway: the ledger stores it, and a `values` written
    # later under pressure is a `values` written wrong.
    # `dict[str, float]`, like every other `Computed.values`. Counts are whole
    # numbers and are carried as floats because the guard that reads them
    # compares renderings, not types.
    values: dict[str, float] = {
        "count": float(pipeline.open_deals),
        "priced": float(pipeline.priced),
        "uncounted": float(pipeline.unpriced),
        "closing_within_90_days": float(pipeline.closing_within_90_days),
    }
    if pipeline.total_minor is not None:
        # Major units for the model to state, minor units for the arithmetic.
        # A sentence saying "148000 fils" would be technically true and useless.
        values["total"] = pipeline.total_minor / 100

    return AmountComputation(
        capability_id=capability_id,
        label=tally.label,
        measures=tally.measures,
        pipeline=pipeline,
        uncounted_label=tally.uncounted_label,
        source=source,
        measured_at=fetched_at,
        computed=Computed(values=values),
        trace={
            "capability": capability_id,
            "measures": tally.measures,
            "count": pipeline.open_deals,
            "total_minor": pipeline.total_minor,
            "currency": pipeline.currency,
            "uncounted": pipeline.unpriced,
            "source": source,
            "window": f"the deals as read on {fetched_at.date().isoformat()}",
            # `compute_from_crawl`'s reasoning, unchanged: named rather than
            # left empty, and never called flat.
            "delta": "no_baseline",
            "method": tally.method,
        },
    )
