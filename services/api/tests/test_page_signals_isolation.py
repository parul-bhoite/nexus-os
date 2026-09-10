"""`page_signals` must be invisible across workspaces, proved not asserted.

Migration 0028 writes `ENABLE ROW LEVEL SECURITY`, `FORCE ROW LEVEL SECURITY`
and one `workspace_isolation` policy, and a comment claiming those three lines
work. This file is the claim tested. It matters more here than for most tables
because of how the failure would present: `page_signals` holds a company's
website structure, and a leak would show up as *plausible* signals for the
wrong company — a title, a word count, an internal link count — scored into a
number that looks exactly like a real one.

Run as the real `nexus_app` role against a real Postgres, for the reason
`test_tenant_isolation.py` gives: RLS is a database behaviour, and a superuser
or `BYPASSRLS` role sails through every policy, so a suite run as `postgres`
would pass while proving nothing.

Note the shape of the negative case. With no GUC set, `nexus_app` is
`NOBYPASSRLS`, so a `SELECT` returns **zero rows rather than an error** — which
reads as an empty table and is the single most dangerous failure mode in this
codebase. `test_a_query_with_no_workspace_set_sees_nothing` asserts the count
rather than expecting a raise, deliberately.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy import Connection, Engine, create_engine

from tests.dburl import database_url

DB_URL = database_url()
requires_db = pytest.mark.requires_db

SIGNALS = {
    "url": "https://example.test/",
    "is_https": True,
    "title": "A page",
    "title_length": 6,
    "meta_description": None,
    "meta_description_length": 0,
}


@pytest.fixture(scope="module")
def engine() -> Iterator[Engine]:
    assert DB_URL is not None
    eng = create_engine(DB_URL, poolclass=sa.pool.NullPool)
    yield eng
    eng.dispose()


@pytest.fixture
def conn(engine: Engine) -> Iterator[Connection]:
    connection = engine.connect()
    trans = connection.begin()
    try:
        yield connection
    finally:
        trans.rollback()
        connection.close()


def set_workspace(conn: Connection, workspace_id: UUID | None) -> None:
    value = "" if workspace_id is None else str(workspace_id)
    conn.execute(sa.text("SELECT set_config('nexus.workspace_id', :ws, true)"), {"ws": value})


def insert_signals(conn: Connection, workspace_id: UUID, session_id: UUID, *, url: str) -> None:
    conn.execute(
        sa.text(
            "INSERT INTO page_signals"
            " (workspace_id, captured_by, session_id, url, position, signals)"
            " VALUES (:ws, 'onboarding', :s, :u, 0, CAST(:sig AS jsonb))"
        ),
        {"ws": str(workspace_id), "s": str(session_id), "u": url, "sig": json.dumps(SIGNALS)},
    )


@pytest.fixture
def two_crawled_workspaces(conn: Connection) -> tuple[UUID, UUID]:
    """Two workspaces in different tenants, each with one crawled page.

    Seeded with the GUC set to each workspace in turn, which is the first proof
    that the policy governs writes as well as reads — `WITH CHECK` refuses a
    row written under the wrong workspace.
    """
    user = uuid4()
    conn.execute(
        sa.text("INSERT INTO app_user (id, email) VALUES (:u, :e)"),
        {"u": str(user), "e": f"signals-{user}@example.test"},
    )

    workspaces: list[UUID] = []
    for name in ("A", "B"):
        tenant, ws, session = uuid4(), uuid4(), uuid4()
        conn.execute(
            sa.text("INSERT INTO tenant (id, name) VALUES (:t, :n)"),
            {"t": str(tenant), "n": f"Tenant {name}"},
        )
        set_workspace(conn, ws)
        conn.execute(
            sa.text(
                "INSERT INTO workspace (id, workspace_id, tenant_id, name)"
                " VALUES (:id, :id, :t, :n)"
            ),
            {"id": str(ws), "t": str(tenant), "n": f"Workspace {name}"},
        )
        conn.execute(
            sa.text(
                "INSERT INTO membership (workspace_id, user_id, role) VALUES (:ws, :u, 'owner')"
            ),
            {"ws": str(ws), "u": str(user)},
        )
        conn.execute(
            sa.text(
                "INSERT INTO onboarding_session (id, workspace_id, user_id, status, phase, domain)"
                " VALUES (:id, :ws, :u, 'active', 'analysing', :d)"
            ),
            {"id": str(session), "ws": str(ws), "u": str(user), "d": f"{name.lower()}.example"},
        )
        insert_signals(conn, ws, session, url=f"https://{name.lower()}.example/")
        workspaces.append(ws)

    return workspaces[0], workspaces[1]


@requires_db
def test_the_app_role_cannot_bypass_rls(conn: Connection) -> None:
    """If this fails every other test in this file is meaningless."""
    row = conn.execute(
        sa.text("SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user")
    ).one()
    assert row.rolsuper is False
    assert row.rolbypassrls is False


@requires_db
def test_row_level_security_is_forced_on_the_table(conn: Connection) -> None:
    """`ENABLE` alone is not enough: the table owner bypasses an enabled policy,
    and `nexus_app` owns every table in this schema — which is exactly why it
    can set `FORCE` at all. Asserted against the catalogue rather than trusting
    the migration ran both statements."""
    row = conn.execute(
        sa.text("SELECT relrowsecurity, relforcerowsecurity FROM pg_class WHERE relname = :t"),
        {"t": "page_signals"},
    ).one()
    assert row.relrowsecurity is True, "RLS is not enabled on page_signals"
    assert row.relforcerowsecurity is True, "RLS is not FORCED — the owner bypasses it"


@requires_db
def test_one_workspace_cannot_read_anothers_page_signals(
    conn: Connection, two_crawled_workspaces: tuple[UUID, UUID]
) -> None:
    ws_a, ws_b = two_crawled_workspaces

    set_workspace(conn, ws_a)
    mine = conn.execute(sa.text("SELECT url FROM page_signals")).scalars().all()
    assert mine == ["https://a.example/"]

    set_workspace(conn, ws_b)
    theirs = conn.execute(sa.text("SELECT url FROM page_signals")).scalars().all()
    assert theirs == ["https://b.example/"]
    assert "https://a.example/" not in theirs


@requires_db
def test_a_query_with_no_workspace_set_sees_nothing(
    conn: Connection, two_crawled_workspaces: tuple[UUID, UUID]
) -> None:
    """**Zero rows, not an error** — and that is the point of asserting it.

    An unscoped read fails silently and reads as "this company has no crawl",
    which the tile renders as `locked`. Wrong, but survivable. The reason this
    test exists is to pin the behaviour so nobody later "fixes" a mysteriously
    empty table by loosening the policy.
    """
    set_workspace(conn, None)
    assert conn.execute(sa.text("SELECT count(*) FROM page_signals")).scalar_one() == 0


@requires_db
def test_a_row_cannot_be_written_into_another_workspace(
    conn: Connection, two_crawled_workspaces: tuple[UUID, UUID]
) -> None:
    """`WITH CHECK`, tested. Without it a compromised or buggy writer could
    plant signals in a workspace it cannot read — which would surface as
    another company's website being scored into your tile."""
    ws_a, ws_b = two_crawled_workspaces
    session = conn.execute(
        sa.text("SELECT id FROM onboarding_session WHERE workspace_id = :ws"), {"ws": str(ws_b)}
    )
    set_workspace(conn, ws_b)
    other_session = session.scalar_one()

    set_workspace(conn, ws_a)
    with pytest.raises(sa.exc.ProgrammingError):
        conn.execute(
            sa.text(
                "INSERT INTO page_signals"
                " (workspace_id, captured_by, session_id, url, position, signals)"
                " VALUES (:ws, 'onboarding', :s, 'https://planted/', 0, CAST(:sig AS jsonb))"
            ),
            {"ws": str(ws_b), "s": str(other_session), "sig": json.dumps(SIGNALS)},
        )


