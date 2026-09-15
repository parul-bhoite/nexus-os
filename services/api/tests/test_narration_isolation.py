"""I2/I3 for the narration reader, and the first display read of `generation`.

Migration 0023 built two indexes on this table for reads that were never
built — `ledger.py`'s header says so. This is the first of them, and it carries
three decisions worth proving rather than trusting:

**It is workspace-wide, with no `scope_key` filter.** It cannot have one: an
Owner's `scope_key` is every department they can reach and a Marketing
manager's is `L3:marketing` *for the same tile*, so filtering on it would mean
neither ever sees the other's sentence. That is safe only because `narrate`
sends the model no facts at all — asserted in
`test_grounding_compute.py::test_the_narrator_is_never_given_a_fact_value` —
and because the query below selects prose and trace keys and **never
`input_snapshot`**, which is where a consumed department fact does land.

**It reads answers only.** A refusal is not a narration to display.

**It uses `->>` and never `=`.** `calculation_trace` is `sa.JSON`, not JSONB,
and `json = json` is not an operator in Postgres — a mistake that passes every
unit test and fails only against a real database.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import get_engine, get_sessionmaker
from app.retrieval.narration import current_narrations
from app.retrieval.scoped import scoped_connection
from tests.dburl import async_database_url

ASYNC_DB_URL = async_database_url()

if TYPE_CHECKING:
    from app.domain.session import ScopedSession

requires_db = pytest.mark.requires_db

TRACE = {
    "numerator": 45,
    "denominator": 65,
    "percentage": 69,
    "page": "https://muscat-marine.om/",
    "window": "the page as fetched on 2026-09-10",
}


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


def _scope(user: UUID, ws: UUID) -> ScopedSession:
    from app.domain.scopes import Department, Role
    from app.domain.session import ScopedSession

    return ScopedSession(
        user_id=user,
        tenant_id=uuid4(),
        workspace_id=ws,
        role=Role.OWNER,
        departments=frozenset(Department),
    )


async def _workspace(db: AsyncSession) -> tuple[UUID, UUID]:
    user, tenant, ws = uuid4(), uuid4(), uuid4()
    await db.execute(
        sa.text("INSERT INTO app_user (id, email) VALUES (:i,:e)"),
        {"i": str(user), "e": f"narr-{user.hex[:8]}@example.com"},
    )
    await db.execute(sa.text("INSERT INTO tenant (id, name) VALUES (:i,'T')"), {"i": str(tenant)})
    await db.execute(sa.text("SELECT set_config('nexus.workspace_id', :w, true)"), {"w": str(ws)})
    await db.execute(
        sa.text(
            "INSERT INTO workspace (id, workspace_id, tenant_id, name, domain)"
            " VALUES (:i,:i,:t,'W',:d)"
        ),
        {"i": str(ws), "t": str(tenant), "d": f"narr-{ws.hex[:8]}.om"},
    )
    await db.execute(
        sa.text(
            "INSERT INTO membership (workspace_id, user_id, role, departments)"
            " VALUES (:w,:u,'owner', ARRAY['marketing']::text[])"
        ),
        {"w": str(ws), "u": str(user)},
    )
    await db.commit()
    return user, ws


async def _write(
    db: AsyncSession,
    ws: UUID,
    *,
    module: str = "marketing.seo_gaps",
    prose: str = "Most of the checks pass.",
    outcome: str = "answered",
    reason: str = "",
    trace: dict[str, object] | None = None,
    version: str = "1",
) -> None:
    await db.execute(sa.text("SELECT set_config('nexus.workspace_id', :w, true)"), {"w": str(ws)})
    await db.execute(
        sa.text(
            "INSERT INTO generation"
            " (workspace_id, module, prompt_version, input_snapshot, calculation_trace,"
            "  scope_key, outcome, unavailable_reason, prose, cost_micros)"
            " VALUES (:w,:m,:v, CAST(:snap AS json), CAST(:tr AS json),"
            "  'L2',:o,:r,:p,0)"
        ),
        {
            "w": str(ws),
            "m": module,
            "v": version,
            # A department-scoped fact, deliberately. The reader must not carry
            # it out — see the test that asserts the column is never selected.
            "snap": json.dumps({"facts": [{"key": "arabic_in_scope", "value": "yes"}]}),
            "tr": json.dumps(trace if trace is not None else TRACE),
            "o": outcome,
            "r": reason,
            "p": prose,
        },
    )
    await db.commit()


async def _cleanup(db: AsyncSession, user: UUID, ws: UUID) -> None:
    await db.execute(sa.text("SELECT set_config('nexus.workspace_id', :w, true)"), {"w": str(ws)})
    for statement in (
        "DELETE FROM generation WHERE workspace_id = :w",
        "DELETE FROM membership WHERE workspace_id = :w",
        "DELETE FROM workspace WHERE id = :w",
    ):
        await db.execute(sa.text(statement), {"w": str(ws)})
    await db.execute(sa.text("DELETE FROM app_user WHERE id = :u"), {"u": str(user)})
    await db.commit()


@requires_db
async def test_it_reads_this_workspaces_narration_with_its_trace(app_db: None) -> None:
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as db:
        user, ws = await _workspace(db)
        await _write(db, ws)
    try:
        async with scoped_connection(_scope(user, ws)) as db:
            found = await current_narrations(db, _scope(user, ws))

        stored = found["marketing.seo_gaps"]
        assert stored.prose == "Most of the checks pass."
        assert stored.prompt_version == "1"
        # Read through `->>`, so they arrive as strings — which is what
        # `describes` compares against `str(...)` of the live computation.
        assert stored.numerator == "45"
        assert stored.denominator == "65"
        assert stored.page == "https://muscat-marine.om/"
        assert stored.window == "the page as fetched on 2026-09-10"
    finally:
        async with sessionmaker() as db:
            await _cleanup(db, user, ws)


@requires_db
async def test_a_refusal_is_not_a_narration_to_display(app_db: None) -> None:
    """**`outcome = 'answered'` is in the `WHERE`, not filtered afterwards.**

    Without it, a founder who exhausted their allowance yesterday opens the
    dashboard today and reads "your allowance is spent" — hours after it reset.
    The refusal belongs to the attempt somebody just made, which is the POST's
    response; the page says what is true now.
    """
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as db:
        user, ws = await _workspace(db)
        await _write(db, ws, outcome="unavailable", reason="budget_exhausted", prose="")
    try:
        async with scoped_connection(_scope(user, ws)) as db:
            assert await current_narrations(db, _scope(user, ws)) == {}
    finally:
        async with sessionmaker() as db:
            await _cleanup(db, user, ws)


@requires_db
async def test_the_newest_narration_per_capability_wins(app_db: None) -> None:
    """Re-narrating leaves both rows — the ledger is a record, not a cache — so
    the read has to pick. `DISTINCT ON (module) … ORDER BY module, created_at
    DESC` is the pick, and getting it backwards would show the first sentence
    somebody replaced."""
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as db:
        user, ws = await _workspace(db)
        await _write(db, ws, prose="The first thing we said.")
        await _write(db, ws, prose="What we say now.")
    try:
        async with scoped_connection(_scope(user, ws)) as db:
            found = await current_narrations(db, _scope(user, ws))

        assert found["marketing.seo_gaps"].prose == "What we say now."
    finally:
        async with sessionmaker() as db:
            await _cleanup(db, user, ws)


@requires_db
async def test_each_capability_keeps_its_own_sentence(app_db: None) -> None:
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as db:
        user, ws = await _workspace(db)
        await _write(db, ws, module="marketing.seo_gaps", prose="About the SEO score.")
        await _write(db, ws, module="marketing.brand_intelligence", prose="About legibility.")
    try:
        async with scoped_connection(_scope(user, ws)) as db:
            found = await current_narrations(db, _scope(user, ws))

        assert found["marketing.seo_gaps"].prose == "About the SEO score."
        assert found["marketing.brand_intelligence"].prose == "About legibility."
    finally:
        async with sessionmaker() as db:
            await _cleanup(db, user, ws)


@requires_db
async def test_another_workspaces_narration_is_invisible(app_db: None) -> None:
    """The leak that would matter: prose about another company's website,
    rendered beside this company's figure, both individually plausible."""
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as db:
        user_a, ws_a = await _workspace(db)
        await _write(db, ws_a, prose="Belongs to A.")
    async with sessionmaker() as db:
        user_b, ws_b = await _workspace(db)
    try:
        async with scoped_connection(_scope(user_b, ws_b)) as db:
            assert await current_narrations(db, _scope(user_b, ws_b)) == {}
    finally:
        async with sessionmaker() as db:
            await _cleanup(db, user_a, ws_a)
        async with sessionmaker() as db:
            await _cleanup(db, user_b, ws_b)


def test_the_reader_never_selects_the_input_snapshot() -> None:
    """**The other half of why a workspace-wide read is honest.**

    `input_snapshot` is where a capability's `consumes_facts` land, and
    `marketing.seo_gaps` consumes `arabic_in_scope`, which is
    `Scope.L3_DEPARTMENT`. The prose cannot contain it — the narrator is sent
    no facts — but the *column* holds it, and this read is not department
    scoped. Selecting it would turn a display query into a cross-department
    leak with no other code change.

    Asserted against the SQL rather than the result, because a column nobody
    reads today is a column somebody adds to a `SELECT *` tomorrow.
    """
    from app.retrieval.narration import _CURRENT

    sql = str(_CURRENT).lower()
    assert "input_snapshot" not in sql
    assert "select *" not in sql


def test_the_reader_is_covered_by_the_signature_guard() -> None:
    """`test_retrieval_signatures` walks `app.retrieval` with `pkgutil`, so a
    new module is picked up for free — but a rename or a leading underscore
    drops it out silently, and a guard going quiet looks like a guard
    passing."""
    from tests.test_retrieval_signatures import _public_callables

    discovered = {name for name, _ in _public_callables()}
    assert "app.retrieval.narration.current_narrations" in discovered, sorted(discovered)
