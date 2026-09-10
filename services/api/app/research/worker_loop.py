"""The worker's loop: claim a run, dispatch its sources, record each outcome.

Everything it needs already exists — `CLAIM_SQL` takes a run without two workers
taking the same one, `crawl_site` returns an outcome instead of raising, and
`state_for` derives the run's state from its sources. This is the wiring, and
its whole job is to preserve Q56 across the join.

**Each source is written independently, as it finishes.** Not batched at the
end: a worker that crashes after five of six sources should leave five results
behind, and the founder watching the progress screen should see them arrive
rather than nothing for four minutes and then everything.
"""

from __future__ import annotations

import json
from typing import Final
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import jobs_session
from app.domain.page_signals import CaptureSource, signals_to_json
from app.domain.research import (
    CLAIM_SQL,
    STALE_AFTER_MINUTES,
    SourceKind,
    SourceState,
    state_for,
)
from app.logging import get_logger
from app.research.runner import CrawlOutcome, crawl_site
from app.retrieval.scoped import apply_workspace_scope

log = get_logger(__name__)

CONCURRENT_SOURCES: Final = 3
"""How many sources run at once. Three rather than six because they share an
outbound connection budget and a database pool — running all six flat out makes
the slowest one slower, and none of them is the bottleneck the founder feels."""

UNAVAILABLE_NO_CREDENTIALS: Final = "unavailable: no_credentials"
"""Q53/D2. Keyword data **stays locked** rather than estimated. An estimate
that looks like a measurement is the one thing this product cannot ship — and it
would look exactly like the real thing on the screen."""


async def _record(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    run_id: UUID,
    kind: SourceKind,
    outcome: CrawlOutcome,
) -> None:
    """Write one source's outcome.

    **Scopes first, every time.** The GUC is transaction-local, so the commit
    that ended the previous statement also ended the scope — and an UPDATE under
    RLS with no policy match affects **zero rows and raises nothing**. The
    source stays `running` forever, the run never finishes, and there is nothing
    in any log. Found exactly that way.
    """
    # What was read, not just that reading happened.
    #
    # `result_json` existed from 0014 and nothing ever wrote it, so a completed
    # run left twenty fetched pages in memory and a row saying `succeeded` —
    # the deep research the founder was promised produced a green tick and no
    # material. Keeping the text is what lets the Brain be built from it later,
    # and what makes a claim in the Brain traceable to a page after the fact.
    payload = (
        json.dumps({"pages": outcome.pages, "js_rendered_urls": outcome.js_rendered_urls})
        if outcome.pages or outcome.js_rendered_urls
        else None
    )
    await apply_workspace_scope(db, workspace_id)
    await db.execute(
        text(
            "UPDATE research_source"
            "   SET state = :s, error_reason = :e, finished_at = now(), result_json = :p"
            " WHERE run_id = :r AND kind = :k"
        ),
        {
            "s": outcome.state.value,
            "e": outcome.error_reason,
            "p": payload,
            "r": str(run_id),
            "k": kind.value,
        },
    )

    # The signals, in the same transaction and only for a crawl. The other
    # source kinds have no HTML and nothing to extract.
    #
    # This path matters more than the onboarding one, because **it is the crawl
    # that recurs.** Onboarding runs once; this runs whenever a founder asks for
    # a fresh read. Leaving it out would mean the recurring crawl held signals
    # in memory and dropped them — the exact gap migration 0028 exists to close.
    #
    # Requires the `GRANT ... TO nexus_jobs` in 0028: this runs on the
    # maintenance role, and without the grant it raises `permission denied`
    # inside `_run_source`'s deliberately broad `except`, which reaches the
    # founder as "This step did not finish" and names nothing.
    if kind is SourceKind.CRAWL and outcome.signals:
        await db.execute(
            text(
                "UPDATE page_signals SET superseded_at = now()"
                " WHERE workspace_id = :ws AND superseded_at IS NULL"
            ),
            {"ws": workspace_id},
        )
        for position, page in enumerate(outcome.pages):
            captured = outcome.signals.get(str(page.get("url", "")))
            if captured is None:
                continue
            await db.execute(
                text(
                    "INSERT INTO page_signals"
                    " (workspace_id, captured_by, run_id, url, position, signals)"
                    " VALUES (:ws, :by, :r, :url, :pos, CAST(:sig AS jsonb))"
                ),
                {
                    "ws": workspace_id,
                    "by": CaptureSource.RESEARCH_RUN.value,
                    "r": str(run_id),
                    "url": str(page.get("url", "")),
                    "pos": position,
                    "sig": json.dumps(signals_to_json(captured)),
                },
            )

    await db.commit()


