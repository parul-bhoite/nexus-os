"""`price` and `onboarding_subscription` — the Payment step's two tables.

The onboarding "Payment" step prices a workspace by the departments it runs and
the tools it has declared (`app/domain/pricing.py`), and lets it pay or start a
trial (`app/routes/billing.py`). Two tables, and they are deliberately shaped
differently.

## `price` — a global reference table, read under every workspace

Unlike every other table this migration's neighbours create, `price` carries no
`workspace_id` and its RLS policy is `USING (true)`. That is a genuine
departure from the tenant-row pattern `crm_deal_workspace_isolation` (0031) set
and `onboarding_subscription` below follows, and it is deliberate rather than an
oversight: a price list is not a tenant's data, it is the product's own published
rate card, identical for every workspace that reads it. A per-tenant policy here
would not protect anything — there is nothing in this table that is sensitive to
isolate — and would only cost a predicate on a table every quote reads.

`ENABLE`/`FORCE ROW LEVEL SECURITY` are still turned on, so the table fails
closed if a future migration ever adds a column worth restricting; today's
policy simply grants every row to every reader. **Writes are not restricted by
RLS at all** — `price_readable`'s `WITH CHECK (true)` permits any write the
application role attempts. Nothing stops `nexus_app` writing a bad row; what
stops a *caller* is `app/routes/billing.py`'s admin gate, checked in the service
layer against `Settings.platform_admin_emails`, same as every other
authorisation decision in this codebase (never in the database). This is a
narrower guarantee than `onboarding_subscription`'s, and it is written out
explicitly here so nobody reads "RLS enabled" on this table and assumes it means
what it means on every other one.

Seeded with the day-one rate card: six departments (`executive` excluded — it is
never selected, `app/domain/departments.AUTOMATIC`, and must never be billed)
and the nine tools from `app/domain/connections.PROVIDERS`. Amounts are OMR
minor units (baisa, x1000) and are **illustrative placeholders set by this
migration**, not a researched price list — `PUT /admin/prices/{kind}/{key}` is
how a platform admin corrects them without a second migration.

## `onboarding_subscription` — one row per pay-or-trial decision, tenant-scoped

Ordinary shape: `ENABLE`/`FORCE ROW LEVEL SECURITY` plus a single
`onboarding_subscription_workspace_isolation` policy keyed on
`nexus.workspace_id`, identical in structure to `crm_deal_workspace_isolation`
(0031). `line_items` is the quote snapshot at the moment of the decision —
`app/domain/pricing.quote_for`'s own line items, stored rather than
recomputed — because the price list `price` is read from can change later and a
receipt must describe what was actually charged, not what the rate card says
today. `(status = 'trial') = (trial_expires_at IS NOT NULL)` is the same
shape as `ck_crm_deal_amount_currency`: one column's presence is the other's
precondition, and the constraint makes "trial with no expiry" or "paid with an
expiry" impossible to write rather than merely undocumented.

Purely additive. No `DROP`, no existing table touched.

Revision ID: 0042
Revises: 0041
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0042"
down_revision = "0041"
branch_labels = None
depends_on = None

# OMR minor units (baisa): amount_minor = amount_omr * 1000.
_DEPARTMENT_PRICES: tuple[tuple[str, int], ...] = (
    ("marketing", 25_000),
    ("sales", 30_000),
    ("finance", 30_000),
    ("operations", 20_000),
    ("hr", 20_000),
    ("strategy", 25_000),
    # `executive` is deliberately absent: `app/domain/departments.AUTOMATIC`
    # is never selected and must never be billed.
)

_TOOL_PRICES: tuple[tuple[str, int], ...] = (
    ("ga4", 8_000),
    ("search_console", 6_000),
    ("hubspot", 15_000),
    ("salesforce", 15_000),
    ("pipedrive", 15_000),
    ("zoho_crm", 15_000),
    ("xero", 12_000),
    ("quickbooks", 12_000),
    ("stripe", 10_000),
)


def upgrade() -> None:
    op.create_table(
        "price",
        sa.Column("kind", sa.Text, nullable=False),
        sa.Column("key", sa.Text, nullable=False),
        sa.Column("amount_minor", sa.Integer, nullable=False),
        sa.Column("currency", sa.Text, nullable=False, server_default="OMR"),
        sa.Column("active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.PrimaryKeyConstraint("kind", "key"),
    )
    op.create_check_constraint(
        "ck_price_kind",
        "price",
        "kind IN ('department', 'tool')",
    )
    op.create_check_constraint(
        "ck_price_amount_non_negative",
        "price",
        "amount_minor >= 0",
    )

    op.execute("ALTER TABLE price ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE price FORCE ROW LEVEL SECURITY")
    # `USING (true)` / `WITH CHECK (true)` — reference data, not a tenant row.
    # See the module docstring for why this table does not follow the
    # `*_workspace_isolation` shape every neighbouring migration uses.
    op.execute(
        """
        CREATE POLICY price_readable ON price
        USING (true)
        WITH CHECK (true)
        """
    )

    for key, amount in _DEPARTMENT_PRICES:
        op.execute(
            sa.text(
                "INSERT INTO price (kind, key, amount_minor, currency, active, updated_at)"
                " VALUES ('department', :key, :amount, 'OMR', true, now())"
            ).bindparams(key=key, amount=amount)
        )
    for key, amount in _TOOL_PRICES:
        op.execute(
            sa.text(
                "INSERT INTO price (kind, key, amount_minor, currency, active, updated_at)"
                " VALUES ('tool', :key, :amount, 'OMR', true, now())"
            ).bindparams(key=key, amount=amount)
        )

    op.create_table(
        "onboarding_subscription",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.Text, nullable=False),
        sa.Column("amount_minor", sa.Integer, nullable=False),
        sa.Column("currency", sa.Text, nullable=False),
        sa.Column("line_items", postgresql.JSONB, nullable=False),
        sa.Column("trial_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspace.id"], ondelete="CASCADE"),
    )
    op.create_check_constraint(
        "ck_onboarding_subscription_status",
        "onboarding_subscription",
        "status IN ('paid', 'trial')",
    )
    op.create_check_constraint(
        "ck_onboarding_subscription_trial_expiry",
        "onboarding_subscription",
        "(status = 'trial') = (trial_expires_at IS NOT NULL)",
    )
    op.create_index(
        "ix_onboarding_subscription_workspace_created",
        "onboarding_subscription",
        ["workspace_id", sa.text("created_at DESC")],
    )

    op.execute("ALTER TABLE onboarding_subscription ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE onboarding_subscription FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY onboarding_subscription_workspace_isolation ON onboarding_subscription
        USING (
            workspace_id = NULLIF(current_setting('nexus.workspace_id', true), '')::uuid
        )
        WITH CHECK (
            workspace_id = NULLIF(current_setting('nexus.workspace_id', true), '')::uuid
        )
        """
    )


def downgrade() -> None:
    op.drop_table("onboarding_subscription")
    op.drop_table("price")
