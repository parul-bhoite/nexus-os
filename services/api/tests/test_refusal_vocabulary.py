"""One vocabulary, two surfaces, and no reason without copy on either.

`doc/20` A2. `test_narration_copy.py` used to iterate `UnavailableReason`
directly and assert a sentence for every member, which made "a reason with no
copy" impossible. A2 broke that by adding `NO_PASSAGE` and `UNCITED_CLAIM` —
reasons a narration tile can never emit, and whose narration copy would have had
to satisfy *"every sentence mentions the score, the figure or the number"*
beside an assistant answer that has no figure on the screen at all.

**The guarantee is split here rather than dropped.** Narration is total over
`NARRATION_REASONS`, the assistant is total over `ASSISTANT_REASONS`, and this
file asserts the two cover the enum. A tenth reason added later still fails a
test rather than shipping as a blank space — it just has to be assigned to a
surface first, which is the question its author should be answering anyway.

**Why one enum and not two.** `generation.unavailable_reason` is a single `text`
column that both surfaces write to. Two enums would eventually put `no_passage`
and `NoPassage` in the same column, and every query counting refusals would be
quietly wrong about one of them.
"""

from __future__ import annotations

from app.assistant.grounding import ASSISTANT_REASONS
from app.assistant.grounding import sentence_for as assistant_sentence_for
from app.domain.narration import NARRATION_REASONS
from app.domain.narration import sentence_for as narration_sentence_for
from app.grounding.pipeline import UnavailableReason


def test_every_reason_belongs_to_a_surface() -> None:
    """The replacement for the totality `test_narration_copy.py` gave up."""
    covered = NARRATION_REASONS | ASSISTANT_REASONS
    missing = set(UnavailableReason) - covered

    assert missing == set(), (
        "these reasons have copy on no surface, so they render as a blank space: "
        + ", ".join(sorted(r.value for r in missing))
        + ". Add the member to NARRATION_REASONS or ASSISTANT_REASONS with its sentence."
    )


def test_every_shared_reason_is_worded_separately_for_each_surface() -> None:
    """**Rewritten in A6, and the history is the point.**

    A2 pinned this to `== {INVENTED_NUMBER}`, on the reasoning that a second
    overlap would mean somebody had reused a reason rather than naming what
    actually went wrong. A6 made that wrong: a spent budget, a disabled skill,
    an absent model and a malformed response happen to *both* surfaces, for the
    same cause, and giving the assistant its own names for them would be the
    duplicate-vocabulary failure ADR 0054 exists to prevent.

    So the invariant is not how much the sets overlap — it is that an overlap
    never means shared copy. Every reason on both surfaces is worded twice,
    because the two screens do not contain the same things.
    """
    shared = NARRATION_REASONS & ASSISTANT_REASONS
    assert shared, "the sets have diverged completely, which ADR 0054 did not intend"

    same = sorted(
        reason.value
        for reason in shared
        if narration_sentence_for(reason) == assistant_sentence_for(reason)
    )
    assert same == [], (
        "these reasons show identical copy on a tile and in a chat bubble: "
        + ", ".join(same)
        + ". One of the two screens is being described wrongly — a tile has a figure "
        "beside it and the assistant does not."
    )


def test_the_shared_reason_is_worded_for_its_own_surface() -> None:
    """The concrete thing the split was made to prevent.

    Narration's sentence ends *"The score above is unaffected"*, which is true
    beside a tile and false beside an assistant answer, where there is no score.
    Identical copy on both surfaces would mean the split bought nothing.
    """
    tile = narration_sentence_for(UnavailableReason.INVENTED_NUMBER)
    chat = assistant_sentence_for(UnavailableReason.INVENTED_NUMBER)

    assert tile != chat
    assert "score" in tile.lower()
    assert "score" not in chat.lower(), (
        "the assistant refusal mentions a score, and there is none on that screen"
    )


def test_a_surface_refuses_the_other_surfaces_reason() -> None:
    """Crossing the maps has to be loud.

    Returning a plausible-but-wrong sentence is the failure mode that would
    survive review — it renders, it reads fine, and it describes a screen the
    reader is not looking at.
    """
    for reason in ASSISTANT_REASONS - NARRATION_REASONS:
        try:
            narration_sentence_for(reason)
        except KeyError:
            continue
        raise AssertionError(f"narration produced a sentence for {reason.value}")

    for reason in NARRATION_REASONS - ASSISTANT_REASONS:
        try:
            assistant_sentence_for(reason)
        except KeyError:
            continue
        raise AssertionError(f"the assistant produced a sentence for {reason.value}")
