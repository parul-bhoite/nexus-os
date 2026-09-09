"""The one path from a capability to a sentence a founder can check.

`doc/12` P14's acceptance test: *"Every number rendered anywhere traces to a
`generation` row naming its inputs and its calculation."* This module is what
makes "anywhere" true — it is the only way to get a narrated figure out of the
system, so a tile cannot acquire one by another route.

    assemble context -> compute (pure) -> guarded model call -> record the row

Each step already existed and none of them were joined. `pipeline.run` was a
pure function nothing called; `context.assemble` had no callers because there
was nothing to assemble for; and `generation` had two indexes, a check
constraint and no rows. This is the seam.

## Why the row is written even when there is no answer

Especially then. *"The tile said it could not compute this"* is a support
conversation, and without a row it is unfalsifiable: a missing input, a schema
failure and an exhausted budget look identical on screen and want three
different responses. The row is written inside the caller's transaction, so the
answer and its provenance are one fact — `audit.record`'s rule, for
`audit.record`'s reason.

## What this module refuses to do

**It does not compute.** `computed` arrives from `calculators/`, which is pure
and contains no model. Adding arithmetic here would make this a second place
numbers come from, and I1 is the claim that there is exactly one.

**It does not decide what a tile renders.** It returns an `Answer` and the id of
the row behind it. Turning that into `LIVE` or `UNAVAILABLE` is `state_for`'s
job, and a function that both produced the prose and chose the state could
disagree with the tile beside it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.contracts import (
    LlmAuthError,
    LlmRequestError,
    LlmTransientError,
    LlmUnavailableError,
)
from app.ai.runtime.runner import SkillFailedError, SkillOutputInvalidError, SkillRunner
from app.config import Settings
from app.domain.registry import BY_ID, Capability
from app.domain.session import ScopedSession
from app.grounding import ledger
from app.grounding.context import CompanyContext
from app.grounding.pipeline import Answer, Computed, Outcome, UnavailableReason, run
from app.logging import get_logger

log = get_logger(__name__)

NARRATOR = "narrate-metric"
"""The skill that phrases a computed figure. Named here rather than passed in:
one narrator means one voice across sixty tiles, and a per-caller narrator is
how two tiles on one page end up written by different hands."""


@dataclass(frozen=True, slots=True)
class Narrated:
    """An answer, and the ledger row it traces to."""

    answer: Answer
    generation_id: UUID

    @property
    def answered(self) -> bool:
        return self.answer.outcome is Outcome.ANSWERED


def _snapshot(
    capability: Capability, context: CompanyContext, computed: Computed
) -> dict[str, Any]:
    """What this answer was made of, in a form somebody can read a year later.

    The facts are recorded **with their sources**, not just their values. A
    snapshot saying `payment_terms: "30 days"` proves what we used; one that
    also says where it came from proves whether we were entitled to use it, and
    the second question is the one an audit asks.
    """
    return {
        "capability": capability.id,
        "company": context.company_name,
        "currency": context.currency,
        "reporting": {
            "fiscal_year_start_month": context.reporting.fiscal_year_start_month,
            "week_start": context.reporting.week_start.value,
            "timezone": context.reporting.timezone,
        },
        "facts": [
            {"key": fact.key, "value": fact.value, "source": fact.source_ref}
            for fact in context.facts_for(capability.consumes_facts)
        ],
        "missing_facts": list(context.missing_facts(capability.consumes_facts)),
        "brain_present": context.brain is not None,
    }


async def narrate(
    db: AsyncSession,
    scope: ScopedSession,
    *,
    capability_id: str,
    context: CompanyContext,
    computed: Computed,
    trace: dict[str, Any],
    runner: SkillRunner,
    settings: Settings,
) -> Narrated:
    """Narrate one computed figure, and record what it was made of.

    `trace` is the calculator's own working — the method, the numerator, the
    denominator, the window. It is passed in rather than reconstructed because
    only the calculator knows it, and a trace assembled here would be a
    plausible account of arithmetic that happened somewhere else. It is what the
    tile's *"+ why this number"* drawer reads.

    Raises `KeyError` for an unknown capability id. Not a soft failure: a
    capability id that does not resolve means a caller has typed one, and the
    registry's whole purpose is that they cannot.
    """
    capability = BY_ID[capability_id]

    budgets = await ledger.budgets_for(
        db,
        workspace_id=scope.workspace_id,
        user_id=scope.user_id,
        settings=settings,
        timezone=context.reporting.timezone,
    )

    tokens = {"input": 0, "output": 0}

    async def call_model(values: Computed) -> str:
        """One skill invocation, and the only place a model is reached.

        `attempts=1`, so the retry budget belongs to the pipeline. The runner
        retries on a schema failure and the pipeline retries on an invented
        number; letting both retry would spend four provider calls where P14
        specifies two, and the second pair would be indistinguishable from the
        first in the log.
        """
        result = await runner.invoke(
            NARRATOR,
            messages=[],
            grounding={
                "label": capability.name,
                "value": values.values,
                "unit": context.currency,
                "window": trace.get("window", ""),
                "sources": [source.value for source in capability.required_sources],
                "delta": trace.get("delta", ""),
            },
            attempts=1,
        )
        tokens["input"] += result.completion.usage.input_tokens
        tokens["output"] += result.completion.usage.output_tokens
        sentence = str(result.data.get("sentence", ""))
        because = str(result.data.get("because", ""))
        return f"{sentence} {because}".strip()

    try:
        answer = await run(
            skill=NARRATOR,
            computed=computed,
            call_model=call_model,
            budgets=budgets,
            disabled_skills=settings.disabled_ai_skills_set,
        )
    except Exception as failure:
        # **The row is written for this too**, which is why the exception is
        # caught here rather than allowed to become a 500. A tile is a place on
        # a screen: it has to say something, and *"could not compute"* with no
        # ledger row behind it is the unfalsifiable support conversation this
        # table exists to end.
        answer = Answer(
            outcome=Outcome.UNAVAILABLE,
            reason=unavailable_for(failure),
            values=computed.values,
        )

    generation_id = await ledger.record(
        db,
        workspace_id=scope.workspace_id,
        module=capability.id,
        prompt_version=runner.registry.get(NARRATOR).version,
        answer=answer,
        input_snapshot=_snapshot(capability, context, computed),
        calculation_trace=trace,
        scope_key=context.scope_key,
        input_tokens=tokens["input"],
        output_tokens=tokens["output"],
        requested_by_user_id=scope.user_id,
    )

    log.info(
        "grounding.narrated",
        capability=capability.id,
        outcome=answer.outcome.value,
        reason=answer.reason.value if answer.reason else "",
        retried=answer.retried,
        generation_id=str(generation_id),
    )
    return Narrated(answer=answer, generation_id=generation_id)


def unavailable_for(error: Exception) -> UnavailableReason:
    """Which named state a failure renders as — or a re-raise, if it is our bug.

    The mapping matters because the reasons are what a founder is shown, and
    three of these want three different responses: wait, connect something, or
    tell us. Collapsing them into one "unavailable" is what the enum exists to
    prevent.

    **`SkillFailedError` is re-raised, deliberately.** It means a caller invoked
    a skill without the grounding it declares — our mistake, not a runtime
    condition — and the runner's own docstring says loud is the whole point.
    Rendering it as a tile state would hide a programming error behind a
    sentence about the customer's data.
    """
    if isinstance(error, SkillOutputInvalidError):
        return UnavailableReason.SCHEMA_INVALID
    if isinstance(error, LlmUnavailableError | LlmAuthError):
        return UnavailableReason.MODEL_UNAVAILABLE
    if isinstance(error, LlmTransientError | LlmRequestError):
        return UnavailableReason.PROVIDER_FAILED
    if isinstance(error, SkillFailedError):
        raise error
    raise error
