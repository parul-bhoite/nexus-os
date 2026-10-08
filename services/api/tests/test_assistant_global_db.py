"""The global, metric-aware assistant answers from figures — and invents nothing.

ADR 0086. Driven against real Postgres with a `ScriptedProvider` (no real model):
what is asserted is the **guard and the flow**, not the model's phrasing. The
prompt's answer quality is the A12 human-eval step; what matters here is that

- a figure the grounding supplied may be stated (the happy path);
- a figure it did **not** supply is rejected — the whole answer refused, not the
  number corrected (I1, the point of the whole path);
- the model's own "no" becomes an honest refusal, not a pipeline error;
- an empty bundle refuses **without calling the model** at all;
- the endpoint is 404 while the feature is dark.

The insight (a PageSpeed score of 88) is the measured figure; `88` is therefore
permitted and `97` is not.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.providers import ScriptedProvider
from app.config import get_settings
from app.db import get_engine, get_sessionmaker
from app.domain.scopes import Department, Role
from app.domain.session import ScopedSession
from app.grounding import qa
from app.main import create_app
from tests.dburl import async_database_url

ASYNC_DB_URL = async_database_url()
requires_db = pytest.mark.requires_db


def _answer(prose: str, *, answered: bool = True) -> str:
    import json

    return json.dumps({"answered": answered, "answer": prose})


def _provider(prose: str, *, answered: bool = True) -> ScriptedProvider:
    return ScriptedProvider({"assistant-global": _answer(prose, answered=answered)})


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


async def _workspace(db: AsyncSession, *, with_insight: bool) -> tuple[UUID, UUID]:
    user, tenant, ws = uuid4(), uuid4(), uuid4()
    await db.execute(
        sa.text("INSERT INTO app_user (id, email) VALUES (:i,:e)"),
        {"i": str(user), "e": f"gqa-{user.hex[:8]}@example.com"},
    )
    await db.execute(sa.text("INSERT INTO tenant (id, name) VALUES (:i,'T')"), {"i": str(tenant)})
    await db.execute(sa.text("SELECT set_config('nexus.workspace_id', :w, true)"), {"w": str(ws)})
    await db.execute(
        sa.text(
            "INSERT INTO workspace (id, workspace_id, tenant_id, name, domain, domain_verified_at)"
            " VALUES (:i,:i,:t,'W',:d, now())"
        ),
        {"i": str(ws), "t": str(tenant), "d": f"gqa-{ws.hex[:8]}.om"},
    )
    if with_insight:
        await db.execute(
            sa.text(
                "INSERT INTO workspace_insight (workspace_id, source, metric_key, value_numeric,"
                " unit, provenance, department, captured_at)"
                " VALUES (:w, 'pagespeed', 'performance_score', 88, 'score',"
                "         'PageSpeed Insights, https://gqa.om/', 'marketing', :at)"
            ),
            {"w": str(ws), "at": datetime(2026, 10, 8, 9, 0, tzinfo=UTC)},
        )
    await db.commit()
    return user, ws


async def _cleanup(db: AsyncSession, user: UUID, ws: UUID) -> None:
    await db.execute(sa.text("SELECT set_config('nexus.workspace_id', :w, true)"), {"w": str(ws)})
    for stmt in (
        "DELETE FROM generation WHERE workspace_id = :w",
        "DELETE FROM workspace_insight WHERE workspace_id = :w",
        "DELETE FROM workspace WHERE id = :w",
    ):
        await db.execute(sa.text(stmt), {"w": str(ws)})
    await db.execute(sa.text("DELETE FROM app_user WHERE id = :u"), {"u": str(user)})
    await db.commit()


def _scope(user: UUID, ws: UUID) -> ScopedSession:
    return ScopedSession(
        user_id=user,
        tenant_id=uuid4(),
        workspace_id=ws,
        role=Role.OWNER,
        departments=frozenset(Department),
    )


@requires_db
async def test_a_grounded_figure_may_be_stated(app_db: None) -> None:
    from app.db import _unscoped_session

    async with _unscoped_session() as db:
        user, ws = await _workspace(db, with_insight=True)
        try:
            await db.execute(
                sa.text("SELECT set_config('nexus.workspace_id', :w, true)"), {"w": str(ws)}
            )
            result = await qa.answer(
                db,
                _scope(user, ws),
                "What is our website performance score?",
                provider=_provider("PageSpeed measured a performance score of 88."),
                settings=get_settings(),
            )
            await db.commit()
            assert result.answered is True
            assert "88" in result.prose
            assert any("pagespeed" in label for label in result.grounded_on)
        finally:
            await _cleanup(db, user, ws)


@requires_db
async def test_an_invented_figure_is_refused_whole(app_db: None) -> None:
    """97 is in no figure we supplied. I1: the whole answer is refused, not fixed."""
    from app.db import _unscoped_session

    async with _unscoped_session() as db:
        user, ws = await _workspace(db, with_insight=True)
        try:
            await db.execute(
                sa.text("SELECT set_config('nexus.workspace_id', :w, true)"), {"w": str(ws)}
            )
            result = await qa.answer(
                db,
                _scope(user, ws),
                "What is our performance score?",
                provider=_provider("Your performance score is 97."),
                settings=get_settings(),
            )
            await db.commit()
            assert result.answered is False
            assert "discarded" in result.sentence.lower()
            assert "97" not in result.prose  # nothing invented reaches the reader
        finally:
            await _cleanup(db, user, ws)


@requires_db
async def test_a_model_no_becomes_an_honest_refusal(app_db: None) -> None:
    from app.db import _unscoped_session

    async with _unscoped_session() as db:
        user, ws = await _workspace(db, with_insight=True)
        try:
            await db.execute(
                sa.text("SELECT set_config('nexus.workspace_id', :w, true)"), {"w": str(ws)}
            )
            result = await qa.answer(
                db,
                _scope(user, ws),
                "Is that score good compared to competitors?",
                provider=_provider("", answered=False),
                settings=get_settings(),
            )
            await db.commit()
            assert result.answered is False
            assert result.sentence
            assert result.prose == ""
        finally:
            await _cleanup(db, user, ws)


@requires_db
async def test_an_empty_bundle_refuses_without_calling_the_model(app_db: None) -> None:
    """No insight, no brain, no crawl → refuse before a model is ever invoked.
    The scripted provider has no script for this skill, so a call would raise."""
    from app.db import _unscoped_session

    async with _unscoped_session() as db:
        user, ws = await _workspace(db, with_insight=False)
        try:
            await db.execute(
                sa.text("SELECT set_config('nexus.workspace_id', :w, true)"), {"w": str(ws)}
            )
            result = await qa.answer(
                db,
                _scope(user, ws),
                "What is our performance score?",
                provider=ScriptedProvider({}),  # would raise if called
                settings=get_settings(),
            )
            await db.commit()
            assert result.answered is False
            assert result.grounded_on == ()
        finally:
            await _cleanup(db, user, ws)


# ── The dark gate ──────────────────────────────────────────────


@pytest.fixture
def client(app_db: None) -> Iterator[TestClient]:
    from app.deps import current_scope

    app = create_app()
    app.dependency_overrides[current_scope] = lambda: _scope(uuid4(), uuid4())
    with TestClient(app) as made:
        yield made
    app.dependency_overrides.clear()


@requires_db
def test_the_endpoint_is_404_while_the_flag_is_off(client: TestClient) -> None:
    """assistant_enabled is False by default — the endpoint 404s, not 403, so its
    existence is not disclosed (doc/20 A8)."""
    client.cookies.set("nexus_csrf", "t")
    response = client.post(
        "/assistant/ask",
        json={"question": "anything"},
        headers={"X-CSRF-Token": "t"},
    )
    assert response.status_code == 404, response.text
