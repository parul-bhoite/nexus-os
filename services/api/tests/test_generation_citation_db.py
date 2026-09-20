"""`generation_citation` behaves like a ledger, not like a cache. `doc/20` A4.

Against Neon, because every claim here is about the *table* — row-level security,
two foreign keys with deliberately opposite delete rules, and a uniqueness
constraint. None of it can be proved against a monkeypatched write, and the
phase rule says so: *"driven through the application rather than around it."*

**The isolation assertions read `pg_class` rather than trusting the migration.**
`nexus_app` is `NOBYPASSRLS`, so a policy that is missing or wrong returns
**zero rows rather than an error** — a query against an unprotected table and a
query against a correctly protected one both look like "no rows" from the
caller's side. Reading `relrowsecurity` and `relforcerowsecurity` is the only
way to tell "isolated" from "empty", and `CLAUDE.md` records why that
distinction has cost this project time before.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError, ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import _unscoped_session, get_engine, get_sessionmaker
from app.retrieval.scoped import apply_workspace_scope
from tests.dburl import async_database_url

pytestmark = pytest.mark.requires_db

ASYNC_DB_URL = async_database_url()


@dataclass(frozen=True, slots=True)
class Seed:
    tenant_id: UUID
    user_id: UUID
    workspace_id: UUID
    document_id: UUID
    chunk_id: UUID
    generation_id: UUID


@pytest.fixture
async def app_db(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[None]:
    """The same fixture `test_grounding_ledger_db.py` uses, for the same reason:
    `conftest.py` pins `NEXUS_DATABASE_URL` to empty, so the engine has to be
    pointed deliberately rather than by ambient configuration."""
    assert ASYNC_DB_URL is not None, (
        "`requires_db` guarantees a database; a missing URL is a broken harness"
    )
    monkeypatch.setenv("NEXUS_DATABASE_URL", ASYNC_DB_URL)
    monkeypatch.setenv("NEXUS_STORAGE_SIGNING_SECRET", "test-secret")
    for cache in (get_settings, get_engine, get_sessionmaker):
        cache.cache_clear()
    yield
    await get_engine().dispose()
    for cache in (get_settings, get_engine, get_sessionmaker):
        cache.cache_clear()


async def _seed(db: AsyncSession, *, label: str = "A") -> Seed:
    """A workspace with one document, one chunk and one generation.

    Not committed. Each test runs in one transaction and lets it roll back —
    cheaper than a teardown against `us-east-2`, and it cannot leave a
    half-deleted workspace behind when an assertion fails partway through.
    """
    seed = Seed(uuid4(), uuid4(), uuid4(), uuid4(), uuid4(), uuid4())

    await apply_workspace_scope(db, str(seed.workspace_id))
    await db.execute(
        sa.text("INSERT INTO tenant (id, name) VALUES (:t, :n)"),
        {"t": str(seed.tenant_id), "n": f"Citation Test {label}"},
    )
    await db.execute(
        sa.text("INSERT INTO app_user (id, email) VALUES (:u, :e)"),
        {"u": str(seed.user_id), "e": f"cite-{seed.user_id}@example.invalid"},
    )
    await db.execute(
        sa.text(
            "INSERT INTO workspace (id, workspace_id, tenant_id, name, reporting_currency)"
            " VALUES (:id, :id, :t, :n, 'OMR')"
        ),
        {"id": str(seed.workspace_id), "t": str(seed.tenant_id), "n": f"Citation Test {label}"},
    )
    await db.execute(
        sa.text(
            "INSERT INTO document"
            " (id, workspace_id, filename, content_type, size_bytes, storage_key, content_sha256)"
            " VALUES (:d, :ws, 'terms.pdf', 'application/pdf', 1024, :key, :sha)"
        ),
        {
            "d": str(seed.document_id),
            "ws": str(seed.workspace_id),
            "key": f"docs/{seed.document_id}",
            "sha": f"{seed.document_id.hex}{seed.document_id.hex}",
        },
    )
    await db.execute(
        sa.text(
            "INSERT INTO chunk"
            " (id, workspace_id, document_id, ordinal, content, scope, department,"
            "  classified_by, confidence, review_state)"
            " VALUES (:c, :ws, :d, 0, 'Payment is due within 30 days.', 'L3',"
            "         ARRAY['finance'], 'rules', 1.0, 'approved')"
        ),
        {"c": str(seed.chunk_id), "ws": str(seed.workspace_id), "d": str(seed.document_id)},
    )
    await db.execute(
        sa.text(
            "INSERT INTO generation"
            " (id, workspace_id, module, prompt_version, input_snapshot, calculation_trace,"
            "  scope_key, outcome, prose)"
            # `ck_generation_prose_matches_outcome` (0029): an answered row must
            # carry a sentence. Omitting it here failed six tests at the seed —
            # the constraint doing exactly its job on a test that was wrong.
            " VALUES (:g, :ws, 'assistant.ask', '1', '{}'::json, '{}'::json,"
            "         'L3:finance', 'answered', 'Payment is due within 30 days.')"
        ),
        {"g": str(seed.generation_id), "ws": str(seed.workspace_id)},
    )
    return seed


async def _cite(db: AsyncSession, seed: Seed, *, chunk_id: UUID | None = None) -> None:
    await db.execute(
        sa.text(
            "INSERT INTO generation_citation"
            " (workspace_id, generation_id, chunk_id, document_id, source_page,"
            "  source_label, ordinal)"
            " VALUES (:ws, :g, :c, :d, 1, 'terms.pdf', 0)"
        ),
        {
            "ws": str(seed.workspace_id),
            "g": str(seed.generation_id),
            "c": str(chunk_id or seed.chunk_id),
            "d": str(seed.document_id),
        },
    )


# ── Isolation ─────────────────────────────────────────────────


async def test_the_table_is_protected_rather_than_merely_empty(app_db: None) -> None:
    """Read from `pg_class`, not inferred from the migration having run.

    Both flags matter and they are different claims: `relrowsecurity` turns
    policies on, `relforcerowsecurity` applies them to the table's **owner**
    too. `nexus_app` owns every table here, so without the second flag every
    policy in this database would be inert while the whole isolation suite kept
    passing.
    """
    async with _unscoped_session() as db:
        row = (
            await db.execute(
                sa.text(
                    "SELECT relrowsecurity, relforcerowsecurity FROM pg_class"
                    " WHERE relname = 'generation_citation'"
                )
            )
        ).one()

        assert row.relrowsecurity is True
        assert row.relforcerowsecurity is True, "policies would not apply to the owning role"


async def test_a_citation_is_invisible_from_another_workspace(app_db: None) -> None:
    """The row exists and the query returns nothing, which is the whole point of
    keying the policy on the GUC rather than on a join to `generation`."""
    async with _unscoped_session() as db:
        seed = await _seed(db)
        await _cite(db, seed)
        await db.flush()

        mine = (
            await db.execute(
                sa.text("SELECT count(*) FROM generation_citation WHERE generation_id = :g"),
                {"g": str(seed.generation_id)},
            )
        ).scalar()
        assert mine == 1

        # Same transaction, same row, a different workspace on the GUC.
        await apply_workspace_scope(db, str(uuid4()))
        theirs = (
            await db.execute(
                sa.text("SELECT count(*) FROM generation_citation WHERE generation_id = :g"),
                {"g": str(seed.generation_id)},
            )
        ).scalar()

        assert theirs == 0


async def test_a_citation_cannot_be_written_into_another_workspace(app_db: None) -> None:
    """`WITH CHECK`, which is the half that is easy to omit.

    A `USING`-only policy hides other workspaces' rows on read while happily
    accepting a write into one — a leak that looks like isolation right up until
    somebody queries as the other tenant.
    """
    async with _unscoped_session() as db:
        seed = await _seed(db)
        await db.flush()

        with pytest.raises(ProgrammingError, match=r"row-level security"):
            await db.execute(
                sa.text(
                    "INSERT INTO generation_citation"
                    " (workspace_id, generation_id, chunk_id, document_id, ordinal)"
                    " VALUES (:other, :g, :c, :d, 0)"
                ),
                {
                    "other": str(uuid4()),
                    "g": str(seed.generation_id),
                    "c": str(seed.chunk_id),
                    "d": str(seed.document_id),
                },
            )


# ── The delete rules, which are opposite on purpose ───────────


async def test_deleting_the_answer_deletes_its_citations(app_db: None) -> None:
    """`ON DELETE CASCADE` on `generation_id`. A citation is *about* an answer;
    keeping it after the answer is gone would leave a pointer to nothing."""
    async with _unscoped_session() as db:
        seed = await _seed(db)
        await _cite(db, seed)
        await db.flush()

        await db.execute(
            sa.text("DELETE FROM generation WHERE id = :g"), {"g": str(seed.generation_id)}
        )
        await db.flush()

        left = (
            await db.execute(
                sa.text("SELECT count(*) FROM generation_citation WHERE generation_id = :g"),
                {"g": str(seed.generation_id)},
            )
        ).scalar()
        assert left == 0


async def test_a_cited_chunk_cannot_be_hard_deleted(app_db: None) -> None:
    """`ON DELETE RESTRICT` on `chunk_id`, and **this is the constraint that
    will surprise somebody** (ADR 0056).

    It is deliberate. `CASCADE` would erase the evidence exactly when a chunk is
    deleted — the answer would remain and its basis would be gone, which is the
    opposite of what a ledger is for. `document` already soft-deletes, so the
    ordinary path is unaffected; what fails here is a hard delete, which is
    precisely the operation that should stop and ask.
    """
    async with _unscoped_session() as db:
        seed = await _seed(db)
        await _cite(db, seed)
        await db.flush()

        with pytest.raises(IntegrityError, match="generation_citation"):
            await db.execute(sa.text("DELETE FROM chunk WHERE id = :c"), {"c": str(seed.chunk_id)})
            await db.flush()


async def test_one_answer_cites_one_chunk_once(app_db: None) -> None:
    """The unique constraint. A duplicate is a caller bug, and storing it
    silently would double every "which answers quoted this chunk?" figure — the
    question the table was created to answer."""
    async with _unscoped_session() as db:
        seed = await _seed(db)
        await _cite(db, seed)
        await db.flush()

        with pytest.raises(IntegrityError, match="uq_generation_citation__generation_chunk"):
            await _cite(db, seed)
            await db.flush()


async def test_a_citation_cannot_point_at_a_chunk_that_does_not_exist(app_db: None) -> None:
    """Referential integrity is the thing a JSON blob of ids could never have
    (ADR 0056), and it is load-bearing rather than tidy: ADR 0053 lets a
    citation **license a figure**, so a citation the database will not vouch for
    is a permission to state a number."""
    async with _unscoped_session() as db:
        seed = await _seed(db)
        await db.flush()

        with pytest.raises(IntegrityError, match="chunk"):
            await _cite(db, seed, chunk_id=uuid4())
            await db.flush()
