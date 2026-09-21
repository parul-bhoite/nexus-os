"""What an answer has to survive before a reader sees it. `doc/20` A2.

**The rule is not in a prompt.** ADR 0052 says a figure question must be refused
rather than answered thinly, and a refusal a prompt requests is a refusal the
model may decline to give. Every check here runs over the model's output after
the fact, on text the model cannot see, and rejects the whole answer rather than
editing it — the same stance `grounding/pipeline.py` takes for narration, and
for the same reason: a partially corrected answer still carries the reader's
impression of the part that was wrong.

Three things are checked, in an order chosen so each one can trust the last:

1. **Were any passages readable at all.** No passages means no possible
   grounding, and the caller should not have reached a model.
2. **Does every citation name a passage that was sent.** A fabricated source
   invalidates everything downstream, including the numerals that were about to
   be checked against it.
3. **Is every figure in the prose present in the passages it cited.** I1, moved
   from calculators to quotations.

**Why the permitted numerals come from the *cited* passages and not from all of
them.** A figure lifted out of a passage the answer never claimed to be reading
is a figure the reader cannot check — they would follow the citation and not
find it. Allowing the whole retrieved set would make the citation decorative,
which is the failure `AssistantAnswer`'s docstring already refuses.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Final
from uuid import UUID

from app.assistant.contracts import AssistantAnswer, AssistantRefusal, Citation
from app.grounding.pipeline import Computed, UnavailableReason, invented_numbers, numerals_supplied
from app.retrieval.chunks import Passage

NOTHING_COMPUTED: Final = Computed()
"""**The assistant computes nothing, and this says so in the type.**

`invented_numbers` takes the calculators' output as the permitted set. The
assistant has no calculators — the import allowlist in
`tests/test_assistant_boundary.py` forbids reaching one — so the permitted set
is empty and every legitimate figure has to arrive through `also_permitted`,
which is to say out of a quoted passage. An empty `Computed` is the honest
spelling of that, not a placeholder to be filled in later.
"""

ASSISTANT_REASONS: Final[frozenset[UnavailableReason]] = frozenset(
    {
        UnavailableReason.NO_PASSAGE,
        UnavailableReason.UNCITED_CLAIM,
        UnavailableReason.INVENTED_NUMBER,
        UnavailableReason.EMBEDDER_UNCONFIGURED,
        UnavailableReason.SCHEMA_INVALID,
        UnavailableReason.MODEL_UNAVAILABLE,
        UnavailableReason.BUDGET_EXHAUSTED,
        UnavailableReason.SKILL_DISABLED,
        UnavailableReason.PROVIDER_FAILED,
    }
)
"""Every reason the assistant can show a reader.

