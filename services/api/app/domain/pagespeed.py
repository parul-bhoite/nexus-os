"""Fetch a PageSpeed score for a workspace's site and store it as an insight.

ADR 0082. Called best-effort just after onboarding completes (and, later, on
demand). Three outcomes, and two of them store nothing:

- **No key** (the shipped default): return `False`, store nothing. Absent is a
  supported state (ADR 0011) — never a zero, which would claim a measured-bad site.
- **Provider failure**: return `False`, store nothing, log the type. A failed
  telemetry fetch must never break onboarding completion, so the error is caught
  here rather than raised at the caller.
- **Success**: compute the score with the pure calculator and record one
  `workspace_insight`, provenance naming the URL and the source.

The caller's transaction must already be scoped (the GUC set) — RLS governs the
insert, so an unscoped write would be refused by the policy, not by this module.
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.calculators.pagespeed import PERFORMANCE_SCORE, PageSpeedShapeError, performance_score
from app.connectors.contracts import ConnectorError
from app.connectors.pagespeed import PageSpeedClient
from app.domain.dashboards import Source
from app.domain.insights import Insight, record
from app.domain.scopes import Department
from app.logging import get_logger

log = get_logger(__name__)


async def capture(
    db: AsyncSession, *, workspace_id: UUID, url: str, client: PageSpeedClient
) -> bool:
    """Fetch, compute and store one PageSpeed insight. Returns whether it stored.

    Best-effort by contract: the only exceptions it lets through are programming
    errors, never a provider state or a malformed payload.
    """
    if not client.available:
        log.info("pagespeed.unconfigured", workspace_id=str(workspace_id))
        return False

    try:
        payload = await client.audit(url)
        score = performance_score(payload)
    except (ConnectorError, PageSpeedShapeError) as failed:
        log.warning(
            "pagespeed.capture_failed",
            workspace_id=str(workspace_id),
            error=type(failed).__name__,
        )
        return False

    await record(
        db,
        workspace_id=workspace_id,
        insight=Insight(
            source=Source.PAGESPEED,
            metric_key=PERFORMANCE_SCORE,
            value_numeric=Decimal(score),
            unit="score",
            provenance=f"PageSpeed Insights, {url}",
            department=Department.MARKETING,
        ),
    )
    log.info("pagespeed.captured", workspace_id=str(workspace_id), score=score)
    return True
