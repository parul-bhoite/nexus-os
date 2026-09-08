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

**The four log keys an operator should care about, and which one to alert on.**
An earlier round asked for alerting on `onboarding.rejections_exhausted`; that
key now fires only when there is nothing left to ask at all, which is a clean
finish. Anyone who wired it got silence for the failure they meant to catch.

- `onboarding.fallback_served` (warning) — **the model failed repeatedly** and
  hand-written wording was used instead. This is the degraded case, and the one
  worth alerting on.
- `onboarding.floor_served` (warning) — the interview was about to end with
  nothing from the person's own department, so one was insisted on.
- `onboarding.ceiling` (info) — the interview ran its full length. Normal.
- `onboarding.rejections_exhausted` (warning) — every field with hand-written
  wording is already answered. Rare, and not a failure.

There is still no counter or metric behind any of these — they are log lines, so
rate has to come from the log backend rather than from the application.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from app.ai.runtime.commands import CommandContext, get_commands
from app.ai.runtime.fields import BRAIN_GROUPS, next_fallback
from app.ai.runtime.hooks import HookEvent, HookPoint
from app.domain.onboarding_sessions import Phase, TurnRole
from app.logging import get_logger

log = get_logger(__name__)

MAX_QUESTIONS = 5
"""A hard ceiling on the interview, independent of what the model wants.

Primarily a termination guarantee. Without it a skill that never returns `done`
walks a person through the entire catalogue — roughly twenty-three askable
fields — and the failure looks like the product being tedious rather than like a
bug.

It was 14, which was a ceiling nobody expected to reach and which the model
therefore reached: `question-generation` is asked "what should we ask next" and
there is always a defensible next field, so the ceiling became the *length*. A
person signing up met fifteen prose questions before seeing the product, which
is the point at which onboarding stops collecting better answers and starts
collecting shorter ones.

Five, plus the opening free-text turn, is the interview. Everything else is a
question the workspace can ask later, in context, when it has a reason to —
which is a better question anyway, because by then the person has seen what the
answer is for. Nothing is lost by not asking now: an unanswered field is a
`known_gap` with its own unlock, and that is what the gap list is for.
"""

