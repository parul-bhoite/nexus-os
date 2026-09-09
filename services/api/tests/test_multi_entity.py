"""ADR 0026's four guards, and the one that replaces a deleted rule.

Multi-entity reverses Q9/Q17 — one person, one company. The reversal itself is a
deletion: `membership` was left many-to-many deliberately (`doc/11` §3.2, *"keep
the schema, constrain the product"*), so lifting the constraint needed no
migration. What needs care is everything around it.

The four:

1. **Reachable workspaces are exactly the caller's memberships.** This replaces
   `assert_no_live_membership`. A rule removed without its replacement asserted
   is a rule nobody notices the absence of.
2. **The group path never reads without a workspace scope.** Everything in this
   codebase is built so a cross-tenant read cannot happen, and the group view is
   the one read that spans tenants — so it opens one scoped session per entity
   rather than loosening a predicate.
3. **Nothing is cached across a switch.** I5 was retired with
   `_teardown_on_switch` and comes back with this. Entity A's figures under
   entity B's name is the worst failure this product can have, and it would look
   entirely normal on screen.
4. **Departments are per entity.** Somebody may be Finance at one and
   Operations at another, so a group read must not report one set.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.service import memberships_for_user
from app.config import get_settings
from app.db import _unscoped_session, get_engine, get_sessionmaker
from app.domain.group import read_across_entities
from app.domain.scopes import Department
from app.domain.session import ScopedSession
from app.retrieval.scoped import apply_user_scope, apply_workspace_scope
from tests.dburl import async_database_url

pytestmark = pytest.mark.requires_db

ASYNC_DB_URL = async_database_url()


@dataclass(frozen=True, slots=True)
class Group:
    """One person holding two entities, with different departments in each."""

    user_id: UUID
    tenant_id: UUID
    finance_ws: UUID
    operations_ws: UUID
    stranger_ws: UUID
    """A third entity this person holds **no** membership in. A group test with
    only the caller's own workspaces cannot tell isolation from an empty
    table — the same reason `evals/test_permissions.py` seeds a second one."""


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


async def _seed(db: AsyncSession) -> Group:
    group = Group(uuid4(), uuid4(), uuid4(), uuid4(), uuid4())

    await db.execute(
        sa.text("INSERT INTO tenant (id, name) VALUES (:t, 'Group Test')"),
        {"t": str(group.tenant_id)},
    )
    await db.execute(
        sa.text("INSERT INTO app_user (id, email) VALUES (:u, :e)"),
        {"u": str(group.user_id), "e": f"group-{group.user_id}@example.invalid"},
    )

    for workspace, name in (
        (group.finance_ws, "Entity One"),
        (group.operations_ws, "Entity Two"),
        (group.stranger_ws, "Not Theirs"),
    ):
        await apply_workspace_scope(db, str(workspace))
        await db.execute(
            sa.text(
                "INSERT INTO workspace (id, workspace_id, tenant_id, name)"
                " VALUES (:id, :id, :t, :n)"
            ),
            {"id": str(workspace), "t": str(group.tenant_id), "n": name},
        )

    # **Different departments per entity**, which is the arrangement the fourth
    # guard is about. Finance at one, Operations at the other, and a manager
    # rather than an owner so `departments` is read from the row rather than
    # granted by the role.
    for workspace, department in (
        (group.finance_ws, "finance"),
        (group.operations_ws, "operations"),
    ):
        await apply_workspace_scope(db, str(workspace))
        await db.execute(
            sa.text(
                "INSERT INTO membership (workspace_id, user_id, role, departments)"
                " VALUES (:ws, :u, 'department_manager', ARRAY[:d])"
            ),
            {"ws": str(workspace), "u": str(group.user_id), "d": department},
        )

    return group


# ── 1. The rule that replaces the deleted guard ───────────────


async def test_reachable_workspaces_are_exactly_the_callers_memberships(
    app_db: None,
) -> None:
    """The replacement for `assert_no_live_membership`.

    That guard made "one person, one company" true by refusing a second
    `membership` row. Deleting it does **not** widen what anybody can reach —
    reach was always the membership — and this is the assertion that says so.

    The third workspace is the whole test: a group read that returned two
    entities would pass against a seed with two, and fail nothing when a
    predicate quietly matched everything.
    """
    async with _unscoped_session() as db:
        group = await _seed(db)
        await db.flush()

        await apply_user_scope(db, group.user_id)
        memberships = await memberships_for_user(db, user_id=group.user_id)

        held = {m.workspace_id for m in memberships}

        assert held == {group.finance_ws, group.operations_ws}
        assert group.stranger_ws not in held, (
            "a workspace this person has no membership in must not be reachable,"
            " and multi-entity changes nothing about that"
        )


async def test_a_second_membership_is_no_longer_refused(app_db: None) -> None:
    """The reversal itself. Two live memberships, and no migration needed —
    `membership` was many-to-many all along (`doc/11` §3.2)."""
    from app.domain.membership import live_membership_count

    async with _unscoped_session() as db:
        group = await _seed(db)
        await db.flush()

        assert await live_membership_count(db, user_id=group.user_id) == 2


# ── 2. The group read never spans a scope ─────────────────────


async def test_the_group_read_opens_one_scope_per_entity(app_db: None) -> None:
    """The property this module exists to preserve.

    A single loosened query would be one round trip instead of N, and its first
    bug would be invisible: a workspace id appearing in a list it should not be
    in returns rows rather than an error.

    So the assertion is on the **scopes handed to the reader** — one per entity,
    each carrying exactly one workspace id.
    """
    async with _unscoped_session() as db:
        group = await _seed(db)
        await db.commit()

    seen: list[UUID] = []

    async def read_one(scope: ScopedSession) -> UUID:
        seen.append(scope.workspace_id)
        return scope.workspace_id

    try:
        reading = await read_across_entities(
            user_id=group.user_id,
            session_factory=_unscoped_session,
            open_scoped=read_one,
        )

        assert sorted(seen) == sorted([group.finance_ws, group.operations_ws])
        assert reading.total == 2
        assert reading.covered == 2
        assert reading.complete
        assert group.stranger_ws not in seen
    finally:
        await _teardown(group)


async def test_an_entity_that_cannot_be_read_is_named_not_dropped(
    app_db: None,
) -> None:
    """One company's source being unreachable must not blank the other three —
    and must not quietly shrink the denominator either. A group total silently
    missing one entity is indistinguishable from a smaller group."""
    async with _unscoped_session() as db:
        group = await _seed(db)
        await db.commit()

    async def fail_on_operations(scope: ScopedSession) -> str:
        if scope.workspace_id == group.operations_ws:
            raise RuntimeError("accounting unreachable")
        return "read"

    try:
        reading = await read_across_entities(
            user_id=group.user_id,
            session_factory=_unscoped_session,
            open_scoped=fail_on_operations,
        )

        assert reading.covered == 1
        assert reading.total == 2, "the denominator counts what was asked, not what answered"
        assert reading.unreadable == (group.operations_ws,)
        assert not reading.complete
    finally:
        await _teardown(group)


async def test_a_person_with_no_membership_has_an_empty_group_not_an_error(
    app_db: None,
) -> None:
    """A group is a property of memberships. Nobody's is not a failure."""

    async def never_called(scope: ScopedSession) -> str:
        raise AssertionError("no entity should be read for a person holding none")

    reading = await read_across_entities(
        user_id=uuid4(),
        session_factory=_unscoped_session,
        open_scoped=never_called,
    )

    assert reading.entities == ()
    assert reading.total == 0


