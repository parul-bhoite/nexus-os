"""The audit trail is written, and reading it is a privilege.

Doc 07 I9. `audit_log` has existed since migration 0002 and nothing wrote to it
until P4 — which is the ordinary way an audit requirement dies. The table is
there, the schema review passes, and the log is empty.

So there are two claims here and they fail differently:

- **Every state change leaves a row.** Checked structurally *and* behaviourally.
  The structural half is an `ast` walk asserting each `AuditAction` has a call
  site, because a behavioural sweep over all nine would need nine fixtures and
  the one nobody wrote would be the one that silently stopped being logged.
- **Not everyone may read it.** A trail every member can read tells each of them
  who signed in, who was invited and who uploaded what — surveillance rather
  than accountability. Owner and Executive only.
"""

from __future__ import annotations

import ast
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy import Connection, Engine, create_engine

from app.config import get_settings
from app.db import get_engine, get_sessionmaker
from app.domain.audit import AuditAction
from app.main import create_app
from tests.dburl import async_database_url, database_url

APP_DIR = Path(__file__).resolve().parents[1] / "app"
PASSWORD = "Correct-horse-battery-staple1"
SIGNING_SECRET = "test-signing-secret-not-a-real-one"

DB_URL = database_url()
ASYNC_DB_URL = async_database_url()
requires_db = pytest.mark.requires_db

