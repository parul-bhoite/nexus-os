"""On-time dispatch — `doc/15` S10.4, ADR 0036.

**The first ops rate**, and the one figure in the layer that divides. Everything
here is about what it refuses to divide by:

- not the orders recorded, which would score work that has not happened
- not a zero denominator, which would call a company late for having sent nothing
- not a threshold we chose, which is D32 and why `grace_days` is an argument

Hermetic: `calculators/` is pure by construction.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import pytest

from app.calculators.dispatch import OnTime, on_time_rate

TODAY = date(2026, 9, 17)
PROMISED = date(2026, 9, 10)


@dataclass(frozen=True, slots=True)
class Order:
    promised_on: date
    dispatched_on: date | None = None


def _rate(orders: list[Order], *, grace: int = 0, today: date = TODAY) -> OnTime:
    return on_time_rate(orders, today=today, grace_days=grace)


# ── The numerator and the denominator ─────────────────────────


def test_on_time_is_dispatched_on_or_before_the_promise() -> None:
    result = _rate(
        [
            Order(PROMISED, date(2026, 9, 9)),
            Order(PROMISED, PROMISED),
            Order(PROMISED, date(2026, 9, 11)),
        ]
    )

    assert (result.on_time, result.dispatched) == (2, 3)
    assert result.late == 1


def test_the_deadline_day_itself_is_on_time() -> None:
    """The boundary. Something dispatched on the promised day met the promise,
    and calling it late would be a threshold nobody set — the same boundary
    `count_items` keeps for a task due today."""
    assert _rate([Order(PROMISED, PROMISED)]).on_time == 1


def test_the_denominator_is_what_went_out_not_what_was_recorded() -> None:
    """**The division this figure must not make.** Dividing by orders recorded
    reports a company as late for having a backlog, which is a statement about
    work not yet done rather than about work done badly."""
    result = _rate([Order(PROMISED, PROMISED), Order(PROMISED), Order(PROMISED)])

    assert result.dispatched == 1
    assert result.percentage == 100.0
    assert result.outstanding == 2


def test_nothing_dispatched_is_no_rate_rather_than_zero_percent() -> None:
    """I10. A workspace that recorded ten orders and sent none has no on-time
    rate. `0%` would say every one of them was late."""
    result = _rate([Order(PROMISED), Order(PROMISED)])

    assert result.dispatched == 0
    assert result.percentage is None


def test_nothing_recorded_at_all_is_also_no_rate() -> None:
    result = _rate([])

    assert result.percentage is None
    assert (result.on_time, result.outstanding, result.overdue) == (0, 0, 0)


# ── Grace — D32, the threshold the founder sets ───────────────


def test_grace_moves_the_deadline() -> None:
    """The whole of D32. The same dispatch is late under one rule and on time
    under another, and the rule is the customer's."""
    late_by_two = [Order(PROMISED, date(2026, 9, 12))]

    assert _rate(late_by_two, grace=0).on_time == 0
    assert _rate(late_by_two, grace=1).on_time == 0
    assert _rate(late_by_two, grace=2).on_time == 1


def test_the_rule_travels_with_the_figure() -> None:
    """A percentage whose rule is invisible cannot be checked by the person it
    is about."""
    assert _rate([Order(PROMISED, PROMISED)], grace=3).grace_days == 3


def test_grace_is_an_argument_so_there_is_no_default_to_inherit() -> None:
    """**The reason the column is nullable with no server default.** A grace
    this function supplied itself would be a threshold we set for every
    workspace, silently."""
    import inspect

    signature = inspect.signature(on_time_rate)

    assert signature.parameters["grace_days"].default is inspect.Parameter.empty
    assert signature.parameters["today"].default is inspect.Parameter.empty


# ── Outstanding, and overdue within it ────────────────────────


def test_outstanding_past_the_deadline_is_overdue() -> None:
    result = _rate([Order(date(2026, 9, 1)), Order(date(2026, 12, 1))])

    assert result.outstanding == 2
    assert result.overdue == 1


def test_overdue_is_a_subset_of_outstanding_not_an_addition() -> None:
    result = _rate([Order(date(2026, 9, 1))])

    assert result.outstanding == 1
    assert result.overdue == 1


def test_an_outstanding_order_due_today_is_not_yet_overdue() -> None:
    """The day is not over. Calling it late at midnight is the threshold nobody
    set, again."""
    assert _rate([Order(TODAY)]).overdue == 0


def test_a_dispatched_order_is_never_overdue_however_late_it_was() -> None:
    """It went out. It is counted as late in the rate, which is where lateness
    belongs — an overdue queue that included delivered orders would send
    somebody chasing them."""
    result = _rate([Order(date(2026, 1, 1), date(2026, 9, 16))])

    assert result.overdue == 0
    assert result.late == 1


def test_grace_moves_the_overdue_boundary_too() -> None:
    """One rule, applied at both ends. A grace that made a dispatch on time but
    left it overdue would be two definitions of late on one tile."""
    just_past = [Order(date(2026, 9, 16))]

    assert _rate(just_past, grace=0).overdue == 1
    assert _rate(just_past, grace=5).overdue == 0


# ── It is a rate, and it adds up ──────────────────────────────


def test_the_parts_partition_what_was_recorded() -> None:
    orders = [
        Order(PROMISED, PROMISED),
        Order(PROMISED, date(2026, 9, 20)),
        Order(date(2026, 9, 1)),
        Order(date(2026, 12, 1)),
    ]
    result = _rate(orders)

    assert result.dispatched + result.outstanding == len(orders)
    assert result.on_time + result.late == result.dispatched
    assert result.overdue <= result.outstanding


@pytest.mark.parametrize(
    ("on_time", "total", "expected"),
    [(1, 3, 33.3), (2, 3, 66.7), (1, 1, 100.0), (0, 4, 0.0)],
)
def test_the_percentage_is_rounded_once_here(on_time: int, total: int, expected: float) -> None:
    """Served rather than divided by a client, so the figure and the working
    drawer cannot round differently — `ScoreFigureOut.percentage`'s reason.

    `0.0` is a real rate here and not an I10 violation: four orders went out and
    none was on time, which is a measurement rather than an absence.
    """
    orders = [Order(PROMISED, PROMISED)] * on_time + [Order(PROMISED, date(2026, 9, 30))] * (
        total - on_time
    )

    assert _rate(orders).percentage == expected
