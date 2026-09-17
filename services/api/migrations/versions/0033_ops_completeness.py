"""`ops_completeness` — somebody saying "yes, this is all of them".

`doc/15` S10.2, ADR 0035 (D29). The ops layer **fails on adoption, not on an
API**: nothing in `ops_project` distinguishes a founder who recorded three of
twelve projects from one who recorded twelve. A count is true either way, which
is why S10.1 shipped. A rate is not, and every ops capability after S10.1 is a
rate — so the thing a rate needs is a fact the database cannot hold about
itself, and this table is where a person supplies it.

## Append-only, never upserted

One row per confirmation, not one per workspace and entity kept current. The
question is asked again as the business changes, and *when somebody last vouched
for the record* is precisely what a reader of a rate needs. An upsert would keep
the answer and destroy its history, which is the half that carries the doubt.

Reads take the newest row per entity. There is no unique constraint on
`(workspace_id, entity)` for that reason, and adding one later would mean
choosing which confirmations to delete.

## Per entity, not per layer

Somebody can plausibly have recorded every project and a third of the tasks. One
switch covering both would let the honest half vouch for the careless one. The
CHECK lists the two entity kinds S10.1 built; `doc/15` S10.3 and S10.5 widen it.

## Two dates, deliberately

`complete_as_of` is the date the claim is *about*; `confirmed_at` is when it was
made. A founder catching up on Monday can honestly say the record was complete
as of Friday, and a figure reporting Monday would overstate how current the
claim is. Nothing here expires either of them — an expiry after N days would be
a threshold nobody set, and ADR 0035 rejects it as D29's staleness option.

Additive: one new table, no change to anything existing. RLS enabled and forced,
as on both S10.1 tables.

Revision ID: 0033
Revises: 0032
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0033"
down_revision = "0032"
branch_labels = None
depends_on = None

ENTITIES = ("projects", "tasks")


def _one_of(column: str, values: tuple[str, ...]) -> str:
    """`col IN ('a', 'b')`, written rather than borrowed from a tuple's repr —
    `0032`'s helper and its reason: Python renders a one-member tuple as
    `('a',)` and Postgres rejects the trailing comma."""
    return f"{column} IN (" + ", ".join(f"'{value}'" for value in values) + ")"


def upgrade() -> None:
    op.create_table(
        "ops_completeness",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("entity", sa.Text, nullable=False),
        sa.Column("complete_as_of", sa.Date, nullable=False),
        # Who vouched. `doc/13` §7's treatment of a self-reported figure is the
        # founder's words *plus an attribution* — "You, 8 September" — so the
        # person is part of the fact rather than an audit detail beside it.
        sa.Column("confirmed_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "confirmed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspace.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["confirmed_by"], ["app_user.id"], ondelete="RESTRICT"),
    )
    op.create_check_constraint(
        "ck_ops_completeness_entity", "ops_completeness", _one_of("entity", ENTITIES)
    )

    # The only read: the newest confirmation per entity for one workspace.
    # Descending on `confirmed_at` so "the latest" is the index's first row
    # rather than a sort over every confirmation a workspace has ever made.
    op.create_index(
        "ix_ops_completeness_latest",
        "ops_completeness",
        ["workspace_id", "entity", sa.text("confirmed_at DESC")],
    )

    op.execute("ALTER TABLE ops_completeness ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE ops_completeness FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY ops_completeness_workspace_isolation ON ops_completeness
        USING (
            workspace_id = NULLIF(current_setting('nexus.workspace_id', true), '')::uuid
        )
        WITH CHECK (
            workspace_id = NULLIF(current_setting('nexus.workspace_id', true), '')::uuid
        )
        """
    )


def downgrade() -> None:
    op.drop_table("ops_completeness")
