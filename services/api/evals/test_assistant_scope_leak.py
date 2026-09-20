"""What a refusal tells you about what you cannot see. `doc/20` A9.

**The assertion this file exists for:** the refusal a caller gets when the
content does not exist is **byte-identical** to the refusal they get when it
exists at a scope they lack. `api-design`'s 404-not-403 rule, applied to prose —
and prose is where it is easiest to lose, because a helpful sentence is a
natural thing to write.

*"There is a document about salaries but you cannot see it"* and *"I could not
find anything about that"* are the same HTTP status and the same shape. Only the
words differ, and the words are the disclosure.

Two workspaces, built to be indistinguishable from the caller's side:

- **A** holds one Sales passage. A Finance contributor can read nothing in it.
- **B** holds nothing at all.

Same question, same role, same code. Every field of both answers must match,
including the `generation` row's `unavailable_reason` — because a support
engineer reading the ledger must not be able to tell them apart either, and the
row outlives the response.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.assistant import ask as ask_module
from app.assistant.contracts import AssistantRefusal, Question
from app.config import get_settings
from app.db import _unscoped_session, get_engine, get_sessionmaker
from app.domain.scopes import Department, Role
from app.domain.session import ScopedSession
from app.grounding.pipeline import UnavailableReason
from app.retrieval import chunks as chunks_module
from app.retrieval.scoped import apply_workspace_scope
from tests.dburl import async_database_url
from tests.test_assistant_ask_db import DIM, _provider, _StubEmbedder

pytestmark = pytest.mark.requires_db

ASYNC_DB_URL = async_database_url()
QUESTION = Question(text="What is the sales commission structure?", department=Department.FINANCE)


@dataclass(frozen=True, slots=True)
class Workspace:
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


@pytest.fixture(autouse=True)
def stub_embedder(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ask_module, "get_embedder", _StubEmbedder)


async def _workspace(db: AsyncSession, *, with_sales_passage: bool) -> Workspace:
    ws = Workspace(uuid4(), uuid4(), uuid4())
    await apply_workspace_scope(db, str(ws.workspace_id))

    await db.execute(
        sa.text("INSERT INTO tenant (id, name) VALUES (:t,'Leak')"), {"t": str(ws.tenant_id)}
    )
    await db.execute(
        sa.text("INSERT INTO app_user (id, email) VALUES (:u,:e)"),
        {"u": str(ws.user_id), "e": f"leak-{ws.user_id}@example.invalid"},
    )
    await db.execute(
        sa.text(
            "INSERT INTO workspace (id, workspace_id, tenant_id, name, reporting_currency)"
            " VALUES (:i,:i,:t,'Leak','OMR')"
        ),
        {"i": str(ws.workspace_id), "t": str(ws.tenant_id)},
    )
    if not with_sales_passage:
        return ws

    document = uuid4()
    await db.execute(
        sa.text(
            "INSERT INTO document (id, workspace_id, filename, content_type, size_bytes,"
            " storage_key, content_sha256)"
            " VALUES (:d,:w,'comp.pdf','application/pdf',1,:k,:h)"
        ),
        {
            "d": str(document),
            "w": str(ws.workspace_id),
            "k": f"k/{document}",
            "h": document.hex * 2,
        },
    )
    await db.execute(
        sa.text(
            "INSERT INTO chunk (id, workspace_id, document_id, ordinal, content, scope,"
            " department, classified_by, confidence, review_state, source_page,"
            " source_label, embedding, embedding_model_id, embedding_dim)"
            " VALUES (:i,:w,:d,0,'Sales commission is 4 percent of closed revenue.','L3',"
            "         ARRAY['sales'],'rules',1.0,'approved',1,'comp.pdf',"
            "         CAST(:e AS vector),'stub',:dim)"
        ),
        {
            "i": str(uuid4()),
            "w": str(ws.workspace_id),
            "d": str(document),
            "e": str([0.1] * DIM),
            "dim": DIM,
        },
    )
    return ws


def _finance_contributor(ws: Workspace) -> ScopedSession:
    return ScopedSession(
        user_id=ws.user_id,
        tenant_id=ws.tenant_id,
        workspace_id=ws.workspace_id,
        role=Role.CONTRIBUTOR,
        departments=frozenset({Department.FINANCE}),
    )


async def _reason_on_the_row(db: AsyncSession, ws: Workspace) -> str:
    return str(
        (
            await db.execute(
                sa.text(
                    "SELECT unavailable_reason FROM generation"
                    " WHERE workspace_id = :w AND module = :m"
                ),
                {"w": str(ws.workspace_id), "m": ask_module.MODULE},
            )
        ).scalar_one()
    )


async def test_a_refusal_is_identical_whether_or_not_the_content_exists(app_db: None) -> None:
    """**The single most important assertion in `doc/20`.**

    Compared field by field rather than on the reason alone, because the leak
    would arrive in the *sentence* — the one part of a refusal somebody is
    tempted to make more helpful.
    """
    async with _unscoped_session() as db:
        hidden = await _workspace(db, with_sales_passage=True)
        empty = await _workspace(db, with_sales_passage=False)

        await apply_workspace_scope(db, str(hidden.workspace_id))
        a = await ask_module.ask(
            db,
            _finance_contributor(hidden),
            QUESTION,
            provider=_provider(),
            settings=get_settings(),
        )
        reason_a = await _reason_on_the_row(db, hidden)

        await apply_workspace_scope(db, str(empty.workspace_id))
        b = await ask_module.ask(
            db,
            _finance_contributor(empty),
            QUESTION,
            provider=_provider(),
            settings=get_settings(),
        )
        reason_b = await _reason_on_the_row(db, empty)

        assert isinstance(a, AssistantRefusal)
        assert isinstance(b, AssistantRefusal)
        assert a == b, "the two refusals differ, so a caller can probe for what exists"
        assert a.sentence == b.sentence
        assert a.capability_id is None and b.capability_id is None
        # The ledger must not be able to tell them apart either. It outlives the
        # response, and a support engineer reading it is a second audience.
        assert reason_a == reason_b == UnavailableReason.NO_PASSAGE.value


async def test_the_refusal_never_names_a_department_or_a_count(app_db: None) -> None:
    """The two shapes the sentence could leak in.

    *"…but you cannot see it"* names existence; *"I found 3 but can only quote
    one"* names a count. The passage set the model sees **is** the permitted
    set, so there is no filtered-out category to describe — and `chunks.count`
    is deliberately not called on this path.
    """
    async with _unscoped_session() as db:
        hidden = await _workspace(db, with_sales_passage=True)
        result = await ask_module.ask(
            db,
            _finance_contributor(hidden),
            QUESTION,
            provider=_provider(),
            settings=get_settings(),
        )

        assert isinstance(result, AssistantRefusal)
        lowered = result.sentence.lower()

        # **Every department, not just the one that was hidden.** `doc/20`
        # offers a hand-check — "changing `sentence_for(NO_PASSAGE)` to mention
        # the department turns the identical-refusal test red" — and that is
        # **not true**: the sentence is a constant, so a globally wrong one
        # stays trivially identical to itself. The test above proves the wording
        # does not *vary* with what exists; only this one can prove the wording
        # does not name a scope at all. Planted and confirmed.
        for department in Department:
            assert department.value not in lowered, (
                f"the refusal names {department.value!r} — a caller learns which "
                "shelf they were refused from"
            )
        for leak in ("permission", "access", "not allowed", "cannot see", "hidden", "restricted"):
            assert leak not in lowered, f"the refusal says {leak!r}"
        assert not any(ch.isdigit() for ch in result.sentence), "a count is a disclosure"


async def test_count_is_never_called_on_the_ask_path(
    app_db: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`chunks.count` answers *"how many may I read?"* — and asking it here would
    put a number in reach of the prose. `doc/20` §5 Q6.1 says it is not called
    on this path; this is what makes that true rather than intended."""
    called: list[int] = []
    original = chunks_module.count

    async def spy(*args: object, **kwargs: object) -> int:
        called.append(1)
        return await original(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(chunks_module, "count", spy)
    monkeypatch.setattr("app.assistant.ask.search", chunks_module.search)

    async with _unscoped_session() as db:
        ws = await _workspace(db, with_sales_passage=True)
        await ask_module.ask(
            db, _finance_contributor(ws), QUESTION, provider=_provider(), settings=get_settings()
        )

        assert called == [], "`chunks.count` was called on the ask path"


async def test_a_refusal_records_no_citations_rather_than_leaving_them_ambiguous(
    app_db: None,
) -> None:
    """Zero rows, not absent-and-ambiguous.

    A refusal that wrote no `generation` row at all would be indistinguishable
    from one whose citations were lost, and *"which answers quoted this chunk?"*
    would quietly under-report.
    """
    async with _unscoped_session() as db:
        ws = await _workspace(db, with_sales_passage=True)
        await ask_module.ask(
            db, _finance_contributor(ws), QUESTION, provider=_provider(), settings=get_settings()
        )
        await db.flush()

        generation_id = (
            await db.execute(
                sa.text("SELECT id FROM generation WHERE workspace_id = :w"),
                {"w": str(ws.workspace_id)},
            )
        ).scalar_one()
        citations = (
            await db.execute(
                sa.text("SELECT count(*) FROM generation_citation WHERE generation_id = :g"),
                {"g": str(generation_id)},
            )
        ).scalar_one()

        assert citations == 0
