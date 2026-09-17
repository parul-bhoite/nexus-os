"""`ops_project` and `ops_task` — the first records a customer writes into NEXUS.

`doc/15` S10.1. Every table before this one holds something we read: a page we
crawled, a provider we queried, answers given once during onboarding. These hold
what a founder typed, and expects back.

**Two tables, not seven.** `ops_layer` is a single `Source` covering projects,
tasks, milestones, issues, dispatches, stock and suppliers — and `doc/15` argues
that building them together is the mistake the deferral avoided. Projects and
tasks come first because everything else hangs off a project, and because both
tiles they serve are **counts rather than rates**: a count of what was recorded
is true whether or not the record is complete, so these two can ship before D29
settles how the ops layer knows it holds everything.

## `status` is constrained, `progress` is not stored

A CHECK on status, because `projects_board` renders "on-time or at-risk" and a
free-text status makes that ungrouped. No `progress` column: a percentage a
founder types is a number nobody computed, and `doc/05` §0's `self_reported`
state exists for exactly that — but it belongs on the *figure*, not baked into a
column that later reads as measured.

## `due_on` is a date and nullable

A task with no due date is an ordinary task, not an overdue one. Nullable so that
"nobody said when" and "due and late" stay different facts — the same distinction
`amount_minor` keeps for an unpriced deal (I10).

## Deleted, not gone

`archived_at` rather than a `DELETE`. A project that vanishes takes its tasks'
history with it, and a founder who archived something by accident has no way
back. Every read filters on it.

Additive: two new tables, no change to anything existing. RLS enabled and forced
on both.

Revision ID: 0032
Revises: 0031
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0032"
down_revision = "0031"
branch_labels = None
depends_on = None

PROJECT_STATUSES = ("planned", "active", "blocked", "done")
TASK_STATUSES = ("todo", "doing", "done")

TABLES = ("ops_project", "ops_task")


def _one_of(values: tuple[str, ...]) -> str:
    """`status IN ('a', 'b')`, written rather than borrowed from a tuple's repr.

    `f"status IN {values!r}"` happens to produce valid SQL for these two tuples
    and stops the day one has a single member — Python renders that as `('a',)`
    and Postgres rejects the trailing comma. A one-line helper is cheaper than a
    migration that fails on the fourth status somebody adds.
    """
    return "status IN (" + ", ".join(f"'{value}'" for value in values) + ")"


def upgrade() -> None:
    op.create_table(
        "ops_project",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("status", sa.Text, nullable=False, server_default="active"),
        sa.Column("client", sa.Text),
        sa.Column("due_on", sa.Date),
        # Who recorded it. Not derivable from `updated_at`, which answers "when
        # did this row last change" rather than "who told us this" — the same
        # distinction `workspace_connection.declared_by` keeps.
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
    op.create_check_constraint("ck_ops_project_status", "ops_project", _one_of(PROJECT_STATUSES))

    op.create_table(
        "ops_task",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        # Nullable: a task that belongs to no project is ordinary — "call the
        # supplier" is work without being a project. Requiring one would make
        # somebody invent a project to record a task, and an invented project
        # then counts on `projects_board`.
        sa.Column("project_id", postgresql.UUID(as_uuid=True)),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("status", sa.Text, nullable=False, server_default="todo"),
        sa.Column("assignee_id", postgresql.UUID(as_uuid=True)),
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
        # A project going takes its tasks with it. The alternative — orphaned
        # tasks pointing at nothing — would keep counting on `task_queue` with
        # no way to see what they belonged to.
        sa.ForeignKeyConstraint(["project_id"], ["ops_project.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["assignee_id"], ["app_user.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by"], ["app_user.id"], ondelete="RESTRICT"),
    )
    op.create_check_constraint("ck_ops_task_status", "ops_task", _one_of(TASK_STATUSES))

    # The two reads these tables exist for: this workspace's live projects, and
    # its live tasks. Partial on `archived_at IS NULL`, because an archived row
    # is never an answer to either.
    op.create_index(
        "ix_ops_project_live",
        "ops_project",
        ["workspace_id", "status"],
        postgresql_where=sa.text("archived_at IS NULL"),
    )
    op.create_index(
        "ix_ops_task_live",
        "ops_task",
        ["workspace_id", "status", "due_on"],
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


def downgrade() -> None:
    op.drop_table("ops_task")
    op.drop_table("ops_project")
