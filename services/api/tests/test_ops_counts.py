"""Counting projects and tasks — `doc/15` S10.1.

The ops layer **fails on adoption, not on an API**, and this calculator is
shaped entirely by that. A founder who recorded three of twelve projects gives us
a database indistinguishable from one who recorded twelve, so:

- a **count** is true either way — it says what was recorded, not what is the case
- a **rate** is not — "67% on time" over a third of reality is a wrong number
  with a plausible denominator

These assert the counts, and assert that nothing here has quietly become a rate.
Hermetic: `calculators/` is pure by construction.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from app.calculators.ops import OpsCounts, count_items

TODAY = date(2026, 9, 17)


@dataclass(frozen=True, slots=True)
class Item:
    status: str
    due_on: date | None = None


def _counts(items: list[Item]) -> OpsCounts:
    return count_items(list(items), today=TODAY)


# ── What is open ──────────────────────────────────────────────


def test_it_counts_what_was_recorded_and_what_is_open() -> None:
    result = _counts([Item("active"), Item("done"), Item("blocked")])

    assert result.recorded == 3
    assert result.open_items == 2
    assert result.done == 1


def test_open_is_everything_that_is_not_done() -> None:
    """The two vocabularies share only the terminal status — projects are
    `planned|active|blocked|done`, tasks are `todo|doing|done`. Enumerating the
    open ones would mean a list kept in step with two CHECK constraints."""
    projects = _counts([Item("planned"), Item("active"), Item("blocked")])
    tasks = _counts([Item("todo"), Item("doing")])

    assert projects.open_items == 3
    assert tasks.open_items == 2


def test_nothing_recorded_is_all_zeroes_and_not_an_error() -> None:
    """An empty list is a workspace that has used the layer and has nothing open
    right now. *Never having used it at all* is `current_ops` returning `None`,
    which is a different state and the tile renders it differently."""
    result = _counts([])

    assert (result.recorded, result.open_items, result.overdue) == (0, 0, 0)


# ── Overdue ───────────────────────────────────────────────────


def test_overdue_is_a_past_date_on_something_still_open() -> None:
    result = _counts([Item("active", date(2026, 9, 1)), Item("active", date(2026, 12, 1))])

    assert result.overdue == 1


def test_a_finished_item_is_never_overdue() -> None:
    """It was late, perhaps. It is not outstanding, and a queue of overdue work
    that included things already delivered would send somebody chasing them."""
    result = _counts([Item("done", date(2026, 1, 1))])

    assert result.overdue == 0


def test_an_item_with_no_due_date_is_never_overdue() -> None:
    """Nobody said when, so nothing is late — the same distinction an unpriced
    deal keeps (I10). Counted separately so the figure can say so."""
    result = _counts([Item("active"), Item("active")])

    assert result.overdue == 0
    assert result.undated == 2


def test_due_today_is_not_yet_overdue() -> None:
    """The boundary. Something due today has the day to happen in, and calling it
    late at midnight would be a threshold nobody set."""
    result = _counts([Item("active", TODAY)])

    assert result.overdue == 0


def test_undated_counts_only_what_is_open() -> None:
    """A finished item with no date is not an omission worth reporting — it is
    done."""
    result = _counts([Item("done"), Item("active")])

    assert result.undated == 1


def test_the_boundary_moves_with_the_date_passed_in() -> None:
    """`today` is an argument so it is testable without freezing the clock — the
    same reason `compute_pipeline` takes one, and the lesson M33 taught about
    tests that encode the current moment."""
    items = [Item("active", date(2026, 9, 10))]

    assert count_items(items, today=date(2026, 9, 17)).overdue == 1
    assert count_items(items, today=date(2026, 9, 1)).overdue == 0


# ── It has not become a rate ──────────────────────────────────


def test_nothing_here_is_a_percentage() -> None:
    """**The rule this calculator exists under.** A rate over a partial record is
    a wrong number with a plausible denominator, and `doc/15` S10.4 — the first
    ops rate — waits for D29 to settle how the layer knows it holds everything.
    """
    result = _counts([Item("active", date(2026, 1, 1)), Item("done")])

    assert not hasattr(result, "on_time_rate")
    assert not hasattr(result, "percentage")
    assert not hasattr(result, "completion")
    assert all(
        isinstance(getattr(result, f), int)
        for f in ("recorded", "open_items", "overdue", "undated")
    )


def test_the_counts_add_up() -> None:
    """Every recorded item is done or open, and every open one is overdue,
    undated, or due in future. A count that did not partition would be
    double-counting somewhere."""
    items = [
        Item("done"),
        Item("active", date(2026, 1, 1)),
        Item("active"),
        Item("active", date(2026, 12, 1)),
    ]
    result = _counts(items)

    assert result.done + result.open_items == result.recorded
    assert result.overdue + result.undated <= result.open_items
