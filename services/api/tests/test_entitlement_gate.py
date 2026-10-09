"""The dashboard is gated on entitlement, server-side. ADR 0084.

Through the real app against real Postgres: an unentitled workspace gets 402 from
`/dashboards/surface`; a paid one gets 200. RLS secures the *data* either way —
this proves the *use* gate, which is the gap a direct API call could otherwise
drive through.

`require_entitled` is deliberately **not** overridden here (every other dashboard
HTTP test overrides it, because it is not what they are testing). `current_scope`
is overridden to a seeded workspace so the test needs no real session cookie,
while the gate still reads that workspace's subscription for real.
"""

from __future__ import annotations

from collections.abc import Iterator
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from fastapi import status
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine

from app.config import get_settings
from app.db import get_engine, get_sessionmaker
from app.domain.scopes import Department, Role
from app.domain.session import ScopedSession
from app.main import create_app
from tests.dburl import async_database_url, database_url

requires_db = pytest.mark.requires_db


@pytest.fixture(scope="module")
def engine() -> Iterator[Engine]:
    url = database_url()
    assert url is not None
    made = create_engine(url, future=True)
    yield made
    made.dispose()


@pytest.fixture
def app_db(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("NEXUS_DATABASE_URL", async_database_url() or "")
    monkeypatch.setenv("NEXUS_STORAGE_SIGNING_SECRET", "test-secret")
    for cache in (get_settings, get_engine, get_sessionmaker):
        cache.cache_clear()
    yield
    for cache in (get_settings, get_engine, get_sessionmaker):
        cache.cache_clear()


def _set_ws(conn: sa.Connection, ws: UUID) -> None:
    conn.execute(sa.text("SELECT set_config('nexus.workspace_id', :w, true)"), {"w": str(ws)})


@pytest.fixture
def workspace(engine: Engine) -> Iterator[tuple[UUID, UUID]]:
    user, tenant, ws = uuid4(), uuid4(), uuid4()
    with engine.begin() as conn:
        conn.execute(
            sa.text("INSERT INTO app_user (id, email) VALUES (:i,:e)"),
            {"i": str(user), "e": f"gate-{user.hex[:8]}@example.com"},
        )
        conn.execute(sa.text("INSERT INTO tenant (id, name) VALUES (:i,'T')"), {"i": str(tenant)})
        _set_ws(conn, ws)
        conn.execute(
            sa.text(
                "INSERT INTO workspace (id, workspace_id, tenant_id, name, domain)"
                " VALUES (:i,:i,:t,'W',:d)"
            ),
            {"i": str(ws), "t": str(tenant), "d": f"gate-{ws.hex[:8]}.om"},
        )
        conn.execute(
            sa.text(
                "INSERT INTO membership (workspace_id, user_id, role, departments)"
                " VALUES (:w,:u,'owner', ARRAY['marketing']::text[])"
            ),
            {"w": str(ws), "u": str(user)},
        )
    yield user, ws
    with engine.begin() as conn:
        _set_ws(conn, ws)
        for stmt in (
            "DELETE FROM onboarding_subscription WHERE workspace_id = :w",
            "DELETE FROM membership WHERE workspace_id = :w",
            "DELETE FROM workspace WHERE id = :w",
        ):
            conn.execute(sa.text(stmt), {"w": str(ws)})
        conn.execute(sa.text("DELETE FROM app_user WHERE id = :u"), {"u": str(user)})


def _entitle(engine: Engine, ws: UUID) -> None:
    with engine.begin() as conn:
        _set_ws(conn, ws)
        conn.execute(
            sa.text(
                "INSERT INTO onboarding_subscription"
                " (workspace_id, status, amount_minor, currency, line_items, created_at)"
                " VALUES (:w, 'paid', 50000, 'OMR', CAST('[]' AS jsonb), now())"
            ),
            {"w": str(ws)},
        )


@pytest.fixture
def client(app_db: None, workspace: tuple[UUID, UUID]) -> Iterator[TestClient]:
    from app.deps import current_scope
    from app.routes.dashboards import answered_questions, running_departments

    user, ws = workspace
    app = create_app()
    app.dependency_overrides[current_scope] = lambda: ScopedSession(
        user_id=user,
        tenant_id=uuid4(),
        workspace_id=ws,
        role=Role.OWNER,
        departments=frozenset(Department),
    )
    app.dependency_overrides[running_departments] = lambda: frozenset(Department)
    app.dependency_overrides[answered_questions] = lambda: frozenset()
    # NB: require_entitled is intentionally NOT overridden — it is the thing under
    # test here.
    with TestClient(app) as made:
        yield made
    app.dependency_overrides.clear()


@requires_db
def test_an_unentitled_workspace_is_refused_with_402(
    client: TestClient, workspace: tuple[UUID, UUID]
) -> None:
    """No subscription row at all → not entitled → 402, not 200 and not a 403."""
    response = client.get("/dashboards/surface")
    assert response.status_code == status.HTTP_402_PAYMENT_REQUIRED, response.text


@requires_db
def test_a_paid_workspace_is_served(
    client: TestClient, workspace: tuple[UUID, UUID], engine: Engine
) -> None:
    _, ws = workspace
    _entitle(engine, ws)
    response = client.get("/dashboards/surface")
    assert response.status_code == 200, response.text
