"""Rate limiting the research path.

Doc 06 §1.2: *"Metered APIs must never sit on an unauthenticated path... Without
this, a script exhausts a paid quota and degrades the product for paying
tenants."*

Until Phase 2 that unauthenticated path existed, and the limits were shaped
around it: **per IP**, to stop one client hammering the endpoint; **per domain**,
to stop many clients being pointed at one victim; and a **global daily ceiling**
to bound the bill. `doc/11` Q1 retired the anonymous audit, and both of the first
two lost their subject with it. There is no address to attribute a crawl to when
every caller is authenticated, and no reflected-DoS shape to block when the
target has to be a domain the workspace has claimed.

What replaces them is the identity that now exists on every call:

- **per workspace** — the tenant fairness limit. One customer running research in
  a loop must not consume the day's budget that the others are paying for.
- **global daily ceiling** — the actual cost containment, unchanged. The first
  limit bounds any single tenant; only this one bounds the bill.

Counters are fixed-window and live in Postgres (ADR 0001 — no Redis). A fixed
window permits up to 2x the limit across a boundary; that is an accepted
trade-off for a ceiling whose purpose is bounding spend rather than precision.

The re-keying needed no migration. A bucket is an opaque string, so the old
`ip:` and `domain:` rows are simply never written again and age out through
`purge_expired`.
"""

from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True, slots=True)
class Limit:
    bucket_prefix: str
    max_count: int
    window: timedelta


# Two constraints set these numbers, and neither is "how much crawling feels
# reasonable":
#
# - **Only the global ceiling bounds the bill.** Loosening the per-workspace
#   limit does not raise the maximum spend, because `GLOBAL_DAILY` still caps
#   the crawls per day across every tenant. That is the limit to keep tight.
# - **The per-workspace limit is about fairness, not cost.** It exists so one
#   customer looping on research cannot spend the ceiling the others are paying
#   for. Set too tight it rejects ordinary use, which is the failure that costs
#   a customer rather than money.
#
# `PER_WORKSPACE` is deliberately generous against `GLOBAL_DAILY`: a single
# tenant can take a tenth of the day's budget before being told to wait, and
# ten busy tenants can coexist without any of them noticing a limit exists.
#
# **P11 owns the real number.** It builds the research job model and will know
# what one run actually costs; until then this bounds a path with no callers,
# and a limit nobody has measured should not pretend otherwise.
PER_WORKSPACE = Limit("workspace", max_count=50, window=timedelta(hours=24))
GLOBAL_DAILY = Limit("global", max_count=500, window=timedelta(days=1))

# The third bucket this section's docstring promised and never wrote (L-04):
# the reflected-DoS shape `PER_WORKSPACE` does not stop. Many workspaces
# researching the same target — a competitor everyone in one industry is
# watching — stay under their own per-workspace allowance while that one
# domain absorbs a crawl from each of them. Same shape as `SCAN_PER_DOMAIN`
# below, for the identical reason.
CRAWL_PER_DOMAIN = Limit("crawl_domain", max_count=10, window=timedelta(hours=24))

# ── Credential endpoints (D14, P4) ────────────────────────────
#
# Two counters, because either alone is defeated by the obvious move: per-IP
# falls to a botnet, per-email falls to rotating the target. Both, and an
# attacker has to spread across addresses *and* sources to stay under.
#
# **These do not gate the request.** Exceeding them costs a delay, applied
# before an identical 401 — never a 429, never a lock. `app/routes/auth.py`
# explains why at the call site, and `tests/test_login_rate_limit.py` is what
# holds it to it. The numbers are the point at which a human stops looking like
# a human: nobody types their own password wrong ten times in an hour, and
# nobody registers five accounts from one address in one.
LOGIN_PER_IP = Limit("login_ip", max_count=10, window=timedelta(hours=1))
LOGIN_PER_EMAIL = Limit("login_email", max_count=10, window=timedelta(hours=1))
REGISTER_PER_IP = Limit("register_ip", max_count=5, window=timedelta(hours=1))

