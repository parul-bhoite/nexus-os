"""How often does the answering document reach the model? `doc/20` A9.

**What this half can honestly measure, and what it cannot.**

A9 asks for three counts: answered, wrongly refused, and answered with a
citation that does not support the claim. **None of them is computable without
a model**, and scripting one would only measure the script. So the third count
is hand-judged, by A9's own admission, and the first two belong to the live
half.

What *is* computable with no model and no key is the thing all three rest on:
**did the document holding the answer get retrieved at all?** If it did not, the
assistant cannot answer however good the prompt is, and a refusal is retrieval's
failure rather than the model's. If it did, an unanswered question is a
generation problem. That distinction is the whole value of measuring here, and
it is why this file reports a rank rather than a pass mark.

**It asserts a floor as well as reporting**, because a number nobody fails on is
a number nobody reads. The floor is deliberately below the measured value — it
exists to catch a regression in `retrieval/`, not to encode today's score as a
target.

Needs a real embedder. Skipped, loudly, when one is not configured: a recall
figure computed over hash-derived vectors would be a confident number about
nothing, which `CLAUDE.md` warns about more sharply than it warns about a
missing model.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import _unscoped_session, get_engine, get_sessionmaker
from app.domain.scopes import Department, Role
from app.domain.session import ScopedSession
from app.embeddings.registry import get_embedder
from app.retrieval.chunks import search
from app.retrieval.scoped import apply_workspace_scope
from evals.fixtures.assistant.questions import QUESTIONS, Outcome, Question
from tests.dburl import async_database_url

pytestmark = pytest.mark.requires_db

ASYNC_DB_URL = async_database_url()
DOCUMENTS = Path(__file__).parent / "fixtures" / "assistant" / "documents"
LIMIT = 8
"""`ask.PASSAGE_LIMIT`. Measured at the number the product actually uses — a
recall figure at a different N describes a product nobody ships."""

RECALL_FLOOR = 0.70
"""Below this, `retrieval/` has regressed. Set under the measured value on
purpose; see the module docstring."""


@dataclass(frozen=True, slots=True)
class Corpus:
    workspace_id: UUID
    tenant_id: UUID
    user_id: UUID
    by_document: dict[UUID, str]


@pytest.fixture(scope="module")
def embedder() -> object:
    emb = get_embedder()
    if not emb.status().usable:
        pytest.skip(
            "no embedder configured — a recall figure over fabricated vectors "
            "would be a confident number about nothing"
        )
    return emb


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


async def _seed(db: AsyncSession, emb: object) -> Corpus:
    """Ten documents, one chunk each, embedded with the real model.

    One chunk per document because each fixture is a few hundred words — the
    chunker would produce one anyway, and splitting here would measure the
    chunker rather than retrieval.
    """
    corpus = Corpus(uuid4(), uuid4(), uuid4(), {})
    await apply_workspace_scope(db, str(corpus.workspace_id))

    await db.execute(
        sa.text("INSERT INTO tenant (id, name) VALUES (:t,'A9 Measurement')"),
        {"t": str(corpus.tenant_id)},
    )
    await db.execute(
        sa.text("INSERT INTO app_user (id, email) VALUES (:u,:e)"),
        {"u": str(corpus.user_id), "e": f"a9-{corpus.user_id}@example.invalid"},
    )
    await db.execute(
        sa.text(
            "INSERT INTO workspace (id, workspace_id, tenant_id, name, reporting_currency)"
            " VALUES (:i,:i,:t,'A9 Measurement','OMR')"
        ),
        {"i": str(corpus.workspace_id), "t": str(corpus.tenant_id)},
    )

    paths = sorted(DOCUMENTS.glob("*.txt"))
    assert paths, f"no fixture documents under {DOCUMENTS}"
    texts = [p.read_text(encoding="utf-8") for p in paths]
    vectors = emb.embed_documents(texts)  # type: ignore[attr-defined]

    for path, text, vector in zip(paths, texts, vectors, strict=True):
        document_id = uuid4()
        corpus.by_document[document_id] = path.name
        await db.execute(
            sa.text(
                "INSERT INTO document (id, workspace_id, filename, content_type,"
                " size_bytes, storage_key, content_sha256)"
                " VALUES (:d,:w,:f,'text/plain',:n,:k,:h)"
            ),
            {
                "d": str(document_id),
                "w": str(corpus.workspace_id),
                "f": path.name,
                "n": len(text),
                "k": f"a9/{document_id}",
                "h": document_id.hex * 2,
            },
        )
        await db.execute(
            sa.text(
                "INSERT INTO chunk (id, workspace_id, document_id, ordinal, content,"
                " scope, department, classified_by, confidence, review_state,"
                " source_page, source_label, embedding, embedding_model_id, embedding_dim)"
                " VALUES (:i,:w,:d,0,:c,'L2',ARRAY[]::text[],'rules',1.0,'approved',"
                "         1,:label,CAST(:e AS vector),:model,:dim)"
            ),
            {
                "i": str(uuid4()),
                "w": str(corpus.workspace_id),
                "d": str(document_id),
                "c": text,
                "label": path.name,
                "e": str(list(vector)),
                "model": emb.model_id,  # type: ignore[attr-defined]
                "dim": len(vector),
            },
        )
    return corpus


def _scope(corpus: Corpus) -> ScopedSession:
    return ScopedSession(
        user_id=corpus.user_id,
        tenant_id=corpus.tenant_id,
        workspace_id=corpus.workspace_id,
        role=Role.OWNER,
        departments=frozenset(Department),
    )


async def test_the_answering_document_reaches_the_model(app_db: None, embedder: object) -> None:
    """The measurement. Reports first, asserts second.

    `noqa: T201` on the prints, following `test_classifier_calibration.py`:
    this is the other place where a `print` **is** the product. A recall
    figure nobody can see the effect of is a figure nobody can argue with,
    and a regression should show as a number moving, not only as a failure.
    """
    async with _unscoped_session() as db:
        corpus = await _seed(db, embedder)
        scope = _scope(corpus)

        answerable = [q for q in QUESTIONS if q.answered_by]
        rows: list[tuple[Question, list[int | None]]] = []

        for question in answerable:
            vector = embedder.embed_query(question.text)  # type: ignore[attr-defined]
            passages = await search(db, scope, embedding=vector, limit=LIMIT)
            order = [corpus.by_document[p.document_id] for p in passages]
            rows.append(
                (
                    question,
                    [
                        order.index(name) + 1 if name in order else None
                        for name in question.answered_by
                    ],
                )
            )

        hits = sum(1 for _, ranks in rows for r in ranks if r is not None)
        wanted = sum(len(ranks) for _, ranks in rows)
        top3 = sum(1 for _, ranks in rows for r in ranks if r is not None and r <= 3)
        first = sum(1 for _, ranks in rows for r in ranks if r == 1)

        print(f"\n{'─' * 72}")  # noqa: T201
        print(  # noqa: T201
            f"A9 retrieval measurement — {len(QUESTIONS)} questions, "
            f"{len(corpus.by_document)} documents, N={LIMIT}"
        )
        print(f"{'─' * 72}")  # noqa: T201
        for question, ranks in rows:
            shown = ", ".join(
                f"{n}@{r}" if r else f"{n}@MISS"
                for n, r in zip(question.answered_by, ranks, strict=True)
            )
            flag = " " if all(r is not None for r in ranks) else "!"
            print(f" {flag} {question.text[:52]:54s} {shown}")  # noqa: T201
        print(f"{'─' * 72}")  # noqa: T201
        print(f"  recall@{LIMIT}   {hits}/{wanted}  ({hits / wanted:.0%})")  # noqa: T201
        print(f"  recall@3   {top3}/{wanted}  ({top3 / wanted:.0%})")  # noqa: T201
        print(f"  rank 1     {first}/{wanted}  ({first / wanted:.0%})")  # noqa: T201
        print("\n  Not measured here — needs a model, see the module docstring:")  # noqa: T201
        for outcome in (Outcome.REFUSE_ABSENT, Outcome.REFUSE_ARITHMETIC):
            n = sum(1 for q in QUESTIONS if q.expect is outcome)
            print(f"    {n} questions expecting {outcome.value}")  # noqa: T201
        print(f"{'─' * 72}\n")  # noqa: T201

        assert hits / wanted >= RECALL_FLOOR, (
            f"retrieval recall@{LIMIT} is {hits / wanted:.0%}, under the "
            f"{RECALL_FLOOR:.0%} floor — `retrieval/` has regressed, or the "
            f"fixture corpus has drifted from the questions"
        )


def test_every_question_names_a_document_that_exists() -> None:
    """A question pointing at a file nobody wrote would count as a retrieval
    miss forever, and the number would be wrong in the pessimistic direction —
    the direction nobody investigates."""
    on_disk = {p.name for p in DOCUMENTS.glob("*.txt")}
    named = {name for q in QUESTIONS for name in q.answered_by}

    assert named <= on_disk, f"questions name missing documents: {sorted(named - on_disk)}"
    assert on_disk <= named, (
        f"documents no question exercises: {sorted(on_disk - named)} — "
        "corpus weight that measures nothing"
    )


def test_the_refusal_questions_name_no_document() -> None:
    """A question expecting a refusal must not claim a source. If it had one the
    corpus *would* answer it, and the expectation is wrong rather than the
    product."""
    for question in QUESTIONS:
        if question.expect in (Outcome.REFUSE_ABSENT, Outcome.REFUSE_ARITHMETIC):
            if question.expect is Outcome.REFUSE_ABSENT:
                assert not question.answered_by, (
                    f"{question.text!r} expects a refusal but names a source"
                )
            else:
                # Arithmetic refusals *do* name the document holding the inputs:
                # the figures are retrievable and it is the sum that is refused.
                assert question.answered_by, (
                    f"{question.text!r} refuses arithmetic over figures it does not name"
                )
