"""The invitation email: what it says, and that it is actually sent.

`build_invitation_email` was written, wired into `create_invitation`, and
covered by **nothing** — found by grepping the suite for its name and getting no
hits. That is the gap that matters here: the delivery half of an invitation can
be deleted, or quietly stop being called, and every test in
`test_invitation_flow.py` would still pass, because that file proves the *token
and the policies* rather than the send.

Two levels, because they fail for different reasons:

- The **content** tests drive the real function. They are pure, so they are
  cheap, and they are where the `inviter` branch lives.
- The **wiring** test reads `create_invitation`'s syntax tree and asserts the
  send is still there. It is structural for the same reason
  `test_scan_boundary.py` is: driving the real route needs an authenticated
  owner *and* a verified domain (D19's gate), and a test that expensive tends to
  be the one somebody deletes — while the failure it guards against is simply
  "the call is gone".
"""

from __future__ import annotations

import ast
import inspect
from collections.abc import AsyncIterator
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.auth.invitations_email import build_invitation_email
from app.routes.setup import INVITATION_SENDER_SQL
from tests.dburl import async_database_url

BASE = "https://app.example.om"
TOKEN = "a-token-nobody-can-guess"

ASYNC_DB_URL = async_database_url()
requires_db = pytest.mark.requires_db


# ── What it says ──────────────────────────────────────────────


def test_the_link_carries_the_token_and_the_accept_path() -> None:
    """The link is the whole invitation: the token names the workspace, the role
    and the departments, so a recipient chooses none of them and structurally
    cannot choose wrong."""
    email = build_invitation_email(to="new@example.om", token=TOKEN, base_url=BASE, company="Acme")

    assert f"{BASE}/invitations/accept?token={TOKEN}" in email.text_body


def test_a_trailing_slash_on_the_base_url_does_not_double() -> None:
    email = build_invitation_email(
        to="new@example.om", token=TOKEN, base_url=f"{BASE}/", company="Acme"
    )

    assert "//invitations" not in email.text_body
    assert f"{BASE}/invitations/accept?token={TOKEN}" in email.text_body


def test_the_subject_names_the_company() -> None:
    """An invitation that does not say which company it is for reads as
    phishing — and the recipient may hold accounts at several."""
    email = build_invitation_email(to="new@example.om", token=TOKEN, base_url=BASE, company="Acme")

    assert "Acme" in email.subject


def test_the_inviter_is_named_when_known() -> None:
    """The half that had no caller until this pass. `display_name` is nullable,
    so both branches are real states rather than one being theoretical."""
    email = build_invitation_email(
        to="new@example.om", token=TOKEN, base_url=BASE, company="Acme", inviter="Priya"
    )

    assert "Priya has invited you" in email.subject
    assert "Priya has invited you" in email.text_body


def test_an_unknown_inviter_falls_back_rather_than_naming_a_blank() -> None:
    email = build_invitation_email(
        to="new@example.om", token=TOKEN, base_url=BASE, company="Acme", inviter=None
    )

    assert "You have been invited" in email.subject
    assert "None" not in email.subject, "a missing name must not be rendered as the word None"
    assert "None" not in email.text_body


def test_the_token_is_never_in_the_subject() -> None:
    """Subjects travel further than bodies — notification previews, mail
    clients' window titles, screen shares — and this one is a bearer credential
    that joins a workspace."""
    email = build_invitation_email(
        to="new@example.om", token=TOKEN, base_url=BASE, company="Acme", inviter="Priya"
    )

    assert TOKEN not in email.subject


# ── That it is sent at all ────────────────────────────────────


def _create_invitation_tree() -> ast.FunctionDef:
    from app.routes import setup

    source = Path(inspect.getfile(setup)).read_text(encoding="utf-8")
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "create_invitation":
            # `AsyncFunctionDef` is not a `FunctionDef`, but every attribute this
            # test reads is shared; the cast keeps the annotation honest.
            return node  # type: ignore[return-value]
    raise AssertionError("create_invitation is gone from app/routes/setup.py")


def test_the_route_still_queues_the_invitation_email() -> None:
    """The regression this file exists for: the send being removed, or never
    reached, while the token keeps coming back to the inviter and every other
    invitation test stays green."""
    calls = [n for n in ast.walk(_create_invitation_tree()) if isinstance(n, ast.Call)]

    queued = [
        call
        for call in calls
        if isinstance(call.func, ast.Attribute) and call.func.attr == "add_task"
    ]
    assert queued, "the invitation email is no longer queued as a background task"

    built = [
        call
        for call in calls
        if isinstance(call.func, ast.Name) and call.func.id == "build_invitation_email"
    ]
    assert built, "create_invitation no longer builds an invitation email"


