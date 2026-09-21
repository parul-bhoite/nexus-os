"""I1, applied to quotations instead of calculations. `doc/20` A2.

Every case here is a **real model output shape**, written as the answer a model
would plausibly produce, not as a unit test of a set difference. The point of
putting them under `evals/` rather than `tests/` is that they describe the
behaviour we are buying, and they should keep describing it when the
implementation behind `check` changes.

The eight cases split three ways:

- **Answered** — the numeral is in a passage the answer cited, in a form a
  reader can match. Rejecting these would be the guard's expensive failure mode:
  correct answers thrown away until somebody widens the rule to nothing.
- **Refused** — the figure was computed, converted, rounded or imagined. Each
  one is arithmetic the model did rather than a quotation it made, and the
  distinction is the product.
- **Structural** — no passages at all, and a citation naming a passage that was
  never sent.
"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from app.assistant.contracts import AssistantAnswer, Citation
from app.assistant.grounding import (
    ASSISTANT_REASONS,
    check,
    echoed_from_question,
    sentence_for,
)
from app.domain.scopes import Scope
from app.grounding.pipeline import UnavailableReason
from app.retrieval.chunks import Passage

DOCUMENT = UUID("11111111-1111-1111-1111-111111111111")


def _passage(content: str) -> Passage:
    return Passage(
        id=uuid4(),
        content=content,
        document_id=DOCUMENT,
        source_page=4,
        source_label="Annual report 2025",
        scope=Scope.L2_COMPANY_INTERNAL,
        department=(),
    )


def _citing(*passages: Passage) -> tuple[Citation, ...]:
    return tuple(
        Citation(
            chunk_id=p.id,
            document_id=p.document_id,
            source_label=p.source_label,
            source_page=p.source_page,
        )
        for p in passages
    )


def _answer(prose: str, *cited: Passage) -> AssistantAnswer:
    return AssistantAnswer(prose=prose, citations=_citing(*cited))


# --------------------------------------------------------------------------
# Answered
# --------------------------------------------------------------------------


def test_a_figure_quoted_exactly_from_a_cited_passage_is_answered() -> None:
    """The base case. If this fails the assistant cannot report anything from a
    document that contains a number, which is most documents."""
    passage = _passage("Headcount at year end stood at 43,000 across all regions.")

    assert check(_answer("Headcount was 43,000 at year end.", passage), [passage]) is None


def test_the_same_figure_written_without_the_comma_is_answered() -> None:
    """43000 and 43,000 are one number, and a reader matching the quotation
    would say the answer was right. `pipeline._numbers_in` strips separators for
    exactly this reason, and this case is what stops someone "simplifying" it.
    """
    passage = _passage("Headcount at year end stood at 43,000 across all regions.")

    assert check(_answer("Headcount was 43000 at year end.", passage), [passage]) is None


def test_a_purely_qualitative_answer_is_answered() -> None:
    """No numerals means nothing for this guard to catch — **and that is a real
    limit worth stating rather than a pass to be proud of.**

    `check` verifies figures and citations. It does not verify that the prose
    fairly represents the passage: an answer saying "the contract permits early
    termination" when the passage says the opposite has no numeral in it and
    goes through. Catching that needs a faithfulness eval against a model
    (`doc/20` A5), and until that exists this is the honest boundary of what A2
    buys.
    """
    passage = _passage("Either party may terminate this agreement with ninety days notice.")

    assert (
        check(_answer("The contract allows either side to end it early.", passage), [passage])
        is None
    )


# --------------------------------------------------------------------------
# Refused — the model did arithmetic
# --------------------------------------------------------------------------


def test_a_computed_percentage_change_is_refused() -> None:
    """Both endpoints are quoted, the percentage is not. This is the case most
    likely to feel harsh and it is the one the rule is for: *"up 12%"* is a
    calculation, it is the sort of thing a founder repeats in a board meeting,
    and no calculator produced it.
    """
    passage = _passage("Revenue was 43,000 in 2024 and 48,000 in 2025.")

    refusal = check(_answer("Revenue was up 12% year on year.", passage), [passage])

    assert refusal is not None
    assert refusal.reason is UnavailableReason.INVENTED_NUMBER


def test_a_currency_conversion_is_refused() -> None:
    """The model supplied a rate from its training data. That rate is a figure
    nobody in this product fetched, and it is stale by an unknown amount."""
    passage = _passage("The penalty is capped at 50,000 EUR per incident.")

    refusal = check(_answer("The penalty is capped at about 54,000 USD.", passage), [passage])

    assert refusal is not None
    assert refusal.reason is UnavailableReason.INVENTED_NUMBER


def test_rounding_a_quoted_figure_is_refused() -> None:
    """43,217 rounded to 43,000 is the friendliest possible invention, which is
    what makes it worth a test. It reads as helpful, it is wrong by 217, and a
    reader who follows the citation finds a different number than the one they
    were told."""
    passage = _passage("Headcount at year end stood at 43,217.")

    refusal = check(_answer("Headcount was roughly 43,000.", passage), [passage])

    assert refusal is not None
    assert refusal.reason is UnavailableReason.INVENTED_NUMBER


def test_a_figure_from_an_uncited_passage_is_refused() -> None:
    """Both passages were retrieved; only one was cited. The number came from
    the other.

    This is the case that makes citations load-bearing rather than decorative —
    the reader follows the one citation offered and does not find the figure
    there.
    """
    cited = _passage("Our largest office is in Berlin.")
    uncited_passage = _passage("Headcount at year end stood at 43,217.")

    refusal = check(_answer("Headcount was 43,217.", cited), [cited, uncited_passage])

    assert refusal is not None
    assert refusal.reason is UnavailableReason.INVENTED_NUMBER


# --------------------------------------------------------------------------
# Refused — structural
# --------------------------------------------------------------------------


def test_no_passages_at_all_is_refused_rather_than_answered() -> None:
    """The caller should never have reached a model, and `check` says so anyway.

    An answer produced with nothing retrieved is an answer produced from the
    model's memory of the internet, which is the one thing this product is sold
    on not doing.
    """
    refusal = check(_answer("Your payment terms are net 30."), [])

    assert refusal is not None
    assert refusal.reason is UnavailableReason.NO_PASSAGE


def test_citing_a_passage_that_was_never_sent_is_refused() -> None:
    """A fabricated source. Checked before the numerals, because a citation the
    answer invented cannot be trusted to license the figures attributed to it.
    """
    sent = _passage("Either party may terminate with ninety days notice.")
    never_sent = _passage("Late payment attracts interest at 8 percent.")

    refusal = check(_answer("Late payment attracts 8 percent.", never_sent), [sent])

    assert refusal is not None
    assert refusal.reason is UnavailableReason.UNCITED_CLAIM


# --------------------------------------------------------------------------
# The copy
# --------------------------------------------------------------------------


@pytest.mark.parametrize("reason", sorted(ASSISTANT_REASONS))
def test_every_verdict_has_a_sentence_a_reader_can_act_on(reason: UnavailableReason) -> None:
    """Totality over the assistant's own set — the other half of the guarantee
    `test_refusal_vocabulary.py` splits. A refusal with no sentence renders as
    an empty bubble, which reads as the assistant having crashed.
    """
    sentence = sentence_for(reason)

    assert sentence.strip() == sentence
    assert sentence.endswith(".")
    assert len(sentence) <= 220, f"{reason.value} is too long to read in a chat bubble"
    assert "!" not in sentence
    assert "sorry" not in sentence.lower()


def test_a_refusal_never_blames_the_customers_documents_for_our_own_fault() -> None:
    """`test_narration_copy.py`'s rule, carried across. `INVENTED_NUMBER` and
    `UNCITED_CLAIM` are both ours — a model we chose, behind a prompt we wrote —
    and a sentence that implied otherwise sends somebody auditing their own PDFs
    for a fault in our pipeline.
    """
    for reason in (UnavailableReason.INVENTED_NUMBER, UnavailableReason.UNCITED_CLAIM):
        sentence = sentence_for(reason).lower()
        assert "our" in sentence or "we " in sentence, reason.value


def test_the_no_passage_sentence_says_what_would_make_it_answerable() -> None:
    """ADR 0052 and `doc/04` §6 rule 1: every refusal is a call to action. This
    is the refusal a founder hits most often on day one, when they have uploaded
    two documents, and "no" without a next step is where they stop."""
    sentence = sentence_for(UnavailableReason.NO_PASSAGE).lower()

    assert "upload" in sentence
    assert "document" in sentence


def test_one_chunk_cited_by_three_segments_yields_one_citation() -> None:
    """**A regression test for a 500 that a real model produced.**

    Asked a question whose answer rests on one passage, a model answers in
    several segments and cites that passage in each — which is correct of it.
    `resolve` returned a citation per mention, `generation_citation` holds one
    row per (answer, chunk) by ADR 0056, and the insert failed on the unique
    constraint. The constraint was right; the caller was the bug.

    Deduplication is not cosmetic here. The panel keys its citation list on the
    chunk id, so duplicates were also a broken list in the browser.
    """
    from app.assistant.fence import prepare, resolve

    passages = [_passage("Payment is due within 30 days."), _passage("Delivery is FOB origin.")]
    grounding = prepare(passages)

    citations, unknown = resolve(grounding, ["p1", "p1", "p2", "p1"])

    assert unknown == ()
    assert [c.chunk_id for c in citations] == [passages[0].id, passages[1].id], (
        "first mention wins, and order is the answer's rather than the retrieval's"
    )


# --------------------------------------------------------------------------
# ADR 0062 — a figure the customer typed
# --------------------------------------------------------------------------


def test_a_figure_from_the_question_is_not_an_invention() -> None:
    """**The defect A9's first live run found.**

    Asked *"who can approve a purchase of 3,000 rial?"* over a policy banded
    *"500 to 5,000"*, the assistant refused with `INVENTED_NUMBER` — telling the
    reader their own number was fabricated, on the question shape most likely to
    involve a threshold. 1 of 26 answerable questions.
    """
    passage = _passage("Purchases from 500 to 5,000 OMR require department head approval.")
    answer = _answer("A purchase of 3,000 OMR needs department head approval.", passage)

    assert check(answer, [passage], question_numerals=frozenset({"3000"})) is None


def test_the_permission_does_not_extend_to_an_uncited_answer() -> None:
    """**The narrowing, and the reason this was a decision rather than a fix.**

    A question is attacker-reachable: *"Is our revenue 5,000,000?"* would let a
    model hand the figure back as though it were grounded. Tying the permission
    to a citation is what stops the question laundering a number — an answer
    pointing at nothing gets ADR 0053's original, stricter set.
    """
    passage = _passage("Our largest office is in Berlin.")
    answer = AssistantAnswer(prose="Yes, revenue is 5,000,000.", citations=())

    refusal = check(answer, [passage], question_numerals=frozenset({"5000000"}))

    assert refusal is not None
    assert refusal.reason is UnavailableReason.UNCITED_CLAIM or (
        refusal.reason is UnavailableReason.INVENTED_NUMBER
    )


def test_an_echo_is_recorded_rather_than_silent() -> None:
    """ADR 0062's other half. The permission is narrow, not invisible: an answer
    that leaned on it says so on its `generation` row, so a reviewer can find
    the echoes instead of inferring them."""
    passage = _passage("Purchases from 500 to 5,000 OMR require department head approval.")

    echoed = echoed_from_question(
        "A purchase of 3,000 OMR needs department head approval.",
        [passage],
        frozenset({"3000"}),
    )
    assert echoed == frozenset({"3000"})

    # A figure quoted from the passage is not an echo, even when the question
    # happens to contain it too.
    quoted = echoed_from_question("The band starts at 500.", [passage], frozenset({"500"}))
    assert quoted == frozenset()
