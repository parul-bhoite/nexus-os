"""The agentic onboarding journey: `onboarding_session` and `onboarding_turn`.

Two tables, and the second is the interesting one.

`onboarding_turn` records every exchange **with the field it targeted and the
scope that field carries**. That is what makes a generated question storable: the
question's wording came from a model, but `target_field` was checked against the
declared catalogue in `app/ai/runtime/fields.py` before the question was asked,
and `scope` is copied from the catalogue rather than from anything the model
returned. An answer whose target is null is a free-text aside, not a fact, and
nothing downstream promotes it.

`ck_onboarding_turn_scoped_answer` enforces the pairing in the database: a user
turn that names a target must carry a scope. Without it a future code path could
write an answer with a field but no sensitivity, and it would be stored — the
constraint is there because "we always set both" is a claim about code that
changes, and this is a claim about data that does not.

Revision ID: 0024
Revises: 0023
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None

TABLES = ("onboarding_turn", "onboarding_session")

PHASES = ("analysing", "brief", "discovery", "persona", "assembling", "ready")
STATUSES = ("active", "completed", "abandoned")


def upgrade() -> None:
    op.create_table(
        "onboarding_session",
        sa.Column("id", sa.Uuid, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("workspace_id", sa.Uuid, nullable=False),
        sa.Column("user_id", sa.Uuid, nullable=False),
        sa.Column("status", sa.Text, nullable=False, server_default="active"),
        sa.Column("phase", sa.Text, nullable=False, server_default="analysing"),
        sa.Column("domain", sa.Text),
        # Drafts, not truth. Nothing here is authoritative until it is promoted
        # into company_brain / persona / fact by the relevant command — so a
        # half-finished onboarding leaves no half-written Brain behind.
        sa.Column("research", postgresql.JSONB),
        sa.Column("brief", postgresql.JSONB),
        sa.Column("persona_draft", postgresql.JSONB),
        sa.Column("context", postgresql.JSONB),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspace.id"], ondelete="CASCADE"),
        sa.CheckConstraint(
            "status IN ('" + "', '".join(STATUSES) + "')", name="ck_onboarding_session_status"
        ),
        sa.CheckConstraint(
            "phase IN ('" + "', '".join(PHASES) + "')", name="ck_onboarding_session_phase"
        ),
        sa.CheckConstraint(
            "(status <> 'completed') OR (completed_at IS NOT NULL)",
            name="ck_onboarding_session_completed_at",
        ),
    )
    # One live journey per workspace. A second concurrent session would race on
    # which one gets to promote its drafts into the Brain.
    op.execute(
        "CREATE UNIQUE INDEX ux_onboarding_session_active ON onboarding_session (workspace_id)"
        " WHERE status = 'active'"
    )

    op.create_table(
        "onboarding_turn",
        sa.Column("id", sa.Uuid, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("session_id", sa.Uuid, nullable=False),
        sa.Column("workspace_id", sa.Uuid, nullable=False),
        sa.Column("seq", sa.Integer, nullable=False),
        sa.Column("role", sa.Text, nullable=False),
        sa.Column("text", sa.Text, nullable=False),
        # Copied from the field catalogue at ask time, never from model output.
        sa.Column("target_field", sa.Text),
        sa.Column("scope", sa.SmallInteger),
        sa.Column("skill", sa.Text),
        sa.Column("skill_version", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["session_id"], ["onboarding_session.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspace.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("session_id", "seq", name="uq_onboarding_turn_seq"),
        sa.CheckConstraint("role IN ('agent', 'user')", name="ck_onboarding_turn_role"),
        sa.CheckConstraint("scope IS NULL OR scope BETWEEN 1 AND 5",
                           name="ck_onboarding_turn_scope"),
        sa.CheckConstraint(
            "target_field IS NULL OR scope IS NOT NULL",
            name="ck_onboarding_turn_scoped_answer",
        ),
    )
    op.create_index("ix_onboarding_turn_session", "onboarding_turn", ["session_id", "seq"])

    for table in TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"""
            CREATE POLICY {table}_workspace_isolation ON {table}
                USING (
                    workspace_id
                    = NULLIF(current_setting('nexus.workspace_id', true), '')::uuid
                )
                WITH CHECK (
                    workspace_id
                    = NULLIF(current_setting('nexus.workspace_id', true), '')::uuid
                )
            """
        )


def downgrade() -> None:
    for table in TABLES:
        op.execute(f"DROP POLICY IF EXISTS {table}_workspace_isolation ON {table}")
    op.drop_index("ix_onboarding_turn_session", table_name="onboarding_turn")
    op.drop_table("onboarding_turn")
    op.execute("DROP INDEX IF EXISTS ux_onboarding_session_active")
    op.drop_table("onboarding_session")
