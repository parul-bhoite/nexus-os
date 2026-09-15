"""What a tile says when the sentence could not be written.

Seven refusal reasons, and **a real number is on screen beside every one of
them.** That is the constraint the copy has to satisfy and the reason it lives
in Python rather than in the TSX: the score was computed by
`calculators/audit.py` without a model, so a refusal about the *explanation*
must never read as doubt about the *figure*. "Something went wrong" beside 45
out of 65 makes a reader distrust the 45.

Total over the enum on purpose. An eighth reason added later fails this file
rather than shipping as a blank space where a sentence belongs — the same
mechanism `test_render_states.py` uses on `WidgetState`.
"""

from __future__ import annotations

from app.domain.narration import sentence_for
from app.grounding.pipeline import UnavailableReason

# Words that describe a broken product. ADR 0011 makes an absent model a
# **supported** state, so the sentence for it may not borrow this vocabulary.
BROKEN = ("error", "failed", "broken", "crash", "unavailable service", "problem with your")


def test_every_reason_has_a_sentence() -> None:
    """Totality. A reason with no copy renders as an empty paragraph, which
    reads as a rendering bug rather than as an answer."""
    for reason in UnavailableReason:
        sentence = sentence_for(reason)
        assert sentence, reason.value
        assert sentence.strip() == sentence
        assert sentence.endswith((".", "?")), f"{reason.value}: {sentence!r}"


def test_no_two_reasons_say_the_same_thing() -> None:
    """Two reasons producing one sentence means one of them is not worth
    distinguishing — the same rule `STATE_LABEL` is held to."""
    sentences = {sentence_for(reason) for reason in UnavailableReason}
    assert len(sentences) == len(list(UnavailableReason))


def test_every_sentence_is_short_enough_to_read_on_a_tile() -> None:
    for reason in UnavailableReason:
        assert len(sentence_for(reason)) <= 220, reason.value


def test_no_sentence_puts_the_score_in_doubt() -> None:
    """**The whole point of this file.**

    The figure beside the refusal was computed in pure Python from a crawled
    page and no model touched it. Every sentence has to leave that standing.
    """
    for reason in UnavailableReason:
        sentence = sentence_for(reason).lower()
        assert "score" in sentence or "figure" in sentence or "number" in sentence, (
            f"{reason.value} does not mention the figure at all, so a reader "
            f"cannot tell whether it is affected"
        )


def test_an_absent_model_reads_as_a_supported_state() -> None:
    """ADR 0011: no API key is not a degraded deployment.

    The application starts, serves everything and reports `unconfigured`. A
    tile that said "error" here would contradict `/health/ready` and turn a
    documented configuration into an outage on the one screen where somebody is
    deciding whether to trust us.
    """
    sentence = sentence_for(UnavailableReason.MODEL_UNAVAILABLE).lower()

    for word in BROKEN:
        assert word not in sentence, f"{word!r} in {sentence!r}"
    assert "configured" in sentence or "configuration" in sentence


def test_a_disabled_skill_reads_as_a_choice_not_a_fault() -> None:
    """The kill switch is somebody's decision, and saying so is what stops a
    founder chasing a fault that does not exist."""
    sentence = sentence_for(UnavailableReason.SKILL_DISABLED).lower()

    for word in BROKEN:
        assert word not in sentence, f"{word!r} in {sentence!r}"
    assert "off" in sentence or "disabled" in sentence or "switched" in sentence


def test_an_exhausted_budget_says_when_it_comes_back() -> None:
    """`routes/research.py`'s rule, transferred: *"A founder who cannot tell
    whether to wait an hour or a month gives up or asks support."* The window
    resets at midnight in the workspace's own reporting timezone, which is what
    `budgets_for` truncates on — so the sentence has to name that, not UTC."""
    sentence = sentence_for(UnavailableReason.BUDGET_EXHAUSTED).lower()

    assert "today" in sentence or "allowance" in sentence
    assert "reset" in sentence or "midnight" in sentence or "tomorrow" in sentence
    assert "utc" not in sentence, "the window is the workspace's timezone, not UTC"


def test_a_transient_provider_failure_invites_a_retry() -> None:
    sentence = sentence_for(UnavailableReason.PROVIDER_FAILED).lower()
    assert "again" in sentence


def test_our_own_faults_are_owned_rather_than_blamed_on_the_data() -> None:
    """`schema_invalid` and `invented_number` are both **ours**: the first is a
    malformed response, the second is a model stating a figure no calculation
    produced. Neither is a fact about the customer's business, and a sentence
    that implied otherwise would send somebody looking at their own data for a
    fault in our prompt.

    Asserted as **ownership**, not as a banned phrase. Banning "your data"
    outright was the first version of this and it was wrong: it failed
    *"rather than anything about your data"*, which is precisely the
    reassurance the sentence should carry. What matters is that we say whose
    fault it is, not that we avoid the words.
    """
    for reason in (UnavailableReason.SCHEMA_INVALID, UnavailableReason.INVENTED_NUMBER):
        sentence = sentence_for(reason).lower()
        assert "our" in sentence or "we " in sentence, (
            f"{reason.value} does not own the fault, so a reader will assume it is theirs"
        )
        assert "unaffected" in sentence or "still" in sentence, reason.value


def test_a_discarded_invented_number_says_what_was_discarded() -> None:
    """The one refusal that is evidence the guard works. A founder reading it
    should understand that we threw prose away *because* it stated a figure we
    could not trace — that is the product's central claim, visible."""
    sentence = sentence_for(UnavailableReason.INVENTED_NUMBER).lower()

    assert "discard" in sentence or "rejected" in sentence or "threw" in sentence
    assert "calculation" in sentence or "computed" in sentence


def test_missing_input_defers_to_the_tiles_own_unlock() -> None:
    """`unlock_for_sources` already produces the specific sentence — "Needs
    keyword data." — and a generic restatement here would be a second, vaguer
    wording of the same fact. The route prefers the unlock; this is the
    fallback for when there is not one."""
    sentence = sentence_for(UnavailableReason.MISSING_INPUT).lower()
    assert "needs" in sentence or "missing" in sentence or "not" in sentence


def test_no_sentence_is_cheerful_about_a_refusal() -> None:
    """`SKILL.md`'s voice rule, applied to our own copy: no exclamation marks,
    and the reader decides what matters about their own business."""
    for reason in UnavailableReason:
        sentence = sentence_for(reason)
        assert "!" not in sentence, reason.value
        assert "sorry" not in sentence.lower(), reason.value
        assert "oops" not in sentence.lower(), reason.value
