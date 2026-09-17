# Required environment

**Generated from `Settings`. Do not edit by hand** —
`tests/test_deployment_env.py` regenerates this and fails if it disagrees.

A hand-written list of environment variables drifts, and the way you find out
is a deployment that boots and then fails on the first request needing the
setting nobody wrote down.

## Refused at startup when missing

In any environment other than `local` and `ci`, the process refuses to start
and names **every** missing variable at once — a deployment fixing them one
restart at a time is a deployment being told the truth slowly.

- `NEXUS_DATABASE_URL`
- `NEXUS_STORAGE_SIGNING_SECRET`
- `NEXUS_CONNECTOR_SECRET_KEY`

`NEXUS_ENV` has no default and is required everywhere, including locally
(ADR 0015): a missing value used to mean `local`, which is how a production
process ends up with insecure cookies and the docs page open.

## Optional, and absent is a supported state

- `NEXUS_ANTHROPIC_API_KEY` — without it the language model reports
  `unconfigured` and refuses rather than inventing (ADR 0011).
- `NEXUS_JOBS_DATABASE_URL` — the `nexus_jobs` role for maintenance lookups
  that RLS hides from the app role (ADR 0018).
- `NEXUS_RUN_SCHEDULER` — **true on exactly one container**, the worker.
  Every API process running every job means one copy of each sweep per
  replica, and the jobs are idempotent rather than exclusive, so the symptom
  is load rather than an error anybody sees.
- `NEXUS_PROXY_TIMEOUT_MS` — the BFF's budget, 30s by default (finding #23).
