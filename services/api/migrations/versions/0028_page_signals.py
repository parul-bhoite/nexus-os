"""`page_signals` — what each crawled page demonstrably contained.

**Why a table and not a JSONB key on something that already exists.**

Two candidates were rejected. `onboarding_session.research` is written by
`save_crawl`, which does `{k: _storable(str(v)) for k, v in dict(p).items()}`
(`app/domain/onboarding_sessions.py`) — a nested dict would be stored as its
Python `repr` and come back as an unparseable string. It is also written with
`research = COALESCE(research,'{}') || :patch`, a merge rather than a replace,
so a reader would have to know which of two differently-shaped writers wrote
last. `research_source.result_json` was rejected because it does not exist for
the onboarding path at all.

**Why this table exists now, having not existed for a year.**
`app/research/extract.py::extract_signals` and `app/calculators/audit.py` were
both written in M2, are both pure, and had **zero callers** — because the crawl
kept only `{"url", "text"}` and threw the HTML away. `PageSignals` was
unrecoverable from anything stored, so the scoring functions could never be
fed. This table is the missing half.

**`superseded_at` rather than a unique key**, matching `company_brain`. A
re-crawl marks the previous rows superseded and inserts fresh ones in the same
transaction, so a reader ordering by `position` cannot pick a stale page and a
history remains for anyone asking why a figure moved.

**`position` is the index into the caller's *kept* page list.** Onboarding
filters pages by `is_prose` after the crawl returns, so `position = 0` is the
first page that survived that filter, not the first fetched. `site.plan` orders
by priority, which makes 0 the page the crawl led with — a documented rule
rather than a guess about which URL is the home page.

**The `nexus_jobs` grant is load-bearing, and asymmetric to 0020 and 0024.**
The background crawl runs on the maintenance role (`app/jobs/scheduler.py` uses
`jobs_session()`), so without a grant `worker_loop._record` dies with
`permission denied` inside a broad `except` that renders to the founder as
"This step did not finish", naming nothing. Unlike 0021 this needs **no extra
policy**: policies are `TO PUBLIC` by default, so the workspace-isolation
policy below already covers `nexus_jobs`, and `_record` calls
`apply_workspace_scope` before writing. 0021 needed `USING (true)` because a
run is *claimed* before its workspace is known; a signals insert happens after.

Revision ID: 0028
Revises: 0027
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0028"
down_revision = "0027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "page_signals",
        sa.Column(
            "id", sa.Uuid, primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column("workspace_id", sa.Uuid, nullable=False),
        sa.Column("captured_by", sa.Text, nullable=False),
        sa.Column("session_id", sa.Uuid),
        sa.Column("run_id", sa.Uuid),
        sa.Column("url", sa.Text, nullable=False),
        sa.Column("position", sa.Integer, nullable=False),
        sa.Column("signals", postgresql.JSONB, nullable=False),
        sa.Column(
            "captured_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("superseded_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspace.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["session_id"], ["onboarding_session.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["run_id"], ["research_run.id"], ondelete="CASCADE"),
        # The value list. Registered against `app.research.signals.CaptureSource`
        # in `tests/test_constraint_enum_parity.py` in this same commit — a
        # value-list CHECK with no Python counterpart fails
        # `test_every_value_list_constraint_is_registered` rather than the test
        # it was added for, which has cost three CI round trips before.
        sa.CheckConstraint(
            "captured_by IN ('onboarding', 'research_run')",
            name="ck_page_signals_captured_by",
        ),
        # Provenance is not optional and not guessable. A signals row that
        # cannot name the crawl it came from is a number nobody can trace back
        # to a fetch, and being checkable is the one property this product
        # cannot give up. Enforced here rather than in code because "we always
        # set one of them" is a claim about code that changes.
        sa.CheckConstraint(
            "(captured_by = 'onboarding' AND session_id IS NOT NULL AND run_id IS NULL)"
            " OR (captured_by = 'research_run' AND run_id IS NOT NULL AND session_id IS NULL)",
            name="ck_page_signals_provenance",
        ),
    )

    # Partial, because every read filters on `superseded_at IS NULL` and the
    # superseded rows are history nobody queries by position.
    op.execute(
        "CREATE INDEX ix_page_signals_current ON page_signals (workspace_id, position)"
        " WHERE superseded_at IS NULL"
    )

    op.execute("ALTER TABLE page_signals ENABLE ROW LEVEL SECURITY")
    # ENABLE alone is not enough: the table owner bypasses an enabled policy,
    # and `nexus_app` owns every table here — which is what lets it set FORCE at
    # all. `tests/test_page_signals_isolation.py` asserts both flags against
    # `pg_class` rather than trusting that both statements ran.
    op.execute("ALTER TABLE page_signals FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY page_signals_workspace_isolation ON page_signals
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

    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'nexus_jobs') THEN
                -- SELECT, INSERT and UPDATE. INSERT because the background
                -- crawl is a real writer here, unlike 0021 where the worker
                -- only claims and finishes rows the application created.
                -- UPDATE for the supersede. No DELETE: superseded rows are the
                -- history that explains why a figure moved.
                GRANT SELECT, INSERT, UPDATE ON page_signals TO nexus_jobs;
            ELSE
                RAISE NOTICE 'nexus_jobs is absent: skipping the page_signals grant. '
                    'The background crawl will fail to store signals until '
                    'db/bootstrap.sql has run.';
            END IF;
        END $$;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'nexus_jobs') THEN
                REVOKE ALL ON page_signals FROM nexus_jobs;
            END IF;
        END $$;
        """
    )
    op.execute("DROP POLICY IF EXISTS page_signals_workspace_isolation ON page_signals")
    op.execute("DROP INDEX IF EXISTS ix_page_signals_current")
    op.drop_table("page_signals")
