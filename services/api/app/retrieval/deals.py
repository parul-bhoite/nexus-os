"""This workspace's CRM deals, for the calculator to count.

I2/I3: takes a `ScopedSession`, never a `user_id`, and the RLS policy on
`crm_deal` is the floor the explicit `workspace_id = :w` doubles — the reason
`retrieval/crawl.py` gives, which is that it makes the index usable and compares
the same value the policy does.

## Rows, not a figure

This returns deals. `calculators/pipeline.py` counts them. The separation is I1's
plumbing and it is worth being exact about why: a total computed in SQL would be
a number produced outside `calculators/`, reproducible only by re-running a query
nobody kept, and the working drawer would have nothing to show.

`SUM()` in the SELECT would also make the currency problem invisible. Postgres
will happily add fils to cents; the calculator refuses, and it can only refuse
because it sees the rows.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Final

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.calculators.pipeline import Deal
from app.domain.session import ScopedSession

_DEALS: Final = sa.text(
    """
    SELECT external_id, amount_minor, currency, stage, closes_on, fetched_at
      FROM crm_deal
     WHERE workspace_id = :w
     ORDER BY fetched_at DESC, external_id
    """
)
"""Every deal this workspace has, newest fetch first.

**No `LIMIT`.** A pipeline computed over the first hundred rows and presented as
the pipeline is a wrong number with a plausible denominator — the failure the
adapter's `truncated` flag exists to report, and it would be reintroduced here by
a cap added for tidiness.

`ORDER BY fetched_at DESC, external_id` is stable: the second key is what stops
two deals fetched in the same instant swapping places between requests, which
would make the working drawer look rewritten while saying the same thing.
"""


@dataclass(frozen=True, slots=True)
class DealSnapshot:
    """The deals, and when they were read.

    `fetched_at` travels with them for the same reason `CrawlSnapshot` carries
    `captured_at`: a figure whose date is unknown is a figure nobody can check,
    and for a reader that is indistinguishable from one we invented.
    """

    deals: list[Deal]
    fetched_at: datetime
    provider: str


async def current_deals(db: AsyncSession, scope: ScopedSession) -> DealSnapshot | None:
    """This workspace's deals, or `None` if none have ever been read.

    **`None` is load-bearing and is not an empty list.** No rows means no sync
    has happened — the tile is `locked` and should say so. An empty list means a
    connected CRM with no open deals, which is a real pipeline of zero. Collapsing
    the two would let "we have never looked" render as "you have no deals" (I10).
    """
    rows = (await db.execute(_DEALS, {"w": str(scope.workspace_id)})).all()
    if not rows:
        return None

    return DealSnapshot(
        deals=[
            Deal(
                external_id=str(row.external_id),
                amount_minor=row.amount_minor,
                currency=row.currency,
                stage=row.stage,
                closes_on=row.closes_on,
            )
            for row in rows
        ],
        # The newest fetch in the set. `ORDER BY fetched_at DESC` puts it first,
        # and it is the honest date for the figure: the oldest would claim the
        # pipeline is staler than it is.
        fetched_at=rows[0].fetched_at,
        provider="crm",
    )
