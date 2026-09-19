"""`public_scan.js_rendered` — a JS shell is not "everything passed". G7.

**Found while building the store (G7), not planned in migration `0037`.**
Without this column, a JavaScript-rendered page (`engine.ScanResult(
gap_checks=(), js_rendered=True)`) and a genuinely perfect page (`gap_checks=()`
because every check held) serialise identically — an empty `checks` array
either way. `/scan`'s "all held" state and its "could not be read" state
(Q51, `app/research/site.py`) are different claims about the world, and a
reader who typed a JavaScript-heavy site deserves to be told which one is
true, not shown a health score for a page nobody could read.

Additive, reversible: one column, `NOT NULL DEFAULT false`, so every row
`0037` could have produced is valid under it without a backfill.

Revision ID: 0038
Revises: 0037
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0038"
down_revision = "0037"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "public_scan",
        sa.Column("js_rendered", sa.Boolean, nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("public_scan", "js_rendered")
