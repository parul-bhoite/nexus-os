"""How much of what a company spends goes to one supplier. Pure.

`doc/15` S10.5. `operations.supplier_risk` shows *"concentration and on-time
delivery per supplier"*, and this computes the first half.

## Concentration is a share, so it stands behind the completeness gate

Unlike every stock and project count, this one **divides**. A founder who has
recorded three of their ten suppliers would be told that one of them is 60% of
their exposure — a wrong number with a plausible denominator, which is the
failure D29 exists to catch. `may_compute_a_rate` is the gate and the caller
applies it; this module computes.

## A supplier with no spend recorded is counted and left out

Not treated as zero, which would say the company spends nothing with them and
drag the share of everybody else upwards. It is the shape `Pipeline` keeps for an
unpriced deal: counted in the population, excluded from the total, and reported
separately so the figure can say what it left out (I10).

## Nothing here is called a risk

The capability is named `supplier_risk` and this returns a share. Whether 40% with
one supplier is dangerous depends on how replaceable they are, which nobody has
told us — so the figure states the concentration and the tile does not grade it.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol


class Supplied(Protocol):
    """One supplier, narrowed to what the share needs."""

    @property
    def name(self) -> str: ...

    @property
    def spend_minor(self) -> int | None: ...


@dataclass(frozen=True, slots=True)
class Concentration:
    """The largest supplier's share of recorded spend."""

    recorded: int
    """Every supplier on file, priced or not."""

    priced: int
    """How many carry a spend figure. The population the share is over."""

    unpriced: int
    """Counted, and deliberately not in the total."""

    largest_name: str
    largest_minor: int
    total_minor: int

    @property
    def percentage(self) -> float | None:
        """`None` when nothing is priced, never `0.0`.

        Zero would say the biggest supplier accounts for none of the spend,
        which is a claim about the company rather than about the absence of
        figures (I10). Rounded here, once, so the served number and the working
        drawer cannot disagree.
        """
        if self.total_minor <= 0:
            return None
        return round(self.largest_minor / self.total_minor * 100, 1)


def concentration(suppliers: Sequence[Supplied]) -> Concentration:
    """The share of recorded spend going to the largest single supplier.

    Ties are broken by name so the same data names the same supplier on every
    request — an alternating answer would read as the exposure moving when only
    the iteration order did.
    """
    priced = [s for s in suppliers if s.spend_minor is not None]
    total = sum(s.spend_minor or 0 for s in priced)

    largest_name, largest_minor = "", 0
    for supplier in sorted(priced, key=lambda s: (-(s.spend_minor or 0), s.name)):
        largest_name, largest_minor = supplier.name, supplier.spend_minor or 0
        break

    return Concentration(
        recorded=len(suppliers),
        priced=len(priced),
        unpriced=len(suppliers) - len(priced),
        largest_name=largest_name,
        largest_minor=largest_minor,
        total_minor=total,
    )
