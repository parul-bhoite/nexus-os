"""Database engine and session.

The engine is created lazily so the process can boot — and answer `/health` —
without a database. That matters operationally: liveness must not depend on a
dependency, or an outage becomes a restart loop.

Note what is deliberately absent. There is no `get_session()` that application
code may call freely. From M1, every read goes through `retrieval/`, which takes
a `ScopedSession` and applies the permission predicate as part of the query
(I2, I3). A bare session handed around the codebase is exactly the bypass those
invariants exist to prevent, so the accessor here is named to discourage it and
will become internal to `retrieval/` once that package exists.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from functools import lru_cache

import sqlalchemy as sa
from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from app.config import Settings, get_settings
from app.logging import get_logger

log = get_logger(__name__)


@lru_cache
def get_engine() -> AsyncEngine:
    settings = get_settings()
    url = settings.require("database_url")

    # Four timeouts, and they are not redundant. `statement_timeout` bounds a
    # single query; `lock_timeout` bounds *waiting* for a lock, which the first
    # does not, because a statement blocked on a lock has not started
    # executing; `idle_in_transaction_session_timeout` bounds an open
    # transaction doing nothing, which is the shape a request that died
    # mid-flight leaves behind and the one that blocks every later migration;
    # and asyncpg's `command_timeout` is client-side, so it still fires when
    # the server is unreachable rather than merely slow.
    #
    # Before this there were none. One query that never finished held a
    # connection out of a pool of five until the process was restarted, with
    # `pool_pre_ping` reporting it healthy throughout.
    #
    # **The three server-side ones are applied after connecting, not in the
    # startup packet** — see `_apply_session_timeouts` below. Only
    # `application_name` goes in `server_settings`, because it is the one that
    # survived.
    server_settings = {
        # Named in `pg_stat_activity`, so a connection can be attributed to
        # this process rather than guessed at from its query.
        "application_name": "nexus-api",
    }

    kwargs: dict[str, object] = {
        "echo": False,
        # All four come from settings now, and the reasoning for each value is
        # in `Settings` beside it. They were hardcoded here, which put four
        # numbers whose cost is entirely a function of network distance in the
        # one file that cannot know how far away the database is.
        #
        # The headline: `pool_pre_ping` is a ping per checkout, so it costs one
        # round trip per request — about 2ms against a co-located database and
        # a measured ~1.27s against the Neon instance in `.env`. It stays on by
        # default because the safe default is on; `NEXUS_DB_POOL_PRE_PING=false`
        # is the escape hatch for a remote database, and
        # `db_pool_recycle_seconds` is what keeps that survivable.
        "pool_pre_ping": settings.db_pool_pre_ping,
        "pool_size": settings.db_pool_size,
        "max_overflow": settings.db_pool_max_overflow,
        # Recycle before a provider's idle timeout rather than after it.
        "pool_recycle": settings.db_pool_recycle_seconds,
        # How long a request waits for a connection before failing. The default
        # is 30 seconds, which is longer than a caller will wait.
        "pool_timeout": settings.db_pool_timeout_seconds,
        "connect_args": {
            "server_settings": server_settings,
            "command_timeout": settings.db_command_timeout_seconds,
        },
    }

    # A transaction-mode pooler (PgBouncer, and Neon's `-pooler` endpoint) hands
    # a different server connection to each transaction, so a prepared statement
    # created on one is missing on the next — asyncpg then fails with
    # "prepared statement ... does not exist" under concurrency. Disabling both
    # caches is the documented requirement.
    #
    # Our GUC-based scoping is unaffected: `set_config(..., is_local => true)` is
    # transaction-scoped, so it travels with the transaction rather than the
    # session. Session-level state would have been silently wrong here.
    #
    # Explicit configuration, not a substring match on the hostname. It was
    # `if "-pooler" in url`, which is a guess: true of Neon's pooled endpoint
    # and of nothing else, so PgBouncer in front of RDS or a Cloud SQL proxy
    # left it silently false — and the failure it prevents appears only under
    # concurrency, which is the hardest possible way to find out.
    if settings.db_transaction_pooler:
        kwargs["poolclass"] = NullPool  # the pooler is doing the pooling
        kwargs.pop("pool_size", None)
        kwargs.pop("max_overflow", None)
        kwargs.pop("pool_recycle", None)
        kwargs.pop("pool_timeout", None)
        # And the ping, which is pure waste here. `NullPool` opens a fresh
        # connection for every checkout, so pre-pinging asks "is this brand-new
        # connection alive" — a round trip whose answer is known, on a path
        # where round trips are the thing that hurts.
        kwargs.pop("pool_pre_ping", None)
        # Both caches, and both in `connect_args`. `statement_cache_size` is
        # asyncpg's own; `prepared_statement_cache_size` is SQLAlchemy's, and
        # its adapter pops it from the *connect* keywords rather than accepting
        # it on the engine — so the previous `kwargs[...] = 0` raised
        # `TypeError: Invalid argument(s) 'prepared_statement_cache_size' sent
        # to create_engine()`. This whole branch had therefore never been
        # executed: nothing in the suite used a pooler URL, and production
        # connects to Neon's direct host (ADR 0008). The pooler path did not
        # merely mis-handle the cache; it could not build an engine at all.
        kwargs["connect_args"] = {
            "server_settings": server_settings,
            "command_timeout": settings.db_command_timeout_seconds,
            "statement_cache_size": 0,
            "prepared_statement_cache_size": 0,
        }

    engine = create_async_engine(url, **kwargs)
    _apply_session_timeouts(engine, settings)
    return engine


async def warm_pool() -> int:
    """Open the pool's connections up front. Returns how many came up.

    **A connection costs 7.1 seconds to establish against a remote database**,
    measured — TLS, plus whatever waking a serverless compute involves. Without
    this the first requests after a deploy each pay it one at a time, so the
    slowest requests this application ever serves are the ones a person makes
    immediately after it starts. Which is also when somebody is most likely to
    be watching.

    Opened concurrently, so the whole pool costs about as long as one
    connection rather than `pool_size` times as long.

    **Never raises.** A database that is down must not stop the process from
    starting: `/health` has to come up to *report* that the database is down,
    and a container that refuses to boot reports nothing at all. It returns the
    count and logs the failure, and the pool fills lazily as before.

    Not called when no URL is configured — `get_engine` requires one, and the
    application is required to run without a database for tests and tooling.
    """
    import anyio

    settings = get_settings()
    if not settings.database_url.get_secret_value():
        return 0
    if settings.db_transaction_pooler:
        # `NullPool` holds nothing between checkouts, so there is no pool to
        # fill — the connections opened here would be closed again immediately
        # and the first request would still pay full price. The pooler in front
        # is what is meant to be keeping connections warm.
        return 0

    engine = get_engine()
    opened = 0

    async def one() -> None:
        nonlocal opened
        try:
            async with engine.connect() as conn:
                await conn.execute(sa.text("SELECT 1"))
            opened += 1
        except Exception as exc:
            log.warning("db.warm_pool.failed", error=str(exc))

    async with anyio.create_task_group() as tg:
        for _ in range(max(0, settings.db_pool_size)):
            tg.start_soon(one)

    log.info("db.warm_pool", opened=opened, pool_size=settings.db_pool_size)
    return opened


def _apply_session_timeouts(engine: AsyncEngine, settings: Settings) -> None:
    """Set the three server-side timeouts on every new connection.

    They used to travel in asyncpg's `server_settings`, which becomes the
    connection's startup packet. That works on stock PostgreSQL — and CI runs
    stock PostgreSQL, so it was green — but **Neon's proxy filters the startup
    packet to an allowlist and silently drops all three.** `SHOW
    statement_timeout` on a live application connection returned `0`.

    Silently is the word that matters. Nothing errored, nothing logged, and
    `application_name` — sent in the very same dictionary — arrived intact, so
    the connection looked correctly configured from every angle except asking
    the server what it thought. ADR 0008 makes Neon the production database, so
    for as long as this was true the protection existed in CI and nowhere that
    mattered (finding #15).

    Issued here instead, on the pool's `connect` event, which runs once per
    physical connection rather than once per checkout — so this costs one round
    trip per connection, not one per request.

    `set_config(name, value, false)` rather than `SET name = value`: `SET` takes
    no parameters, so the values would have to be interpolated into the SQL, and
    these come from configuration. `false` is the `is_local` flag, making the
    setting last for the session rather than the transaction — a `SET LOCAL`
    here would be reverted by the first commit and protect nothing.
    """
    timeouts = (
        ("statement_timeout", settings.db_statement_timeout),
        ("lock_timeout", settings.db_lock_timeout),
        ("idle_in_transaction_session_timeout", settings.db_idle_in_transaction_timeout),
    )
    # `$1`, not `%s`. SQLAlchemy's asyncpg dialect is `numeric_dollar` — the
    # first version of this used `%s` and every connection failed with
    # "syntax error at or near %", which is at least a loud failure rather than
    # the silent one it was written to replace.
    statement = "SELECT " + ", ".join(
        f"set_config('{name}', ${i}, false)" for i, (name, _) in enumerate(timeouts, start=1)
    )
    values = tuple(value for _, value in timeouts)

    @event.listens_for(engine.sync_engine, "connect")
    def _set_timeouts(dbapi_connection: object, _record: object) -> None:
        cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
        try:
            cursor.execute(statement, values)
        finally:
            cursor.close()


@lru_cache
def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(get_engine(), expire_on_commit=False)


@asynccontextmanager
async def _unscoped_session() -> AsyncIterator[AsyncSession]:
    """A session with NO permission predicate applied.

    Only infrastructure may use this — health probes, migrations, jobs that
    operate on system tables. Never for reading customer data: that path is
    `retrieval/`, which requires a `ScopedSession`.
    """
    async with get_sessionmaker()() as session:
        yield session


# ── The maintenance connection (ADR 0018) ─────────────────────


@lru_cache
def get_jobs_engine() -> AsyncEngine:
    """The engine for `nexus_jobs`, which is a different role and a smaller one.

    Separate from `get_engine` rather than a parameter on it, because the whole
    value of ADR 0018 is that the two identities cannot be confused: this one
    authenticates with its own credentials and holds a policy on exactly one
    table, and no caller can reach it by passing a flag.

    **It refuses rather than falling back.** An unset `NEXUS_JOBS_DATABASE_URL`
    raises here, and `Settings` refuses to boot without one outside `local` and
    `ci`. Falling back to the application role would let the expiry sweep run
    under a policy that hides every row from it — matching zero and reporting
    success, which is precisely the silent failure D24 was raised about.
    """
    settings = get_settings()
    url = settings.jobs_database_url.get_secret_value()
    if not url:
        raise RuntimeError(
            "NEXUS_JOBS_DATABASE_URL is not set. Maintenance writes connect as "
            "nexus_jobs (ADR 0018); running them as nexus_app would silently "
            "match zero rows under the domain_claim policy."
        )

    engine = create_async_engine(
        url,
        echo=False,
        pool_pre_ping=True,
        # A sweep every hour and the occasional dispute record. A pool would
        # hold connections open on a serverless Postgres billed for them.
        poolclass=NullPool,
        connect_args={
            "server_settings": {"application_name": "nexus-jobs"},
            "command_timeout": settings.db_command_timeout_seconds,
        },
    )
    _apply_session_timeouts(engine, settings)
    return engine


@asynccontextmanager
async def jobs_session() -> AsyncIterator[AsyncSession]:
    """A session as `nexus_jobs`. Never for request-path reads of user data.

    The only callers are the expiry sweep and the dispute record — the two
    writes ADR 0018 names. Anything else belongs on `_unscoped_session` or, for
    customer data, on `retrieval/`.
    """
    factory = async_sessionmaker(get_jobs_engine(), expire_on_commit=False)
    async with factory() as session:
        yield session
