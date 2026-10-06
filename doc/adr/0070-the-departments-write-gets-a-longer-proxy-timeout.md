# ADR 0070 — The departments write gets a longer proxy timeout

- Status: Accepted
- Date: 2026-10-06
- Related: ADR 0069 (conversational onboarding — the walkthrough that surfaced
  this), finding #23 (why the default proxy timeout is 30s and not 15s),
  `MODEL_TIMEOUT_MS` in `apps/web/lib/auth-proxy.ts`.

## Context

The BFF proxy (`apps/web/lib/auth-proxy.ts`) aborts an upstream request after a
default **30s** (`TIMEOUT_MS`), with named exceptions for model-backed routes
(`MODEL_TIMEOUT_MS`, 90s) and a few onboarding-agent routes (explicit literals up
to 240s). `PUT /api/companies/current/departments` — the replace-the-department-set
write — inherited the 30s default.

During the ADR 0069 onboarding walkthrough against Neon it **504'd twice in a
row** on the critical path. The cause was not a single slow request but a cascade:
the replace-set is a delete-and-reinsert that re-derives what each director can
see, and on a slow day it ran past 30s; the proxy aborted; **the aborted write
left its row/lock held**, so the retry blocked on that lock and timed out too. A
founder was stuck mid-onboarding on a 504 that a retry could not clear. Restarting
the API (dropping the connections, releasing the lock) was the only way through.

The same endpoint had succeeded earlier in the session — it is intermittent,
driven by Neon latency, and the 30s ceiling is simply too low for this particular
write when the database is far away and busy.

## Decision

Give `PUT /api/companies/current/departments` an explicit **`timeoutMs: 90_000`**,
documented in the route with the failure it prevents. The GET on the same path
keeps the default — it is a single fast read.

An explicit literal, **not `MODEL_TIMEOUT_MS`**: no model is invoked here, and
`apps/web/lib/__tests__/auth-proxy.test.ts` reserves that constant for
skill-invoking routes, so borrowing it would both misdescribe the route and risk
tripping that test's intent. 90s matches the slow-write headroom
`MODEL_TIMEOUT_MS` already uses, which is the right order of magnitude for a
multi-statement write to a managed database.

## Reasoning

- **Raising the ceiling removes the trigger, not just the symptom.** The
  user-visible failure was the *second* timeout (the lock-blocked retry). It only
  happened because the *first* request aborted. A window the write comfortably
  fits in means no abort, so no orphaned lock, so no cascade — the retry path is
  never entered.
- **30s was calibrated for a read, and this is not a read.** The default's own
  docstring says it is "comfortably above a round trip to a managed database" —
  i.e. sized for one statement. The department replace is several statements plus
  a re-derivation; holding it to the single-read budget was the mistake.
- **Client-side mitigation only, by intent.** This does not touch the backend.
  The deeper fix — releasing the lock when the client disconnects, or making the
  replace fewer round trips — is real but larger, and this one-line change
  unblocks onboarding today without a schema or transaction-handling change. See
  *Consequences*.
- **Scoped to the one route.** Raising the global default would hide genuinely
  slow reads elsewhere behind a 90s wall; the problem is specific to this write.

## Consequences

- A genuinely hung departments write now ties up the request for up to 90s before
  the founder is told it failed — a worse wait in the rare true-hang case, traded
  for removing the common slow-but-fine abort. Acceptable: a 90s wait that then
  succeeds beats a 30s failure that cannot be retried.
- The underlying **lock-orphan-on-abort** behaviour still exists for any write
  that does abort (a different route, or a >90s departments write). The backend
  fix for it is deliberately **deferred**, not taken here. If aborts recur, that
  becomes its own change (and likely its own ADR): release on disconnect, a
  server-side `statement_timeout`/`lock_timeout` tuned below the proxy ceiling, or
  fewer statements in the replace.
- This is the local-Neon profile. CI and the throwaway container answer in
  microseconds and never approach either ceiling, so the change is invisible
  there — the usual "green where nobody deploys" caveat applies in reverse.

## Revisit trigger

Revisit if any of:
- The departments write starts exceeding **90s** (the cascade would return at the
  higher ceiling) — at which point the backend fix above is the answer, not a
  higher number.
- Connection pooling, a Neon region change, or a rewrite of `update_departments`
  materially lowers the write's latency, making the raised ceiling unnecessary —
  fold it back to the default rather than leave a ceiling nobody needs.
- A second route needs the same treatment, which would argue for a named
  `WRITE_TIMEOUT_MS` constant rather than a second literal.
