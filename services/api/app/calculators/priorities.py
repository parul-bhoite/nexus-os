"""What is overdue across the ops layer, ranked by how far past its date. Pure.

`doc/15` S10.7. `executive.todays_priorities` shows *"ranked actions across
departments"*, and the whole difficulty is the word **ranked**.

## The ranking rule, and the one it refuses

Four record types can be late: a task, a milestone, an order, and an issue with
a due date. They are late in exactly the same unit — **days past a date somebody
set** — so ranking them against each other is a comparison of like with like, not
a weighting we chose.

**Two things are deliberately not in that ranking.** A high-severity issue with
no due date and a stock line eight units under its minimum are both worth
attention, and neither is measured in days. Putting them in one list with the
overdue work would need a rule converting severity, or units short, into
lateness — a weighting nobody set, which is the same objection ADR 0040 raises
against a department score and ADR 0029 against a company one.

So they are returned **beside** the ranking, each ordered by its own real
measure, and the tile shows two groups rather than one false ordering.

## Nothing here is a score

No points, no weights, no total. Every row is one record, its own number, and
the date it passed — a founder can open any of them and see the same figure.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from typing import Final, Protocol

DONE: Final = "done"

SEVERITY_RANK: Final[dict[str, int]] = {"high": 0, "medium": 1, "low": 2}
"""Worst first. The order a register is read in, and **not** a weight — nothing
multiplies by it or adds it to anything. It decides position in a list of issues
and reaches no other list."""


class Overdue(Protocol):
    """Anything with a status and a date it can be past."""

    @property
    def status(self) -> str: ...

    @property
    def due_on(self) -> date | None: ...


class Graded(Protocol):
    """An issue: late like the others, or severe without being late."""

    @property
    def status(self) -> str: ...

    @property
    def due_on(self) -> date | None: ...

    @property
    def severity(self) -> str: ...


class Stocked(Protocol):
    """A stock line, which is short rather than late."""

    @property
    def on_hand(self) -> int: ...

    @property
    def minimum(self) -> int: ...


@dataclass(frozen=True, slots=True)
class Item:
    """One thing to look at, and the number that put it there."""

    kind: str
    """`task`, `milestone`, `order`, `issue`, `stock`. Rendered, and what lets a
    reader tell why two rows sit together."""

    title: str
    measure: int
    """Days past the date for the ranked list; units short, or severity rank, for
    the ones beside it. **Never compared across kinds** except within the
    overdue list, where every measure is days."""

    detail: str
    """What the measure means here, in words — "9 days past", "8 short". A number
    whose unit is implied is a number a reader can misread."""


@dataclass(frozen=True, slots=True)
class Priorities:
    """What is late, and what is worth attention but is not measured in days."""

    overdue: tuple[Item, ...]
    unranked: tuple[Item, ...]
    """High-severity issues with no date, and stock under its minimum. Beside the
    ranking rather than in it, because converting either into days would be a
    weighting nobody set."""

    @property
    def total(self) -> int:
        return len(self.overdue) + len(self.unranked)


def _days_late(item: Overdue, *, today: date) -> int | None:
    if item.status == DONE or item.due_on is None or item.due_on >= today:
        return None
    return (today - item.due_on).days


def compose(
    *,
    tasks: Sequence[Overdue],
    milestones: Sequence[Overdue],
    orders: Sequence[Overdue],
    issues: Sequence[Graded],
    stock: Sequence[Stocked],
    today: date,
    limit: int = 8,
) -> Priorities:
    """The overdue work across the ops layer, worst first, and what sits beside it.

    Each sequence is passed separately rather than as one list, because the
    `kind` a row renders with is a fact about which table it came from and
    deriving it from a duck-typed object would be guessing.

    `limit` caps each list and not the counts — a tile showing eight rows beside
    "fourteen things are late" states both facts; a count that followed the cap
    would under-report the problem.
    """
    ranked: list[Item] = []
    for kind, rows in (("task", tasks), ("milestone", milestones), ("order", orders)):
        for row in rows:
            late = _days_late(row, today=today)
            if late is None:
                continue
            ranked.append(
                Item(
                    kind=kind,
                    title=label(row),
                    measure=late,
                    detail=f"{late} {'day' if late == 1 else 'days'} past",
                )
            )

    beside: list[Item] = []
    for issue in issues:
        late = _days_late(issue, today=today)
        if late is not None:
            ranked.append(
                Item(
                    kind="issue",
                    title=label(issue),
                    measure=late,
                    detail=f"{late} {'day' if late == 1 else 'days'} past",
                )
            )
        elif issue.status != DONE and issue.severity in SEVERITY_RANK:
            # **Not converted into days.** An open high-severity issue with no
            # date is worth attention and is not late; ranking it against
            # something nine days overdue would need a weighting nobody set.
            beside.append(
                Item(
                    kind="issue",
                    title=label(issue),
                    measure=SEVERITY_RANK[issue.severity],
                    detail=f"{issue.severity} severity, no date",
                )
            )

    for item in stock:
        if item.on_hand < item.minimum:
            beside.append(
                Item(
                    kind="stock",
                    title=label(item),
                    measure=item.minimum - item.on_hand,
                    detail=f"{item.minimum - item.on_hand} short",
                )
            )

    # Worst first, then by kind and title so two things equally late do not swap
    # places between requests and make the tile look rewritten.
    ranked.sort(key=lambda row: (-row.measure, row.kind, row.title))
    # The second list is ordered *within* each kind by that kind's own measure —
    # severity rank ascending for issues, shortfall descending for stock — and
    # never across them. `kind` leads the key for exactly that reason.
    beside.sort(
        key=lambda row: (
            row.kind,
            row.measure if row.kind == "issue" else -row.measure,
            row.title,
        )
    )

    return Priorities(overdue=tuple(ranked[:limit]), unranked=tuple(beside[:limit]))


def label(row: object) -> str:
    """Whatever the record calls itself.

    The ops records use three different names for the same idea — `title` on a
    task, an issue and a milestone, `name` on a project and a stock line,
    `reference` on an order. One helper rather than a `kind`-shaped branch at
    every call site.
    """
    for attribute in ("title", "name", "reference"):
        value = getattr(row, attribute, None)
        if isinstance(value, str) and value:
            return value
    return "Untitled"
