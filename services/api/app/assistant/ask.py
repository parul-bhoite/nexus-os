"""One question, one answer or one refusal. `doc/20` A6.

**The order is the design**, and every step is placed where it is because of
what happens if it runs later:

1. **No embedder → refuse.** ADR 0003 plus ADR 0011's pattern. There is no
   text-search fallback: a worse retriever does not fail, it *ranks*, producing
   confident citations to the wrong passages with no visible symptom.
2. **Embed the question**, in a worker thread — the model is CPU-bound and this
   runs inside the request loop.
3. **Retrieve**, through `chunks.search`, which puts the permission predicate
   inside the query and takes no identity argument (I2/I3).
4. **Nothing retrieved → refuse without calling a model.** An answer produced
   from no passages is an answer produced from the model's memory.
5. **Fence and taint**, via `fence.prepare` — opaque per-call refs, never chunk
   ids (ADR 0055).
6. **`pipeline.run`**, so the kill switch, the budget and the retry are the same
   ones every other generation gets. §10: *"the assistant must go through
   `pipeline.run`."*
7. **`grounding.check`**, the strict verdict.
8. **Record**, in the caller's transaction: the `generation` row and its
   citations, tagged with the scope of what was cited (ADR 0057).

**Two numeral checks, deliberately.** `pipeline.run` is given the numerals of
*every* retrieved passage and rejects-and-retries on anything outside that —
cheap, and it buys the retry. `check` then applies ADR 0053's real rule, which
permits only the numerals of the passages the answer actually **cited**. The
loose one cannot approve anything the strict one rejects, because the strict set
is a subset; it only decides what is worth a second attempt.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Final
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.contracts import (
    LlmProvider,
    LlmTransientError,
    LlmUnavailableError,
    Message,
)
from app.ai.runtime.runner import SkillFailedError, SkillResult, SkillRunner
from app.assistant.budget import (
    QuestionTooLargeError,
    check_grounding,
    check_question,
    consume_ask,
)
from app.assistant.contracts import AssistantAnswer, AssistantRefusal, Citation, Question
from app.assistant.fence import Grounding, prepare, resolve
from app.assistant.grounding import (
    check,
    echoed_from_question,
    permitted_numerals,
    sentence_for,
)
from app.config import Settings
from app.domain.scopes import Department, Scope
from app.domain.session import ScopedSession
from app.embeddings.registry import get_embedder
from app.grounding.ledger import budgets_for, record
from app.grounding.pipeline import (
    Answer,
    Computed,
    Outcome,
    UnavailableReason,
    numerals_supplied,
    run,
)
from app.logging import get_logger
from app.retrieval.chunks import Passage, search

SKILL: Final = "assistant-answer"
MODULE: Final = "assistant.ask"

PASSAGE_LIMIT: Final = 8
"""How many passages the model sees.

`doc/20` §7 option D notes the asymmetry that makes this the cheap lever worth
pulling before a cheaper model: the failure mode of a small N is a **refusal**,
and the failure mode of a weak model is a **confident wrong answer**.
"""

MAX_SEGMENTS: Final = 12
"""Bounded here because it cannot be bounded in the schema.

`runner.validate` implements no `maxItems`, and a keyword it does not implement
is silently ignored rather than rejected — so `maxItems: 12` in `schema.json`
would read as a limit while enforcing nothing. `tests/test_assistant_skill_definition.py`
asserts the schema does *not* carry it, so this stays the only bound.
"""

DECLINED: Final = "The model declined to answer from these passages."
"""Stands in for the empty prose of a well-formed `answered: false`. Never
rendered — see `_read_output`."""

RETENTION_DAYS: Final = 365
"""How long an assistant generation is kept.

