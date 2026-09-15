"""A rejected question must be re-asked **with the rejection in front of it**.

## The defect this file exists for

`onboarding_commands.generate_questions` returns `{"rejected": True, "reason":
...}` when the model writes a compound question, names an undeclared field, or
returns nothing. Its docstring promises the model "is asked again with the
failure in front of it".

**It was not.** `OnboardingAgent._next_question` did:

    if result.get("rejected"):
        rejections += 1
        continue

and re-ran the command with identical arguments. Same conversation, same known
answers, same prompt — so the model produced **the same question**, and was
rejected for the same reason, `MAX_REJECTIONS` times.

Observed in a browser against the real provider: eight `question-generation`
calls in 37 seconds, every one returning

    "When you land in the system, what should show first — the government
     contract pipeline, the repair turnaround metrics, or something else?"

and every one refused as compound. Thirty-seven seconds is past the BFF's
thirty-second timeout, so the founder was told **"Cannot reach the onboarding
service right now"** — which was false. The service was reachable and working
the whole time; it was looping.

So there are three separate failures here and this file covers the first two:
the retry carried no feedback, and the loop was long enough to blow the
request budget. The third — a timeout message that misdiagnoses a slow
success as an unreachable service — is asserted in
`tests/test_onboarding_timeout_copy.py`.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, ClassVar
from uuid import uuid4

import pytest

from app.domain.onboarding_agent import MAX_REJECTIONS, OnboardingAgent
from app.domain.onboarding_sessions import Phase


class _Commands:
    """Records every call, and answers `generate-questions` from a script.

    The assertion surface is `calls` — what the agent *asked for* on each
    attempt. That is where this defect lived: the answers were fine, the
    questions the agent asked were identical.
    """

    def __init__(self, script: list[Mapping[str, Any]]) -> None:
        self._script = list(script)
        self.calls: list[dict[str, Any]] = []

    async def run(self, name: str, ctx: object, **kwargs: Any) -> Mapping[str, Any]:
        self.calls.append({"name": name, **kwargs})
        if name != "generate-questions":
            return {}
        if not self._script:
            raise AssertionError(
                f"the agent called generate-questions {len(self.calls)} times; "
                f"the script has run out. An unbounded retry is the defect."
            )
        return self._script.pop(0)


class _Ctx:
    """Only what `next_question` reads: the grounding the fallback picks a
    department from. Everything else on a real `CommandContext` belongs to the
    commands, which are stubbed."""

    grounding: ClassVar[dict[str, Any]] = {"user_context": {"department": "marketing"}}


def _agent(script: list[Mapping[str, Any]]) -> tuple[OnboardingAgent, _Commands]:
    commands = _Commands(script)
    agent = OnboardingAgent.__new__(OnboardingAgent)
    agent._ctx = _Ctx()  # type: ignore[attr-defined]
    agent._commands = commands  # type: ignore[attr-defined]
    return agent, commands


def _state() -> Any:
    from app.domain.onboarding_agent import AgentState

    return AgentState(
        workspace_id=uuid4(),
        session_id=uuid4(),
        domain="muscat-marine.om",
        company_name="Muscat Marine Services",
        phase=Phase.DISCOVERY,
    )


REJECTED_COMPOUND = {
    "done": False,
    "rejected": True,
    "reason": (
        "that asks more than one thing — ask a single question in under "
        "twenty words, and leave the rest for a later turn"
    ),
}

ACCEPTED = {
    "done": False,
    "question": "What counts as a lead worth passing to Sales?",
    "target": "fact.marketing.lead_definition",
    "scope": 3,
    "skill": "question-generation",
    "skill_version": "6",
}


@pytest.mark.asyncio
async def test_a_rejected_question_is_re_asked_with_the_reason_attached() -> None:
    """**The assertion the defect would have failed.**

    Attempt two must differ from attempt one by carrying what was refused.
    Without it the model sees an identical prompt and returns an identical
    question, which is not a retry — it is the same call made twice.
    """
    agent, commands = _agent([REJECTED_COMPOUND, ACCEPTED])

    await agent.next_question(_state())

    asked = [c for c in commands.calls if c["name"] == "generate-questions"]
    assert len(asked) == 2, "the rejection should have produced exactly one retry"

    first, second = asked
    assert not first.get("rejections"), "nothing was refused before the first attempt"
    assert second.get("rejections"), (
        "the second attempt carried no record of the first being refused, so the "
        "model sees an identical prompt and returns an identical question — which "
        "is the whole defect"
    )
    assert "more than one thing" in str(second["rejections"]), (
        "the retry must carry the *reason*, not merely a count — a count tells "
        "the model it failed without telling it what to do differently"
    )


@pytest.mark.asyncio
async def test_every_rejection_so_far_is_carried_not_just_the_last() -> None:
    """Three strikes, and the model should see all three.

    Carrying only the most recent reason lets the model alternate between two
    faults for ever: compound, then undeclared, then compound again, each
    looking novel to a prompt with a one-item memory.
    """
    agent, commands = _agent(
        [
            REJECTED_COMPOUND,
            {"done": False, "rejected": True, "reason": "'fact.finance.runway' was not offered"},
            ACCEPTED,
        ]
    )

    await agent.next_question(_state())

    asked = [c for c in commands.calls if c["name"] == "generate-questions"]
    assert len(asked) == 3
    carried = str(asked[2]["rejections"])
    assert "more than one thing" in carried
    assert "was not offered" in carried


@pytest.mark.asyncio
async def test_the_retry_budget_is_small_enough_to_answer_inside_a_request() -> None:
    """**The second half of the defect: the loop was too long to survive.**

    `MAX_REJECTIONS` was 8. Each `question-generation` call against the real
    provider took 4.2 to 4.9 seconds, so a fully-rejected turn spent **37
    seconds** before serving its fallback — past the BFF's thirty-second abort,
    which is why the founder saw an error while the API was still working.

    The budget has to leave room for the rest of the request (storing the
    answer, the classifier, the round trips to `us-east-2`) inside that same
    thirty seconds. Asserted as arithmetic rather than as a number, so the
    reason survives somebody raising it.
    """
    slowest_call_seconds = 5.0
    budget_seconds = 30.0
    room_for_the_rest_of_the_request = 10.0

    assert MAX_REJECTIONS * slowest_call_seconds <= (
        budget_seconds - room_for_the_rest_of_the_request
    ), (
        f"MAX_REJECTIONS={MAX_REJECTIONS} can spend "
        f"{MAX_REJECTIONS * slowest_call_seconds:.0f}s on question generation alone, "
        f"which does not fit inside the {budget_seconds:.0f}s request budget. A founder "
        f"then sees a timeout while the service is working normally."
    )


@pytest.mark.asyncio
async def test_the_loop_stops_at_the_budget_and_serves_the_fallback() -> None:
    """Exhaustion is still an outcome, not a hang.

    The fallback is hand-written and cannot be rejected by the gates that got
    us here, which is what makes this terminate rather than recurse.
    """
    agent, commands = _agent([REJECTED_COMPOUND] * MAX_REJECTIONS)
    state = _state()

    result = await agent.next_question(state)

    asked = [c for c in commands.calls if c["name"] == "generate-questions"]
    assert len(asked) == MAX_REJECTIONS, "the loop ran past its own budget"
    assert result.get("question"), "exhaustion must still produce a question"
    assert result.get("skill") == "fallback"


@pytest.mark.asyncio
async def test_an_accepted_question_never_mentions_a_rejection() -> None:
    """The happy path pays nothing for the retry machinery — no extra key in
    the grounding, no second call."""
    agent, commands = _agent([ACCEPTED])

    result = await agent.next_question(_state())

    asked = [c for c in commands.calls if c["name"] == "generate-questions"]
    assert len(asked) == 1
    assert not asked[0].get("rejections")
    assert result["question"] == ACCEPTED["question"]