def test_the_route_passes_the_inviter_through() -> None:
    """`inviter` is optional on the builder, so omitting it is silent — the
    email simply stops naming who invited you, and no test would notice. It had
    in fact never been passed at all until this pass."""
    built = next(
        call
        for call in ast.walk(_create_invitation_tree())
        if isinstance(call, ast.Call)
        and isinstance(call.func, ast.Name)
        and call.func.id == "build_invitation_email"
    )

    assert "inviter" in {kw.arg for kw in built.keywords}, (
        "create_invitation builds the email without an inviter, so every "
        "invitation reads 'You have been invited' rather than naming a person"
    )


# ── Where the inviter's name comes from ───────────────────────


@pytest.fixture
async def db() -> AsyncIterator[AsyncSession]:
    """One transaction, rolled back — the suite leaves nothing on a shared
    database. Same shape as `test_invitation_flow.py`'s fixture."""
    assert ASYNC_DB_URL is not None
    engine = create_async_engine(ASYNC_DB_URL, poolclass=NullPool)
    async with engine.connect() as connection:
        transaction = await connection.begin()
        session = AsyncSession(bind=connection, expire_on_commit=False)
        try:
            yield session
        finally:
            await session.close()
            await transaction.rollback()
    await engine.dispose()


async def _seed(db: AsyncSession, *, display_name: str | None) -> tuple[UUID, UUID]:

    user_id, workspace_id = uuid4(), uuid4()
    await db.execute(
        text("INSERT INTO app_user (id, email, display_name) VALUES (:i, :e, :n)"),
        {"i": str(user_id), "e": f"u-{user_id}@example.com", "n": display_name},
    )
    tenant_id = (
        await db.execute(text("INSERT INTO tenant (name) VALUES ('Acme') RETURNING id"))
    ).scalar_one()
    await db.execute(
        text(
            "SELECT set_config('nexus.workspace_id', :w, true),"
            "       set_config('nexus.user_id', :u, true)"
        ),
        {"w": str(workspace_id), "u": str(user_id)},
    )
    await db.execute(
        text(
            "INSERT INTO workspace (id, workspace_id, tenant_id, name, domain)"
            " VALUES (:i, :i, :t, 'Acme', :d)"
        ),
        {"i": str(workspace_id), "t": str(tenant_id), "d": f"t-{workspace_id}.example"},
    )
    return user_id, workspace_id


@requires_db
async def test_the_sender_query_returns_the_company_and_the_inviter(db: AsyncSession) -> None:
    """The real statement the route runs, against a real database.

    A scalar subquery that named the wrong column, or a row attribute read under
    the wrong name, degrades to `None` rather than raising — so every invitation
    would quietly go back to "You have been invited" and the AST test above
    would still pass.
    """
    user_id, workspace_id = await _seed(db, display_name="Priya")

    row = (
        await db.execute(INVITATION_SENDER_SQL, {"w": str(workspace_id), "u": str(user_id)})
    ).first()

    assert row is not None
    assert row.company == "Acme"
    assert row.inviter == "Priya"


@requires_db
async def test_a_nameless_inviter_yields_none_rather_than_failing(db: AsyncSession) -> None:
    """`display_name` is nullable — somebody who registered without one still
    gets to invite, and the email falls back to "You have been invited"."""
    user_id, workspace_id = await _seed(db, display_name=None)

    row = (
        await db.execute(INVITATION_SENDER_SQL, {"w": str(workspace_id), "u": str(user_id)})
    ).first()

    assert row is not None
    assert row.company == "Acme"
    assert row.inviter is None


@requires_db
async def test_an_unknown_inviter_does_not_take_the_company_with_it(db: AsyncSession) -> None:
    """The reason this is a scalar subquery and not a join.

    Under a join, a user row that is missing or invisible produces **no row at
    all** — and the caller's `if row else "your company"` fallback would then
    strip the company name out of the subject line, which is the one thing
    keeping the email from reading as phishing.
    """
    _, workspace_id = await _seed(db, display_name="Priya")

    row = (
        await db.execute(INVITATION_SENDER_SQL, {"w": str(workspace_id), "u": str(uuid4())})
    ).first()

    assert row is not None, "the company must survive an inviter the query cannot see"
    assert row.company == "Acme"
    assert row.inviter is None
