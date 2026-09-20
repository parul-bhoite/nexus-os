"""What a question, an answer and a refusal are. No behaviour.

`doc/20` A1. Every field here is shaped by a rule that already exists somewhere
else in the product, and the docstrings say which — a contract that invented its
own vocabulary would be a second answer to a question already settled.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.domain.scopes import Department
from app.grounding.pipeline import UnavailableReason


@dataclass(frozen=True, slots=True)
class Question:
    """What was asked, and the department it was asked of.

    **The department is not a filter the caller may choose.** It is the director
    whose page the question was asked from, and what may be *read* is decided by
    the `ScopedSession` passed alongside — `retrieval/chunks.py` takes no
    identity argument for exactly this reason. Carrying the department here says
    which director is answering, never who may see what.
    """

    text: str
    department: Department


@dataclass(frozen=True, slots=True)
class Citation:
    """Where one claim came from, precise enough to open.

    Mirrors `retrieval.chunks.Passage` rather than restating it loosely: a
    citation a reader cannot follow to the page it came from is decoration, and
    `source_label`/`source_page` are what make it followable.
    """

    chunk_id: UUID
    document_id: UUID
    source_label: str | None
    source_page: int | None


@dataclass(frozen=True, slots=True)
class AssistantAnswer:
    """Prose, and the passages it is allowed to have come from.

    `citations` is not decoration and not optional: A2's check rejects an answer
    citing a reference that was never sent, and the numeral rule permits only
    figures that appear in these passages' text. An answer with no citations is
    therefore an answer with no permitted numerals — which is the correct and
    deliberate consequence, not an edge case to smooth over.
    """

    prose: str
    citations: tuple[Citation, ...]


@dataclass(frozen=True, slots=True)
class AssistantRefusal:
    """No answer, and why — with the capability that would answer it, if known.

    **`capability_id` is optional and is never guessed** (ADR 0052's addition).
    Naming a capability sends somebody to connect a system; naming the wrong one
    sends them to connect a system that would not have helped, which is worse
    than saying nothing. So it is populated only where the question is one the
    product already maps to a capability, and left `None` otherwise.

    **The sentence is not built here.** `domain/dashboards.unlock_for_sources`
    already turns a capability's missing sources into "Needs X and Y.", and one
    wording for unlocks across the product is the point of that function. This
    carries the id; the route renders it. That also keeps this package out of the
    dashboard domain, which the import allowlist enforces.
    """

    reason: UnavailableReason
    sentence: str
    """What to show the reader. Always specific — `UnavailableReason`'s own
    docstring: "unavailable" alone tells a founder nothing about whether to
    wait, connect something, or ask us."""

    capability_id: str | None = None
