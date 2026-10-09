"""Capturing a PageSpeed score stores one insight — or nothing, honestly.

`domain/pagespeed.py::capture` is the fetch-on-completion unit. Proven against
real Postgres with a **fixture transport** (no live Google call — `/goal` §5):

- a configured client over a recorded payload stores a `workspace_insight`;
- an unconfigured client (no key, the shipped default — ADR 0011/0082) stores
  nothing and does not raise;
- a provider failure stores nothing and does not raise — best-effort, because a
  failed telemetry fetch must never break onboarding completion.

The negative cases assert **no row**, not a zero: a zero score would render as a
real, terrible grade for a site nobody measured.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Mapping
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.connectors.contracts import ProviderUnavailableError
from app.connectors.pagespeed import PageSpeedClient, PageSpeedTransport
from app.db import get_engine, get_sessionmaker
from app.domain import insights
from app.domain.dashboards import Source
from app.domain.pagespeed import capture
from tests.dburl import async_database_url

ASYNC_DB_URL = async_database_url()
requires_db = pytest.mark.requires_db

FIXTURE = Path(__file__).parent / "fixtures" / "pagespeed" / "acme_mobile.json"


class _StubTransport:
    """Returns a recorded PSI payload; records that it was asked and with what."""

    def __init__(self, payload: Mapping[str, Any]) -> None:
        self._payload = payload
        self.calls: list[str] = []

    async def run(self, *, url: str, api_key: str, strategy: str) -> Mapping[str, Any]:
        self.calls.append(url)
        return self._payload


class _FailingTransport:
    async def run(self, *, url: str, api_key: str, strategy: str) -> Mapping[str, Any]:
        raise ProviderUnavailableError("PageSpeed answered 503")


def _configured(transport: PageSpeedTransport) -> PageSpeedClient:
    return PageSpeedClient(api_key="test-key", strategy="mobile", transport=transport)


def _unconfigured() -> PageSpeedClient:
    return PageSpeedClient(api_key="", strategy="mobile", transport=_StubTransport({}))


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
        {"i": str(user), "e": f"psi-{user.hex[:8]}@example.com"},
    )
    await db.execute(sa.text("INSERT INTO tenant (id, name) VALUES (:i,'T')"), {"i": str(tenant)})
    await db.execute(sa.text("SELECT set_config('nexus.workspace_id', :w, true)"), {"w": str(ws)})
    await db.execute(
        sa.text(
            "INSERT INTO workspace (id, workspace_id, tenant_id, name, domain, domain_verified_at)"
            " VALUES (:i,:i,:t,'W',:d, now())"
        ),
        {"i": str(ws), "t": str(tenant), "d": f"psi-{ws.hex[:8]}.om"},
    )
    await db.commit()
    return user, ws


async def _cleanup(db: AsyncSession, user: UUID, ws: UUID) -> None:
    await db.execute(sa.text("SELECT set_config('nexus.workspace_id', :w, true)"), {"w": str(ws)})
    await db.execute(sa.text("DELETE FROM workspace_insight WHERE workspace_id=:w"), {"w": str(ws)})
    await db.execute(sa.text("DELETE FROM workspace WHERE id=:w"), {"w": str(ws)})
    await db.execute(sa.text("DELETE FROM app_user WHERE id=:u"), {"u": str(user)})
    await db.commit()


@requires_db
async def test_a_configured_capture_stores_the_score(app_db: None) -> None:
    from app.db import _unscoped_session

    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    transport = _StubTransport(payload)

    async with _unscoped_session() as db:
        user, ws = await _workspace(db)
        try:
            await db.execute(
                sa.text("SELECT set_config('nexus.workspace_id', :w, true)"), {"w": str(ws)}
            )
            stored = await capture(
                db, workspace_id=ws, url="https://acme.test/", client=_configured(transport)
            )
            await db.commit()
            assert stored is True
            assert transport.calls == ["https://acme.test/"]

            await db.execute(
                sa.text("SELECT set_config('nexus.workspace_id', :w, true)"), {"w": str(ws)}
            )
            rows = await insights.current(db, workspace_id=ws, source=Source.PAGESPEED)
            assert len(rows) == 1
            assert rows[0].metric_key == "performance_score"
            assert rows[0].value_numeric == 88
            assert rows[0].unit == "score"
            assert "acme.test" in rows[0].provenance
        finally:
            await _cleanup(db, user, ws)


@requires_db
async def test_an_unconfigured_capture_stores_nothing(app_db: None) -> None:
    from app.db import _unscoped_session

    async with _unscoped_session() as db:
        user, ws = await _workspace(db)
        try:
            await db.execute(
                sa.text("SELECT set_config('nexus.workspace_id', :w, true)"), {"w": str(ws)}
            )
            stored = await capture(
                db, workspace_id=ws, url="https://acme.test/", client=_unconfigured()
            )
            await db.commit()
            assert stored is False, "no key is a supported state"

            await db.execute(
                sa.text("SELECT set_config('nexus.workspace_id', :w, true)"), {"w": str(ws)}
            )
            assert await insights.current(db, workspace_id=ws, source=Source.PAGESPEED) == []
        finally:
            await _cleanup(db, user, ws)


@requires_db
async def test_a_provider_failure_stores_nothing_and_does_not_raise(app_db: None) -> None:
    from app.db import _unscoped_session

    async with _unscoped_session() as db:
        user, ws = await _workspace(db)
        try:
            await db.execute(
                sa.text("SELECT set_config('nexus.workspace_id', :w, true)"), {"w": str(ws)}
            )
            stored = await capture(
                db,
                workspace_id=ws,
                url="https://acme.test/",
                client=_configured(_FailingTransport()),
            )
            await db.commit()
            assert stored is False, "a failed fetch must never break completion"

            await db.execute(
                sa.text("SELECT set_config('nexus.workspace_id', :w, true)"), {"w": str(ws)}
            )
            assert await insights.current(db, workspace_id=ws, source=Source.PAGESPEED) == []
        finally:
            await _cleanup(db, user, ws)
