"""Database timeouts, asserted on the server rather than on the keyword arguments.

`app/db.py` set none of these. A single query that never finished would hold a
connection from a pool of five until the process was restarted, and a
transaction left open by a request that died mid-flight would hold its locks
indefinitely — with `pool_pre_ping` cheerfully reporting the connection healthy.
On a serverless Postgres billed by connection-time that is also a cost bug.

The four that matter here are different from each other, which is why all four
are set rather than one:

- `statement_timeout` bounds a single query;
- `lock_timeout` bounds *waiting* for a lock, which a statement timeout does not,
  because a statement blocked on a lock has not started executing;
- `idle_in_transaction_session_timeout` bounds an open transaction doing nothing
  — the shape a crashed request leaves behind, and the one that blocks DDL;
- asyncpg's `command_timeout` is client-side, so it still fires when the server
  is unreachable rather than merely slow. A server-side timeout cannot help
  when the answer never arrives.

Asserted with `SHOW`, against the application's own engine, because a test over
`create_async_engine`'s keyword arguments proves the arguments were passed and
not that Postgres accepted them — and `server_settings` names are silently
per-driver.

**That distinction stopped being theoretical.** The three server-side timeouts
originally travelled in asyncpg's `server_settings`, which becomes the startup
packet. Stock PostgreSQL honours it; **Neon's proxy filters the startup packet
and dropped all three**, so `SHOW statement_timeout` on a live application
connection returned `0` while `application_name`, sent in the same dictionary,
arrived intact. CI runs stock PostgreSQL, so these tests passed there throughout
— the protection existed in CI and nowhere that mattered, since ADR 0008 makes
Neon production (finding #15).

They are now issued with `set_config` on the pool's `connect` event. The tests
below are written so that reverting to `server_settings` fails them **on Neon**
and still passes on stock PostgreSQL, which is the honest shape of this problem:
no test run against one database can prove a claim about the other. Run the
suite against Neon before believing anything here.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from sqlalchemy import text
from sqlalchemy.pool import NullPool

from app.config import Env, Settings, get_settings
from app.db import _unscoped_session, get_engine, get_sessionmaker
from tests.dburl import async_database_url

ASYNC_DB_URL = async_database_url()

# The real marker, declared in pyproject.toml. See the note in conftest.py.
requires_db = pytest.mark.requires_db


@pytest.fixture
async def app_db(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[None]:
    """Point the application's engine at the real database for this test."""
    assert ASYNC_DB_URL is not None
    monkeypatch.setenv("NEXUS_DATABASE_URL", ASYNC_DB_URL)
    for cache in (get_settings, get_engine, get_sessionmaker):
        cache.cache_clear()
    try:
        yield
    finally:
        await get_engine().dispose()
        for cache in (get_settings, get_engine, get_sessionmaker):
            cache.cache_clear()


@requires_db
@pytest.mark.parametrize(
    ("guc", "expected_ms"),
    [
        ("statement_timeout", 15_000),
        ("lock_timeout", 5_000),
        ("idle_in_transaction_session_timeout", 180_000),
    ],
)
async def test_the_server_has_the_timeout_applied(guc: str, expected_ms: int, app_db: None) -> None:
    """The session actually has it, not merely that we asked for it.

    Read from `pg_settings`, which reports the value in the setting's base unit
    — milliseconds for all three — rather than from `SHOW`, which renders it for
    a human and **normalises the units while doing so**. That is not a
    hypothetical: raising the idle timeout from `30s` to `180s` made `SHOW`
    return `3min`, and this test failed on a change that was entirely correct.
    A test that breaks when nothing broke teaches people to edit the test.
    """
    async with _unscoped_session() as session:
        value = (
            await session.execute(
                text("SELECT setting FROM pg_settings WHERE name = :guc"), {"guc": guc}
            )
        ).scalar_one()
    assert int(value) == expected_ms


