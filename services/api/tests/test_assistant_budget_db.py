"""Nothing is spent that was not allowed. `doc/20` A7, shape from ADR 0058.

Every refusal here is asserted on **`ScriptedProvider.calls` being empty**,
because that is the claim. A budget check that runs and then calls the model
anyway is not a budget; and the only way to tell the difference from the
outside is that the bill arrives.

Against real Postgres: the daily budget is computed from `generation` rows and
the rate limit is an upsert on a bucket table, so both are database behaviour.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.assistant import ask as ask_module
from app.assistant.budget import (
    ASK_LIMIT,
    MAX_GROUNDING_CHARS,
    MAX_QUESTION_CHARS,
    QuestionTooLargeError,
    check_grounding,
    check_question,
)
from app.assistant.contracts import AssistantRefusal
from app.config import get_settings
from app.connectors.rate_limit import RateLimitedError
from app.db import _unscoped_session, get_engine, get_sessionmaker
from app.domain.scopes import Department, Scope
from app.grounding.pipeline import UnavailableReason
from app.retrieval.chunks import Passage
from tests.dburl import async_database_url
from tests.test_assistant_ask_db import (
    ANSWER,
    DIM,
    QUESTION,
    Seed,
    _provider,
    _scope,
    _seed,
    _StubEmbedder,
)

pytestmark = pytest.mark.requires_db

ASYNC_DB_URL = async_database_url()


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


async def _spend(db: AsyncSession, seed: Seed, tokens: int, *, user: UUID | None) -> None:
    """Burn today's allowance with a real `generation` row.

    Written through SQL rather than through `ask` because the point is to arrive
    at a *state*, and spending it through the assistant would take as many
    questions as the budget allows.
    """
    await db.execute(
        sa.text(
            "INSERT INTO generation (id, workspace_id, module, prompt_version,"
            " input_snapshot, calculation_trace, scope_key, outcome, prose,"
            " input_tokens, output_tokens, requested_by_user_id)"
            " VALUES (:i,:w,'narrate-metric','1','{}'::json,'{}'::json,'L2',"
            "         'answered','x',:t,0,:u)"
        ),
        {
            "i": str(uuid4()),
            "w": str(seed.workspace_id),
            "t": tokens,
            "u": str(user) if user else None,
        },
    )


# ── The daily budgets ─────────────────────────────────────────


async def test_a_workspace_at_its_tenant_budget_makes_no_provider_call(app_db: None) -> None:
    async with _unscoped_session() as db:
        seed = await _seed(db)
        settings = get_settings()
        await _spend(db, seed, settings.tenant_daily_token_budget, user=None)
        provider = _provider()

        result = await ask_module.ask(
            db,
            _scope(seed, Department.FINANCE),
            QUESTION,
            provider=provider,
            settings=settings,
        )

        assert isinstance(result, AssistantRefusal)
        assert result.reason is UnavailableReason.BUDGET_EXHAUSTED
        assert provider.calls == [], "the budget was checked and then spent anyway"


async def test_a_user_at_their_own_budget_is_refused_in_a_workspace_with_room(
    app_db: None,
) -> None:
    """The two budgets are different claims. A workspace with plenty left must
    still refuse the person who has used their share, or the per-user limit is
    decoration."""
    async with _unscoped_session() as db:
        seed = await _seed(db)
        settings = get_settings()
        await _spend(db, seed, settings.user_daily_token_budget, user=seed.user_id)
        provider = _provider()

        result = await ask_module.ask(
            db,
            _scope(seed, Department.FINANCE),
            QUESTION,
            provider=provider,
            settings=settings,
        )

        assert isinstance(result, AssistantRefusal)
        assert result.reason is UnavailableReason.BUDGET_EXHAUSTED
        assert provider.calls == []


# ── The rate limit ────────────────────────────────────────────


async def test_the_eleventh_question_in_the_window_is_refused_before_the_model(
    app_db: None,
) -> None:
    """`ASK_LIMIT` is ten an hour, and the eleventh raises rather than answering.

    `RateLimitedError` propagates out of `ask` rather than becoming an
    `AssistantRefusal`, because a 429 carries `Retry-After` and that is a
    transport concern the route renders — a refusal bubble saying "too many
    questions" would lose the header a client needs to back off politely.
    """
    async with _unscoped_session() as db:
        seed = await _seed(db)
        scope = _scope(seed, Department.FINANCE)
        provider = _provider()

        for _ in range(ASK_LIMIT.max_count):
            await ask_module.ask(db, scope, QUESTION, provider=provider, settings=get_settings())
        calls_before = len(provider.calls)

        with pytest.raises(RateLimitedError):
            await ask_module.ask(db, scope, QUESTION, provider=provider, settings=get_settings())

        assert len(provider.calls) == calls_before, "the refused question still reached the model"


# ── The per-question ceiling ──────────────────────────────────


def test_a_question_longer_than_a_question_is_refused() -> None:
    check_question("x" * MAX_QUESTION_CHARS)
    with pytest.raises(QuestionTooLargeError):
        check_question("x" * (MAX_QUESTION_CHARS + 1))


def test_a_synthetic_two_hundred_passage_retrieval_is_refused_before_the_call() -> None:
    """**The gap the daily budget cannot close.**

    `budgets_for` reads what has already been spent, so it can only stop a
    question after the expensive one has been paid for. This one is inside the
    daily allowance right until it is charged.
    """
    passages = [
        Passage(
            id=uuid4(),
            content="x" * 2_000,
            document_id=uuid4(),
            source_page=None,
            source_label=None,
            scope=Scope.L2_COMPANY_INTERNAL,
            department=(),
        )
        for _ in range(200)
    ]
    assert sum(len(p.content) for p in passages) > MAX_GROUNDING_CHARS

    with pytest.raises(QuestionTooLargeError):
        check_grounding(passages)


def test_an_ordinary_retrieval_is_not_refused() -> None:
    """The other half, so the ceiling cannot pass by refusing everything —
    which would be a different bug wearing this one's clothes."""
    check_grounding(
        [
            Passage(
                id=uuid4(),
                content="Payment is due within 30 days." * 20,
                document_id=uuid4(),
                source_page=None,
                source_label=None,
                scope=Scope.L2_COMPANY_INTERNAL,
                department=(),
            )
            for _ in range(8)
        ]
    )


