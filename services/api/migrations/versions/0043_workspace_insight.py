"""`workspace_insight` — where a measured insight lands once, rather than being recomputed.

ADR 0081. The dashboard computes figures live and never persists them (I1),
which is right for a figure derived from rows already in this database
(`crm_deal`, `ops_*`) and reproducible on demand. It is wrong for a figure
derived from a **remote fetch**: a PageSpeed score for a URL at 09:00 is not
reproducible later, and recomputing would re-call the vendor on every page load.
So a connector insight is stored, the same way `crm_deal` and `page_signals`
land a provider's rows before a calculator reads them.

**Not the Company Brain.** `company_brain` holds *stated* facts a founder told
us (`generated_by ∈ answers/model/unavailable`). A measured number is a
different kind of thing; it lives here and the Brain page merely reads it.

**Append-only, no supersede column.** "Current" is the newest `captured_at` per
`(workspace_id, source, metric_key)`, exactly as `retrieval/deals.py` treats
`crm_deal.fetched_at`. History is what lets a tile say STALE or show a trend.

`ck_workspace_insight_has_value` — an insight with no value is nothing.
`ck_workspace_insight_unit_needs_number` — a unit with no number describes
nothing. Same shape, and same reason, as `ck_crm_deal_amount_currency`.

Revision ID: 0043
Revises: 0042
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0043"
down_revision = "0042"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "workspace_insight",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        # The `Source` enum value that produced this — 'pagespeed', 'crm', …
        # Text rather than an enum type: a new source is a row here, not a
        # schema migration on an enum, and the ledger in `domain/sources.py` is
        # already the authority on the set.
        sa.Column("source", sa.Text, nullable=False),
        # The canonical metric this row carries, e.g. 'performance_score'.
        sa.Column("metric_key", sa.Text, nullable=False),
        # Exactly one of these three carries the value; the check below enforces
        # that at least one is present. Numeric (not float) for the same reason
        # `crm_deal.amount_minor` is an integer: a measured number stored as a
        # float is a number that stops adding up.
        sa.Column("value_numeric", sa.Numeric),
        sa.Column("value_text", sa.Text),
        sa.Column("detail", postgresql.JSONB),
        # A unit only means something beside a number — 'score', 'ms', 'percent',
        # 'AED'. Paired with value_numeric by ck_workspace_insight_unit_needs_number.
        sa.Column("unit", sa.Text),
        # How this figure was produced, in words a reader can trace back to a
        # fetch. Not null: a figure nobody can trace is the one thing this
        # product cannot ship (cf. ck_page_signals_provenance).
        sa.Column("provenance", sa.Text, nullable=False),
        # Which director surface this belongs on, when known. Nullable: some
        # insights are workspace-wide. Text, not the Department enum, for the
        # same reason `source` is text.
        sa.Column("department", sa.Text),
        # When we read it, not when the underlying thing changed — the honest
        # date for the figure, as `crm_deal.fetched_at` is.
        sa.Column(
            "captured_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspace.id"], ondelete="CASCADE"),
    )

    op.create_check_constraint(
        "ck_workspace_insight_has_value",
        "workspace_insight",
        "(value_numeric IS NOT NULL OR value_text IS NOT NULL OR detail IS NOT NULL)",
    )
    op.create_check_constraint(
        "ck_workspace_insight_unit_needs_number",
        "workspace_insight",
        "(unit IS NULL OR value_numeric IS NOT NULL)",
    )

    # The only read: this workspace's insights, newest first per source+metric.
    op.create_index(
        "ix_workspace_insight_lookup",
        "workspace_insight",
        ["workspace_id", "source", "metric_key", sa.text("captured_at DESC")],
    )

    op.execute("ALTER TABLE workspace_insight ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE workspace_insight FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY workspace_insight_workspace_isolation ON workspace_insight
        USING (
            workspace_id = NULLIF(current_setting('nexus.workspace_id', true), '')::uuid
        )
        WITH CHECK (
            workspace_id = NULLIF(current_setting('nexus.workspace_id', true), '')::uuid
        )
        """
    )


def downgrade() -> None:
    op.drop_table("workspace_insight")
