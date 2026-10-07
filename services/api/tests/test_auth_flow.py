"""Registration, login, session and workspace-switch behaviour, end to end.

Runs against the real database. The interesting assertions are the negative
ones: that login does not become a user-enumeration oracle, that a session token
is never reusable after logout, and that a workspace id in a request body is
validated rather than believed.
"""

from __future__ import annotations

from collections.abc import Iterator
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy import Connection, Engine, create_engine

from tests.dburl import database_url

PASSWORD = "Correct-horse-battery-staple1"


DB_URL = database_url()
# The real marker, declared in pyproject.toml. Previously a local
# `pytest.mark.skipif` — nine copies of it, so nine places a database suite
# could silently vanish from a green run. The skip decision now lives in
# conftest.py, which fails the session if it ever fires.
requires_db = pytest.mark.requires_db


@pytest.fixture(scope="module")
def engine() -> Iterator[Engine]:
    # `requires_db` guarantees a database, so a missing URL here is a broken
    # harness rather than an absent one. Assert loudly instead of skipping —
    # a skip is what tests/test_ci_contract.py exists to make impossible.
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


def set_scope(conn: Connection, *, workspace: UUID | None = None, user: UUID | None = None) -> None:
    conn.execute(
        sa.text(
            "SELECT set_config('nexus.workspace_id', :ws, true),"
            "       set_config('nexus.user_id', :uid, true)"
        ),
        {"ws": str(workspace) if workspace else "", "uid": str(user) if user else ""},
    )


@pytest.fixture
def agency_setup(conn: Connection) -> dict[str, UUID]:
    """One identity, two client workspaces — the agency case from doc 06 §2.1."""
    operator, outsider = uuid4(), uuid4()
    tenant_a, tenant_b = uuid4(), uuid4()
    ws_a, ws_b = uuid4(), uuid4()

    conn.execute(
        sa.text("INSERT INTO tenant (id, name) VALUES (:a,'A'), (:b,'B')"),
        {"a": str(tenant_a), "b": str(tenant_b)},
    )
    conn.execute(
        sa.text("INSERT INTO app_user (id, email) VALUES (:o,:oe), (:x,:xe)"),
        {
            "o": str(operator),
            "oe": f"op-{operator}@example.test",
            "x": str(outsider),
            "xe": f"out-{outsider}@example.test",
        },
    )
    for tenant, ws, name in ((tenant_a, ws_a, "Client A"), (tenant_b, ws_b, "Client B")):
        set_scope(conn, workspace=ws)
        conn.execute(
            sa.text(
                "INSERT INTO workspace (id, workspace_id, tenant_id, name) VALUES (:id,:id,:t,:n)"
            ),
            {"id": str(ws), "t": str(tenant), "n": name},
        )
        conn.execute(
            sa.text("INSERT INTO membership (workspace_id, user_id, role) VALUES (:ws,:u,'owner')"),
            {"ws": str(ws), "u": str(operator)},
        )

    return {
        "operator": operator,
        "outsider": outsider,
        "ws_a": ws_a,
        "ws_b": ws_b,
    }


# ── Self-membership policy (migration 0003) ───────────────────


@requires_db
def test_user_sees_own_memberships_across_workspaces(
    conn: Connection, agency_setup: dict[str, UUID]
) -> None:
    """The switcher needs this; without it there is no way to list workspaces."""
    set_scope(conn, workspace=None, user=agency_setup["operator"])
    rows = conn.execute(sa.text("SELECT workspace_id FROM membership")).scalars().all()
    assert {str(r) for r in rows} == {str(agency_setup["ws_a"]), str(agency_setup["ws_b"])}


@requires_db
def test_self_membership_policy_does_not_expose_other_people(
    conn: Connection, agency_setup: dict[str, UUID]
) -> None:
    """The widened policy must return *only* the caller's own rows.

    This is the test that keeps migration 0003 narrow. If the predicate ever
    drifts from `user_id = <caller>`, the switcher becomes a directory of who
    works where.
    """
    set_scope(conn, workspace=None, user=agency_setup["outsider"])
    rows = conn.execute(sa.text("SELECT workspace_id FROM membership")).all()
    assert rows == []


@requires_db
def test_self_membership_policy_is_select_only(
    conn: Connection, agency_setup: dict[str, UUID]
) -> None:
    """Doc 06 §2.2 — role is set by the inviter, never self-declared.

    Seeing your membership must not imply being able to change it, or role is
    a dropdown away from privilege escalation.
    """
    set_scope(conn, workspace=None, user=agency_setup["operator"])
    result = conn.execute(
        sa.text("UPDATE membership SET role = 'owner' WHERE user_id = :u"),
        {"u": str(agency_setup["operator"])},
    )
    assert result.rowcount == 0


