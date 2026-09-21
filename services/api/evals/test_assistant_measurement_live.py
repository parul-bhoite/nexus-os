"""The three counts A9 asks for, against the real model. `doc/20` A9, live half.

The deterministic half (`test_assistant_measurement.py`) measures whether the
answering document **reaches** the model; ADR 0061 says why that is all it can
honestly do. This half measures what the model then **does** with it, over the
same 33 questions and the same ten authored documents.

**Two of the three counts are produced here. The third is not automatable** and
A9 says so: whether a citation actually supports the claim is a judgement.
What this file does for it is write a transcript — every question, the prose,
the passages cited — so the judging is reading rather than re-running.

**Nothing about model quality is asserted.** A model that answers two fewer
questions this month is not a regression in this repository, and a test that
failed on it would be a test nobody could fix. Two things *are* asserted,
because they are ours:

- A question the corpus cannot answer must not come back answered. That is the
  product's central claim, and a violation is an invented answer.
- Every answer must carry at least one citation.
"""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import AsyncIterator
from dataclasses import replace
from pathlib import Path
from typing import cast
from uuid import uuid4

import pytest

from app.ai.registry import get_provider
from app.assistant.ask import ask
from app.assistant.contracts import AssistantAnswer, Question
from app.config import get_settings
from app.db import _unscoped_session, get_engine, get_sessionmaker
from app.domain.scopes import Department
from app.embeddings.registry import get_embedder
from evals.fixtures.assistant.questions import QUESTIONS, Outcome
from evals.live import gated
from evals.test_assistant_measurement import _scope, _seed
from tests.dburl import async_database_url

pytestmark = [pytest.mark.requires_db, pytest.mark.live_eval]

ASYNC_DB_URL = async_database_url()
TRANSCRIPT = Path(
    os.environ.get("NEXUS_EVAL_TRANSCRIPT")
    or Path(tempfile.gettempdir()) / "a9-live-transcript.json"
)
"""Where the transcript for hand-judging lands. Overridable, because the third
count is somebody reading this file and they may want it somewhere durable."""


