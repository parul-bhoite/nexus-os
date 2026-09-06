"""A company exists before its domain is proved — and can do less until it is.

**This reverses a rule.** Doc 07 M3's acceptance was *"no workspace exists
without a verified domain"*, and `create_workspace_for_claim` enforced it by
being the only path that could insert one. D19 splits that in two:

- **Creating a company needs no verified claim.** Verification is a DNS record
  or a file upload, and demanding it before a user can see anything at all put
  a systems administration task between a signed-up user and the product. Every
  `CurrentScope` endpoint answered 403 until it was done, which is why
  `AccountPanel` had a paragraph explaining the dead end.
- **Verification still gates what it always protected.** Inviting colleagues and
  connecting tools are the two acts that reach beyond the person doing them —
  one adds people to a company, the other pulls in its data. Those still require
  a proved domain.

So the property under test is no longer "no unverified workspace" but "an
unverified workspace **cannot do the things verification exists to protect**".
That is a weaker claim about existence and the same claim about authority, and
the tests below are written to fail if the second half slips.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy import Connection, Engine, create_engine

from app.config import get_settings
from app.db import get_engine, get_sessionmaker
from tests.dburl import async_database_url, database_url

DB_URL = database_url()
ASYNC_DB_URL = async_database_url()
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
    try:
        yield connection
    finally:
        connection.close()


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


async def _make_user(db: object) -> UUID:
    user = uuid4()
    await db.execute(  # type: ignore[attr-defined]
        sa.text("INSERT INTO app_user (id, email) VALUES (:i,:e)"),
        {"i": str(user), "e": f"co-{user.hex[:8]}@example.com"},
    )
    return user


async def _cleanup(db: object, *, user: UUID, workspace: UUID | None = None) -> None:
    if workspace is not None:
        await db.execute(  # type: ignore[attr-defined]
            sa.text("SELECT set_config('nexus.workspace_id', :w, true)"), {"w": str(workspace)}
        )
        for statement in (
            "DELETE FROM research_run WHERE workspace_id = :w",
            "DELETE FROM audit_log WHERE workspace_id = :w",
            "DELETE FROM membership WHERE workspace_id = :w",
        ):
            await db.execute(sa.text(statement), {"w": str(workspace)})  # type: ignore[attr-defined]
        await db.execute(  # type: ignore[attr-defined]
            sa.text("DELETE FROM workspace WHERE id = :w"), {"w": str(workspace)}
        )
    await db.execute(  # type: ignore[attr-defined]
        sa.text("DELETE FROM app_user WHERE id = :u"), {"u": str(user)}
    )
    await db.commit()  # type: ignore[attr-defined]


# ── Creation no longer waits for verification ─────────────────


@requires_db
async def test_workspace_is_created_without_a_verified_claim(app_db: None) -> None:
    """D19. The whole point of the split, and the reversal of doc 07 M3."""
    from app.auth.companies import CompanyDetails, create_company
    from app.db import _unscoped_session

    async with _unscoped_session() as db:
        user = await _make_user(db)
        await db.commit()
        created = None
        try:
            created = await create_company(
                db,
                user_id=user,
                details=CompanyDetails(
                    name="Acme Trading",
                    website_url=f"https://acme-{user.hex[:8]}.om",
                ),
            )
            await db.commit()

            assert created.workspace_id is not None
            # The GUC is transaction-local, so the commit above cleared it and
            # `workspace` carries FORCE RLS — a read without it matches nothing.
            # Same lesson `test_audit_log.py` learned: the empty result is the
            # policy working, not the write failing.
            await db.execute(
                sa.text("SELECT set_config('nexus.workspace_id', :w, true)"),
                {"w": str(created.workspace_id)},
            )
            row = (
                await db.execute(
                    sa.text(
                        "SELECT domain_verified_at, trial_ends_at FROM workspace WHERE id = :w"
                    ),
                    {"w": str(created.workspace_id)},
                )
            ).one()
            assert row.domain_verified_at is None, "creation must not imply verification"
            assert row.trial_ends_at is not None, "a trial must start (45 days, doc/11 §5)"
        finally:
            await _cleanup(db, user=user, workspace=created.workspace_id if created else None)


@requires_db
async def test_the_owner_membership_is_created_in_the_same_transaction(app_db: None) -> None:
    """A workspace with no members is unreachable by anyone, including the
    person who just made it — and there is no path in the product to add the
    first one. It has to be atomic with the workspace, not a second step."""
    from app.auth.companies import CompanyDetails, create_company
    from app.db import _unscoped_session

    async with _unscoped_session() as db:
        user = await _make_user(db)
        await db.commit()
        created = None
        try:
            created = await create_company(
                db,
                user_id=user,
                details=CompanyDetails(
                    name="Solo Co",
                    website_url=f"https://solo-{user.hex[:8]}.om",
                ),
            )
            await db.commit()

            await db.execute(
                sa.text("SELECT set_config('nexus.user_id', :u, true)"), {"u": str(user)}
            )
            role = (
                await db.execute(
                    sa.text("SELECT role FROM membership WHERE user_id = :u"), {"u": str(user)}
                )
            ).scalar()
            assert role == "owner"
        finally:
            await _cleanup(db, user=user, workspace=created.workspace_id if created else None)


@requires_db
async def test_registration_enqueues_a_research_run(app_db: None) -> None:
    """Enqueue only — P11 builds the engine. Recorded rather than fired so the
    request survives a restart, and so the queue is visible before there is
    anything to drain it."""
    from app.auth.companies import CompanyDetails, create_company
    from app.db import _unscoped_session

    async with _unscoped_session() as db:
        user = await _make_user(db)
        await db.commit()
        created = None
        try:
            created = await create_company(
                db,
                user_id=user,
                details=CompanyDetails(
                    name="Crawl Co",
                    website_url=f"https://crawl-{user.hex[:8]}.om",
                ),
            )
            await db.commit()

            await db.execute(
                sa.text("SELECT set_config('nexus.workspace_id', :w, true)"),
                {"w": str(created.workspace_id)},
            )
            state = (
                await db.execute(
                    sa.text("SELECT state FROM research_run WHERE workspace_id = :w"),
                    {"w": str(created.workspace_id)},
                )
            ).scalar()
            assert state == "queued"
        finally:
            await _cleanup(db, user=user, workspace=created.workspace_id if created else None)


# ── What an unverified workspace still cannot do ──────────────


@requires_db
async def test_unverified_workspace_cannot_invite(app_db: None) -> None:
    """The half of the old rule that survives. Inviting adds a person to a
    company, and the only evidence that this *is* your company is the domain."""
    from app.auth.companies import CompanyDetails, create_company
    from app.auth.workspaces import UnverifiedWorkspaceError, require_verified_domain
    from app.db import _unscoped_session

    async with _unscoped_session() as db:
        user = await _make_user(db)
        await db.commit()
        created = None
        try:
            created = await create_company(
                db,
                user_id=user,
                details=CompanyDetails(
                    name="Unverified Co",
                    website_url=f"https://unv-{user.hex[:8]}.om",
                ),
            )
            await db.commit()

            await db.execute(
                sa.text("SELECT set_config('nexus.workspace_id', :w, true)"),
                {"w": str(created.workspace_id)},
            )
            with pytest.raises(UnverifiedWorkspaceError):
                await require_verified_domain(db, workspace_id=created.workspace_id)
        finally:
            await _cleanup(db, user=user, workspace=created.workspace_id if created else None)


@requires_db
async def test_a_verified_workspace_may_invite(app_db: None) -> None:
    """The other side of the gate, so the test above cannot pass by the check
    simply refusing everything."""
    from app.auth.companies import CompanyDetails, create_company
    from app.auth.workspaces import require_verified_domain
    from app.db import _unscoped_session

    async with _unscoped_session() as db:
        user = await _make_user(db)
        await db.commit()
        created = None
        try:
            created = await create_company(
                db,
                user_id=user,
                details=CompanyDetails(
                    name="Verified Co",
                    website_url=f"https://ver-{user.hex[:8]}.om",
                ),
            )
            await db.execute(
                sa.text("SELECT set_config('nexus.workspace_id', :w, true)"),
                {"w": str(created.workspace_id)},
            )
            await db.execute(
                sa.text("UPDATE workspace SET domain_verified_at = now() WHERE id = :w"),
                {"w": str(created.workspace_id)},
            )
            await db.commit()

            # Re-scoped after the commit, for the reason above. Without this the
            # gate reads no row, concludes "unverified", and refuses — which is
            # the safe direction to fail and would have made this test pass for
            # entirely the wrong reason.
            await db.execute(
                sa.text("SELECT set_config('nexus.workspace_id', :w, true)"),
                {"w": str(created.workspace_id)},
            )
            await require_verified_domain(db, workspace_id=created.workspace_id)
        finally:
            await _cleanup(db, user=user, workspace=created.workspace_id if created else None)


# ── The duplicate-domain branch (doc/11 Q8) ───────────────────


@requires_db
async def test_duplicate_verified_domain_offers_a_join_request_not_a_workspace(
    app_db: None,
) -> None:
    """Two people from one company signing up separately is the ordinary case,
    not an attack — and answering it with a second workspace splits their data
    in half silently, which is the worst available outcome.

    Only a **verified** workspace claims a domain this way. An unverified one has
    proved nothing, so it cannot block a stranger from registering.
    """
    from app.auth.companies import (
        CompanyDetails,
        DomainAlreadyRegisteredError,
        create_company,
    )
    from app.db import _unscoped_session

    domain_owner = None
    second = None
    first_ws = None

    async with _unscoped_session() as db:
        try:
            domain_owner = await _make_user(db)
            second = await _make_user(db)
            await db.commit()

            shared = f"https://shared-{domain_owner.hex[:8]}.om"
            created = await create_company(
                db,
                user_id=domain_owner,
                details=CompanyDetails(
                    name="First In",
                    website_url=shared,
                ),
            )
            first_ws = created.workspace_id
            await db.execute(
                sa.text("SELECT set_config('nexus.workspace_id', :w, true)"),
                {"w": str(first_ws)},
            )
            await db.execute(
                sa.text("UPDATE workspace SET domain_verified_at = now() WHERE id = :w"),
                {"w": str(first_ws)},
            )
            await db.commit()

            with pytest.raises(DomainAlreadyRegisteredError) as raised:
                await create_company(
                    db,
                    user_id=second,
                    details=CompanyDetails(
                        name="Second In",
                        website_url=shared,
                    ),
                )
            # The error names the workspace to join, or the caller has nothing
            # to offer the user but a refusal.
            assert raised.value.workspace_id == first_ws
        finally:
            await db.rollback()
            for user in (domain_owner, second):
                if user is not None:
                    await _cleanup(db, user=user, workspace=None)
            if first_ws is not None:
                await _cleanup(db, user=uuid4(), workspace=first_ws)


@requires_db
async def test_an_unverified_duplicate_does_not_block_registration(app_db: None) -> None:
    """The boundary of the rule above. A workspace that has not proved the
    domain has no standing to stop anyone else registering it — otherwise
    typing a domain would be enough to reserve it against its real owner."""
    from app.auth.companies import CompanyDetails, create_company
    from app.db import _unscoped_session

    async with _unscoped_session() as db:
        first = await _make_user(db)
        second = await _make_user(db)
        await db.commit()
        a = b = None
        try:
            shared = f"https://open-{first.hex[:8]}.om"
            a = await create_company(
                db,
                user_id=first,
                details=CompanyDetails(name="A", website_url=shared),
            )
            await db.commit()
            b = await create_company(
                db,
                user_id=second,
                details=CompanyDetails(name="B", website_url=shared),
            )
            await db.commit()

            assert a.workspace_id != b.workspace_id
        finally:
            for user, created in ((first, a), (second, b)):
                await _cleanup(db, user=user, workspace=created.workspace_id if created else None)
