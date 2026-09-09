"""`narrate` — the one path from a capability to a sentence, driven end to end.

`doc/13` step B. The pieces have their own tests: eleven evals cover the
pipeline's ordering, `test_grounding_ledger_db` covers the row and the budget.
This covers the **seam** — that a real capability id, a real context, a real
skill and a real ledger row compose into one call, and that the guard fires
through the whole composition rather than only when `run` is called directly.

Driven with `ScriptedProvider`, so it runs with no API key. That is a supported
state rather than a degraded one (ADR 0011), and it is what lets the narration
path be tested at all — an unscripted skill raises instead of improvising, so a
test here can never pass against invented output.

The two model-facing assertions are the ones worth having:

- **an invented number is refused through the composition**, not just in the
  unit, and the refusal is still recorded; and
- **the runner is asked for one attempt**, because the pipeline owns the retry.
  Four provider calls where P14 specifies two is the defect this proves absent.
"""

from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

import pytest

from app.ai.providers import ScriptedProvider
from app.ai.runtime.runner import SkillRunner
from app.config import get_settings
from app.domain.reporting import ReportingSettings
from app.domain.scopes import Department, Role
from app.domain.session import ScopedSession
from app.grounding.answer import NARRATOR, narrate
from app.grounding.context import CompanyContext, Fact
from app.grounding.pipeline import Computed, Outcome, UnavailableReason

CAPABILITY = "finance.runway_alert"
"""Real, because `narrate` resolves it through the registry. It consumes
`runway_alert_months`, which is what makes the snapshot assertion meaningful."""

WORKSPACE = uuid4()
USER = uuid4()


def _scope() -> ScopedSession:
    return ScopedSession(
        user_id=USER,
        tenant_id=uuid4(),
        workspace_id=WORKSPACE,
        role=Role.OWNER,
        departments=frozenset({Department.FINANCE}),
    )


def _context() -> CompanyContext:
    return CompanyContext(
        workspace_id=WORKSPACE,
        company_name="Nakhla Trading",
        currency="OMR",
        reporting=ReportingSettings(),
        department_facts={
            "finance": (
                Fact(
                    key="runway_alert_months",
                    value="6",
                    source_ref="onboarding_answer:finance:runway_alert_months",
                    source_kind="user_confirmed",
                ),
            )
        },
        scope_key="L3:finance",
    )


def _runner(sentence: str, because: str = "") -> SkillRunner:
    return SkillRunner(
        ScriptedProvider({NARRATOR: json.dumps({"sentence": sentence, "because": because})})
    )