# ── What the ledger may hold ──────────────────────────────────


async def test_the_snapshot_never_contains_passage_body_text(app_db: None) -> None:
    """`doc/06` §9: `input_snapshot` is *"a second copy of customer content"*.

    Duplicating the corpus into a table with a different lifecycle means a
    deletion request that removes a document leaves its text behind in every
    generation row that quoted it. Asserted on the serialised snapshot, because
    a nested structure can hide the text from a shallower check.
    """
    async with _unscoped_session() as db:
        seed = await _seed(db)
        await ask_module.ask(
            db,
            _scope(seed, Department.FINANCE),
            QUESTION,
            provider=_provider(ANSWER),
            settings=get_settings(),
        )
        await db.flush()

        snapshot = (
            await db.execute(
                sa.text(
                    "SELECT input_snapshot::text AS s FROM generation"
                    " WHERE workspace_id = :w AND module = :m"
                ),
                {"w": str(seed.workspace_id), "m": ask_module.MODULE},
            )
        ).scalar_one()

        assert "Payment is due within 30 days." not in snapshot
        assert str(seed.finance_chunk) in snapshot, (
            "the ids must be here — `generation_citation` records what was cited, "
            "and reviewing a bad answer needs what was retrieved"
        )


def test_the_dimension_fixture_is_the_real_one() -> None:
    """Guards the import from `test_assistant_ask_db`: if that module's stub
    ever stops matching the column, these tests would seed vectors Postgres
    rejects and the failure would look like a budget defect."""
    assert DIM == 1024
