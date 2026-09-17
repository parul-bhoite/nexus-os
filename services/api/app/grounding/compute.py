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

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from enum import StrEnum
from typing import Any, Final, Protocol

from app.calculators.audit import CategoryScore, score_brand, score_technical_seo
from app.calculators.completeness import (
    DISPATCHES,
    ISSUES,
    MILESTONES,
    PROJECTS,
    STOCK,
    SUPPLIERS,
    TASKS,
    Confirmation,
    may_compute_a_rate,
)
from app.calculators.dispatch import on_time_rate
from app.calculators.ops import (
    Bucket,
    Dated,
    Graded,
    OpsCounts,
    count_items,
    count_open_by_severity,
)
from app.calculators.pipeline import Deal, Pipeline, compute_pipeline
from app.calculators.stock import count_stock
from app.calculators.supplier import concentration
from app.domain.page_signals import PageSignals
from app.grounding.pipeline import Computed
from app.retrieval.crawl import CrawlSnapshot
from app.retrieval.ops import OpsSnapshot

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
    "sales.deals_lite": Tally(
        calculator=compute_pipeline,
        label="Deals you have recorded",
        measures=(
            "Every deal you have written down here that is not closed, counted, with "
            "the priced ones totalled. These are your own records rather than a CRM's "
            "— nothing has been checked against another system — and they are counted "
            "separately from anything a connected CRM reports."
        ),
        uncounted_label="unpriced",
        method="calculators.pipeline.compute_pipeline",
    ),
}
"""The second dispatch — **two capabilities, one calculator, two populations.**

`sales.pipeline_board` counts what a provider reported and `sales.deals_lite`
counts what somebody typed; `retrieval/deals.py` partitions the one table by
`provider` (ADR 0038). The arithmetic is identical, which is why reuse was worth
it, and the provenance is not, which is why the figures differ.

Guarded against the registry in both directions by
`test_grounding_compute.py`, which iterates every dispatch rather than naming
one — this docstring claimed that guard for a slice before it was true."""

AMOUNT_CAPABILITIES: Final[frozenset[str]] = frozenset(PIPELINE_TALLIES)
"""Which capabilities produce an amount rather than a score.

Read by `routes/dashboards._narratable`, which refuses them: `narrate-metric`
speaks in numerator and denominator, so a pipeline sentence grounded in those
keys would be grounded in nothing (ADR 0033).
"""


class Records(Protocol):
    """Picks one of a snapshot's lists. `PipelineCalculator`'s sibling."""

    def __call__(self, snapshot: OpsSnapshot) -> Sequence[Dated]: ...


class GradedRecords(Protocol):
    """Picks a list whose items carry a severity."""

    def __call__(self, snapshot: OpsSnapshot) -> Sequence[Graded]: ...


SEVERITY_ORDER: Final[tuple[str, ...]] = ("high", "medium", "low")
"""Worst first, ordered here rather than by the column.

`severity` is text, so `ORDER BY severity` sorts "high" between "low" and
"medium" — which on a figure read for triage is worse than no order at all.
"""


@dataclass(frozen=True, slots=True)
class Census:
    """One records-backed calculator, over rows the customer typed themselves.

    `Audit` and `Tally`'s third sibling (ADR 0034), and the same three fields
    for the same reason: a calculator, what it counted, and what it did not.

    The difference this kind carries is **whose rows these are**. A crawl reads
    a page that exists and a CRM is authoritative about its own deals; the ops
    layer holds what somebody remembered to type. `measures` therefore has one
    extra job here — saying that the figure counts the record rather than the
    company — and `doc/15` D29 is the open question of how we would ever know
    the two are the same.
    """

    select: Records
    """Which of the snapshot's lists this capability counts."""

    entity: str
    """Which entity's completeness confirmation vouches for this figure — ADR
    0035. `calculators.completeness.ENTITIES`' vocabulary, and not the same
    string as `noun` by accident: `noun` is rendered and `entity` is a key, and
    collapsing them would make a copy change a schema change."""

    noun: str
    """What one row is, in the plural. Rendered, so "projects" and not
    "ops_project" — and carried rather than derived from the capability id,
    which reads `task_queue` and would give "queues"."""

    label: str
    measures: str
    method: str

    open_label: str = "still open"
    """What the second number means, in the tile's own words.

    "12 projects recorded, 3 still open" is right for work and wrong for stock,
    where the same field counts lines under their minimum. Carried rather than
    hard-coded in the client, because the phrase is a fact about the record type
    and the client should not have to know which capability it is drawing.
    """

    graded: GradedRecords | None = None
    """Where the severity breakdown comes from, for the capabilities that have
    one. `None` for most: a project is not more or less severe than another
    project, and inventing a band for every record type would be a dimension
    nobody recorded."""


