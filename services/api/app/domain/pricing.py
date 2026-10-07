"""What a workspace would be charged, and whether it is entitled today.

The Payment step of onboarding. Two things live here:

- `quote_for` builds the bill from a workspace's own facts — its selected
  departments (`app/domain/departments.py`) and its declared tools
  (`app/domain/connections.py`) — priced against the `price` reference table
  migration 0042 created. **Every amount comes from that table.** I1 forbids a
  figure computed or guessed inside this module; a missing or inactive price
  is surfaced as `unavailable`, never silently substituted with zero (I10).
- `entitlement_for` reads the latest `onboarding_subscription` row and answers
  one question: can this workspace use the product today.

Neither function decides *whether* a workspace may read or write — that is
`app/routes/billing.py`'s job, via `CurrentScope`. This module is pure
computation and queries, the same split `service.py` keeps from `router.py`
everywhere else in this codebase.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import connections
from app.domain.departments import AUTOMATIC, label_for, selected_departments
from app.domain.scopes import Department
from app.retrieval.scoped import apply_workspace_scope

PriceKey = tuple[str, str]
"""`(kind, key)` — `kind` is `'department'` or `'tool'`, `key` is the catalogue id."""


@dataclass(frozen=True, slots=True)
class PriceRow:
    kind: str
    key: str
    amount_minor: int
    currency: str
    active: bool


async def load_prices(db: AsyncSession) -> dict[PriceKey, PriceRow]:
    """Every active price, keyed by `(kind, key)`.

    `price` carries no workspace scope — see migration 0042's docstring for why
    a reference table reads the same for every tenant — so this needs no
    `apply_workspace_scope` call of its own. Inactive rows are excluded here
    rather than filtered by each caller, so "no active price" and "no row at
    all" collapse to the same lookup miss everywhere this is read.
    """
    rows = (
        (
            await db.execute(
                sa.text(
                    "SELECT kind, key, amount_minor, currency, active"
                    " FROM price WHERE active = true"
                )
            )
        )
        .mappings()
        .all()
    )
    return {
        (row["kind"], row["key"]): PriceRow(
            kind=row["kind"],
            key=row["key"],
            amount_minor=row["amount_minor"],
            currency=row["currency"],
            active=row["active"],
        )
        for row in rows
    }


async def _reporting_currency(db: AsyncSession, *, workspace_id: UUID) -> str:
    row = (
        (
            await db.execute(
                sa.text("SELECT reporting_currency FROM workspace WHERE id = :w"),
                {"w": str(workspace_id)},
            )
        )
        .mappings()
        .first()
    )
    currency = row["reporting_currency"] if row is not None else None
    return currency or "OMR"


async def quote_for(db: AsyncSession, *, workspace_id: UUID) -> dict[str, Any]:
    """The bill this workspace would see today, built from its own facts.

    Line items, in order:

    - One per selected department (excluding `executive`, which is never
      billed — `app/domain/departments.AUTOMATIC`), priced from `price`.
    - One per declared tool whose department is **not** selected: billed as
      `additional`, because the company is paying for a capability outside the
      departments it already covers.
    - One per declared tool whose department **is** selected: `included`, at
      zero, because the department's own line already covers it. Recorded
      rather than omitted, so the bill shows what a tool's declaration bought
      rather than implying it cost nothing to notice.

    A selected department or declared tool with no active price becomes an
    `unavailable` line at `amount_minor: None` and is **excluded from
    `total_minor`** — I10 forbids treating "we have no price for this" as "this
    is free". The caller decides what an unavailable line means for the
    screen; this only refuses to invent a number.
    """
    prices = await load_prices(db)
    currency = await _reporting_currency(db, workspace_id=workspace_id)

    departments = await selected_departments(db, workspace_id=workspace_id)
    billable_departments = sorted(d.value for d in departments if d is not AUTOMATIC)
    declared_tools = await connections.declared(db, workspace_id=workspace_id)

    line_items: list[dict[str, Any]] = []
    total_minor = 0

    for key in billable_departments:
        label = label_for(Department(key))
        price = prices.get(("department", key))
        if price is None:
            line_items.append(
                {
                    "kind": "department",
                    "key": key,
                    "label": label,
                    "amount_minor": None,
                    "unavailable": True,
                }
            )
            continue
        line_items.append(
            {
                "kind": "department",
                "key": key,
                "label": label,
                "amount_minor": price.amount_minor,
            }
        )
        total_minor += price.amount_minor

    selected_department_values = {d.value for d in departments}
    for provider_id in declared_tools:
        tool = connections.by_id(provider_id)
        included = tool.department.value in selected_department_values
        if included:
            line_items.append(
                {
                    "kind": "tool",
                    "key": provider_id,
                    "label": tool.name,
                    "amount_minor": 0,
                    "included": True,
                }
            )
            continue

        price = prices.get(("tool", provider_id))
        if price is None:
            line_items.append(
                {
                    "kind": "tool",
                    "key": provider_id,
                    "label": tool.name,
                    "amount_minor": None,
                    "included": False,
                    "unavailable": True,
                }
            )
            continue
        line_items.append(
            {
                "kind": "tool",
                "key": provider_id,
                "label": tool.name,
                "amount_minor": price.amount_minor,
                "included": False,
            }
        )
        total_minor += price.amount_minor

    return {
        "currency": currency,
        "period": "monthly",
        "line_items": line_items,
        "total_minor": total_minor,
    }


# ── Entitlement ───────────────────────────────────────────────

EntitlementKind = Literal["paid", "trial"]


@dataclass(frozen=True, slots=True)
class Entitlement:
    entitled: bool
    kind: EntitlementKind | None
    trial_expires_at: datetime | None


async def entitlement_for(db: AsyncSession, *, workspace_id: UUID) -> Entitlement:
    """Whether this workspace may use the product today, and why.

    Reads the **latest** `onboarding_subscription` row only — a workspace that
    paid and later let a trial lapse is not re-evaluated against history, the
    most recent decision is the one that stands. `entitled` is:

    - `True` when `status = 'paid'`.
    - `True` when `status = 'trial'` and `trial_expires_at` is still ahead of
      now.
    - `False` otherwise, including "no subscription row at all".
    """
    await apply_workspace_scope(db, workspace_id)
    row = (
        (
            await db.execute(
                sa.text(
                    "SELECT status, trial_expires_at FROM onboarding_subscription"
                    " WHERE workspace_id = :w ORDER BY created_at DESC LIMIT 1"
                ),
                {"w": str(workspace_id)},
            )
        )
        .mappings()
        .first()
    )

    if row is None:
        return Entitlement(entitled=False, kind=None, trial_expires_at=None)

    status = row["status"]
    trial_expires_at = row["trial_expires_at"]

    if status == "paid":
        return Entitlement(entitled=True, kind="paid", trial_expires_at=None)

    # status == "trial"
    now = datetime.now(UTC)
    still_live = trial_expires_at is not None and now < trial_expires_at
    return Entitlement(
        entitled=still_live,
        kind="trial",
        trial_expires_at=trial_expires_at,
    )
