"""A stored sentence, whether it still describes the figure, and what to say
when there is no sentence.

Pure. No session, no model, no capability registry — `describes` is called once
per tile inside a request that has already spent its round trips, and
`sentence_for` is a lookup.

## Why a stored narration needs checking at all

The figure is recomputed from the crawl on every page load. The sentence is
written once and kept. So the two can drift, and the drift is the worst failure
this product can have: prose written about 45 out of 65 rendered beside a fresh
39 out of 65. Both halves individually true, the sentence well written, nothing
on screen saying they describe different measurements — and a reader would act
on it.

`describes` is what stops that, and it errs towards dropping the sentence.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.grounding.compute import Computation
from app.grounding.pipeline import UnavailableReason


@dataclass(frozen=True, slots=True)
class StoredNarration:
    """One `generation` row, as much of it as a tile needs.

    The five trace fields arrive from `calculation_trace ->> '…'`, so they are
    **strings or `None`** — `json` has no equality operator in Postgres, which
    is why the comparison happens here rather than in the query, and `->>` is
    the only accessor that type supports.
    """

    module: str
    prose: str
    prompt_version: str
    narrated_at: datetime

    numerator: str | None
    denominator: str | None
    percentage: str | None
    page: str | None
    window: str | None


def describes(stored: StoredNarration, computation: Computation) -> bool:
    """Whether this sentence was written about this figure.

    **All five fields, and each one catches a case the others do not:**

    `numerator` — the figure moved. The obvious one, and the only one a
    single-field check would catch.

    `denominator` — 45/65 and 9/13 are both 69%. A changed denominator means
    the calculator changed scale, so prose about "most of the checks" was
    written against a different set of them.

    `percentage` — it is in `computed.values`, which makes it a numeral the
    prose is *permitted to state*. A rounding change would leave the numerator
    matching and a stated percentage wrong.

    `page` — the same score on two different pages is the same number about
    different things, and the sentence may name the page.

    `window` — the only place the fetch date lives. **A re-crawl the next day
    with an identical score must invalidate**, because the prose may cite the
    date, and citing a date we have since replaced is a false statement about
    when we looked. This is the case a naive implementation gets wrong: every
    numeric field still matches.

    Compared as strings throughout. `json.dumps` wrote `45`, `->>` reads back
    `"45"`, `str(45)` is `"45"`. Casting to `int` would raise on a malformed
    trace and turn a staleness check into a 500 on the dashboard — so a garbage
    value has to be a mismatch. A missing key gives `None` from `->>`, which
    never equals a `str()`, so an unreadable trace **fails closed**: we cannot
    prove the sentence still applies, and the honest response to that is to
    stop showing it.
    """
    if stored.module != computation.capability_id:
        return False

    return (
        stored.numerator == str(computation.score.score)
        and stored.denominator == str(computation.score.max_score)
        and stored.percentage == str(computation.score.percentage)
        and stored.page == str(computation.trace["page"])
        and stored.window == str(computation.trace["window"])
    )


# ── What a tile says when there is no sentence ────────────────
#
# Server-authored, for the reason `BlockCard` already gives about `unlock`: the
# sentence comes from the API so one wording change reaches every surface, and
# so a tile cannot ship with the space drawn and the copy forgotten. A
# reason-to-sentence map in the TSX would be that failure with an extra step.
#
# **Every one of these renders beside a real number.** The score was computed
# by `calculators/audit.py` from a crawled page and no model touched it, so a
# refusal about the *explanation* must not read as doubt about the *figure*.
# "Something went wrong" beside 45 out of 65 makes a reader distrust the 45,
# which is the opposite of what this product is for.

_SENTENCES: dict[UnavailableReason, str] = {
    # ADR 0011. No key is a supported state, so this borrows none of the
    # vocabulary of a fault — no "error", no "failed", no "unavailable
    # service". It names a configuration and says the score did not need one.
    UnavailableReason.MODEL_UNAVAILABLE: (
        "No language model is configured, so nothing can write the explanation. "
        "The score above was computed without one and is unaffected."
    ),
    # Somebody's decision, and saying so is what stops a founder chasing a
    # fault that does not exist.
    UnavailableReason.SKILL_DISABLED: (
        "Written explanations are switched off for this deployment. "
        "The score above is computed either way."
    ),
    # `routes/research.py`'s rule, transferred: a founder who cannot tell
    # whether to wait an hour or a month gives up or asks support. The window
    # is the one `budgets_for` truncates on — the workspace's own reporting
    # timezone, never UTC.
    UnavailableReason.BUDGET_EXHAUSTED: (
        "This workspace has used its language-model allowance for today. It resets at "
        "midnight in your reporting timezone; the score above does not use the allowance."
    ),
    UnavailableReason.PROVIDER_FAILED: (
        "The language model did not answer. Nothing is wrong with your data — the score "
        "above still stands, and this is worth trying again in a moment."
    ),
    # Ours, not theirs. A sentence implying otherwise would send somebody
    # looking at their own data for a fault in our prompt.
    UnavailableReason.SCHEMA_INVALID: (
        "The explanation came back malformed twice, which is ours to fix rather than "
        "anything about your data. The score above is unaffected."
    ),
    # The one refusal that is evidence the guard works, so it says what was
    # discarded and why — I1, visible.
    UnavailableReason.INVENTED_NUMBER: (
        "We discarded the explanation because it stated a figure the calculation did not "
        "produce. That is the check working. The score above is unaffected."
    ),
    # The route prefers `unlock_for_sources`, which produces the specific
    # sentence ("Needs keyword data."). This is the fallback for when there is
    # not one, and it stays vague deliberately rather than guessing which input.
    UnavailableReason.MISSING_INPUT: (
        "Something this explanation needs is missing, so there is no sentence to show. "
        "The figure above is what we can compute today."
    ),
}


def sentence_for(reason: UnavailableReason) -> str:
    """The copy for one refusal.

    Total over the enum, and `tests/test_narration_copy.py` proves it: an
    eighth reason added later fails that file rather than shipping as a blank
    space where a sentence belongs.
    """
    return _SENTENCES[reason]