@requires_db
async def test_the_timeouts_survive_a_pool_checkout_cycle(app_db: None) -> None:
    """Set once per connection, not once per session.

    `set_config(..., false)` is session-scoped, so it lasts as long as the
    physical connection and a pooled connection carries it into the next
    request. The failure this rules out is a `SET LOCAL` — reverted by the first
    commit, which would leave the second and every later user of that connection
    unprotected while the first checkout looked fine.
    """
    async with _unscoped_session() as session:
        first = (await session.execute(text("SHOW statement_timeout"))).scalar_one()
        # A commit is what would discard a transaction-scoped setting.
        await session.commit()
        after_commit = (await session.execute(text("SHOW statement_timeout"))).scalar_one()

    # Return to the pool, then take a connection again.
    async with _unscoped_session() as session:
        reused = (await session.execute(text("SHOW statement_timeout"))).scalar_one()

    assert first == "15s"
    assert after_commit == "15s", "a commit discarded it — this is SET LOCAL, not SET"
    assert reused == "15s", "the setting did not survive returning to the pool"


@requires_db
async def test_application_name_still_arrives(app_db: None) -> None:
    """The control in the experiment that found #15.

    `application_name` is the one setting still sent in `server_settings`, and
    it arrives on Neon. Keeping it asserted here is what distinguishes "the
    startup packet is filtered" from "the connection is misconfigured" if this
    ever regresses — and it is why the fix targeted three settings rather than
    four.
    """
    async with _unscoped_session() as session:
        value = (await session.execute(text("SHOW application_name"))).scalar_one()

    assert value == "nexus-api"


@requires_db
async def test_a_statement_that_overruns_is_cancelled(app_db: None) -> None:
    """The timeout does something, proved without waiting fifteen seconds.

    `SET LOCAL` narrows it for this transaction only. What is being tested is
    that `statement_timeout` is live on the connection at all — a session where
    it is disabled would sleep happily past any local value.
    """
    from sqlalchemy.exc import DBAPIError

    async with _unscoped_session() as session:
        await session.execute(text("SET LOCAL statement_timeout = '100ms'"))
        with pytest.raises(DBAPIError) as raised:
            await session.execute(text("SELECT pg_sleep(2)"))

    assert "canceling statement" in str(raised.value).lower()


# ── The pooler decision is configuration, not a substring ─────


def test_the_transaction_pooler_is_an_explicit_setting() -> None:
    """It was `if "-pooler" in url`.

    That is a guess about a hostname. It is true of Neon's pooled endpoint and
    of nothing else — PgBouncer in front of RDS, a Cloud SQL proxy, or Neon
    renaming the endpoint all leave it silently false, and the failure it
    prevents is `prepared statement ... does not exist` appearing only under
    concurrency, which is the hardest possible way to find out.
    """
    assert "db_transaction_pooler" in Settings.model_fields
    # `_env_file` is a real pydantic-settings argument that its generated
    # `__init__` signature does not advertise, so `--strict` cannot see it.
    # Kept because dropping it would let a developer's `.env` decide the
    # assertion — which is the opposite of what this test is for.
    settings = Settings(_env_file=None, env=Env.local)  # type: ignore[call-arg]
    assert settings.db_transaction_pooler is False


@pytest.mark.parametrize("pooled", [True, False])
def test_the_pool_shape_follows_the_setting(pooled: bool, monkeypatch: pytest.MonkeyPatch) -> None:
    """A transaction-mode pooler is already pooling, so we must not pool again —
    and we must stop caching prepared statements, which is the documented
    requirement rather than a precaution."""
    monkeypatch.setenv("NEXUS_DATABASE_URL", "postgresql+asyncpg://u:p@example.invalid:5432/nexus")
    monkeypatch.setenv("NEXUS_DB_TRANSACTION_POOLER", "true" if pooled else "false")
    for cache in (get_settings, get_engine, get_sessionmaker):
        cache.cache_clear()
    try:
        engine = get_engine()
        if pooled:
            assert isinstance(engine.pool, NullPool)
        else:
            assert not isinstance(engine.pool, NullPool)
    finally:
        for cache in (get_settings, get_engine, get_sessionmaker):
            cache.cache_clear()