OPS_CENSUSES: Final[dict[str, Census]] = {
    "operations.projects_board": Census(
        select=lambda snapshot: snapshot.projects,
        entity=PROJECTS,
        noun="projects",
        label="Projects recorded",
        measures=(
            "Every project recorded in NEXUS, counted: how many are still open, how "
            "many passed a date you set, and how many were never given one. Not a "
            "completion rate and not an on-time percentage — both divide by a total "
            "only you can confirm is all of them."
        ),
        method="calculators.ops.count_items",
    ),
    "operations.task_queue": Census(
        select=lambda snapshot: snapshot.tasks,
        entity=TASKS,
        noun="tasks",
        label="Tasks recorded",
        measures=(
            "Every task recorded in NEXUS, counted: how many are still open, how many "
            "are past their due date, and how many have no due date at all. Not a "
            "throughput figure and not a workload per person — this counts what was "
            "written down, which is not the same as what is being done."
        ),
        method="calculators.ops.count_items",
    ),
    "operations.milestone_timeline": Census(
        select=lambda snapshot: snapshot.milestones,
        entity=MILESTONES,
        noun="milestones",
        label="Milestones recorded",
        measures=(
            "Every milestone recorded against a project, counted: how many are still "
            "ahead and how many passed their planned date without being marked done. "
            "Not a schedule forecast and not a slip in days — both would need a "
            "baseline nobody set when the date was first written down."
        ),
        method="calculators.ops.count_items",
    ),
    "operations.stock_levels": Census(
        select=lambda snapshot: snapshot.stock,
        entity=STOCK,
        noun="items",
        open_label="below their minimum",
        label="Stock recorded",
        measures=(
            "Every stock line recorded, counted, and how many are under the minimum "
            "you set for them — the shortest first, because one unit short of two "
            "hundred and one unit short of two are the same order to place. Not a "
            "reorder quantity: that needs lead times and consumption nobody has given "
            "us, and a number invented here would look exactly like one we measured."
        ),
        method="calculators.stock.count_stock",
    ),
    "operations.issue_register": Census(
        select=lambda snapshot: snapshot.issues,
        entity=ISSUES,
        noun="issues",
        label="Issues recorded",
        measures=(
            "Every issue recorded and not yet closed, counted and split by the "
            "severity somebody gave it. Not a resolution time and not a rate of any "
            "kind — this says what is open, which is not the same as how quickly "
            "anything gets fixed."
        ),
        method="calculators.ops.count_items",
        graded=lambda snapshot: snapshot.issues,
    ),
}
"""The third dispatch, and the first over rows NEXUS itself stores.

Guarded against the registry in both directions by `test_grounding_compute.py`,
which iterates every dispatch and separately asserts that it has not missed one.
"""

COUNT_CAPABILITIES: Final[frozenset[str]] = frozenset(OPS_CENSUSES)
"""Which capabilities produce a count rather than a score or an amount.

Read by `routes/dashboards._narratable`, which refuses them for
`AMOUNT_CAPABILITIES`' reason: `narrate-metric` speaks in numerator and
denominator, and a count has neither — a sentence grounded in those keys would
be grounded in nothing.
"""


@dataclass(frozen=True, slots=True)
class RateParts:
    """A rate, normalised, whatever produced it.

    **Added when the second rate arrived.** `RateComputation` used to hold an
    `OnTime` — the dispatch calculator's own shape — which made the figure and
    the one calculator that fed it the same thing. Supplier concentration is
    also a rate and shares none of `OnTime`'s fields, so the union's fourth arm
    would have needed a fifth for every rate after it.
    """

    numerator: int
    denominator: int
    percentage: float | None

    denominator_label: str
    """What the fraction is over, in words — "orders that went out", "of
    recorded spend". Rendered, because a rate whose denominator is unnamed is a
    number nobody can check."""

    unit: str = "count"
    """`"count"` or `"money"`. **Not inferred from `currency` being set**, because
    a workspace that has not finished its reporting settings has money with no
    currency — and a client reading `currency is None` as "these are counts"
    would print minor units at somebody as though they were order numbers."""

    currency: str | None = None
    """The workspace's reporting currency, when it has one. `None` is a real
    state: `POST /companies` deliberately does not write it (the fact is asked
    later, as a constrained choice), so a young workspace has money it cannot
    format. Never defaulted here — a currency nobody chose is a fact nobody
    gave."""

    outstanding: int = 0
    overdue: int = 0
    """Counts that sit beside the rate and are true under every refusal.
    Defaulted because not every rate has an equivalent — concentration has
    `unpriced` and uses neither."""

    excluded: int = 0
    """Recorded, and deliberately not in the denominator: an unpriced supplier,
    an order that has not gone out. The figure says so rather than folding it in
    or dropping it (I10)."""


