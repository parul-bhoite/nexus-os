"""The company brain is assembled, never invented.

Phase 13's table, built from the founder's own answers. The distinction these
tests protect is the whole product: **assembling what somebody told you is not
generating**, so a workspace with no language model gets a real brain rather
than an apology — and every line of it can name the question it came from.
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
from app.domain.company_brain import Brain, _plain
from tests.dburl import async_database_url

ASYNC_DB_URL = async_database_url()

if TYPE_CHECKING:
    from app.domain.session import ScopedSession

requires_db = pytest.mark.requires_db


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


async def _workspace(db: AsyncSession) -> tuple[UUID, UUID]:
    """A workspace and its owner, committed."""
    user, tenant, ws = uuid4(), uuid4(), uuid4()
    await db.execute(
        sa.text("INSERT INTO app_user (id, email) VALUES (:i,:e)"),
        {"i": str(user), "e": f"spine-{user.hex[:8]}@example.com"},
    )
    await db.execute(sa.text("INSERT INTO tenant (id, name) VALUES (:i,'T')"), {"i": str(tenant)})
    await db.execute(sa.text("SELECT set_config('nexus.workspace_id', :w, true)"), {"w": str(ws)})
    await db.execute(
        sa.text(
            "INSERT INTO workspace (id, workspace_id, tenant_id, name, domain,"
            " domain_verified_at) VALUES (:i,:i,:t,'W',:d, now())"
        ),
        {"i": str(ws), "t": str(tenant), "d": f"spine-{ws.hex[:8]}.om"},
    )
    await db.execute(
        sa.text(
            "INSERT INTO membership (workspace_id, user_id, role, departments)"
            " VALUES (:w,:u,'owner', ARRAY['executive']::text[])"
        ),
        {"w": str(ws), "u": str(user)},
    )
    await db.commit()
    return user, ws


def _owner_scope(user: UUID, ws: UUID) -> ScopedSession:
    """The founder, in their own workspace, holding every department.

    Owner rather than a manager because these three tests are about the
    *company's* shape — which departments it runs, and what a blank answer
    means — and an owner is the caller for whom the permission lattice never
    refuses. If a check still fires for an owner, it is not a permission check.
    """
    from app.domain.scopes import Department, Role
    from app.domain.session import ScopedSession

    return ScopedSession(
        user_id=user,
        tenant_id=uuid4(),
        workspace_id=ws,
        role=Role.OWNER,
        departments=frozenset(Department),
    )


async def _cleanup(db: AsyncSession, user: UUID, ws: UUID) -> None:
    await db.execute(sa.text("SELECT set_config('nexus.workspace_id', :w, true)"), {"w": str(ws)})
    for statement in (
        "DELETE FROM onboarding_progress WHERE workspace_id = :w",
        "DELETE FROM workspace_department WHERE workspace_id = :w",
        "DELETE FROM onboarding_answer WHERE workspace_id = :w",
        "DELETE FROM audit_log WHERE workspace_id = :w",
        "DELETE FROM membership WHERE workspace_id = :w",
        "DELETE FROM workspace WHERE id = :w",
    ):
        await db.execute(sa.text(statement), {"w": str(ws)})
    await db.execute(sa.text("DELETE FROM app_user WHERE id = :u"), {"u": str(user)})
    await db.commit()


def test_a_jsonb_string_is_unquoted_before_it_reaches_a_human() -> None:
    """`onboarding_answer.value` is jsonb, so a stored string arrives quoted.

    Rendering `"\\"Dates and dried fruit\\""` into the brain puts the JSON
    encoding in front of the founder, which reads as a bug and is one.
    """
    assert _plain(json.dumps("Dates and dried fruit")) == "Dates and dried fruit"
    assert _plain(json.dumps(["Grow exports", "Hire a manager"])) == "Grow exports, Hire a manager"
    assert _plain("plain text") == "plain text"


def test_a_brain_with_nothing_answered_says_why() -> None:
    """The schema refuses an unavailable brain with no reason, because "we could
    not build one" with no reason is indistinguishable from a bug — and the
    founder is the person who has to decide whether to care."""
    empty = Brain(generated_by="unavailable", unavailable_reason="Nothing has been answered yet.")
    assert empty.unavailable_reason


@requires_db
async def test_the_brain_is_built_from_answers_and_names_its_sources(app_db: None) -> None:
    """The property the table exists for: every claim points at a question.

    `ck_company_brain_grounded_has_provenance` makes it structural — a brain
    marked as grounded cannot be stored with an empty provenance list, so
    "never invent" is enforced by the database rather than by a habit.
    """

    import sqlalchemy as sa

    from app.db import _unscoped_session
    from app.domain import company_brain

    async with _unscoped_session() as db:
        user, ws = await _workspace(db)
        try:
            await db.execute(
                sa.text("SELECT set_config('nexus.workspace_id', :w, true)"), {"w": str(ws)}
            )
            for key, value, assumed, state in (
                ("what_you_sell", "Dates and dried fruit", False, "bound"),
                ("ideal_customer", "Hotels in Muscat", False, "bound"),
                ("fiscal_year_start", "January", True, "bound"),
                ("payment_terms", "Net 30", False, "bound"),
                # A Contributor's proposal. Must not become a company fact.
                ("approver", "Whoever is around", False, "proposed"),
            ):
                await db.execute(
                    sa.text(
                        "INSERT INTO onboarding_answer (workspace_id, answered_by_user_id,"
                        " question_key, value, scope, department, is_assumption, answer_state)"
                        " VALUES (:w, :u, :k, CAST(:v AS jsonb), 'L2',"
                        "         :d, :a, :s)"
                    ),
                    {
                        "w": str(ws),
                        "u": str(user),
                        "k": key,
                        "v": json.dumps(value),
                        "d": "finance" if key in {"payment_terms", "approver"} else None,
                        "a": assumed,
                        "s": state,
                    },
                )
            await db.commit()

            # The GUC is transaction-local (`set_config(..., true)`), so the
            # commit above dropped it — and RLS then correctly returns nothing.
            # `scoped_connection` sets it per transaction for real callers; this
            # test drives the domain function directly and has to do the same.
            await db.execute(
                sa.text("SELECT set_config('nexus.workspace_id', :w, true)"), {"w": str(ws)}
            )

            built = await company_brain.build(db, workspace_id=ws)

            assert built.generated_by == "answers", "no model is needed to have a brain"
            assert built.products_services == "Dates and dried fruit"
            assert built.target_customers == "Hotels in Muscat"
            assert built.provenance, "a grounded brain must name its sources"
            assert "what_you_sell" in built.provenance

            # The assumption is recorded as one, and stays out of the prose.
            assert any("assumed" in a for a in built.assumptions)
            assert "January" not in (built.profile or "")

            # The proposal is excluded. The review gate exists for exactly this.
            assert "Whoever is around" not in (built.profile or "")
            assert "approver" not in built.provenance

            version = await company_brain.store(db, workspace_id=ws, brain=built)
            await db.commit()
            assert version == 1
            await db.execute(
                sa.text("SELECT set_config('nexus.workspace_id', :w, true)"), {"w": str(ws)}
            )

            # A rebuild supersedes rather than duplicates: the partial unique
            # index permits exactly one live brain per workspace.
            again = await company_brain.store(db, workspace_id=ws, brain=built)
            await db.commit()
            assert again == 2
            await db.execute(
                sa.text("SELECT set_config('nexus.workspace_id', :w, true)"), {"w": str(ws)}
            )

            live = (
                await db.execute(
                    sa.text(
                        "SELECT count(*) FROM company_brain"
                        " WHERE workspace_id = :w AND superseded_at IS NULL"
                    ),
                    {"w": str(ws)},
                )
            ).scalar_one()
            assert live == 1, "two current brains must be impossible, not merely unlikely"

            held = await company_brain.current(db, workspace_id=ws)
            assert held is not None
            assert held.products_services == "Dates and dried fruit"
        finally:
            await db.execute(
                sa.text("SELECT set_config('nexus.workspace_id', :w, true)"), {"w": str(ws)}
            )
            await db.execute(
                sa.text("DELETE FROM company_brain WHERE workspace_id = :w"), {"w": str(ws)}
            )
            await _cleanup(db, user, ws)


@requires_db
async def test_a_lost_first_build_race_returns_the_winners_brain_not_a_500(
    app_db: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The losing side of a concurrent first build reads the winner's brain.

    `GET /brain` builds on first access. Two clients hitting an unbuilt brain at
    once — the dashboard panel and this page, or a dev double-mount — both see no
    live row and both insert version 1; the partial unique index on the
    un-superseded row rejects the second. The loser must return the brain that
    won, not surface the index doing its job as "that did not load".

    Simulated deterministically rather than with real concurrency (two cold
    connections to a managed database race on DNS, not on the row): a brain is
    seeded, then `read_brain` is forced down the build path with a `current` that
    reports None once, and a `store` that raises `IntegrityError` exactly as the
    database would for the losing insert. The fix must roll back, re-read, and
    return the seeded brain.
    """
    from sqlalchemy.exc import IntegrityError

    from app.db import _unscoped_session
    from app.domain import company_brain
    from app.routes import spine

    async with _unscoped_session() as db:
        user, ws = await _workspace(db)

    scope = _owner_scope(user, ws)
    try:
        # The winner's brain already exists and is current.
        async with _unscoped_session() as db:
            await db.execute(
                sa.text("SELECT set_config('nexus.workspace_id', :w, true)"), {"w": str(ws)}
            )
            built = await company_brain.build(db, workspace_id=ws)
            await company_brain.store(db, workspace_id=ws, brain=built)
            await db.commit()

        real_current = company_brain.current
        calls = {"n": 0}

        async def current_blind_once(db: object, *, workspace_id: UUID) -> object:
            # First call (read_brain's opening check) reports no brain, forcing the
            # build path — this is the losing racer's stale view. Every later call,
            # including the fallback re-read, tells the truth.
            calls["n"] += 1
            if calls["n"] == 1:
                return None
            return await real_current(db, workspace_id=workspace_id)  # type: ignore[arg-type]

        async def store_conflict(db: object, *, workspace_id: UUID, brain: object) -> int:
            raise IntegrityError("INSERT", {}, Exception("duplicate un-superseded brain"))

        # Patch the module directly, not via `spine.brain` (an implicit re-export):
        # `spine` holds `company_brain` under that alias, so patching the module
        # object here is what `read_brain`'s `brain.current`/`brain.store` resolve.
        monkeypatch.setattr(company_brain, "current", current_blind_once)
        monkeypatch.setattr(company_brain, "store", store_conflict)

        out = await spine.read_brain(scope)

        # No 500: the losing request returned the brain the winner wrote.
        assert out.version == 1
        assert calls["n"] >= 2, "the fallback must re-read current after the conflict"
    finally:
        async with _unscoped_session() as db:
            await db.execute(
                sa.text("SELECT set_config('nexus.workspace_id', :w, true)"), {"w": str(ws)}
            )
            await db.execute(
                sa.text("DELETE FROM company_brain WHERE workspace_id = :w"), {"w": str(ws)}
            )
            await _cleanup(db, user, ws)