# ── 4. Departments are per entity ─────────────────────────────


async def test_departments_are_resolved_per_entity_and_not_per_person(
    app_db: None,
) -> None:
    """ADR 0026's consequence 7, and the one most likely to be got wrong.

    This person is a Finance manager at one entity and an Operations manager at
    the other. A group view that reported "their departments" as one set would
    be wrong about every entity but one — and the direction of the error is the
    dangerous one: it would show them Finance figures under the company where
    they hold Operations.
    """
    async with _unscoped_session() as db:
        group = await _seed(db)
        await db.commit()

    async def departments_of(scope: ScopedSession) -> frozenset[Department]:
        return scope.departments

    try:
        reading = await read_across_entities(
            user_id=group.user_id,
            session_factory=_unscoped_session,
            open_scoped=departments_of,
        )

        by_workspace = {entity.workspace_id: entity.value for entity in reading.entities}

        assert by_workspace[group.finance_ws] == frozenset({Department.FINANCE})
        assert by_workspace[group.operations_ws] == frozenset({Department.OPERATIONS})
        assert by_workspace[group.finance_ws] != by_workspace[group.operations_ws]
    finally:
        await _teardown(group)


# ── 3. Nothing is cached across a switch (I5) ─────────────────


def test_nothing_is_cached_across_an_entity_switch() -> None:
    """I5, retired with `_teardown_on_switch` and back with ADR 0026.

    **Currently true by construction**, and this test is what stops that
    silently ceasing to be true. The only process-level caches are
    `get_settings`, `get_engine` and `get_sessionmaker` — all workspace-agnostic
    — and `current_scope` rebuilds the scope, including its departments, from
    the active membership on every request.

    So the guard is a census: every `lru_cache` in the application, checked
    against a list of the three that are allowed to exist. A fourth appearing
    fails here, and whoever adds it has to say how it is invalidated on switch.

    Entity A's figures under entity B's name would look completely normal on
    screen. That is why this is asserted as an equality and not a bound.
    """
    import ast
    from pathlib import Path

    app_root = Path(__file__).resolve().parents[1] / "app"
    cached: set[str] = set()

    for source in app_root.rglob("*.py"):
        tree = ast.parse(source.read_text())
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            for decorator in node.decorator_list:
                name = decorator.id if isinstance(decorator, ast.Name) else None
                if name is None and isinstance(decorator, ast.Attribute):
                    name = decorator.attr
                if name in {"lru_cache", "cache"}:
                    cached.add(f"{source.relative_to(app_root)}::{node.name}")

    # Six, and every one is keyed by the **process** rather than by anything
    # narrower: settings, three engines/sessionmakers, the language-model
    # provider and the embedder. None of them holds a workspace's data, which is
    # why none needs invalidating on switch — and why a seventh has to justify
    # itself here before it ships.
    #
    # Writing this list is what found `get_embedder`, which I had missed.
    assert cached == {
        "config.py::get_settings",
        "db.py::get_engine",
        "db.py::get_sessionmaker",
        "db.py::get_jobs_engine",
        "ai/registry.py::get_provider",
        "embeddings/registry.py::get_embedder",
    }, (
        "a new process-level cache appeared. If it is keyed by anything narrower"
        " than the process — a workspace, a person, a brain, a computed tile —"
        f" it must be invalidated when the session's entity changes. Found: {sorted(cached)}"
    )