@dataclass(frozen=True, slots=True)
class Ratio:
    """One rate-producing calculator, and what it is honest to call its output.

    `Audit`, `Tally` and `Census`'s fourth sibling (ADR 0036). Same three
    fields, same reason — plus the entity whose completeness confirmation is one
    of the two things that let it divide at all.
    """

    entity: str
    label: str
    measures: str
    method: str


OPS_RATIOS: Final[dict[str, Ratio]] = {
    "operations.supplier_risk": Ratio(
        entity=SUPPLIERS,
        label="Your largest supplier",
        measures=(
            "The share of the spend you have recorded that goes to one supplier. "
            "Not on-time delivery per supplier — that needs a record of what each one "
            "promised and when it arrived, which this layer does not hold — and not a "
            "judgement about whether that share is dangerous, which depends on how "
            "replaceable they are."
        ),
        method="calculators.supplier.concentration",
    ),
    "operations.on_time_dispatch": Ratio(
        entity=DISPATCHES,
        label="Dispatched on time",
        measures=(
            "Of the orders that actually went out, the share that left on or before "
            "the date you promised, allowing the grace you set. Orders still waiting "
            "are not in this figure at all — they are reported beside it, because "
            "dividing by work that has not happened would report a backlog as lateness."
        ),
        method="calculators.dispatch.on_time_rate",
    ),
}
"""The fourth dispatch, and the first that divides.

Guarded against the registry in both directions by `test_grounding_compute.py`,
which iterates every dispatch and separately asserts it has not missed one.
"""

RATE_CAPABILITIES: Final[frozenset[str]] = frozenset(OPS_RATIOS)


class RateRefusal(StrEnum):
    """Why a rate could not be computed. **Never a zero percent.**

    Two gates, and they refuse for different reasons, so a tile can say which
    one is missing. "We cannot tell you anything" and "answer one question and
    we can" are different messages, and only the second is actionable.
    """

    UNVOUCHED = "unvouched"
    """Nobody has confirmed the record is complete (ADR 0035), so the
    denominator may be a third of reality."""

    NO_RULE = "no_rule"
    """Nobody has said what late means here (ADR 0036, D32), so the numerator
    has no definition."""

    NOTHING_SENT = "nothing_sent"
    """The record is vouched for and the rule is set, and nothing has been
    dispatched yet — so the denominator is zero and there is genuinely no rate
    (I10). Not a refusal so much as an absence, and named separately because the
    customer has nothing left to do about it."""

    NOTHING_PRICED = "nothing_priced"
    """Suppliers are recorded and none carries a spend figure, so there is
    nothing to take a share of. Distinct from `NOTHING_SENT` because the thing
    to do about it is different: enter what you spend, rather than wait."""


@dataclass(frozen=True, slots=True)
class RateComputation:
    """A rate, the counts behind it, and why it is missing when it is."""

    capability_id: str
    label: str
    measures: str
    parts: RateParts
    confirmation: Confirmation | None
    refused: RateRefusal | None
    """`None` exactly when `rate.percentage` may be shown. The two are decided
    together, here, so no caller can render one without the other."""

    recorded_at: datetime
    computed: Computed
    trace: dict[str, Any]


def _parts_for(
    capability_id: str, snapshot: OpsSnapshot, *, today: date
) -> tuple[RateParts, RateRefusal | None]:
    """Normalise one capability's own calculator into a rate, and say what is
    missing when the answer is nothing.

    **An explicit branch per capability, not a registry of callables.** There
    are two, they have genuinely different shapes, and a dict of lambdas here
    would be indirection bought with nothing. The refusal returned is the one
    *specific to this rate* — completeness is checked by the caller, because it
    applies to every rate and has to be checked first.
    """
    if capability_id == "operations.supplier_risk":
        share = concentration(snapshot.suppliers)
        return (
            RateParts(
                numerator=share.largest_minor,
                denominator=share.total_minor,
                percentage=share.percentage,
                denominator_label="of the spend you have recorded",
                # Money, so the client formats it — or, with no reporting
                # currency set, shows the share alone rather than minor units.
                unit="money",
                currency=snapshot.reporting_currency,
                excluded=share.unpriced,
            ),
            None if share.percentage is not None else RateRefusal.NOTHING_PRICED,
        )

    rate = on_time_rate(snapshot.dispatches, today=today, grace_days=snapshot.grace_days or 0)
    specific: RateRefusal | None = None
    if snapshot.grace_days is None:
        # The rule has to exist before the numerator means anything (D32). This
        # is checked before the denominator, because a founder with no rule set
        # has something to do either way.
        specific = RateRefusal.NO_RULE
    elif rate.percentage is None:
        specific = RateRefusal.NOTHING_SENT

    return (
        RateParts(
            numerator=rate.on_time,
            denominator=rate.dispatched,
            percentage=rate.percentage,
            denominator_label="orders that went out",
            outstanding=rate.outstanding,
            overdue=rate.overdue,
            excluded=rate.outstanding,
        ),
        specific,
    )