class _Recorder:
    """Stands in for the database, and records exactly what would be written.

    The row itself is proved against Neon in `test_grounding_ledger_db`. What
    this needs is the *arguments*, which is a different assertion: that the
    snapshot names the facts the capability declares, that the trace is the
    calculator's own, and that a refusal is recorded rather than swallowed.
    """

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def record(self, _db: object, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        return uuid4()

    async def budgets_for(self, _db: object, **_kwargs: Any) -> Any:
        from app.grounding.pipeline import Budgets

        return Budgets(tenant_spent=0, tenant_limit=1_000_000, user_spent=0, user_limit=100_000)


@pytest.fixture
def recorder(monkeypatch: pytest.MonkeyPatch) -> _Recorder:
    """Patches the ledger module `answer` imported, not a global.

    `answer.py` does `from app.grounding import ledger` and calls
    `ledger.record`, so patching attributes on that module is patching the same
    object the code under test reaches. Patching a re-exported name would leave
    the real one running and this test asserting against a recorder nothing
    wrote to.
    """
    stub = _Recorder()
    from app.grounding import ledger

    monkeypatch.setattr(ledger, "record", stub.record)
    monkeypatch.setattr(ledger, "budgets_for", stub.budgets_for)
    return stub


TRACE = {
    "method": "cash on hand / mean monthly burn",
    "window": "1 Jul - 31 Jul",
    "delta": "unchanged",
}


async def test_a_narrated_figure_records_the_facts_it_was_grounded_in(
    recorder: _Recorder,
) -> None:
    """The whole seam, and P14's acceptance seen from the narration end.

    The sentence carries no numeral — the tile already shows the figure, and the
    skill's contract is that it says what the figure *means*. What proves the
    grounding is the snapshot: it names the fact the capability declares it
    consumes, and the source that fact came from.
    """
    result = await narrate(
        db=None,  # type: ignore[arg-type]
        scope=_scope(),
        capability_id=CAPABILITY,
        context=_context(),
        computed=Computed(values={"runway_months": 7.4}),
        trace=TRACE,
        runner=_runner("Cash runway is unchanged since last month."),
        settings=get_settings(),
    )

    assert result.answered
    assert result.answer.outcome is Outcome.ANSWERED
    assert "unchanged" in result.answer.prose

    written = recorder.calls[-1]
    assert written["module"] == CAPABILITY
    assert written["calculation_trace"] == TRACE, "the calculator's own working, not a retelling"
    assert written["scope_key"] == "L3:finance"
    assert written["input_snapshot"]["facts"] == [
        {
            "key": "runway_alert_months",
            "value": "6",
            "source": "onboarding_answer:finance:runway_alert_months",
        }
    ]
    assert written["input_snapshot"]["missing_facts"] == []

    # What the provider reported, accumulated rather than estimated. `input` is
    # zero here and that is correct: the narrator passes the figure as
    # **grounding** rather than as a message — the system block, not a user turn
    # — and `ScriptedProvider` sizes its input from message length alone. The
    # output side is real, so it is the half that proves the wiring.
    assert written["output_tokens"] > 0


async def test_an_invented_number_is_refused_through_the_whole_composition(
    recorder: _Recorder,
) -> None:
    """I1's teeth, fired through `narrate` rather than through `run` directly.

    The scripted model says a figure no calculation produced. Both attempts say
    it, so the answer is rejected — and the refusal is **recorded**, because a
    tile that says it could not compute something with no row behind it is the
    unfalsifiable support conversation the ledger exists to end.
    """
    result = await narrate(
        db=None,  # type: ignore[arg-type]
        scope=_scope(),
        capability_id=CAPABILITY,
        context=_context(),
        computed=Computed(values={"runway_months": 7.4}),
        trace=TRACE,
        runner=_runner("Runway is 9 months, down sharply."),
        settings=get_settings(),
    )

    assert not result.answered
    assert result.answer.reason is UnavailableReason.INVENTED_NUMBER
    assert result.answer.retried, "rejected only after a second attempt said it again"

    written = recorder.calls[-1]
    assert written["answer"].reason is UnavailableReason.INVENTED_NUMBER
    assert written["output_tokens"] > 0, (
        "two attempts were paid for, and the ledger has to show it — a refusal"
        " that reports zero tokens hides what the guard cost"
    )


async def test_the_pipeline_owns_the_retry_so_the_provider_is_called_twice_not_four_times(
    recorder: _Recorder,
) -> None:
    """The composition defect, asserted as a count.

    The runner retries on a schema failure and the pipeline retries on an
    invented number. At their defaults that is four provider calls for one tile,
    and the second pair looks identical to the first in the log. `narrate` passes
    `attempts=1`, so the retry budget stays where the interesting failure is.
    """
    provider = ScriptedProvider(
        {NARRATOR: json.dumps({"sentence": "Runway is 9 months.", "because": ""})}
    )

    await narrate(
        db=None,  # type: ignore[arg-type]
        scope=_scope(),
        capability_id=CAPABILITY,
        context=_context(),
        computed=Computed(values={"runway_months": 7.4}),
        trace=TRACE,
        runner=SkillRunner(provider),
        settings=get_settings(),
    )

    assert len(provider.calls) == 2, (
        f"P14 specifies two model calls; the provider saw {len(provider.calls)}"
    )


async def test_a_missing_fact_is_named_and_no_model_is_reached(
    recorder: _Recorder,
) -> None:
    """A blank tile tells a founder nothing. *"We need your runway threshold"*
    tells them what to do — and asking a model to narrate a number nobody has is
    how invented figures get invited in, so the provider is never called."""
    provider = ScriptedProvider({NARRATOR: json.dumps({"sentence": "anything"})})

    result = await narrate(
        db=None,  # type: ignore[arg-type]
        scope=_scope(),
        capability_id=CAPABILITY,
        context=_context(),
        computed=Computed(values={}, missing=("runway_alert_months",)),
        trace=TRACE,
        runner=SkillRunner(provider),
        settings=get_settings(),
    )

    assert result.answer.reason is UnavailableReason.MISSING_INPUT
    assert result.answer.missing == ("runway_alert_months",)
    assert provider.calls == [], "nothing was spent on a calculation that could not run"
    assert recorder.calls, "and the refusal is still recorded"


async def test_an_unknown_capability_raises_rather_than_narrating_nothing(
    recorder: _Recorder,
) -> None:
    """A capability id that does not resolve means a caller typed one, and the
    registry's whole purpose is that they cannot. Rendering it as a tile state
    would hide the typo behind a sentence about the customer's data."""
    with pytest.raises(KeyError):
        await narrate(
            db=None,  # type: ignore[arg-type]
            scope=_scope(),
            capability_id="finance.a_tile_nobody_declared",
            context=_context(),
            computed=Computed(values={"x": 1.0}),
            trace=TRACE,
            runner=_runner("Anything."),
            settings=get_settings(),
        )