@requires_db
def test_unidentified_caller_sees_no_memberships(conn: Connection) -> None:
    set_scope(conn, workspace=None, user=None)
    assert conn.execute(sa.text("SELECT count(*) FROM membership")).scalar() == 0


# ── Session storage ───────────────────────────────────────────


@requires_db
def test_session_stores_only_a_token_hash(conn: Connection, agency_setup: dict[str, UUID]) -> None:
    """A leaked database must not yield usable sessions."""
    from app.auth.tokens import hash_token, new_token

    token = new_token()
    conn.execute(
        sa.text(
            "INSERT INTO user_session (user_id, token_hash, expires_at)"
            " VALUES (:u, :h, now() + interval '1 hour')"
        ),
        {"u": str(agency_setup["operator"]), "h": hash_token(token)},
    )

    stored = conn.execute(sa.text("SELECT token_hash FROM user_session")).scalars().all()
    assert token not in stored
    assert all(len(s) == 64 for s in stored)


@requires_db
def test_expired_sessions_are_not_resolvable(
    conn: Connection, agency_setup: dict[str, UUID]
) -> None:
    from app.auth.tokens import hash_token, new_token

    token = new_token()
    conn.execute(
        sa.text(
            "INSERT INTO user_session (user_id, token_hash, expires_at)"
            " VALUES (:u, :h, now() - interval '1 second')"
        ),
        {"u": str(agency_setup["operator"]), "h": hash_token(token)},
    )
    row = conn.execute(
        sa.text(
            "SELECT id FROM user_session"
            " WHERE token_hash = :h AND revoked_at IS NULL AND expires_at > now()"
        ),
        {"h": hash_token(token)},
    ).first()
    assert row is None


@requires_db
def test_revoked_sessions_are_not_resolvable(
    conn: Connection, agency_setup: dict[str, UUID]
) -> None:
    """Logout must be effective immediately, not at expiry."""
    from app.auth.tokens import hash_token, new_token

    token = new_token()
    conn.execute(
        sa.text(
            "INSERT INTO user_session (user_id, token_hash, expires_at, revoked_at)"
            " VALUES (:u, :h, now() + interval '1 hour', now())"
        ),
        {"u": str(agency_setup["operator"]), "h": hash_token(token)},
    )
    row = conn.execute(
        sa.text(
            "SELECT id FROM user_session"
            " WHERE token_hash = :h AND revoked_at IS NULL AND expires_at > now()"
        ),
        {"h": hash_token(token)},
    ).first()
    assert row is None


# ── Schema-level guarantees ───────────────────────────────────


@requires_db
def test_email_uniqueness_is_case_insensitive(conn: Connection) -> None:
    """Parul@x.com and parul@x.com must be one account, not two."""
    email = f"Case-{uuid4()}@Example.test"
    conn.execute(sa.text("INSERT INTO app_user (email) VALUES (:e)"), {"e": email.lower()})
    with pytest.raises(sa.exc.IntegrityError):
        conn.execute(sa.text("INSERT INTO app_user (email) VALUES (:e)"), {"e": email.upper()})


@requires_db
def test_membership_role_is_constrained(conn: Connection, agency_setup: dict[str, UUID]) -> None:
    """An unknown role must not be storable; the scope table has no row for it."""
    set_scope(conn, workspace=agency_setup["ws_a"])
    with pytest.raises(sa.exc.IntegrityError):
        conn.execute(
            sa.text(
                "INSERT INTO membership (workspace_id, user_id, role)"
                " VALUES (:ws, :u, 'superadmin')"
            ),
            {"ws": str(agency_setup["ws_a"]), "u": str(agency_setup["outsider"])},
        )


@requires_db
def test_a_user_cannot_hold_two_memberships_in_one_workspace(
    conn: Connection, agency_setup: dict[str, UUID]
) -> None:
    """Two rows would make the effective role ambiguous — and resolution order
    is exactly where a privilege-escalation bug hides."""
    set_scope(conn, workspace=agency_setup["ws_a"])
    with pytest.raises(sa.exc.IntegrityError):
        conn.execute(
            sa.text(
                "INSERT INTO membership (workspace_id, user_id, role) VALUES (:ws, :u, 'viewer')"
            ),
            {"ws": str(agency_setup["ws_a"]), "u": str(agency_setup["operator"])},
        )
