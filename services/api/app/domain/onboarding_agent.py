"""The onboarding agent: a plan over commands, not a prompt with tools.

The agent is deliberately *not* a model deciding what to do next. It is a small
state machine whose steps are commands, because the order of onboarding is a
product decision with a database schema behind it — which phase writes the Brain,
which one may promote a draft — and that is not a decision to re-derive on every
request from whatever the model feels like doing.

What the model decides is everything inside a step: what to ask, in what words,
in what order, and when there is nothing left worth asking. That is the split ADR
0019 was reaching for, held in code rather than in a system prompt.

    analysing -> brief -> discovery -> persona -> assembling -> ready

`discovery` is the loop. It runs `generate-questions` until the skill says it is
done or the safety limit trips, and each accepted turn is written with the field
it targeted and the scope that field carries.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from app.ai.runtime.commands import CommandContext, get_commands
from app.ai.runtime.hooks import HookEvent, HookPoint
from app.domain.onboarding_sessions import Phase, TurnRole
from app.logging import get_logger

log = get_logger(__name__)

MAX_QUESTIONS = 14
"""A hard ceiling on the interview, independent of what the model wants.

Not a quality lever — a termination guarantee. Without it a skill that never
returns `done` walks a person through the entire catalogue, and the failure looks
like the product being tedious rather than like a bug.
"""

MAX_REJECTIONS = 3
"""Consecutive undeclared-target rejections before the loop gives up.

