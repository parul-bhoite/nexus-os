"""`generation.prose` — the sentence, stored beside the provenance that backs it.

**The table held everything about an answer except the answer.** Migration 0023
gave `generation` the inputs (`input_snapshot`), the arithmetic
(`calculation_trace`), the outcome, the refusal reason and the token counts —
and `Answer.prose` was persisted nowhere. So a narrated sentence lived exactly
as long as the HTTP response that carried it, and a founder who reloaded a tile
lost it.

**One column, not a `narration` table.** A separate table would permit a
sentence with no generation row behind it, which is the unfalsifiable state P14
exists to forbid; and the prose is derived from the same inputs, so it has to
inherit the same `scope_key` and the same retention tag. One row makes both
true by construction.

`ck_generation_prose_matches_outcome` is the exact shape of
`ck_generation_reason_matches_outcome`, for the exact analogue of its reason:
an `answered` row with no prose claims success and can show nothing, and an
`unavailable` row carrying prose is prose that nothing validated.
`ledger.record` raises a `ValueError` on the same pair before the insert, so a
caller is told which branch forgot rather than reading a constraint name off
Neon.

The index is what makes the read-back an index scan. 0023 built
`(workspace_id, created_at)` and `(requested_by_user_id, created_at)` for reads
that were never built; neither carries `module`, and the dashboard's read is
`DISTINCT ON (module) … ORDER BY module, created_at DESC`. Non-partial
deliberately: a `WHERE outcome = 'answered'` variant would be a second index on
nearly the same columns, and the outcome filter is cheap once the two-column
prefix has narrowed it.

Additive. No `DROP`, and the table is empty, so the CHECK cannot fail an
existing row.

Revision ID: 0029
Revises: 0028
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0029"
down_revision = "0028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "generation",
        # `server_default=""` rather than nullable: every existing row is a
        # refusal or does not exist, and an empty string is what the CHECK
        # below requires of one. A nullable column would make "no sentence" and
        # "nobody set the column" the same value, which is the distinction
        # `unavailable_reason` already declines to blur.
        sa.Column("prose", sa.Text, nullable=False, server_default=""),
    )
    op.create_check_constraint(
        "ck_generation_prose_matches_outcome",
        "generation",
        "(outcome = 'answered') = (prose <> '')",
    )
    op.create_index(
        "ix_generation_workspace_module_recent",
        "generation",
        ["workspace_id", "module", sa.text("created_at DESC")],
    )


def downgrade() -> None:
    op.drop_index("ix_generation_workspace_module_recent", table_name="generation")
    op.drop_constraint("ck_generation_prose_matches_outcome", "generation", type_="check")
    op.drop_column("generation", "prose")
