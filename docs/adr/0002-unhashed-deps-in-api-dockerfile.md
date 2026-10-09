# 0002. Install three missing deps via unhashed pip in the API Dockerfile

- **Status:** Accepted (temporary)
- **Date:** 2026-10-09
- **Deciders:** @parul-bhoite

## Context

The API image crash-looped on Railway with `ModuleNotFoundError: No module
named 'cryptography'`. Investigation showed `requirements-dev.lock` is missing
three dependencies that `pyproject.toml` declares and `uv.lock` resolves:
`cryptography>=44.0`, `mcp>=2.2`, `defusedxml>=0.7` (the finding-#16 lock-drift
class already documented in `nexus-os/CLAUDE.md`).

The image installs the lock with `pip install --require-hashes -r
requirements-dev.lock`, then `pip install -e . --no-deps`. Because the project
package is installed with `--no-deps`, anything the lock omits never lands — so
these three never install in the image, even though a local `pip install -e .`
pulls them from `pyproject`. The image had therefore never successfully booted
this import path. `cryptography` (connector credential sealing) and
`defusedxml` (document XML parsing) are imported at startup; `mcp` is imported
lazily (CRM connector sessions only).

This blocked the deploy and had to be resolved to get a live link.

## Options considered

### A. Regenerate `requirements-dev.lock` from pyproject (the documented fix)
`uv pip compile … --generate-hashes`. Produces a complete, hashed lock. But a
fresh resolve bumps the pinned core: SQLAlchemy 2.0.52 → 2.1.4, pydantic 2.13 →
2.14, fastapi, starlette, asyncpg, and more (verified by generating to a temp
file and diffing). Any of those could change runtime behaviour, and validating
them needs build/run cycles the deploy could not absorb at that moment.

### B. Add the missing packages via a separate unhashed `pip install` in the Dockerfile
Adds only the omitted packages; their transitive deps (`cffi`, `pycparser`) are
already in the lock, so no pinned core version moves. Deviates from the
`--require-hashes` discipline for these lines. Matches the pattern already used
for the optional `anthropic` SDK.

### C. Hand-edit the hashed lock to add the three
The lock header says "Generated, never edited by hand"; computing correct hashes
by hand is error-prone. Rejected.

## Decision

Option B, scoped to the two startup-critical packages:
`RUN pip install "cryptography>=44.0" "defusedxml>=0.7"`. `mcp` is deferred —
it is imported lazily, and pulling it would force the pydantic/starlette bump
(it is why Option A moved those), which is exactly the risk being avoided.

## Reasoning

The decisive constraint was blast radius versus time. Option A is the correct
end state but changes ~20 pinned versions including two minor-version bumps
(SQLAlchemy 2.0→2.1), untested against this app, with no room to validate before
the deploy. Option B changes nothing already pinned — it only adds packages the
app already declares and expects — so it unblocks the boot with the smallest
possible surface. The hashed-install guarantee is weakened for exactly two
pure-ish additions whose transitive deps were already hashed in the lock, which
is a deliberately small, reversible concession. `mcp` stays out because adding
it would reintroduce the core bump this decision exists to avoid, and nothing at
startup needs it.

## Consequences

- The API image boots and serves; the deploy is unblocked.
- The image's dependency set is no longer fully hash-pinned: `cryptography`,
  `defusedxml`, and whatever they pull resolve at build time, so two builds can
  differ — the drift this project otherwise works to prevent, now in the image.
- `mcp`-backed CRM connector sessions will raise `ModuleNotFoundError` if
  exercised, until `mcp` is installed (lock regen, or another explicit install).
- A newcomer reading the Dockerfile sees deps installed in two places (lock +
  ad-hoc pip), which is a smell that must be explained — hence this record.

## Revisit trigger

Regenerate `requirements-dev.lock` from `pyproject.toml` (the command in the
lockfile header) and delete the ad-hoc `pip install` lines (`anthropic` too)
**before the next intentional core version bump**, or as soon as a maintenance
window allows validating the resulting SQLAlchemy/pydantic/starlette bumps —
whichever comes first. Also revisit immediately if a CRM connector feature that
uses `mcp` is scheduled, since that needs `mcp` present.
