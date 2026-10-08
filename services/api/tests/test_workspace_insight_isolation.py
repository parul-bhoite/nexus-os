"""`workspace_insight` must be invisible across workspaces, proved not asserted.

Migration 0043 writes `ENABLE`/`FORCE ROW LEVEL SECURITY` and one isolation
policy. This file is that claim tested. It matters here because of how a leak
would present: a measured insight — a PageSpeed score, a pipeline total — shown
against the wrong company reads as a plausible real figure, which is the failure
mode this product can least afford.

Run as the real `nexus_app` role (`NOBYPASSRLS`) against real Postgres, for the
reason `test_tenant_isolation.py` gives: a superuser sails through every policy.
And note the negative case — with no GUC set, a `SELECT` returns **zero rows, not
an error**, which reads as an empty table; `test_a_query_with_no_workspace_set`
pins that so nobody "fixes" a mysteriously empty table by loosening the policy.
"""

from __future__ import annotations

from collections.abc import Iterator
from uuid import UUID, uuid4

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


def insert_insight(conn: Connection, workspace_id: UUID, *, metric: str) -> None:
    conn.execute(
        sa.text(
            "INSERT INTO workspace_insight"
            " (workspace_id, source, metric_key, value_numeric, unit, provenance)"
            " VALUES (:ws, 'pagespeed', :m, 88, 'score', 'PageSpeed')"
        ),
        {"ws": str(workspace_id), "m": metric},
    )


@pytest.fixture
def two_workspaces(conn: Connection) -> tuple[UUID, UUID]:
    """Two workspaces in different tenants, each with one insight.

    Seeded with the GUC set to each workspace in turn — the first proof that the
    policy governs writes too: `WITH CHECK` refuses a row written under the wrong
    workspace.
    """
    workspaces: list[UUID] = []
    for name in ("A", "B"):
        tenant, ws = uuid4(), uuid4()
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
        insert_insight(conn, ws, metric=f"metric_{name.lower()}")
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
    """`ENABLE` alone is not enough: the owner bypasses an enabled policy, and
    `nexus_app` owns every table. Asserted against the catalogue, not the migration."""
    row = conn.execute(
        sa.text("SELECT relrowsecurity, relforcerowsecurity FROM pg_class WHERE relname = :t"),
        {"t": "workspace_insight"},
    ).one()
    assert row.relrowsecurity is True, "RLS is not enabled on workspace_insight"
    assert row.relforcerowsecurity is True, "RLS is not FORCED — the owner bypasses it"


@requires_db
def test_one_workspace_cannot_read_anothers_insights(
    conn: Connection, two_workspaces: tuple[UUID, UUID]
) -> None:
    ws_a, ws_b = two_workspaces

    set_workspace(conn, ws_a)
    mine = conn.execute(sa.text("SELECT metric_key FROM workspace_insight")).scalars().all()
    assert mine == ["metric_a"]

    set_workspace(conn, ws_b)
    theirs = conn.execute(sa.text("SELECT metric_key FROM workspace_insight")).scalars().all()
    assert theirs == ["metric_b"]
    assert "metric_a" not in theirs


@requires_db
def test_a_query_with_no_workspace_set_sees_nothing(
    conn: Connection, two_workspaces: tuple[UUID, UUID]
) -> None:
    """Zero rows, not an error — pinned so nobody loosens the policy to "fix" it."""
    set_workspace(conn, None)
    assert conn.execute(sa.text("SELECT count(*) FROM workspace_insight")).scalar_one() == 0


@requires_db
def test_an_insight_cannot_be_written_into_another_workspace(
    conn: Connection, two_workspaces: tuple[UUID, UUID]
) -> None:
    """`WITH CHECK`, tested. Without it a buggy writer could plant an insight in a
    workspace it cannot read — surfacing as another company's number in your tile."""
    ws_a, ws_b = two_workspaces
    set_workspace(conn, ws_a)
    with pytest.raises(sa.exc.ProgrammingError):
        insert_insight(conn, ws_b, metric="planted")


@requires_db
def test_an_insight_must_carry_a_value(conn: Connection, two_workspaces: tuple[UUID, UUID]) -> None:
    """`ck_workspace_insight_has_value`. An insight with no value is nothing."""
    ws_a, _ = two_workspaces
    set_workspace(conn, ws_a)
    with pytest.raises(sa.exc.IntegrityError):
        conn.execute(
            sa.text(
                "INSERT INTO workspace_insight (workspace_id, source, metric_key, provenance)"
                " VALUES (:ws, 'pagespeed', 'empty', 'PageSpeed')"
            ),
            {"ws": str(ws_a)},
        )


@requires_db
def test_a_unit_requires_a_number(conn: Connection, two_workspaces: tuple[UUID, UUID]) -> None:
    """`ck_workspace_insight_unit_needs_number`. A unit beside no number describes
    nothing — the same pairing as `crm_deal`'s amount and currency."""
    ws_a, _ = two_workspaces
    set_workspace(conn, ws_a)
    with pytest.raises(sa.exc.IntegrityError):
        conn.execute(
            sa.text(
                "INSERT INTO workspace_insight"
                " (workspace_id, source, metric_key, value_text, unit, provenance)"
                " VALUES (:ws, 'pagespeed', 'labelled', 'fast', 'score', 'PageSpeed')"
            ),
            {"ws": str(ws_a)},
        )
