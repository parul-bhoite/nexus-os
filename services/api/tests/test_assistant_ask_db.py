"""`ask` end to end, against real Postgres. `doc/20` A6's acceptance.

**The H1 experiment, driven through the assistant.** The same data, the same
question, two callers: one holding Finance gets an answer citing the Finance
passage; one holding only Executive gets `NO_PASSAGE`. That pair is the product
claim — permission is enforced *inside the retrieval query*, so the second
caller's refusal is not a filter applied to an answer, it is an answer that was
never possible.

No network: the model is a `ScriptedProvider`, which raises on anything
unscripted rather than improvising, and the embedder is stubbed so the suite
does not load ~2 GB of weights to prove something about SQL.

**What the scripted provider is asserted on is what was *sent*.** That the
fence reached the system prompt, and that no chunk id did — the interesting
bugs in this composition are all about what crossed the boundary, not about what
came back.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from typing import Any
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.contracts import Availability as LlmAvailability
from app.ai.providers import ScriptedProvider
from app.assistant import ask as ask_module
from app.assistant.ask import MODULE, ask, scope_key_for_passages
from app.assistant.contracts import AssistantAnswer, AssistantRefusal, Question
from app.config import get_settings
from app.db import _unscoped_session, get_engine, get_sessionmaker
from app.domain.scopes import Department, Role, Scope
from app.domain.session import ScopedSession
from app.embeddings.contracts import Availability, EmbedderStatus
from app.grounding.pipeline import UnavailableReason
from app.retrieval.chunks import Passage
from app.retrieval.scoped import apply_workspace_scope
from tests.dburl import async_database_url

pytestmark = pytest.mark.requires_db

ASYNC_DB_URL = async_database_url()
DIM = 1024

ANSWER = (
    '{"answered": true, "segments": [{"text": "Payment is due within 30 days.",'
    ' "cited_refs": ["p1"]}]}'
)


@dataclass(frozen=True, slots=True)
class Seed:
    user_id: UUID
    workspace_id: UUID
    tenant_id: UUID
    document_id: UUID
    finance_chunk: UUID


class _StubEmbedder:
    """Deterministic, and never returned by the real registry.

    `CLAUDE.md` is emphatic that a fabricated embedding **ranks** rather than
    failing — so this exists only inside a test that monkeypatches it in by
    name, and `DeterministicEmbedder`'s ban is untouched.
    """

    @property
    def model_id(self) -> str:
        return "stub"

    @property
    def dimension(self) -> int:
        return DIM

    def status(self) -> EmbedderStatus:
        return EmbedderStatus(
            availability=Availability.AVAILABLE,
            provider="stub",
            model="stub",
            dimension=DIM,
            detail="test",
        )

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        return [[0.1] * DIM for _ in texts]

    def embed_query(self, text: str) -> list[float]:
        return [0.1] * DIM


class _UnusableEmbedder(_StubEmbedder):
    def status(self) -> EmbedderStatus:
        return EmbedderStatus(
            availability=Availability.UNCONFIGURED,
            provider="none",
            model="",
            dimension=0,
            detail="not installed",
        )


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


async def _seed(db: AsyncSession) -> Seed:
    """One Finance passage, embedded. Rolled back, never committed."""
    seed = Seed(uuid4(), uuid4(), uuid4(), uuid4(), uuid4())
    await apply_workspace_scope(db, str(seed.workspace_id))

    await db.execute(
        sa.text("INSERT INTO tenant (id, name) VALUES (:t,'Ask Test')"),
        {"t": str(seed.tenant_id)},
    )
    await db.execute(
        sa.text("INSERT INTO app_user (id, email) VALUES (:u,:e)"),
        {"u": str(seed.user_id), "e": f"ask-{seed.user_id}@example.invalid"},
    )
    await db.execute(
        sa.text(
            "INSERT INTO workspace (id, workspace_id, tenant_id, name, reporting_currency)"
            " VALUES (:i,:i,:t,'Ask Test','OMR')"
        ),
        {"i": str(seed.workspace_id), "t": str(seed.tenant_id)},
    )
    await db.execute(
        sa.text(
            "INSERT INTO document (id, workspace_id, filename, content_type, size_bytes,"
            " storage_key, content_sha256)"
            " VALUES (:d,:w,'terms.pdf','application/pdf',1,:k,:h)"
        ),
        {
            "d": str(seed.document_id),
            "w": str(seed.workspace_id),
            "k": f"k/{seed.document_id}",
            "h": seed.document_id.hex * 2,
        },
    )
    await db.execute(
        sa.text(
            "INSERT INTO chunk (id, workspace_id, document_id, ordinal, content, scope,"
            " department, classified_by, confidence, review_state, source_page,"
            # `ck_chunk_embedding_provenance`: a stored vector must name the
            # model that produced it. An embedding whose origin is unknown can
            # never be re-embedded correctly when the model changes.
            " source_label, embedding, embedding_model_id, embedding_dim)"
            " VALUES (:i,:w,:d,0,'Payment is due within 30 days.','L3',ARRAY['finance'],"
            "         'rules',1.0,'approved',1,'terms.pdf',CAST(:e AS vector),'stub',:dim)"
        ),
        {
            "i": str(seed.finance_chunk),
            "w": str(seed.workspace_id),
            "d": str(seed.document_id),
            "e": str([0.1] * DIM),
            "dim": DIM,
        },
    )
    return seed


def _scope(seed: Seed, *departments: Department) -> ScopedSession:
    return ScopedSession(
        user_id=seed.user_id,
        tenant_id=seed.tenant_id,
        workspace_id=seed.workspace_id,
        role=Role.CONTRIBUTOR,
        departments=frozenset(departments),
    )


def _provider(response: str = ANSWER) -> ScriptedProvider:
    return ScriptedProvider({"assistant-answer": response})


QUESTION = Question(text="What are our payment terms?", department=Department.FINANCE)


# ── The H1 experiment ─────────────────────────────────────────


async def test_a_caller_holding_finance_gets_an_answer_citing_the_finance_passage(
    app_db: None,
) -> None:
    async with _unscoped_session() as db:
        seed = await _seed(db)
        provider = _provider()

        result = await ask(
            db,
            _scope(seed, Department.FINANCE),
            QUESTION,
            provider=provider,
            settings=get_settings(),
        )

        assert isinstance(result, AssistantAnswer)
        assert [c.chunk_id for c in result.citations] == [seed.finance_chunk]


async def test_the_same_caller_without_finance_gets_no_passage_over_the_same_data(
    app_db: None,
) -> None:
    """**The pair is the claim.** Same rows, same question, same code path —
    and the model is never called, which the provider's own call log proves.
    A refusal produced by filtering an answer would show a call here."""
    async with _unscoped_session() as db:
        seed = await _seed(db)
        provider = _provider()

        result = await ask(
            db,
            _scope(seed, Department.EXECUTIVE),
            QUESTION,
            provider=provider,
            settings=get_settings(),
        )

        assert isinstance(result, AssistantRefusal)
        assert result.reason is UnavailableReason.NO_PASSAGE
        assert provider.calls == [], "nothing was retrievable, so nothing should have been asked"


# ── What crossed the boundary ─────────────────────────────────


async def test_the_fence_reaches_the_prompt_and_no_chunk_id_does(app_db: None) -> None:
    """Both halves matter. The fence is what lets a human reading the transcript
    see which sentence was customer content; the absent chunk id is ADR 0055 —
    an id in the prompt is an id in the model's output, and from there in a log.
    """
    async with _unscoped_session() as db:
        seed = await _seed(db)
        provider = _provider()

        await ask(
            db,
            _scope(seed, Department.FINANCE),
            QUESTION,
            provider=provider,
            settings=get_settings(),
        )

        assert len(provider.calls) == 1
        call = provider.calls[0]
        sent = call.system + " ".join(m.content for m in call.messages) + str(call.grounding)

        assert "<untrusted source=document ref=p1>" in sent
        assert "Payment is due within 30 days." in sent
        # ADR 0055. Checked across everything sent, not just one field — a
        # chunk id leaking through grounding would be no better than one in
        # the system prompt.
        assert str(seed.finance_chunk) not in sent
        assert str(seed.document_id) not in sent


async def test_every_retrieved_passage_taints_the_turn(
    app_db: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A6 step 5, asserted through the shipped composition rather than through
    `fence.prepare` directly — which is exactly what ADR 0055's revisit trigger
    warns about: `prepare` surviving as a wrapper nothing calls, with the taint
    eval still pointed at it."""
    seen: list[Any] = []
    original = ask_module.prepare

    def capture(passages: Any) -> Any:
        grounding = original(passages)
        seen.append(grounding)
        return grounding

    monkeypatch.setattr("app.assistant.ask.prepare", capture)

    async with _unscoped_session() as db:
        seed = await _seed(db)
        await ask(
            db,
            _scope(seed, Department.FINANCE),
            QUESTION,
            provider=_provider(),
            settings=get_settings(),
        )

        assert len(seen) == 1, "the shipped path did not call `prepare`"
        assert seen[0].turn.tainted
        assert len(seen[0].turn.blocks) == 1


