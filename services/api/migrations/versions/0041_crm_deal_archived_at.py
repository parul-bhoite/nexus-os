"""`crm_deal.archived_at` — bringing a typed deal in line with "archive, never delete".

`apps/web/components/ops/WorkRecorder.tsx`'s header rule is "archive, never
delete", and every other ops row type (`ops_project`, `ops_task`,
`ops_milestone`, `ops_issue`, `ops_dispatch`, `ops_stock_item`, `ops_supplier`)
already carries `archived_at` for it. `crm_deal` was the one exception, and
0031's own docstring said why — it is a sync target, and a provider that stops
reporting a deal means the row goes.

That reasoning covers `provider != 'nexus'` rows. It never covered a **typed**
deal (`provider = 'nexus'`, ADR 0038): nothing syncs those away, a founder types
them the same way they type a task, and `ops.py`'s `delete_deal` was hard-
deleting them with only a confirm dialog standing in for the archive path every
sibling record type already has. This column is what closes that gap without
touching the sync path — a synced row simply never gets `archived_at` set.

**Column shape matches `0036`'s `ops_stock_item.archived_at` and
`ops_supplier.archived_at` exactly**: `TIMESTAMPTZ`, nullable, no default. A
default would mean every existing row is backfilled to "archived at migration
time", which is false for every one of them.

**The partial index matches the shape of `ix_ops_stock_item_live` /
`ix_ops_supplier_live`** — `WHERE archived_at IS NULL` — but keyed on
`(workspace_id, provider)` rather than `(workspace_id, name)`, because that is
the pair `retrieval/deals.py` actually filters live rows by (`both_populations`
partitions on `provider` after reading by `workspace_id`; `typed_deal_records`
filters on both directly).

**No RLS change.** `crm_deal_workspace_isolation` from `0031` already covers
every column on the row including this one; adding a column to a table with
`FORCE ROW LEVEL SECURITY` does not touch the policy, and this migration does
not drop or recreate it.

Purely additive: one column, one partial index. No `DROP`, no existing row
touched.

Revision ID: 0041
Revises: 0040
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0041"
down_revision = "0040"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("crm_deal", sa.Column("archived_at", sa.DateTime(timezone=True)))

    op.create_index(
        "ix_crm_deal_live",
        "crm_deal",
        ["workspace_id", "provider"],
        postgresql_where=sa.text("archived_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_crm_deal_live", table_name="crm_deal")
    op.drop_column("crm_deal", "archived_at")
