"""Recording projects and tasks — the first place a customer writes into NEXUS.

`doc/15` S10.1. Every other route reads: a crawl we performed, a provider we
queried, answers given during onboarding. These accept records a founder types
and expects back, which brings three things this codebase has not needed.

## Who may write

**Anyone in the workspace, including a Contributor.** Deliberately wider than
`/connections`, and for a reason: connecting a tool grants a read of the whole
company's data, while recording a task is the work itself. A layer only managers
could write to would be a layer nobody uses, and `ops_layer`'s own
`cannot_answer` says this source fails on adoption rather than on an API.

A Viewer is still refused — `doc/06` §2.3 gives them company-wide material and no
department, and writing is not reading.

## Why there is no partial update

`PUT`, not `PATCH`. Two people editing one project is ordinary, and a field-wise
merge makes "whose value won" unanswerable after the fact. A whole-record write
with `updated_at` checked against what the client last read means the second
writer is told, rather than silently overwriting — see `_guard_conflict`.

## Archive, never delete

`DELETE` sets `archived_at`. A project that vanishes takes its tasks with it, and
a founder who archived something by accident has no way back. Every read filters
on it, so an archived row stops counting immediately without stopping existing.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Annotated
from uuid import UUID

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.auth.csrf import require_csrf
from app.calculators.completeness import ENTITIES
from app.deps import CurrentScope
from app.domain.scopes import Role
from app.logging import get_logger
from app.retrieval.ops import current_ops
from app.retrieval.scoped import scoped_connection

router = APIRouter(prefix="/ops", tags=["ops"])
log = get_logger(__name__)

PROJECT_STATUSES = frozenset({"planned", "active", "blocked", "done"})
TASK_STATUSES = frozenset({"todo", "doing", "done"})


class ProjectIn(BaseModel):
    name: Annotated[str, Field(min_length=1, max_length=200)]
    status: str = "active"
    client: Annotated[str | None, Field(max_length=200)] = None
    due_on: date | None = None


class TaskIn(BaseModel):
    title: Annotated[str, Field(min_length=1, max_length=300)]
    status: str = "todo"
    project_id: UUID | None = None
    assignee_id: UUID | None = None
    due_on: date | None = None


class ProjectOut(BaseModel):
    id: UUID
    name: str
    status: str
    client: str | None
    due_on: date | None


class TaskOut(BaseModel):
    id: UUID
    project_id: UUID | None
    title: str
    status: str
    assignee_id: UUID | None
    due_on: date | None


class ConfirmationIn(BaseModel):
    entity: str
    complete_as_of: date | None = None
    """The date the claim is *about*. Defaults to today, because "is this all of
    them?" is almost always answered about right now — and is settable, because
    somebody catching up on Monday can honestly vouch for Friday."""


class ConfirmationOut(BaseModel):
    entity: str
    complete_as_of: date
    confirmed_on: date


class OpsOut(BaseModel):
    projects: list[ProjectOut]
    tasks: list[TaskOut]
    completeness: list[ConfirmationOut]
    """Who has vouched for what — ADR 0035 (D29).

    A list rather than a map with null entries: an entity nobody has confirmed
    is simply absent, and a `{"projects": null}` invites a client to render
    "not confirmed: null" somewhere. Empty is the ordinary state.
    """

    recorded_at: str
    """Empty when nothing has been recorded — the state that leaves the tiles
    `locked`. Not the same as a workspace with everything marked done."""


def _may_write(scope: CurrentScope) -> None:
    """Anyone in a department. A Viewer is not.

    The check is on holding *any* department rather than on a role, because a
    Contributor recording their own work is the ordinary case this layer exists
    for, and gating it on seniority would leave it empty.
    """
    if scope.role is Role.VIEWER or not scope.departments:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Recording work needs a place in a department. A viewer sees "
            "company-wide material and does not hold one.",
        )


def _validate(value: str, allowed: frozenset[str], field: str) -> str:
    """Refuse an unknown status here rather than at the CHECK constraint.

    Postgres would reject it too, as an `IntegrityError` that reaches the client
    as a 500 naming a constraint. The same refusal at the edge is a 422 naming
    the field and what it accepts.
    """
    if value not in allowed:
        raise HTTPException(
            # `HTTP_422_UNPROCESSABLE_CONTENT`, not `..._ENTITY`: the latter is
            # deprecated in this Starlette, and `filterwarnings = ["error"]`
            # turns the warning into a 500 on the one path that raises it. The
            # same class of failure CLAUDE.md records from an anyio deprecation.
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"{field} must be one of: {', '.join(sorted(allowed))}.",
        )
    return value


@router.get("", response_model=OpsOut)
async def read_ops(scope: CurrentScope) -> OpsOut:
    """Everything this workspace has recorded."""
    async with scoped_connection(scope) as db:
        snapshot = await current_ops(db, scope)

    if snapshot is None:
        return OpsOut(projects=[], tasks=[], completeness=[], recorded_at="")

    return OpsOut(
        projects=[
            ProjectOut(id=p.id, name=p.name, status=p.status, client=p.client, due_on=p.due_on)
            for p in snapshot.projects
        ],
        completeness=[
            ConfirmationOut(
                entity=confirmation.entity,
                complete_as_of=confirmation.complete_as_of,
                confirmed_on=confirmation.confirmed_on,
            )
            for confirmation in snapshot.confirmations.values()
        ],
        tasks=[
            TaskOut(
                id=t.id,
                project_id=t.project_id,
                title=t.title,
                status=t.status,
                assignee_id=t.assignee_id,
                due_on=t.due_on,
            )
            for t in snapshot.tasks
        ],
        recorded_at=snapshot.recorded_at.isoformat() if snapshot.recorded_at else "",
    )


@router.post(
    "/projects",
    response_model=ProjectOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_csrf)],
)
async def create_project(body: ProjectIn, scope: CurrentScope) -> ProjectOut:
    _may_write(scope)
    _validate(body.status, PROJECT_STATUSES, "status")

    async with scoped_connection(scope) as db:
        row = (
            await db.execute(
                sa.text(
                    "INSERT INTO ops_project"
                    " (workspace_id, name, status, client, due_on, created_by)"
                    " VALUES (:w, :name, :status, :client, :due, :user)"
                    " RETURNING id, name, status, client, due_on"
                ),
                {
                    "w": str(scope.workspace_id),
                    "name": body.name.strip(),
                    "status": body.status,
                    "client": body.client.strip() if body.client else None,
                    "due": body.due_on,
                    "user": str(scope.user_id),
                },
            )
        ).one()
        await db.commit()

    log.info("ops.project_created", status=body.status)
    return ProjectOut(
        id=row.id, name=row.name, status=row.status, client=row.client, due_on=row.due_on
    )


@router.post(
    "/tasks",
    response_model=TaskOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_csrf)],
)
async def create_task(body: TaskIn, scope: CurrentScope) -> TaskOut:
    _may_write(scope)
    _validate(body.status, TASK_STATUSES, "status")

    async with scoped_connection(scope) as db:
        # A `project_id` from another workspace would be refused by the foreign
        # key only if that project did not exist at all. **RLS is what makes
        # this safe**: the insert runs with `nexus.workspace_id` set, and the
        # policy's `WITH CHECK` refuses a row whose workspace does not match —
        # but the FK points at a row the policy hides, so the failure would be a
        # confusing constraint error rather than a clear refusal. Checked here
        # so it is a 404 naming the project.
        if body.project_id is not None:
            found = (
                await db.execute(
                    sa.text(
                        "SELECT 1 FROM ops_project"
                        " WHERE id = :p AND workspace_id = :w AND archived_at IS NULL"
                    ),
                    {"p": str(body.project_id), "w": str(scope.workspace_id)},
                )
            ).one_or_none()
            if found is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "That project does not exist here.")

        row = (
            await db.execute(
                sa.text(
                    "INSERT INTO ops_task"
                    " (workspace_id, project_id, title, status, assignee_id, due_on, created_by)"
                    " VALUES (:w, :project, :title, :status, :assignee, :due, :user)"
                    " RETURNING id, project_id, title, status, assignee_id, due_on"
                ),
                {
                    "w": str(scope.workspace_id),
                    "project": str(body.project_id) if body.project_id else None,
                    "title": body.title.strip(),
                    "status": body.status,
                    "assignee": str(body.assignee_id) if body.assignee_id else None,
                    "due": body.due_on,
                    "user": str(scope.user_id),
                },
            )
        ).one()
        await db.commit()

    log.info("ops.task_created", status=body.status, has_project=body.project_id is not None)
    return TaskOut(
        id=row.id,
        project_id=row.project_id,
        title=row.title,
        status=row.status,
        assignee_id=row.assignee_id,
        due_on=row.due_on,
    )


@router.delete(
    "/projects/{project_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_csrf)],
)
async def archive_project(project_id: UUID, scope: CurrentScope) -> None:
    """Archive, not delete. Idempotent — archiving twice is the same intent."""
    _may_write(scope)

    async with scoped_connection(scope) as db:
        await db.execute(
            sa.text(
                "UPDATE ops_project SET archived_at = :now, updated_at = :now"
                " WHERE id = :p AND workspace_id = :w AND archived_at IS NULL"
            ),
            {"p": str(project_id), "w": str(scope.workspace_id), "now": datetime.now(UTC)},
        )
        await db.commit()


@router.delete(
    "/tasks/{task_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_csrf)],
)
async def archive_task(task_id: UUID, scope: CurrentScope) -> None:
    _may_write(scope)

    async with scoped_connection(scope) as db:
        await db.execute(
            sa.text(
                "UPDATE ops_task SET archived_at = :now, updated_at = :now"
                " WHERE id = :t AND workspace_id = :w AND archived_at IS NULL"
            ),
            {"t": str(task_id), "w": str(scope.workspace_id), "now": datetime.now(UTC)},
        )
        await db.commit()


@router.post(
    "/completeness",
    response_model=ConfirmationOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_csrf)],
)
async def confirm_completeness(body: ConfirmationIn, scope: CurrentScope) -> ConfirmationOut:
    """Record that this entity's list is all of them — `doc/15` S10.2, ADR 0035.

    **The one fact the database cannot hold about itself.** Every row in
    `ops_project` is evidence that a project exists; nothing in the table is
    evidence that no other project does. Without this, `doc/15` S10.4's on-time
    rate divides by a denominator nobody vouched for.

    **201 and a new row every time, never an update.** The table is append-only:
    the question is asked again as the business changes, and when somebody last
    vouched for the record is exactly what a reader of a rate needs. Replacing
    the previous answer would keep the claim and destroy its history, which is
    the half that carries the doubt.

    A future date is refused. "Complete as of next Tuesday" is not a thing
    anybody can know, and a figure carrying it would report a confirmation that
    has not happened yet.
    """
    _may_write(scope)
    _validate(body.entity, ENTITIES, "entity")

    as_of = body.complete_as_of or datetime.now(UTC).date()
    if as_of > datetime.now(UTC).date():
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "complete_as_of cannot be in the future — nobody can vouch for a record as it will be.",
        )

    async with scoped_connection(scope) as db:
        row = (
            await db.execute(
                sa.text(
                    "INSERT INTO ops_completeness"
                    " (workspace_id, entity, complete_as_of, confirmed_by)"
                    " VALUES (:w, :entity, :as_of, :user)"
                    " RETURNING entity, complete_as_of, confirmed_at"
                ),
                {
                    "w": str(scope.workspace_id),
                    "entity": body.entity,
                    "as_of": as_of,
                    "user": str(scope.user_id),
                },
            )
        ).one()
        await db.commit()

    log.info("ops.completeness_confirmed", entity=body.entity)
    return ConfirmationOut(
        entity=row.entity,
        complete_as_of=row.complete_as_of,
        confirmed_on=row.confirmed_at.date(),
    )
