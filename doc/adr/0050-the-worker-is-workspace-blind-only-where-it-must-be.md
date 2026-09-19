# 0050. The worker is workspace-blind only where it must be

- **Status:** Accepted
- **Date:** 2026-09-19
- **Deciders:** Parul
- **Narrows:** ADR 0021's grant (migration 0021), not ADR 0018's role split
- **Closes:** the scope-loss half of `AUDIT-FINDINGS.md` finding #26
- **Implemented by:** migration `0039_narrow_research_source_worker_policies`

## Context

`nexus_jobs` exists (ADR 0018) so maintenance that must span tenants can hold a
**narrow policy** rather than `BYPASSRLS`. Migration 0021 gave it `USING (true)`
on two tables so the research worker could claim queued runs, and the reason was
sound for one of them: **the worker has no workspace until it claims a run.**
`CLAIM_SQL` is an UPDATE on `research_run` issued before anyone knows whose row
it is. A GUC-keyed policy there would match nothing, and the worker would
process nothing while looking perfectly healthy — finding #25, exactly.

`research_source` was granted the same blanket policy in the same statement, and
that half was never needed. Every access to it happens *after* the claim has
said which workspace this is, and `worker_loop` calls `apply_workspace_scope`
immediately before each one.

What made this worth a migration rather than tidying is what the blanket policy
cost. `worker_loop._write_one` was added in the same pass to close the pattern
finding #26 names: three times, an UPDATE ran with the workspace scope lost,
matched zero rows, raised nothing, and left a run that could never finish with
nothing in any log. The guard raises unless a write matches exactly one row.

**The guard could not fire where the bug happens.** `_research_job` passes a
`jobs_session()`, so all three guarded writes run as `nexus_jobs` in production.
Permissive policies **OR**, so `research_source_worker_write USING (true)`
sitting beside the GUC-keyed `research_source_workspace_isolation` meant the GUC
could not reduce a rowcount to zero for that role. The guard fired only in
tests, which drive the app role — the most misleading possible place for a guard
to work, because the register would have recorded the pattern as closed.

Found by `security-reviewer` on the guard commit, and confirmed against Neon's
`pg_policy` rather than inferred from the migration having run.

## Options considered

### A. Leave the policies; accept the guard as missing-row detection only

`_write_one` still catches a row that was never inserted or was deleted, on any
path. Honest, if the register says only that.

It leaves the original defect — the one that has now occurred three times —
undetectable in production, and the next occurrence as invisible as the first.

### B. Rewrite both `research_source` policies as GUC-keyed

Symmetrical with 0021 and explicit about intent.

The predicate would be character-for-character `research_source_workspace_isolation`,
which is a `PUBLIC` policy `FOR ALL` and therefore already governs `nexus_jobs`.
Two identical permissive policies are one rule with a second place to drift.

### C. Drop the two `research_source` worker policies; keep the grant

Leave the PUBLIC isolation policy as the single rule for every role, and leave
`research_run`'s two policies untouched.

## Decision

Option C. Migration 0039 drops `research_source_worker` and
`research_source_worker_write`. `GRANT SELECT, UPDATE ON research_source TO
nexus_jobs` stays — table privileges and row policies are separate concerns, and
the worker still needs the privilege.

`research_run` keeps both blanket policies, because the claim genuinely must be
workspace-blind.

## Reasoning

**The decisive question was which writes can possibly precede knowing the
workspace, and the answer is exactly one: the claim.** Everything after it is
scoped by construction, so a blanket policy over `research_source` bought
nothing and disabled the only mechanism that can detect a lost scope — a
rowcount of zero.

Dropping rather than replacing (C over B) follows from the isolation policy
already being `PUBLIC` and `FOR ALL`. Restating it per-role would make the
narrowing *look* more deliberate while creating a second definition to keep in
step; the smaller surface is the safer one.

**What stays uncovered, deliberately.** The third guarded write — the final
`UPDATE research_run SET state` — still runs under `research_run_worker_claim
USING (true)`, so a lost scope there is still undetectable. Splitting that
policy so the claim is permitted but the finish is GUC-keyed was considered and
rejected: the claim's predicate would have to reproduce `CLAIM_SQL`'s staleness
window (`state = 'queued' OR stale`) inside RLS, where it would drift away from
the SQL it mirrors. A guard that is correct for two of three writes and honest
about the third beats one that is subtly wrong about all three.

**Failure direction.** If this narrowing is wrong — if some path touches
`research_source` without scoping first — the worker fails **closed**: the write
matches nothing and `_write_one` raises loudly. That is the opposite of the
failure this whole thread is about, and it is why the change was safe to make
before every caller could be exhaustively enumerated.

## Consequences

- A lost workspace scope in the worker's two `research_source` writes now
  matches zero rows and raises `DiscardedWriteError`, on the role production
  actually uses.
- `nexus_jobs` can no longer read or write another workspace's sources while
  unscoped, which is a real reduction in what a compromised worker reaches.
- The final run-state write keeps its blind spot; finding #26 stays open for
  that sliver rather than being marked closed.
- Reversible: `downgrade` recreates 0021's policies verbatim. Reversing also
  restores the blind spot, which the migration's docstring says plainly.

## Revisit trigger

If a second consumer of `research_source` under `nexus_jobs` appears that
legitimately needs cross-workspace reads — a backfill, a support tool, an
analytics sweep — it needs its own policy argued on its own terms, not this one
widened back. And if `CLAIM_SQL`'s staleness predicate ever moves into the
database (a view, a function), revisit splitting `research_run_worker_claim`,
because the drift objection above disappears with it.