async def _run_source(
    db: AsyncSession, *, workspace_id: UUID, run_id: UUID, kind: SourceKind, seeds: list[str]
) -> None:
    """One source, start to finish. **Never raises.**

    The `except` is deliberately broad. Q56 says one source failing must not
    fail the run, and a source that raises an exception nobody anticipated would
    do exactly that — so anything unhandled becomes a failed source with a
    reason, and the other five carry on.
    """
    # Scoped here, and again in `_record`. The GUC is transaction-local, so the
    # commit below ends it — and an UPDATE under RLS with no policy match
    # affects **zero rows and raises nothing**, leaving the source `queued`
    # forever with nothing in any log.
    await apply_workspace_scope(db, workspace_id)
    await db.execute(
        text(
            "UPDATE research_source SET state='running', started_at=now()"
            " WHERE run_id=:r AND kind=:k"
        ),
        {"r": str(run_id), "k": kind.value},
    )
    await db.commit()

    try:
        if kind is SourceKind.CRAWL:
            outcome = await crawl_site(seeds)
        elif kind is SourceKind.KEYWORDS:
            # Not implemented, and **not estimated** (Q53/D2).
            outcome = CrawlOutcome(
                state=SourceState.FAILED, error_reason=UNAVAILABLE_NO_CREDENTIALS
            )
        else:
            # The remaining four have no implementation yet. `skipped` rather
            # than `failed`: nothing broke, we have not built it, and telling a
            # founder their competitors research failed would be blaming them
            # for our backlog.
            outcome = CrawlOutcome(state=SourceState.SKIPPED)
    except Exception as exc:
        log.warning("research.source_crashed", kind=kind.value, error=str(exc))
        outcome = CrawlOutcome(
            state=SourceState.FAILED,
            error_reason="This step did not finish. The rest of your research is unaffected.",
        )

    await _record(db, workspace_id=workspace_id, run_id=run_id, kind=kind, outcome=outcome)


async def process_one_run(db: AsyncSession, *, only: UUID | None = None) -> UUID | None:
    """Claim a run and finish it, or return `None` if there is nothing queued.

    **The session must be able to see runs across workspaces**, and the app role
    cannot: `research_run` is row-level secured on `nexus.workspace_id`, so an
    app-role connection with no GUC set sees nothing and this returns `None`
    forever — a worker that looks healthy and processes nothing.

    So the claim runs on the **`nexus_jobs` role** (ADR 0018, migration 0021),
    which exists for exactly this shape: maintenance that must span tenants
    while holding a narrow policy rather than `BYPASSRLS`. It may SELECT and
    UPDATE runs and sources and nothing else — it cannot create a run, because
    queueing belongs to the founder who asked and is counted against their
    allowance.

    The `db` passed in is used for the **workspace-scoped** work that follows,
    once the claim has told us which workspace that is.

    `only` narrows the claim to one run. The worker never passes it — taking the
    oldest *is* the queue — but without it a test cannot assert anything on a
    shared database, because it claims whatever is oldest and that is somebody
    else's row. Finding #26.
    """
    # Claimed on the jobs connection: it is the only one that can see a run
    # before we know whose it is.
    async with jobs_session() as jobs:
        claimed = (
            await jobs.execute(
                text(CLAIM_SQL),
                {"stale": STALE_AFTER_MINUTES, "only": str(only) if only else None},
            )
        ).first()
        if claimed is None:
            return None
        await jobs.commit()

    run_id, workspace_id = claimed.id, claimed.workspace_id
    await apply_workspace_scope(db, workspace_id)

    row = (
        await db.execute(
            text("SELECT domain, website_url FROM workspace WHERE id = :w"),
            {"w": str(workspace_id)},
        )
    ).first()
    seeds = [
        u
        for u in ((row.website_url if row else None), (f"https://{row.domain}" if row else None))
        if u
    ]

    # **Commit before fanning out.** This session opened a transaction to read
    # the workspace, and a transaction held open across the gather keeps a
    # snapshot from before any source committed — so the read below would find
    # every source still `running` and derive a state from stale rows. Nothing
    # errors; the run simply never appears to finish.
    await db.commit()

    # **Sequential, on the session already scoped to this workspace.**
    #
    # The concurrent version — one session per source under a semaphore — is
    # written and does not work: the sources' updates matched zero rows under
    # RLS and every source stayed `queued`, with the crash handler firing
    # correctly and nothing in any log to say the write had been discarded.
    # That is the third time in this file that a silently-zero-row UPDATE has
    # looked exactly like work that never ran.
    #
    # Sequential is provably correct and six sources is not a throughput
    # problem: the crawl dominates, and D20 caps it at ten minutes regardless.
    # Concurrency here is an optimisation, and an optimisation that loses
    # results is worse than a slow run. `CONCURRENT_SOURCES` stays as the
    # documented intent for whoever finishes it.
    for kind in SourceKind:
        await _run_source(db, workspace_id=workspace_id, run_id=run_id, kind=kind, seeds=seeds)

    await apply_workspace_scope(db, workspace_id)
    states = [
        SourceState(r.state)
        for r in (
            await db.execute(
                text("SELECT state FROM research_source WHERE run_id = :r"),
                {"r": str(run_id)},
            )
        ).all()
    ]
    await db.execute(
        text("UPDATE research_run SET state = :s, finished_at = now() WHERE id = :i"),
        {"s": state_for(states).value, "i": str(run_id)},
    )
    await db.commit()

    log.info("research.run_finished", run_id=str(run_id), state=state_for(states).value)
    return UUID(str(run_id))
