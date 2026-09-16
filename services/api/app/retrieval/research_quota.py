"""How many research runs this workspace has started **this month, where it lives**.

Lifted out of `routes/research.py`, which counted with a bare
`date_trunc('month', now())`. That truncates in the *session* timezone — GMT on
this deployment — so the manual allowance turned over on the **UTC**
month boundary rather than the workspace's.

Every GCC timezone is ahead of UTC, so that cutoff sits *later* than the real
one — four hours later for Muscat. The runs a founder starts in the first hours
of their own month fall before it and are never counted against it, so the
allowance is quietly larger than the three we promised. The error runs in the
direction of generosity, which is exactly why nobody would ever report it.

**Milder than the M33 ledger bug, and worth saying why.** There both sides went
naive and Postgres reinterpreted the cutoff, opening a four-hour window each day
in which the budget was simply unenforced. Here both sides stay `timestamptz`,
so the comparison is sound and only the boundary is in the wrong place.

Postgres 18.4 has three-argument `date_trunc(field, timestamptz, zone)`, which
returns a `timestamptz`. That is what keeps M33's double-conversion trap from
recurring: there is no `AT TIME ZONE` round trip to get half of right.

The `now` parameter exists so the boundary is testable without freezing the
clock, mirroring `connectors.rate_limit.consume(..., now=…)`. It is never passed
in production.
"""

from __future__ import annotations

from datetime import datetime
from typing import Final

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.session import ScopedSession

_MANUAL_RUNS_SQL: Final = sa.text(
    """
    SELECT count(*)
      FROM research_run
     WHERE requested_by_user_id IS NOT NULL
       AND requested_at >= date_trunc(
             'month',
             COALESCE(CAST(:now AS timestamptz), now()),
             COALESCE((SELECT report_timezone FROM workspace WHERE id = :w), 'UTC')
           )
    """
)
"""Manual runs since the workspace's own start of month.

**`requested_by_user_id IS NOT NULL` is what makes a run manual.** The weekly
sweep has no requester, and charging it to the founder's three would mean the
product quietly consuming the allowance it gave them.

**The `COALESCE` on the timezone is unreachable today, and it stays.** Both
routes to a `NULL` are closed: migration 0027 made `report_timezone` `NOT NULL
DEFAULT 'Asia/Muscat'`, and `:w` is `scope.workspace_id`, which is the same
value `scoped_connection` writes into the GUC the RLS policy compares — so the
subselect cannot miss its row either.

It is kept because of what the `NULL` would do rather than how likely it is:
`date_trunc(…, NULL)` is `NULL`, `requested_at >= NULL` is `NULL`, no row
qualifies, the count is zero — and zero does not read as an error, it reads as
**an allowance nobody has touched**. A nullable column or a caller passing some
other `:w` would not produce a wrong boundary; it would produce an *unlimited*
allowance, on a screen that looked correct. Four characters turn that into the
bug this module was written to fix.

Asserted against the SQL in `test_research_quota_month.py` rather than through a
result, because by the paragraph above there is no input that reaches it.

No `workspace_id = :w` on `research_run` itself — RLS already restricts it, and
the `:w` here names the row whose timezone we want rather than the rows we
count.
"""


async def manual_runs_this_month(
    db: AsyncSession, scope: ScopedSession, *, now: datetime | None = None
) -> int:
    """Manual runs started since the start of this workspace's month."""
    return int(
        (
            await db.execute(
                _MANUAL_RUNS_SQL,
                # **The `datetime` itself, never `isoformat()`.** asyncpg binds
                # by type rather than by literal text, and the `CAST` above
                # types this parameter as `timestamptz` — for which it demands
                # a `datetime` and refuses to parse a string, with a `DataError`
                # rather than a wrong answer. Same trap as `interval`, which
                # wants a `timedelta`.
                {"now": now, "w": str(scope.workspace_id)},
            )
        ).scalar_one()
    )
