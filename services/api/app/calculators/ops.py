"""Counting projects and tasks. Pure, and counts only.

`doc/15` S10.1. The first ops calculator, and it is deliberately the least
ambitious one the ten ops capabilities allow.

## Why counts and not rates

The ops layer **fails on adoption, not on an API** — `domain/sources.py` says so
in its own `cannot_answer`, and `doc/15` builds the whole plan around it. A
founder who has recorded three of twelve projects gives us a database that looks
exactly like a founder who has twelve.

A **count** survives that: *"3 projects recorded, 1 overdue"* is true either way,
because it says what was recorded rather than what is the case. A **rate** does
not: *"67% on time"* over a third of reality is a wrong number with a plausible
denominator, which is the failure this product exists to prevent.

So this computes counts, and `doc/15` S10.4 — the first ops rate — waits for D29
to settle how the layer knows it holds everything.

## Overdue is a date comparison, not a judgement

`due_on` in the past and not `done`. No grace period, no "at risk" band: both
would be a threshold nobody set, and `doc/05` §0's rule about self-reported
numbers is exactly that a figure a founder typed must not be dressed as one we
measured.

A task with no `due_on` is **never overdue**. Nobody said when, so nothing is
late — the same distinction `amount_minor` keeps for an unpriced deal (I10).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from typing import Final, Protocol


class Dated(Protocol):
    """Any ops record, narrowed to what counting needs.

    A project, a task, a milestone or an issue. `due_on` is whichever date that
    record type is late against — a milestone's `planned_on` is passed in as
    this, because "the date somebody said it would happen" is one idea under two
    column names.
    """

    @property
    def status(self) -> str: ...

    @property
    def due_on(self) -> date | None: ...


class Graded(Protocol):
    """An ops record that also carries a severity."""

    @property
    def status(self) -> str: ...

    @property
    def severity(self) -> str: ...


DONE: Final = "done"
"""The one status every vocabulary shares.

`ops_project` has `planned|active|blocked|done`, `ops_task` has `todo|doing|done`,
`ops_milestone` has `planned|done` and `ops_issue` has `open|done`. Only the
terminal word means the same thing in all four — which is why this counts what is
*not* done rather than enumerating what is open. A list of open statuses would
have to be kept in step with four CHECK constraints, and `doc/15` has three more
record types to come.
"""


@dataclass(frozen=True, slots=True)
class OpsCounts:
    """What is recorded, what is open, and what is late."""

    recorded: int
    open_items: int
    overdue: int
    undated: int
    """Open items with no due date. Reported rather than dropped: `overdue`
    counts only what could be late, and a reader deciding whether "1 overdue" is
    reassuring needs to know how many were never given a date at all."""

    @property
    def done(self) -> int:
        return self.recorded - self.open_items


def count_items(items: Sequence[Dated], *, today: date) -> OpsCounts:
    """Count a list of projects or of tasks.

    One function for both, because the counting question is identical and two
    copies would be two places for "overdue" to drift apart. `today` is passed
    in so the boundary is testable without freezing the clock — the same reason
    `compute_pipeline` and `manual_runs_this_month` take one.

    `Sequence`, not `list`: `list` is invariant, so a caller holding a
    `list[Project]` could not pass it to a `list[Dated]` parameter without a
    cast — and a cast at a call site is a type check somebody turned off.
    """
    open_items = [item for item in items if item.status != DONE]

    return OpsCounts(
        recorded=len(items),
        open_items=len(open_items),
        overdue=sum(1 for item in open_items if item.due_on is not None and item.due_on < today),
        undated=sum(1 for item in open_items if item.due_on is None),
    )


@dataclass(frozen=True, slots=True)
class Bucket:
    """One severity band and how many open items are in it."""

    label: str
    count: int


def count_open_by_severity(items: Sequence[Graded], *, order: Sequence[str]) -> tuple[Bucket, ...]:
    """Open items per severity band, in the order a reader should see them.

    `doc/05` 6.9 is *"open issues by severity and owner"*, and a severity split
    is still a **count** — ADR 0034's rule is that nothing divides, not that
    nothing is grouped. Three counts side by side say which to look at first
    without implying a proportion of anything.

    **Closed items are excluded.** A register is a queue: an issue somebody
    resolved last month is not something to look at first, and counting it would
    make a tidy workspace look like a busy one.

    **`order` is passed in, and every band appears even at zero.** Alphabetical
    would put "high" between "low" and "medium", which is worse than useless on
    a figure read for triage. A band at zero is reported rather than dropped,
    because "no high-severity issues" is the reassuring thing a reader came for
    and an absent row makes them count the list to be sure.

    A severity outside `order` is counted under its own name at the end rather
    than silently discarded — the CHECK constraint should make that impossible,
    and a figure that quietly loses rows when it is not would be worse than one
    that shows an unexpected label.
    """
    open_items = [item for item in items if item.status != DONE]
    tally: dict[str, int] = {label: 0 for label in order}
    for item in open_items:
        tally[item.severity] = tally.get(item.severity, 0) + 1

    return tuple(Bucket(label=label, count=count) for label, count in tally.items())