# ── The ledger ────────────────────────────────────────────────


async def _generation(db: AsyncSession, workspace_id: UUID) -> Any:
    return (
        await db.execute(
            sa.text(
                "SELECT id, outcome, unavailable_reason, scope_key, retention_until,"
                "       input_snapshot"
                "  FROM generation WHERE workspace_id = :w AND module = :m"
            ),
            {"w": str(workspace_id), "m": MODULE},
        )
    ).one()


async def test_an_answer_writes_its_row_its_citations_and_a_retention_date(
    app_db: None,
) -> None:
    async with _unscoped_session() as db:
        seed = await _seed(db)
        await ask(
            db,
            _scope(seed, Department.FINANCE),
            QUESTION,
            provider=_provider(),
            settings=get_settings(),
        )
        await db.flush()

        row = await _generation(db, seed.workspace_id)
        assert row.outcome == "answered"
        # ADR 0057: the tag comes from what was cited, not from who asked.
        assert row.scope_key == "L3:finance"
        assert row.retention_until is not None, (
            "the column has existed since 0023 and nothing ever wrote it (ADR 0057)"
        )
        # **This assertion was the opposite in A6, and A7 corrected it.**
        # ADR 0055 keeps chunk ids out of the *prompt* — an id in the prompt is
        # an id in the model's output and from there in a log. The stored
        # snapshot is a different question, and `doc/20` A7 wants the ids there:
        # `generation_citation` records what was **cited**, and reviewing a bad
        # answer needs what was **retrieved**. Over-applying the prompt rule to
        # the ledger would have lost exactly that.
        snapshot = row.input_snapshot
        assert snapshot["refs"] == {"p1": str(seed.finance_chunk)}
        assert snapshot["passage_count"] == 1
        assert snapshot["tainted"] is True, "every retrieved passage taints the turn"
        # ADR 0058 and `doc/06` §9: the question yes, the passage bodies never.
        assert snapshot["question"] == QUESTION.text
        assert "Payment is due within 30 days." not in str(snapshot), (
            "passage text in `input_snapshot` duplicates the corpus into a table "
            "with a different lifecycle — a deleted document would leave its text here"
        )

        cited = (
            await db.execute(
                sa.text(
                    "SELECT chunk_id, ordinal FROM generation_citation"
                    " WHERE generation_id = :g ORDER BY ordinal"
                ),
                {"g": str(row.id)},
            )
        ).all()
        assert [c.chunk_id for c in cited] == [seed.finance_chunk]


