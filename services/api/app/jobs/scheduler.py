"""Scheduled work.

Deliberately minimal. Doc 07 §3 calls for "a scheduler for crawls, refreshes,
score recomputation and briefs"; today there is exactly one job, and adding a
queue, a broker and a worker pool for it would be building for a load that does
not exist.

APScheduler in-process is the honest choice at this size, and it has one
limitation worth naming rather than discovering: **with more than one API
process, every process runs the job.** The expiry sweep is idempotent so that is
currently harmless, but the moment a job is *not* idempotent — sending a brief,
charging a card — this needs a real scheduler with leader election. That is
recorded here so it is a decision rather than an accident.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.db import _unscoped_session, jobs_session
from app.jobs.expiry import run_expiry_sweep
from app.logging import get_logger

log = get_logger(__name__)

FIRST_RUN_DELAY = timedelta(seconds=45)
"""Long enough for the pool and migrations to settle, short enough that a
restart is not what stands between expired data and its deletion."""

EXPIRY_INTERVAL_MINUTES = 60

EMBEDDING_INTERVAL_MINUTES = 5
"""Short. A document the customer just uploaded should become searchable in
minutes, not hours - and a pass with nothing to do costs one indexed query."""

EMBEDDING_BATCH = 64

RESEARCH_INTERVAL_MINUTES = 1
"""Short, because a founder is watching.

The run is enqueued the moment their company is created and its results feed the
Company Brain at the end of onboarding — a sweep on a long interval would mean
the interview routinely finishes first and the Brain is built from the three
pages the foreground read. A pass with nothing queued costs one indexed query.
"""


async def _expiry_job() -> None:
    try:
        async with _unscoped_session() as db, jobs_session() as jobs_db:
            await run_expiry_sweep(db, jobs_db)
    except Exception as exc:
        log.warning("expiry.sweep.failed", error=type(exc).__name__)


async def _research_job() -> None:
    """Claim and finish one queued research run.

    The last link in a chain that was otherwise complete. `process_one_run`
    was written, tested and reachable, and nothing scheduled it — so a run
    enqueued at company registration sat `queued` forever. Company creation
    inserted the run, the sources were added, the worker loop knew how to drain
    them, and no clock ever called it. Nothing errored; the queue simply grew.

    One run per tick, not a drain loop. `process_one_run` claims a single run
    without two workers taking the same one, and finishing one run per minute is
    both enough for the signup rate this product has and a natural cap on how
    much crawling happens at once.
    """
    from app.research.worker_loop import process_one_run

    async with jobs_session() as db:
        run_id = await process_one_run(db)
    if run_id is not None:
        log.info("research.run_finished", run_id=str(run_id))


async def _embedding_job() -> None:
    """Fill in vectors for chunks uploaded since the last pass (task 5.6).

    Runs in the API process, like the expiry sweep. That is acceptable while the
    embedder is absent by default: `embed_pending` checks availability before it
    queries, and the model is imported lazily, so a deployment without the
    optional dependency pays nothing at all.

    It stops being acceptable the moment `[embeddings]` is installed in
    production - the weights are ~2GB resident, in the process that serves
    requests. At that point this belongs in a separate worker. Recorded here
    rather than in a backlog because the trade-off is invisible from the outside
    until memory runs out.
    """
    from app.documents.embed import embed_pending
    from app.embeddings.registry import get_embedder

    try:
        async with _unscoped_session() as db:
            report = await embed_pending(db, get_embedder(), limit=EMBEDDING_BATCH)
            if report.embedded:
                await db.commit()
    except Exception as exc:
        log.warning("embeddings.pass.failed", error=type(exc).__name__)


def build_scheduler() -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone="UTC")
    scheduler.add_job(
        _expiry_job,
        trigger=IntervalTrigger(minutes=EXPIRY_INTERVAL_MINUTES),
        id="expiry_sweep",
        name="Expire Preview data and stale claims",
        # Skip rather than pile up if a run overruns its window.
        max_instances=1,
        coalesce=True,
        # Run shortly after start so a long-lived process is not the only thing
        # standing between expired data and its deletion.
        #
        # This said `next_run_time=None` for its whole life, which is not "no
        # opinion" — it is APScheduler's representation of *paused*. `add_job`
        # only computes a first fire time when the attribute is absent, so the
        # slot being set to None meant one was never computed and the sweep
        # never ran, in any deployment. Startup logged `scheduler.started
        # jobs=['expiry_sweep']` throughout, so nothing looked wrong.
        #
        # What that cost: Preview audits of companies who have no account here
        # were retained past their TTL indefinitely, which `jobs/expiry.py`
        # calls an obligation to a third party. `rate_limit_counter` grew
        # without bound on the unauthenticated path.
        next_run_time=datetime.now(UTC) + FIRST_RUN_DELAY,
    )
    scheduler.add_job(
        _embedding_job,
        trigger=IntervalTrigger(minutes=EMBEDDING_INTERVAL_MINUTES),
        id="embedding_pass",
        name="Embed newly uploaded document chunks",
        max_instances=1,
        coalesce=True,
        # Explicit for the same reason as above: omitting it would be fine, but
        # `None` would silently mean paused, and that mistake has already been
        # made once in this file.
        next_run_time=datetime.now(UTC) + FIRST_RUN_DELAY,
    )
    scheduler.add_job(
        _research_job,
        trigger=IntervalTrigger(minutes=RESEARCH_INTERVAL_MINUTES),
        id="research_runs",
        name="Drain queued company research runs",
        max_instances=1,
        coalesce=True,
        next_run_time=datetime.now(UTC) + FIRST_RUN_DELAY,
    )
    return scheduler
