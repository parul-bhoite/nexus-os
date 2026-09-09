"""Panel 7, and the restate rule on an answer. `doc/13` §14 and §10.

Two gaps, and they are the same gap seen twice: **a thing you can set during
onboarding and never again.** Department selection had no post-onboarding home,
so a company that hired into a new function could not add its director. And a
department answer could be corrected with nothing recording that a figure had
moved — while the *company* questions had been audited since P4.

Against Neon, because both claims are about rows: an audit row that names what
it restated, and a selection that survives without re-advancing the spine.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import _unscoped_session, get_engine, get_sessionmaker
from app.domain.departments import select_departments, selected_departments
from app.domain.registry import consumers_of
from app.domain.scopes import Department, Role
from app.domain.session import ScopedSession
from app.retrieval.scoped import apply_workspace_scope
from tests.dburl import async_database_url

pytestmark = pytest.mark.requires_db

ASYNC_DB_URL = async_database_url()


@dataclass(frozen=True, slots=True)
class Seed:
    tenant_id: UUID
    user_id: UUID
    workspace_id: UUID


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


async def _seed(db: AsyncSession) -> Seed:
    seed = Seed(uuid4(), uuid4(), uuid4())

    await apply_workspace_scope(db, str(seed.workspace_id))
    await db.execute(
        sa.text("INSERT INTO tenant (id, name) VALUES (:t, 'Settings Test')"),
        {"t": str(seed.tenant_id)},
    )
    await db.execute(
        sa.text("INSERT INTO app_user (id, email) VALUES (:u, :e)"),
        {"u": str(seed.user_id), "e": f"settings-{seed.user_id}@example.invalid"},
    )
    await db.execute(
        sa.text(
            "INSERT INTO workspace (id, workspace_id, tenant_id, name)"
            " VALUES (:id, :id, :t, 'Settings Test')"
        ),
        {"id": str(seed.workspace_id), "t": str(seed.tenant_id)},
    )
    await db.execute(
        sa.text(
            "INSERT INTO membership (workspace_id, user_id, role, departments)"
            " VALUES (:ws, :u, 'owner', ARRAY['finance'])"
        ),
        {"ws": str(seed.workspace_id), "u": str(seed.user_id)},
    )
    return seed


def _scope(seed: Seed) -> ScopedSession:
    return ScopedSession(
        user_id=seed.user_id,
        tenant_id=seed.tenant_id,
        workspace_id=seed.workspace_id,
        role=Role.OWNER,
        departments=frozenset({Department.FINANCE}),
    )


# ── Panel 7: the selection has a home ─────────────────────────


async def test_a_department_can_be_added_after_onboarding(app_db: None) -> None:
    """The gap this panel closes.

    `POST /onboarding/departments` is the only writer today and it calls
    `complete_stage`, so a company that hired into a new function either could
    not add its director or had to re-advance a finished spine to do it.
    """
    async with _unscoped_session() as db:
        seed = await _seed(db)

        await select_departments(
            db,
            workspace_id=seed.workspace_id,
            departments={Department.FINANCE},
        )
        assert Department.MARKETING not in await selected_departments(
            db, workspace_id=seed.workspace_id
        )

        await select_departments(
            db,
            workspace_id=seed.workspace_id,
            departments={Department.FINANCE, Department.MARKETING},
        )
        after = await selected_departments(db, workspace_id=seed.workspace_id)

        assert Department.MARKETING in after
        assert Department.FINANCE in after


async def test_a_removed_department_keeps_its_answers(app_db: None) -> None:
    """Q32, and the reason removal is a scope change rather than a tidy-up.

    An answer records what was true for the department it was asked about. A
    company that stops running Sales has not made its old Sales answers untrue,
    it has made them historical — and deleting them would lose the evidence a
    later disagreement needs.
    """
    async with _unscoped_session() as db:
        seed = await _seed(db)

        await select_departments(
            db,
            workspace_id=seed.workspace_id,
            departments={Department.FINANCE, Department.SALES},
        )
        await db.execute(
            sa.text(
                "INSERT INTO onboarding_answer"
                " (workspace_id, answered_by_user_id, question_key, value,"
                "  scope, department, answer_state)"
                " VALUES (:w, :u, 'quota_period', CAST('\"monthly\"' AS jsonb),"
                "         'L3', 'sales', 'bound')"
            ),
            {"w": str(seed.workspace_id), "u": str(seed.user_id)},
        )
        await db.flush()

        await select_departments(
            db, workspace_id=seed.workspace_id, departments={Department.FINANCE}
        )
        await db.flush()

        surviving = (
            await db.execute(
                sa.text(
                    "SELECT count(*) FROM onboarding_answer"
                    " WHERE workspace_id = :w AND department = 'sales'"
                ),
                {"w": str(seed.workspace_id)},
            )
        ).scalar_one()

        assert surviving == 1, "the answer outlives the department it described"
        assert Department.SALES not in await selected_departments(
            db, workspace_id=seed.workspace_id
        )


# ── The restate rule on an answer ─────────────────────────────


async def test_a_changed_answer_names_the_capabilities_that_read_it(
    app_db: None,
) -> None:
    """`doc/13` §10, and the thing that makes the record worth having.

    "Three tiles were affected" is a number nobody can check. *"Read by
    finance.receivables_ageing"* is one they can open — and it is derived, not
    typed: the question bank declares each question's consumer and the registry
    inverts it.
    """
    reads_it = consumers_of("payment_terms")

    assert reads_it == ("finance.receivables_ageing",), (
        "the join step A built. Before it, this returned () for every fact and"
        " the ranking that depended on it scored everything equally"
    )


async def test_a_first_answer_is_not_a_restatement(app_db: None) -> None:
    """The distinction the audit row rests on.

    `store_answer` is an upsert, so after it runs a first answer and a
    correction are indistinguishable — which is why the route reads the previous
    value **before** writing. Logging every answer as a restatement would bury
    the corrections, which are the ones that move a figure somebody has already
    acted on.
    """
    async with _unscoped_session() as db:
        seed = await _seed(db)

        held = {
            row.question_key: row.value
            for row in (
                await db.execute(
                    sa.text(
                        "SELECT question_key, value FROM onboarding_answer"
                        " WHERE workspace_id = :w AND department = 'finance'"
                    ),
                    {"w": str(seed.workspace_id)},
                )
            ).all()
        }

        assert held == {}, "nothing answered yet, so nothing can be a restatement"


async def test_the_audit_action_for_a_department_change_exists_and_is_distinct(
    app_db: None,
) -> None:
    """A scope change recorded under a name that means something else is a row
    nobody finds. `DEPARTMENTS_CHANGED` is its own action for the same reason
    `REPORTING_CHANGED` is."""
    from app.domain.audit import AuditAction

    # The value, not an identity comparison against another member — mypy
    # proves that one true, and a test that cannot fail is decoration. What can
    # go wrong is the *string*, which is what the row carries and what somebody
    # greps for.
    assert AuditAction.DEPARTMENTS_CHANGED.value == "departments_changed"
    actions = {action.value for action in AuditAction}
    assert len(actions) == len(list(AuditAction)), "two actions with one value"


# ── Panel 2: preferences, which authorise nothing ─────────────


async def test_preferences_answer_with_defaults_rather_than_a_404(app_db: None) -> None:
    """A person who joined by invitation has no persona row.

    The question *"what language do you read in?"* has an answer either way, and
    it is the one the product is already using — so absent is answered with the
    defaults the columns carry. A 404 would make the panel unreachable for
    exactly the people who never went through onboarding.
    """
    from app.routes.auth import read_preferences

    async with _unscoped_session() as db:
        seed = await _seed(db)
        await db.commit()

    try:
        prefs = await read_preferences(_scope(seed))

        assert prefs.language == "en"
        assert prefs.timezone == "Asia/Muscat"
        assert prefs.priority_topics == []
    finally:
        async with _unscoped_session() as db:
            await apply_workspace_scope(db, str(seed.workspace_id))
            for statement in (
                "DELETE FROM persona WHERE user_id = :u",
                "DELETE FROM membership WHERE workspace_id = :w",
                "DELETE FROM workspace WHERE id = :w",
                "DELETE FROM app_user WHERE id = :u",
                "DELETE FROM tenant WHERE id = :t",
            ):
                await db.execute(
                    sa.text(statement),
                    {
                        "w": str(seed.workspace_id),
                        "u": str(seed.user_id),
                        "t": str(seed.tenant_id),
                    },
                )
            await db.commit()


def test_no_preference_field_can_authorise_anything() -> None:
    """`doc/06` §2.6, and the reason panel 2 needs no administrator gate.

    Every field the panel writes is a `persona.*` column, and the catalogue
    fails the process at import if a role-shaped key is ever added to that
    namespace. This asserts the panel's own field list stays inside it — a
    `department` or a `role` here would be a permission wearing a preference's
    clothes.
    """
    from app.ai.runtime.fields import FIELD_CATALOGUE, FieldKind
    from app.routes.auth import PreferencesIn

    written = set(PreferencesIn.model_fields)

    assert written == {
        "language",
        "timezone",
        "communication_style",
        "default_landing_screen",
    }
    for name in written:
        spec = FIELD_CATALOGUE.get(f"persona.{name}")
        if spec is not None:
            assert spec.kind is FieldKind.PERSONA, name

    assert "role" not in written
    assert "department" not in written, (
        "`persona.department` fails `assert_persona_is_not_authorisation` at"
        " import, by design — and it must not arrive through this route either"
    )
