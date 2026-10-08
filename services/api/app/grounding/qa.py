"""The global assistant: one question, answered from this workspace's own figures.

ADR 0086. The metric-aware half of the Nexus Assistant, and the counterpart to
`app/assistant/ask.py` — which answers from uploaded **documents** with chunk
citations. This one answers from **computed figures, measured insights and
stated facts**, and its provenance is the `generation` row's trace, not a
`generation_citation` (a computed metric has no document chunk to cite, and that
table is FK-bound to real chunks — ADR 0057). It is the narration pattern
(`app/grounding/answer.py`) widened from one figure to a bundle and from a fixed
tile to a free-text question.

**I1 is kept exactly as narration keeps it.** The numbers come from
`calculators/` and the insight store — never from the model. `pipeline.run`
rejects any numeral in the prose that was not in the grounding, retrying once and
then refusing the whole answer. The model phrases; it does not compute.

This lives in `app/grounding/` (not `app/assistant/`, which the boundary test
forbids from importing calculators) precisely because assembling the figure
bundle *does* read `calculators/` and the insight store.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any, Final

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.contracts import LlmTransientError, LlmUnavailableError, Message
from app.ai.runtime.runner import SkillFailedError, SkillRunner
from app.domain import company_brain
from app.domain.insights import StoredInsight
from app.domain.registry import BY_ID
from app.domain.session import ScopedSession
from app.grounding.compute import (
    COMPOSITIONS,
    MEASURABLE,
    compute_from_crawl,
    compute_from_deals,
    compute_from_ops,
    compute_rate_from_ops,
    computes,
)
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
from app.retrieval.crawl import current_page_signals
from app.retrieval.deals import DealSnapshot, both_populations
from app.retrieval.insights import current_insights
from app.retrieval.ops import current_ops

SKILL: Final = "assistant-global"
MODULE: Final = "grounding.qa"
MAX_QUESTION_CHARS: Final = 2000

_log = get_logger(__name__)

_SENTENCES: Final[dict[UnavailableReason, str]] = {
    UnavailableReason.NO_PASSAGE: (
        "There are no figures, insights or facts about this workspace yet that would answer "
        "that. Connect a tool or finish setup, and ask again once there is something measured."
    ),
    UnavailableReason.INVENTED_NUMBER: (
        "We discarded the answer because it stated a figure that none of your data supplied. "
        "That is the check working, and it is ours rather than anything about your figures."
    ),
    UnavailableReason.SCHEMA_INVALID: (
        "The answer came back in a shape we could not read, twice. That is ours to fix, and "
        "nothing half-formed was shown to you."
    ),
    UnavailableReason.MODEL_UNAVAILABLE: (
        "The language model is not configured for this deployment, so there is nothing to write "
        "the answer. Your figures were not the problem."
    ),
    UnavailableReason.BUDGET_EXHAUSTED: (
        "This workspace has used its allowance of questions for today. It resets at midnight in "
        "your own reporting timezone."
    ),
    UnavailableReason.SKILL_DISABLED: (
        "The assistant has been switched off for this workspace. That is somebody's choice rather "
        "than a fault, and whoever administers the workspace can turn it back on."
    ),
    UnavailableReason.PROVIDER_FAILED: (
        "The language model did not respond. Nothing was lost — asking again is worth doing."
    ),
}


class QuestionTooLargeError(ValueError):
    """The question is longer than the ceiling. A request-shaped refusal, raised
    before anything is assembled or any model is called."""


@dataclass(frozen=True, slots=True)
class QaAnswer:
    answered: bool
    """True with prose, or False with a refusal sentence."""
    prose: str
    sentence: str
    """The refusal copy when `answered` is False; empty when answered."""
    grounded_on: tuple[str, ...]
    """The labels of the figures/insights/facts assembled for this answer — what
    a reviewer sees as the provenance, since there are no chunk citations."""


def _sentence(reason: UnavailableReason) -> str:
    return _SENTENCES.get(reason, _SENTENCES[UnavailableReason.SCHEMA_INVALID])


def _insight_line(insight: StoredInsight) -> tuple[str, float | None, str]:
    """A readable line for one insight, plus its numeric value for `Computed`.

    Returns (label, value_or_none, line). `value_or_none` feeds the permitted-set;
    the line is what the model reads."""
    if insight.value_numeric is not None:
        value = float(insight.value_numeric)
        shown = f"{value:g}" + (f" {insight.unit}" if insight.unit else "")
    else:
        value = None
        shown = insight.value_text or ""
    captured = insight.captured_at.date().isoformat()
    label = f"{insight.source}/{insight.metric_key}"
    line = f"- {label}: {shown} (measured by {insight.provenance} on {captured})"
    return label, value, line


def _figure_for(
    capability_id: str,
    *,
    crawl: Any,
    synced: DealSnapshot | None,
    typed: DealSnapshot | None,
    ops: Any,
    today: date,
) -> Any | None:
    """The one computation for a capability, whatever its kind — or `None`.

    Tries each `grounding/compute` dispatch and takes the first that answers, the
    same `or` chain the surface's tile uses. Every kind it returns carries the
    same `(computed, label)` pair, so the bundle folds them identically. The
    compute functions are keyed by their own registries and return `None` for a
    capability that is not theirs, so trying all of them is safe.

    Compositions (`operations.score_drivers`, `executive.todays_priorities`) are
    excluded by the caller: they explain or rank other figures rather than
    carrying a headline number, so there is nothing for the guard to permit."""
    if crawl is not None:
        crawl_figure = compute_from_crawl(capability_id, crawl)
        if crawl_figure is not None:
            return crawl_figure

    # `sales.deals_lite` reads the deals somebody typed; every other deal figure
    # reads what a provider synced. The partition is ADR 0038's and must not blur.
    population = typed if capability_id == "sales.deals_lite" else synced
    if population is not None:
        amount = compute_from_deals(
            capability_id,
            population.deals,
            today=today,
            source=population.provider,
            fetched_at=population.fetched_at,
        )
        if amount is not None:
            return amount

    if ops is not None:
        count = compute_from_ops(capability_id, ops, today=today)
        if count is not None:
            return count
        rate = compute_rate_from_ops(capability_id, ops, today=today)
        # A refused rate has no percentage to state (nothing priced, not
        # confirmed) — skip it rather than ground on a number that is not shown.
        if rate is not None and rate.refused is None:
            return rate

    return None


def _assemble(
    scope: ScopedSession,
    insights: tuple[StoredInsight, ...],
    brain: Any,
    crawl: Any,
    synced: DealSnapshot | None,
    typed: DealSnapshot | None,
    ops: Any,
    *,
    today: date,
) -> tuple[Computed, list[str], list[str]]:
    """Build the permitted figure set, the readable grounding lines, and the
    labels of everything assembled. No model, no numbers of our own — every value
    came from the insight store or a calculator (I1)."""
    values: dict[str, float] = {}
    lines: list[str] = []
    labels: list[str] = []

    for insight in insights:
        label, value, line = _insight_line(insight)
        lines.append(line)
        labels.append(label)
        if value is not None:
            values[label] = value

    # Computed figures — crawl audit, CRM pipeline, operations counts and rates.
    # Scoped to the departments this caller may reach, the same filter the
    # dashboard applies to its tiles, so the assistant never grounds on a figure
    # the reader could not see on their own dashboard.
    for capability_id in sorted(MEASURABLE):
        if not computes(capability_id) or capability_id in COMPOSITIONS:
            continue
        capability = BY_ID.get(capability_id)
        if capability is None or not scope.may_reach_department(capability.department):
            continue
        figure = _figure_for(
            capability_id, crawl=crawl, synced=synced, typed=typed, ops=ops, today=today
        )
        if figure is None or not figure.computed.values:
            continue
        labels.append(capability_id)
        for key, value in figure.computed.values.items():
            values[f"{capability_id}.{key}"] = value
        rendered = ", ".join(
            f"{key.replace('_', ' ')} {amount:g}" for key, amount in figure.computed.values.items()
        )
        lines.append(f"- {figure.label}: {rendered}")

    if brain is not None:
        for name, field in (
            ("what you sell", brain.products_services),
            ("your customers", brain.target_customers),
            ("your goals", brain.goals),
            ("profile", brain.profile),
        ):
            if field:
                lines.append(f"- You told us ({name}): {field}")
        labels.append("company_brain")

    return Computed(values=values), lines, labels


async def answer(
    db: AsyncSession,
    scope: ScopedSession,
    question_text: str,
    *,
    provider: Any,
    settings: Any,
    disabled_skills: frozenset[str] = frozenset(),
    timezone: str = "UTC",
) -> QaAnswer:
    """Answer `question_text` from this workspace's figures, insights and facts.

    Takes a `ScopedSession` and no identifiers (I2). Every read below is scoped;
    nothing here can see another workspace's data, and the model only ever sees
    what the caller could.
    """
    text = question_text.strip()
    if not text or len(text) > MAX_QUESTION_CHARS:
        raise QuestionTooLargeError(f"question is {len(text)} chars (max {MAX_QUESTION_CHARS})")

    insights = tuple(await current_insights(db, scope))
    brain = await company_brain.current(db, workspace_id=scope.workspace_id)
    crawl = await current_page_signals(db, scope)
    synced, typed = await both_populations(db, scope)
    ops = await current_ops(db, scope)
    today = datetime.now(UTC).date()

    computed, lines, labels = _assemble(
        scope, insights, brain, crawl, synced, typed, ops, today=today
    )

    if not lines:
        # Nothing to ground on. Refuse before a model is called — an answer
        # produced from an empty bundle is an answer produced from memory.
        return QaAnswer(
            answered=False,
            prose="",
            sentence=_sentence(UnavailableReason.NO_PASSAGE),
            grounded_on=(),
        )

    block = "Figures, insights and facts about this workspace:\n" + "\n".join(lines)
    budgets = await budgets_for(
        db,
        workspace_id=scope.workspace_id,
        user_id=scope.user_id,
        settings=settings,
        timezone=timezone,
    )
    runner = SkillRunner(provider=provider)
    tokens = {"in": 0, "out": 0}
    output: dict[str, Any] = {}

    async def call_model(_: Computed) -> str:
        result = await runner.invoke(
            SKILL,
            messages=[Message(role="user", content=f"{block}\n\nQuestion: {text}")],
            grounding={"question": text},
            attempts=1,
        )
        payload = dict(result.data)
        output.update(payload)
        tokens["in"] = result.completion.usage.input_tokens
        tokens["out"] = result.completion.usage.output_tokens
        if not payload.get("answered"):
            # A valid, complete "no" — empty prose. Carries no numerals, so the
            # guard has nothing to reject; `answer` below turns it into a refusal.
            return ""
        return str(payload.get("answer", ""))

    try:
        result = await run(
            skill=SKILL,
            computed=computed,
            call_model=call_model,
            budgets=budgets,
            disabled_skills=disabled_skills,
            # The grounding we put in front of the model: the figure values plus
            # every numeral in the readable block (brain facts, insight dates and
            # units). Nothing parsed back out of the model's own answer.
            also_permitted=numerals_supplied(block),
        )
    except LlmUnavailableError:
        return _refuse(UnavailableReason.MODEL_UNAVAILABLE, labels)
    except LlmTransientError:
        return _refuse(UnavailableReason.PROVIDER_FAILED, labels)
    except (SkillFailedError, ValueError, KeyError, TypeError):
        return _refuse(UnavailableReason.SCHEMA_INVALID, labels)

    answered = result.outcome is Outcome.ANSWERED and bool(output.get("answered"))
    reason = result.reason

    await _record(db, scope, text, result, labels, tokens, answered=answered)

    if not answered:
        # A parsed "no" is an honest NO_PASSAGE, not a pipeline failure.
        shown = reason if reason is not None else UnavailableReason.NO_PASSAGE
        return QaAnswer(answered=False, prose="", sentence=_sentence(shown), grounded_on=())

    return QaAnswer(answered=True, prose=result.prose, sentence="", grounded_on=tuple(labels))


def _refuse(reason: UnavailableReason, labels: list[str]) -> QaAnswer:
    return QaAnswer(answered=False, prose="", sentence=_sentence(reason), grounded_on=())


async def _record(
    db: AsyncSession,
    scope: ScopedSession,
    question: str,
    result: Answer,
    labels: list[str],
    tokens: dict[str, int],
    *,
    answered: bool,
) -> None:
    """Write the generation row this answer traces to. Provenance is the trace —
    the labels of what was assembled — not a chunk citation."""
    await record(
        db,
        workspace_id=scope.workspace_id,
        module=MODULE,
        prompt_version="1",
        answer=result,
        input_snapshot={"question": question, "grounded_on": labels},
        calculation_trace={"grounded_on": labels, "answered": answered},
        scope_key="L2",
        input_tokens=tokens["in"],
        output_tokens=tokens["out"],
        requested_by_user_id=scope.user_id,
    )
