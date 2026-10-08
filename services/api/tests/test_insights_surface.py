"""A stored insight reaches both surfaces: the dashboard and the Brain. ADR 0085.

Through the real app against real Postgres. A `workspace_insight` row (as PageSpeed
would write on completion) must appear:

- on `/dashboards/surface` in its own `insights` region (not as a calculator tile);
- on `/insights`, the ungated endpoint the Brain page reads before payment;

each carrying its provenance and capture date — the honesty the store exists for.

`require_entitled` is overridden for the surface call (this is the insights test,
not the paywall's); `/insights` is ungated by design, so it needs no override.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
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
            {"i": str(user), "e": f"ins-{user.hex[:8]}@example.com"},
        )
        conn.execute(sa.text("INSERT INTO tenant (id, name) VALUES (:i,'T')"), {"i": str(tenant)})
        _set_ws(conn, ws)
        conn.execute(
            sa.text(
                "INSERT INTO workspace (id, workspace_id, tenant_id, name, domain)"
                " VALUES (:i,:i,:t,'W',:d)"
            ),
            {"i": str(ws), "t": str(tenant), "d": f"ins-{ws.hex[:8]}.om"},
        )
        conn.execute(
            sa.text(
                "INSERT INTO membership (workspace_id, user_id, role, departments)"
                " VALUES (:w,:u,'owner', ARRAY['marketing']::text[])"
            ),
            {"w": str(ws), "u": str(user)},
        )
        conn.execute(
            sa.text(
                "INSERT INTO workspace_insight (workspace_id, source, metric_key, value_numeric,"
                " unit, provenance, department, captured_at)"
                " VALUES (:w, 'pagespeed', 'performance_score', 88, 'score',"
                "         'PageSpeed Insights, https://ins.om/', 'marketing', :at)"
            ),
            {"w": str(ws), "at": datetime(2026, 10, 8, 9, 0, tzinfo=UTC)},
        )
    yield user, ws
    with engine.begin() as conn:
        _set_ws(conn, ws)
        for stmt in (
            "DELETE FROM workspace_insight WHERE workspace_id = :w",
            "DELETE FROM membership WHERE workspace_id = :w",
            "DELETE FROM workspace WHERE id = :w",
        ):
            conn.execute(sa.text(stmt), {"w": str(ws)})
        conn.execute(sa.text("DELETE FROM app_user WHERE id = :u"), {"u": str(user)})


@pytest.fixture
def client(app_db: None, workspace: tuple[UUID, UUID]) -> Iterator[TestClient]:
    from app.deps import current_scope
    from app.deps_entitlement import require_entitled
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
    app.dependency_overrides[require_entitled] = lambda: None
    with TestClient(app) as made:
        yield made
    app.dependency_overrides.clear()


@requires_db
def test_the_dashboard_surface_carries_the_insight(client: TestClient) -> None:
    body = client.get("/dashboards/surface")
    assert body.status_code == 200, body.text
    insights = body.json()["insights"]
    assert len(insights) == 1
    one = insights[0]
    assert one["source"] == "pagespeed"
    assert one["metric_key"] == "performance_score"
    assert one["value_numeric"] == 88
    assert one["unit"] == "score"
    assert "ins.om" in one["provenance"]
    assert one["captured_at"].startswith("2026-10-08")


@requires_db
def test_the_brain_endpoint_carries_the_insight(client: TestClient) -> None:
    """`/insights` is ungated — the Brain page reads it before payment."""
    body = client.get("/insights")
    assert body.status_code == 200, body.text
    insights = body.json()
    assert [i["metric_key"] for i in insights] == ["performance_score"]
    assert insights[0]["department"] == "marketing"
