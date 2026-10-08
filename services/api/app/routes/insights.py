"""`GET /insights` — the measured connector insights a workspace holds.

ADR 0085. The same `workspace_insight` rows the dashboard surface carries, but on
their own endpoint so the **Company Brain page can read them too**. The Brain is
reviewed during onboarding, *before* payment, so it cannot read the
entitlement-gated `/dashboards/*` surface (ADR 0084) — this route is deliberately
ungated for that reason, and like `/brain` it exposes only the caller's own
workspace through `current_insights`' `ScopedSession` (I2/I3).

It reuses `InsightOut` and `_insight_out` from the dashboards route so the two
surfaces cannot render one insight two ways — the same reason the measured tiles
share `figure_out`.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.deps import CurrentScope
from app.retrieval.insights import current_insights
from app.retrieval.scoped import scoped_connection
from app.routes.dashboards import InsightOut, _insight_out

router = APIRouter(tags=["insights"])


@router.get("/insights", response_model=list[InsightOut])
async def list_insights(scope: CurrentScope) -> list[InsightOut]:
    """Every current insight for the caller's workspace, newest per metric.

    Empty until a connector has stored one — never a fabricated placeholder.
    """
    async with scoped_connection(scope) as db:
        stored = await current_insights(db, scope)
    return [_insight_out(insight) for insight in stored]
