"""On-time dispatch — the first rate the ops layer computes. Pure.

`doc/15` S10.4, ADR 0036 (D32). Every ops figure before this one was a count,
because a count states what was recorded and is true whether or not the record
is complete. A rate divides, and dividing needs two things the layer did not
have: a denominator somebody vouched for (ADR 0035) and a definition of "late"
the customer set rather than one we chose.

## Both are the caller's problem, deliberately

This module computes; it does not decide whether it *may*. `grace_days` arrives
as an `int` because by the time anything calls this, somebody has supplied one —
`routes/dashboards` is where the refusal lives, and keeping the refusal out of
here means the arithmetic can be read and tested without a permission story
tangled through it.

## What counts, and what is left out

**The denominator is what actually went out.** An order still sitting there is
not on time and is not late in the sense this figure means — it has not been
dispatched at all, so including it would be scoring work that has not happened.
It is reported separately as `outstanding`, and the part of it that is past the
promised date as `overdue`, so the rate is never read as the whole picture.

That is the same shape `Pipeline` keeps for an unpriced deal and `OpsCounts`
keeps for an undated task: the thing that could not be counted is counted
separately rather than folded in or dropped (I10).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Protocol


class Dispatch(Protocol):
    """One promised delivery, narrowed to what the rate needs."""

    @property
    def promised_on(self) -> date: ...

    @property
    def dispatched_on(self) -> date | None: ...


@dataclass(frozen=True, slots=True)
class OnTime:
    """A rate, its two halves, and what it does not cover."""

    on_time: int
    """The numerator: dispatched on or before the promised date plus grace."""

    dispatched: int
    """The denominator: everything that actually went out. **Never the number of
    orders recorded** — that would divide by work not yet done and report a
    company as late for having a backlog."""

    outstanding: int
    """Recorded and not yet dispatched. Outside the rate entirely."""

    overdue: int
    """Of `outstanding`, the ones already past the promised date plus grace.
    A subset of `outstanding`, not an addition to it."""

    grace_days: int
    """The rule this was computed under, carried so the figure can state it. A
    percentage whose rule is invisible cannot be checked by the person it is
    about."""

    @property
    def percentage(self) -> float | None:
        """`None` when nothing has been dispatched, never `0.0`.

        A workspace that recorded ten orders and sent none has no on-time rate.
        Zero would say every one of them was late, which is a statement about
        performance rather than about the absence of data (I10).

        Rounded here, once, so the served figure and the working drawer cannot
        round differently — `ScoreFigureOut.percentage`'s reason.
        """
        if self.dispatched == 0:
            return None
        return round(self.on_time / self.dispatched * 100, 1)

    @property
    def late(self) -> int:
        """Dispatched, but after the promise. The numerator's complement, named
        rather than left for a reader to subtract."""
        return self.dispatched - self.on_time


def on_time_rate(dispatches: Sequence[Dispatch], *, today: date, grace_days: int) -> OnTime:
    """How much of what went out, went out on time.

    `today` and `grace_days` are both arguments so the boundary is testable
    without freezing the clock or reaching for a workspace — the same reason
    `compute_pipeline` and `count_items` take a `today`.

    **The deadline is `promised_on + grace_days`, and the comparison is `<=` at
    both ends.** A dispatch that went out on the deadline is on time, and one
    still outstanding *on* the deadline is not yet overdue: the day is not over,
    and calling it late at midnight would be a threshold nobody set — the same
    boundary `count_items` keeps for a task due today.
    """
    on_time = dispatched = outstanding = overdue = 0

    for item in dispatches:
        deadline = item.promised_on + timedelta(days=grace_days)
        if item.dispatched_on is not None:
            dispatched += 1
            if item.dispatched_on <= deadline:
                on_time += 1
        else:
            outstanding += 1
            if today > deadline:
                overdue += 1

    return OnTime(
        on_time=on_time,
        dispatched=dispatched,
        outstanding=outstanding,
        overdue=overdue,
        grace_days=grace_days,
    )