The first three are `check`'s own verdicts; the rest are produced by `ask.py`
and `pipeline.run` before or around the model call. They were added in A6 rather
than written speculatively in A2 — each one arrived with the code that emits
it."""

_SENTENCES: Final[dict[UnavailableReason, str]] = {
    # Not a failure. ADR 0052 makes documents the product, so a question outside
    # them is a supported outcome — and the sentence has to say what would make
    # it answerable, because a founder who reads "no" without a next step
    # concludes the assistant does not work.
    UnavailableReason.NO_PASSAGE: (
        "Nothing in the documents this workspace has uploaded covers that. Upload the document "
        "that would answer it, or ask about something they contain."
    ),
    # The one refusal that names our own machinery, because a reader who is told
    # only "we could not answer" will ask the same question again and get the
    # same silence.
    UnavailableReason.UNCITED_CLAIM: (
        "We discarded the answer because it pointed at a passage it was never given. Nothing "
        "unverified was shown to you. Asking again is worth doing — this one is ours, not yours."
    ),
    # I1, visible. Narration's wording for this reason ends "the score above is
    # unaffected"; there is no score here, and saying so would be describing a
    # figure that is not on the screen. Same reason, different surface, which is
    # the whole argument for two maps.
    UnavailableReason.INVENTED_NUMBER: (
        "We discarded the answer because it stated a figure that appears in none of the passages "
        "it quoted. That is the check working, and it is ours rather than anything about your "
        "documents."
    ),
    # **A supported state, not an outage** (ADR 0003 + ADR 0011's pattern). The
    # sentence says what is switched off rather than apologising, because the
    # honest next step is an operator's, not the reader's.
    UnavailableReason.EMBEDDER_UNCONFIGURED: (
        "Searching your documents needs the embedding model, which is not switched on for this "
        "deployment. Nothing is wrong with your documents — until it is enabled, this assistant "
        "has no way to find the right passage."
    ),
    UnavailableReason.SCHEMA_INVALID: (
        "The answer came back in a shape we could not read, twice. That is ours to fix, and "
        "nothing half-formed was shown to you."
    ),
    # ADR 0011: no key is a documented configuration, not a fault.
    UnavailableReason.MODEL_UNAVAILABLE: (
        "The language model is not configured for this deployment, so there is nothing to write "
        "the answer. Your documents were not the problem."
    ),
    UnavailableReason.BUDGET_EXHAUSTED: (
        "This workspace has used its allowance of questions for today. It resets at midnight in "
        "your own reporting timezone."
    ),
    UnavailableReason.SKILL_DISABLED: (
        "Answering from documents has been switched off for this workspace. That is somebody's "
        "choice rather than a fault, and whoever administers the workspace can turn it back on."
    ),
    UnavailableReason.PROVIDER_FAILED: (
        "The language model did not respond. Nothing was lost — asking again is worth doing."
    ),
}


def sentence_for(reason: UnavailableReason) -> str:
    """The copy for one assistant refusal.

    Total over `ASSISTANT_REASONS`; `evals/test_assistant_grounding.py` proves
    it. The narration map is the other half and the two must not be crossed —
    `app/domain/narration.py` says why.
    """
    try:
        return _SENTENCES[reason]
    except KeyError:
        raise KeyError(
            f"{reason.value} is not a grounding verdict — `check` cannot reach it. "
            f"Narration tiles take their copy from app/domain/narration.py."
        ) from None


def permitted_numerals(passages: Iterable[Passage]) -> frozenset[str]:
    """Every figure an answer may state, having read these passages.

    A thin, named wrapper over `numerals_supplied` rather than its own parser.
    Reimplementing the numeral regex here would give the product two definitions
    of what counts as a figure, and the one that drifted would be this one —
    `pipeline.NUMBER` is deliberately greedy and the comment above it explains
    the asymmetry that makes greediness correct.
    """
    return numerals_supplied(*(passage.content for passage in passages))


def uncited(citations: Iterable[Citation], sent: Iterable[Passage]) -> set[UUID]:
    """Chunk ids the answer cited that were never retrieved for it.

    Membership is by chunk id and not by content: two passages can quote the
    same sentence, and what matters is whether the reader can open the thing
    they were pointed at.
    """
    available = {passage.id for passage in sent}
    return {citation.chunk_id for citation in citations if citation.chunk_id not in available}


def echoed_from_question(
    prose: str, cited: Iterable[Passage], question_numerals: frozenset[str]
) -> frozenset[str]:
    """Figures the answer states that came from the **question**, not a passage.

    Empty almost always. When it is not, the answer leaned on ADR 0062's
    permission, and `ask.py` records that on the `generation` row — the whole
    point of the narrowing is that an echo is visible afterwards rather than
    indistinguishable from a quotation.
    """
    stated = numerals_supplied(prose)
    return frozenset(stated & question_numerals) - permitted_numerals(cited)


def check(
    answer: AssistantAnswer,
    passages: Iterable[Passage],
    *,
    question_numerals: frozenset[str] = frozenset(),
) -> AssistantRefusal | None:
    """The gate. `None` means the answer may be shown, unchanged.

    Returns a refusal rather than raising because a refusal is a **product
    state** with copy of its own, not an exception — the same stance ADR 0011
    takes for an absent model. Raising would make the caller decide what to say,
    which is how two surfaces end up wording the same refusal differently.

    `capability_id` is never set here. Mapping a question to the capability that
    would answer it needs the question, which this function is not given, and
    ADR 0052's addition is explicit that a guessed capability is worse than
    none.

    **`question_numerals` is ADR 0062, and it is narrower than it looks.** A
    figure the customer typed is not an invention: asking *"who can approve
    3,000 rial?"* over a policy banded *"500 to 5,000"* was refused with
    *"it stated a figure that appears in none of the passages"* — the product
    calling the reader's own number fabricated. Passing the question's numerals
    here fixes that class.

    It applies **only to an answer that cites something**. An answer with no
    citation gets no permission at all, which is what stops the question
    becoming a channel for laundering a figure: *"is our revenue 5,000,000?"*
    cannot be echoed back by an answer that points at nothing.
    """
    sent = tuple(passages)

    if not sent:
        # Defence in depth. The caller is expected to refuse before reaching a
        # model at all — an answer produced from nothing is an answer produced
        # from the model's memory — but a guard that trusts its caller to have
        # already run it is not a guard.
        return _refuse(UnavailableReason.NO_PASSAGE)

    if uncited(answer.citations, sent):
        return _refuse(UnavailableReason.UNCITED_CLAIM)

    cited = tuple(p for p in sent if p.id in {c.chunk_id for c in answer.citations})
    permitted = permitted_numerals(cited)
    if answer.citations:
        # Only here. An uncited answer keeps ADR 0053's original, stricter set.
        permitted = frozenset(permitted | question_numerals)

    if invented_numbers(answer.prose, NOTHING_COMPUTED, also_permitted=permitted):
        return _refuse(UnavailableReason.INVENTED_NUMBER)

    return None


def _refuse(reason: UnavailableReason) -> AssistantRefusal:
    return AssistantRefusal(reason=reason, sentence=sentence_for(reason))