def compute_rate_from_ops(
    capability_id: str, snapshot: OpsSnapshot, *, today: date
) -> RateComputation | None:
    """The on-time rate, or the reason there is not one.

    **Both gates are applied here rather than at the tile**, so there is exactly
    one place that decides whether a percentage may be shown. A route that
    checked them itself would be a second copy of the rule, free to drift — and
    the drift would surface as a percentage on a screen.

    The counts are computed either way. `outstanding` and `overdue` are true
    without a vouched denominator or a grace rule, and withholding them along
    with the rate would tell a founder nothing when we can honestly tell them
    something.
    """
    ratio = OPS_RATIOS.get(capability_id)
    if ratio is None:
        return None

    confirmation = snapshot.confirmations.get(ratio.entity)
    parts, specific = _parts_for(capability_id, snapshot, today=today)

    # **Completeness is checked first, whatever the rate.** Both missing is the
    # first-run state, and telling somebody to price their suppliers while we
    # also cannot trust the list sends them to do the less useful job first.
    refused: RateRefusal | None = None
    if not may_compute_a_rate(confirmation):
        refused = RateRefusal.UNVOUCHED
    else:
        refused = specific

    values: dict[str, float] = {
        "outstanding": float(parts.outstanding),
        "overdue": float(parts.overdue),
        "excluded": float(parts.excluded),
    }
    if refused is None:
        # **Only when it may be shown.** `answer._permitted` treats everything
        # here as a numeral the prose may state, so a numerator published while
        # the tile refuses would be a figure the model could write about and a
        # reader could never see.
        values.update(
            {
                "numerator": float(parts.numerator),
                "denominator": float(parts.denominator),
                "percentage": float(parts.percentage or 0.0),
            }
        )

    return RateComputation(
        capability_id=capability_id,
        label=ratio.label,
        measures=ratio.measures,
        parts=parts,
        confirmation=confirmation,
        refused=refused,
        recorded_at=snapshot.recorded_at or datetime.combine(today, datetime.min.time(), UTC),
        computed=Computed(values=values),
        trace={
            "capability": capability_id,
            "measures": ratio.measures,
            "numerator": parts.numerator,
            "denominator": parts.denominator,
            "outstanding": parts.outstanding,
            "overdue": parts.overdue,
            "excluded": parts.excluded,
            "grace_days": snapshot.grace_days,
            "refused": refused.value if refused else "",
            "source": "your own records",
            "window": f"the orders recorded as of {today.isoformat()}",
            "delta": "no_baseline",
            "method": ratio.method,
        },
    )


@dataclass(frozen=True, slots=True)
class CountComputation:
    """Counts over the customer's own records, and the working behind them.

    `recorded_at`, not `measured_at`. The other two kinds carry the moment we
    fetched something; nobody fetched this, so the only honest timestamp is the
    moment somebody typed — `retrieval/ops.py` makes the same point about the
    field it reads.
    """

    capability_id: str
    label: str
    measures: str
    noun: str
    open_label: str
    counts: OpsCounts
    breakdown: tuple[Bucket, ...]
    """Open items per severity band, or empty for a record type that has none.

    Still a count — ADR 0034 forbids dividing, not grouping. Three counts side
    by side say which to look at first without implying a proportion.
    """

    recorded_at: datetime

    confirmation: Confirmation | None
    """Somebody saying this entity's record is all of it, or `None` — ADR 0035.

    **`None` is the common case and the one that matters.** It does not stop the
    count, which is true either way; it stops any rate over it, and it is what
    the tile says in words rather than leaving a reader to assume the figure
    describes the company.
    """

    computed: Computed
    trace: dict[str, Any]


