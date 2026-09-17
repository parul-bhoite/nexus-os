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
    """A project or a task, narrowed to what counting needs."""

    @property
    def status(self) -> str: ...

    @property
    def due_on(self) -> date | None: ...


DONE: Final = "done"
"""The one status both vocabularies share.

`ops_project` has `planned|active|blocked|done` and `ops_task` has
`todo|doing|done`, and only the terminal one means the same thing in both — which
is why this counts what is *not* done rather than enumerating what is open. A
list of open statuses would have to be kept in step with two CHECK constraints.
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
