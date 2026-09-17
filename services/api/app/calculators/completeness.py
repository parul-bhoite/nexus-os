"""Whether the ops layer has been vouched for. Pure, and the gate every rate passes.

`doc/15` S10.2, ADR 0035. The ops layer **fails on adoption, not on an API**:
nothing in the database distinguishes a founder who recorded three of twelve
projects from one who recorded twelve. A count survives that and a rate does
not, so a rate needs something the database cannot supply — somebody saying *"yes,
this is all of them"*.

## Why this is a module and not an `if`

The first ops rate is `doc/15` S10.4 and does not exist yet. The rule is written
before it anyway, because a rule added after the code it governs is a rule added
once somebody has already shipped around it — and the shape of that shipping is
a percentage on a screen, which is the one thing this product cannot take back.

## What it deliberately does not do

**It never judges whether a confirmation has gone stale.** A founder who
confirmed in March and stopped recording in April has a record we were told was
complete and probably is not. The mitigation is to report the date and let a
reader decide; an expiry after N days would be a threshold nobody set, and an
accurate list that simply stopped changing is indistinguishable from an
abandoned one. That was D29's staleness option, and ADR 0035 rejects it.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Final

PROJECTS: Final = "projects"
TASKS: Final = "tasks"
MILESTONES: Final = "milestones"
ISSUES: Final = "issues"

ENTITIES: Final[frozenset[str]] = frozenset({PROJECTS, TASKS, MILESTONES, ISSUES})
"""The entity kinds a founder can vouch for, today.

Per entity rather than once for the layer: somebody can plausibly have recorded
every project and a third of the tasks, and one switch covering both would let
the honest half vouch for the careless one. `doc/15` S10.3 added milestones and
issues; S10.5 adds stock and suppliers.

Kept in step with `ck_ops_completeness_entity` by hand, and a database test
asserts the two agree — a value legal here and refused by the constraint is a
500 on a write somebody was told was fine.
"""


@dataclass(frozen=True, slots=True)
class Confirmation:
    """Somebody said this entity's record was complete, and when.

    `complete_as_of` is the date the claim is *about*; `confirmed_on` is the day
    they made it. Usually the same day, and they are stored separately because a
    founder catching up on Monday can honestly say the record was complete as of
    Friday — and a figure that reported Monday would be overstating how current
    the claim is.
    """

    entity: str
    complete_as_of: date
    confirmed_on: date


def may_compute_a_rate(confirmation: Confirmation | None) -> bool:
    """**The gate.** No confirmation, no rate — ADR 0035.

    Deliberately a function over `Confirmation | None` rather than a bare
    `is not None` at each call site. There will be several call sites, they will
    be written months apart, and the question each is really asking is "may I
    divide by this?" — which deserves a name, a docstring and a test rather than
    a truthiness check somebody reads past.

    It takes the confirmation and not the counts on purpose: a rate is refused
    because nobody vouched for the denominator, never because the denominator
    happens to be small.
    """
    return confirmation is not None


def unvouched(confirmation: Confirmation | None) -> bool:
    """Whether a reader should be told the record has not been vouched for.

    The inverse of the gate, named separately because it drives copy rather than
    arithmetic, and because `if not may_compute_a_rate(...)` reads as a thing
    about rates on a tile that is showing a count.
    """
    return confirmation is None
