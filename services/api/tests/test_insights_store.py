"""The insight store records a measured figure and reads back its current head.

`domain/insights.py` is the write path (ADR 0081); `retrieval/insights.py` is the
scoped read. These tests protect two things: a half-formed insight is refused at
construction (not three frames down as an opaque IntegrityError), and `current`
returns the **newest** row per `(source, metric_key)` — because a stale head would
be a figure that looks current and is not.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import get_engine, get_sessionmaker
from app.domain.dashboards import Source
from app.domain.insights import Insight, InsightError
from app.domain.scopes import Department
from tests.dburl import async_database_url

ASYNC_DB_URL = async_database_url()
requires_db = pytest.mark.requires_db


# ── Pure: a half-formed insight is refused at construction ──────


def test_an_insight_with_no_value_is_refused() -> None:
    """Value-less is nothing. Mirrors `ck_workspace_insight_has_value`, but fails
    at construction with a message naming the metric."""
    with pytest.raises(InsightError, match="carries no value"):
        Insight(source=Source.PAGESPEED, metric_key="performance_score", provenance="PageSpeed")


def test_a_unit_without_a_number_is_refused() -> None:
    """A unit beside no number describes nothing. Mirrors
    `ck_workspace_insight_unit_needs_number`."""
    with pytest.raises(InsightError, match="no value_numeric"):
        Insight(
            source=Source.PAGESPEED,
            metric_key="performance_score",
            provenance="PageSpeed",
            value_text="fast",
            unit="score",
        )


def test_an_insight_with_no_provenance_is_refused() -> None:
    """A figure nobody can trace is the one thing this product cannot ship."""
    with pytest.raises(InsightError, match="no provenance"):
        Insight(
            source=Source.PAGESPEED,
            metric_key="performance_score",
            provenance="   ",
            value_numeric=Decimal("88"),
            unit="score",
        )


def test_a_well_formed_insight_constructs() -> None:
    insight = Insight(
        source=Source.PAGESPEED,
        metric_key="performance_score",
        provenance="PageSpeed Insights, https://acme.test/ at 09:00",
        value_numeric=Decimal("88"),
        unit="score",
        department=Department.MARKETING,
    )
    assert insight.value_numeric == Decimal("88")


# ── DB: record then read the current head ──────────────────────


@pytest.fixture
async def app_db(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[None]:
    assert ASYNC_DB_URL is not None
    monkeypatch.setenv("NEXUS_DATABASE_URL", ASYNC_DB_URL)
    monkeypatch.setenv("NEXUS_STORAGE_SIGNING_SECRET", "test-secret")
    for cache in (get_settings, get_engine, get_sessionmaker):
        cache.cache_clear()
    yield
    await get_engine().dispose()
    for cache in (get_settings, get_engine, get_sessionmaker):
        cache.cache_clear()


async def _workspace(db: AsyncSession) -> tuple[UUID, UUID]:
    user, tenant, ws = uuid4(), uuid4(), uuid4()
    await db.execute(
        sa.text("INSERT INTO app_user (id, email) VALUES (:i,:e)"),
        {"i": str(user), "e": f"insight-{user.hex[:8]}@example.com"},
    )
    await db.execute(sa.text("INSERT INTO tenant (id, name) VALUES (:i,'T')"), {"i": str(tenant)})
    await db.execute(sa.text("SELECT set_config('nexus.workspace_id', :w, true)"), {"w": str(ws)})
    await db.execute(
        sa.text(
            "INSERT INTO workspace (id, workspace_id, tenant_id, name, domain, domain_verified_at)"
            " VALUES (:i,:i,:t,'W',:d, now())"
        ),
        {"i": str(ws), "t": str(tenant), "d": f"insight-{ws.hex[:8]}.om"},
    )
    await db.commit()
    return user, ws


async def _cleanup(db: AsyncSession, user: UUID, ws: UUID) -> None:
    await db.execute(sa.text("SELECT set_config('nexus.workspace_id', :w, true)"), {"w": str(ws)})
    await db.execute(
        sa.text("DELETE FROM workspace_insight WHERE workspace_id = :w"), {"w": str(ws)}
    )
    await db.execute(sa.text("DELETE FROM workspace WHERE id = :w"), {"w": str(ws)})
    await db.execute(sa.text("DELETE FROM app_user WHERE id = :u"), {"u": str(user)})
    await db.commit()


@requires_db
async def test_current_returns_the_newest_row_per_metric(app_db: None) -> None:
    """Two captures of the same metric; `current` returns the later one, with its
    numeric value, unit and provenance intact."""
    from app.db import _unscoped_session
    from app.domain import insights

    async with _unscoped_session() as db:
        user, ws = await _workspace(db)
        try:
            await db.execute(
                sa.text("SELECT set_config('nexus.workspace_id', :w, true)"), {"w": str(ws)}
            )
            # An older capture, then a newer one of the same metric. The explicit
            # captured_at makes the ordering deterministic rather than relying on
            # two now() calls a microsecond apart.
            await db.execute(
                sa.text(
                    "INSERT INTO workspace_insight (workspace_id, source, metric_key,"
                    " value_numeric, unit, provenance, captured_at)"
                    " VALUES (:w,'pagespeed','performance_score', 61,'score','old',"
                    "         now() - interval '1 day')"
                ),
                {"w": str(ws)},
            )
            await insights.record(
                db,
                workspace_id=ws,
                insight=Insight(
                    source=Source.PAGESPEED,
                    metric_key="performance_score",
                    provenance="PageSpeed Insights, https://acme.test/",
                    value_numeric=Decimal("88"),
                    unit="score",
                    department=Department.MARKETING,
                ),
            )
            await db.commit()
            await db.execute(
                sa.text("SELECT set_config('nexus.workspace_id', :w, true)"), {"w": str(ws)}
            )

            rows = await insights.current(db, workspace_id=ws, source=Source.PAGESPEED)
            assert len(rows) == 1, "the time series collapses to one head per metric"
            head = rows[0]
            assert head.value_numeric == Decimal("88"), "the newer capture wins"
            assert head.unit == "score"
            assert head.department == "marketing"
            assert "acme.test" in head.provenance

            # A source filter that matches nothing returns nothing, not an error.
            assert await insights.current(db, workspace_id=ws, source=Source.CRM) == []
        finally:
            await _cleanup(db, user, ws)
