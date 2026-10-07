"""A declared-but-unconnected tool becomes a finish-your-setup nudge.

ADR 0083, driven through the real `observed_sources` dependency the `/surface`
route uses, against real Postgres: declare a tool, and it arrives on the brief as
a nudge with the capability its connection unlocks — the doc/09 §3 conversion
mechanism, grounded in a fact the customer gave us.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import get_engine, get_sessionmaker
from app.domain.connections import gaps_for
from app.domain.scopes import Department, Role
from app.domain.session import ScopedSession
from tests.dburl import async_database_url

ASYNC_DB_URL = async_database_url()
requires_db = pytest.mark.requires_db


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
        {"i": str(user), "e": f"nudge-{user.hex[:8]}@example.com"},
    )
    await db.execute(sa.text("INSERT INTO tenant (id, name) VALUES (:i,'T')"), {"i": str(tenant)})
    await db.execute(sa.text("SELECT set_config('nexus.workspace_id', :w, true)"), {"w": str(ws)})
    await db.execute(
        sa.text(
            "INSERT INTO workspace (id, workspace_id, tenant_id, name, domain, domain_verified_at)"
            " VALUES (:i,:i,:t,'W',:d, now())"
        ),
        {"i": str(ws), "t": str(tenant), "d": f"nudge-{ws.hex[:8]}.om"},
    )
    await db.execute(
        sa.text(
            "INSERT INTO membership (workspace_id, user_id, role, departments)"
            " VALUES (:w,:u,'owner', ARRAY['executive','sales']::text[])"
        ),
        {"w": str(ws), "u": str(user)},
    )
    # The declaration: "we run HubSpot", state 'declared' — never connected.
    await db.execute(
        sa.text(
            "INSERT INTO workspace_connection (workspace_id, provider, state, declared_by,"
            " declared_at) VALUES (:w, 'hubspot', 'declared', :u, now())"
        ),
        {"w": str(ws), "u": str(user)},
    )
    await db.commit()
    return user, ws


async def _cleanup(db: AsyncSession, user: UUID, ws: UUID) -> None:
    await db.execute(sa.text("SELECT set_config('nexus.workspace_id', :w, true)"), {"w": str(ws)})
    for stmt in (
        "DELETE FROM workspace_connection WHERE workspace_id=:w",
        "DELETE FROM membership WHERE workspace_id=:w",
        "DELETE FROM workspace WHERE id=:w",
    ):
        await db.execute(sa.text(stmt), {"w": str(ws)})
    await db.execute(sa.text("DELETE FROM app_user WHERE id=:u"), {"u": str(user)})
    await db.commit()


@requires_db
async def test_a_declared_tool_reaches_the_brief_as_a_nudge(app_db: None) -> None:
    from app.db import _unscoped_session
    from app.routes.dashboards import observed_sources

    async with _unscoped_session() as db:
        user, ws = await _workspace(db)

    try:
        scope = ScopedSession(
            user_id=user,
            tenant_id=uuid4(),
            workspace_id=ws,
            role=Role.OWNER,
            departments=frozenset({Department.EXECUTIVE, Department.SALES}),
        )
        # The real dependency the /surface route uses — its own scoped transaction.
        observed = await observed_sources(scope)
        assert "hubspot" in observed.declared_providers

        gaps = gaps_for(observed.declared_providers)
        assert any("HubSpot" in gap["unlocked_by"] for gap in gaps), (
            "a declared, unconnected HubSpot must name a connect action"
        )
        assert all(gap["topic"] for gap in gaps), "every nudge names what it unlocks"
    finally:
        async with _unscoped_session() as db:
            await _cleanup(db, user, ws)