@pytest.fixture
async def app_db(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[None]:
    skip = gated()
    if skip:
        pytest.skip(skip)
    assert ASYNC_DB_URL is not None
    monkeypatch.setenv("NEXUS_DATABASE_URL", ASYNC_DB_URL)
    monkeypatch.setenv("NEXUS_STORAGE_SIGNING_SECRET", "test-secret")
    for cache in (get_settings, get_engine, get_sessionmaker):
        cache.cache_clear()
    yield
    await get_engine().dispose()
    for cache in (get_settings, get_engine, get_sessionmaker):
        cache.cache_clear()


async def test_the_three_counts(app_db: None) -> None:
    """Report answered and wrongly-refused; write the transcript for the third.

    `noqa: T201` — the report is the product, as in
    `test_classifier_calibration.py`. A12 reads this.
    """
    embedder = get_embedder()
    if not embedder.status().usable:
        pytest.skip("no embedder — a live run without retrieval measures nothing")

    async with _unscoped_session() as db:
        corpus = await _seed(db, embedder)
        scope = _scope(corpus)
        provider = get_provider()
        settings = get_settings()

        transcript: list[dict[str, object]] = []
        for question in QUESTIONS:
            # **A fresh identity per question, and not to dodge a limit.**
            # `ASK_LIMIT` is ten an hour *per user* (ADR 0058), chosen against
            # the timing oracle — it bounds how fast one person can probe for
            # what exists. A measurement harness is not a person: asking 33
            # questions as one user made the eval fail on the eleventh, which
            # is the limit working. Raising `ASK_LIMIT` to fit the harness
            # would weaken a real defence to suit a test, so the harness stops
            # pretending to be one caller instead.
            asking = replace(scope, user_id=uuid4())
            result = await ask(
                db,
                asking,
                Question(text=question.text, department=Department(question.department)),
                provider=provider,
                settings=settings,
            )
            answered = isinstance(result, AssistantAnswer)
            transcript.append(
                {
                    "question": question.text,
                    "expected": question.expect.value,
                    "answered": answered,
                    "prose": result.prose if isinstance(result, AssistantAnswer) else "",
                    "reason": None if answered else result.reason.value,  # type: ignore[union-attr]
                    "sentence": None if answered else result.sentence,  # type: ignore[union-attr]
                    "cited": (
                        [corpus.by_document.get(c.document_id, "?") for c in result.citations]
                        if isinstance(result, AssistantAnswer)
                        else []
                    ),
                    "should_have_cited": list(question.answered_by),
                    "note_for_judging": question.note,
                }
            )

        wants_answer = {Outcome.ANSWER, Outcome.ANSWER_MULTI}
        answered_ok = [
            t
            for t in transcript
            if t["expected"] in {o.value for o in wants_answer} and t["answered"]
        ]
        wrongly_refused = [
            t
            for t in transcript
            if t["expected"] in {o.value for o in wants_answer} and not t["answered"]
        ]
        refused_ok = [
            t
            for t in transcript
            if t["expected"] == Outcome.REFUSE_ABSENT.value and not t["answered"]
        ]
        wrongly_answered = [
            t for t in transcript if t["expected"] == Outcome.REFUSE_ABSENT.value and t["answered"]
        ]
        arithmetic = [t for t in transcript if t["expected"] == Outcome.REFUSE_ARITHMETIC.value]
        expected_answers = len(answered_ok) + len(wrongly_refused)

        TRANSCRIPT.write_text(json.dumps(transcript, indent=2), encoding="utf-8")

        print(f"\n{'═' * 76}")  # noqa: T201
        print(f"A9 LIVE — {len(QUESTIONS)} questions, real model, real retrieval")  # noqa: T201
        print(f"{'═' * 76}")  # noqa: T201
        for t in transcript:
            got = "answered" if t["answered"] else f"refused:{t['reason']}"
            cites = ",".join(cast("list[str]", t["cited"])) or "—"
            print(f"  [{t['expected']:>17}] {got:<26} {str(t['question'])[:44]:46s} {cites[:34]}")  # noqa: T201
        print(f"{'═' * 76}")  # noqa: T201
        print(f"  answered (of {expected_answers} that should be)   {len(answered_ok)}")  # noqa: T201
        print(f"  wrongly refused                    {len(wrongly_refused)}")  # noqa: T201
        absent_total = len(refused_ok) + len(wrongly_answered)
        print(f"  correctly refused as absent        {len(refused_ok)}/{absent_total}")  # noqa: T201
        print(f"  WRONGLY ANSWERED (invented)        {len(wrongly_answered)}")  # noqa: T201
        print(f"  arithmetic questions               {len(arithmetic)}  (judge by hand)")  # noqa: T201
        print("\n  third count — citations that do not support the claim: NOT AUTOMATED")  # noqa: T201
        print(f"  transcript for judging: {TRANSCRIPT}")  # noqa: T201
        print(f"{'═' * 76}\n")  # noqa: T201

        # **Automatable after all.** A9 wrote the third count off as
        # hand-judgement entirely. The first live run showed the arithmetic
        # slice of it is mechanical: a computed figure either appears or it
        # does not. What stays human is whether a citation supports a
        # qualitative claim.
        computed = [
            (q.text, bad)
            for q, t in zip(QUESTIONS, transcript, strict=True)
            for bad in q.forbidden
            if bad in str(t["prose"])
        ]
        assert not computed, f"a computed figure reached the reader (ADR 0053): {computed}"

        # Ours, and therefore asserted. Model quality is not.
        assert not wrongly_answered, (
            "the assistant answered a question the corpus cannot answer: "
            f"{[t['question'] for t in wrongly_answered]}"
        )
        for t in transcript:
            if t["answered"]:
                assert t["cited"], f"answered with no citation: {t['question']}"
