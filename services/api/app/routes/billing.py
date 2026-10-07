"""The onboarding Payment step, over HTTP.

Quote, pay, start a trial, and check entitlement — plus two admin endpoints
over the rate card itself. `app/domain/pricing.py` does the computation and the
reads; this module is the thin HTTP wrapper doc 07 M1 requires of a router.

**No `_require_model()` here.** Unlike `onboarding_agent.py`, nothing in this
router calls a language model — pricing is a table lookup, and ADR 0022 is
about the guided interview, not every onboarding screen.

## Who may pay or start a trial

Any authenticated member of the workspace — the same authority `CurrentScope`
already grants every other onboarding endpoint. This is a workspace-level
commitment (what the whole company is billed), not a department-scoped action,
so there is no narrower role gate to add on top of being a member at all.

## The admin endpoints

`GET /admin/prices` and `PUT /admin/prices/{kind}/{key}` are gated on
`Settings.platform_admin_email_set` — see `config.py` for why this is an
interim email allowlist rather than a role. The check reads the caller's own
`app_user.email`, never a value the client supplies, for the same reason every
other authorisation decision in this codebase is server-side: a client that
could name its own email as "admin" would not be gated at all.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.auth.csrf import require_csrf
from app.config import Settings, get_settings
from app.deps import CurrentScope
from app.domain.pricing import Entitlement, entitlement_for, quote_for
from app.logging import get_logger
from app.retrieval.scoped import scoped_connection

router = APIRouter(tags=["billing"])
log = get_logger(__name__)

CurrentSettings = Annotated[Settings, Depends(get_settings)]

TRIAL_LENGTH = timedelta(days=7)


# ── Wire ──────────────────────────────────────────────────────


class LineItemOut(BaseModel):
    kind: str
    key: str
    label: str
    amount_minor: int | None
    included: bool = False
    unavailable: bool = False


class QuoteOut(BaseModel):
    currency: str
    period: str
    line_items: list[LineItemOut]
    total_minor: int


class EntitlementOut(BaseModel):
    entitled: bool
    kind: str | None
    trial_expires_at: str | None


class PriceOut(BaseModel):
    kind: str
    key: str
    amount_minor: int
    currency: str
    active: bool
    updated_at: str
    updated_by: str | None


class PriceUpdateIn(BaseModel):
    amount_minor: int = Field(ge=0)
    active: bool


# ── Helpers ───────────────────────────────────────────────────


def _quote_out(quote: dict[str, Any]) -> QuoteOut:
    return QuoteOut(
        currency=quote["currency"],
        period=quote["period"],
        line_items=[LineItemOut(**item) for item in quote["line_items"]],
        total_minor=quote["total_minor"],
    )


def _entitlement_out(entitlement: Entitlement) -> EntitlementOut:
    return EntitlementOut(
        entitled=entitlement.entitled,
        kind=entitlement.kind,
        trial_expires_at=(
            entitlement.trial_expires_at.isoformat() if entitlement.trial_expires_at else None
        ),
    )


async def _require_platform_admin(scope: CurrentScope, settings: CurrentSettings, db: Any) -> None:
    """403 unless the caller's own email is on the allowlist.

    Reads `app_user.email` by the caller's own `user_id` — never from anything
    the client supplies. An empty allowlist (the default, `config.py`) means
    nobody is admin, including a deployment that never configured one.
    """
    allowlist = settings.platform_admin_email_set
    if not allowlist:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No platform admin is configured for this deployment.",
        )
    row = (
        (
            await db.execute(
                sa.text("SELECT email FROM app_user WHERE id = :u"),
                {"u": str(scope.user_id)},
            )
        )
        .mappings()
        .first()
    )
    email = (row["email"] if row is not None else "").strip().lower()
    if email not in allowlist:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This action requires a platform admin.",
        )


# ── Endpoints ─────────────────────────────────────────────────


@router.get("/billing/quote", response_model=QuoteOut)
async def read_quote(scope: CurrentScope) -> QuoteOut:
    """What this workspace would be charged today, from its own selections."""
    async with scoped_connection(scope) as db:
        quote = await quote_for(db, workspace_id=scope.workspace_id)
    return _quote_out(quote)


@router.get("/billing/status", response_model=EntitlementOut)
async def read_status(scope: CurrentScope) -> EntitlementOut:
    """Whether this workspace may use the product today, and why."""
    async with scoped_connection(scope) as db:
        entitlement = await entitlement_for(db, workspace_id=scope.workspace_id)
    return _entitlement_out(entitlement)


@router.post(
    "/billing/pay",
    response_model=EntitlementOut,
    dependencies=[Depends(require_csrf)],
)
async def pay(scope: CurrentScope) -> EntitlementOut:
    """Pay today's quote. A dummy gateway — it always succeeds.

    Idempotent-ish: a workspace that is already entitled is returned as-is
    rather than billed a second time for one double-click.
    """
    async with scoped_connection(scope) as db:
        existing = await entitlement_for(db, workspace_id=scope.workspace_id)
        if existing.entitled:
            return _entitlement_out(existing)

        quote = await quote_for(db, workspace_id=scope.workspace_id)
        await db.execute(
            sa.text(
                "INSERT INTO onboarding_subscription"
                " (workspace_id, status, amount_minor, currency, line_items, created_by)"
                " VALUES (:w, 'paid', :amount, :currency, CAST(:items AS jsonb), :u)"
            ),
            {
                "w": str(scope.workspace_id),
                "amount": quote["total_minor"],
                "currency": quote["currency"],
                "items": json.dumps(quote["line_items"]),
                "u": str(scope.user_id),
            },
        )
        entitlement = await entitlement_for(db, workspace_id=scope.workspace_id)
    log.info(
        "billing.paid", workspace_id=str(scope.workspace_id), amount_minor=quote["total_minor"]
    )
    return _entitlement_out(entitlement)


@router.post(
    "/billing/trial",
    response_model=EntitlementOut,
    dependencies=[Depends(require_csrf)],
)
async def start_trial(scope: CurrentScope) -> EntitlementOut:
    """Start a 7-day trial. Nothing is charged.

    Idempotent-ish, same as `pay`: a workspace already entitled is returned
    as-is, so a double-click does not open a second trial clock.
    """
    async with scoped_connection(scope) as db:
        existing = await entitlement_for(db, workspace_id=scope.workspace_id)
        if existing.entitled:
            return _entitlement_out(existing)

        quote = await quote_for(db, workspace_id=scope.workspace_id)
        expires_at = datetime.now(UTC) + TRIAL_LENGTH
        await db.execute(
            sa.text(
                "INSERT INTO onboarding_subscription"
                " (workspace_id, status, amount_minor, currency, line_items,"
                "  trial_expires_at, created_by)"
                " VALUES (:w, 'trial', 0, :currency, CAST(:items AS jsonb), :expires, :u)"
            ),
            {
                "w": str(scope.workspace_id),
                "currency": quote["currency"],
                "items": json.dumps(quote["line_items"]),
                "expires": expires_at,
                "u": str(scope.user_id),
            },
        )
        entitlement = await entitlement_for(db, workspace_id=scope.workspace_id)
    log.info(
        "billing.trial_started",
        workspace_id=str(scope.workspace_id),
        trial_expires_at=expires_at.isoformat(),
    )
    return _entitlement_out(entitlement)


@router.get("/admin/prices", response_model=list[PriceOut])
async def list_prices(scope: CurrentScope, settings: CurrentSettings) -> list[PriceOut]:
    """Every price row, active and inactive. Platform-admin only."""
    async with scoped_connection(scope) as db:
        await _require_platform_admin(scope, settings, db)
        rows = (
            (
                await db.execute(
                    sa.text(
                        "SELECT kind, key, amount_minor, currency, active, updated_at, updated_by"
                        " FROM price ORDER BY kind, key"
                    )
                )
            )
            .mappings()
            .all()
        )
    return [
        PriceOut(
            kind=row["kind"],
            key=row["key"],
            amount_minor=row["amount_minor"],
            currency=row["currency"],
            active=row["active"],
            updated_at=row["updated_at"].isoformat(),
            updated_by=str(row["updated_by"]) if row["updated_by"] else None,
        )
        for row in rows
    ]


@router.put(
    "/admin/prices/{kind}/{key}",
    response_model=PriceOut,
    dependencies=[Depends(require_csrf)],
)
async def update_price(
    kind: str,
    key: str,
    payload: PriceUpdateIn,
    scope: CurrentScope,
    settings: CurrentSettings,
) -> PriceOut:
    """Correct one row of the rate card. Platform-admin only."""
    async with scoped_connection(scope) as db:
        await _require_platform_admin(scope, settings, db)
        row = (
            (
                await db.execute(
                    sa.text(
                        "UPDATE price SET amount_minor = :amount, active = :active,"
                        " updated_at = now(), updated_by = :u"
                        " WHERE kind = :kind AND key = :key"
                        " RETURNING kind, key, amount_minor, currency, active,"
                        "           updated_at, updated_by"
                    ),
                    {
                        "amount": payload.amount_minor,
                        "active": payload.active,
                        "u": str(scope.user_id),
                        "kind": kind,
                        "key": key,
                    },
                )
            )
            .mappings()
            .first()
        )
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No price row for {kind}/{key}.",
            )
    log.info("billing.price_updated", kind=kind, key=key, amount_minor=payload.amount_minor)
    return PriceOut(
        kind=row["kind"],
        key=row["key"],
        amount_minor=row["amount_minor"],
        currency=row["currency"],
        active=row["active"],
        updated_at=row["updated_at"].isoformat(),
        updated_by=str(row["updated_by"]) if row["updated_by"] else None,
    )
