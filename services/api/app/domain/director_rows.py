"""The seven directors, as a row on the common surface rather than a tab rail.

`doc/14` step 6. The rail used to sit at the top of a director page and gate it,
so a founder picked a department before the product said anything. Here the
departments are a block a reader passes on the way to something else, and the
left panel is how they actually navigate.

## Four states, because four different sentences are true

`doc/13` §7's rule applied a level up: **each state has to tell the reader
something different**, and a state whose sentence is wrong is worse than no row.

- `measuring` — something here produces a figure. Open it.
- `answerable` — nothing computes, but questions are open that this reader can
  answer. Effort on their side, and it is worth naming as such.
- `waiting` — nothing computes and nothing is being asked. The department is
  waiting on a source or on us, and saying "answer some questions" would be
  sending somebody to a form that does not exist.
- `empty` — nothing at all. `doc/14` left this open and it is answered here.

## Naming the blocker rather than a generic wait

`waiting` names the source the most capabilities in that department require.
That is arithmetic over the registry, not a guess, and it is the difference
between "needs a connection" — which tells a founder nothing — and "needs your
accounting system", which tells them whether it is even relevant to them.

**It still never promises an unlock.** ADR 0030's finding holds: connecting that
source switches nothing on while the capabilities behind it have no calculator,
so the line says what is needed and not what would follow.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Collection
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from app.domain.dashboards import LABELS, Source
from app.domain.registry import TILES
from app.domain.scopes import Department


class RowState(StrEnum):
    MEASURING = "measuring"
    ANSWERABLE = "answerable"
    WAITING = "waiting"
    EMPTY = "empty"


@dataclass(frozen=True, slots=True)
class DirectorRow:
    department: Department
    measuring: int
    unanswered: int
    state: RowState
    line: str
    """Server-authored and never empty, the same rule `unlock` follows: one
    wording change has to reach every surface, and a row cannot ship with the
    space drawn and the sentence forgotten."""


def _blocker(department: Department) -> Source | None:
    """The source the most capabilities here require.

    `Counter.most_common` is deterministic for the counts but not for ties, so
    the key sorts on the source value as well — otherwise the same workspace
    gets a different sentence between requests for no reason a reader could see.
    """
    needed = Counter(
        source for c in TILES if c.department is department for source in c.required_sources
    )
    if not needed:
        return None
    return min(needed, key=lambda source: (-needed[source], source.value))


# What is alive, then what the reader can move, then what is waiting on us.
_ORDER: Final = {
    RowState.MEASURING: 0,
    RowState.ANSWERABLE: 1,
    RowState.WAITING: 2,
    RowState.EMPTY: 3,
}


def compose(
    *,
    departments: Collection[Department],
    measuring: Collection[str],
    unanswered: dict[Department, int],
    label: Callable[[Department], str],
) -> tuple[DirectorRow, ...]:
    """One row per department this reader can open, most alive first.

    `departments` arrives already filtered — by what the company runs and by
    what the caller may reach — so this function has no permission logic of its
    own to drift out of step with the nav's.

    **Ordered by state, then by the department's display name.** Sorting on the
    enum value instead looks alphabetical and is not: `hr` renders as "People",
    so it landed between Finance and Marketing and the block read as a list
    somebody had shuffled. Leading with what measures also puts the only row
    worth opening at the top, which is what a summary is for.
    """
    rows: list[DirectorRow] = []

    for department in departments:
        theirs = [c for c in TILES if c.department is department]
        measured = sum(1 for c in theirs if c.id in measuring)
        open_questions = unanswered.get(department, 0)

        if measured:
            state = RowState.MEASURING
            line = (
                f"{measured} of this department's capabilities "
                f"{'produces a figure' if measured == 1 else 'produce a figure'} today."
            )
        elif open_questions:
            state = RowState.ANSWERABLE
            # Deliberately short. The first draft appended "answering changes
            # what these capabilities will count, not whether they exist yet"
            # to every row, and on a real workspace that clause rendered five
            # times in a block of seven — noise that buried the one row saying
            # something different. The claim is made once, in the questions
            # region directly above.
            line = (
                f"{open_questions} {'question' if open_questions == 1 else 'questions'} "
                "open here, and nothing measured yet."
            )
        elif theirs:
            state = RowState.WAITING
            blocker = _blocker(department)
            line = (
                f"Nothing here can be computed yet. Most of it needs {LABELS[blocker]}."
                if blocker is not None
                else "Nothing here can be computed yet."
            )
        else:
            # `doc/14`'s open question. Unreachable today — every department in
            # the registry holds tiles — and kept because the alternative is a
            # row with an empty sentence, which is the one thing worse than a
            # row that admits there is nothing.
            state = RowState.EMPTY
            line = "Nothing is specified for this department yet."

        rows.append(
            DirectorRow(
                department=department,
                measuring=measured,
                unanswered=open_questions,
                state=state,
                line=line,
            )
        )

    return tuple(sorted(rows, key=lambda row: (_ORDER[row.state], label(row.department))))
