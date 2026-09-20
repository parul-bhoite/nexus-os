"""`POST /dashboards/{department}/ask`. `doc/20` A8, shape from ADR 0059.

Its own module rather than a third endpoint on `dashboards.py`'s 2,300 lines,
because `tests/test_no_unauthenticated_crawl.py` walks imports and **falls back
to the module** when it cannot attribute them to a route function. This is the
endpoint where *"what can this path reach?"* is most worth being able to answer
precisely, and a module with five imports answers it.

**The refusals are `dashboards.py`'s, imported rather than reimplemented.**
`reachable_director` is what 404s a department the caller does not hold, and
sharing the function is what stops the ask endpoint and the director page
drifting apart on who may see what.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.ai.registry import get_provider
from app.assistant.ask import ask
from app.assistant.contracts import AssistantAnswer, Question
from app.auth.csrf import require_csrf
from app.config import Settings, get_settings
from app.connectors.rate_limit import RateLimitedError
from app.deps import CurrentScope
from app.retrieval.scoped import scoped_connection
from app.routes.dashboards import ReachableDirector

router = APIRouter(prefix="/dashboards", tags=["assistant"])


class AskIn(BaseModel):
    question: str = Field(min_length=1, max_length=1_000)


class CitationOut(BaseModel):
    """Enough to open the passage. A citation a reader cannot follow is
    decoration — `chunk_id` is what the document viewer needs, and the label and
    page are what makes it recognisable before they click."""

    chunk_id: str
    document_id: str
    source_label: str | None
    source_page: int | None


class AskOut(BaseModel):
    """One shape for both outcomes, because the client must not have to branch
    on an HTTP status to know whether it got an answer.

    `answered` false carries `sentence` and no prose; `answered` true carries
    prose and at least one citation. `reason` is the machine-readable name and
    `sentence` is the copy **we** wrote — the model never words its own refusal
    (`doc/20` §5 Q7.2).
    """

    answered: bool
    prose: str = ""
    citations: list[CitationOut] = Field(default_factory=list)
    reason: str | None = None
    sentence: str | None = None


RESPONSES: dict[int | str, dict[str, object]] = {
    429: {
        "description": (
            "Too many questions in the window. Carries `Retry-After` so a client "
            "can back off politely rather than guessing."
        )
    },
    404: {
        "description": (
            "The department does not exist, the caller does not hold it, or the "
            "assistant is not enabled. **Deliberately indistinguishable** — "
            "'this exists and you may not have it' is itself a disclosure."
        )
    },
}


@router.post(
    "/{department}/ask",
    response_model=AskOut,
    status_code=status.HTTP_200_OK,
    summary="Ask this director a question about the workspace's own documents",
    dependencies=[Depends(require_csrf)],
    responses=RESPONSES,
)
async def ask_director(
    body: AskIn,
    director: ReachableDirector,
    scope: CurrentScope,
    settings: Annotated[Settings, Depends(get_settings)],
) -> AskOut:
    """Answer from passages this caller may read, or refuse saying why.

    **404 when the flag is off**, not 403 and not 501. The existence of an
    unreleased endpoint is information, and a caller probing for it learns
    nothing they could not have learned by guessing a department name — which
    is the same answer `reachable_director` already gives.

    **No `_require_model()` gate**, following `narrate_block`'s reasoning
    exactly: with no key, the composition returns `MODEL_UNAVAILABLE`, the row
    is written, and the panel says so. A 503 would turn a documented
    configuration (ADR 0011) into an outage.

    **A refusal is a 200.** It is an outcome, not an error: the reader gets a
    sentence we wrote, and a 4xx would push the client into an error path and
    tempt it to render wording of its own.

    **The rate limit is the exception to that, and it is a 429.** It is not a
    statement about the workspace's documents, it is a statement about this
    caller's pace, and the `Retry-After` header is the part a client acts on —
    wrapping it in a 200 refusal bubble would throw that away. `scan.py` renders
    `RateLimitedError` the same way, and this route reached production as a
    **500** until an end-to-end run hit the limit: `ask` raises, and nothing
    here caught it.
    """
    if not settings.assistant_enabled:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")

    # `scoped_connection` is what sets `nexus.workspace_id`, and every RLS
    # policy the composition touches — `chunk`, `generation`,
    # `generation_citation` — reads it. Without it `nexus_app` is `NOBYPASSRLS`
    # and the retrieval returns **zero rows rather than an error**, which would
    # surface as a permanent, plausible "nothing in your documents covers that".
    try:
        async with scoped_connection(scope) as db:
            result = await ask(
                db,
                scope,
                Question(text=body.question, department=director.department),
                provider=get_provider(),
                settings=settings,
                disabled_skills=settings.disabled_ai_skills_set,
            )
            await db.commit()
    except RateLimitedError as exc:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Too many questions right now — try again shortly.",
            headers={"Retry-After": str(exc.retry_after_seconds)},
        ) from exc

    if isinstance(result, AssistantAnswer):
        return AskOut(
            answered=True,
            prose=result.prose,
            citations=[
                CitationOut(
                    chunk_id=str(c.chunk_id),
                    document_id=str(c.document_id),
                    source_label=c.source_label,
                    source_page=c.source_page,
                )
                for c in result.citations
            ],
        )

    return AskOut(answered=False, reason=result.reason.value, sentence=result.sentence)
