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

_EVERYTHING: Final = sa.text(
    """
    SELECT
      (SELECT COALESCE(json_agg(t), '[]'::json) FROM (
          SELECT id, name, status, client, due_on, updated_at
            FROM ops_project
           WHERE workspace_id = :w AND archived_at IS NULL
           ORDER BY due_on NULLS LAST, name) t)                        AS projects,
      (SELECT COALESCE(json_agg(t), '[]'::json) FROM (
          SELECT id, project_id, title, status, assignee_id, due_on, updated_at
            FROM ops_task
           WHERE workspace_id = :w AND archived_at IS NULL
           ORDER BY due_on NULLS LAST, title) t)                       AS tasks,
      (SELECT COALESCE(json_agg(t), '[]'::json) FROM (
          SELECT id, project_id, title, status, planned_on, updated_at
            FROM ops_milestone
           WHERE workspace_id = :w AND archived_at IS NULL
           ORDER BY planned_on, title) t)                              AS milestones,
      (SELECT COALESCE(json_agg(t), '[]'::json) FROM (
          SELECT id, project_id, title, status, severity, owner_id, due_on, updated_at
            FROM ops_issue
           WHERE workspace_id = :w AND archived_at IS NULL
           ORDER BY due_on NULLS LAST, title) t)                       AS issues,
      (SELECT COALESCE(json_agg(t), '[]'::json) FROM (
          SELECT id, project_id, reference, promised_on, dispatched_on, updated_at
            FROM ops_dispatch
           WHERE workspace_id = :w AND archived_at IS NULL
           ORDER BY promised_on, reference) t)                         AS dispatches,
      (SELECT COALESCE(json_agg(t), '[]'::json) FROM (
          SELECT id, name, unit, on_hand, minimum, updated_at
            FROM ops_stock_item
           WHERE workspace_id = :w AND archived_at IS NULL
           ORDER BY name) t)                                           AS stock,
      (SELECT COALESCE(json_agg(t), '[]'::json) FROM (
          SELECT id, name, category, spend_minor, updated_at
            FROM ops_supplier
           WHERE workspace_id = :w AND archived_at IS NULL
           ORDER BY name) t)                                           AS suppliers,
      (SELECT COALESCE(json_agg(t), '[]'::json) FROM (
          SELECT DISTINCT ON (entity) entity, complete_as_of, confirmed_at
            FROM ops_completeness
           WHERE workspace_id = :w
           ORDER BY entity, confirmed_at DESC) t)                      AS confirmations,
      (SELECT dispatch_grace_days FROM workspace WHERE id = :w)        AS grace_days,
      (SELECT reporting_currency FROM workspace WHERE id = :w)         AS reporting_currency
    """
)
"""Everything this workspace recorded, in **one round trip**.

This was nine statements — seven tables, the completeness log and the two
workspace rules — issued one after another on a single connection. Correct, and
nine round trips: against a Neon instance ~2s away that is eighteen seconds
before the route has composed anything, and `/dashboards/surface` crossed the
BFF's 30-second timeout in `doc/15` S10.6 as a result. The page stopped loading.

**Nothing moved into SQL except the fetching.** `retrieval/ops.py`'s standing
rule is that arithmetic belongs in `calculators/` where the working drawer can
show it — no `count(*)`, no `GROUP BY`, no share computed here. `json_agg` is a
transport: the same rows, in the same order, in one answer instead of nine.

`COALESCE(..., '[]')` so an empty table is an empty list rather than `NULL`, and
the caller has one shape to handle. `json_agg` over an ordered subquery preserves
that order, which is what keeps the lists stable between requests — the reason
each `ORDER BY` carries a second key.
"""


def _uuid(value: object) -> UUID | None:
    """JSON gives strings; the dataclasses hold `UUID`s.

    `None` in, `None` out — `project_id`, `assignee_id` and `owner_id` are all
    genuinely nullable, and a converter that raised on the ordinary case would be
    a converter nobody could use.
    """
    return UUID(str(value)) if value is not None else None


