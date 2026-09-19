"""The anonymous scanner's three rate-limit buckets. G6, ADR 0046.

Runs against the real database, the same reasoning `test_rate_limit.py`
states: the limit is enforced by an atomic upsert, and an in-memory fake
would test the fake rather than the guarantee.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from uuid import uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy import Connection, Engine, create_engine, text

from app.config import get_settings
from app.connectors.rate_limit import (
    SCAN_GLOBAL_DAILY,
    SCAN_PER_DOMAIN,
    SCAN_PER_IP,
    Limit,
    RateLimitedError,
    check_and_increment,
    hash_bucket_key,
)
from app.db import _unscoped_session, get_engine, get_sessionmaker
from tests.dburl import async_database_url, database_url

DB_URL = database_url()
ASYNC_DB_URL = async_database_url()
requires_db = pytest.mark.requires_db

SECRET = "test-secret-does-not-matter-here"


@pytest.fixture(scope="module")
def engine() -> Iterator[Engine]:
    assert DB_URL is not None
    eng = create_engine(DB_URL, poolclass=sa.pool.NullPool)
    yield eng
    eng.dispose()


@pytest.fixture
def conn(engine: Engine) -> Iterator[Connection]:
    connection = engine.connect()
    trans = connection.begin()
    try:
        yield connection
    finally:
        trans.rollback()
        connection.close()


@pytest.fixture
async def app_db(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[None]:
    """The async side, wired the way `test_company_registration.py`'s
    `app_db` fixture is — `conftest.py` pins `NEXUS_DATABASE_URL` empty for
    hermeticity, so a test that needs `_unscoped_session`/`check_and_increment`
    for real has to set it and clear the `lru_cache`d factories that read it
    at import time."""
    assert ASYNC_DB_URL is not None
    monkeypatch.setenv("NEXUS_DATABASE_URL", ASYNC_DB_URL)
    monkeypatch.setenv("NEXUS_STORAGE_SIGNING_SECRET", "test-secret")
    for cache in (get_settings, get_engine, get_sessionmaker):
        cache.cache_clear()
    yield
    await get_engine().dispose()
    for cache in (get_settings, get_engine, get_sessionmaker):
        cache.cache_clear()


def consume(conn: Connection, limit: Limit, key: str) -> int:
    """Synchronous mirror of `check_and_increment`'s upsert, for setup steps
    that need to reach the limit without yet asserting the refusal."""
    result = conn.execute(
        text(
            """
            INSERT INTO rate_limit_counter (bucket, window_start, count)
            VALUES (:bucket, date_trunc('hour', now()), 1)
            ON CONFLICT (bucket, window_start)
            DO UPDATE SET count = rate_limit_counter.count + 1
            RETURNING count
            """
        ),
        {"bucket": f"{limit.bucket_prefix}:{key}"},
    )
    return int(result.scalar_one())


@requires_db
async def test_the_nplus1th_scan_request_is_refused_with_retry_after(app_db: None) -> None:
    """The one behaviour `test_rate_limit.py`'s buckets never need: this path
    gates the request. `check_and_increment` — not the counting-only
    `consume` login uses — is what a 429 comes from."""
    key = hash_bucket_key(str(uuid4()), secret=SECRET)
    async with _unscoped_session() as db:
        for _ in range(SCAN_PER_IP.max_count):
            await check_and_increment(db, SCAN_PER_IP, key)
            await db.commit()

        with pytest.raises(RateLimitedError) as exc:
            await check_and_increment(db, SCAN_PER_IP, key)

    assert exc.value.retry_after_seconds > 0
    assert exc.value.scope == SCAN_PER_IP.bucket_prefix


@requires_db
def test_per_domain_refuses_a_second_caller_from_a_different_address(conn: Connection) -> None:
    """The reflected-DoS shape this bucket exists to stop: two different
    addresses, pointed at the same domain, must not each get their own
    per-domain allowance — the domain is the key, not the caller."""
    domain = f"victim-{uuid4()}.example"
    for _ in range(SCAN_PER_DOMAIN.max_count):
        # Attacker A, many requests.
        consume(conn, SCAN_PER_DOMAIN, domain)

    # Attacker B, a different address, same domain — must land in the same
    # bucket and see it already exhausted.
    count = consume(conn, SCAN_PER_DOMAIN, domain)
    assert count > SCAN_PER_DOMAIN.max_count


@requires_db
def test_rate_limit_counter_holds_no_plaintext_address(conn: Connection) -> None:
    """Asserted against the table, not the code — the same distinction
    `hash_bucket_key`'s own docstring draws: counting somebody does not
    require naming them."""
    real_ip = "203.0.113.77"
    key = hash_bucket_key(real_ip, secret=SECRET)
    consume(conn, SCAN_PER_IP, key)

    rows = conn.execute(
        text("SELECT bucket FROM rate_limit_counter WHERE bucket LIKE :prefix"),
        {"prefix": f"{SCAN_PER_IP.bucket_prefix}:%"},
    ).all()
    assert rows, "the test's own insert should have produced a row"
    assert all(real_ip not in row.bucket for row in rows)


def test_scan_buckets_are_named_for_the_abuse_they_stop() -> None:
    assert SCAN_PER_IP.bucket_prefix == "scan_ip"
    assert SCAN_PER_DOMAIN.bucket_prefix == "scan_domain"
    assert SCAN_GLOBAL_DAILY.bucket_prefix == "scan_global"


def test_the_global_ceiling_sits_above_the_per_key_allowances() -> None:
    """Only the global ceiling bounds the total load this scanner generates —
    a ceiling either per-key limit could reach alone is a per-key limit
    wearing the wrong name."""
    assert SCAN_GLOBAL_DAILY.max_count > SCAN_PER_IP.max_count
    assert SCAN_GLOBAL_DAILY.max_count > SCAN_PER_DOMAIN.max_count
