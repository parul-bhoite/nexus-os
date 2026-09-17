"""Projects and tasks a workspace recorded — the ops layer's first two reads.

`doc/15` S10.1. I2/I3: takes a `ScopedSession`, never a `user_id`, and the RLS
policy is the floor the explicit `workspace_id = :w` doubles — `retrieval/crawl.py`
gives the reason, which is that it makes the partial index usable and compares
the same value the policy does.

## Rows, and the counting happens elsewhere

`SELECT count(*) … GROUP BY status` would be fewer bytes and would put the
arithmetic in SQL, where `calculators/` cannot see it and the working drawer has
nothing to show. The same rule `retrieval/deals.py` follows, for the same reason.

## Archived rows are filtered here, not by the caller

`archived_at IS NULL` is in every statement rather than left to a predicate
downstream. A caller that forgot it would count a project somebody deliberately
put away, and the tile would be right about the database and wrong about the
company.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Final
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.calculators.completeness import Confirmation
from app.domain.session import ScopedSession

_PROJECTS: Final = sa.text(
    """
    SELECT id, name, status, client, due_on, updated_at
      FROM ops_project
     WHERE workspace_id = :w AND archived_at IS NULL
     ORDER BY due_on NULLS LAST, name
    """
)
"""Live projects, soonest due first.

`NULLS LAST` deliberately: a project with no date is not the most urgent thing on
the board, which is where Postgres's default for `ASC` would put it. `name` is
the tie-break so two projects due the same day do not swap places between
requests.
"""

_TASKS: Final = sa.text(
    """
    SELECT id, project_id, title, status, assignee_id, due_on, updated_at
      FROM ops_task
     WHERE workspace_id = :w AND archived_at IS NULL
     ORDER BY due_on NULLS LAST, title
    """
)


_COMPLETENESS: Final = sa.text(
    """
    SELECT DISTINCT ON (entity) entity, complete_as_of, confirmed_at
      FROM ops_completeness
     WHERE workspace_id = :w
     ORDER BY entity, confirmed_at DESC
    """
)
"""The newest confirmation per entity — ADR 0035.

`DISTINCT ON` rather than a window function or a correlated subquery: the table
is append-only, the index is `(workspace_id, entity, confirmed_at DESC)`, and
this is the shape that reads it straight. A `GROUP BY entity` with `max()` would
give the date and lose the row it came from, which is the half carrying who
said it.
"""


@dataclass(frozen=True, slots=True)
class Project:
    id: UUID
    name: str
    status: str
    client: str | None
    due_on: date | None


@dataclass(frozen=True, slots=True)
class Task:
    id: UUID
    project_id: UUID | None
    title: str
    status: str
    assignee_id: UUID | None
    due_on: date | None


@dataclass(frozen=True, slots=True)
class OpsSnapshot:
    """What this workspace has recorded, and when it last changed.

    `recorded_at` is the newest `updated_at` across both tables. It is the
    honest date for a figure built from these rows — *"as recorded on the 14th"*
    — and it is the only date available: unlike a crawl, nobody fetched anything,
    so there is no moment of measurement beyond the moment somebody typed.
    """

    projects: list[Project]
    tasks: list[Task]
    recorded_at: datetime | None

    confirmations: dict[str, Confirmation] = field(default_factory=dict)
    """The newest completeness confirmation per entity, keyed by entity.

    **Absent is the common case and the meaningful one.** A missing key means
    nobody has said whether this is all of them, which is what stops a rate
    (ADR 0035) and what the tile says in words. Defaulted so a caller building a
    snapshot in a hermetic test keeps compiling.
    """


async def current_ops(db: AsyncSession, scope: ScopedSession) -> OpsSnapshot | None:
    """This workspace's projects and tasks, or `None` if it has recorded none.

    **`None` is not an empty snapshot**, and the distinction is the whole reason
    `doc/15` lets this slice ship before D29. No rows at all means the ops layer
    has never been used: the tile is `locked` and says what would turn it on. An
    empty *list* inside a snapshot would mean somebody has used it and currently
    has nothing open, which is a real and different state.
    """
    project_rows = (await db.execute(_PROJECTS, {"w": str(scope.workspace_id)})).all()
    task_rows = (await db.execute(_TASKS, {"w": str(scope.workspace_id)})).all()

    if not project_rows and not task_rows:
        # Read before the confirmations on purpose: a workspace that has
        # recorded nothing cannot have vouched for anything, and a third round
        # trip to `us-east-2` to prove that costs a page load for no answer.
        return None

    confirmation_rows = (await db.execute(_COMPLETENESS, {"w": str(scope.workspace_id)})).all()

    stamps = [row.updated_at for row in project_rows] + [row.updated_at for row in task_rows]

    return OpsSnapshot(
        projects=[
            Project(
                id=row.id,
                name=row.name,
                status=row.status,
                client=row.client,
                due_on=row.due_on,
            )
            for row in project_rows
        ],
        tasks=[
            Task(
                id=row.id,
                project_id=row.project_id,
                title=row.title,
                status=row.status,
                assignee_id=row.assignee_id,
                due_on=row.due_on,
            )
            for row in task_rows
        ],
        recorded_at=max(stamps) if stamps else None,
        confirmations={
            row.entity: Confirmation(
                entity=row.entity,
                complete_as_of=row.complete_as_of,
                confirmed_on=row.confirmed_at.date(),
            )
            for row in confirmation_rows
        },
    )