async def test_a_refusal_writes_a_row_too(app_db: None) -> None:
    """**A ledger holding only the answers cannot say how often the product
    declined** — and for this design that is the number that matters most,
    because a refusal is the outcome it produces on purpose."""
    async with _unscoped_session() as db:
        seed = await _seed(db)
        await ask(
            db,
            _scope(seed, Department.EXECUTIVE),
            QUESTION,
            provider=_provider(),
            settings=get_settings(),
        )
        await db.flush()

        row = await _generation(db, seed.workspace_id)
        assert row.outcome == "unavailable"
        assert row.unavailable_reason == UnavailableReason.NO_PASSAGE.value
        assert row.retention_until is not None


# ── Refusals that never reach a model ─────────────────────────


async def test_no_embedder_refuses_rather_than_falling_back_to_text_search(
    app_db: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ADR 0003 + ADR 0011's pattern, and the argument is `CLAUDE.md`'s: a worse
    retriever does not fail, it **ranks** — confident citations to the wrong
    passages, with no visible symptom at all."""
    monkeypatch.setattr(ask_module, "get_embedder", _UnusableEmbedder)
    async with _unscoped_session() as db:
        seed = await _seed(db)
        provider = _provider()

        result = await ask(
            db,
            _scope(seed, Department.FINANCE),
            QUESTION,
            provider=provider,
            settings=get_settings(),
        )

        assert isinstance(result, AssistantRefusal)
        assert result.reason is UnavailableReason.EMBEDDER_UNCONFIGURED
        assert provider.calls == []


async def test_a_model_citing_a_ref_it_was_never_given_is_refused(app_db: None) -> None:
    """The injection outcome, now through the shipped path rather than through
    A3's stand-in harness."""
    async with _unscoped_session() as db:
        seed = await _seed(db)
        result = await ask(
            db,
            _scope(seed, Department.FINANCE),
            QUESTION,
            provider=_provider(
                '{"answered": true, "segments": [{"text": "Net 30.", "cited_refs": ["p9"]}]}'
            ),
            settings=get_settings(),
        )

        assert isinstance(result, AssistantRefusal)
        assert result.reason is UnavailableReason.UNCITED_CLAIM


async def test_a_model_stating_a_figure_no_passage_carries_is_refused(app_db: None) -> None:
    """I1 through the real composition. The passage says 30 days; the answer
    says 45."""
    async with _unscoped_session() as db:
        seed = await _seed(db)
        result = await ask(
            db,
            _scope(seed, Department.FINANCE),
            QUESTION,
            provider=_provider(
                '{"answered": true, "segments":'
                ' [{"text": "Payment is due within 45 days.", "cited_refs": ["p1"]}]}'
            ),
            settings=get_settings(),
        )

        assert isinstance(result, AssistantRefusal)
        assert result.reason is UnavailableReason.INVENTED_NUMBER


async def test_answered_false_is_a_refusal_not_an_empty_answer(app_db: None) -> None:
    """The model's own "no". It must not become a blank answer bubble."""
    async with _unscoped_session() as db:
        seed = await _seed(db)
        result = await ask(
            db,
            _scope(seed, Department.FINANCE),
            QUESTION,
            provider=_provider('{"answered": false, "segments": []}'),
            settings=get_settings(),
        )

        assert isinstance(result, AssistantRefusal)


# ── The scope tag ─────────────────────────────────────────────


def _passage(scope: Scope, *departments: Department) -> Passage:
    return Passage(
        id=uuid4(),
        content="x",
        document_id=uuid4(),
        source_page=None,
        source_label=None,
        scope=scope,
        department=departments,
    )


def test_one_restricted_citation_makes_the_whole_answer_restricted() -> None:
    """ADR 0057, and deliberately blunt: an artefact is as sensitive as the most
    sensitive thing in it. A tag computed any other way lets the restricted
    sentence live on under a weaker rule, which is the side door migration 0023
    names."""
    tag = scope_key_for_passages(
        (
            _passage(Scope.L2_COMPANY_INTERNAL),
            _passage(Scope.L4_RESTRICTED, Department.FINANCE),
        )
    )
    assert tag == "L4:finance"


def test_the_tag_is_sorted_so_identical_inputs_produce_one_key() -> None:
    """`context.scope_key_for`'s reason, unchanged: an unsorted join gives two
    tags to identical inputs, and the retention and export queries that read
    this column then miss rows."""
    one = scope_key_for_passages(
        (_passage(Scope.L3_DEPARTMENT, Department.SALES, Department.FINANCE),)
    )
    two = scope_key_for_passages(
        (_passage(Scope.L3_DEPARTMENT, Department.FINANCE, Department.SALES),)
    )
    assert one == two == "L3:finance,sales"


def test_llm_availability_is_imported_to_keep_the_boundary_honest() -> None:
    """`test_ai_boundary.py` forbids naming the vendor; importing the contract's
    own enum is how a test says "a provider" without saying which."""
    assert LlmAvailability.AVAILABLE


async def test_a_parsed_no_is_no_passage_and_not_a_malformed_response(app_db: None) -> None:
    """**A regression test for the most common outcome getting the wrong words.**

    `answered: false` is a complete, valid response and its prose is empty.
    `pipeline.run` reads empty prose as malformed, retries, and returns
    `SCHEMA_INVALID` — so a founder asking a runway question of a supplier
    agreement was told *"the answer came back in a shape we could not read"*,
    which blames our pipeline for the assistant working exactly as designed.

    Found end to end against a real model, not by any unit test: the scripted
    provider returns whatever a test hands it, and every earlier test handed it
    something that parsed **and** answered.
    """
    async with _unscoped_session() as db:
        seed = await _seed(db)
        provider = _provider('{"answered": false, "segments": []}')

        result = await ask(
            db,
            _scope(seed, Department.FINANCE),
            QUESTION,
            provider=provider,
            settings=get_settings(),
        )
        await db.flush()

        assert isinstance(result, AssistantRefusal)
        assert result.reason is UnavailableReason.NO_PASSAGE, (
            "a model that read the passages and said no is not a malformed response"
        )
        assert "shape we could not read" not in result.sentence
        # And it cost one call, not two: the retry existed only because empty
        # prose looked like a failure.
        assert len(provider.calls) == 1, f"declining cost {len(provider.calls)} model calls"

        row = await _generation(db, seed.workspace_id)
        assert row.unavailable_reason == UnavailableReason.NO_PASSAGE.value
