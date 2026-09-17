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
from datetime import date, datetime
from typing import Final
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.calculators.pipeline import Deal
from app.domain.session import ScopedSession

TYPED: Final = "nexus"
"""The `provider` a hand-typed deal carries — ADR 0038 (D30).

`sales.deals_lite` reuses this table rather than adding one, and **the whole
safety of that reuse is the partition below.** A provider name is what tells a
synced deal from one somebody wrote down.
"""

_SYNCED: Final = sa.text(
    """
    SELECT external_id, amount_minor, currency, stage, closes_on, fetched_at
      FROM crm_deal
     WHERE workspace_id = :w AND provider <> :typed
     ORDER BY fetched_at DESC, external_id
    """
)
"""Every deal a **provider** told us about, newest fetch first.

**The `provider <> :typed` clause is not a tidy-up.** Without it this query
returns hand-typed deals as well, and `sales.pipeline_board` reports them as
though a CRM had said so — a typed number and a measured one rendered
identically, which is the thing `doc/05` §0 exists to prevent. It would be
silent: the figure would look exactly as plausible as before.

**No `LIMIT`.** A pipeline computed over the first hundred rows and presented as
the pipeline is a wrong number with a plausible denominator — the failure the
adapter's `truncated` flag exists to report, and it would be reintroduced here by
a cap added for tidiness.

`ORDER BY fetched_at DESC, external_id` is stable: the second key is what stops
two deals fetched in the same instant swapping places between requests, which
would make the working drawer look rewritten while saying the same thing.
"""


_TYPED: Final = sa.text(
    """
    SELECT external_id, amount_minor, currency, stage, closes_on, fetched_at
      FROM crm_deal
     WHERE workspace_id = :w AND provider = :typed
     ORDER BY fetched_at DESC, external_id
    """
)
"""Every deal somebody wrote down here. The other half of the partition."""


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
    rows = (await db.execute(_SYNCED, {"w": str(scope.workspace_id), "typed": TYPED})).all()
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


_TYPED_ROWS: Final = sa.text(
    """
    SELECT id, name, amount_minor, currency, stage, closes_on
      FROM crm_deal
     WHERE workspace_id = :w AND provider = :typed
     ORDER BY closes_on NULLS LAST, name
    """
)
"""The typed deals **as records**, for the surface that wrote them.

Separate from `_TYPED` on purpose. `Deal` is the calculator's shape and carries
no database id and no name — deliberately, because a pipeline total needs
neither and a calculator that could see a row id could start keying on one. A
list somebody edits needs both.
"""


@dataclass(frozen=True, slots=True)
class TypedDeal:
    """One hand-recorded deal, as the write surface sees it."""

    id: UUID
    name: str | None
    amount_minor: int | None
    currency: str | None
    stage: str | None
    closes_on: date | None


async def typed_deal_records(db: AsyncSession, scope: ScopedSession) -> list[TypedDeal]:
    """Every deal this workspace typed, for listing and removing.

    A list rather than `None`-or-a-list: this feeds a page section that renders
    nothing when empty, and there is no "we have never looked" state to
    distinguish — nobody fetches these, somebody types them.
    """
    rows = (await db.execute(_TYPED_ROWS, {"w": str(scope.workspace_id), "typed": TYPED})).all()
    return [
        TypedDeal(
            id=row.id,
            name=row.name,
            amount_minor=row.amount_minor,
            currency=row.currency,
            stage=row.stage,
            closes_on=row.closes_on,
        )
        for row in rows
    ]


async def current_typed_deals(db: AsyncSession, scope: ScopedSession) -> DealSnapshot | None:
    """The deals somebody recorded by hand, or `None` if nobody has — ADR 0038.

    Deliberately the same shape as `current_deals`, because a typed deal and a
    synced one are the same *kind* of fact with different standing. What differs
    is the provenance the figure carries, not the arithmetic —
    `calculators/pipeline.py` is untouched by this and that was the argument for
    reusing the table at all.

    `fetched_at` here is the moment somebody saved the row rather than the moment
    we asked a provider. The column's name is wider than `0031`'s comment made
    it; the figure never says "read from your CRM" about one of these, because
    `self_reported` decides that sentence.
    """
    rows = (await db.execute(_TYPED, {"w": str(scope.workspace_id), "typed": TYPED})).all()
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
        fetched_at=rows[0].fetched_at,
        provider=TYPED,
    )
