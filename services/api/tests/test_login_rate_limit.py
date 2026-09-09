"""Rate limiting the credential endpoints, without becoming an oracle.

D14, answered in `doc/11` §5.2: **per-IP and per-email counters, exponential
backoff rather than a lock, and an identical 401 in every case with the delay
applied silently.**

Every clause of that is load-bearing, and the third is the one this file exists
to defend. The obvious implementation — a `429` with `Retry-After` once an
address has been guessed at too often — is worse than no limit at all for the
property M1 spent its effort on: a `429` keyed by email is a **confirmation that
the address has an account**, available to anyone, for the price of a handful of
requests. It would undo account-enumeration resistance in the act of adding
security.

So the contract asserted below is narrow and absolute: **a caller can tell they
are being slowed down, and cannot tell whose account they are slowing down
against.** The status, the body and the headers are identical for a real address
and an invented one, at every point in the backoff curve.

The lock was rejected for a different reason, recorded in `DECISIONS-REQUIRED.md`
D14: a per-account lock is a denial-of-service vector against a named user.
Anyone who knows an Owner's address could hold them out of their own workspace
during an incident, which is when they need it most.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from uuid import uuid4

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy import Connection, Engine, create_engine

from app.config import get_settings
from app.db import get_engine, get_sessionmaker
from app.main import create_app
from tests.dburl import async_database_url, database_url

PASSWORD = "correct-horse-battery-staple"
WRONG = "not-the-right-password-at-all"
SIGNING_SECRET = "test-signing-secret-not-a-real-one"

DB_URL = database_url()
ASYNC_DB_URL = async_database_url()
requires_db = pytest.mark.requires_db

# Headers that legitimately differ between any two responses. Everything else
# must match, including `Retry-After` if it is ever present — the whole point is
# that a caller learns nothing from comparing two replies.
VARYING_HEADERS = {"date", "x-request-id", "content-length"}


@pytest.fixture(scope="module")
def engine() -> Iterator[Engine]:
    assert DB_URL is not None
    eng = create_engine(DB_URL, poolclass=sa.pool.NullPool)
    yield eng
    eng.dispose()


@pytest.fixture
def conn(engine: Engine) -> Iterator[Connection]:
    connection = engine.connect()
    try:
        yield connection
    finally:
        connection.close()


@pytest.fixture
def api_env(tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> None:
    assert ASYNC_DB_URL is not None
    monkeypatch.setenv("NEXUS_DATABASE_URL", ASYNC_DB_URL)
    monkeypatch.setenv("NEXUS_STORAGE_SIGNING_SECRET", SIGNING_SECRET)
    monkeypatch.setenv("NEXUS_MAIL_ROOT", str(tmp_path_factory.mktemp("mail")))
    # The backoff is real time, and this file spends 40 attempts crossing the
    # limit deliberately. At the shipped curve that is minutes of sleeping to
    # prove a property that has nothing to do with the wall clock — the claim is
    # that two replies are *indistinguishable*, not that either was slow.
    #
    # Not zero: a zero cap would mean the throttle never runs, and these tests
    # would pass over a code path they never execute.
    monkeypatch.setenv("NEXUS_LOGIN_BACKOFF_BASE_SECONDS", "0.001")
    monkeypatch.setenv("NEXUS_LOGIN_BACKOFF_MAX_SECONDS", "0.01")
    for cache in (get_settings, get_engine, get_sessionmaker):
        cache.cache_clear()


@pytest.fixture
def client(api_env: None) -> Iterator[TestClient]:
    with TestClient(create_app()) as c:
        yield c
    for cache in (get_settings, get_engine, get_sessionmaker):
        cache.cache_clear()


@pytest.fixture
async def app_db(api_env: None) -> AsyncIterator[None]:
    yield
    await get_engine().dispose()


def a_fresh_address() -> str:
    return f"p4-{uuid4().hex[:12]}@example.com"


def cleanup(conn: Connection, *emails: str) -> None:
    for email in emails:
        conn.execute(sa.text("DELETE FROM app_user WHERE lower(email) = lower(:e)"), {"e": email})
    conn.execute(sa.text("DELETE FROM rate_limit_counter WHERE bucket LIKE 'login%'"))
    conn.execute(sa.text("DELETE FROM rate_limit_counter WHERE bucket LIKE 'register%'"))
    conn.commit()


def signature(response: object) -> tuple[object, ...]:
    """Everything a caller can observe, minus what legitimately varies."""
    status_code = response.status_code  # type: ignore[attr-defined]
    content = response.content  # type: ignore[attr-defined]
    headers = {
        k.lower(): v
        for k, v in response.headers.items()  # type: ignore[attr-defined]
        if k.lower() not in VARYING_HEADERS
    }
    return (status_code, content, tuple(sorted(headers.items())))


# ── The property the whole design protects ────────────────────


@requires_db
def test_login_rate_limit_preserves_enumeration_resistance(
    client: TestClient, conn: Connection
) -> None:
    """Twenty attempts against a real address and twenty against an invented
    one. Every reply must be indistinguishable, pairwise and in aggregate.

    Pairwise matters as much as the set: if the known address starts returning
    a different shape at attempt six and the unknown one at attempt nine, the
    *point at which they diverge* is itself the oracle.
    """
    known, unknown = a_fresh_address(), a_fresh_address()

    try:
        assert (
            client.post("/auth/register", json={"email": known, "password": PASSWORD}).status_code
            == 201
        )

        known_replies = []
        unknown_replies = []
        for _ in range(20):
            known_replies.append(
                signature(client.post("/auth/login", json={"email": known, "password": WRONG}))
            )
            unknown_replies.append(
                signature(client.post("/auth/login", json={"email": unknown, "password": WRONG}))
            )

        divergent = [
            i for i, (a, b) in enumerate(zip(known_replies, unknown_replies, strict=True)) if a != b
        ]
        assert divergent == [], (
            f"attempts {divergent} differ between a real and an invented address. "
            f"First divergence: known={known_replies[divergent[0]]} "
            f"unknown={unknown_replies[divergent[0]]}"
        )

        # And every reply is a 401 — never a 429, which keyed by email would
        # announce that the address exists.
        assert {r[0] for r in known_replies} == {401}
        assert {r[0] for r in unknown_replies} == {401}
    finally:
        cleanup(conn, known, unknown)


@requires_db
def test_the_limit_actually_bites(client: TestClient, conn: Connection) -> None:
    """The other half. A test that only asserted "indistinguishable" would pass
    against no rate limiting at all — two unlimited endpoints are perfectly
    indistinguishable from each other.

    Asserted on the counters rather than on the wall clock: the backoff is a
    delay, and timing assertions in CI are how a suite becomes flaky.

    **And the first version of that assertion was still time-dependent**, which
    is worth stating because the docstring above claimed it was not. It read
    `max(hits) >= 6` over the matching buckets, and `_window_start` floors a
    bucket to the hour — so six attempts that straddle an hour boundary land in
    two rows and neither one reaches six. It failed once at `13:59:38 → 14:00:23`
    inside an 86-minute run, having passed every run before it.

    `rate_limit` documents the 2x-across-a-boundary behaviour as accepted, so
    the split is the product working as designed. Summing instead of maxing is
    exact here because `a_fresh_address` means the `login_email` rows belong to
    this test and nothing else — `login_ip` accumulates across the module, which
    is why it is only checked for existence.
    """
    email = a_fresh_address()
    try:
        for _ in range(6):
            client.post("/auth/login", json={"email": email, "password": WRONG})

        buckets = conn.execute(
            sa.text(
                "SELECT bucket, count AS hits FROM rate_limit_counter WHERE bucket LIKE 'login%'"
            )
        ).all()
        prefixes = {b.bucket.split(":", 1)[0] for b in buckets}

        assert "login_ip" in prefixes, "no per-IP counter — a botnet is unbounded per address"
        assert "login_email" in prefixes, (
            "no per-email counter — rotating source addresses defeats a per-IP limit alone"
        )
        # `count AS hits`: `Row.count` resolves to `tuple.count`, the method.
        counted = sum(b.hits for b in buckets if b.bucket.startswith("login_email:"))
        assert counted == 6, (
            f"six attempts against a fresh address counted {counted} times. "
            "Summed, not maxed — see the docstring on the hour boundary."
        )
    finally:
        cleanup(conn, email)


@requires_db
def test_the_email_counter_is_keyed_by_a_hash(client: TestClient, conn: Connection) -> None:
    """The counter table would otherwise become a list of every address anyone
    has tried to sign in as — readable by anything that can read the table, and
    retained for the life of the window.

    This is the same reasoning the retired per-IP Preview bucket used, and the
    reason `hash_bucket_key` outlived the IP it was written for.
    """
    email = a_fresh_address()
    try:
        client.post("/auth/login", json={"email": email, "password": WRONG})
        buckets = [
            b.bucket
            for b in conn.execute(
                sa.text("SELECT bucket FROM rate_limit_counter WHERE bucket LIKE 'login_email%'")
            ).all()
        ]
        assert buckets, "no per-email counter was written"
        local_part = email.split("@")[0]
        for bucket in buckets:
            assert email not in bucket
            assert local_part not in bucket
    finally:
        cleanup(conn, email)


@requires_db
def test_a_correct_password_still_works_while_backed_off(
    client: TestClient, conn: Connection
) -> None:
    """Backoff, not a lock — D14's central choice, asserted.

    Someone who fat-fingers their password five times must still get in on the
    sixth attempt. A lock here would mean anyone who knows an Owner's address
    can hold them out of their own workspace at will, which is precisely the
    denial-of-service vector the decision rejected.
    """
    email = a_fresh_address()
    try:
        client.post("/auth/register", json={"email": email, "password": PASSWORD})
        for _ in range(5):
            client.post("/auth/login", json={"email": email, "password": WRONG})

        good = client.post("/auth/login", json={"email": email, "password": PASSWORD})
        assert good.status_code == 200, (
            "the real owner was locked out — this is a lock, not backoff"
        )
    finally:
        cleanup(conn, email)


@requires_db
def test_register_is_bounded_too(client: TestClient, conn: Connection) -> None:
    """`POST /auth/register` is an unbounded `app_user` growth vector, and it is
    the more expensive of the two: every call hashes a password."""
    made = [a_fresh_address() for _ in range(4)]
    try:
        for email in made:
            client.post("/auth/register", json={"email": email, "password": PASSWORD})

        buckets = conn.execute(
            sa.text("SELECT bucket FROM rate_limit_counter WHERE bucket LIKE 'register%'")
        ).all()
        assert buckets, "registration is not metered at all"
    finally:
        cleanup(conn, *made)