def test_a_pooler_hostname_alone_no_longer_changes_behaviour(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The regression guard for the substring match returning.

    A URL naming a `-pooler` host with the setting off must pool normally. If
    someone reinstates the convenience, this fails.
    """
    monkeypatch.setenv(
        "NEXUS_DATABASE_URL", "postgresql+asyncpg://u:p@ep-x-pooler.example.invalid:5432/nexus"
    )
    monkeypatch.setenv("NEXUS_DB_TRANSACTION_POOLER", "false")
    for cache in (get_settings, get_engine, get_sessionmaker):
        cache.cache_clear()
    try:
        assert not isinstance(get_engine().pool, NullPool)
    finally:
        for cache in (get_settings, get_engine, get_sessionmaker):
            cache.cache_clear()


def test_the_idle_timeout_outlasts_the_slowest_model_call() -> None:
    """The idle-in-transaction limit must exceed the work done inside one.

    Not a style rule — this is a defect that already happened. `scoped_connection`
    wraps a whole handler in one transaction, and onboarding's handlers then wait
    tens of seconds on a model with that transaction sitting idle. At the old
    30s, a `/read` that spent 27.7s in `company-research` and 8.0s in
    `company-summary` had its connection closed by Postgres before it could write:
    `InterfaceError: connection is closed`, a 500, and two model calls paid for
    and thrown away.

    Asserted against the *skills' own* declared timeouts rather than a number
    typed twice, so raising a skill's `timeout_seconds` past the database's
    patience fails here instead of in production. The real fix is to stop holding
    a transaction across a provider call at all; until then this is the coupling,
    and it is better written down than remembered.
    """
    from app.ai.runtime.skills import SkillRegistry
    from app.config import get_settings

    idle = get_settings().db_idle_in_transaction_timeout
    assert idle.endswith("s"), f"expected a seconds value, got {idle!r}"
    idle_seconds = float(idle.removesuffix("s"))

    registry = SkillRegistry().load()
    slowest = max(
        (registry.get(name).timeout_seconds or 0) for name in registry.names()
    )
    assert slowest > 0, "no skill declares a timeout; this test would prove nothing"
    assert idle_seconds > slowest, (
        f"idle_in_transaction_session_timeout is {idle_seconds}s but a skill may "
        f"run for {slowest}s inside the transaction. A handler that waits longer "
        f"than the database will tolerate loses its connection mid-request."
    )


# ── The pool (findings B1/B5) ─────────────────────────────────
#
# These four were hardcoded, and the cost of every one of them is a function of
# how far away the database is — which is the one thing the code cannot know.
# Measured against the Neon instance in `.env` (us-east-2, from a laptop): a
# cold connect is 7,148ms, a warm statement 529ms, and one argon2 hash 19ms.
# That last number is why these tests exist in this file rather than in an auth
# one: the breaking-point report attributed login latency under load to argon2
# serialising on CPU, and a hash is 1/370th of a connection. It was the pool.


def _engine_with(monkeypatch: pytest.MonkeyPatch, **env: str) -> object:
    """Build an engine under an environment, without connecting to anything.

    `example.invalid` is unresolvable on purpose. Engine construction is lazy,
    so every assertion below reads configuration rather than reaching a server
    — which is what keeps these runnable with no database.
    """
    monkeypatch.setenv("NEXUS_DATABASE_URL", "postgresql+asyncpg://u:p@example.invalid:5432/nexus")
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    for cache in (get_settings, get_engine, get_sessionmaker):
        cache.cache_clear()
    return get_engine().pool


def test_the_pool_dimensions_follow_the_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tunable, because the right values depend on the round trip to the database."""
    try:
        pool = _engine_with(
            monkeypatch,
            NEXUS_DB_POOL_SIZE="7",
            NEXUS_DB_POOL_MAX_OVERFLOW="3",
            NEXUS_DB_POOL_RECYCLE_SECONDS="90",
        )
        assert pool.size() == 7
        assert pool._max_overflow == 3
        assert pool._recycle == 90
    finally:
        for cache in (get_settings, get_engine, get_sessionmaker):
            cache.cache_clear()


def test_pre_ping_can_be_turned_off_but_defaults_on(monkeypatch: pytest.MonkeyPatch) -> None:
    """**The single most expensive line in the request path on a remote database.**

    A ping per checkout is a round trip per request: measured at ~1.27s against
    us-east-2 (2,249ms with it, 977ms without, for checkout plus one
    statement), and about 2ms against a database in the same region. So it is a
    deployment decision rather than a constant.

    Defaulting *on* is the assertion that matters. The safe default has to be
    the one that survives a provider closing a connection underneath us; the
    fast default is opt-in, because a wrong choice there fails as an
    intermittent 500 rather than as slowness somebody can see.
    """
    try:
        assert _engine_with(monkeypatch)._pre_ping is True
        assert _engine_with(monkeypatch, NEXUS_DB_POOL_PRE_PING="false")._pre_ping is False
    finally:
        for cache in (get_settings, get_engine, get_sessionmaker):
            cache.cache_clear()


def test_a_transaction_pooler_is_never_pre_pinged(monkeypatch: pytest.MonkeyPatch) -> None:
    """`NullPool` opens a fresh connection per checkout, so a ping is known-waste.

    Asking "is this brand-new connection alive" costs a round trip to learn
    something the previous line established — on the deployment shape where
    round trips are already the problem.
    """
    try:
        pool = _engine_with(
            monkeypatch, NEXUS_DB_TRANSACTION_POOLER="true", NEXUS_DB_POOL_PRE_PING="true"
        )
        assert isinstance(pool, NullPool)
        assert pool._pre_ping is False, "a pooler connection was pinged for nothing"
    finally:
        for cache in (get_settings, get_engine, get_sessionmaker):
            cache.cache_clear()


def test_the_recycle_stays_inside_a_provider_idle_timeout() -> None:
    """It was 300s, which is *on* the boundary rather than inside it.

    Recycling is the free half of staying ahead of a dead connection — an age
    check in the pool, no round trip — and it only helps if it fires before the
    provider gives up. A value equal to the timeout it is racing is as likely
    to run after as before.
    """
    settings = Settings(_env_file=None, env=Env.local)  # type: ignore[call-arg]
    assert settings.db_pool_recycle_seconds < 300


async def test_warming_is_skipped_when_there_is_nothing_to_warm(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No database, and a pooler, are both "no pool to fill" — not a failure.

    The application is required to run with no database at all (tests, tooling,
    `/health` reporting that it is down), so this cannot be a startup
    precondition. And under a transaction pooler `NullPool` keeps nothing
    between checkouts, so connections opened here would close again immediately
    and the first request would still pay full price.
    """
    from app.db import warm_pool

    monkeypatch.setenv("NEXUS_DATABASE_URL", "")
    for cache in (get_settings, get_engine, get_sessionmaker):
        cache.cache_clear()
    try:
        assert await warm_pool() == 0

        monkeypatch.setenv(
            "NEXUS_DATABASE_URL", "postgresql+asyncpg://u:p@example.invalid:5432/nexus"
        )
        monkeypatch.setenv("NEXUS_DB_TRANSACTION_POOLER", "true")
        for cache in (get_settings, get_engine, get_sessionmaker):
            cache.cache_clear()
        assert await warm_pool() == 0
    finally:
        for cache in (get_settings, get_engine, get_sessionmaker):
            cache.cache_clear()


async def test_warming_never_raises_when_the_database_is_unreachable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A container that refuses to boot reports nothing at all.

    `/health` exists to say the database is down, which it can only do if the
    process started. So warming logs its failure and returns a count — it is an
    optimisation, and an optimisation that can prevent startup is a liability.
    """
    from app.db import warm_pool

    monkeypatch.setenv("NEXUS_DATABASE_URL", "postgresql+asyncpg://u:p@example.invalid:5432/nexus")
    monkeypatch.setenv("NEXUS_DB_TRANSACTION_POOLER", "false")
    monkeypatch.setenv("NEXUS_DB_POOL_SIZE", "2")
    for cache in (get_settings, get_engine, get_sessionmaker):
        cache.cache_clear()
    try:
        assert await warm_pool() == 0, "an unreachable host must warm nothing and raise nothing"
    finally:
        for cache in (get_settings, get_engine, get_sessionmaker):
            cache.cache_clear()
