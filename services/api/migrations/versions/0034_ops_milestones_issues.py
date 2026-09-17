"""`ops_milestone` and `ops_issue` — the two record types that hang off a project.

`doc/15` S10.3. `operations.milestone_timeline` (doc/05 6.3, *"milestones with
planned dates"*) and `operations.issue_register` (6.9, *"open issues by severity
and owner"*).

## `done` is the shared terminal status, again

Four vocabularies now — projects, tasks, milestones, issues — and `done` is the
only word all four mean the same way. `calculators/ops.count_items` counts what
is *not* done rather than enumerating what is open, precisely so a fifth record
type does not require editing a list of open statuses kept in step with four
CHECK constraints.

Milestones are `planned | done`. **There is deliberately no `missed`**: a missed
milestone is a planned date in the past that nobody marked done, which is a
comparison the calculator already makes. Storing it would let the stored value
and the computed one disagree, and the one on the screen would be whichever the
tile happened to read.

## `project_id` differs between the two, and that is not an oversight

A **milestone** belongs to a project — it is a point in that project's plan, and
one without a project is not a milestone, it is a date. `NOT NULL`.

An **issue** does not. `0032` made `ops_task.project_id` nullable because
requiring one would make somebody invent a project to record work, and an
invented project then counts on `projects_board` — a snag noticed in the
workshop has exactly that shape. Nullable, for that reason.

## Severity is a small closed set

`low | medium | high`. Three, because the register is read to decide what to look
at first and a five-point scale makes that decision harder rather than finer.
Constrained rather than free text so the breakdown can be grouped at all; ordered
in code rather than by the column, because alphabetical would put "high" between
"low" and "medium".

## Widening `ck_ops_completeness_entity`

D29 asks *"is this all of them?"* per entity (ADR 0035), so two new record types
mean two new entities. The constraint is dropped and recreated with the wider
set — **widening only**: every value that was legal stays legal, so no existing
row can be invalidated. `0033`'s docstring said S10.3 would do this.

Additive: two new tables and one widened CHECK. No `DROP TABLE`, no `DROP
COLUMN`, nothing that can lose a row. RLS enabled and forced on both new tables.

Revision ID: 0034
Revises: 0033
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0034"
down_revision = "0033"
branch_labels = None
depends_on = None

MILESTONE_STATUSES = ("planned", "done")
ISSUE_STATUSES = ("open", "done")
SEVERITIES = ("low", "medium", "high")

ENTITIES = ("projects", "tasks", "milestones", "issues")
PREVIOUS_ENTITIES = ("projects", "tasks")

TABLES = ("ops_milestone", "ops_issue")


def _one_of(column: str, values: tuple[str, ...]) -> str:
    """`col IN ('a', 'b')` — `0032`'s helper and its reason: Python renders a
    one-member tuple as `('a',)` and Postgres rejects the trailing comma."""
    return f"{column} IN (" + ", ".join(f"'{value}'" for value in values) + ")"


def upgrade() -> None:
    op.create_table(
        "ops_milestone",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("status", sa.Text, nullable=False, server_default="planned"),
        # `NOT NULL`, unlike every other date in this layer. doc/05 6.3 is
        # "milestones with planned dates" — a milestone with no date is the one
        # thing a timeline cannot draw, and it would silently join the `undated`
        # count on a tile whose whole subject is when things happen.
        sa.Column("planned_on", sa.Date, nullable=False),
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
    op.create_check_constraint(
        "ck_ops_milestone_status", "ops_milestone", _one_of("status", MILESTONE_STATUSES)
    )

    op.create_table(
        "ops_issue",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True)),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("status", sa.Text, nullable=False, server_default="open"),
        sa.Column("severity", sa.Text, nullable=False, server_default="medium"),
        # "by severity **and owner**" — doc/05 6.9. Nullable: an unowned issue is
        # a real and common state, and it is the one a register exists to make
        # visible rather than to refuse at entry.
        sa.Column("owner_id", postgresql.UUID(as_uuid=True)),
        sa.Column("due_on", sa.Date),
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
        sa.ForeignKeyConstraint(["owner_id"], ["app_user.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by"], ["app_user.id"], ondelete="RESTRICT"),
    )
    op.create_check_constraint(
        "ck_ops_issue_status", "ops_issue", _one_of("status", ISSUE_STATUSES)
    )
    op.create_check_constraint(
        "ck_ops_issue_severity", "ops_issue", _one_of("severity", SEVERITIES)
    )

    op.create_index(
        "ix_ops_milestone_live",
        "ops_milestone",
        ["workspace_id", "planned_on"],
        postgresql_where=sa.text("archived_at IS NULL"),
    )
    op.create_index(
        "ix_ops_issue_live",
        "ops_issue",
        ["workspace_id", "status", "severity"],
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

    # Widening only — every previously legal value stays legal, so no existing
    # row can be invalidated by this.
    op.drop_constraint("ck_ops_completeness_entity", "ops_completeness", type_="check")
    op.create_check_constraint(
        "ck_ops_completeness_entity", "ops_completeness", _one_of("entity", ENTITIES)
    )


def downgrade() -> None:
    op.drop_constraint("ck_ops_completeness_entity", "ops_completeness", type_="check")
    op.create_check_constraint(
        "ck_ops_completeness_entity", "ops_completeness", _one_of("entity", PREVIOUS_ENTITIES)
    )
    op.drop_table("ops_issue")
    op.drop_table("ops_milestone")
