"""Expiring what is time-bound.

Until Phase 2 this module's centre of gravity was Preview data, and the reason
was unusual enough to be worth remembering: **the subject of that data was not
our user.** A company whose site had been crawled by a stranger evaluating them
had no login here, could not see what we held, and could not ask an account
manager to remove it. Doc 06 §10 answered that with a short TTL and a
deletion-request path keyed on the domain rather than on an account, and this
job is what carried it out.

`doc/11` Q1 retired the unauthenticated crawl, so no third-party data is
collected and the obligation does not arise — **D9 is void rather than
satisfied**, for the *authenticated* research crawl this module originally
governed.

**ADR 0046/0048 reopen a narrow version of it.** `public_scan` is exactly
the shape D9 described — third-party data, no account to attach it to — and
`expire_public_scans` is this job's replacement for `expire_previews`,
scoped to the one table that needs it. Without this sweep,
`store.get_fresh`'s read query keeps returning nothing (correctly filtering
on `expires_at > now()`) while the table grows without bound — a silent
failure in the direction that looks fine, the same shape `AUDIT-FINDINGS.md`
already recorded once for the original sweep.

What remains from before Phase 2: abandoned domain claims, and rate-limit
counters for windows that have closed.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.logging import get_logger

log = get_logger(__name__)

PUBLIC_SCAN_DELETE_GRACE = timedelta(days=1)
"""How long a soft-deleted `public_scan` row survives before this sweep hard-
deletes it. Short — the visitor asked for it to be gone — but not zero, so a
delete recorded a moment before the sweep runs is not lost to a race with no
transaction spanning both."""


@dataclass(frozen=True, slots=True)
class ExpiryReport:
    rate_limit_rows_deleted: int
    claims_expired: int
    public_scans_expired: int


async def expire_stale_claims(db: AsyncSession, *, now: datetime | None = None) -> int:
    """Close out domain claims nobody completed.

    Marked expired rather than deleted: the attempt is part of the audit trail
    for a contested domain, and deleting it would erase who tried.
    """
    moment = now or datetime.now(UTC)
    result = await db.execute(
        text(
            "WITH stale AS ("
            "  UPDATE domain_claim SET state = 'expired'"
            "   WHERE state = 'pending' AND expires_at <= :now"
            "  RETURNING 1"
            ") SELECT count(*) FROM stale"
        ),
        {"now": moment},
    )
    return int(result.scalar_one())


async def expire_public_scans(db: AsyncSession, *, now: datetime | None = None) -> int:
    """Hard-delete `public_scan` rows that have run their course.

    Two conditions, because there are two ways a row is done: its TTL passed
    (`expires_at`, ADR 0048's seven days), or a visitor deleted it themselves
    and the grace period since has passed. No RLS on this table (ADR 0048
    rule — it has no `workspace_id` to scope by), so this runs on `db`, the
    same unscoped session `purge_expired` uses for `rate_limit_counter`, not
    `jobs_db`.
    """
    moment = now or datetime.now(UTC)
    result = await db.execute(
        text(
            "WITH gone AS ("
            "  DELETE FROM public_scan"
            "   WHERE expires_at <= :now"
            "      OR (deleted_at IS NOT NULL AND deleted_at <= :grace_cutoff)"
            "  RETURNING 1"
            ") SELECT count(*) FROM gone"
        ),
        {"now": moment, "grace_cutoff": moment - PUBLIC_SCAN_DELETE_GRACE},
    )
    return int(result.scalar_one())


async def run_expiry_sweep(
    db: AsyncSession, jobs_db: AsyncSession, *, now: datetime | None = None
) -> ExpiryReport:
    """One pass of everything time-bound. Safe to run repeatedly.

    **Two sessions, and they are different roles** (ADR 0018). The split is not
    tidiness:

    - `expire_stale_claims` spans every user's claims. Since migration 0013,
      `domain_claim` carries a `user_id` policy, so the application role sees
      none of them — the statement would match zero rows and this function would
      report a clean sweep for ever. It runs as `nexus_jobs`, which holds the
      one role-targeted policy that permits it.
    - `purge_expired` clears `rate_limit_counter`, and `expire_public_scans`
      clears `public_scan` — neither has RLS and `nexus_jobs` is deliberately
      **not** granted either. Both run on `db`, the same unscoped session,
      and both access is one table wide and stays that way.

    Passed in rather than opened here so a test can drive the real function
    against real sessions instead of a copy of its SQL.
    """
    from app.connectors.rate_limit import purge_expired

    claims = await expire_stale_claims(jobs_db, now=now)
    await jobs_db.commit()

    counters = await purge_expired(db)
    scans = await expire_public_scans(db, now=now)
    await db.commit()

    report = ExpiryReport(counters, claims, scans)
    if claims or counters or scans:
        log.info(
            "expiry.sweep",
            claims_expired=claims,
            rate_limit_rows_deleted=counters,
            public_scans_expired=scans,
        )
    return report
