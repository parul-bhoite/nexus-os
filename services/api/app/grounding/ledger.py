"""The generation ledger: what was spent, and what every answer was made of.

`doc/12` P14. Two jobs, one table, and they are the same job seen from either
end. Reading `generation` backwards answers *"where did this number come from?"*
Reading it forwards answers *"what has this workspace spent today?"* — and
migration 0023 built an index for each direction while nothing wrote a single
row.

## Every outcome is recorded, including the refusals

An `unavailable` generation is the row somebody suspicious will actually read.
*"The tile said it could not compute this"* is a support conversation, and
without a row it is an unfalsifiable one — nobody can tell a missing input from
a schema failure from an exhausted budget, and all three look identical on the
screen. `ck_generation_reason_matches_outcome` makes the reason mandatory for
exactly this reason, so a row is refused rather than stored uninformative.

## The budget is counted, never estimated

`tenant_daily_token_budget` and `user_daily_token_budget` have sat in
`config.py` since M0 with nothing reading them. They are counted here from the
rows themselves rather than from a cache or a counter, because a counter is a
second source of truth about spending and the one thing worse than an
overspend is an overspend nobody can reconstruct.

**Both budgets bind, and the tighter one wins.** The tenant limit protects us
from a workspace; the user limit protects a workspace from one of its own
members. Neither implies the other — an owner can exhaust their own allowance
while the company has most of its day left.

**A day is a day in the report timezone**, not in UTC. A GCC founder whose
budget resets at 4am local time because the server counts in UTC has a budget
that resets in the middle of their working morning, which reads as an outage.
"""

from __future__ import annotations

import json
from typing import Any, Final
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.grounding.pipeline import Answer, Budgets, Outcome

_SPENT_SQL: Final = """
    SELECT
      COALESCE(SUM(input_tokens + output_tokens), 0) AS tenant,
      COALESCE(SUM(CASE WHEN requested_by_user_id = :u
                        THEN input_tokens + output_tokens ELSE 0 END), 0) AS "user"
      FROM generation
     WHERE workspace_id = :w
       AND created_at >= date_trunc('day', now() AT TIME ZONE :tz) AT TIME ZONE :tz
"""
"""One query for both numbers.

Two queries would be two round trips to `us-east-2` on the hot path of every
generation, and — worse — two moments in time. A tenant total read a second
before a user total can disagree with it, and the disagreement always favours
spending.

## The second `AT TIME ZONE :tz` is load-bearing, and it was missing

`now() AT TIME ZONE :tz` converts to a **naive** local timestamp, and
`date_trunc` keeps it naive. Comparing a naive timestamp against a
`timestamptz` column makes Postgres reinterpret it in the **session**
timezone — GMT on this deployment — so local midnight in Muscat became
midnight *UTC*. Converting back with a second `AT TIME ZONE :tz` is what turns
naive local midnight into the instant it actually was.

**The window this opened was four hours wide, every day.** Between 20:00 and
24:00 UTC the cutoff sat in the future, so the query summed nothing, both
budgets read zero, and `exhausted` could not become true — the daily token
budget was simply unenforced for a sixth of each day, and the four hours moved
with the workspace's own reporting timezone.

Found at 22:13 UTC by a full-suite run, which is the only reason it was found
at all: three tests in `test_grounding_ledger_db.py` fail inside that window
and pass every other hour of the day. Same shape as the fixed-window rate-limit
boundary — a test that encodes "now" is a test that is green most of the time.
`test_the_day_boundary_is_the_workspaces_midnight_not_utc` pins it against an
explicit timestamp rather than against the clock.
"""


async def budgets_for(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    user_id: UUID | None,
    settings: Settings,
    timezone: str,
) -> Budgets:
    """What is left today, for this workspace and this person.

    `user_id` is nullable because some generations have no human asker — a
    scheduled brief, a background refresh. Those still count against the tenant
    and cannot exhaust anybody's personal allowance, which is the honest
    arrangement: nobody should lose their own budget to a job they did not run.
    """
    row = (
        await db.execute(
            text(_SPENT_SQL),
            {"w": str(workspace_id), "u": str(user_id) if user_id else None, "tz": timezone},
        )
    ).one()

    return Budgets(
        tenant_spent=int(row.tenant),
        tenant_limit=settings.tenant_daily_token_budget,
        user_spent=int(row.user),
        user_limit=settings.user_daily_token_budget,
    )


_INSERT_SQL: Final = """
    INSERT INTO generation
      (workspace_id, module, prompt_version, input_snapshot, calculation_trace,
       scope_key, outcome, unavailable_reason, input_tokens, output_tokens,
       cost_micros, requested_by_user_id)
    VALUES
      (:w, :module, :version, CAST(:snapshot AS json), CAST(:trace AS json),
       :scope_key, :outcome, :reason, :input_tokens, :output_tokens,
       :cost_micros, :user)
    RETURNING id
"""


async def record(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    module: str,
    prompt_version: str,
    answer: Answer,
    input_snapshot: dict[str, Any],
    calculation_trace: dict[str, Any],
    scope_key: str,
    input_tokens: int = 0,
    output_tokens: int = 0,
    requested_by_user_id: UUID | None = None,
) -> UUID:
    """Write the row this answer traces to, and return its id.

    **On the caller's session, inside their transaction** — the same rule
    `audit.record` follows, for the same reason: a ledger row that survives a
    rolled-back answer is a lie about what happened, and one that vanishes when
    the answer is kept leaves a number on a screen with nothing behind it.

    The insert relies on the caller having set `nexus.workspace_id`, which
    `scoped_connection` does. `generation` carries `FORCE ROW LEVEL SECURITY`
    with a `WITH CHECK` on `workspace_id`, so an unscoped insert is refused
    outright rather than landing in the wrong tenant.

    `cost_micros` stays 0 and is not estimated. There is no price table in the
    repository, and a made-up cost in a column called `cost_micros` is exactly
    the kind of number this whole phase exists to refuse. The budget is measured
    in tokens, which are counted; money arrives when a price list does.
    """
    reason = answer.reason.value if answer.reason else ""

    # The constraint says an unavailable outcome must carry a reason, and this
    # says the same thing one layer earlier — where the caller can be told which
    # of its branches forgot, rather than reading a constraint name from Neon.
    if (answer.outcome is Outcome.UNAVAILABLE) != bool(reason):
        raise ValueError(
            f"{module}: outcome {answer.outcome.value} with reason {reason!r}."
            " An unavailable generation must say which kind it is, and an"
            " answered one must not claim a reason."
        )

    result = await db.execute(
        text(_INSERT_SQL),
        {
            "w": str(workspace_id),
            "module": module,
            "version": prompt_version,
            # `json.dumps` rather than passing the dict: asyncpg binds a Python
            # dict to a text parameter as its `repr`, which is single-quoted and
            # not JSON. It parses back as a string containing a dict.
            "snapshot": json.dumps(input_snapshot, default=str, sort_keys=True),
            "trace": json.dumps(calculation_trace, default=str, sort_keys=True),
            "scope_key": scope_key,
            "outcome": answer.outcome.value,
            "reason": reason,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cost_micros": 0,
            "user": str(requested_by_user_id) if requested_by_user_id else None,
        },
    )
    return UUID(str(result.scalar_one()))
