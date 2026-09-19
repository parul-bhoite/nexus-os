"""`public_scan` — the anonymous Instant Gap Analysis scan result. ADR 0048.

**No `workspace_id`, and no RLS.** Every other table in this schema carries a
tenant column that `FORCE ROW LEVEL SECURITY`'s policy filters on
(`nexus.workspace_id`); this row is written before any workspace exists, for
a domain the visitor merely typed. There is no tenant to write the predicate
against — an `ENABLE ROW LEVEL SECURITY` with no matching policy would deny
every row to every role including the one that wrote it, and a policy that
matched everything would be RLS in name only. A named absence, checked by
`tests/test_public_scan_schema.py`, is safer than either.

**Only computed signals are stored, never page content.** `checks` and
`scores` are what `app/calculators/audit.py` produced — a label and an
evidence string per check, never HTML, never `page_signals.py`'s
`text_sample`, never a scraped email address. That precedent
(`SIGNALS_NOT_STORED`, ADR 0048 rule 1) is what makes this table's contents
safe to hold with no workspace boundary around them at all.

**`expires_at` defaults to seven days from `created_at`, set by the database,
not by the inserting code.** ADR 0048's retention window is structural this
way: a caller cannot forget to set it, and a raw insert (this migration's own
test) proves the seven days without any application code existing yet.

**`ix_public_scan__domain_created`** is the read path: the freshest
unexpired, undeleted row for a domain. **`ix_public_scan__expires_at`** is
`jobs/expiry.py`'s sweep (G11) — partial, over live rows only, because a
soft-deleted row is that job's business regardless of its TTL.

Revision ID: 0037
Revises: 0036
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0037"
down_revision = "0036"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "public_scan",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        # Normalised (lowercase, no scheme, no trailing slash) — the shape
        # `app.connectors.domain_check.normalise_domain` already produces, so
        # the cache lookup and the domain-verification path agree on what a
        # domain string looks like.
        sa.Column("domain", sa.Text, nullable=False),
        # The URL actually fetched, after redirects — may differ from
        # `domain` (http -> https, a bare domain redirecting to `/en`, etc.)
        # and is kept so the record says what was really read.
        sa.Column("scanned_url", sa.Text, nullable=False),
        sa.Column("checks", postgresql.JSONB, nullable=False),
        sa.Column("scores", postgresql.JSONB, nullable=False),
        # Stored, never assumed — `doc/18` §3. Always 1 under the current
        # budget, but the column says so rather than the reader inferring it.
        sa.Column("pages_read", sa.Integer, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "expires_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now() + interval '7 days'"),
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
    )

    op.create_index(
        "ix_public_scan__domain_created",
        "public_scan",
        ["domain", sa.text("created_at DESC")],
    )
    op.create_index(
        "ix_public_scan__expires_at",
        "public_scan",
        ["expires_at"],
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    # Deliberately no RLS — see the module docstring.


def downgrade() -> None:
    op.drop_table("public_scan")