A model that cannot name a declared field three times running is not going to on
the fourth, and each attempt costs a call.
"""


@dataclass(slots=True)
class Turn:
    role: str
    text: str
    target_field: str | None = None
    scope: int | None = None
    skill: str | None = None
    skill_version: str | None = None


@dataclass(slots=True)
class AgentState:
    session_id: UUID
    workspace_id: str
    domain: str
    company_name: str
    phase: str = Phase.ANALYSING
    turns: list[Turn] = field(default_factory=list)
    answers: dict[str, str] = field(default_factory=dict)
    research: dict[str, Any] = field(default_factory=dict)
    brief: dict[str, Any] = field(default_factory=dict)
    asked: int = 0

    @property
    def conversation(self) -> list[dict[str, str]]:
        return [{"role": t.role, "text": t.text} for t in self.turns]


class OnboardingAgent:
    """Drives the journey. One instance per request, cheap to build."""

    def __init__(self, ctx: CommandContext) -> None:
        self._ctx = ctx
        self._commands = get_commands()

    async def start(self, state: AgentState, *, pages: Sequence[Mapping[str, str]]) -> AgentState:
        await self._ctx.hooks.emit(
            HookEvent(
                point=HookPoint.ONBOARDING_START,
                workspace_id=state.workspace_id,
                session=self._ctx.session,
                payload={"domain": state.domain, "session_id": str(state.session_id)},
            )
        )
        result = await self._commands.run(
            "research-company",
            self._ctx,
            session_id=state.session_id,
            domain=state.domain,
            pages=pages,
            company_name=state.company_name,
        )
        state.research = dict(result["research"])
        state.brief = dict(result["brief"])
        state.phase = Phase.BRIEF
        opening = str(state.brief.get("opening_line", "")) or (
            f"I have read {state.domain}. Here is what I think I know."
        )
        state.turns.append(Turn(role=TurnRole.AGENT, text=opening, skill="company-summary"))
        return state

    async def confirm_brief(self, state: AgentState, corrections: Mapping[str, str]) -> AgentState:
        """A correction outranks the reading, and is recorded as such.

        Stored into `answers` keyed by the same field the statement targeted, so
        the brain builder sees it at `user_confirmed` precedence and supersedes
        the crawled value rather than sitting beside it.
        """
        for key, value in corrections.items():
            state.answers[key] = value
            state.turns.append(
                Turn(role=TurnRole.USER, text=value, target_field=key, scope=_scope_of(key))
            )
            await self._ctx.hooks.emit(
                HookEvent(
                    point=HookPoint.ANSWER_SUBMITTED,
                    workspace_id=state.workspace_id,
                    session=self._ctx.session,
                    payload={
                        "target": key,
                        "scope": _scope_of(key),
                        "origin": "brief-correction",
                        "actor_user_id": self._ctx.actor_user_id,
                    },
                )
            )
        state.phase = Phase.DISCOVERY
        return state

    async def open_discovery(self, state: AgentState, answer: str) -> Mapping[str, Any]:
        """The one free-text turn, interpreted before anything is stored.

        Everything after this is a targeted question with a declared field. This
        turn is prose, so it needs `user-discovery` to turn it into interests
        that each cite the span that produced them.
        """
        profile = str(state.research.get("profile", {}).get("value", ""))
        result = await self._commands.run(
            "interpret-user",
            self._ctx,
            session_id=state.session_id,
            answer=answer,
            company_profile=profile,
        )
        state.turns.append(
            Turn(role=TurnRole.USER, text=answer, target_field="persona.stated_purpose", scope=5)
        )
        purpose = result.get("stated_purpose", {})
        if isinstance(purpose, dict) and purpose.get("value"):
            state.answers["persona.stated_purpose"] = str(purpose["value"])
        return result

    async def next_question(self, state: AgentState) -> Mapping[str, Any] | None:
        """One turn of the interview, or None when the interview is over.

        Returns None on three distinct conditions — the skill said done, the
        ceiling tripped, or the model could not name a declared field often
        enough. All three end the loop; only the first is a clean finish, and the
        others are logged so a degraded run is visible rather than silent.
        """
        if state.asked >= MAX_QUESTIONS:
            log.info("onboarding.ceiling", workspace_id=state.workspace_id, asked=state.asked)
            state.phase = Phase.PERSONA
            return None

        rejections = 0
        while rejections < MAX_REJECTIONS:
            result = await self._commands.run(
                "generate-questions",
                self._ctx,
                session_id=state.session_id,
                already_known=state.answers,
                conversation=state.conversation,
            )
            if result.get("done"):
                state.phase = Phase.PERSONA
                return None
            if result.get("rejected"):
                rejections += 1
                continue

            state.asked += 1
            state.turns.append(
                Turn(
                    role="agent",
                    text=str(result["question"]),
                    target_field=str(result["target"]),
                    scope=int(result["scope"]),
                    skill=str(result.get("skill", "")),
                    skill_version=str(result.get("skill_version", "")),
                )
            )
            return result

        log.warning("onboarding.rejections_exhausted", workspace_id=state.workspace_id)
        state.phase = Phase.PERSONA
        return None

    async def submit_answer(self, state: AgentState, *, target: str, text: str) -> AgentState:
        """Record an answer against the field the question declared.

        `target` is taken from the *agent's own last turn*, not from the client.
        A client that could name the target could choose the scope its answer is
        stored at, which is the whole thing the catalogue exists to prevent.
        """
        expected = next(
            (t.target_field for t in reversed(state.turns) if t.role == "agent" and t.target_field),
            None,
        )
        if expected is None or expected != target:
            raise ValueError(
                f"answer targets {target!r} but the last question targeted {expected!r}; "
                f"the target is set when the question is asked, not when it is answered"
            )

        scope = _scope_of(target)
        state.answers[target] = text
        state.turns.append(Turn(role=TurnRole.USER, text=text, target_field=target, scope=scope))
        await self._ctx.hooks.emit(
            HookEvent(
                point=HookPoint.ANSWER_SUBMITTED,
                workspace_id=state.workspace_id,
                session=self._ctx.session,
                payload={
                    "target": target,
                    "scope": scope,
                    "origin": "interview",
                    "actor_user_id": self._ctx.actor_user_id,
                },
            )
        )
        return state

    # ── Assembly, one stage per call ──────────────────────────
    #
    # These three were one `finish` method behind one HTTP request: persona,
    # brain and context in a row, three sequential model calls at high, high
    # and medium effort with the brain builder alone allowed 8192 output
    # tokens over a prompt carrying up to twenty crawled pages. Two to four
    # minutes, and — because `scoped_connection` opens a single transaction for
    # the whole request — **nothing durable until all three had finished.**
    #
    # A failure or a killed process at the third call therefore discarded the
    # first two, and the retry paid for them again. That happened: a 503 from
    # the proxy, clicked twice, six model calls, no rows written.
    #
    # Each command already writes its own stage and advances the phase —
    # `persona` then `assembling` then `ready`, which is why those two middle
    # phases exist in the enum. They were simply never committed separately.
    # Splitting the *caller* is the whole fix; the commands did not change.
    #
    # The route runs exactly one of these per request and commits it, choosing
    # which from the phase on the row rather than from anything the client
    # sends — the same rule as `submit_answer`'s target. A client that could
    # name the stage could skip one, and a Brain assembled without its persona
    # is not a shorter journey, it is a different artefact.

    async def build_persona(self, state: AgentState) -> Mapping[str, Any]:
        """Stage one. Writes `persona_draft`, moves the phase to `persona`."""
        profile = str(state.research.get("profile", {}).get("value", ""))
        return await self._commands.run(
            "build-persona",
            self._ctx,
            session_id=state.session_id,
            answers=state.answers,
            company_profile=profile,
        )

    async def build_brain(
        self, state: AgentState, *, deep_research: Mapping[str, Any] | None = None
    ) -> Mapping[str, Any]:
        """Stage two. The expensive one. Moves the phase to `assembling`.

        `state.company_name` has to be real here — the skill declares
        `company_name` in `requires_grounding`. The old single-call path
        rehydrated without it and passed an empty string, so every Brain was
        assembled by a model that had not been told the company's name.
        """
        return await self._commands.run(
            "build-company-brain",
            self._ctx,
            session_id=state.session_id,
            research=state.research,
            answers=state.answers,
            company_name=state.company_name,
            domain=state.domain,
            deep_research=deep_research,
        )

    async def build_context(
        self,
        state: AgentState,
        *,
        brain: Mapping[str, Any],
        persona: Mapping[str, Any],
        role_reach: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        """Stage three. Moves the phase to `ready`.

        `brain` and `persona` are read back off the session row rather than held
        in memory from the earlier stages — that is what makes this callable as
        its own request, and therefore what makes a retry resume here instead of
        starting again.
        """
        context = await self._commands.run(
            "personalize-context",
            self._ctx,
            session_id=state.session_id,
            brain=brain,
            persona=persona,
            role_reach=role_reach,
        )
        state.phase = Phase.READY
        await self._ctx.hooks.emit(
            HookEvent(
                point=HookPoint.ONBOARDING_COMPLETED,
                workspace_id=state.workspace_id,
                session=self._ctx.session,
                payload={
                    "questions_asked": state.asked,
                    "brain_values": len(brain.get("values", [])),
                    "persona_fields": len(persona.get("fields", [])),
                    "still_unavailable": len(brain.get("unavailable", [])),
                },
            )
        )
        return context


def _scope_of(key: str) -> int:
    from app.ai.runtime.fields import resolve

    return resolve(key).scope