MAX_REJECTIONS = 8
"""Consecutive rejected questions before the loop stops asking the model.

**It was 3, and three validators now share it.** The undeclared-target gate it
was sized for, plus the compound check and the shape check added later — all
three firing against `claude-haiku-4-5`. An audit of six interviews found half
of them ending here: Finance after one question, Chief of Staff after two,
Operations after **none**, each presented to the person as a considered
decision to stop.

Eight, because the arithmetic was wrong rather than the idea. A rejection is
one Haiku call of about a second and the failure reason is fed back, so
attempts are cheap and get better; an interview that asks a Head of Operations
nothing is not cheap at all. The question ceiling stays at `MAX_QUESTIONS` — a
rejected question is not a question asked, and conflating the two is what made
this a lost turn instead of a retry.

Exhausting these no longer ends the interview either. See `next_question`.
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

    def _floor(self, state: AgentState) -> Mapping[str, Any] | None:
        """One own-department fact, or the interview does not get to end.

        **The floor used to be on the rejection path only.** `next_fallback`
        prefers the answerer's department, so exhausting the retries could not
        leave Operations with nothing — but the *other two* exits, the model
        saying `done` and the ceiling tripping, both returned without looking at
        what had been collected. With five questions and twelve fields offered
        (nine shared plus three own), a model can legitimately spend every turn
        on shared narrative and leave `_record_facts` writing zero rows.

        So this is checked at all three exits now: if nothing in the person's own
        department has been answered and there is hand-written wording for one,
        it is asked. It costs at most one extra question and it is the
        difference between a workspace that knows an operational threshold and
        one that knows none.

        Returns None when there is nothing to insist on — no department, or the
        department already has an answer, or nothing left with a fallback — so
        the caller's own exit runs unchanged.
        """
        department = self._department()
        if department is None:
            return None
        if any(key.startswith(f"fact.{department}.") for key in state.answers):
            return None

        fallback = next_fallback(department, state.answers)
        if fallback is None or fallback.department != department:
            # Nothing of theirs left to ask. `next_fallback` falls through to the
            # shared set once a department is exhausted, and a shared field does
            # not satisfy a floor that exists to guarantee a departmental one.
            return None

        log.warning(
            "onboarding.floor_served",
            workspace_id=state.workspace_id,
            department=department,
            target=fallback.key,
            asked=state.asked,
        )
        state.asked += 1
        state.turns.append(
            Turn(
                role=TurnRole.AGENT,
                text=fallback.fallback_question,
                target_field=fallback.key,
                scope=fallback.scope,
                skill="floor",
            )
        )
        return {
            "done": False,
            "question": fallback.fallback_question,
            "target": fallback.key,
            "scope": fallback.scope,
            "choices": [],
            "skill": "floor",
            "skill_version": "1",
        }

    def _department(self) -> str | None:
        """The answerer's department, from the grounding every skill receives.

        The same value `generate-questions` narrows the catalogue with, read the
        same way, so the fallback cannot offer a field the model was never shown.
        """
        context = dict(self._ctx.grounding).get("user_context") or {}
        return str(context.get("department") or "").strip() or None

    async def next_question(self, state: AgentState) -> Mapping[str, Any]:
        """One turn of the interview, or a `done` verdict carrying its reason.

        The interview ends on three distinct conditions — the skill said done,
        the ceiling tripped, or the model could not name a declared field often
        enough. All three end the loop; only the first is a clean finish, and
        the others are logged so a degraded run is visible rather than silent.

        **It used to return None for all three, and the reason died with it.**
        The route then supplied its own closing line, so every interview in an
        audit of seven — all seven — ended on the literal string "nothing
        further worth asking", which is the one phrasing the skill's own prompt
        forbids: *"Say what you have enough of — not 'no further questions'."*
        The model was writing a real reason and it was being discarded one
        function above where it was needed. Each exit now names itself.
        """
        if state.asked >= MAX_QUESTIONS:
            floor = self._floor(state)
            if floor is not None:
                return floor
            log.info("onboarding.ceiling", workspace_id=state.workspace_id, asked=state.asked)
            state.phase = Phase.PERSONA
            return {
                "done": True,
                # The ceiling is a product decision, not a failure, and saying
                # so is more use than "nothing further worth asking" — it tells
                # the person why it stopped while they were still talking.
                "reason": (
                    f"that is the {MAX_QUESTIONS} questions I get to ask. "
                    "Anything else your workspace can ask later, in context."
                ),
            }

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
                floor = self._floor(state)
                if floor is not None:
                    return floor
                state.phase = Phase.PERSONA
                # The skill's own words. It is told to say what it has enough
                # of, and it does; the fallback is for a `done` with an empty
                # reason, which the schema permits.
                return {
                    "done": True,
                    "reason": str(result.get("reason", "")).strip()
                    or "I have enough to build on.",
                }
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

        # **Exhausted, but not finished.** Ending here is what produced the
        # worst outcome in the round-two audit: three of six interviews closed
        # early, one having asked nothing at all, each reported to the person as
        # a decision rather than a failure. A validator without a fallback
        # trades the defect it prevents for a blank interview, which is worse.
        #
        # So the hand-written wording is served instead. It cannot be rejected
        # by the gates that got us here — `fallback_question` says why, and a
        # test asserts it — so this terminates.
        fallback = next_fallback(self._department(), state.answers)
        if fallback is not None:
            log.warning(
                "onboarding.fallback_served",
                workspace_id=state.workspace_id,
                target=fallback.key,
                asked=state.asked,
            )
            state.asked += 1
            state.turns.append(
                Turn(
                    role=TurnRole.AGENT,
                    text=fallback.fallback_question,
                    target_field=fallback.key,
                    scope=fallback.scope,
                    skill="fallback",
                )
            )
            return {
                "done": False,
                "question": fallback.fallback_question,
                "target": fallback.key,
                "scope": fallback.scope,
                "choices": [],
                "skill": "fallback",
                "skill_version": "1",
            }

        # Nothing left with hand-written wording either — every field this
        # person can answer is answered. That is a real finish.
        log.warning("onboarding.rejections_exhausted", workspace_id=state.workspace_id)
        state.phase = Phase.PERSONA
        return {"done": True, "reason": "I have asked everything I can usefully ask."}

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
        self,
        state: AgentState,
        *,
        group: str,
        so_far: Mapping[str, Any] | None = None,
        deep_research: Mapping[str, Any] | None = None,
    ) -> Mapping[str, Any]:
        """Stage two, one **group** at a time. Moves to `assembling` on the last.

        The expensive stage, and it was one call for all seven Brain fields —
        which took 242 seconds against a real site and was killed by the proxy
        both times it was measured. `BRAIN_GROUPS` is the split and its docstring
        is the reasoning; this signature is what carries it through.

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
            group=group,
            so_far=so_far,
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


def next_brain_group(context: Mapping[str, Any]) -> str | None:
    """The first group not yet committed, or None when the Brain is whole.

    Read off the session row rather than held in memory, which is what makes a
    part-built Brain resumable: a run killed between groups comes back, sees
    which names are in `groups_done`, and starts at the one that did not finish.

    Order comes from `BRAIN_GROUPS`, not from the stored list — so inserting a
    group runs it for journeys already part-way through, instead of skipping it
    for anyone whose row predates it.
    """
    done = set(context.get("groups_done", []))
    return next((g.name for g in BRAIN_GROUPS if g.name not in done), None)


def _scope_of(key: str) -> int:
    from app.ai.runtime.fields import resolve

    return resolve(key).scope
