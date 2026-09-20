"""Passages, on their way in. `doc/20` A6 step 5, pulled forward by A3 (ADR 0055).

**Why this exists before `ask.py` does.** A3's structural eval asserts that every
retrieved passage taints the turn. If the `Turn.read` loop lived in the eval's
own harness, that eval would assert the harness calls the function the harness
calls — green forever, and silent on the day the real composition forgets. The
taint has to happen in shipped code for the test to mean anything, so the part of
A6 that does it is here, and A6 calls this rather than repeating it.

Everything here is pure: no database, no model, no clock.

**Refs are opaque and assigned per call.** A chunk id in the prompt is a chunk id
in the model's output, and from there in a log, an error message, or a sentence
shown to somebody who should not have learned that the chunk exists. `p1`
carries no information outside this one call, which is the point — and because
the mapping back is held here rather than parsed out of the answer, a ref the
model invented resolves to nothing instead of to a row.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from uuid import UUID

from app.assistant.contracts import Citation
from app.domain.untrusted import Turn, UntrustedSource, wrap_untrusted
from app.retrieval.chunks import Passage


@dataclass(frozen=True, slots=True)
class Grounding:
    """What the model is shown, and the taint that showing it created.

    `turn` and `block` are produced together and must stay that way: a caller
    that rendered the block without reading the passages into a turn would have
    a prompt full of customer instructions and a turn that claims nothing
    untrusted has happened. Returning them as one object is what stops the two
    being wired up separately.
    """

    turn: Turn
    block: str
    """The fenced passages, ready to drop into a system prompt.

    **The fence is not the protection** — `untrusted.py`'s own words, and A3
    proves it by closing the fence from inside a payload. The protection is that
    `turn` is tainted; the fence is what lets a human reading the transcript see
    which sentence did it.
    """

    by_ref: Mapping[str, Passage] = field(default_factory=dict)

    @property
    def passages(self) -> tuple[Passage, ...]:
        return tuple(self.by_ref.values())


def prepare(passages: Sequence[Passage]) -> Grounding:
    """Fence the passages, taint the turn, and issue a ref for each.

    Order is preserved and refs are positional, so `p1` is the best match. That
    is information the model may act on, and it is information the *customer's
    own documents* produced — unlike a chunk id, which is information about our
    storage.
    """
    turn = Turn()
    by_ref: dict[str, Passage] = {}
    rendered: list[str] = []

    for position, passage in enumerate(passages, start=1):
        ref = f"p{position}"
        by_ref[ref] = passage
        block = wrap_untrusted(UntrustedSource.DOCUMENT, passage.content, ref=ref)
        turn.read(block)
        rendered.append(block.render())

    return Grounding(turn=turn, block="\n\n".join(rendered), by_ref=by_ref)


def resolve(
    grounding: Grounding, cited: Iterable[str]
) -> tuple[tuple[Citation, ...], tuple[str, ...]]:
    """Turn the refs an answer claims into citations, and name the ones we never
    issued.

    Returns `(citations, unknown)`. **`unknown` being non-empty is a refusal**,
    not a set to drop quietly: a model that cited `p7` when six passages were
    sent either miscounted or was told to say it, and in both cases the rest of
    the answer was produced under an assumption that did not hold.

    Dropping them silently is the tempting bug, because the answer usually still
    reads fine with one citation removed.

    **Deduplicated by chunk, first mention winning.** A model answering in three
    segments that all rest on the same passage cites it three times, which is
    correct of it and wrong as a list of sources: `generation_citation` holds one
    row per answer per chunk (ADR 0056), and the panel keys its citation list on
    the chunk id. Both broke here before this existed — a real answer from a real
    model returned a 500 on the unique constraint, which is that constraint doing
    exactly what its comment says it is for.

    Order is the answer's own, not the retrieval's: a reader follows citations in
    the order the prose raised them.
    """
    citations: list[Citation] = []
    unknown: list[str] = []
    seen: set[UUID] = set()

    for ref in cited:
        passage = grounding.by_ref.get(ref)
        if passage is None:
            unknown.append(ref)
            continue
        if passage.id in seen:
            continue
        seen.add(passage.id)
        citations.append(
            Citation(
                chunk_id=passage.id,
                document_id=passage.document_id,
                source_label=passage.source_label,
                source_page=passage.source_page,
            )
        )

    return tuple(citations), tuple(unknown)