# `/auth/password-reset/request` and `/confirm` were unmetered — the one gap in
# an otherwise-covered set of credential endpoints, and the cheapest one to
# query: a request costs no password hash, unlike login and register. Same
# shape as the pair above, same reason for the pair: per-IP falls to a
# botnet, per-email falls to rotating the target address.
RESET_PER_IP = Limit("reset_ip", max_count=10, window=timedelta(hours=1))
RESET_PER_EMAIL = Limit("reset_email", max_count=5, window=timedelta(hours=1))

# ── Domain verification checks (finding #4) ───────────────────
#
# `/domains/{id}/check` performs a **server-side fetch against a host the caller
# named** — a DNS TXT lookup, or an HTTPS GET of a well-known path. It is the
# only unmetered outbound fetch left in the product, and it became the only one
# when P2 deleted the preview's `PER_DOMAIN` bucket, which finding #4 had cited
# as its mitigation.
#
# Two counters, because the two abuses are different:
#
# - **per user** — bounds one account looping the button, which is also the
#   accidental case: a founder waiting for DNS to propagate clicks Check every
#   few seconds, and that should cost them nothing worse than a wait.
# - **per domain** — the reflected-DoS shape. Many accounts pointed at one
#   victim stay under any per-user limit while the target is hammered by
#   requests it did not ask for and cannot attribute to whoever chose it.
#
# Generous, because a real claimant is genuinely uncertain when their record
# will appear and re-checking is the correct thing for them to do. These stop a
# script, not a person.
CHECK_PER_USER = Limit("domaincheck_user", max_count=30, window=timedelta(hours=1))
CHECK_PER_DOMAIN = Limit("domaincheck_domain", max_count=60, window=timedelta(hours=24))

# ── Company registration (L-04) ────────────────────────────────
#
# `POST /companies` creates a tenant, a workspace and a queued `research_run`
# in one call — the research run is what eventually spends `PER_WORKSPACE`,
# `GLOBAL_DAILY` and `CRAWL_PER_DOMAIN` above, but nothing bounded how many of
# them one signed-in account could queue by calling this endpoint on a loop.
# Generous: registering a second or third genuine company (an agency, a
# holding structure) is a real case doc 06 §1.1 already accommodates via
# `confirm_separate_company`, and this exists to stop a script, not a founder.
COMPANY_REGISTER_PER_USER = Limit("company_register_user", max_count=10, window=timedelta(days=1))

# ── The anonymous scanner (ADR 0046, `doc/18` G6) ──────────────
#
# `app/scan/` is the one anonymous surface permitted a server-side fetch, and
# these are the three buckets that bound it — the same shape the retired
# preview audit used (`app/routes/preview.py`, deleted at `dc287dd`), because
# each still stops a different abuse and neither the shape nor the numbers
# were wrong the first time:
#
# - **per IP** — one client hammering the endpoint.
# - **per domain** — the reflected-DoS shape a per-IP limit does not stop,
#   since each attacker address stays under its own allowance while the
#   target absorbs requests from all of them combined.
# - **global daily** — the ceiling. The only one that bounds the total load
#   this scanner generates against the wider internet, whatever the other two
#   allow.
#
# Values carried over unchanged from the retired preview audit — a scan reads
# one page rather than up to twenty, so if anything these are generous, and a
# number nobody has re-measured for the new shape should not pretend to be
# freshly tuned.
SCAN_PER_IP = Limit("scan_ip", max_count=20, window=timedelta(hours=1))
SCAN_PER_DOMAIN = Limit("scan_domain", max_count=5, window=timedelta(hours=24))
SCAN_GLOBAL_DAILY = Limit("scan_global", max_count=500, window=timedelta(days=1))

# Doubling from a quarter of a second, capped. The cap matters: an uncapped
# curve turns the twentieth attempt into a request that holds a worker for
# minutes, so the backoff becomes a way to exhaust the server it protects.
BACKOFF_BASE_SECONDS = 0.25
BACKOFF_MAX_SECONDS = 8.0


