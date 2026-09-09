"""`/evals/grounding` — the four specs (`doc/12` P14).

I1 says every number is fetched or computed, never generated. Until now that was
a property of a codebase with no generation in it, which is easy. These are the
first tests that could catch a violation, and each is written so that **breaking
the pipeline turns it red** — a spec that passes against a broken pipeline
certifies the thing it was meant to catch.

The failure this guards against does not look like a failure. A model that
invents one figure among four correct ones produces an answer that reads
perfectly, cites real sources, and is wrong in the one place somebody will act
on.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from app.grounding.pipeline import (
    Answer,
    Budgets,
    Computed,
    Outcome,
    UnavailableReason,
    describes_no_change,
    invented_numbers,
    run,
)

PLENTY = Budgets(tenant_spent=0, tenant_limit=1_000_000, user_spent=0, user_limit=100_000)
NO_SKILLS_DISABLED: frozenset[str] = frozenset()


def _saying(*prose: str) -> Callable[[Computed], Awaitable[str]]:
    """A model that says these things in order, one per call.

    Async because `run` awaits it, and `run` awaits it because the real provider
    is async. Nothing here touches a network — which is the point of the seam:
    the whole pipeline is exercised with no key, and no key is a supported state
    rather than a degraded one (ADR 0011).
    """
    said = list(prose)

    async def call(_computed: Computed) -> str:
        return said.pop(0) if said else said_last(prose)

    return call


def said_last(prose: tuple[str, ...]) -> str:
    return prose[-1] if prose else ""


# ── 1. A model-produced number is rejected ────────────────────


async def test_a_number_the_calculation_did_not_produce_is_rejected() -> None:
    """The spec this whole phase exists for.

    Rejected, not corrected. Rewriting the model's figure would put our number
    inside their sentence and leave the reasoning around it untouched — a
    corrected number inside an argument built on a wrong one.
    """
    computed = Computed(values={"receivables": 4500.0})

    answer = await run(
        skill="finance.summary",
        computed=computed,
        call_model=_saying(
            "Receivables are 4500, up from 3900 last month.",  # 3900 is invented
            "Receivables are 4500, up from 3900 last month.",
        ),
        budgets=PLENTY,
        disabled_skills=NO_SKILLS_DISABLED,
    )

    assert answer.outcome is Outcome.UNAVAILABLE
    assert answer.reason is UnavailableReason.INVENTED_NUMBER
    assert answer.retried, "the pipeline retries once before giving up"


async def test_the_same_number_formatted_differently_is_not_invented() -> None:
    """A value of 4500.0 may be written 4500 or 4,500. Refusing the model
    ordinary formatting would reject correct answers and make this guard so
    noisy somebody would switch it off."""
    computed = Computed(values={"receivables": 4500.0})
    assert not invented_numbers("Receivables stand at 4,500.", computed)
    assert not invented_numbers("Receivables: 4500.00", computed)


async def test_a_retry_that_behaves_is_answered() -> None:
    """One bad attempt is not a failure. The retry exists because models are
    occasionally sloppy rather than systematically wrong, and spending an
    Unavailable on the first slip would make the product feel broken."""
    computed = Computed(values={"runway": 7.0})

    answer = await run(
        skill="finance.runway",
        computed=computed,
        call_model=_saying("Runway is 9 months.", "Runway is 7 months."),
        budgets=PLENTY,
        disabled_skills=NO_SKILLS_DISABLED,
    )

    assert answer.outcome is Outcome.ANSWERED
    assert answer.retried


# ── 2. A zero delta reports "unchanged", not 0% ───────────────


async def test_a_zero_delta_is_described_as_unchanged() -> None:
    """ "0%" is technically true and reads as a measurement failure.

    A founder cannot tell "nothing moved" from "we could not compute this", and
    those want completely different reactions.
    """
    assert describes_no_change("Receivables are unchanged since last month.")
    assert describes_no_change("Conversion is flat.")
    assert not describes_no_change("Receivables are up 4%.")


async def test_zero_is_still_a_permitted_number() -> None:
    """The rule is about *prose*, not about forbidding the digit. A computed
    zero is a real value and must survive the invention check."""
    assert not invented_numbers("The delta is 0.", Computed(values={"delta": 0.0}))


# ── 3. A missing input renders its named state ────────────────


async def test_a_missing_input_names_what_is_missing() -> None:
    """A blank tile tells a founder nothing. "We need your fiscal year start"
    tells them what to do — and the model is never called, because asking one to
    narrate a number nobody has is how invented figures get invited in."""
    called: list[int] = []

    async def must_not_run(_computed: Computed) -> str:
        called.append(1)
        return "anything"

    answer = await run(
        skill="finance.summary",
        computed=Computed(values={}, missing=("fiscal_year_start",)),
        call_model=must_not_run,
        budgets=PLENTY,
        disabled_skills=NO_SKILLS_DISABLED,
    )

    assert answer.outcome is Outcome.UNAVAILABLE
    assert answer.reason is UnavailableReason.MISSING_INPUT
    assert answer.missing == ("fiscal_year_start",)
    assert not called, "a calculation that cannot run must not reach the model"


# ── 4. A schema failure after retry renders Unavailable ───────


async def test_two_empty_responses_render_unavailable() -> None:
    answer = await run(
        skill="finance.summary",
        computed=Computed(values={"x": 1.0}),
        call_model=_saying("", ""),
        budgets=PLENTY,
        disabled_skills=NO_SKILLS_DISABLED,
    )

    assert answer.outcome is Outcome.UNAVAILABLE
    assert answer.reason is UnavailableReason.SCHEMA_INVALID


# ── The two guards that were never consulted ──────────────────


async def test_an_exhausted_budget_degrades_to_unavailable_not_a_cheaper_model() -> None:
    """An unevaluated model is not a fallback — it is a different product
    nobody agreed to, and it looks identical to the real one on screen."""
    spent = Budgets(tenant_spent=10, tenant_limit=10, user_spent=0, user_limit=100)

    answer = await run(
        skill="finance.summary",
        computed=Computed(values={"x": 1.0}),
        call_model=_saying("x is 1"),
        budgets=spent,
        disabled_skills=NO_SKILLS_DISABLED,
    )

    assert answer.outcome is Outcome.UNAVAILABLE
    assert answer.reason is UnavailableReason.BUDGET_EXHAUSTED


async def test_the_per_user_budget_binds_independently_of_the_tenant() -> None:
    """One person cannot spend the whole company's allowance, and a company
    with room does not rescue a person who has none."""
    user_spent = Budgets(tenant_spent=0, tenant_limit=10_000, user_spent=50, user_limit=50)
    answer = await run(
        skill="s",
        computed=Computed(values={"x": 1.0}),
        call_model=_saying("x is 1"),
        budgets=user_spent,
        disabled_skills=NO_SKILLS_DISABLED,
    )
    assert answer.reason is UnavailableReason.BUDGET_EXHAUSTED


async def test_the_kill_switch_is_consulted_before_anything_is_spent() -> None:
    """`disabled_ai_skills` has existed and been read since M0 without a single
    caller consulting it — a switch nobody wired up is a switch that does not
    work, which is worse than not having one."""
    called: list[int] = []

    async def must_not_run(_computed: Computed) -> str:
        called.append(1)
        return "anything"

    answer = await run(
        skill="finance.summary",
        computed=Computed(values={"x": 1.0}),
        call_model=must_not_run,
        budgets=PLENTY,
        disabled_skills=frozenset({"finance.summary"}),
    )

    assert answer.outcome is Outcome.UNAVAILABLE
    assert answer.reason is UnavailableReason.SKILL_DISABLED
    assert not called, "a disabled skill must not cost a model call"


async def test_every_unavailable_says_which_kind_it_is() -> None:
    """ "Unavailable" alone tells a founder nothing about whether to wait,
    connect something, or ask us."""
    for reason in UnavailableReason:
        assert reason.value, reason
    assert Answer(outcome=Outcome.UNAVAILABLE).reason is None, (
        "the default carries no reason, so a caller cannot forget to set one "
        "and have it look deliberate"
    )
