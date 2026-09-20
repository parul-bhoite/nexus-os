"""`/evals/permissions` — the eight red-team specs (`doc/12` P10).

Executable specifications, not unit tests. Each one is an attack somebody would
actually try, written so that **breaking the predicate turns it red**. The
acceptance test for this phase is that removing `AND department && :depts` from
the query fails these; a spec that passes against a broken predicate is worse
than no spec, because it certifies the thing it was meant to catch.

They run against a real database, because the predicate *is* SQL. A mock would
be asserting that a string I wrote equals a string I wrote.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import _unscoped_session, get_engine, get_sessionmaker
from app.domain.capabilities import Locked, locked_unless_in_scope
from app.domain.scopes import Department, Role, Scope
from app.domain.session import ScopedSession
from app.retrieval.chunks import count, search
from tests.dburl import async_database_url

ASYNC_DB_URL = async_database_url()
requires_db = pytest.mark.requires_db

# A 1024-dimension vector, matching the configured embedding width. The values
# do not matter — these specs assert *which rows come back*, never their order.
QUERY = [0.1] * 1024


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


async def _fixture(db: AsyncSession) -> tuple[UUID, UUID, UUID, dict[str, UUID]]:
    """A workspace holding one chunk at every scope, plus a second workspace.

    The second exists so cross-workspace retrieval is a *positive* test — a
    suite with one tenant cannot tell isolation from an empty table.
    """
    owner, other_user = uuid4(), uuid4()
    tenant, ws, other_ws = uuid4(), uuid4(), uuid4()

    for user in (owner, other_user):
        await db.execute(
            sa.text("INSERT INTO app_user (id, email) VALUES (:i,:e)"),
            {"i": str(user), "e": f"eval-{user.hex[:8]}@example.com"},
        )
    await db.execute(sa.text("INSERT INTO tenant (id, name) VALUES (:i,'T')"), {"i": str(tenant)})

    ids: dict[str, UUID] = {}
    for workspace in (ws, other_ws):
        await db.execute(
            sa.text("SELECT set_config('nexus.workspace_id', :w, true)"), {"w": str(workspace)}
        )
        await db.execute(
            sa.text(
                "INSERT INTO workspace (id, workspace_id, tenant_id, name, domain,"
                " domain_verified_at) VALUES (:i,:i,:t,'W',:d, now())"
            ),
            {"i": str(workspace), "t": str(tenant), "d": f"eval-{workspace.hex[:8]}.om"},
        )
        document = uuid4()
        await db.execute(
            sa.text(
                "INSERT INTO document (id, workspace_id, uploaded_by_user_id, filename,"
                " content_type, size_bytes, storage_key, content_sha256, status,"
                " consent_given_at, consent_text_version)"
                " VALUES (:i,:w,:u,'f.pdf','application/pdf',1,:k,:h,'indexed',"
                "         now(), '2026-08-18.v1')"
            ),
            {
                "i": str(document),
                "w": str(workspace),
                "u": str(owner),
                "k": f"k/{document}",
                "h": document.hex,
            },
        )

        rows: tuple[tuple[str, str, list[str], bool, UUID], ...] = (
            # `department` is `text[] NOT NULL` — an empty array, never NULL.
            # `&&` against NULL is NULL, which is not TRUE, so the predicate
            # would have quietly excluded every non-departmental row.
            ("l1", "L1", [], False, owner),
            ("l2", "L2", [], False, owner),
            ("l3_finance", "L3", ["finance"], False, owner),
            ("l3_finance_rollup", "L3", ["finance"], True, owner),
            ("l3_sales", "L3", ["sales"], False, owner),
            ("l4_named", "L4", [], False, owner),
            ("l5_owner", "L5", [], False, owner),
            ("l5_other", "L5", [], False, other_user),
        )
        for ordinal, (name, scope_code, depts, aggregate, holder) in enumerate(rows):
            chunk = uuid4()
            if workspace == ws:
                ids[name] = chunk
            await db.execute(
                sa.text(
                    "INSERT INTO chunk (id, workspace_id, document_id, ordinal, content,"
                    " scope, department, sensitivity, is_dept_aggregate, owner_user_id,"
                    " review_state, source_page, source_label, classified_by, confidence)"
                    " VALUES (:i,:w,:d,:o,:c,:s,:dept,'normal',:agg,:owner,"
                    "         'auto_approved',1,'page 1','rule',1.0)"
                ),
                {
                    "i": str(chunk),
                    "w": str(workspace),
                    "d": str(document),
                    "o": ordinal,
                    "c": f"secret about {name}",
                    "s": scope_code,
                    "dept": depts,
                    "agg": aggregate,
                    "owner": str(holder),
                },
            )
    await db.commit()
    return owner, ws, other_ws, ids


async def _cleanup(db: AsyncSession, workspaces: tuple[UUID, ...]) -> None:
    for workspace in workspaces:
        await db.execute(
            sa.text("SELECT set_config('nexus.workspace_id', :w, true)"), {"w": str(workspace)}
        )
        for statement in (
            "DELETE FROM chunk WHERE workspace_id = :w",
            "DELETE FROM document WHERE workspace_id = :w",
            "DELETE FROM workspace WHERE id = :w",
        ):
            await db.execute(sa.text(statement), {"w": str(workspace)})
    await db.commit()


def caller(
    *,
    user: UUID,
    ws: UUID,
    role: Role,
    departments: set[Department] | None = None,
    named: set[UUID] | None = None,
) -> ScopedSession:
    return ScopedSession(
        user_id=user,
        tenant_id=uuid4(),
        workspace_id=ws,
        role=role,
        departments=frozenset(departments or set()),
        named_l4_item_ids=frozenset(named or set()),
    )


async def _as(db: AsyncSession, scope: ScopedSession) -> None:
    await db.execute(
        sa.text("SELECT set_config('nexus.workspace_id', :w, true)"),
        {"w": str(scope.workspace_id)},
    )


@requires_db
async def test_the_eight_permission_specs(app_db: None) -> None:
    """All eight, in one transaction over one fixture.

    One test rather than eight because the fixture is expensive against a remote
    database and every spec reads the same rows — and because the *set* is the
    specification. A file where six pass and two are skipped reads as mostly
    secure, which is not a state this predicate has.
    """
    async with _unscoped_session() as db:
        owner, ws, other_ws, ids = await _fixture(db)
        try:
            contributor = caller(
                user=owner, ws=ws, role=Role.CONTRIBUTOR, departments={Department.FINANCE}
            )
            await _as(db, contributor)
            got = {p.id for p in await search(db, contributor, embedding=QUERY, limit=50)}

            # ── 1. A Contributor reaching L3 Finance ──────────────
            # They hold Finance, so the department rows are theirs — but the
            # roll-up computed across the department is not.
            assert ids["l3_finance"] in got, "their own department's rows are readable"
            assert ids["l3_sales"] not in got, "a department they do not hold must not appear"
            assert ids["l3_finance_rollup"] not in got, (
                "a restricted Contributor must not read the department aggregate — "
                "`is_dept_aggregate` is part of the predicate, not a later filter"
            )

            # ── 2. Existence disclosure via counts ────────────────
            # The count must come *through* the predicate. Counting everything
            # and subtracting is how a count becomes an oracle: "47 you cannot
            # see" states that 47 exist.
            assert await count(db, contributor) == len(got), (
                "the count must be computed through the same predicate as the read"
            )

            # ── 3. …and via titles or metadata ────────────────────
            # Nothing about a hidden row may come back, not even its label.
            for passage in await search(db, contributor, embedding=QUERY, limit=50):
                assert "l3_sales" not in passage.content
                assert "l5_other" not in passage.content

            # ── 3b. The scope a passage reports is one the caller may read ─
            # **ADR 0057 adds `scope` and `department` to `Passage`, and this is
            # where they are held honest.** A6 tags the `generation` row with
            # them, so a field disagreeing with the predicate would not just be
            # a wrong label — it would mis-classify the stored artefact, and the
            # scope lattice would have a side door exactly where migration 0023
            # says it must not.
            #
            # Asserted here rather than in a unit test because the claim is
            # about agreement between two things: what the `WHERE` let through
            # and what the `SELECT` reported. Only a real query has both.
            for passage in await search(db, contributor, embedding=QUERY, limit=50):
                assert passage.scope is not Scope.L4_RESTRICTED, (
                    "an unnamed Contributor must never hold an L4 passage"
                )
                if passage.scope is Scope.L3_DEPARTMENT:
                    assert Department.FINANCE in passage.department, (
                        f"{passage.id} reports departments {passage.department}, none of which "
                        "this caller holds — the predicate and the row disagree"
                    )
                    assert Department.SALES not in passage.department

            # ── 4. A spoofed identity argument ────────────────────
            # There is nowhere to put one. `search` takes a `ScopedSession` and
            # no `user_id`, so a bug two layers up cannot become a cross-tenant
            # read by passing the wrong string.
            import inspect

            parameters = set(inspect.signature(search).parameters)
            assert "user_id" not in parameters and "identity" not in parameters, (
                "an identity argument is exactly the shape this design excludes"
            )

            # ── 5. Cross-workspace retrieval ──────────────────────
            # The same caller, pointed at another company's workspace id.
            trespasser = caller(
                user=owner, ws=other_ws, role=Role.OWNER, departments=set(Department)
            )
            await _as(db, trespasser)
            theirs = await search(db, trespasser, embedding=QUERY, limit=50)
            assert not (set(ids.values()) & {p.id for p in theirs}), (
                "no row from the first workspace may be reachable from the second"
            )

            # ── 6. Cached-result reuse across roles ───────────────
            # An owner and a contributor must not share a cache entry (I5).
            an_owner = caller(user=owner, ws=ws, role=Role.OWNER, departments=set(Department))
            assert an_owner.cache_key() != contributor.cache_key(), (
                "a cache keyed loosely enough to collide serves one role's rows to another"
            )

            # ── 7. A Contributor reading another user's record ────
            await _as(db, contributor)
            assert ids["l5_other"] not in got, "L5 is uploader-only, and that includes peers"
            assert ids["l5_owner"] in got, "their own L5 rows are theirs"

            # ── 8. An L4 item not named for the caller ────────────
            assert ids["l4_named"] not in got, "L4 is reachable only when named"

            named = caller(
                user=owner,
                ws=ws,
                role=Role.CONTRIBUTOR,
                departments={Department.FINANCE},
                named={ids["l4_named"]},
            )
            await _as(db, named)
            with_name = {p.id for p in await search(db, named, embedding=QUERY, limit=50)}
            assert ids["l4_named"] in with_name, "naming the caller is what opens an L4 item"
            # …and only then may a passage report L4. The pair matters: 3b above
            # would also pass if `scope` were hardcoded to anything that is not
            # L4, which is the false green worth excluding.
            named_passages = await search(db, named, embedding=QUERY, limit=50)
            assert any(p.scope is Scope.L4_RESTRICTED for p in named_passages), (
                "a named L4 item must report its real scope, not a safe-looking one"
            )
        finally:
            await _cleanup(db, (ws, other_ws))
            await db.execute(sa.text("DELETE FROM app_user WHERE id = :u"), {"u": str(owner)})
            await db.commit()


def test_locked_is_a_distinct_answer_from_filtered_out() -> None:
    """`ARCHITECTURE-LLD.md` §3.2.

    A calculator whose inputs are not all inside the caller's scope returns
    `Locked` rather than computing over what it can see. A number computed from
    a subset is **wrong while looking right**, and nothing on the screen says so.
    """
    contributor = caller(user=uuid4(), ws=uuid4(), role=Role.CONTRIBUTOR)
    # A Contributor's `max_scope` is L3, the same as an Owner's — the levels say
    # what *kind* of thing a role may see, not *which* things. So the honest
    # test is a capability they lack the department for.
    locked = locked_unless_in_scope(
        contributor,
        capability="Finance health",
        needs=Scope.L3_DEPARTMENT,
        department=Department.FINANCE,
    )
    assert isinstance(locked, Locked)
    assert locked.reason, "a refusal that does not say what would change it is a dead end"

    # An owner holding Finance is not locked out of it.
    owner = caller(user=uuid4(), ws=uuid4(), role=Role.OWNER, departments=set(Department))
    assert (
        locked_unless_in_scope(
            owner,
            capability="Finance health",
            needs=Scope.L3_DEPARTMENT,
            department=Department.FINANCE,
        )
        is None
    )

    # **Nobody reaches L4 by role.** It is reached by being named on the item,
    # which is why `named_l4_item_ids` is on the session at all — so an owner is
    # locked out of an L4 calculation exactly as a contributor is, and that is
    # the design rather than an oversight.
    assert isinstance(
        locked_unless_in_scope(owner, capability="Company health score", needs=Scope.L4_RESTRICTED),
        Locked,
    )
