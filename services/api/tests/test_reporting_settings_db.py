"""The reporting endpoint against a real database, and the restate rule.

`test_reporting_settings.py` proves the derivation — which tiles a setting
moves, and that presentation moves none. This proves the half that only Postgres
can: the defaults migration 0027 installed, the stamp that moves *only* when a
number is actually restated, the audit row that goes with it, and the read/write
asymmetry.

`test_document_upload_db.py` is the pattern, and the reason is the same one
recorded there: a route whose decisions are proved over a substituted writer is a
route whose writes have never touched a database. The four CHECKs in 0027 are
exactly the shape of defect that gap hid twice before.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy import Connection, Engine, create_engine

from app.auth.csrf import CSRF_COOKIE_NAME, CSRF_HEADER_NAME
from app.auth.tokens import hash_token, new_token
from app.config import get_settings
from app.db import get_engine, get_sessionmaker
from app.domain.reporting import DEFAULT_TIMEZONE, WeekStart
from app.main import create_app
from tests.dburl import async_database_url, database_url

DB_URL = database_url()
ASYNC_DB_URL = async_database_url()

requires_db = pytest.mark.requires_db

pytestmark = requires_db

CSRF = "a-known-csrf-value"
REPORTING = "/companies/current/reporting"


@dataclass(frozen=True, slots=True)
class Seed:
    tenant_id: UUID
    user_id: UUID
    workspace_id: UUID
    session_token: str


@pytest.fixture(scope="module")
def engine() -> Iterator[Engine]:
    assert DB_URL is not None
    eng = create_engine(DB_URL, poolclass=sa.pool.NullPool)
    yield eng
    eng.dispose()


def _set_scope(conn: Connection, *, workspace: UUID | None, user: UUID | None) -> None:
    conn.execute(
        sa.text(
            "SELECT set_config('nexus.workspace_id', :ws, false),"
            "       set_config('nexus.user_id', :uid, false)"
        ),
        {"ws": str(workspace) if workspace else "", "uid": str(user) if user else ""},
    )


def _seed(engine: Engine, *, role: str) -> Iterator[Seed]:
    seed = Seed(uuid4(), uuid4(), uuid4(), new_token())

    with engine.connect() as conn:
        _set_scope(conn, workspace=seed.workspace_id, user=seed.user_id)
        conn.execute(
            sa.text("INSERT INTO tenant (id, name) VALUES (:t, 'Reporting DB Test')"),
            {"t": str(seed.tenant_id)},
        )
        conn.execute(
            sa.text("INSERT INTO app_user (id, email) VALUES (:u, :e)"),
            {"u": str(seed.user_id), "e": f"reporting-{seed.user_id}@example.invalid"},
        )
        conn.execute(
            sa.text(
                "INSERT INTO workspace (id, workspace_id, tenant_id, name)"
                " VALUES (:id, :id, :t, 'Reporting DB Test')"
            ),
            {"id": str(seed.workspace_id), "t": str(seed.tenant_id)},
        )
        conn.execute(
            sa.text(
                "INSERT INTO membership (workspace_id, user_id, role, departments)"
                " VALUES (:ws, :u, :role, ARRAY['finance'])"
            ),
            {"ws": str(seed.workspace_id), "u": str(seed.user_id), "role": role},
        )
        conn.execute(
            sa.text(
                "INSERT INTO user_session"
                " (user_id, token_hash, expires_at, active_workspace_id, user_agent)"
                " VALUES (:u, :h, now() + interval '1 hour', :ws, 'pytest')"
            ),
            {
                "u": str(seed.user_id),
                "h": hash_token(seed.session_token),
                "ws": str(seed.workspace_id),
            },
        )
        conn.commit()

    yield seed

    with engine.connect() as conn:
        _set_scope(conn, workspace=seed.workspace_id, user=seed.user_id)
        for statement in (
            "DELETE FROM audit_log WHERE workspace_id = :ws",
            "DELETE FROM membership WHERE workspace_id = :ws",
            "DELETE FROM workspace WHERE id = :ws",
        ):
            conn.execute(sa.text(statement), {"ws": str(seed.workspace_id)})
        conn.execute(
            sa.text("DELETE FROM user_session WHERE user_id = :u"), {"u": str(seed.user_id)}
        )
        conn.execute(sa.text("DELETE FROM app_user WHERE id = :u"), {"u": str(seed.user_id)})
        conn.execute(sa.text("DELETE FROM tenant WHERE id = :t"), {"t": str(seed.tenant_id)})
        conn.commit()


@pytest.fixture
def owner(engine: Engine) -> Iterator[Seed]:
    yield from _seed(engine, role="owner")


@pytest.fixture
def contributor(engine: Engine) -> Iterator[Seed]:
    yield from _seed(engine, role="contributor")


def _client(seed: Seed, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    assert ASYNC_DB_URL is not None
    monkeypatch.setenv("NEXUS_DATABASE_URL", ASYNC_DB_URL)
    for cache in (get_settings, get_engine, get_sessionmaker):
        cache.cache_clear()

    app = create_app()
    try:
        with TestClient(app) as client:
            client.cookies.set("nexus_session", seed.session_token)
            client.cookies.set(CSRF_COOKIE_NAME, CSRF)
            yield client
    finally:
        for cache in (get_settings, get_engine, get_sessionmaker):
            cache.cache_clear()


@pytest.fixture
def as_owner(owner: Seed, monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[TestClient, Seed]]:
    for client in _client(owner, monkeypatch):
        yield client, owner


@pytest.fixture
def as_contributor(
    contributor: Seed, monkeypatch: pytest.MonkeyPatch
) -> Iterator[tuple[TestClient, Seed]]:
    for client in _client(contributor, monkeypatch):
        yield client, contributor


def _put(client: TestClient, **overrides: Any) -> Any:
    body: dict[str, Any] = {
        # Required since the currency gap was closed. A PUT without them is a
        # 422 — the panel always sends every field, and letting them be omitted
        # would mean deciding whether an absent currency clears one or keeps it.
        "currency": "OMR",
        "country": "OM",
        "fiscal_year_start_month": 1,
        "week_start": "sunday",
        "timezone": DEFAULT_TIMEZONE,
        "scale": "thousands",
        "decimals": 1,
    }
    body.update(overrides)
    return client.put(REPORTING, json=body, headers={CSRF_HEADER_NAME: CSRF})


def _stamp_and_audit(engine: Engine, workspace_id: UUID) -> tuple[Any, list[Any]]:
    with engine.connect() as conn:
        _set_scope(conn, workspace=workspace_id, user=None)
        stamp = conn.execute(
            sa.text("SELECT reporting_changed_at FROM workspace WHERE id = :ws"),
            {"ws": str(workspace_id)},
        ).scalar_one()
        rows = list(
            conn.execute(
                sa.text(
                    "SELECT action, reason FROM audit_log"
                    " WHERE workspace_id = :ws AND action = 'reporting_changed'"
                ),
                {"ws": str(workspace_id)},
            ).mappings()
        )
    return stamp, rows


# ── What migration 0027 installed ─────────────────────────────


def test_a_new_workspace_can_already_state_its_window(
    as_owner: tuple[TestClient, Seed],
) -> None:
    """The whole reason the columns have server defaults.

    A dashboard cannot render without all five, so a workspace that has never
    seen the settings screen must still be able to say what its windows are cut
    against. Nullable columns would have pushed that decision into every reader.
    """
    client, _ = as_owner
    response = client.get(REPORTING)

    assert response.status_code == 200
    body = response.json()

    assert body["week_start"] == WeekStart.SUNDAY.value, "the GCC working week"
    assert body["timezone"] == DEFAULT_TIMEZONE
    assert body["fiscal_year_start_month"] == 1
    assert body["changed_at"] is None, "never changed is not the same as changed at creation"


def test_every_setting_arrives_with_the_sentence_that_makes_it_checkable(
    as_owner: tuple[TestClient, Seed],
) -> None:
    """The count is served, not computed in the browser. A tile count is a claim,
    and the browser is the last place that should be deciding one."""
    client, _ = as_owner
    settings = client.get(REPORTING).json()["settings"]

    assert {s["key"] for s in settings} == {
        "currency",
        "fiscal_year_start_month",
        "week_start",
        "timezone",
        "scale",
        "decimals",
    }
    for setting in settings:
        assert setting["changes"]
        if not setting["restates"]:
            continue
        if setting["key"] == "currency":
            # **Restates and moves nothing**, which is the third case the
            # screen has to be able to say. It relabels every figure in the
            # product and recomputes none, so a "moves N tiles" sentence would
            # read "moves 0 tiles" — true and useless.
            assert setting["moves_tiles"] == 0
            assert setting["moves_departments"] == []
        else:
            assert setting["moves_tiles"] > 0
            assert setting["moves_departments"]


# ── The restate rule ──────────────────────────────────────────


def test_moving_the_reporting_week_stamps_and_logs_it(
    as_owner: tuple[TestClient, Seed], engine: Engine
) -> None:
    """`doc/13` §10. Numbers are never silently restated under a founder who has
    already acted on them, so the change carries a stamp every later derivation
    is compared against and an audit row naming who moved it."""
    client, seed = as_owner

    response = _put(client, week_start="monday")

    assert response.status_code == 200
    assert response.json()["week_start"] == "monday"

    stamp, audit = _stamp_and_audit(engine, seed.workspace_id)
    assert stamp is not None, "the restate stamp moved"
    assert len(audit) == 1
    assert "monday" in audit[0]["reason"]


def test_changing_only_the_units_restates_nothing(
    as_owner: tuple[TestClient, Seed], engine: Engine
) -> None:
    """`184.6K` and `184,600` are the same number.

    So the stamp does not move and nothing is logged — logging a display
    preference as a restatement would bury the three changes that matter among
    the two that do not.
    """
    client, seed = as_owner

    response = _put(client, scale="units", decimals=0)

    assert response.status_code == 200
    assert response.json()["scale"] == "units"

    stamp, audit = _stamp_and_audit(engine, seed.workspace_id)
    assert stamp is None
    assert audit == []


def test_the_database_refuses_a_week_that_is_not_a_day(
    as_owner: tuple[TestClient, Seed],
) -> None:
    """Bounded in three places — the request model, the dataclass, and
    `ck_workspace_reporting_week_start`. This is the outermost one, and a 422
    rather than a 500 is the difference between a refusal and a crash."""
    client, _ = as_owner

    assert _put(client, week_start="someday").status_code == 422
    assert _put(client, fiscal_year_start_month=13).status_code == 422
    assert _put(client, decimals=5).status_code == 422


# ── Who may read, and who may change ─────────────────────────


def test_a_contributor_may_read_the_assumptions_and_not_move_them(
    as_contributor: tuple[TestClient, Seed],
) -> None:
    """The asymmetry, and it is deliberate in both directions.

    **Read:** a number is only checkable if the assumptions under it are visible
    to the person checking, and a working drawer on a Contributor's own tile
    cites the reporting week. Hiding it would make their own arithmetic
    unverifiable.

    **Write:** 403 rather than 404. This caller can see the resource — the same
    endpoint just served it — so its existence is not a secret. What they may
    not do is move it, and saying so is the honest answer.
    """
    client, _ = as_contributor

    read = client.get(REPORTING)
    assert read.status_code == 200
    assert read.json()["may_administer"] is False

    refused = _put(client, week_start="monday")
    assert refused.status_code == 403
    assert "owner" in refused.json()["detail"].lower()
