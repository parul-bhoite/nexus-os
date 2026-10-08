"""This workspace's measured insights, for the dashboard and assistant to read.

I2/I3: takes a `ScopedSession`, never a `user_id`, so a caller cannot supply the
scope it reads under. The RLS policy on `workspace_insight` is the floor; the
explicit `workspace_id = :w` inside `domain.insights.current` doubles it, so the
index is usable and the compared value is the same one the policy checks — the
reasoning `retrieval/deals.py` gives.

A thin boundary over `domain.insights.current` rather than a second copy of the
query: the SQL lives in one place, and this module exists to pin the *signature*
— retrieval takes authority, never identifiers.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import insights
from app.domain.dashboards import Source
from app.domain.insights import StoredInsight
from app.domain.session import ScopedSession


async def current_insights(
    db: AsyncSession, scope: ScopedSession, *, source: Source | None = None
) -> list[StoredInsight]:
    """The newest insight per `(source, metric_key)` the caller's workspace holds.

    The transaction must already be scoped (the GUC set) — `scoped_connection`
    does that — so RLS is in force on the read as well as the explicit predicate.
    """
    return await insights.current(db, workspace_id=scope.workspace_id, source=source)
