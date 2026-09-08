"""Password hashing.

argon2id, the current OWASP recommendation. Parameters are stored inside the
hash string, so raising them later does not invalidate existing hashes —
`needs_rehash` detects the difference and the next successful login upgrades it.
"""

from __future__ import annotations

import os

from anyio import CapacityLimiter, to_thread
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

# OWASP's second recommended configuration: 19 MiB, 2 iterations, 1 lane.
_hasher = PasswordHasher(
    time_cost=2,
    memory_cost=19456,
    parallelism=1,
    hash_len=32,
    salt_len=16,
)

# Long enough to matter, short enough that argon2's memory cost is not a DoS
# vector. Without an upper bound, a multi-megabyte password is a free CPU burn.
MIN_PASSWORD_LENGTH = 12
MAX_PASSWORD_LENGTH = 1024


class WeakPasswordError(ValueError):
    pass


def validate_password(password: str) -> None:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise WeakPasswordError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters.")
    if len(password) > MAX_PASSWORD_LENGTH:
        raise WeakPasswordError(f"Password must be at most {MAX_PASSWORD_LENGTH} characters.")


def hash_password(password: str) -> str:
    validate_password(password)
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    """Constant-time-ish verification. Never raises on a wrong password."""
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, InvalidHashError):
        return False
    except Exception:
        # A malformed stored hash is a data problem, not an authentication
        # success. Fail closed.
        return False


def needs_rehash(password_hash: str) -> bool:
    try:
        return _hasher.check_needs_rehash(password_hash)
    except InvalidHashError:
        return True


# A hash of a throwaway value, used to spend comparable time when no user
# exists. Without this, "unknown email" returns measurably faster than "wrong
# password" and the login endpoint becomes a user-enumeration oracle.
DUMMY_HASH = _hasher.hash("nexus-timing-equaliser-not-a-real-password")


def spend_dummy_verification() -> None:
    verify_password(DUMMY_HASH, "wrong")


# ── Off the event loop (finding #1, P4) ───────────────────────
#
# argon2id is deliberately expensive: ~40-80 ms of *synchronous* CPU per call,
# by design, because that is what defeats offline cracking. Called directly from
# an `async def` it holds the only thread the event loop has, so thirty login
# attempts a second against a non-existent account stall **every** endpoint —
# dashboards, uploads, and `/health`, which is how a load balancer decides the
# process is dead. The attacker does not need a valid account: the dummy-hash
# equaliser above means a guess at an unknown address costs exactly as much.
#
# It compounds with the rate limit rather than being fixed by it, which is why
# `doc/12` §Phase 4 pairs them: backoff makes each attacker slower, and moving
# the work off the loop is what stops the attempts they do make from taking the
# service down with them.


# ── And bounded, not merely off the loop (finding B1) ─────────
#
# Moving the work to a thread stopped it blocking the event loop. It did not
# bound how *much* of it can run at once, and a breaking-point test found the
# difference: twenty concurrent logins against non-existent addresses drove
# per-request latency to 47.8s, past the web proxy's 30s abort, so real users
# saw 503s. The rate limit does not prevent it — by D14 the login path never
# refuses and never locks, it spends a backoff **after** answering, so the first
# burst of a flood pays the full hash cost before any backoff exists to spend.
#
# Two things were unbounded, and this fixes both.
#
# **CPU and memory.** Each call is one core for tens of milliseconds and holds
# 19 MiB while it runs. `parallelism=1` means more concurrent hashes than cores
# buys no throughput at all — it only multiplies latency and resident memory.
# Twenty in flight was ~380 MiB and every core pegged.
#
# **The shared thread pool.** `to_thread.run_sync` without a limiter draws on
# anyio's default `CapacityLimiter`, which is process-wide and defaults to 40
# tokens. So an argon2 flood does not only starve itself: it exhausts the pool
# every *other* blocking call in the application shares. A dedicated limiter is
# what keeps the flood inside its own budget.
#
# **What this does and does not fix.** Excess hashes now queue instead of
# running, so a flood still makes *its own* requests slow — that is the
# attacker's problem, and the point. What it stops is the flood taking the
# service down with it: the event loop stays free, the shared pool stays
# available, and `/health` keeps answering, which is how a load balancer decides
# whether this process is alive.
_HASHING_LIMITER = CapacityLimiter(max(2, (os.cpu_count() or 2) - 1))
"""Concurrent argon2 calls allowed process-wide.

Sized to cores rather than to a round number, because the work is CPU-bound and
single-lane: at `parallelism=1` a hash occupies exactly one core, so a cap above
the core count adds queueing latency and 19 MiB per waiter without completing
anything sooner. One core is left for the event loop, and a floor of two keeps a
single-core box from serialising logins behind one another entirely.

Worth re-measuring rather than trusting: it bounds peak memory at roughly
`limit x 19 MiB`, which is the number to check on a small container.
"""


async def hash_password_async(password: str) -> str:
    """`hash_password`, on a worker thread, at most `_HASHING_LIMITER` at once."""
    validate_password(password)
    return await to_thread.run_sync(_hasher.hash, password, limiter=_HASHING_LIMITER)


async def verify_password_async(password_hash: str, password: str) -> bool:
    return await to_thread.run_sync(
        verify_password, password_hash, password, limiter=_HASHING_LIMITER
    )


async def spend_dummy_verification_async() -> None:
    # Under the same limiter as a real verification, deliberately. The dummy
    # exists so an unknown address costs what a known one does; letting it
    # bypass the queue would restore the timing difference it was added to
    # remove, and under load the gap would be the whole queueing delay rather
    # than the few milliseconds the equaliser was written for.
    await to_thread.run_sync(spend_dummy_verification, limiter=_HASHING_LIMITER)
