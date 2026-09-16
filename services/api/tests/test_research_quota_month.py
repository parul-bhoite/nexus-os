"""The manual-run allowance turns over at the **workspace's** midnight.

`routes/research.py` counted with a bare `date_trunc('month', now())`, which
truncates in the *session* timezone — GMT on this deployment. Every GCC
timezone is ahead of UTC, so that cutoff sits later than the real one, and the
runs a founder starts in the first hours of their own month fall before it and
are never counted. The allowance is silently larger than three.

**Milder than M33 and asserted the same way.** There, both sides went naive and
Postgres reinterpreted the cutoff, leaving the daily token budget unenforced for
four hours out of every twenty-four. Here both sides stay `timestamptz`, so only
the boundary is misplaced — but a test that reads the clock would still be green
for all but a few hours a month, which is the same failure mode that hid M33 for
weeks. So `manual_runs_this_month` takes `now`, and every case below pins an
explicit instant.

The boundary is in SQL, so these need a real Postgres. There is nothing to
assert in Python.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import get_engine, get_sessionmaker
from app.retrieval.research_quota import manual_runs_this_month
from app.retrieval.scoped import scoped_connection
from tests.dburl import async_database_url

ASYNC_DB_URL = async_database_url()

if TYPE_CHECKING:
    from app.domain.session import ScopedSession

requires_db = pytest.mark.requires_db

# Muscat is UTC+4, so its October begins at 20:00 UTC on 30 September.
LOCAL_MONTH_START = datetime(2026, 9, 30, 20, 0, tzinfo=UTC)
UTC_MONTH_START = datetime(2026, 10, 1, 0, 0, tzinfo=UTC)
NOW = datetime(2026, 10, 1, 9, 0, tzinfo=UTC)
"""Well inside October in both timezones, so nothing below turns on *when the
question is asked* — only on where the month is judged to start."""


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
        {"i": str(user), "e": f"quota-{user.hex[:8]}@example.com"},
    )
    await db.execute(sa.text("INSERT INTO tenant (id, name) VALUES (:i,'T')"), {"i": str(tenant)})
    await db.execute(sa.text("SELECT set_config('nexus.workspace_id', :w, true)"), {"w": str(ws)})
    await db.execute(
        sa.text(
            "INSERT INTO workspace (id, workspace_id, tenant_id, name, domain, report_timezone)"
            " VALUES (:i,:i,:t,'W',:d,:tz)"
        ),
        {"i": str(ws), "t": str(tenant), "d": f"quota-{ws.hex[:8]}.om", "tz": "Asia/Muscat"},
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


async def _run(db: AsyncSession, ws: UUID, at: datetime, *, requester: UUID | None) -> None:
    await db.execute(sa.text("SELECT set_config('nexus.workspace_id', :w, true)"), {"w": str(ws)})
    await db.execute(
        sa.text(
            "INSERT INTO research_run (workspace_id, state, requested_by_user_id, requested_at)"
            " VALUES (:w,'complete',:u,:at)"
        ),
        {"w": str(ws), "u": str(requester) if requester else None, "at": at},
    )
    await db.commit()


async def _cleanup(db: AsyncSession, user: UUID, ws: UUID) -> None:
    await db.execute(sa.text("SELECT set_config('nexus.workspace_id', :w, true)"), {"w": str(ws)})
    for statement in (
        "DELETE FROM research_run WHERE workspace_id = :w",
        "DELETE FROM membership WHERE workspace_id = :w",
        "DELETE FROM workspace WHERE id = :w",
    ):
        await db.execute(sa.text(statement), {"w": str(ws)})
    await db.execute(sa.text("DELETE FROM app_user WHERE id = :u"), {"u": str(user)})
    await db.commit()


@requires_db
async def test_a_run_started_in_the_workspaces_new_month_counts_against_it(app_db: None) -> None:
    """**The whole defect, in one row.**

    20:30 UTC on 30 September is half past midnight on 1 October in Muscat — the
    founder's new month, their first run of it. Under `date_trunc('month',
    now())` the cutoff is 00:00 *UTC*, this row sits before it, and the run is
    free: the allowance reads as three remaining when two are.
    """
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as db:
        user, ws = await _workspace(db)
        await _run(db, ws, LOCAL_MONTH_START.replace(hour=20, minute=30), requester=user)
    try:
        async with scoped_connection(_scope(user, ws)) as db:
            assert await manual_runs_this_month(db, _scope(user, ws), now=NOW) == 1
    finally:
        async with sessionmaker() as db:
            await _cleanup(db, user, ws)


@requires_db
async def test_last_months_runs_do_not_follow_the_founder_into_the_new_one(app_db: None) -> None:
    """The mirror, and the reason the boundary cannot simply be moved earlier by
    a fixed amount: 19:00 UTC is 23:00 on 30 September in Muscat, genuinely the
    old month, and a founder who starts October with one run already spent has
    been charged for work they did in September."""
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as db:
        user, ws = await _workspace(db)
        await _run(db, ws, datetime(2026, 9, 30, 19, 0, tzinfo=UTC), requester=user)
    try:
        async with scoped_connection(_scope(user, ws)) as db:
            assert await manual_runs_this_month(db, _scope(user, ws), now=NOW) == 0
    finally:
        async with sessionmaker() as db:
            await _cleanup(db, user, ws)


@requires_db
async def test_the_weekly_sweep_does_not_consume_the_founders_allowance(app_db: None) -> None:
    """`requested_by_user_id IS NOT NULL` is what makes a run manual. The sweep
    has no requester, and charging it to the three would mean the product
    quietly consuming the allowance it gave them."""
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as db:
        user, ws = await _workspace(db)
        await _run(db, ws, UTC_MONTH_START.replace(hour=6), requester=None)
    try:
        async with scoped_connection(_scope(user, ws)) as db:
            assert await manual_runs_this_month(db, _scope(user, ws), now=NOW) == 0
    finally:
        async with sessionmaker() as db:
            await _cleanup(db, user, ws)


@requires_db
async def test_another_workspaces_runs_are_invisible(app_db: None) -> None:
    """I2 for the new reader. The query has no `workspace_id` predicate of its
    own on `research_run` — RLS is the whole of it — so this is the assertion
    that the policy is doing that work."""
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as db:
        user_a, ws_a = await _workspace(db)
        await _run(db, ws_a, NOW.replace(hour=8), requester=user_a)
    async with sessionmaker() as db:
        user_b, ws_b = await _workspace(db)
    try:
        async with scoped_connection(_scope(user_b, ws_b)) as db:
            assert await manual_runs_this_month(db, _scope(user_b, ws_b), now=NOW) == 0
    finally:
        async with sessionmaker() as db:
            await _cleanup(db, user_a, ws_a)
        async with sessionmaker() as db:
            await _cleanup(db, user_b, ws_b)


def test_the_reader_is_covered_by_the_signature_guard() -> None:
    from tests.test_retrieval_signatures import _public_callables

    discovered = {name for name, _ in _public_callables()}
    assert "app.retrieval.research_quota.manual_runs_this_month" in discovered, sorted(discovered)


def test_the_timezone_fallback_is_kept_even_though_nothing_can_reach_it() -> None:
    """**The `COALESCE` that looks like defensive noise and is a bypass if
    removed.**

    Nothing reaches it today, and that was worth establishing rather than
    assuming: migration 0027 made `report_timezone` `NOT NULL DEFAULT
    'Asia/Muscat'`, and `:w` is `scope.workspace_id` — the same value
    `scoped_connection` writes into the GUC the RLS policy compares — so the
    subselect cannot miss its row either.

    It stays because of what a `NULL` would *do*. `date_trunc(…, NULL)` is
    `NULL`, `requested_at >= NULL` is `NULL`, no row qualifies, the count is
    zero — and zero does not read as an error, it reads as an allowance nobody
    has touched. Making that column nullable again, or passing some other `:w`,
    would not produce a wrong boundary; it would produce an **unlimited** one,
    on a screen that looked right.

    Asserted against the SQL, not a result, for the reason the first paragraph
    gives — the same reason `test_narration_isolation.py` asserts
    `input_snapshot` stays out of a `SELECT`.
    """
    from app.retrieval.research_quota import _MANUAL_RUNS_SQL

    sql = " ".join(str(_MANUAL_RUNS_SQL).lower().split())
    assert "coalesce((select report_timezone from workspace where id = :w), 'utc')" in sql
