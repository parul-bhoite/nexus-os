"""`ops_stock_item` and `ops_supplier` — the last two record types in the plan.

`doc/15` S10.5. `operations.stock_levels` (*"on hand against minimums, ordered by
consequence rather than alphabetically"*) and `operations.supplier_risk`
(*"concentration and on-time delivery per supplier"*).

## Stock is a count; suppliers are a share

`ops_stock_item` holds `on_hand` and `minimum`, and everything the tile says
about it is a count — how many items are below the level somebody set. A count
is true whether or not the record is complete, so the stock tile works from the
first row.

`ops_supplier` holds `spend_minor`, and concentration is **a share**: the biggest
supplier's spend over all recorded spend. That is a rate, so it stands behind
D29's completeness gate (ADR 0035) exactly as the on-time figure does. A founder
who has recorded three of their ten suppliers would otherwise be told one of
them is 60% of their exposure, which is a wrong number with a plausible
denominator.

## `minimum` is the founder's, and there is no reorder suggestion

A minimum is a level somebody set for their own business. NEXUS compares against
it and says nothing about what to order: a suggested quantity would be a number
nobody computed, dressed as one we did.

## `spend_minor` is nullable, and that is the I10 shape again

A supplier whose spend nobody has entered is a real and common state. It is
counted as recorded and left out of the share, reported separately — the same
distinction `Pipeline` keeps for an unpriced deal and `count_items` for an
undated task. Minor units in the workspace's reporting currency, as an integer,
because money in a float stops adding up. `BIGINT` because a year of purchases
in fils overflows a plain `INTEGER` sooner than anybody expects.

## Widening `ck_ops_completeness_entity` a third time

Seven entities. Stock and suppliers both get the question, and for suppliers it
gates a rate rather than decorating a count.

Additive: two new tables and one widened CHECK. No `DROP TABLE`, no `DROP
COLUMN`. RLS enabled and forced on both.

Revision ID: 0036
Revises: 0035
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0036"
down_revision = "0035"
branch_labels = None
depends_on = None

ENTITIES = (
    "projects",
    "tasks",
    "milestones",
    "issues",
    "dispatches",
    "stock",
    "suppliers",
)
PREVIOUS_ENTITIES = ("projects", "tasks", "milestones", "issues", "dispatches")

TABLES = ("ops_stock_item", "ops_supplier")


def _one_of(column: str, values: tuple[str, ...]) -> str:
    """`col IN ('a', 'b')` — `0032`'s helper and its reason."""
    return f"{column} IN (" + ", ".join(f"'{value}'" for value in values) + ")"


def upgrade() -> None:
    op.create_table(
        "ops_stock_item",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("unit", sa.Text),
        sa.Column("on_hand", sa.Integer, nullable=False),
        sa.Column("minimum", sa.Integer, nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("archived_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspace.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["app_user.id"], ondelete="RESTRICT"),
    )
    # Neither can be negative. A negative count on hand is a data-entry slip that
    # would quietly drag a shortfall figure in the wrong direction, and a
    # negative minimum would make every item permanently sufficient.
    op.create_check_constraint(
        "ck_ops_stock_item_quantities",
        "ops_stock_item",
        "on_hand >= 0 AND minimum >= 0",
    )

    op.create_table(
        "ops_supplier",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("category", sa.Text),
        # Nullable: a supplier nobody has priced is a real state, counted as
        # recorded and left out of the share rather than treated as zero (I10).
        sa.Column("spend_minor", sa.BigInteger),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("archived_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspace.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["app_user.id"], ondelete="RESTRICT"),
    )
    op.create_check_constraint(
        "ck_ops_supplier_spend",
        "ops_supplier",
        "spend_minor IS NULL OR spend_minor >= 0",
    )

    op.create_index(
        "ix_ops_stock_item_live",
        "ops_stock_item",
        ["workspace_id", "name"],
        postgresql_where=sa.text("archived_at IS NULL"),
    )
    op.create_index(
        "ix_ops_supplier_live",
        "ops_supplier",
        ["workspace_id", "name"],
        postgresql_where=sa.text("archived_at IS NULL"),
    )

    for table in TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"""
            CREATE POLICY {table}_workspace_isolation ON {table}
            USING (
                workspace_id = NULLIF(current_setting('nexus.workspace_id', true), '')::uuid
            )
            WITH CHECK (
                workspace_id = NULLIF(current_setting('nexus.workspace_id', true), '')::uuid
            )
            """
        )

    op.drop_constraint("ck_ops_completeness_entity", "ops_completeness", type_="check")
    op.create_check_constraint(
        "ck_ops_completeness_entity", "ops_completeness", _one_of("entity", ENTITIES)
    )


def downgrade() -> None:
    op.drop_constraint("ck_ops_completeness_entity", "ops_completeness", type_="check")
    op.create_check_constraint(
        "ck_ops_completeness_entity", "ops_completeness", _one_of("entity", PREVIOUS_ENTITIES)
    )
    op.drop_table("ops_supplier")
    op.drop_table("ops_stock_item")
