"""`POST /assistant/ask`. The global, metric-aware assistant. ADR 0086.

The company-wide counterpart to `POST /dashboards/{department}/ask`: that one
answers from a department's uploaded **documents** with chunk citations; this one
answers from the whole workspace's **computed figures, measured insights and
stated facts**, with provenance in the generation row's trace (a computed metric
has no chunk to cite — ADR 0057). The composition is `grounding/qa.py`, which may
read calculators and the insight store; this route only gates and scopes it.

Shipped **dark**: 404 while `assistant_enabled` is off, exactly as the
per-department endpoint — the existence of an unreleased endpoint is itself
information, so it 404s rather than 403s. Turning it on is the A12 decision with
its eval preconditions (`doc/20` §5 Q7); nothing here flips it.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.ai.registry import get_provider
from app.auth.csrf import require_csrf
from app.config import Settings, get_settings
from app.deps import CurrentScope
from app.grounding import qa
from app.retrieval.scoped import scoped_connection

router = APIRouter(prefix="/assistant", tags=["assistant"])


class GlobalAskIn(BaseModel):
    question: str = Field(min_length=1, max_length=2_000)


class GlobalAskOut(BaseModel):
    """One shape for both outcomes, so the client never branches on HTTP status to
    know whether it got an answer. `answered` false carries the refusal
    `sentence` **we** wrote — the model never words its own refusal. `grounded_on`
    names what the answer was built from; there are no chunk citations, because a
    computed figure is not a document."""

    answered: bool
    prose: str = ""
    sentence: str | None = None
    grounded_on: list[str] = []


RESPONSES: dict[int | str, dict[str, object]] = {
    404: {
        "description": (
            "The assistant is not enabled for this deployment. Deliberately a 404: "
            "an unreleased endpoint's existence is itself a disclosure."
        )
    },
}


@router.post(
    "/ask",
    response_model=GlobalAskOut,
    status_code=status.HTTP_200_OK,
    summary="Ask a question about the workspace's own figures, insights and facts",
    dependencies=[Depends(require_csrf)],
    responses=RESPONSES,
)
async def ask_global(
    body: GlobalAskIn,
    scope: CurrentScope,
    settings: Annotated[Settings, Depends(get_settings)],
) -> GlobalAskOut:
    """Answer from this workspace's own figures, or refuse saying why.

    **404 when the flag is off** (not 403, not 501) — the per-department rule,
    for the per-department reason. **No `_require_model()` gate**: with no key the
    composition records `MODEL_UNAVAILABLE` and the widget says so; a 503 would
    turn a documented configuration (ADR 0011) into an outage. **A refusal is a
    200** — an outcome with copy we wrote, not an error the client should style
    itself.
    """
    if not settings.assistant_enabled:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")

    # `scoped_connection` sets `nexus.workspace_id`; every RLS policy the
    # composition reads — `workspace_insight`, `company_brain`, `page_signals`,
    # `generation` — depends on it, and `nexus_app` is NOBYPASSRLS, so without it
    # the reads return zero rows rather than erroring.
    async with scoped_connection(scope) as db:
        result = await qa.answer(
            db,
            scope,
            body.question,
            provider=get_provider(),
            settings=settings,
            disabled_skills=settings.disabled_ai_skills_set,
        )
        await db.commit()

    return GlobalAskOut(
        answered=result.answered,
        prose=result.prose,
        sentence=result.sentence or None,
        grounded_on=list(result.grounded_on),
    )
