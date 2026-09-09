"""One path from facts to an answer, and the rule that makes it trustworthy.

**Every number is computed, never generated** (I1). The model writes prose about
numbers it is *given*; if a figure appears in its output that no calculation
produced, the answer is **rejected**. Not corrected, not flagged — rejected,
because a plausible wrong number beside three right ones is worse than no answer
at all, and a reader has no way to tell which is which.

**The sequence is fixed**, and each step can only fail into the next:

    fetch -> compute -> one model call -> schema-validate -> retry once -> Unavailable

Never a cheaper unevaluated model, never a stale cache. Both are ways of
producing *something* when the honest answer is that we produced nothing, and
both look identical to success on a screen.
"""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Final


class Outcome(StrEnum):
    ANSWERED = "answered"
    UNAVAILABLE = "unavailable"


class UnavailableReason(StrEnum):
    """Why there is no answer. Always specific — "unavailable" alone tells a
    founder nothing about whether to wait, connect something, or ask us."""

    MISSING_INPUT = "missing_input"
    """A calculation needed a fact nobody supplied. Renders as the named state —
    "we need your fiscal year start" — never as a blank tile."""

    INVENTED_NUMBER = "invented_number"
    """The model put a figure in its prose that no calculation produced. The
    whole reason this pipeline exists."""

    SCHEMA_INVALID = "schema_invalid"
    """The output did not fit the contract, twice."""

    BUDGET_EXHAUSTED = "budget_exhausted"
    """The daily allowance is spent. Degrades to Unavailable rather than to a
    cheaper model: an unevaluated model is not a fallback, it is a different
    product nobody agreed to."""

    SKILL_DISABLED = "skill_disabled"
    """Killed by `disabled_ai_skills` — a switch that has existed and been read
    since M0 without any caller consulting it."""

    MODEL_UNAVAILABLE = "model_unavailable"
    """There is no usable language model: no key, or a revoked one.

    **A supported state, not an error** (ADR 0011). It is separate from
    `SCHEMA_INVALID` because the two want opposite responses — one is ours to
    fix and the other is a deployment fact — and collapsing them would make
    *"the product is misconfigured"* indistinguishable from *"the model wrote
    something malformed"* on the one screen where somebody is deciding whether
    to trust us."""

    PROVIDER_FAILED = "provider_failed"
    """The provider was reachable and did not answer: an overload, a timeout, a
    refused request. Distinct from `SCHEMA_INVALID` because nothing was wrong
    with what came back — nothing came back."""


@dataclass(frozen=True, slots=True)
class Computed:
    """What the calculators produced. **The only permitted source of numbers.**"""

    values: dict[str, float] = field(default_factory=dict)
    missing: tuple[str, ...] = ()

    @property
    def complete(self) -> bool:
        return not self.missing


@dataclass(frozen=True, slots=True)
class Answer:
    outcome: Outcome
    prose: str = ""
    values: dict[str, float] = field(default_factory=dict)
    reason: UnavailableReason | None = None
    missing: tuple[str, ...] = ()
    retried: bool = False


NUMBER: Final = re.compile(r"\d[\d,]*(?:\.\d+)?%?")
"""Deliberately greedy. A false positive costs one rejected answer; a false
negative ships an invented figure to somebody who will act on it."""

UNCHANGED_WORDS: Final = ("unchanged", "no change", "flat", "the same")
"""What a zero delta *means*. Reporting "0%" is technically true and reads as a
measurement failure — the founder cannot tell "nothing moved" from "we could not
compute this"."""


def _numbers_in(prose: str) -> set[str]:
    return {m.group().rstrip("%").replace(",", "") for m in NUMBER.finditer(prose)}


def _permitted(computed: Computed) -> set[str]:
    """Every legitimate rendering of a computed value.

    12.0 may be written 12, 12.0 or 12.00 — the same number, and refusing the
    model ordinary formatting would reject correct answers.
    """
    allowed: set[str] = set()
    for value in computed.values.values():
        for rendered in (f"{value:g}", f"{value:.0f}", f"{value:.1f}", f"{value:.2f}"):
            allowed.add(rendered)
            allowed.add(rendered.lstrip("-"))
    return allowed


def invented_numbers(prose: str, computed: Computed) -> set[str]:
    """Figures in the prose that no calculation produced. **I1's teeth.**"""
    return _numbers_in(prose) - _permitted(computed)


def describes_no_change(prose: str) -> bool:
    return any(word in prose.lower() for word in UNCHANGED_WORDS)


@dataclass(frozen=True, slots=True)
class Budgets:
    """The two token budgets that have sat in `config.py` unread since M0."""

    tenant_spent: int
    tenant_limit: int
    user_spent: int
    user_limit: int

    @property
    def exhausted(self) -> bool:
        return self.tenant_spent >= self.tenant_limit or self.user_spent >= self.user_limit


async def run(
    *,
    skill: str,
    computed: Computed,
    call_model: Callable[[Computed], Awaitable[str]],
    budgets: Budgets,
    disabled_skills: frozenset[str],
) -> Answer:
    """The pipeline. Checks are ordered by what they cost to discover.

    The kill switch and the budget come **before** the model call, because both
    are reasons not to spend money and finding out afterwards has already spent
    it. Missing inputs come before that: a calculation that cannot run is not a
    model problem, and asking a model to narrate a number nobody has is how
    invented figures get invited in.

    `call_model` is passed in rather than imported so nothing outside
    `app/ai/` names a vendor (ADR 0011's boundary), and so this whole path is
    testable without a key — which is a supported state, not a degraded one.

    **Async because the model call is.** It was synchronous while nothing called
    it, and a synchronous pipeline can only be joined to an async provider by
    duplicating this ordering somewhere that can await — which would put the
    decision about when to give up in two places. The decisions here are still
    pure; only the call it makes is not.
    """
    if skill in disabled_skills:
        return Answer(outcome=Outcome.UNAVAILABLE, reason=UnavailableReason.SKILL_DISABLED)

    if not computed.complete:
        # The named state, with what is missing. A blank tile tells a founder
        # nothing; "we need your fiscal year start" tells them what to do.
        return Answer(
            outcome=Outcome.UNAVAILABLE,
            reason=UnavailableReason.MISSING_INPUT,
            missing=computed.missing,
            values=computed.values,
        )

    if budgets.exhausted:
        return Answer(outcome=Outcome.UNAVAILABLE, reason=UnavailableReason.BUDGET_EXHAUSTED)

    for attempt in (0, 1):
        prose = await call_model(computed)

        invented = invented_numbers(prose, computed)
        if invented:
            # **Rejected, not corrected.** Rewriting a model's number would put
            # our figure inside their sentence and leave the reasoning around it
            # untouched — a fixed number in an argument built on a wrong one.
            if attempt == 1:
                return Answer(
                    outcome=Outcome.UNAVAILABLE,
                    reason=UnavailableReason.INVENTED_NUMBER,
                    values=computed.values,
                    retried=True,
                )
            continue

        if not prose.strip():
            if attempt == 1:
                return Answer(
                    outcome=Outcome.UNAVAILABLE,
                    reason=UnavailableReason.SCHEMA_INVALID,
                    values=computed.values,
                    retried=True,
                )
            continue

        return Answer(
            outcome=Outcome.ANSWERED,
            prose=prose,
            values=computed.values,
            retried=attempt == 1,
        )

    # Unreachable: both attempts return or continue. Here so a future edit that
    # changes the loop cannot fall through into an implicit `None`.
    return Answer(outcome=Outcome.UNAVAILABLE, reason=UnavailableReason.SCHEMA_INVALID)
