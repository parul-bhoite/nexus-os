"""The pipeline, counted and totalled. Pure, and no model anywhere near it.

`doc/14` step 9's calculator — the half that makes connecting HubSpot visible.
`calculators/` contains no model and no I/O; this takes rows that are already in
the database and returns arithmetic.

## A pipeline is not a score, and this does not pretend otherwise

`calculators/audit.py` produces a `CategoryScore`: a numerator, a denominator
and nine weighted checks. That shape is right for an audit and **wrong for
money**. What is the denominator of a pipeline? There isn't one, and inventing a
target to divide by would be manufacturing a figure the customer never gave us —
I1's exact prohibition, arriving as a helpful-looking percentage.

So this returns its own shape: a count, a total, and the deals it could not add
up. Whether the dashboard can *render* that is a separate and unsettled
question, named in `doc/14` — `FigureOut` today carries `score`, `max_score` and
`percentage`, and none of those means anything here.

## Unpriced deals are counted, never zeroed

A deal nobody has priced is not a deal worth nothing. `unpriced` is part of the
answer rather than a detail dropped on the way, because *"OMR 148,000 across 23
deals"* and *"OMR 148,000 across 23 deals, 3 of which have no value on them"*
are different statements and only the second is true.

## One currency, or none

Deals in two currencies cannot be added. The alternative — converting — needs a
rate, a rate needs a source and a date, and a total built from a rate nobody can
see is exactly the kind of number this product refuses. So a mixed pipeline
totals nothing and says so; the count still holds.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Final

OPEN_STAGES_EXCLUDED: Final[frozenset[str]] = frozenset({"closedwon", "closedlost"})
"""HubSpot's two terminal stages.

Named rather than inferred from a `closed` prefix: a customer can rename a stage
to "Closed - pending paperwork", and a substring match would drop it from the
pipeline silently. A pipeline that quietly shrinks is worse than one that is
wrong in a visible way.
"""


@dataclass(frozen=True, slots=True)
class Deal:
    """One deal, as the calculator needs it. Not the provider's shape."""

    external_id: str
    amount_minor: int | None
    currency: str | None
    stage: str | None
    closes_on: date | None


@dataclass(frozen=True, slots=True)
class Pipeline:
    """What is open, what it is worth, and what could not be counted."""

    open_deals: int
    total_minor: int | None
    """`None` when nothing could be totalled — no priced deals at all, or more
    than one currency. Never `0` standing in for "we could not add these up"
    (I10); a genuinely empty pipeline reports `open_deals = 0` with a total of
    zero in the currency it found, and that is a different sentence."""

    currency: str | None
    unpriced: int
    """Open deals with no amount on them. Part of the answer: a total that did
    not say how many deals it left out is a total presented as complete."""

    closing_within_90_days: int
    """The only time-based cut this makes. Not a forecast — no probability, no
    weighting by stage — because `sales.forecast` requires `history` and this
    capability does not have it."""

    @property
    def priced(self) -> int:
        return self.open_deals - self.unpriced


def _is_open(deal: Deal) -> bool:
    return (deal.stage or "").lower() not in OPEN_STAGES_EXCLUDED


def compute_pipeline(deals: list[Deal], *, today: date) -> Pipeline:
    """Count and total the open pipeline.

    `today` is passed in rather than read from the clock, so the ninety-day
    window is testable without freezing time — the same reason
    `research_quota.manual_runs_this_month` takes a `now`.
    """
    open_deals = [deal for deal in deals if _is_open(deal)]
    priced = [d for d in open_deals if d.amount_minor is not None and d.currency]
    currencies = {d.currency for d in priced}

    # More than one currency: the count still holds, the total cannot. Adding
    # them would need a rate, and a rate needs a source and a date nobody has.
    total = sum(d.amount_minor or 0 for d in priced) if len(currencies) == 1 else None
    currency = next(iter(currencies)) if len(currencies) == 1 else None

    return Pipeline(
        open_deals=len(open_deals),
        total_minor=total,
        currency=currency,
        unpriced=len(open_deals) - len(priced),
        closing_within_90_days=sum(
            1
            for d in open_deals
            if d.closes_on is not None and 0 <= (d.closes_on - today).days <= 90
        ),
    )