def compute_from_ops(
    capability_id: str, snapshot: OpsSnapshot, *, today: date
) -> CountComputation | None:
    """Count a workspace's recorded work, or `None` if nothing counts this.

    `None`, never a zero-valued `CountComputation` — the rule both other
    dispatches follow. **An empty list is still not `None` here**, and means
    something slightly different than it does for deals: a workspace that has
    recorded projects and no tasks has genuinely zero tasks written down. That
    it may have plenty of real ones is D29's question, and is why the figure
    says "recorded" in its own label rather than leaving the reader to assume.
    """
    census = OPS_CENSUSES.get(capability_id)
    if census is None:
        return None

    confirmation = snapshot.confirmations.get(census.entity)

    if capability_id == "operations.stock_levels":
        # **Stock is counted against a level, not a date.** A stock line has no
        # status and nothing to be overdue against, so `count_items` — which
        # counts what is not done and what is past its date — has nothing to
        # read. The shape it produces is the same: a population, the part
        # needing attention, and a ranked list of which.
        stock = count_stock(snapshot.stock)
        counts = OpsCounts(
            recorded=stock.recorded,
            open_items=stock.below_minimum,
            overdue=0,
            undated=0,
        )
        breakdown = tuple(Bucket(label=item.name, count=item.shortfall) for item in stock.shortest)
    else:
        counts = count_items(census.select(snapshot), today=today)
        breakdown = (
            count_open_by_severity(census.graded(snapshot), order=SEVERITY_ORDER)
            if census.graded is not None
            else ()
        )

    # **Every number the prose may state, and only these** — `compute_from_deals`
    # gives the reasoning. Narration is refused for counts (ADR 0034); filled in
    # correctly regardless, because a `values` written later under pressure is a
    # `values` written wrong.
    values: dict[str, float] = {
        "recorded": float(counts.recorded),
        "open": float(counts.open_items),
        "overdue": float(counts.overdue),
        "undated": float(counts.undated),
        "done": float(counts.done),
    }
    # Each band is a figure the prose may state, so each is declared. Prefixed
    # rather than bare — a key called "high" beside "open" and "overdue" reads
    # as a fourth kind of count rather than a slice of one of them.
    # Prefixed by what the band means, so a key never collides with a count and
    # never reads as one. Stock's bands are shortfalls per item, not severities.
    prefix = "short_" if capability_id == "operations.stock_levels" else "severity_"
    values.update({f"{prefix}{bucket.label}": float(bucket.count) for bucket in breakdown})

    return CountComputation(
        capability_id=capability_id,
        label=census.label,
        measures=census.measures,
        noun=census.noun,
        open_label=census.open_label,
        counts=counts,
        breakdown=breakdown,
        confirmation=confirmation,
        recorded_at=snapshot.recorded_at or datetime.combine(today, datetime.min.time(), UTC),
        computed=Computed(values=values),
        trace={
            "capability": capability_id,
            "measures": census.measures,
            "recorded": counts.recorded,
            "open": counts.open_items,
            "overdue": counts.overdue,
            "undated": counts.undated,
            "source": "your own records",
            # Part of the working, not a footnote: a reader checking a count
            # needs to know whether anybody vouched that it is all of them.
            "complete_as_of": (
                confirmation.complete_as_of.isoformat() if confirmation else "not confirmed"
            ),
            "window": f"the {census.noun} recorded as of {today.isoformat()}",
            "delta": "no_baseline",
            "method": census.method,
        },
    )


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


MEASURABLE: Final[frozenset[str]] = (
    frozenset(CRAWL_AUDITS)
    | frozenset(PIPELINE_TALLIES)
    | frozenset(OPS_CENSUSES)
    | frozenset(OPS_RATIOS)
)
"""Every capability something can put a figure on. `computes()` as a set.

**The set `domain.registry.coverage` is injected with.** That injection exists
so `domain` need not import `grounding`, and its docstring says it is only
honest "while the caller passes the real set" — which stopped being true the
day a second dispatch existed, because both the route and its test still passed
`CRAWL_AUDITS`. Coverage then reported a department as blocked while a tile in
it was showing a number.

Defined here, beside the dicts it unions, so a fourth dispatch updates it by
construction rather than by somebody remembering two call sites.
"""


def computes(capability_id: str) -> bool:
    """Whether anything can put a number on this capability's tile.

    All three dispatches. They produce different *kinds* of figure (ADR 0033,
    ADR 0034) and the question this answers is the same for each: is there a
    calculation behind this tile at all.
    """
    return capability_id in MEASURABLE


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
