"""Abandoned domain claims expire — and, since ADR 0046/0048, so does a
narrower third-party retention than the one this file used to describe.

This file was mostly about Preview data, and doc 07 M3's acceptance was
`"no workspace exists without a verified domain, **and Preview data expires**"`.
That clause described `preview_session` (migration 0011, dropped at `doc/11`
Q1), and D9-as-that-obligation stayed void from P2 until G11: `public_scan`
is the new third-party data this project holds, and `expire_public_scans`
below is this job's replacement, scoped to that one table.

What is left from before: a claim someone started and never finished, which
is **marked expired rather than deleted** — the opposite of the rule the
scan tests below enforce, and for the opposite reason: this data is about
our own user, and for a contested domain, who tried to claim it is exactly
what a support conversation needs.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy import Connection, Engine, create_engine, text

from tests.dburl import database_url

DB_URL = database_url()
# The real marker, declared in pyproject.toml. Previously a local
# `pytest.mark.skipif` — nine copies of it, so nine places a database suite
# could silently vanish from a green run. The skip decision now lives in
# conftest.py, which fails the session if it ever fires.
requires_db = pytest.mark.requires_db


@pytest.fixture(scope="module")
def engine() -> Iterator[Engine]:
    # `requires_db` guarantees a database, so a missing URL here is a broken
    # harness rather than an absent one. Assert loudly instead of skipping —
    # a skip is what tests/test_ci_contract.py exists to make impossible.
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


# ── Stale claims ──────────────────────────────────────────────


@requires_db
def test_stale_pending_claims_are_expired_not_deleted(conn: Connection) -> None:
    """The attempt stays in the audit trail: for a contested domain, who tried
    is exactly what a support conversation needs."""
    uid = uuid4()
    conn.execute(
        text("INSERT INTO app_user (id, email) VALUES (:i,:e)"),
        {"i": str(uid), "e": f"u-{uid}@example.com"},
    )
    cid = uuid4()
    # `domain_claim` is row-level secured on `user_id` since migration 0013, so
    # an insert with no `nexus.user_id` fails the WITH CHECK.
    conn.execute(text("SELECT set_config('nexus.user_id', :u, true)"), {"u": str(uid)})
    conn.execute(
        text(
            "INSERT INTO domain_claim"
            " (id, domain, user_id, method, strength, challenge_token, state, expires_at)"
            " VALUES (:i,:d,:u,'dns_txt','strong','tok','pending', now() - interval '1 day')"
        ),
        {"i": str(cid), "d": f"stale-{uuid4().hex[:8]}.om", "u": str(uid)},
    )

    conn.execute(
        text(
            "UPDATE domain_claim SET state = 'expired'"
            " WHERE state = 'pending' AND expires_at <= now()"
        )
    )

    state = conn.execute(
        text("SELECT state FROM domain_claim WHERE id = :i"), {"i": str(cid)}
    ).scalar()
    assert state == "expired"


@requires_db
def test_a_verified_claim_is_not_expired_by_the_sweep(conn: Connection) -> None:
    uid = uuid4()
    conn.execute(
        text("INSERT INTO app_user (id, email) VALUES (:i,:e)"),
        {"i": str(uid), "e": f"u-{uid}@example.com"},
    )
    cid = uuid4()
    # `domain_claim` is row-level secured on `user_id` since migration 0013, so
    # an insert with no `nexus.user_id` fails the WITH CHECK.
    conn.execute(text("SELECT set_config('nexus.user_id', :u, true)"), {"u": str(uid)})
    conn.execute(
        text(
            "INSERT INTO domain_claim"
            " (id, domain, user_id, method, strength, challenge_token, state,"
            "  expires_at, verified_at)"
            " VALUES (:i,:d,:u,'dns_txt','strong','tok','verified',"
            "         now() - interval '1 day', now())"
        ),
        {"i": str(cid), "d": f"done-{uuid4().hex[:8]}.om", "u": str(uid)},
    )

    conn.execute(
        text(
            "UPDATE domain_claim SET state = 'expired'"
            " WHERE state = 'pending' AND expires_at <= now()"
        )
    )

    state = conn.execute(
        text("SELECT state FROM domain_claim WHERE id = :i"), {"i": str(cid)}
    ).scalar()
    assert state == "verified", "a completed verification must not expire with its window"


# ── public_scan (G11, ADR 0046/0048) ────────────────────────────


_INSERT_SCAN_SQL = text(
    "INSERT INTO public_scan"
    " (id, domain, scanned_url, checks, scores, pages_read, js_rendered,"
    "  expires_at, deleted_at)"
    " VALUES (:i, :d, :u, '[]'::jsonb, '[]'::jsonb, 1, false,"
    "         now() + :expires_offset, :deleted_at)"
)


def _insert_scan(
    conn: Connection,
    *,
    expires_offset: timedelta,
    deleted_offset: timedelta | None = None,
) -> str:
    sid = str(uuid4())
    conn.execute(
        _INSERT_SCAN_SQL,
        {
            "i": sid,
            "d": f"expiry-{uuid4().hex[:8]}.example",
            "u": "https://example.example/",
            "expires_offset": expires_offset,
            "deleted_at": None if deleted_offset is None else _now_plus(deleted_offset),
        },
    )
    return sid


def _now_plus(offset: timedelta) -> datetime:
    # Computed in Python, bound as an ordinary parameter — the point of this
    # helper is to avoid ever building SQL text from a per-call value.
    return datetime.now(UTC) + offset


@requires_db
def test_a_scan_past_its_ttl_is_hard_deleted(conn: Connection) -> None:
    sid = _insert_scan(conn, expires_offset=timedelta(hours=-1))

    conn.execute(
        text(
            "DELETE FROM public_scan"
            " WHERE expires_at <= now()"
            "    OR (deleted_at IS NOT NULL AND deleted_at <= now() - interval '1 day')"
        )
    )

    row = conn.execute(text("SELECT 1 FROM public_scan WHERE id = :i"), {"i": sid}).scalar()
    assert row is None


@requires_db
def test_a_live_scan_is_not_touched_by_the_sweep(conn: Connection) -> None:
    sid = _insert_scan(conn, expires_offset=timedelta(days=6))

    conn.execute(
        text(
            "DELETE FROM public_scan"
            " WHERE expires_at <= now()"
            "    OR (deleted_at IS NOT NULL AND deleted_at <= now() - interval '1 day')"
        )
    )

    row = conn.execute(text("SELECT 1 FROM public_scan WHERE id = :i"), {"i": sid}).scalar()
    assert row == 1, "a row still inside its TTL must survive the sweep"


@requires_db
def test_a_soft_deleted_scan_is_hard_deleted_after_its_grace_period(conn: Connection) -> None:
    sid = _insert_scan(
        conn,
        expires_offset=timedelta(days=6),  # TTL not yet reached
        deleted_offset=timedelta(days=-2),  # but past the 1-day grace
    )

    conn.execute(
        text(
            "DELETE FROM public_scan"
            " WHERE expires_at <= now()"
            "    OR (deleted_at IS NOT NULL AND deleted_at <= now() - interval '1 day')"
        )
    )

    row = conn.execute(text("SELECT 1 FROM public_scan WHERE id = :i"), {"i": sid}).scalar()
    assert row is None, "a soft-deleted row must not survive its grace period"


@requires_db
def test_a_recently_soft_deleted_scan_survives_the_grace_period(conn: Connection) -> None:
    sid = _insert_scan(
        conn,
        expires_offset=timedelta(days=6),
        deleted_offset=timedelta(hours=-1),  # well within the 1-day grace
    )

    conn.execute(
        text(
            "DELETE FROM public_scan"
            " WHERE expires_at <= now()"
            "    OR (deleted_at IS NOT NULL AND deleted_at <= now() - interval '1 day')"
        )
    )

    row = conn.execute(text("SELECT 1 FROM public_scan WHERE id = :i"), {"i": sid}).scalar()
    assert row == 1, "a delete recorded moments before the sweep must not be lost to a race"


@requires_db
async def test_expire_public_scans_matches_the_hand_rolled_sql() -> None:
    """The real function, not a second copy of its SQL — the same gap
    `test_rate_limit.py`'s own module docstring names for why it runs
    against a real database rather than trusting the statement by
    inspection."""
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.jobs.expiry import expire_public_scans
    from tests.dburl import async_database_url

    async_url = async_database_url()
    assert async_url is not None
    engine = create_async_engine(async_url, poolclass=sa.pool.NullPool)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_factory() as db:
            domain = f"expiry-fn-{uuid4().hex[:8]}.example"
            await db.execute(
                text(
                    "INSERT INTO public_scan"
                    " (domain, scanned_url, checks, scores, pages_read,"
                    "  js_rendered, expires_at)"
                    " VALUES (:d, :u, '[]'::jsonb, '[]'::jsonb, 1, false,"
                    "         now() - interval '1 hour')"
                ),
                {"d": domain, "u": "https://example.example/"},
            )
            await db.commit()
            deleted = await expire_public_scans(db)
            await db.commit()
            assert deleted >= 1
    finally:
        await engine.dispose()