def _date(value: object) -> date | None:
    return date.fromisoformat(str(value)) if value is not None else None


def _stamp(value: object) -> datetime:
    """Postgres renders `timestamptz` into JSON as an ISO string with an offset,
    which `fromisoformat` reads directly on 3.11+. Not nullable: every row this
    reads has `updated_at NOT NULL`."""
    return datetime.fromisoformat(str(value))


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
    """This workspace's recorded work, or `None` if it has recorded none.

    **`None` is not an empty snapshot**, and the distinction is the whole reason
    `doc/15` let S10.1 ship before D29. No rows at all means the ops layer has
    never been used: the tiles are `locked` and say what would turn them on. An
    empty *list* inside a snapshot means somebody has used it and currently has
    nothing of that kind, which is a real and different state.

    One statement, nine result sets — see `_EVERYTHING`. It was nine statements
    until the surface stopped loading.
    """
    row = (await db.execute(_EVERYTHING, {"w": str(scope.workspace_id)})).one()

    projects = [
        Project(
            id=UUID(str(r["id"])),
            name=r["name"],
            status=r["status"],
            client=r["client"],
            due_on=_date(r["due_on"]),
        )
        for r in row.projects
    ]
    tasks = [
        Task(
            id=UUID(str(r["id"])),
            project_id=_uuid(r["project_id"]),
            title=r["title"],
            status=r["status"],
            assignee_id=_uuid(r["assignee_id"]),
            due_on=_date(r["due_on"]),
        )
        for r in row.tasks
    ]
    milestones = [
        Milestone(
            id=UUID(str(r["id"])),
            project_id=UUID(str(r["project_id"])),
            title=r["title"],
            status=r["status"],
            planned_on=date.fromisoformat(str(r["planned_on"])),
        )
        for r in row.milestones
    ]
    issues = [
        Issue(
            id=UUID(str(r["id"])),
            project_id=_uuid(r["project_id"]),
            title=r["title"],
            status=r["status"],
            severity=r["severity"],
            owner_id=_uuid(r["owner_id"]),
            due_on=_date(r["due_on"]),
        )
        for r in row.issues
    ]
    dispatches = [
        DispatchRecord(
            id=UUID(str(r["id"])),
            project_id=_uuid(r["project_id"]),
            reference=r["reference"],
            promised_on=date.fromisoformat(str(r["promised_on"])),
            dispatched_on=_date(r["dispatched_on"]),
        )
        for r in row.dispatches
    ]
    stock = [
        StockItem(
            id=UUID(str(r["id"])),
            name=r["name"],
            unit=r["unit"],
            on_hand=r["on_hand"],
            minimum=r["minimum"],
        )
        for r in row.stock
    ]
    suppliers = [
        SupplierRecord(
            id=UUID(str(r["id"])),
            name=r["name"],
            category=r["category"],
            spend_minor=r["spend_minor"],
        )
        for r in row.suppliers
    ]

    if not any((projects, tasks, milestones, issues, dispatches, stock, suppliers)):
        return None

    stamps = [
        _stamp(r["updated_at"])
        for rows in (
            row.projects,
            row.tasks,
            row.milestones,
            row.issues,
            row.dispatches,
            row.stock,
            row.suppliers,
        )
        for r in rows
    ]

    return OpsSnapshot(
        projects=projects,
        tasks=tasks,
        milestones=milestones,
        issues=issues,
        dispatches=dispatches,
        stock=stock,
        suppliers=suppliers,
        grace_days=row.grace_days,
        reporting_currency=row.reporting_currency,
        recorded_at=max(stamps) if stamps else None,
        confirmations={
            r["entity"]: Confirmation(
                entity=r["entity"],
                complete_as_of=date.fromisoformat(str(r["complete_as_of"])),
                confirmed_on=_stamp(r["confirmed_at"]).date(),
            )
            for r in row.confirmations
        },
    )
