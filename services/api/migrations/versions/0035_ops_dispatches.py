"""`ops_dispatch`, and the grace period that makes a lateness figure possible.

`doc/15` S10.4, ADR 0036 (D32). `operations.on_time_dispatch` is the **first ops
rate**. Every figure in the layer until now was a count, which states what was
recorded and is true whether or not the record is complete. A rate divides, and
dividing needs a threshold — the point at which an order is late.

## `workspace.dispatch_grace_days` is nullable, with no server default

**That is the entire decision.** `DEFAULT 0` would be a threshold *we* set,
silently, for every workspace — and it would produce a confident percentage
computed under a rule the customer never agreed to. So the column starts empty,
`NULL` means "nobody has said", and the tile refuses to compute a rate until
somebody fills it in.

`late_definition` is asked during onboarding and arrives as free prose — typed
`SINGLE_CHOICE` with no choices, and `AnswerShape.DURATION` turns out to be only
a cue that helps the agent phrase the question. There is no parser, and writing
one would be inventing a threshold from somebody's sentence. `SMALLINT` because
a grace measured in more than a few weeks is a different promise, not a longer
one.

## `promised_on` is `NOT NULL`, `dispatched_on` is not

The promise is the point of the record: an order with no promised date cannot be
on time or late, and there is nothing to store about it that this tile can use.

`dispatched_on` is nullable because "not yet sent" is the ordinary state of a
live order. It is what keeps the rate's denominator honest — the calculator
divides by what actually went out, never by what was recorded, because dividing
by the latter reports a company as late for having a backlog.

## Widening `ck_ops_completeness_entity` again

Five entities now. D29 asks *"is this all of them?"* per entity (ADR 0035), and
a rate needs that answer more than any count did. Widening only: every value
that was legal stays legal.

Additive: one new table, one new nullable column, one widened CHECK. No `DROP
TABLE`, no `DROP COLUMN`. RLS enabled and forced on the new table.

Revision ID: 0035
Revises: 0034
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0035"
down_revision = "0034"
branch_labels = None
depends_on = None

ENTITIES = ("projects", "tasks", "milestones", "issues", "dispatches")
PREVIOUS_ENTITIES = ("projects", "tasks", "milestones", "issues")


def _one_of(column: str, values: tuple[str, ...]) -> str:
    """`col IN ('a', 'b')` — `0032`'s helper and its reason."""
    return f"{column} IN (" + ", ".join(f"'{value}'" for value in values) + ")"


def upgrade() -> None:
    op.create_table(
        "ops_dispatch",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        # Nullable, like an issue's and for `ops_task`'s reason: requiring one
        # would make somebody invent a project to record an order.
        sa.Column("project_id", postgresql.UUID(as_uuid=True)),
        sa.Column("reference", sa.Text, nullable=False),
        sa.Column("promised_on", sa.Date, nullable=False),
        sa.Column("dispatched_on", sa.Date),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("archived_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspace.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["ops_project.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["app_user.id"], ondelete="RESTRICT"),
    )
    op.add_column(
        "workspace",
        # **Nullable, and no server default.** `NULL` means nobody has said what
        # late means here, and that is the gate the rate refuses at.
        sa.Column("dispatch_grace_days", sa.SmallInteger),
    )
    # A dispatch cannot have gone out before it was promised... but it can, and
    # often does: an order shipped early is the good case. The only thing worth
    # constraining is that a grace is not negative, which would turn "late"
    # into "early" without anybody noticing.
    op.create_check_constraint(
        "ck_workspace_dispatch_grace_days",
        "workspace",
        "dispatch_grace_days IS NULL OR dispatch_grace_days >= 0",
    )

    op.create_index(
        "ix_ops_dispatch_live",
        "ops_dispatch",
        ["workspace_id", "promised_on"],
        postgresql_where=sa.text("archived_at IS NULL"),
    )

    op.execute("ALTER TABLE ops_dispatch ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE ops_dispatch FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY ops_dispatch_workspace_isolation ON ops_dispatch
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
    op.drop_constraint("ck_workspace_dispatch_grace_days", "workspace", type_="check")
    op.drop_column("workspace", "dispatch_grace_days")
    op.drop_table("ops_dispatch")
