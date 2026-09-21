# 0060. The one test module that crosses event loops does not pool connections

- **Status:** Accepted
- **Date:** 21 September 2026
- **Deciders:** Parul
- **Decides:** D37
- **Affects:** `services/api/tests/test_onboarding_agent_e2e.py`
- **Closes:** M22, open since before the 19 September regeneration

## Context

M22 has cost a false failure on every full backend run for weeks, recorded only
as *"a known asyncpg flake that passes alone"*. It was never diagnosed because
every symptom pointed somewhere unhelpful: the failing test was different from
the leaking one, the error was a `ResourceWarning` rather than an assertion, and
reproducing it appeared to need a two-hour suite.

The cause, proven on 21 September:

1. A pooled asyncpg connection is **created on one event loop and closed on
   another**. pytest gives each test its own loop; the engine is module-cached.
2. asyncpg's graceful `close()` arms a timeout timer **on the loop that created
   the connection**. That loop is gone, so `loop.call_later` raises
   `RuntimeError: Event loop is closed`.
3. asyncpg catches it and falls back to `_abort()`.
4. Aborting a **TLS** transport on CPython 3.12 does not close the socket
   beneath it — hence three warnings together: `socket`,
   `_SelectorSocketTransport`, `_SSLProtocolTransport`.
5. **SQLAlchemy's `Pool._close_connection` swallows and logs that exception**,
   at DEBUG. Nothing raises; a socket quietly survives.

`filterwarnings = ["error"]` then turns the surviving warning into a failure —
attributed to **whichever test happened to trigger garbage collection**, which
is what made it look random and why "fixing" the reported test would have been
treating a bystander.

**Measured, not inferred.** The leaking teardown completes in 0.008s with no
network round trip and `aborted=True`; a healthy one takes 0.273s with
`aborted=False` and `is_closing=True`. Loop identities confirm the rest: the
leaking test connects on one loop and tears down on another; the clean test uses
one loop for both.

**This is a harness artefact, not a product defect.** Production runs one event
loop for the life of the process, so the cross-loop close cannot occur there.
That is what makes a test-only remedy legitimate rather than a cover-up.

## Options considered

### A. `NullPool` suite-wide in tests
Verified: warnings to zero. Also verified: the two reproducing tests go **100s →
186s**, because every checkout becomes a fresh TLS connect to `us-east-2`.
Across roughly 470 database tests that is hours added to every run.

### B. A narrow `filterwarnings` ignore
Free, and there is precedent in `pyproject.toml` for a narrow, message-matched,
commented ignore. It would also **hide a genuine socket leak anywhere else in
the suite** — and `filterwarnings = ["error"]` has already caught two real
defects here: an unpinned `anyio` deprecation, and a fastembed pooling warning
that surfaced during this very build.

### C. `NullPool` scoped to the one module that reproduces it
A's correctness where the problem is, at part of A's cost, and `error` keeps
meaning what it says everywhere else. **The cost was estimated at "about ninety
seconds" when this was decided. It is not — see the addition below.**

## Decision

Option C.

**Only the pool class changes.** Not `NEXUS_DB_TRANSACTION_POOLER=true`, which
would have been a one-line fixture change and was rejected deliberately: that
flag *also* drops the prepared-statement caches and the pre-ping, so this module
would exercise a driver configuration production never uses. Every other engine
keyword, and every connect hook including `_apply_session_timeouts`, stays
production's.

## Reasoning

**Against A on arithmetic.** It is the most thorough fix and it makes the suite
slower than the problem it solves. A two-hour run becoming four is a cost paid
on every commit, to remove one false failure.

**Against B on what it gives up.** The ignore is not wrong in principle — the
warning genuinely cannot happen in production. It is wrong in blast radius: it
would silence unclosed sockets from `httpx`, from a connector, from anything.
This repository's `filterwarnings = ["error"]` has earned its keep twice, and
trading a standing signal for one flake is the wrong direction.

**C's accepted cost** is a special case: one module behaves differently from its
neighbours, and somebody moving a test into or out of it may be surprised. The
docstring on `_unpooled` states the whole causal chain so that surprise is
answerable in one read rather than another two-hour bisect.

**Why not fix the loop mismatch itself.** It is the real defect, and it lives in
the interaction between pytest's per-test loops and a module-cached engine.
Keying the engine cache by running loop would mean changing `app/db.py` —
production code — to accommodate a test harness. That trade is worse than the
special case, and it is named here so the option is not lost.

## Consequences

- `test_onboarding_agent_e2e.py` opens a fresh connection per checkout. Slower
  than pooling, and the module is already the slowest in the suite.
- The full backend run should go from 4 failures to 3, and then to 0 with the
  three registration fixes already landed — making a green full run the
  baseline again, which it has not been for weeks.
- A test moved **into** this module inherits `NullPool`; one moved **out**
  inherits the flake. The docstring says so.
- If a second module starts crossing loops, this ADR's revisit trigger applies
  rather than a second copy of the fixture.

## Revisit trigger

Reopen when **a second module** needs this, and prefer moving the seam into a
shared fixture at that point rather than copying it a third time. Reopen sooner
if CPython or asyncpg fixes the abort-leaves-TLS-socket-open behaviour, or if
SQLAlchemy stops swallowing the close exception — either makes the underlying
mismatch visible enough to fix properly, and this becomes unnecessary rather
than merely narrow.


## Addition, 21 September 2026 — the measured cost, and a correction

**It works.** The module runs **34 passed, 0 failed, 0 `ResourceWarning`s**,
against a baseline of 32 passed / 2 failed. M22 is closed.

**It costs 11m39s, not the ninety seconds this ADR estimated.** The module goes
**20:03 → 31:42, +58%**. On the full backend run that is roughly +9%, taking
2:09:44 to about 2:21.

The estimate was wrong because it was extrapolated from the two-test
reproduction (100s → 186s, +86s) straight onto a **34-test** module, as though
the penalty were per-run rather than per-checkout. It is per-checkout: every
connection is a fresh TLS handshake to `us-east-2`. The arithmetic was there to
do and was not done.

**The decision still holds**, and now on real numbers rather than a guess:
option A was ~1.9x across roughly 470 database tests — hours. C is eleven and a
half minutes, in one module, buying a green full run for the first time in
weeks.

**What this does change** is the revisit trigger's urgency. A second module
adopting this pattern would cost another double-digit slice of the run, so the
shared-fixture question below should be answered *before* a second copy exists,
not after.