@requires_db
def test_a_signals_row_must_name_the_crawl_it_came_from(
    conn: Connection, two_crawled_workspaces: tuple[UUID, UUID]
) -> None:
    """`ck_page_signals_provenance`. A row that cannot name its crawl is a
    signal nobody can trace back to a fetch, which makes the figure it feeds
    unverifiable — the one property this product cannot give up."""
    ws_a, _ = two_crawled_workspaces
    set_workspace(conn, ws_a)

    with pytest.raises(sa.exc.IntegrityError):
        conn.execute(
            sa.text(
                "INSERT INTO page_signals"
                " (workspace_id, captured_by, url, position, signals)"
                " VALUES (:ws, 'onboarding', 'https://orphan/', 0, CAST(:sig AS jsonb))"
            ),
            {"ws": str(ws_a), "sig": json.dumps(SIGNALS)},
        )


@requires_db
def test_captured_by_is_restricted_to_the_two_writers(
    conn: Connection, two_crawled_workspaces: tuple[UUID, UUID]
) -> None:
    ws_a, _ = two_crawled_workspaces
    set_workspace(conn, ws_a)
    session = conn.execute(sa.text("SELECT id FROM onboarding_session LIMIT 1")).scalar_one()

    with pytest.raises(sa.exc.IntegrityError):
        conn.execute(
            sa.text(
                "INSERT INTO page_signals"
                " (workspace_id, captured_by, session_id, url, position, signals)"
                " VALUES (:ws, 'guessed', :s, 'https://x/', 0, CAST(:sig AS jsonb))"
            ),
            {"ws": str(ws_a), "s": str(session), "sig": json.dumps(SIGNALS)},
        )
