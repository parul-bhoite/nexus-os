"""The insight store: a measured figure, recorded once, with its provenance.

ADR 0081. Where a connector insight lands so it is not recomputed on every page
load — the dashboard computes live from rows already in this database (I1), but a
figure derived from a **remote** fetch is not reproducible later, so it is
stored. Not the Company Brain: that holds *stated* facts; this holds *measured*
ones.

Writes go through `record` here (db + workspace_id, like `company_brain.store`);
scoped reads for the dashboard and assistant go through `retrieval/insights.py`
under a `ScopedSession`, which is the only path that may carry a caller's
authority (I2/I3). `current` here is the server-side read used by assembly paths
that already hold a `workspace_id`.

The two Python-side checks in `Insight.__post_init__` mirror the table's two
check constraints, so a bad insight fails at construction with a message naming
the problem rather than as an opaque `IntegrityError` three frames down.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.dashboards import Source
from app.domain.scopes import Department


class InsightError(ValueError):
    """An insight that carries no value, or a unit with no number to attach to."""


@dataclass(frozen=True, slots=True)
class Insight:
    """One measured figure to record. No id, no captured_at — the store sets both.

    Exactly one of `value_numeric` / `value_text` / `detail` carries the value;
    `__post_init__` refuses a row that carries none, because an insight with no
    value is nothing. A `unit` requires a `value_numeric`, because a unit beside
    no number describes nothing — the same pairing as `crm_deal`'s amount and
    currency.
    """

    source: Source
    metric_key: str
    provenance: str
    value_numeric: Decimal | None = None
    unit: str | None = None
    value_text: str | None = None
    detail: dict[str, object] | None = None
    department: Department | None = None

    def __post_init__(self) -> None:
        if self.value_numeric is None and self.value_text is None and self.detail is None:
            raise InsightError(
                f"insight {self.source.value}/{self.metric_key} carries no value;"
                " set one of value_numeric, value_text or detail"
            )
        if self.unit is not None and self.value_numeric is None:
            raise InsightError(
                f"insight {self.source.value}/{self.metric_key} has a unit {self.unit!r}"
                " but no value_numeric for it to describe"
            )
        if not self.provenance.strip():
            raise InsightError(
                f"insight {self.source.value}/{self.metric_key} has no provenance;"
                " a figure nobody can trace is the one thing this product cannot ship"
            )


@dataclass(frozen=True, slots=True)
class StoredInsight:
    """An insight as read back, with the date it was captured.

    `captured_at` travels with it for the reason `DealSnapshot.fetched_at` does:
    a figure whose date is unknown is a figure nobody can check, which for a
    reader is indistinguishable from one we invented.
    """

    source: str
    metric_key: str
    provenance: str
    captured_at: datetime
    value_numeric: Decimal | None
    unit: str | None
    value_text: str | None
    detail: dict[str, object] | None
    department: str | None


async def record(db: AsyncSession, *, workspace_id: UUID, insight: Insight) -> None:
    """Append one insight. The caller's transaction must already be scoped.

    No supersede, no upsert: the table is a time series and "current" is the
    newest row per `(source, metric_key)`. An upsert would throw away the history
    a STALE state and a trend both read from.
    """
    await db.execute(
        text(
            "INSERT INTO workspace_insight"
            " (workspace_id, source, metric_key, value_numeric, unit, value_text,"
            "  detail, provenance, department)"
            " VALUES (:w, :source, :metric, :num, :unit, :valtext,"
            "         CAST(:detail AS jsonb), :prov, :dept)"
        ),
        {
            "w": str(workspace_id),
            "source": insight.source.value,
            "metric": insight.metric_key,
            "num": insight.value_numeric,
            "unit": insight.unit,
            "valtext": insight.value_text,
            "detail": json.dumps(insight.detail) if insight.detail is not None else None,
            "prov": insight.provenance,
            "dept": insight.department.value if insight.department is not None else None,
        },
    )


async def current(
    db: AsyncSession, *, workspace_id: UUID, source: Source | None = None
) -> list[StoredInsight]:
    """The newest insight per `(source, metric_key)` for this workspace.

    `DISTINCT ON` collapses the time series to its current head; the history
    stays in the table for callers that want a trend. Optionally narrowed to one
    `source` — passed as a bound parameter (NULL means "every source") so the
    query text is a constant and no value is ever interpolated. Ordered for a
    stable surface — by source, then metric.
    """
    rows = (
        await db.execute(
            text(
                "SELECT DISTINCT ON (source, metric_key)"
                "       source, metric_key, value_numeric, unit, value_text, detail,"
                "       provenance, department, captured_at"
                "  FROM workspace_insight"
                " WHERE workspace_id = :w"
                "   AND (CAST(:source AS text) IS NULL OR source = :source)"
                " ORDER BY source, metric_key, captured_at DESC"
            ),
            {"w": str(workspace_id), "source": None if source is None else source.value},
        )
    ).all()

    return [
        StoredInsight(
            source=row.source,
            metric_key=row.metric_key,
            value_numeric=row.value_numeric,
            unit=row.unit,
            value_text=row.value_text,
            detail=row.detail,
            provenance=row.provenance,
            department=row.department,
            captured_at=row.captured_at,
        )
        for row in rows
    ]
