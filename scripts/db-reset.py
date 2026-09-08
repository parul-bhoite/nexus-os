"""Empty every application table, keeping the schema and the migration head.

A fresh sandbox without a migration round trip. Use it when you want to walk the
product from registration again — not as part of the gate, which builds its own
throwaway database from `bootstrap.sql` (ADR 0014) and cannot drift.

Two things worth knowing before reading the output of anything else:

**`SELECT count(*)` lies here.** Most tables carry `FORCE ROW LEVEL SECURITY`, so
a count taken without `nexus.workspace_id` set returns only the rows that are
visible to nobody in particular — which is usually none of them. A workspace's
sessions, turns and audit rows all read as zero from a plain psql session. That
is the policy working, not an empty table.

**`TRUNCATE` is not filtered by RLS.** Row-level security governs `SELECT`,
`INSERT`, `UPDATE` and `DELETE`; `TRUNCATE` is a table-level operation gated by
the `TRUNCATE` privilege alone. So this clears everything even though a count
cannot see it — and the verification below checks heap size rather than counting,
because `nexus_app` is deliberately unable to turn the policies off.

`alembic_version` is left alone. The point is a clean sandbox at the current
head, not a downgrade.

    python scripts/db-reset.py            # clear it
    python scripts/db-reset.py --dry-run  # list what would be cleared
"""

from __future__ import annotations

import argparse
import asyncio
import pathlib
import sys

import asyncpg

REPO = pathlib.Path(__file__).resolve().parent.parent
KEEP = {"alembic_version"}


def database_url() -> str:
    """The URL from `.env`, rewritten from asyncpg's spelling to libpq's."""
    env = REPO / ".env"
    for line in env.read_text().splitlines():
        if line.startswith("NEXUS_DATABASE_URL="):
            raw = line.split("=", 1)[1].strip().strip('"').strip("'")
            return raw.replace("postgresql+asyncpg://", "postgresql://").replace(
                "?ssl=require", ""
            )
    raise SystemExit(f"no NEXUS_DATABASE_URL in {env}")


async def main(dry_run: bool) -> int:
    conn = await asyncpg.connect(database_url(), ssl="require")
    try:
        head = await conn.fetchval("SELECT version_num FROM alembic_version")
        tables = [
            r["tablename"]
            for r in await conn.fetch(
                "SELECT tablename FROM pg_tables WHERE schemaname = 'public' "
                "ORDER BY tablename"
            )
            if r["tablename"] not in KEEP
        ]
        print(f"migration head: {head}")
        print(f"{len(tables)} application tables")

        if dry_run:
            for name in tables:
                print(f"  would clear  {name}")
            return 0

        # One statement, so the foreign keys between these tables never see a
        # half-cleared database. CASCADE is belt and braces: every table with a
        # reference into this set is already in it.
        quoted = ", ".join(f'"{name}"' for name in tables)
        await conn.execute(f"TRUNCATE TABLE {quoted} RESTART IDENTITY CASCADE")

        # Verify by heap size, not by counting.
        #
        # `SET row_security = off` is the obvious move and it does not work here:
        # `nexus_app` is `NOSUPERUSER NOBYPASSRLS` by design, so Postgres refuses
        # the query outright rather than quietly returning a filtered count. That
        # refusal is the isolation model working and must not be argued with — no
        # `NO FORCE ROW LEVEL SECURITY`, however temporary.
        #
        # `TRUNCATE` rewrites the relation to an empty file, so a heap of zero
        # bytes is proof the table is empty that no policy can filter.
        remaining = {
            name: size
            for name in tables
            if (size := await conn.fetchval("SELECT pg_relation_size($1::regclass)", name))
        }
        if remaining:
            print("STILL POPULATED (bytes on disk):", remaining, file=sys.stderr)
            return 1
        print(f"cleared — all {len(tables)} tables empty, schema still at {head}")
        return 0
    finally:
        await conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="list, do not clear")
    raise SystemExit(asyncio.run(main(parser.parse_args().dry_run)))
