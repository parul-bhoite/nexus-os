"""Research progress. **Never one spinner** (Q57).

A run fans out across six independent sources, and a single spinner over the top
of them is a lie of omission: it says "working" while the crawl has already
failed, the connector was skipped, and only keywords are still going. The
founder cannot tell whether to wait, to fix something, or to walk away.

So this returns **every source with its own outcome**, including the ones that
failed and why. A screen built on it can say "your website could not be read —
it renders with JavaScript; we will use your answers and documents instead"
while three other sources are still running.

The run's own state is derived from the sources (`state_for`) rather than read
from the row, so the two can never disagree on screen — which they would the
moment a worker updated one and crashed before the other.
"""

from __future__ import annotations

from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import text

from app.auth.csrf import require_csrf
from app.deps import CurrentScope
from app.domain.research import (
    SourceKind,
    SourceState,
    Trigger,
    manual_runs_left,
    may_start,
    state_for,
)
from app.logging import get_logger
from app.retrieval.research_quota import manual_runs_this_month
from app.retrieval.scoped import scoped_connection

router = APIRouter(prefix="/research", tags=["research"])
log = get_logger(__name__)


class SourceOut(BaseModel):
    kind: str
    state: str
    error_reason: str
    """Empty unless this source failed. Never empty when it did — the schema
    enforces both halves, so a screen can trust it without checking."""

    started_at: object | None = None
    finished_at: object | None = None


class RunOut(BaseModel):
    run_id: UUID
    state: str
    """Derived from the sources, not read from the row. The two cannot disagree
    on screen — which they would the moment a worker updated one and crashed
    before the other."""

    sources: list[SourceOut]
    still_running: int
    """So a caller can decide whether to poll again without re-deriving the
    rule. One number, one meaning."""


class StartOut(BaseModel):
    run_id: UUID
    runs_left_this_month: int


@router.post(
    "",
    response_model=StartOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_csrf)],
)
async def start_run(scope: CurrentScope) -> StartOut:
    """Queue a research run, if the workspace has one left (Q55).

    Queued, not run. The work belongs to the worker — an API process that
    crawled twenty pages inline would hold a request open for five minutes and
    tie the founder's browser to it, and the whole point of the progress screen
    is that they can close the tab.

    The refusal is a **429 carrying the sentence**, not a bare status. A founder
    who cannot tell whether to wait an hour or a month gives up or asks support,
    and both are our failure rather than theirs.
    """
    async with scoped_connection(scope) as db:
        # The month is the **workspace's**, not UTC. This used to be an inline
        # `date_trunc('month', now())`, which truncates in the session timezone
        # and reset the allowance four hours early — see `research_quota.py`.
        used = await manual_runs_this_month(db, scope)

        refusal = may_start(Trigger.MANUAL, manual_this_month=used, automatic_this_week=0)
        if refusal is not None:
            raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, refusal)

        run_id = uuid4()
        await db.execute(
            text(
                "INSERT INTO research_run (id, workspace_id, state, requested_by_user_id)"
                " VALUES (:i, :w, 'queued', :u)"
            ),
            {"i": str(run_id), "w": str(scope.workspace_id), "u": str(scope.user_id)},
        )
        # Every source is created up front, queued. The progress screen can then
        # show six rows from the first moment rather than growing as workers
        # start — a list that appears one item at a time reads as things going
        # wrong.
        for kind in SourceKind:
            await db.execute(
                text(
                    "INSERT INTO research_source (workspace_id, run_id, kind, state)"
                    " VALUES (:w, :r, :k, 'queued')"
                ),
                {"w": str(scope.workspace_id), "r": str(run_id), "k": kind.value},
            )
        await db.commit()

    log.info("research.queued", run_id=str(run_id))
    return StartOut(run_id=run_id, runs_left_this_month=manual_runs_left(used + 1))


@router.get("/{run_id}", response_model=RunOut)
async def read_run(run_id: UUID, scope: CurrentScope) -> RunOut:
    """One run's progress, source by source.

    Scoped by RLS: a run id from another workspace is a 404 rather than a 403,
    because "that run exists and is not yours" confirms another company is using
    the product and roughly when.
    """
    async with scoped_connection(scope) as db:
        run = (
            await db.execute(text("SELECT id FROM research_run WHERE id = :i"), {"i": str(run_id)})
        ).first()
        if run is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "No such research run.")

        rows = (
            await db.execute(
                text(
                    "SELECT kind, state, error_reason, started_at, finished_at"
                    "  FROM research_source WHERE run_id = :i ORDER BY kind"
                ),
                {"i": str(run_id)},
            )
        ).all()

    sources = [
        SourceOut(
            kind=row.kind,
            state=row.state,
            error_reason=row.error_reason,
            started_at=row.started_at,
            finished_at=row.finished_at,
        )
        for row in rows
    ]
    states = [SourceState(row.state) for row in rows]

    return RunOut(
        run_id=run_id,
        state=state_for(states).value,
        sources=sources,
        still_running=sum(1 for s in states if s in (SourceState.QUEUED, SourceState.RUNNING)),
    )