# `role_changed` is in the vocabulary and has no writer, because **the product
# has no way to change a role**: nothing in `app/` issues an `UPDATE membership`,
# and `membership_own_rows` is SELECT-only precisely so nobody can self-promote.
# P17 (Members) builds that screen, and the action is named here so the writer
# arrives with it rather than being remembered afterwards.
#
# Listed rather than omitted, and asserted below, so this exemption cannot
# quietly grow to cover an action that *does* have a path.
UNWIRED: dict[AuditAction, str] = {
    AuditAction.ROLE_CHANGED: "no role-change path exists yet — P17 (Members)",
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
    try:
        yield connection
    finally:
        connection.close()


@pytest.fixture
def api_env(tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> None:
    assert ASYNC_DB_URL is not None
    monkeypatch.setenv("NEXUS_DATABASE_URL", ASYNC_DB_URL)
    monkeypatch.setenv("NEXUS_STORAGE_SIGNING_SECRET", SIGNING_SECRET)
    monkeypatch.setenv("NEXUS_MAIL_ROOT", str(tmp_path_factory.mktemp("mail")))
    monkeypatch.setenv("NEXUS_LOGIN_BACKOFF_MAX_SECONDS", "0.01")
    for cache in (get_settings, get_engine, get_sessionmaker):
        cache.cache_clear()


@pytest.fixture
def client(api_env: None) -> Iterator[TestClient]:
    with TestClient(create_app()) as c:
        yield c
    for cache in (get_settings, get_engine, get_sessionmaker):
        cache.cache_clear()


@pytest.fixture
async def app_db(api_env: None) -> AsyncIterator[None]:
    yield
    await get_engine().dispose()


# ── Every action has a writer ─────────────────────────────────


def _recorded_actions() -> set[str]:
    """Every `AuditAction.X` named anywhere under `app/`, by an `ast` walk.

    Static rather than behavioural on purpose. A sweep that exercised all nine
    actions through the API would need a workspace, a membership, a session, a
    document and an invitation per case — and the case somebody failed to write
    is exactly the one that would then stop being logged without anything going
    red.
    """
    found: set[str] = set()
    for path in APP_DIR.rglob("*.py"):
        if path.name == "audit.py":
            continue  # the definition, not a use
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
                if node.value.id == "AuditAction":
                    found.add(node.attr)
            elif isinstance(node, ast.Attribute) and isinstance(node.value, ast.Attribute):
                if node.value.attr == "AuditAction":
                    found.add(node.attr)
    return found


def test_every_audit_action_is_written_somewhere() -> None:
    """I9's substrate, asserted as coverage of the vocabulary.

    An action in the enum with no call site is a state change nobody is
    recording — which is the state the whole table was in before this phase.
    """
    used = _recorded_actions()
    missing = {
        action for action in AuditAction if action.name not in used and action not in UNWIRED
    }
    assert missing == set(), (
        f"these actions are never written: {sorted(a.value for a in missing)}. "
        "Add the call site, or an UNWIRED entry saying which phase owns it."
    )


def test_no_unwired_entry_outlives_its_gap() -> None:
    """The exemption list prunes itself, exactly as `UNMAPPED` does in
    `test_constraint_enum_parity.py`. When P17 wires the role-change writer,
    this fails until the entry goes — an exemption nobody prunes becomes a list
    of things nobody checks."""
    used = _recorded_actions()
    stale = sorted(a.value for a in UNWIRED if a.name in used)
    assert not stale, f"UNWIRED still excuses {stale}, which now has a writer. Delete the entries."


def test_the_unwired_action_really_has_no_path() -> None:
    """The other half of the guard: `role_changed` is exempt because nothing can
    change a role, not because nobody got round to logging it. If an
    `UPDATE membership` appears, the exemption is wrong and this says so."""
    writes = [
        path.relative_to(APP_DIR).as_posix()
        for path in APP_DIR.rglob("*.py")
        if "UPDATE membership" in path.read_text(encoding="utf-8")
    ]
    assert writes == [], (
        f"{writes} changes a membership row, so a role can change and "
        "AuditAction.ROLE_CHANGED must be written there rather than exempted."
    )


# ── It is actually written, end to end ────────────────────────


@requires_db
async def test_a_login_writes_exactly_one_row(app_db: None) -> None:
    """The behavioural half, on the one action reachable without a workspace
    fixture — and the one that proves the row lands inside the caller's own
    transaction rather than beside it."""
    from app.db import _unscoped_session
    from app.domain import audit

    user, tenant, workspace = uuid4(), uuid4(), uuid4()

    async with _unscoped_session() as db:
        try:
            await db.execute(
                sa.text("INSERT INTO app_user (id, email) VALUES (:i,:e)"),
                {"i": str(user), "e": f"audit-{user.hex[:8]}@example.com"},
            )
            await db.execute(
                sa.text("INSERT INTO tenant (id, name) VALUES (:i,'T')"), {"i": str(tenant)}
            )
            await db.execute(
                sa.text("SELECT set_config('nexus.workspace_id', :w, true)"),
                {"w": str(workspace)},
            )
            await db.execute(
                sa.text(
                    "INSERT INTO workspace (id, workspace_id, tenant_id, name, domain,"
                    " domain_verified_at) VALUES (:i,:i,:t,'W',:d, now())"
                ),
                {"i": str(workspace), "t": str(tenant), "d": f"audit-{workspace.hex[:8]}.om"},
            )
            await db.commit()

            await audit.record(
                db,
                workspace_id=workspace,
                action=audit.AuditAction.LOGIN,
                actor_user_id=user,
            )
            await db.commit()

            # The GUC has to be set again to *read* it. `record` sets it with
            # `is_local => true`, so the commit above cleared it — and
            # `audit_log` carries FORCE ROW LEVEL SECURITY, so a select with no
            # scope matches nothing. That is the policy working: the first
            # version of this test asserted one row, got zero, and the zero was
            # correct.
            await db.execute(
                sa.text("SELECT set_config('nexus.workspace_id', :w, true)"),
                {"w": str(workspace)},
            )
            rows = (
                await db.execute(
                    sa.text("SELECT action, actor_user_id FROM audit_log WHERE workspace_id = :w"),
                    {"w": str(workspace)},
                )
            ).all()
            assert len(rows) == 1
            assert rows[0].action == "login"
            assert UUID(str(rows[0].actor_user_id)) == user
        finally:
            await db.rollback()
            # Same reason as the read above: the delete needs the scope too.
            await db.execute(
                sa.text("SELECT set_config('nexus.workspace_id', :w, true)"),
                {"w": str(workspace)},
            )
            for statement in (
                "DELETE FROM audit_log WHERE workspace_id = :w",
                "DELETE FROM workspace WHERE id = :w",
                "DELETE FROM tenant WHERE id = :t",
                "DELETE FROM app_user WHERE id = :u",
            ):
                await db.execute(
                    sa.text(statement), {"u": str(user), "w": str(workspace), "t": str(tenant)}
                )
            await db.commit()


# ── Reading it is a privilege ─────────────────────────────────


def test_the_audit_route_requires_the_executive_surface() -> None:
    """Owner and Executive, and asserted on the dependency rather than on a
    role list of its own.

    Two places that decide who is senior enough will eventually disagree, and
    the one nobody updated will be the one guarding something. `doc 06` §2.4
    already encodes this pair as the executive surface, so the route reuses it.
    """
    from app.deps import require_executive_surface
    from app.routes import audit as audit_route

    source = Path(audit_route.__file__).read_text(encoding="utf-8")
    assert require_executive_surface.__name__ in source
    # And no second opinion about roles anywhere in the file.
    assert "Role.OWNER" not in source
    assert "Role.EXECUTIVE" not in source


@requires_db
def test_an_unauthenticated_caller_gets_nothing(client: TestClient) -> None:
    """401, not an empty list. A trail that answers `{"entries": []}` to a
    stranger has told them the endpoint exists and that they are not in it."""
    assert client.get("/audit-log").status_code == 401
