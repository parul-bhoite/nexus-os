"""`public_scan` — schema shape only. ADR 0048, migration `0037`.

Two things this file exists to prove, both by hand against a real Postgres
rather than by reading the migration and trusting it:

1. **The seven-day TTL is structural.** A raw `INSERT` naming only the
   required columns still gets an `expires_at` seven days out — the database
   default, not application code that does not exist yet (G7).
2. **The RLS absence is deliberate, not an oversight.** `public_scan` is
   genuinely outside every other table's isolation model: it is not merely
   `relrowsecurity = false` today, it *cannot* be scoped, because it has no
   `workspace_id` column for a policy to filter on at all. Asserting only the
   first would pass just as well for a table someone forgot to secure;
   asserting the second is what tells the two apart.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
import sqlalchemy as sa
from sqlalchemy import Connection, Engine, create_engine

from tests.dburl import database_url

DB_URL = database_url()
requires_db = pytest.mark.requires_db


@pytest.fixture(scope="module")
def engine() -> Iterator[Engine]:
    assert DB_URL is not None
    eng = create_engine(DB_URL, poolclass=sa.pool.NullPool)
    yield eng
    eng.dispose()


@pytest.fixture
def conn(engine: Engine) -> Iterator[Connection]:
    with engine.connect() as c:
        with c.begin():
            yield c
            c.rollback()


@requires_db
def test_expires_at_defaults_to_seven_days_out(conn: Connection) -> None:
    row = conn.execute(
        sa.text(
            "INSERT INTO public_scan (domain, scanned_url, checks, scores, pages_read)"
            " VALUES (:d, :u, '[]'::jsonb, '{}'::jsonb, 1)"
            " RETURNING created_at, expires_at"
        ),
        {"d": "example.om", "u": "https://example.om/"},
    ).one()

    delta = row.expires_at - row.created_at
    assert delta.days == 7, f"expires_at is {delta} after created_at, not 7 days"


@requires_db
def test_public_scan_has_no_row_level_security(conn: Connection) -> None:
    row = conn.execute(
        sa.text(
            "SELECT relrowsecurity, relforcerowsecurity FROM pg_class WHERE relname = 'public_scan'"
        )
    ).one()
    assert row.relrowsecurity is False, (
        "public_scan has RLS enabled — it cannot be, see the migration docstring"
    )
    assert row.relforcerowsecurity is False


@requires_db
def test_public_scan_has_no_workspace_id_to_scope_by(conn: Connection) -> None:
    """The structural reason RLS is absent, not merely the observed fact that
    it is. If this ever gains a `workspace_id` column, the table has stopped
    being what ADR 0048 describes and the RLS decision above needs revisiting,
    not silently inheriting."""
    columns = {
        row.column_name
        for row in conn.execute(
            sa.text(
                "SELECT column_name FROM information_schema.columns"
                " WHERE table_name = 'public_scan'"
            )
        )
    }
    assert "workspace_id" not in columns
    assert "tenant_id" not in columns


@requires_db
def test_public_scan_stores_no_page_content(conn: Connection) -> None:
    """The column set itself is the guard — `checks`/`scores` are the only
    JSON columns, and nothing here is named for HTML, a text sample, or an
    email address. Enumerated explicitly so a later `ALTER TABLE ADD COLUMN
    raw_html ...` fails this test rather than silently widening what a
    tenantless table is allowed to hold."""
    columns = {
        row.column_name
        for row in conn.execute(
            sa.text(
                "SELECT column_name FROM information_schema.columns"
                " WHERE table_name = 'public_scan'"
            )
        )
    }
    assert columns == {
        "id",
        "domain",
        "scanned_url",
        "checks",
        "scores",
        "pages_read",
        "js_rendered",
        "created_at",
        "expires_at",
        "deleted_at",
    }
