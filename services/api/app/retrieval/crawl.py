"""The only reader of crawled page signals.

**No department predicate, and its absence is a decision rather than an
omission.** `chunks.py`'s `PREDICATE` filters L3 rows to the caller's
departments, because an uploaded document can belong to Finance and not to
Marketing. A company's own public website has no such vantage point: it is L1,
every member may read it, and there is no sense in which a title tag is
privileged to one department. What scopes these rows is the workspace, and
nothing else.

So the whole predicate is `workspace_id = :ws AND superseded_at IS NULL`. The
workspace clause doubles the RLS policy for the same reason `chunks.py` doubles
it: it is what makes `ix_page_signals_current` usable, and it is the same value
the policy compares, so the two cannot disagree.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.page_signals import PageSignals, signals_from_json
from app.domain.session import ScopedSession

_CURRENT: Final = sa.text(
    """
    SELECT url, signals, captured_at, count(*) OVER () AS pages_captured
      FROM page_signals
     WHERE workspace_id = :ws
       AND superseded_at IS NULL
     ORDER BY position
     LIMIT 1
    """
)
"""`ORDER BY position LIMIT 1` — the page the crawl led with.

`site.plan` orders the crawl by priority and the writer stores `position` as the
index into the pages it *kept*, so position 0 is a documented rule rather than a
guess about which URL is the home page. `count(*) OVER ()` rides along because
the alternative is a second round trip to `us-east-2` for a number the tile
uses only as context.
"""


@dataclass(frozen=True, slots=True)
class CrawlSnapshot:
    """One page's signals, and enough to say where they came from.

    `url` and `captured_at` are not decoration: a score whose page cannot be
    opened, or whose date is unknown, is a number nobody can check — and for a
    reader that is indistinguishable from one we invented.
    """

    signals: PageSignals
    url: str
    captured_at: datetime
    pages_captured: int
    """How many pages this crawl kept. Context for the figure, not an input to
    it: the calculators score a single page, and saying so is more honest than
    implying the score covers the site."""


async def current_page_signals(db: AsyncSession, scope: ScopedSession) -> CrawlSnapshot | None:
    """The page this workspace's most recent crawl led with, or `None`.

    **`None` is load-bearing.** It means no crawl has been read, and the caller
    renders that as `locked` — because the missing input is the crawl itself,
    not a connector somebody could switch on. Returning a `CrawlSnapshot` with
    an empty `PageSignals` instead would score 0 out of 65 and tell a founder
    their website failed every check, when the truth is that nobody has looked
    at it. That is I10, and this is the boundary where it would be lost.
    """
    row = (await db.execute(_CURRENT, {"ws": str(scope.workspace_id)})).mappings().first()
    if row is None:
        return None

    payload: dict[str, Any] = dict(row["signals"])
    return CrawlSnapshot(
        signals=signals_from_json(payload),
        url=str(row["url"]),
        captured_at=row["captured_at"],
        pages_captured=int(row["pages_captured"]),
    )
