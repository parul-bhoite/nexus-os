"""Stock on hand against the minimums somebody set. Pure, and counts only.

`doc/15` S10.5. `operations.stock_levels` shows *"on hand against minimums,
ordered by consequence rather than alphabetically"*, and both halves of that
sentence are computations rather than presentation.

## Why a count and not a rate

"3 of 12 items are below their minimum" is true whether or not the record is
complete: it says what was recorded. "25% of stock is short" is not, because the
denominator is only the items somebody remembered to enter. The same rule every
ops count has followed since S10.1.

## The minimum is the founder's, and nothing here suggests a quantity

A minimum is a level somebody set for their own business, so comparing against
it is arithmetic over their number. **What to order is not.** A reorder quantity
would need lead times, consumption rates and a service level — none of which
this layer holds — and producing one anyway would be a number nobody computed
wearing the clothes of one we did.

## "Ordered by consequence" is the shortfall, not the ratio

Two items, each one unit short: one has a minimum of two and the other of two
hundred. The ratio says the first is in far worse shape; the shortfall says they
are equally short, which is what somebody placing an order this afternoon needs.
A ratio would also divide by a minimum of zero — a legitimate value meaning
"hold none of this" — and rank an item nobody wants above everything else.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol


class Stocked(Protocol):
    """One stock line, narrowed to what the comparison needs."""

    @property
    def name(self) -> str: ...

    @property
    def on_hand(self) -> int: ...

    @property
    def minimum(self) -> int: ...


@dataclass(frozen=True, slots=True)
class Short:
    """One item below its minimum, and by how much."""

    name: str
    shortfall: int


@dataclass(frozen=True, slots=True)
class StockCounts:
    """What is recorded, and what is short."""

    recorded: int
    below_minimum: int
    shortest: tuple[Short, ...]
    """The items below their minimum, worst shortfall first. Empty when nothing
    is short, which is the good state and renders as such."""

    @property
    def sufficient(self) -> int:
        return self.recorded - self.below_minimum


def count_stock(items: Sequence[Stocked], *, limit: int = 5) -> StockCounts:
    """Count what is short, and rank it by consequence.

    `limit` caps the ranked list rather than the counts — `below_minimum` is
    always the true total, so a tile showing five names beside a count of twelve
    is stating both facts rather than quietly truncating one.

    **Equal at the minimum is not short.** An item sitting exactly on the level
    somebody set has met it, and calling that a shortfall would be a threshold
    nobody set — the same boundary a task due today keeps.
    """
    short = [
        Short(name=item.name, shortfall=item.minimum - item.on_hand)
        for item in items
        if item.on_hand < item.minimum
    ]
    # Worst first, then by name so two equal shortfalls do not swap places
    # between requests and make the tile look rewritten.
    short.sort(key=lambda item: (-item.shortfall, item.name))

    return StockCounts(
        recorded=len(items),
        below_minimum=len(short),
        shortest=tuple(short[:limit]),
    )
