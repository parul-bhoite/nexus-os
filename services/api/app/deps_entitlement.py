"""The entitlement gate: a workspace needs an active plan or trial to use the
product surfaces. ADR 0084.

Server-side, on the API — the trust boundary. `apps/web/middleware.ts` is
presence-only by its own design (it cannot resolve a session, let alone an
entitlement, without the database), so a real gate has to live here. The Next.js
dashboard page carries a second, redirect-before-render copy for the founder's
sake; this is the one that actually refuses.

**Not a data-security control.** Row-level security already makes a workspace's
data invisible to every other tenant, whether or not anyone has paid. This gate
governs *use*: an unentitled workspace gets `402 Payment Required` from the
product endpoints, and the web turns that into a redirect to the payment step. A
402 rather than a 403 because nothing about the caller's *authority* is wrong —
they may own the workspace outright; what is missing is a plan.
"""

from __future__ import annotations

from fastapi import HTTPException, status

from app.deps import CurrentScope
from app.domain.pricing import entitlement_for
from app.retrieval.scoped import scoped_connection


async def require_entitled(scope: CurrentScope) -> None:
    """Refuse the request with 402 unless this workspace has a live plan or trial.

    Its own short scoped transaction: the check is one small read and it must run
    before the handler's own reads, so folding it into `observed_sources` would
    couple the paywall to the dashboard's data assembly. The cost is one extra
    round trip on a surface that already makes several.
    """
    async with scoped_connection(scope) as db:
        entitlement = await entitlement_for(db, workspace_id=scope.workspace_id)

    if not entitlement.entitled:
        raise HTTPException(
            status.HTTP_402_PAYMENT_REQUIRED,
            "This workspace needs an active plan or trial to open its dashboard.",
        )
