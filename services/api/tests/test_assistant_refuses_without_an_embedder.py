"""Absence is a refusal, never a degradation. `doc/20` A10.

**Why this is the acceptance test for a deployment step.** A10 is mostly not
code: `run_scheduler` is already off by default and already true on exactly one
container, and `config.py` already explains why the ~2 GB of weights must not
sit in the process serving requests. What A10 adds to the *product* is the
guarantee that when that worker has not run — or `[embeddings]` is not installed
at all — the assistant says so instead of quietly getting worse.

That distinction is the one `CLAUDE.md` is most emphatic about, and it is not
symmetric with the language model. A missing model **fails**: the call raises
and there is nothing to show. A missing embedder **ranks** — swap in something
plausible and retrieval still returns eight passages, still in an order, still
cited confidently, and nothing on the screen looks different. There is no
symptom. So the rule has to be structural: no text-search fallback, no
`DeterministicEmbedder`, no "best effort" path. Refuse.

**Zero provider calls** is the assertion that makes it real. A refusal that
still pays for a model call is a refusal somebody will later be tempted to turn
into an answer.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
import sqlalchemy as sa

from app.assistant import ask as ask_module
from app.assistant.contracts import AssistantRefusal
from app.config import get_settings
from app.db import _unscoped_session, get_engine, get_sessionmaker
from app.domain.scopes import Department
from app.embeddings.contracts import Availability, EmbedderStatus
from app.grounding.pipeline import UnavailableReason
from tests.dburl import async_database_url
from tests.test_assistant_ask_db import QUESTION, _provider, _scope, _seed, _StubEmbedder

pytestmark = pytest.mark.requires_db

ASYNC_DB_URL = async_database_url()


class _Unconfigured(_StubEmbedder):
    """`[embeddings]` not installed, or the weights not downloaded."""

    def status(self) -> EmbedderStatus:
        return EmbedderStatus(
            availability=Availability.UNCONFIGURED,
            provider="none",
            model="",
            dimension=0,
            detail="fastembed is not installed",
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


async def test_an_unconfigured_embedder_refuses_writes_a_row_and_spends_nothing(
    app_db: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(ask_module, "get_embedder", _Unconfigured)

    async with _unscoped_session() as db:
        seed = await _seed(db)
        provider = _provider()

        result = await ask_module.ask(
            db,
            _scope(seed, Department.FINANCE),
            QUESTION,
            provider=provider,
            settings=get_settings(),
        )
        await db.flush()

        assert isinstance(result, AssistantRefusal)
        assert result.reason is UnavailableReason.EMBEDDER_UNCONFIGURED
        assert provider.calls == [], "a refusal that still pays for a model call"

        row = (
            await db.execute(
                sa.text(
                    "SELECT outcome, unavailable_reason, retention_until FROM generation"
                    " WHERE workspace_id = :w AND module = :m"
                ),
                {"w": str(seed.workspace_id), "m": ask_module.MODULE},
            )
        ).one()
        assert row.outcome == "unavailable"
        assert row.unavailable_reason == UnavailableReason.EMBEDDER_UNCONFIGURED.value
        assert row.retention_until is not None


async def test_the_refusal_says_what_is_switched_off_rather_than_apologising(
    app_db: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ADR 0003 + ADR 0011's pattern: absence is a **supported state**.

    The next step is an operator's, not the reader's, so the sentence must not
    send a founder looking at their own documents for a fault that is in the
    deployment.
    """
    monkeypatch.setattr(ask_module, "get_embedder", _Unconfigured)

    async with _unscoped_session() as db:
        seed = await _seed(db)
        result = await ask_module.ask(
            db,
            _scope(seed, Department.FINANCE),
            QUESTION,
            provider=_provider(),
            settings=get_settings(),
        )

        assert isinstance(result, AssistantRefusal)
        lowered = result.sentence.lower()
        for broken in ("error", "failed", "sorry", "problem with your", "try again"):
            assert broken not in lowered, f"{broken!r} turns a configuration into an outage"
        assert "not switched on" in lowered or "not" in lowered
        assert "document" in lowered, "the reader must be told their documents are fine"


def test_no_fallback_retriever_exists_to_be_switched_on() -> None:
    """**The structural half**, and the reason this file is not just the two
    tests above.

    A future author under pressure adds `if not embedder.usable: text_search()`,
    and every test above still passes — they assert what happens when the
    refusal is reached, not that the refusal is the only path. This reads the
    source for the shapes that fallback takes.
    """
    source = (ask_module.__file__ or "").replace("ask.py", "")
    from pathlib import Path

    ask_source = Path(ask_module.__file__ or "").read_text(encoding="utf-8")
    assert source

    for shape in ("ilike", "to_tsquery", "websearch_to_tsquery", "DeterministicEmbedder"):
        assert shape not in ask_source, (
            f"{shape!r} in ask.py — a worse retriever does not fail, it ranks, and "
            "produces confident citations to the wrong passages with no symptom"
        )