def hash_bucket_key(value: str, *, secret: str) -> str:
    """Keyed hash of whatever identifies the caller.

    Written for the retired per-IP Preview bucket and kept for the same reason
    it existed: without it, `rate_limit_counter` becomes a plaintext list of
    every address anyone has tried to sign in as — readable by anything that can
    read the table, and retained for the life of the window. Counting somebody
    does not require naming them.

    Keyed rather than a plain digest, so the table is not a rainbow-table lookup
    of a namespace as small and guessable as email addresses.
    """
    return hmac.new(secret.encode(), value.strip().lower().encode(), hashlib.sha256).hexdigest()


def backoff_seconds(
    attempts: int,
    *,
    base: float = BACKOFF_BASE_SECONDS,
    cap: float = BACKOFF_MAX_SECONDS,
) -> float:
    """How long to stall before answering, given the attempts so far.

    Zero while under the limit, then doubling to a cap. Returned rather than
    slept here so the caller decides *when* to spend it — which for the login
    path is after the work, not before, so the delay cannot be measured
    separately from the response.
    """
    if attempts <= 0:
        return 0.0
    return float(min(base * (2 ** (attempts - 1)), cap))


class RateLimitedError(Exception):
    def __init__(self, scope: str, retry_after_seconds: int) -> None:
        super().__init__(f"rate limited: {scope}")
        self.scope = scope
        self.retry_after_seconds = retry_after_seconds


def _window_start(now: datetime, window: timedelta) -> datetime:
    seconds = int(window.total_seconds())
    epoch = int(now.timestamp())
    return datetime.fromtimestamp(epoch - (epoch % seconds), tz=UTC)


async def consume(db: AsyncSession, limit: Limit, key: str, *, now: datetime | None = None) -> int:
    """Count one attempt and report how far **over** the limit it is.

    The counting sibling of `check_and_increment`, for the credential path,
    which must never refuse — D14 requires an identical 401 whatever the
    counters say, so a function that raises would be the wrong shape and the
    temptation to let the exception reach the client would be permanent.

    Returns 0 while under the limit; 1 for the first attempt over, 2 for the
    second, and so on. That number is the exponent the backoff curve uses.
    """
    moment = now or datetime.now(UTC)
    start = _window_start(moment, limit.window)

    result = await db.execute(
        text(
            """
            INSERT INTO rate_limit_counter (bucket, window_start, count)
            VALUES (:bucket, :start, 1)
            ON CONFLICT (bucket, window_start)
            DO UPDATE SET count = rate_limit_counter.count + 1
            RETURNING count
            """
        ),
        {"bucket": f"{limit.bucket_prefix}:{key}", "start": start},
    )
    return max(0, int(result.scalar_one()) - limit.max_count)


async def check_and_increment(
    db: AsyncSession, limit: Limit, key: str, *, now: datetime | None = None
) -> None:
    """Consume one unit against a bucket, or raise `RateLimited`.

    The upsert increments and returns the new count in a single statement, so
    two concurrent requests cannot both read a count below the limit and both
    proceed.
    """
    moment = now or datetime.now(UTC)
    start = _window_start(moment, limit.window)
    bucket = f"{limit.bucket_prefix}:{key}"

    result = await db.execute(
        text(
            """
            INSERT INTO rate_limit_counter (bucket, window_start, count)
            VALUES (:bucket, :start, 1)
            ON CONFLICT (bucket, window_start)
            DO UPDATE SET count = rate_limit_counter.count + 1
            RETURNING count
            """
        ),
        {"bucket": bucket, "start": start},
    )
    count = int(result.scalar_one())

    if count > limit.max_count:
        elapsed = (moment - start).total_seconds()
        retry_after = max(1, int(limit.window.total_seconds() - elapsed))
        raise RateLimitedError(limit.bucket_prefix, retry_after)


async def purge_expired(db: AsyncSession, *, older_than: datetime | None = None) -> int:
    """Drop counter rows for windows that can no longer be current."""
    cutoff = older_than or (datetime.now(UTC) - timedelta(days=2))
    result = await db.execute(
        text(
            "WITH deleted AS ("
            "  DELETE FROM rate_limit_counter WHERE window_start < :cutoff RETURNING 1"
            ") SELECT count(*) FROM deleted"
        ),
        {"cutoff": cutoff},
    )
    return int(result.scalar_one())
