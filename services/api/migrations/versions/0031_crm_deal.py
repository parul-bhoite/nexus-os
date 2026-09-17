"""`crm_deal` — where a connector's rows land before a calculator reads them.

`doc/14` step 9. The CRM's equivalent of `page_signals`: what a provider told
us, stored scoped, so that `calculators/pipeline.py` can compute from a row in
this database rather than from a live API call. That separation is I1's
plumbing — a figure computed inside a request to a third party is a figure
nobody can reproduce after the fact.

**`amount_minor` is an integer, and nullable.** Two decisions in one column:

- *Integer* because money in a float is money that stops adding up. Minor units
  — fils, cents — against `currency`, which is the provider's own and not
  assumed to be the workspace's reporting currency.
- *Nullable* because a deal nobody has priced is a real state, and a zero would
  say it is worth nothing. That is the substitution I10 exists to forbid, and
  `sales.pipeline_board` has to be able to say "three of these are unpriced"
  rather than quietly adding zero three times.

`ck_crm_deal_amount_currency` pairs the two: an amount with no currency is a
number nobody can add up, and a currency with no amount describes nothing. Same
shape as `ck_generation_prose_matches_outcome` and for the same reason.

The unique key is `(workspace_id, provider, external_id)`: one row per deal per
provider, so a re-sync updates rather than duplicating. Without it a nightly
sweep would multiply the pipeline by the number of times it had run, and the
figure would look plausible every morning.

Revision ID: 0031
Revises: 0030
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0031"
down_revision = "0030"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "crm_deal",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.Text, nullable=False),
        # The provider's own id. Text rather than a number: HubSpot's are
        # numeric strings, Pipedrive's are integers, and a column that had to be
        # one of those would need a migration on the second CRM.
        sa.Column("external_id", sa.Text, nullable=False),
        sa.Column("name", sa.Text),
        sa.Column("amount_minor", sa.BigInteger),
        sa.Column("currency", sa.Text),
        sa.Column("stage", sa.Text),
        sa.Column("closes_on", sa.Date),
        sa.Column("pipeline", sa.Text),
        # When we read it, not when it changed. The provider's own timestamp
        # would be better and HubSpot does not return one on this call, so this
        # is honest about being the moment we asked.
        sa.Column(
            "fetched_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspace.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("workspace_id", "provider", "external_id", name="uq_crm_deal_external"),
    )

    op.create_check_constraint(
        "ck_crm_deal_amount_currency",
        "crm_deal",
        "(amount_minor IS NULL) = (currency IS NULL)",
    )

    # The calculator's only query: this workspace's deals, newest fetch first.
    op.create_index(
        "ix_crm_deal_workspace_fetched",
        "crm_deal",
        ["workspace_id", sa.text("fetched_at DESC")],
    )

    op.execute("ALTER TABLE crm_deal ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE crm_deal FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY crm_deal_workspace_isolation ON crm_deal
        USING (
            workspace_id = NULLIF(current_setting('nexus.workspace_id', true), '')::uuid
        )
        WITH CHECK (
            workspace_id = NULLIF(current_setting('nexus.workspace_id', true), '')::uuid
        )
        """
    )


def downgrade() -> None:
    op.drop_table("crm_deal")
