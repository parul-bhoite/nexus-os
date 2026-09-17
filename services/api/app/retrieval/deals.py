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

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Final
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy import Row
from sqlalchemy.ext.asyncio import AsyncSession

from app.calculators.pipeline import Deal
from app.domain.session import ScopedSession

TYPED: Final = "nexus"
"""The `provider` a hand-typed deal carries — ADR 0038 (D30).

`sales.deals_lite` reuses this table rather than adding one, and **the whole
safety of that reuse is the partition below.** A provider name is what tells a
synced deal from one somebody wrote down.
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


async def both_populations(
    db: AsyncSession, scope: ScopedSession
) -> tuple[DealSnapshot | None, DealSnapshot | None]:
    """Synced deals and typed deals, in **one round trip** — `(synced, typed)`.

    `current_deals` and `current_typed_deals` read the same table with opposite
    `provider` predicates, so asking twice is a round trip spent on a `WHERE`
    clause. The surface needs both on every load; against a database this machine
    reaches in about a second per statement, that second buys nothing.

    **The partition still happens, and still cannot be skipped** (ADR 0038) — it
    moves from the predicate to the loop below, where it is just as explicit. A
    typed deal reaching `sales.pipeline_board` would be reported as though a CRM
    had said so, which is the failure the partition exists to prevent.

    The two functions remain, because they are the honest thing for a caller that
    wants one population; this is for the caller that wants both.
    """
    rows = (await db.execute(_ALL, {"w": str(scope.workspace_id)})).all()
    synced = [row for row in rows if row.provider != TYPED]
    typed = [row for row in rows if row.provider == TYPED]

    return (
        _snapshot(synced, provider="crm"),
        _snapshot(typed, provider=TYPED),
    )


def _snapshot(rows: Sequence[Row[Any]], *, provider: str) -> DealSnapshot | None:
    """One population's snapshot, or `None` when it has none.

    **`None` is not an empty list**, and the distinction is the whole reason
    `current_deals` documents it: no rows means no sync has happened and the tile
    is `locked`; an empty list would mean a connected CRM with nothing open,
    which is a real pipeline of zero (I10). Shared so the two populations cannot
    answer that question differently.
    """
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
        # The newest fetch in the set. The ORDER BY puts it first, and it is the
        # honest date for the figure: the oldest would claim the pipeline is
        # staler than it is.
        fetched_at=rows[0].fetched_at,
        provider=provider,
    )


_ALL: Final = sa.text(
    """
    SELECT provider, external_id, amount_minor, currency, stage, closes_on, fetched_at
      FROM crm_deal
     WHERE workspace_id = :w
     ORDER BY fetched_at DESC, external_id
    """
)
"""Both populations, for the caller that needs both. `provider` is selected so
the partition can be made in Python rather than by asking twice."""

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
