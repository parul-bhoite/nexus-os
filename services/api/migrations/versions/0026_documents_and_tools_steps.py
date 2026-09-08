"""Two steps between the interview and the assembly: documents, then tools.

Two changes, and they are one change.

**`ck_onboarding_session_phase` gains `documents` and `tools`.** They sit after
`discovery` and before `persona`, which is the ordering the whole feature is
about: the Persona and the Company Brain are assembled from whatever is in hand
when `finish` runs, so everything the person supplies has to be in hand before
it. A journey that assembled first and collected the files afterwards would
produce a Brain that had never read the price list it quotes from, and the only
repair would be assembling it again — every model call paid for twice to reach a
state that could have been reached once.

The order is not enforced here, because a `CHECK` on one column cannot see a
transition. It is enforced in `POST /onboarding/agent/finish`, which reads the
phase off this row under `FOR UPDATE` and refuses to start the assembly from
`discovery` or `documents`. What this migration guarantees is narrower and still
worth having: no other value can be written into the column, so the guard cannot
be defeated by a phase nobody planned for.

**`workspace_connection` records which systems a company runs on.** One row per
workspace per tool, with the *lifecycle* in a column rather than implied by the
row existing:

    declared -> connected -> (revoked | scope_reduced)

Every row today is `declared`, because no OAuth flow exists — `doc/12` P18 waits
on D3 for Google credentials and D10 for the CRM choice. That is exactly why the
state is a column. "The row exists" would have meant "we can read this system",
which would have been false for every row in the table, and the tile that
rendered from it would have come up empty rather than locked. `declared` says
the true thing: they told us, and we have never reached it. When the OAuth half
lands it moves the same row forward. No migration, no second table, and no
guessing afterwards about which connections were ever actually live.

`declared_by` is kept because a declaration is a claim somebody made. When a
Brain says invoices are in Xero and nobody can remember agreeing to that, the
question is who said so and when — and `updated_at` alone cannot answer it.

Revision ID: 0026
Revises: 0025
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0026"
down_revision = "0025"
branch_labels = None
depends_on = None

PHASES = (
    "analysing",
    "brief",
    "discovery",
    "documents",
    "tools",
    "persona",
    "assembling",
    "ready",
)
"""Mirrors `app.domain.onboarding_sessions.Phase`, compared on every run by
`test_constraint_enum_parity`. Written out rather than imported because a
migration that imports application code is a migration that stops running the
day that code is refactored — and the whole point of a migration is that it
still runs against the schema it was written for."""

STATES = ("declared", "connected", "revoked", "scope_reduced")
"""Mirrors `app.domain.connectors.ConnectionState`."""

PROVIDERS = (
    "ga4",
    "search_console",
    "hubspot",
    "salesforce",
    "pipedrive",
    "zoho_crm",
    "xero",
    "quickbooks",
    "stripe",
)
"""Mirrors the ids in `app.domain.connections.PROVIDERS`.

A closed list rather than free text, so that a client cannot store
`provider: "our internal thing"` and leave a row that no dashboard, no gap list
and no future OAuth handler knows what to do with. Adding a tool is a migration,
which is the correct cost: each one needs a name, a department and a sentence
saying what it unlocks before it can honestly appear on the screen.
"""


def upgrade() -> None:
    # Dropped and recreated rather than altered: Postgres has no
    # `ALTER CONSTRAINT` for a CHECK expression, and `NOT VALID` plus a validate
    # buys nothing here — the table is small and every existing row already
    # holds one of the six values this list is a superset of.
    op.drop_constraint("ck_onboarding_session_phase", "onboarding_session")
    op.create_check_constraint(
        "ck_onboarding_session_phase",
        "onboarding_session",
        "phase IN ('" + "', '".join(PHASES) + "')",
    )

    op.create_table(
        "workspace_connection",
        sa.Column("id", sa.Uuid, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("workspace_id", sa.Uuid, nullable=False),
        sa.Column("provider", sa.Text, nullable=False),
        sa.Column("state", sa.Text, nullable=False, server_default="declared"),
        # Who made the claim, and when. Not derivable from `updated_at`, which
        # answers "when did this row last change" and not "who told us this".
        sa.Column("declared_by", sa.Uuid, nullable=False),
        sa.Column("declared_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        # Null until the OAuth half lands, and then never null again for a row
        # that reached `connected` — the CHECK below is what makes that true.
        sa.Column("connected_at", sa.DateTime(timezone=True)),
        # What the connection turned out to support, from `check_completeness`,
        # written at connect. Empty for a declaration: a field-completeness
        # verdict about a system we have never read would be fabricated.
        sa.Column("capabilities", postgresql.JSONB),
        sa.Column("last_error", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspace.id"], ondelete="CASCADE"),
        # `RESTRICT`, not `CASCADE`. A member leaving must not silently delete
        # the record of which systems the company runs on — that is a fact about
        # the business, not about the person who typed it.
        sa.ForeignKeyConstraint(["declared_by"], ["app_user.id"], ondelete="RESTRICT"),
        # One row per tool per workspace. Without this, re-opening the step and
        # pressing continue twice records the same system twice, and the gap
        # list says "connect Xero" in duplicate.
        sa.UniqueConstraint("workspace_id", "provider", name="uq_workspace_connection_provider"),
        sa.CheckConstraint(
            "provider IN ('" + "', '".join(PROVIDERS) + "')",
            name="ck_workspace_connection_provider",
        ),
        sa.CheckConstraint(
            "state IN ('" + "', '".join(STATES) + "')",
            name="ck_workspace_connection_state",
        ),
        # A connection cannot claim to be live without saying when it became so.
        # The same shape as `ck_onboarding_session_completed_at`, and for the
        # same reason: a state that implies a moment must carry the moment, or
        # the first question anybody asks about it has no answer in the row.
        sa.CheckConstraint(
            "(state <> 'connected') OR (connected_at IS NOT NULL)",
            name="ck_workspace_connection_connected_at",
        ),
    )

    op.execute("ALTER TABLE workspace_connection ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE workspace_connection FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY workspace_connection_workspace_isolation ON workspace_connection
            USING (
                workspace_id = NULLIF(current_setting('nexus.workspace_id', true), '')::uuid
            )
            WITH CHECK (
                workspace_id = NULLIF(current_setting('nexus.workspace_id', true), '')::uuid
            )
        """
    )


def downgrade() -> None:
    op.execute(
        "DROP POLICY IF EXISTS workspace_connection_workspace_isolation ON workspace_connection"
    )
    op.drop_table("workspace_connection")

    # Any session parked in one of the two new steps has to go somewhere the old
    # constraint permits, or recreating it fails on the rows this migration made
    # reachable. `discovery` is the honest landing place: the interview is over,
    # the assembly has not begun, and that is precisely where these sessions
    # are. It costs the person the closing card again, which is the cheapest
    # possible consequence of a rollback.
    op.execute(
        "UPDATE onboarding_session SET phase = 'discovery'"
        " WHERE phase IN ('documents', 'tools')"
    )
    op.drop_constraint("ck_onboarding_session_phase", "onboarding_session")
    op.create_check_constraint(
        "ck_onboarding_session_phase",
        "onboarding_session",
        "phase IN ('analysing', 'brief', 'discovery', 'persona', 'assembling', 'ready')",
    )