Written for the first time here (ADR 0057). The column has existed since
migration 0023 and nothing has ever set it, which made it read as a guarantee
the product was not keeping.
"""

_log = get_logger(__name__)


@dataclass(slots=True)
class _ModelOutput:
    """What the closure hands back to the composition.

    `pipeline.run`'s `call_model` returns prose, because that is all the numeral
    guard needs. The refs have to travel out some other way, and a small mutable
    holder is that way — closing over a list would work identically and read
    worse.
    """

    refs: tuple[str, ...] = ()
    segments: int = 0
    answered: bool = True
    parsed: bool = False
    """Whether a well-formed response was read at all.

    Distinguishes *"the model said no"* from *"the model returned something we
    could not read"*, which produce the same empty prose and must not produce
    the same sentence."""
    tokens_in: int = 0
    tokens_out: int = 0
    raw: dict[str, Any] = field(default_factory=dict)


async def ask(
    db: AsyncSession,
    scope: ScopedSession,
    question: Question,
    *,
    provider: LlmProvider,
    settings: Settings,
    disabled_skills: frozenset[str] = frozenset(),
    timezone: str = "UTC",
) -> AssistantAnswer | AssistantRefusal:
    """Answer `question` from passages this caller may read, or refuse saying why.

    Takes a `ScopedSession` and no identifiers. There is deliberately no
    `workspace_id` or `user_id` parameter — that would make scope something a
    caller supplies, which is what I2 forbids.
    """
    # **Before the embedder, not after.** Both of these are refusals about the
    # request rather than about the data, and running them first means a
    # pathological question costs nothing — not a model call, not an embedding,
    # not a retrieval (ADR 0058).
    check_question(question.text)
    await consume_ask(db, user_id=str(scope.user_id))

    embedder = get_embedder()
    if not embedder.status().usable:
        return await _refuse(
            db, scope, question, UnavailableReason.EMBEDDER_UNCONFIGURED, passages=()
        )

    # In a thread: the embedder is CPU-bound local inference, and awaiting it
    # inline would stall every other request on this worker.
    embedding = await asyncio.to_thread(embedder.embed_query, question.text)

    passages = await search(db, scope, embedding=embedding, limit=PASSAGE_LIMIT)
    if not passages:
        # **No model call.** The refusal is ours and identical whether the
        # content does not exist or exists at a scope this caller lacks — the
        # 404-not-403 rule applied to prose.
        return await _refuse(db, scope, question, UnavailableReason.NO_PASSAGE, passages=())

    try:
        check_grounding(passages)
    except QuestionTooLargeError:
        _log.warning("assistant.grounding_over_ceiling", passages=len(passages))
        return await _refuse(
            db, scope, question, UnavailableReason.BUDGET_EXHAUSTED, passages=passages
        )

    grounding = prepare(passages)
    output = _ModelOutput()
    # ADR 0062. A figure the customer typed is not one the model invented —
    # "who can approve 3,000 rial?" was refused for stating 3,000. Permitted
    # only alongside a citation; `check` enforces that half.
    asked_numerals = numerals_supplied(question.text)
    budgets = await budgets_for(
        db,
        workspace_id=scope.workspace_id,
        user_id=scope.user_id,
        settings=settings,
        timezone=timezone,
    )

    runner = SkillRunner(provider=provider)

    async def call_model(_: Computed) -> str:
        result = await runner.invoke(
            SKILL,
            # **The fenced passages go in the message, not in `grounding`.**
            # The provider renders every grounding value through `repr()` —
            # right for narration's scalars, where quoting
            # makes an odd value visible, and wrong for a multi-passage block:
            # it collapses the fences onto one escaped line, spends tokens on
            # backslashes, and destroys the visual separation that is the whole
            # reason the fence helps the model treat the text as data.
            messages=[Message(role="user", content=f"{grounding.block}\n\n{question.text}")],
            grounding={
                "question": question.text,
                # The refs, not the text. Declaring them keeps the
                # `requires_grounding` guard meaningful — a caller that reached
                # a model with nothing retrieved fails loudly — without pushing
                # kilobytes of customer prose through a `repr()`.
                "passage_refs": list(grounding.by_ref),
                "department": question.department.value,
            },
            # **One, not the default two.** `pipeline.run` already retries once
            # on an invented numeral; composed at their defaults the two would
            # spend four provider calls where P14 specifies two, and the second
            # pair would look identical to the first in the log. The narrator
            # makes the same choice, for the same reason.
            attempts=1,
        )
        return _read_output(result, output)

    try:
        answer = await run(
            skill=SKILL,
            computed=Computed(),
            call_model=call_model,
            budgets=budgets,
            disabled_skills=disabled_skills,
            # The loose pre-filter. `check` below applies ADR 0053's cited-only rule.
            also_permitted=frozenset(permitted_numerals(passages) | asked_numerals),
        )
    except LlmUnavailableError:
        # ADR 0011: no key is a documented configuration, not an outage.
        return await _refuse(
            db,
            scope,
            question,
            UnavailableReason.MODEL_UNAVAILABLE,
            passages=passages,
            grounding=grounding,
        )
    except LlmTransientError:
        return await _refuse(
            db,
            scope,
            question,
            UnavailableReason.PROVIDER_FAILED,
            passages=passages,
            grounding=grounding,
        )
    except (SkillFailedError, ValueError, KeyError, TypeError):
        # A response we could not read, twice. Caught rather than propagated
        # because a 500 tells the reader nothing and loses the ledger row.
        return await _refuse(
            db,
            scope,
            question,
            UnavailableReason.SCHEMA_INVALID,
            passages=passages,
            grounding=grounding,
        )

    if answer.outcome is not Outcome.ANSWERED or not output.answered:
        # **A parsed "no" is `NO_PASSAGE`, whatever the pipeline made of it.**
        # The model read the passages and said they do not answer the question,
        # which is the outcome this design produces on purpose — reporting it as
        # a malformed response would tell a founder something is broken on the
        # most ordinary path in the product.
        reason = (
            UnavailableReason.NO_PASSAGE
            if output.parsed and not output.answered
            else (answer.reason or UnavailableReason.NO_PASSAGE)
        )
        return await _refuse(db, scope, question, reason, passages=passages, grounding=grounding)

    if output.segments > MAX_SEGMENTS:
        _log.warning("assistant.too_many_segments", segments=output.segments)
        return await _refuse(
            db,
            scope,
            question,
            UnavailableReason.SCHEMA_INVALID,
            passages=passages,
            grounding=grounding,
        )

    citations, unknown = resolve(grounding, output.refs)
    if unknown:
        return await _refuse(
            db,
            scope,
            question,
            UnavailableReason.UNCITED_CLAIM,
            passages=passages,
            grounding=grounding,
        )

    candidate = AssistantAnswer(prose=answer.prose, citations=citations)
    refusal = check(candidate, passages, question_numerals=asked_numerals)
    if refusal is not None:
        return await _refuse(
            db, scope, question, refusal.reason, passages=passages, grounding=grounding
        )

    generation_id = await record(
        db,
        workspace_id=scope.workspace_id,
        module=MODULE,
        prompt_version="1",
        answer=answer,
        input_snapshot=_snapshot(
            question,
            grounding,
            echoed=echoed_from_question(
                candidate.prose,
                _cited_passages(passages, citations),
                asked_numerals,
            ),
        ),
        calculation_trace={"retrieved": len(passages), "cited": len(citations)},
        scope_key=scope_key_for_passages(_cited_passages(passages, citations)),
        input_tokens=output.tokens_in,
        output_tokens=output.tokens_out,
        requested_by_user_id=scope.user_id,
    )
    await _write_citations(db, scope, generation_id, citations)
    await _set_retention(db, generation_id)
    return candidate


def _read_output(result: SkillResult, into: _ModelOutput) -> str:
    """Pull prose and refs out of one skill response.

    Returns the prose `pipeline.run` will check. A malformed response raises,
    and `pipeline.run` retries once before calling it `SCHEMA_INVALID` — the
    same treatment every other skill gets.
    """
    payload: Any = result.data
    if isinstance(payload, str):
        payload = json.loads(payload)

    segments = payload.get("segments") or []
    into.answered = bool(payload.get("answered"))
    into.parsed = True
    into.segments = len(segments)
    into.refs = tuple(ref for segment in segments for ref in segment.get("cited_refs", []))
    into.raw = payload
    into.tokens_in = result.completion.usage.input_tokens
    into.tokens_out = result.completion.usage.output_tokens

    prose = " ".join(str(segment.get("text", "")) for segment in segments).strip()

    # **`answered: false` is a complete, valid response, and its prose is
    # empty.** `pipeline.run` reads empty prose as malformed, retries, and
    # returns `SCHEMA_INVALID` — so the assistant's *most common correct
    # outcome* cost two model calls and told the reader "the answer came back in
    # a shape we could not read", blaming our pipeline for an honest no. Found
    # end to end, asking a runway question of a supplier agreement.
    #
    # The marker carries no numerals, so the guard has nothing to reject, and it
    # never reaches a reader: `ask` sees `answered` false and refuses.
    return prose or (DECLINED if into.parsed else "")


def _cited_passages(
    passages: tuple[Passage, ...] | list[Passage], citations: tuple[Citation, ...]
) -> tuple[Passage, ...]:
    cited = {c.chunk_id for c in citations}
    return tuple(p for p in passages if p.id in cited)


def scope_key_for_passages(passages: tuple[Passage, ...]) -> str:
    """The tag a generation inherits from what it cited. ADR 0057.

    **The maximum scope, and the union of departments** — a single L4 citation
    makes the whole answer L4. Deliberately blunt: an artefact is as sensitive
    as the most sensitive thing in it, and a tag computed any other way would
    let the restricted sentence live on under a weaker rule, which is the side
    door migration 0023 names.

    Sorted, for the same reason `context.scope_key_for` sorts: an unsorted join
    gives two tags to identical inputs and makes the retention and export
    queries that read this column miss rows.
    """
    if not passages:
        # Unreachable through `ask` — an answer citing nothing is a refusal
        # (ADR 0053) — but a refusal's own row lands here.
        return Scope.L2_COMPANY_INTERNAL.name.split("_")[0]

    highest = max(p.scope for p in passages)
    departments = sorted({d.value for p in passages for d in p.department})
    tag = f"L{highest.value}"
    return f"{tag}:{','.join(departments)}" if departments else tag


def _snapshot(
    question: Question, grounding: Grounding, *, echoed: frozenset[str] = frozenset()
) -> dict[str, Any]:
    """What was asked and what was shown. **Never the passage text.**

    `doc/06` §9 calls `input_snapshot` *"a second copy of customer content"*,
    carrying the same scope tag, retention and export obligations as the
    original. On what will be the highest-frequency path in the product,
    writing passage bodies here would duplicate the corpus into a table with a
    different lifecycle — and the deletion request that removes a document
    would leave its text behind in a thousand generation rows.

    **The question itself is stored** (ADR 0058): a ledger that cannot say what
    was asked cannot settle the disputes it exists for. It is protected by the
    row's own `scope_key`, which ADR 0057 derives from the passages cited.

    The chunk ids are here as well as in `generation_citation`, because the
    citations table records only what was *cited* and this records what was
    *retrieved* — the difference is what a review of a bad answer needs.
    """
    return {
        "question": question.text,
        "department": question.department.value,
        "refs": {ref: str(passage.id) for ref, passage in grounding.by_ref.items()},
        "passage_count": len(grounding.by_ref),
        "tainted": grounding.turn.tainted,
        # **ADR 0062's visibility half.** Non-empty means the answer stated a
        # figure that came from the question rather than from a cited passage.
        # Almost always empty; when it is not, somebody reviewing this answer
        # can see the permission was used instead of having to infer it.
        "question_numerals_echoed": sorted(echoed),
    }


async def _write_citations(
    db: AsyncSession, scope: ScopedSession, generation_id: UUID, citations: tuple[Citation, ...]
) -> None:
    for ordinal, citation in enumerate(citations):
        await db.execute(
            text(
                "INSERT INTO generation_citation"
                " (workspace_id, generation_id, chunk_id, document_id, source_page,"
                "  source_label, ordinal)"
                " VALUES (:ws, :g, :c, :d, :page, :label, :ordinal)"
            ),
            {
                "ws": str(scope.workspace_id),
                "g": str(generation_id),
                "c": str(citation.chunk_id),
                "d": str(citation.document_id),
                "page": citation.source_page,
                "label": citation.source_label or "",
                "ordinal": ordinal,
            },
        )


async def _set_retention(db: AsyncSession, generation_id: UUID) -> None:
    """ADR 0057. `ledger.record` does not take it, and widening its signature
    would put a retention policy on every caller that has never had one."""
    await db.execute(
        text("UPDATE generation SET retention_until = :until WHERE id = :id"),
        {"until": datetime.now(UTC) + timedelta(days=RETENTION_DAYS), "id": str(generation_id)},
    )


async def _refuse(
    db: AsyncSession,
    scope: ScopedSession,
    question: Question,
    reason: UnavailableReason,
    *,
    passages: tuple[Passage, ...] | list[Passage],
    grounding: Grounding | None = None,
) -> AssistantRefusal:
    """Record the refusal, then return it.

    **Every outcome leaves a row, refusals included.** A ledger that holds only
    the answers cannot say how often the product declined, which is the number
    that decides whether the assistant is working — and a refusal is the outcome
    this design produces most.

    Tagged with the scope of what was *retrieved*: a refusal is still an artefact
    about content the caller could read.
    """
    generation_id = await record(
        db,
        workspace_id=scope.workspace_id,
        module=MODULE,
        prompt_version="1",
        answer=Answer(outcome=Outcome.UNAVAILABLE, reason=reason),
        input_snapshot=_snapshot(question, grounding) if grounding else {"question": question.text},
        calculation_trace={"retrieved": len(passages)},
        scope_key=scope_key_for_passages(tuple(passages)),
        requested_by_user_id=scope.user_id,
    )
    await _set_retention(db, generation_id)
    return AssistantRefusal(reason=reason, sentence=sentence_for(reason))


__all__ = [
    "MAX_SEGMENTS",
    "MODULE",
    "PASSAGE_LIMIT",
    "Department",
    "ask",
    # Exported so `tests/test_assistant_ask_db.py` can wrap it and prove the
    # shipped path calls it — ADR 0055's revisit trigger warns that `prepare`
    # surviving as a wrapper nothing calls is the failure to watch for.
    "prepare",
    "scope_key_for_passages",
]
