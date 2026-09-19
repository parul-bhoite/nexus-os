"""Narrow the worker's `research_source` policies to the workspace GUC.

Migration 0021 gave `nexus_jobs` `USING (true)` on both `research_run` and
`research_source`, for one good reason that applies to only one of them: **the
worker has no workspace until it claims a run.** `CLAIM_SQL` is an UPDATE on
`research_run` issued before anybody knows whose row it is, so that policy must
be workspace-blind and stays exactly as it was.

`research_source` is different. Every access to it happens *after* the claim has
said which workspace this is, and `worker_loop` calls `apply_workspace_scope`
immediately before each one. The blanket policy therefore bought nothing and
cost the one thing this table's isolation exists to provide.

**What it cost, concretely.** `research_source_workspace_isolation` is a
`PUBLIC` policy `FOR ALL`, so it already governs `nexus_jobs` — but permissive
policies **OR**, so `USING (true)` beside it meant the GUC could not reduce a
rowcount to zero for this role. That is precisely the failure
`worker_loop._write_one` was added to catch: an UPDATE running with the scope
lost, matching nothing, raising nothing, and leaving a run that never finishes.
The guard fired in tests, which drive the app role, and was inert on the
deployed path, which is `nexus_jobs`. A guard that cannot fire where the bug
happens is worse than none, because the register records the pattern as closed.

**Dropped rather than replaced.** Rewriting them as GUC-keyed policies would
duplicate `research_source_workspace_isolation` exactly, and two identical
permissive policies are one policy with a second place to drift. Removing them
leaves the PUBLIC isolation policy as the single rule for every role. The
`GRANT SELECT, UPDATE` stays: table privileges and row policies are separate,
and the worker still needs the privilege.

ADR 0050. Finding #26.

Revision ID: 0039
Revises: 0038
"""

from __future__ import annotations

from alembic import op

revision = "0039"
down_revision = "0038"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'nexus_jobs') THEN
                -- The grant is deliberately untouched. Only the blanket row
                -- policies go; `research_source_workspace_isolation` (PUBLIC,
                -- FOR ALL, keyed on nexus.workspace_id) governs this role from
                -- here, which is what makes a lost scope match zero rows.
                DROP POLICY IF EXISTS research_source_worker ON research_source;
                DROP POLICY IF EXISTS research_source_worker_write ON research_source;
            ELSE
                RAISE NOTICE
                    'nexus_jobs does not exist - nothing to narrow; re-run db/bootstrap.sql';
            END IF;
        END $$;
        """
    )


def downgrade() -> None:
    """Restore 0021's blanket policies verbatim.

    Reversible, but note what reversing means: the worker regains the ability to
    write any workspace's sources with no GUC set, and `_write_one` goes quiet
    again on the path that matters.
    """
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'nexus_jobs') THEN
                CREATE POLICY research_source_worker ON research_source
                    FOR SELECT TO nexus_jobs USING (true);
                CREATE POLICY research_source_worker_write ON research_source
                    FOR UPDATE TO nexus_jobs USING (true) WITH CHECK (true);
            END IF;
        END $$;
        """
    )
