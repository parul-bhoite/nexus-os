"""What is still open on the founder's side, and what answering it would change.

`doc/14` step 5. The region that replaces the reference mock's *Risks /
Opportunities* columns — those needed a risk engine nobody has built, while
every line here is already derivable from the question bank.

## Answering informs; it does not unlock

The design's first draft said seven capabilities were "unlockable by answering".
The real figure is **zero**: all twenty-four fact-consuming tiles also require a
source, so no question in the bank switches a tile on by itself. That was found
by reading the registry rather than by reasoning about it, and the copy now makes
the smaller, true claim.

## Two tiers, and the split is the useful part

A question whose consumer already **produces a figure** changes a number the
founder can see today — `arabic_in_scope` changes what `marketing.seo_gaps`
counts as a gap, and that tile is on the page. A question whose consumer is not
built changes nothing yet, however important it will be.

Presenting those together would be the same over-claim ADR 0030 refuses at the
capability level: it would let a founder believe the product is waiting on them
when it is mostly waiting on us. So the first tier is listed and the second is
counted.

## Nothing here is ranked by importance

There is no scoring of which question matters more. `Question.why` is the
bank's own sentence about what the answer is for, and ordering by anything we
invented would be an opinion dressed as arithmetic.
"""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass

from app.domain.onboarding import Question
from app.domain.registry import BY_ID
from app.domain.scopes import Department


@dataclass(frozen=True, slots=True)
class OpenQuestion:
    key: str
    department: str
    prompt: str
    """The bank's own wording. Never rephrased here — the question a founder
    sees on the dashboard has to be the question the setup flow will ask."""

    why: str
    """What the answer is for, from the bank. The guard against a field with no
    consumer, which doc 06 calls a form field rather than a question."""

    consumed_by: str
    consumer_name: str
    """The capability's display name, so the line reads as a sentence rather
    than as an id."""


@dataclass(frozen=True, slots=True)
class OpenQuestions:
    changes_a_figure: tuple[OpenQuestion, ...]
    """Answering one of these changes a number already on the page."""

    waiting_on_us: int
    """Open questions whose consumer is not built. Counted rather than listed:
    a founder cannot act on them usefully today, and a list of forty would bury
    the handful that can."""

    total: int


def compose(
    *,
    bank: dict[Department, tuple[Question, ...]],
    departments: frozenset[Department],
    answered: Collection[tuple[str, str]],
    measuring: Collection[str],
) -> OpenQuestions:
    """Every unanswered question this reader can reach, split by what it moves.

    `answered` carries `(department, key)` pairs and a **proposed** answer is not
    among them — a block that looked complete because a Contributor filled it in
    would hide the thing the review gate exists to surface.

    Scoped by the caller for the reason ADR 0029 gives about the brief: the
    questions are `L3_DEPARTMENT` by default, so a composition over every
    department would put another department's questions on a contributor's
    dashboard.
    """
    live: list[OpenQuestion] = []
    later = 0

    for department in sorted(departments, key=lambda d: d.value):
        for question in bank.get(department, ()):
            if (department.value, question.key) in answered:
                continue

            consumer = BY_ID.get(question.consumed_by)
            if consumer is not None and question.consumed_by in measuring:
                live.append(
                    OpenQuestion(
                        key=question.key,
                        department=department.value,
                        prompt=question.prompt,
                        why=question.why,
                        consumed_by=question.consumed_by,
                        consumer_name=consumer.name,
                    )
                )
            else:
                later += 1

    return OpenQuestions(
        changes_a_figure=tuple(live),
        waiting_on_us=later,
        total=len(live) + later,
    )
