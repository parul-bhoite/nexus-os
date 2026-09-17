"""Stock shortfalls and supplier concentration — `doc/15` S10.5.

Two calculators, and the pair makes the layer's dividing line visible:

- **Stock is a count.** "3 of 12 below their minimum" is true whether or not the
  record is complete, so the tile works from the first row.
- **Concentration is a share.** It divides, so it stands behind D29's
  completeness gate — a founder with three of ten suppliers recorded would be
  told one of them is 60% of their exposure.

Hermetic: `calculators/` is pure by construction.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.calculators.stock import count_stock
from app.calculators.supplier import concentration


@dataclass(frozen=True, slots=True)
class Item:
    name: str
    on_hand: int
    minimum: int


@dataclass(frozen=True, slots=True)
class Vendor:
    name: str
    spend_minor: int | None


# ── Stock ─────────────────────────────────────────────────────


def test_it_counts_what_is_below_its_minimum() -> None:
    result = count_stock([Item("Bolts", 2, 10), Item("Nuts", 50, 10), Item("Glue", 0, 5)])

    assert (result.recorded, result.below_minimum, result.sufficient) == (3, 2, 1)


def test_sitting_exactly_on_the_minimum_is_not_short() -> None:
    """The boundary. An item at the level somebody set has met it, and calling
    that a shortfall would be a threshold nobody set."""
    assert count_stock([Item("Bolts", 10, 10)]).below_minimum == 0


def test_it_ranks_by_shortfall_and_not_by_ratio() -> None:
    """**"Ordered by consequence."** Each is one unit short; the ratio says the
    small item is in far worse shape, and the shortfall says they are equally
    short — which is what somebody placing an order this afternoon needs."""
    result = count_stock([Item("Rare", 1, 2), Item("Common", 199, 200), Item("Gone", 0, 40)])

    assert [item.name for item in result.shortest] == ["Gone", "Common", "Rare"]
    assert result.shortest[0].shortfall == 40


def test_a_minimum_of_zero_never_divides_anything() -> None:
    """A legitimate value meaning "hold none of this". A ratio would divide by it
    and rank an item nobody wants above everything else."""
    result = count_stock([Item("Unwanted", 0, 0), Item("Bolts", 1, 5)])

    assert result.below_minimum == 1
    assert [item.name for item in result.shortest] == ["Bolts"]


def test_equal_shortfalls_keep_a_stable_order() -> None:
    """An unstable order makes the tile look rewritten between reloads while
    saying exactly the same thing."""
    items = [Item("Zinc", 0, 5), Item("Alloy", 0, 5)]

    assert [i.name for i in count_stock(items).shortest] == ["Alloy", "Zinc"]


def test_the_ranked_list_is_capped_but_the_count_is_not() -> None:
    """A tile showing five names beside a count of twelve states both facts. A
    count that followed the cap would quietly under-report the problem."""
    items = [Item(f"Item {n}", 0, n + 1) for n in range(12)]

    result = count_stock(items, limit=5)

    assert result.below_minimum == 12
    assert len(result.shortest) == 5


def test_nothing_short_is_the_good_state_and_says_so() -> None:
    result = count_stock([Item("Bolts", 50, 10)])

    assert result.below_minimum == 0
    assert result.shortest == ()


def test_nothing_here_suggests_what_to_order() -> None:
    """A reorder quantity needs lead times, consumption and a service level —
    none of which this layer holds."""
    result = count_stock([Item("Bolts", 1, 10)])

    assert not hasattr(result, "reorder")
    assert not hasattr(result.shortest[0], "order_quantity")


# ── Supplier concentration ────────────────────────────────────


def test_it_is_the_largest_suppliers_share_of_recorded_spend() -> None:
    result = concentration([Vendor("Al Bahja", 60_000), Vendor("Gulf", 40_000)])

    assert result.largest_name == "Al Bahja"
    assert result.percentage == 60.0


def test_a_supplier_with_no_spend_is_counted_and_left_out() -> None:
    """Not treated as zero, which would say the company spends nothing with them
    and drag everybody else's share upwards (I10)."""
    result = concentration([Vendor("Al Bahja", 60_000), Vendor("Gulf", None)])

    assert (result.recorded, result.priced, result.unpriced) == (2, 1, 1)
    assert result.percentage == 100.0, "one priced supplier is all of the recorded spend"


def test_nothing_priced_is_no_share_rather_than_zero_per_cent() -> None:
    """Zero would say the biggest supplier accounts for none of the spend, which
    is a claim about the company rather than about missing figures."""
    result = concentration([Vendor("Al Bahja", None), Vendor("Gulf", None)])

    assert result.percentage is None
    assert result.recorded == 2


def test_no_suppliers_at_all_is_also_no_share() -> None:
    assert concentration([]).percentage is None


def test_a_tie_names_the_same_supplier_every_time() -> None:
    """An alternating answer reads as the exposure moving when only the
    iteration order did."""
    vendors = [Vendor("Zenith", 50_000), Vendor("Apex", 50_000)]

    assert concentration(vendors).largest_name == "Apex"
    assert concentration(list(reversed(vendors))).largest_name == "Apex"


def test_zero_spend_recorded_everywhere_is_not_a_share() -> None:
    """Somebody entering 0 for every supplier has recorded figures, and they sum
    to nothing. Dividing would raise; reporting 0% would be a claim."""
    result = concentration([Vendor("Al Bahja", 0), Vendor("Gulf", 0)])

    assert result.percentage is None


def test_nothing_here_grades_the_exposure() -> None:
    """Whether 40% with one supplier is dangerous depends on how replaceable
    they are, which nobody has told us."""
    result = concentration([Vendor("Al Bahja", 40_000), Vendor("Gulf", 60_000)])

    assert not hasattr(result, "risk")
    assert not hasattr(result, "severity")
