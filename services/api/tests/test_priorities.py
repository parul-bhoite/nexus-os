"""Ranked actions across the ops layer — `doc/15` S10.7, ADR 0040.

The word doing the work is **ranked**. Four record types can be late in the same
unit — days past a date somebody set — so ranking them against each other
compares like with like. A severe issue with no date and a stock line eight units
short are also worth attention and are **not** measured in days; putting them in
the same ordering would need a rule converting severity, or units, into lateness.
That rule is the weighting ADR 0040 refuses.

Hermetic: `calculators/` is pure by construction.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

from app.calculators.priorities import Priorities, compose

TODAY = date(2026, 9, 17)


@dataclass(frozen=True, slots=True)
class Work:
    title: str
    status: str = "todo"
    due_on: date | None = None


@dataclass(frozen=True, slots=True)
class Snag:
    title: str
    severity: str = "high"
    status: str = "open"
    due_on: date | None = None


@dataclass(frozen=True, slots=True)
class Line:
    name: str
    on_hand: int
    minimum: int


def _compose(
    *,
    tasks: Sequence[Work] = (),
    milestones: Sequence[Work] = (),
    orders: Sequence[Work] = (),
    issues: Sequence[Snag] = (),
    stock: Sequence[Line] = (),
) -> Priorities:
    """Typed, not `**kwargs: object`.

    It was the latter, which made every `result.overdue` below an attribute on
    `object` and cost seventeen mypy errors — the same shape as `_post` in
    `test_ops_write_db.py`, made twice in one session. A helper that erases its
    own return type erases it for every assertion that uses it.
    """
    return compose(
        tasks=tasks,
        milestones=milestones,
        orders=orders,
        issues=issues,
        stock=stock,
        today=TODAY,
    )


# ── The ranking, which is days and only days ──────────────────


def test_it_ranks_by_days_past_across_record_types() -> None:
    """Like with like: a task, a milestone and an order are late in the same
    unit, so one ordering over the three is a comparison rather than a
    weighting."""
    result = _compose(
        tasks=[Work("Order glazing", due_on=date(2026, 9, 15))],
        milestones=[Work("Handover", status="planned", due_on=date(2026, 9, 1))],
        orders=[Work("SO-1", status="open", due_on=date(2026, 9, 16))],
    )

    assert [i.title for i in result.overdue] == ["Handover", "Order glazing", "SO-1"]
    assert [i.kind for i in result.overdue] == ["milestone", "task", "order"]


def test_something_due_today_is_not_yet_late() -> None:
    """The boundary every ops calculator keeps: the day is not over."""
    assert _compose(tasks=[Work("Today", due_on=TODAY)]).overdue == ()


def test_finished_work_never_appears() -> None:
    """It was late, perhaps. A queue that included delivered work sends somebody
    chasing it."""
    assert _compose(tasks=[Work("Done", status="done", due_on=date(2026, 1, 1))]).overdue == ()


def test_undated_work_is_not_late() -> None:
    """Nobody said when, so nothing is past."""
    assert _compose(tasks=[Work("Someday")]).overdue == ()


def test_the_detail_names_the_unit() -> None:
    """A number whose unit is implied is a number a reader can misread."""
    result = _compose(tasks=[Work("One", due_on=date(2026, 9, 16))])

    assert result.overdue[0].detail == "1 day past"


def test_equal_lateness_keeps_a_stable_order() -> None:
    same = date(2026, 9, 10)
    result = _compose(tasks=[Work("Zebra", due_on=same), Work("Apple", due_on=same)])

    assert [i.title for i in result.overdue] == ["Apple", "Zebra"]


# ── What is deliberately beside the ranking ───────────────────


def test_a_severe_issue_with_no_date_is_not_ranked_against_overdue_work() -> None:
    """**The refusal.** Converting "high severity" into days would be a weighting
    nobody set — ADR 0040's objection to a department score, one level down."""
    result = _compose(
        tasks=[Work("Late task", due_on=date(2026, 9, 1))],
        issues=[Snag("Roof leak")],
    )

    assert [i.title for i in result.overdue] == ["Late task"]
    assert [i.title for i in result.unranked] == ["Roof leak"]


def test_an_issue_with_a_past_date_is_ranked_like_everything_else() -> None:
    """It is late in days, so it belongs in the ordering that measures days."""
    result = _compose(issues=[Snag("Dated snag", due_on=date(2026, 9, 10))])

    assert [i.kind for i in result.overdue] == ["issue"]
    assert result.unranked == ()


def test_short_stock_sits_beside_the_ranking_and_never_in_it() -> None:
    result = _compose(
        tasks=[Work("Late", due_on=date(2026, 9, 1))],
        stock=[Line("Bolts", on_hand=2, minimum=10)],
    )

    assert [i.kind for i in result.overdue] == ["task"]
    assert [(i.title, i.detail) for i in result.unranked] == [("Bolts", "8 short")]


def test_stock_at_its_minimum_is_not_short() -> None:
    assert _compose(stock=[Line("Bolts", on_hand=10, minimum=10)]).unranked == ()


def test_the_second_list_orders_within_a_kind_and_not_across() -> None:
    """Severity ranks issues; shortfall ranks stock. Nothing compares a severity
    against a shortfall, which is the whole reason they share a list rather than
    an ordering."""
    result = _compose(
        issues=[Snag("Minor", severity="low"), Snag("Major", severity="high")],
        stock=[Line("Small", 9, 10), Line("Big", 0, 40)],
    )

    assert [i.title for i in result.unranked] == ["Major", "Minor", "Big", "Small"]


def test_a_closed_issue_is_in_neither_list() -> None:
    assert _compose(issues=[Snag("Fixed", status="done")]).unranked == ()


# ── It is not a score ─────────────────────────────────────────


def test_nothing_here_totals_or_weights_anything() -> None:
    """Every row is one record, its own number, and the date it passed. A
    founder can open any of them and see the same figure."""
    result = _compose(
        tasks=[Work("Late", due_on=date(2026, 9, 1))],
        stock=[Line("Bolts", 2, 10)],
    )

    assert not hasattr(result, "score")
    assert not hasattr(result, "points")
    assert result.total == 2, "a count of rows, not a sum of their measures"
