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


_MILESTONES: Final = sa.text(
    """
    SELECT id, project_id, title, status, planned_on, updated_at
      FROM ops_milestone
     WHERE workspace_id = :w AND archived_at IS NULL
     ORDER BY planned_on, title
    """
)
"""Live milestones, soonest first.

No `NULLS LAST` here and no need for one: `planned_on` is `NOT NULL`, because
doc/05 6.3 is "milestones with planned dates" and a milestone with no date is
the one thing a timeline cannot draw.
"""

_ISSUES: Final = sa.text(
    """
    SELECT id, project_id, title, status, severity, owner_id, due_on, updated_at
      FROM ops_issue
     WHERE workspace_id = :w AND archived_at IS NULL
     ORDER BY due_on NULLS LAST, title
    """
)
"""Live issues. Ordered by date rather than by severity, because severity is
ordered in code — the column is text, so `ORDER BY severity` would sort "high"
between "low" and "medium"."""

_DISPATCHES: Final = sa.text(
    """
    SELECT id, project_id, reference, promised_on, dispatched_on, updated_at
      FROM ops_dispatch
     WHERE workspace_id = :w AND archived_at IS NULL
     ORDER BY promised_on, reference
    """
)

_STOCK: Final = sa.text(
    """
    SELECT id, name, unit, on_hand, minimum, updated_at
      FROM ops_stock_item
     WHERE workspace_id = :w AND archived_at IS NULL
     ORDER BY name
    """
)
"""Live stock lines, by name.

**Ordered here by name and by consequence in the calculator.** The shortfall is
`minimum - on_hand`, which Postgres could sort on — but ranking is a computation
the working drawer has to be able to show, and `retrieval/` putting arithmetic
in SQL is where `calculators/` stops being able to see it.
"""

_SUPPLIERS: Final = sa.text(
    """
    SELECT id, name, category, spend_minor, updated_at
      FROM ops_supplier
     WHERE workspace_id = :w AND archived_at IS NULL
     ORDER BY name
    """
)

_WORKSPACE_RULES: Final = sa.text(
    "SELECT dispatch_grace_days, reporting_currency FROM workspace WHERE id = :w"
)
"""The rule the on-time rate is computed under — ADR 0036.

`NULL` means nobody has said what late means here, and that is a gate rather
than a missing default: a number chosen by us would produce a confident
percentage under a rule the customer never agreed to.
"""

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
class Milestone:
    id: UUID
    project_id: UUID
    title: str
    status: str
    planned_on: date

    @property
    def due_on(self) -> date:
        """`Dated`'s name for it, so `count_items` needs no second shape.

        A milestone's planned date *is* the date it is late against. Two column
        names for one idea would mean two ways to be overdue, and only one of
        them would be the one the tile reads.
        """
        return self.planned_on


@dataclass(frozen=True, slots=True)
class Issue:
    id: UUID
    project_id: UUID | None
    title: str
    status: str
    severity: str
    owner_id: UUID | None
    due_on: date | None


@dataclass(frozen=True, slots=True)
class DispatchRecord:
    id: UUID
    project_id: UUID | None
    reference: str
    promised_on: date
    dispatched_on: date | None

    @property
    def status(self) -> str:
        """`Dated`'s vocabulary, so a dispatch can be counted like anything else.

        Dispatched is done. There is no `status` column on `ops_dispatch`
        because the fact is already recorded — a date means it went out — and a
        second column saying so would be a second thing to keep in step, free to
        disagree with the date beside it.
        """
        return "done" if self.dispatched_on is not None else "open"

    @property
    def due_on(self) -> date:
        """The promise is what it is late against."""
        return self.promised_on


@dataclass(frozen=True, slots=True)
class StockItem:
    id: UUID
    name: str
    unit: str | None
    on_hand: int
    minimum: int


@dataclass(frozen=True, slots=True)
class SupplierRecord:
    id: UUID
    name: str
    category: str | None
    spend_minor: int | None


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
    milestones: list[Milestone] = field(default_factory=list)
    issues: list[Issue] = field(default_factory=list)
    dispatches: list[DispatchRecord] = field(default_factory=list)
    stock: list[StockItem] = field(default_factory=list)
    suppliers: list[SupplierRecord] = field(default_factory=list)

    reporting_currency: str | None = None
    """The workspace's own, carried so a money rate can be formatted rather than
    printed in minor units."""

    grace_days: int | None = None
    """Days past the promised date before an order is late, or `None` if nobody
    has said — ADR 0036. `None` is what makes `on_time_dispatch` refuse."""

    recorded_at: datetime | None = None

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
    workspace = {"w": str(scope.workspace_id)}
    project_rows = (await db.execute(_PROJECTS, workspace)).all()
    task_rows = (await db.execute(_TASKS, workspace)).all()
    milestone_rows = (await db.execute(_MILESTONES, workspace)).all()
    issue_rows = (await db.execute(_ISSUES, workspace)).all()
    dispatch_rows = (await db.execute(_DISPATCHES, workspace)).all()
    stock_rows = (await db.execute(_STOCK, workspace)).all()
    supplier_rows = (await db.execute(_SUPPLIERS, workspace)).all()

    if not any(
        (
            project_rows,
            task_rows,
            milestone_rows,
            issue_rows,
            dispatch_rows,
            stock_rows,
            supplier_rows,
        )
    ):
        # Read before the confirmations on purpose: a workspace that has
        # recorded nothing cannot have vouched for anything, and a third round
        # trip to `us-east-2` to prove that costs a page load for no answer.
        return None

    confirmation_rows = (await db.execute(_COMPLETENESS, workspace)).all()
    rules = (await db.execute(_WORKSPACE_RULES, workspace)).one_or_none()

    stamps = [
        row.updated_at
        for rows in (
            project_rows,
            task_rows,
            milestone_rows,
            issue_rows,
            dispatch_rows,
            stock_rows,
            supplier_rows,
        )
        for row in rows
    ]

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
        milestones=[
            Milestone(
                id=row.id,
                project_id=row.project_id,
                title=row.title,
                status=row.status,
                planned_on=row.planned_on,
            )
            for row in milestone_rows
        ],
        issues=[
            Issue(
                id=row.id,
                project_id=row.project_id,
                title=row.title,
                status=row.status,
                severity=row.severity,
                owner_id=row.owner_id,
                due_on=row.due_on,
            )
            for row in issue_rows
        ],
        dispatches=[
            DispatchRecord(
                id=row.id,
                project_id=row.project_id,
                reference=row.reference,
                promised_on=row.promised_on,
                dispatched_on=row.dispatched_on,
            )
            for row in dispatch_rows
        ],
        stock=[
            StockItem(
                id=row.id,
                name=row.name,
                unit=row.unit,
                on_hand=row.on_hand,
                minimum=row.minimum,
            )
            for row in stock_rows
        ],
        suppliers=[
            SupplierRecord(
                id=row.id,
                name=row.name,
                category=row.category,
                spend_minor=row.spend_minor,
            )
            for row in supplier_rows
        ],
        grace_days=rules.dispatch_grace_days if rules else None,
        reporting_currency=rules.reporting_currency if rules else None,
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
