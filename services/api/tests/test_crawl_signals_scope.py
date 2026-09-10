"""I2/I3 for the crawl reader: the predicate is in the query, not after it.

`test_page_signals_isolation.py` proves the *database* refuses a cross-workspace
read. This proves the *reader* asks correctly — that `current_page_signals`
takes a `ScopedSession` and gets nothing when the only rows present belong to
somebody else. Both are needed: RLS could be right while the function still
accepted a `workspace_id` and became an injection target (doc 06 §4.3), and the
signature guard alone would not catch a query that filtered in Python.

Also asserts the reader is discovered by `test_retrieval_signatures`'s walk.
That walk is `pkgutil`-based, so a new module is picked up automatically — but
a *rename* or a leading underscore would drop it out silently, and the guard
going quiet is indistinguishable from the guard passing.
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
from app.retrieval.crawl import current_page_signals
from app.retrieval.scoped import scoped_connection
from tests.dburl import async_database_url

ASYNC_DB_URL = async_database_url()

if TYPE_CHECKING:
    from app.domain.session import ScopedSession

requires_db = pytest.mark.requires_db

SIGNALS = {
    "url": "https://crawled.example/",
    "is_https": True,
    "title": "Marine engine repair in Muscat",
    "title_length": 31,
    "meta_description": "Dry-dock maintenance for Omani fleets.",
    "meta_description_length": 38,
    "h1_texts": ["Marine engine repair"],
    "word_count": 640,
    "internal_link_count": 18,
    "has_canonical": True,
    "declared_language": "en",
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


async def _workspace_with_crawl(
    db: AsyncSession, *, pages: int = 1, prefix: str = "a"
) -> tuple[UUID, UUID]:
    """A workspace, an owner, an onboarding session and `pages` signal rows."""
    user, tenant, ws, session = uuid4(), uuid4(), uuid4(), uuid4()
    await db.execute(
        sa.text("INSERT INTO app_user (id, email) VALUES (:i,:e)"),
        {"i": str(user), "e": f"crawl-{user.hex[:8]}@example.com"},
    )
    await db.execute(sa.text("INSERT INTO tenant (id, name) VALUES (:i,'T')"), {"i": str(tenant)})
    await db.execute(sa.text("SELECT set_config('nexus.workspace_id', :w, true)"), {"w": str(ws)})
    await db.execute(
        sa.text(
            "INSERT INTO workspace (id, workspace_id, tenant_id, name, domain)"
            " VALUES (:i,:i,:t,'W',:d)"
        ),
        {"i": str(ws), "t": str(tenant), "d": f"crawl-{ws.hex[:8]}.om"},
    )
    await db.execute(
        sa.text(
            "INSERT INTO membership (workspace_id, user_id, role, departments)"
            " VALUES (:w,:u,'owner', ARRAY['marketing']::text[])"
        ),
        {"w": str(ws), "u": str(user)},
    )
    await db.execute(
        sa.text(
            "INSERT INTO onboarding_session (id, workspace_id, user_id, status, phase, domain)"
            " VALUES (:i,:w,:u,'active','analysing',:d)"
        ),
        {"i": str(session), "w": str(ws), "u": str(user), "d": f"crawl-{ws.hex[:8]}.om"},
    )
    for position in range(pages):
        payload = dict(SIGNALS, url=f"https://{prefix}.example/{position}")
        await db.execute(
            sa.text(
                "INSERT INTO page_signals"
                " (workspace_id, captured_by, session_id, url, position, signals)"
                " VALUES (:w,'onboarding',:s,:u,:p, CAST(:sig AS jsonb))"
            ),
            {
                "w": str(ws),
                "s": str(session),
                "u": f"https://{prefix}.example/{position}",
                "p": position,
                "sig": json.dumps(payload),
            },
        )
    await db.commit()
    return user, ws


async def _cleanup(db: AsyncSession, user: UUID, ws: UUID) -> None:
    await db.execute(sa.text("SELECT set_config('nexus.workspace_id', :w, true)"), {"w": str(ws)})
    for statement in (
        "DELETE FROM page_signals WHERE workspace_id = :w",
        "DELETE FROM onboarding_session WHERE workspace_id = :w",
        "DELETE FROM membership WHERE workspace_id = :w",
        "DELETE FROM workspace WHERE id = :w",
    ):
        await db.execute(sa.text(statement), {"w": str(ws)})
    await db.execute(sa.text("DELETE FROM app_user WHERE id = :u"), {"u": str(user)})
    await db.commit()


@requires_db
async def test_the_reader_returns_this_workspaces_leading_page(app_db: None) -> None:
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as db:
        user, ws = await _workspace_with_crawl(db, pages=3)
    try:
        async with scoped_connection(_scope(user, ws)) as db:
            snapshot = await current_page_signals(db, _scope(user, ws))

        assert snapshot is not None
        # `position` 0 is the page the crawl led with — `site.plan` orders by
        # priority, so this is a documented rule rather than a guess about
        # which URL is the home page.
        assert snapshot.url == "https://a.example/0"
        assert snapshot.pages_captured == 3
        assert snapshot.signals.title == "Marine engine repair in Muscat"
        assert snapshot.signals.word_count == 640
        # Reconstructed as a tuple, not the list JSON gave back.
        assert snapshot.signals.h1_texts == ("Marine engine repair",)
    finally:
        async with sessionmaker() as db:
            await _cleanup(db, user, ws)


@requires_db
async def test_a_workspace_with_no_crawl_reads_none_not_a_zero(app_db: None) -> None:
    """I10 at the read boundary.

    `None` is what makes the tile render `locked`. A `CrawlSnapshot` with an
    empty `PageSignals` would score 0/65 and say the website failed every
    check, when the truth is that nobody has looked at it.
    """
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as db:
        user, ws = await _workspace_with_crawl(db, pages=0)
    try:
        async with scoped_connection(_scope(user, ws)) as db:
            assert await current_page_signals(db, _scope(user, ws)) is None
    finally:
        async with sessionmaker() as db:
            await _cleanup(db, user, ws)


@requires_db
async def test_another_workspaces_crawl_is_invisible(app_db: None) -> None:
    """The leak that would matter most: not an error, but *plausible* signals
    for the wrong company, scored into a number that looks real."""
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as db:
        user_a, ws_a = await _workspace_with_crawl(db, pages=2, prefix="a")
    async with sessionmaker() as db:
        user_b, ws_b = await _workspace_with_crawl(db, pages=0, prefix="b")
    try:
        # B has no crawl of its own and A's rows exist. B must still read None.
        async with scoped_connection(_scope(user_b, ws_b)) as db:
            assert await current_page_signals(db, _scope(user_b, ws_b)) is None

        async with scoped_connection(_scope(user_a, ws_a)) as db:
            mine = await current_page_signals(db, _scope(user_a, ws_a))
        assert mine is not None
        assert mine.url.startswith("https://a.example/")
    finally:
        async with sessionmaker() as db:
            await _cleanup(db, user_a, ws_a)
        async with sessionmaker() as db:
            await _cleanup(db, user_b, ws_b)


@requires_db
async def test_a_superseded_crawl_is_not_read(app_db: None) -> None:
    """Re-crawling supersedes rather than duplicating, so the reader must not
    pick a stale page — and `ORDER BY position LIMIT 1` over both crawls would
    do exactly that, silently, half the time."""
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as db:
        user, ws = await _workspace_with_crawl(db, pages=1, prefix="old")
    try:
        async with sessionmaker() as db:
            await db.execute(
                sa.text("SELECT set_config('nexus.workspace_id', :w, true)"), {"w": str(ws)}
            )
            await db.execute(
                sa.text(
                    "UPDATE page_signals SET superseded_at = now()"
                    " WHERE workspace_id = :w AND superseded_at IS NULL"
                ),
                {"w": str(ws)},
            )
            session_id = (
                await db.execute(
                    sa.text("SELECT id FROM onboarding_session WHERE workspace_id = :w"),
                    {"w": str(ws)},
                )
            ).scalar_one()
            await db.execute(
                sa.text(
                    "INSERT INTO page_signals"
                    " (workspace_id, captured_by, session_id, url, position, signals)"
                    " VALUES (:w,'onboarding',:s,'https://fresh.example/',0, CAST(:sig AS jsonb))"
                ),
                {
                    "w": str(ws),
                    "s": str(session_id),
                    "sig": json.dumps(dict(SIGNALS, url="https://fresh.example/")),
                },
            )
            await db.commit()

        async with scoped_connection(_scope(user, ws)) as db:
            snapshot = await current_page_signals(db, _scope(user, ws))

        assert snapshot is not None
        assert snapshot.url == "https://fresh.example/"
        assert snapshot.pages_captured == 1, "the superseded row was counted"
    finally:
        async with sessionmaker() as db:
            await _cleanup(db, user, ws)


def test_the_reader_is_covered_by_the_signature_guard() -> None:
    """`test_retrieval_signatures` walks `app.retrieval` with `pkgutil`, so a
    new module is picked up for free — but a rename or a leading underscore
    would drop it from the walk, and a guard going quiet looks exactly like a
    guard passing."""
    from tests.test_retrieval_signatures import _public_callables

    # Fully qualified — the walk yields `module.name`, so a bare-name check
    # would pass on any module that happened to export the same symbol.
    discovered = {name for name, _ in _public_callables()}
    assert "app.retrieval.crawl.current_page_signals" in discovered, sorted(discovered)
