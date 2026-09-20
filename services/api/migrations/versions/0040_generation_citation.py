"""`generation_citation` — which passages an answer actually quoted.

`doc/20` A4. **ADR 0056** fixes the shape and **ADR 0057** the scope rule;
neither is re-decided here.

**Rows rather than ids in `input_snapshot`**, because the question this table
exists to answer is *"which answers quoted this chunk?"* — asked by a customer
wanting to know what an answer was based on, and by a deletion request that must
find every artefact derived from a document. In JSON that is an unindexed scan
with no referential integrity; here it is a foreign key.

That integrity is load-bearing rather than tidy. ADR 0053 lets a citation
**license a figure** — the numerals an answer may state are the ones in the
passages it cited — so a citation the database will not vouch for is a
permission to state a number.

**`workspace_id` is on the row**, not reached by joining `generation` inside the
policy. A policy that joins is a second place isolation can be written wrongly,
and `nexus_app` is `NOBYPASSRLS`: a wrong policy returns **zero rows rather than
an error**, which reads as an empty table rather than as a fault.

**`ON DELETE RESTRICT` on `chunk_id` is the deliberate friction.** `CASCADE`
would erase the evidence exactly when a chunk is deleted — the answer would
remain and its basis would be gone, which is the opposite of what a ledger is
for. `RESTRICT` means a cited chunk cannot be hard-deleted and a hard delete
will fail loudly. `document` already soft-deletes, so the ordinary path is
untouched; what this blocks is precisely the operation that should stop and ask.
`generation_id` cascades, because deleting the answer deletes the thing the
citation is about.

Purely additive: no `DROP`, no column rewritten, no existing row touched.

Revision ID: 0040
Revises: 0039
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0040"
down_revision = "0039"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "generation_citation",
        sa.Column("id", sa.Uuid, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        # Local, so the policy below keys on this row and never on a join.
        sa.Column("workspace_id", sa.Uuid, nullable=False),
        sa.Column("generation_id", sa.Uuid, nullable=False),
        sa.Column("chunk_id", sa.Uuid, nullable=False),
        sa.Column("document_id", sa.Uuid, nullable=False),
        # Enough to render the citation without re-reading the chunk — and to
        # keep rendering it if the chunk later becomes unreadable to this
        # caller. A citation a reader cannot follow is decoration, but one that
        # disappears from an answer they already saw is worse.
        sa.Column("source_page", sa.Integer, nullable=True),
        sa.Column("source_label", sa.Text, nullable=False, server_default=""),
        # The order the answer cited them in, so it renders as written rather
        # than in whatever order the rows come back.
        sa.Column("ordinal", sa.Integer, nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspace.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["generation_id"], ["generation.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["chunk_id"], ["chunk.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["document_id"], ["document.id"], ondelete="RESTRICT"),
        # One answer cites one chunk once. A duplicate is a bug in the caller,
        # and silently storing it would double-count every "which answers
        # quoted this?" figure.
        sa.UniqueConstraint(
            "generation_id", "chunk_id", name="uq_generation_citation__generation_chunk"
        ),
        sa.CheckConstraint("ordinal >= 0", name="ck_generation_citation_ordinal_non_negative"),
    )

    # "Which answers quoted this chunk?" and its document-level sibling. Both
    # are the deletion path's queries, not reporting conveniences.
    op.create_index("ix_generation_citation__chunk", "generation_citation", ["chunk_id"])
    op.create_index("ix_generation_citation__document", "generation_citation", ["document_id"])
    # Reading one answer's citations back, in order.
    op.create_index(
        "ix_generation_citation__generation", "generation_citation", ["generation_id", "ordinal"]
    )

    op.execute("ALTER TABLE generation_citation ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE generation_citation FORCE ROW LEVEL SECURITY")
    # Mirrors `generation_workspace_isolation` exactly, including `WITH CHECK`:
    # without it a caller could insert a row into another workspace that they
    # then could not see, which is a write leak wearing a read guarantee.
    op.execute(
        """
        CREATE POLICY generation_citation_workspace_isolation ON generation_citation
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
    op.execute(
        "DROP POLICY IF EXISTS generation_citation_workspace_isolation ON generation_citation"
    )
    op.drop_index("ix_generation_citation__generation", table_name="generation_citation")
    op.drop_index("ix_generation_citation__document", table_name="generation_citation")
    op.drop_index("ix_generation_citation__chunk", table_name="generation_citation")
    op.drop_table("generation_citation")
