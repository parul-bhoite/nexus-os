"""What one question may cost, and how often one person may ask. `doc/20` A7.

Shape fixed by **ADR 0058**: the assistant shares the existing daily budgets
rather than getting a third, and the two things that actually bound spend live
here — a **per-question ceiling** and a **per-user rate limit**.

The daily budget alone is not enough, and the gap is specific. `budgets_for`
looks at what has already been spent, so it can only stop the question *after*
the expensive one has been paid for. A single question retrieving 200 long
passages is inside the daily allowance right up until it is charged, and then
it has spent a large fraction of the day. The ceiling refuses that one before
the call.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Final

from sqlalchemy.ext.asyncio import AsyncSession

from app.connectors.rate_limit import Limit, check_and_increment
from app.retrieval.chunks import Passage

MAX_QUESTION_CHARS: Final = 1_000
"""A question, not a document.

Pasting a contract into the box and asking "what do you think" is the shape this
refuses. It is also the cheapest possible defence against a prompt-stuffing
attempt, though not a serious one — the fence and the empty tool set are.
"""

MAX_GROUNDING_CHARS: Final = 60_000
"""The ceiling, in characters rather than tokens.

**Characters on purpose.** Counting tokens needs the vendor's tokeniser, which
`app/assistant/` may not import (ADR 0011's boundary, enforced by
`tests/test_assistant_boundary.py`) — and an estimate dressed up as a token
count is worse than an honest character count, because the next reader trusts
the units. ~60k characters is roughly 15k tokens for English prose; the margin
absorbs the error.
"""

ASK_LIMIT: Final = Limit(bucket_prefix="assistant_ask", max_count=10, window=timedelta(hours=1))
"""Ten questions an hour, per user.

Chosen against the **timing oracle** rather than against cost. `doc/20` §5 Q6.3
accepts that a fast refusal and a slow answer are distinguishable, which lets a
caller probe for whether content exists. That leak is real and this plan does
not close it — what this limit does is bound the probing rate, which is the
difference between a leak and an enumeration.
"""


class QuestionTooLargeError(ValueError):
    """The question or its grounding exceeds the per-question ceiling."""


def check_question(text: str) -> None:
    if len(text) > MAX_QUESTION_CHARS:
        raise QuestionTooLargeError(
            f"a question is {len(text)} characters, over the {MAX_QUESTION_CHARS} ceiling"
        )


def check_grounding(passages: tuple[Passage, ...] | list[Passage]) -> None:
    """Refuse before the call, not after the bill.

    Measured on the passages rather than on the rendered block so the number
    means the same thing if the fence's wording changes.
    """
    total = sum(len(p.content) for p in passages)
    if total > MAX_GROUNDING_CHARS:
        raise QuestionTooLargeError(
            f"{len(passages)} passages total {total} characters, over the "
            f"{MAX_GROUNDING_CHARS} ceiling for one question"
        )


async def consume_ask(db: AsyncSession, *, user_id: str) -> None:
    """One unit against this user's ask bucket, or `RateLimited`.

    Keyed per user rather than per workspace: the limit is about one person
    probing, and a workspace-wide bucket would let one user's questions refuse
    a colleague's.
    """
    await check_and_increment(db, ASK_LIMIT, user_id)