async def _teardown(group: Group) -> None:
    async with _unscoped_session() as db:
        for workspace in (group.finance_ws, group.operations_ws, group.stranger_ws):
            await apply_workspace_scope(db, str(workspace))
            for statement in (
                "DELETE FROM audit_log WHERE workspace_id = :w",
                "DELETE FROM membership WHERE workspace_id = :w",
                "DELETE FROM workspace WHERE id = :w",
            ):
                await db.execute(sa.text(statement), {"w": str(workspace)})
        await db.execute(sa.text("DELETE FROM app_user WHERE id = :u"), {"u": str(group.user_id)})
        await db.execute(sa.text("DELETE FROM tenant WHERE id = :t"), {"t": str(group.tenant_id)})
        await db.commit()


# ── The switch, and what its reply must say ───────────────────


async def test_the_switch_reply_names_the_entity_just_entered(app_db: None) -> None:
    """The bug a browser found and no test would have.

    `CurrentSession` is resolved at the start of the request, so after the
    `UPDATE` its `active_workspace_id` still holds the entity being **left**.
    The first version of the route returned the list computed against it, so the
    reply said the switch had not happened — while the audit row and the very
    next request both said it had.

    Every test here asserted the write or the refusal. None asserted the flag in
    the reply, which is the only thing a client reads.
    """
    from app.routes.auth import _workspaces_for

    async with _unscoped_session() as db:
        group = await _seed(db)
        await db.commit()

    try:
        entered = await _workspaces_for(group.user_id, group.operations_ws)
        active = {w.workspace_id for w in entered.workspaces if w.active}

        assert active == {group.operations_ws}, "the id passed in, not the session's"
        assert len(entered.workspaces) == 2

        # And the other direction, so the test cannot pass by always answering
        # with the same workspace.
        back = await _workspaces_for(group.user_id, group.finance_ws)
        assert {w.workspace_id for w in back.workspaces if w.active} == {group.finance_ws}
    finally:
        await _teardown(group)


async def test_the_switch_list_holds_the_role_at_each_entity(app_db: None) -> None:
    """Being an Owner of one company grants nothing at another, and the switcher
    shows which is which — an Owner at one and a manager at the next is the
    ordinary case for a group finance director."""
    from app.routes.auth import _workspaces_for

    async with _unscoped_session() as db:
        group = await _seed(db)
        await db.commit()

    try:
        listed = await _workspaces_for(group.user_id, group.finance_ws)
        roles = {w.workspace_id: w.role for w in listed.workspaces}

        # The seed makes them a department manager at both, so the assertion is
        # that the role is read per membership rather than assumed.
        assert roles[group.finance_ws] == "department_manager"
        assert roles[group.operations_ws] == "department_manager"
        assert group.stranger_ws not in roles
    finally:
        await _teardown(group)
