"""The worker joins the pieces without losing Q56.

`crawl_site` returns instead of raising, `CLAIM_SQL` stops two workers taking
one run, `state_for` derives the run's state. This is the wiring, and wiring is
where an invariant that each piece holds individually gets dropped.

The end-to-end test is the one worth having: a real run, real rows, one source
deliberately crashing, and the other five still arriving.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from uuid import uuid4

import pytest
import sqlalchemy as sa

from app.config import get_settings
from app.db import get_engine, get_sessionmaker, jobs_session
from app.domain.research import SourceKind, SourceState
from app.research import worker_loop
from app.research.runner import CrawlOutcome
from app.retrieval.scoped import apply_workspace_scope
from tests.dburl import async_database_url, database_url, jobs_database_url

ASYNC_DB_URL = async_database_url()
requires_db = pytest.mark.requires_db


@pytest.fixture
async def app_db(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[None]:
    assert ASYNC_DB_URL is not None
    monkeypatch.setenv("NEXUS_DATABASE_URL", ASYNC_DB_URL)
    monkeypatch.setenv("NEXUS_STORAGE_SIGNING_SECRET", "test-secret")
    for cache in (get_settings, get_engine, get_sessionmaker):
        cache.cache_clear()
    yield
    await get_engine().dispose()
    for cache in (get_settings, get_engine, get_sessionmaker):
        cache.cache_clear()


def test_keyword_data_is_never_estimated() -> None:
    """Q53/D2. An estimate that looks like a measurement is the one thing this
    product cannot ship — and on screen it would look exactly like the real
    thing."""
    assert "no_credentials" in worker_loop.UNAVAILABLE_NO_CREDENTIALS
    assert "unavailable" in worker_loop.UNAVAILABLE_NO_CREDENTIALS


def test_sources_do_not_all_run_at_once() -> None:
    """Six sources flat out share one outbound budget and one database pool,
    which makes the slowest slower without any of them being the bottleneck the
    founder actually feels."""
    assert 0 < worker_loop.CONCURRENT_SOURCES < len(SourceKind)


@requires_db
async def test_a_crashing_source_does_not_take_the_run_with_it(
    app_db: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Q56, across the wiring. The crawl raises something nobody anticipated;
    the other five sources must still be written and the run must still finish.
    """

    async def explode(*_: object, **__: object) -> CrawlOutcome:
        raise RuntimeError("something nobody anticipated")

    monkeypatch.setattr(worker_loop, "crawl_site", explode)

    async with get_sessionmaker()() as db:
        user, tenant, ws = uuid4(), uuid4(), uuid4()
        await db.execute(
            sa.text("INSERT INTO app_user (id, email) VALUES (:i,:e)"),
            {"i": str(user), "e": f"wl-{user.hex[:8]}@example.com"},
        )
        await db.execute(
            sa.text("INSERT INTO tenant (id, name) VALUES (:i,'T')"), {"i": str(tenant)}
        )
        await apply_workspace_scope(db, ws)
        await db.execute(
            sa.text(
                "INSERT INTO workspace (id, workspace_id, tenant_id, name, domain,"
                " website_url, domain_verified_at)"
                " VALUES (:i,:i,:t,'W',:d,:u, now())"
            ),
            {
                "i": str(ws),
                "t": str(tenant),
                "d": f"wl-{ws.hex[:8]}.om",
                "u": f"https://wl-{ws.hex[:8]}.om",
            },
        )
        run = uuid4()
        await db.execute(
            sa.text(
                "INSERT INTO research_run (id, workspace_id, state, requested_by_user_id)"
                " VALUES (:i,:w,'queued',:u)"
            ),
            {"i": str(run), "w": str(ws), "u": str(user)},
        )
        for kind in SourceKind:
            await db.execute(
                sa.text(
                    "INSERT INTO research_source (workspace_id, run_id, kind, state)"
                    " VALUES (:w,:r,:k,'queued')"
                ),
                {"w": str(ws), "r": str(run), "k": kind.value},
            )
        await db.commit()

        try:
            # **No scoping here, deliberately.** The worker claims as
            # `nexus_jobs`, which can see runs before it knows whose they are —
            # that is finding #25's fix (migration 0021). If this test scoped
            # the session first it would pass whether or not the grant exists,
            # and the defect it was written for would be invisible again.
            # **Claim this run specifically** (`only`).
            #
            # `CLAIM_SQL` takes the *oldest* queued run, which is right — the
            # founder who asked first is served first. It also means that on a
            # shared database this test claims somebody else's row, and the
            # assertion then quietly depends on the queue being empty, which is
            # not a state a shared database has.
            #
            # Draining was the first attempt and it deadlocked on a sourceless
            # run that re-queued itself. Narrowing the claim is the actual fix,
            # and it is a shape the worker wants anyway — `only` is finding
            # #26's resolution.
            processed = await asyncio.wait_for(
                worker_loop.process_one_run(db, only=run), timeout=180
            )
            assert processed is not None and str(processed) == str(run)

            await apply_workspace_scope(db, ws)
            rows = {
                r.kind: (r.state, r.error_reason)
                for r in (
                    await db.execute(
                        sa.text(
                            "SELECT kind, state, error_reason FROM research_source"
                            " WHERE run_id = :r"
                        ),
                        {"r": str(processed)},
                    )
                ).all()
            }

            # Every source was written, including the one that blew up.
            assert set(rows) == {k.value for k in SourceKind}
            assert rows["crawl"][0] == "failed"
            assert "rest of your research is unaffected" in rows["crawl"][1]

            # Q53/D2 — locked, not estimated.
            assert rows["keywords"][1] == worker_loop.UNAVAILABLE_NO_CREDENTIALS

            # The unbuilt sources are skipped, not failed: nothing broke, and
            # telling a founder their competitors research failed would blame
            # them for our backlog.
            assert rows["competitors"][0] == SourceState.SKIPPED.value

            # And the run itself finished rather than dying with the crawl.
            run_state = (
                await db.execute(
                    sa.text("SELECT state FROM research_run WHERE id = :i"),
                    {"i": str(processed)},
                )
            ).scalar_one()
            assert run_state in ("complete", "failed")
        finally:
            await apply_workspace_scope(db, ws)
            for statement in (
                "DELETE FROM research_source WHERE workspace_id = :w",
                "DELETE FROM research_run WHERE workspace_id = :w",
                "DELETE FROM workspace WHERE id = :w",
            ):
                await db.execute(sa.text(statement), {"w": str(ws)})
            await db.execute(sa.text("DELETE FROM app_user WHERE id = :u"), {"u": str(user)})
            await db.commit()


# ── The recurring crawl stores its signals ────────────────────


@requires_db
async def test_the_background_crawl_stores_page_signals(
    app_db: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The write path that actually recurs.

    Onboarding crawls once; this crawls whenever a founder asks for a fresh
    read. Leaving it out would have meant the recurring crawl held signals in
    memory and dropped them — the exact gap migration 0028 exists to close, and
    the one the browser walkthrough could never have caught, because a browser
    only exercises the onboarding path.

    Also the test that would catch a missing `GRANT ... TO nexus_jobs`: this
    runs on the app role rather than the worker's, so it proves the SQL and not
    the permission — `test_ci_contract.py` owns the grant. The two together are
    the coverage; either alone would leave a silent `permission denied` inside
    `_run_source`'s deliberately broad `except`.
    """
    from app.domain.page_signals import PageSignals, signals_to_json

    fetched = PageSignals(
        url="https://recrawled.example/",
        is_https=True,
        title="A page the worker read",
        title_length=22,
        meta_description="Long enough to be a real description of a real business.",
        meta_description_length=56,
        h1_texts=("A page the worker read",),
        word_count=420,
        internal_link_count=11,
    )

    async def one_page(*_: object, **__: object) -> CrawlOutcome:
        return CrawlOutcome(
            state=SourceState.SUCCEEDED,
            pages=[{"url": "https://recrawled.example/", "text": "Real prose about a business."}],
            signals={"https://recrawled.example/": fetched},
        )

    async with get_sessionmaker()() as db:
        user, tenant, ws, run = uuid4(), uuid4(), uuid4(), uuid4()
        await db.execute(
            sa.text("INSERT INTO app_user (id, email) VALUES (:i,:e)"),
            {"i": str(user), "e": f"sig-{user.hex[:8]}@example.com"},
        )
        await db.execute(
            sa.text("INSERT INTO tenant (id, name) VALUES (:i,'T')"), {"i": str(tenant)}
        )
        await apply_workspace_scope(db, ws)
        await db.execute(
            sa.text(
                "INSERT INTO workspace (id, workspace_id, tenant_id, name, domain)"
                " VALUES (:i,:i,:t,'W',:d)"
            ),
            {"i": str(ws), "t": str(tenant), "d": f"sig-{ws.hex[:8]}.om"},
        )
        await db.execute(
            sa.text(
                "INSERT INTO research_run (id, workspace_id, state, requested_by_user_id)"
                " VALUES (:i,:w,'running',:u)"
            ),
            {"i": str(run), "w": str(ws), "u": str(user)},
        )
        await db.execute(
            sa.text(
                "INSERT INTO research_source (workspace_id, run_id, kind, state)"
                " VALUES (:w,:r,:k,'running')"
            ),
            {"w": str(ws), "r": str(run), "k": SourceKind.CRAWL.value},
        )
        # A previous crawl's row, so the supersede is exercised rather than
        # assumed. Two generations both current would leave the reader's
        # `ORDER BY position LIMIT 1` picking a stale page half the time.
        await db.execute(
            sa.text(
                "INSERT INTO page_signals"
                " (workspace_id, captured_by, run_id, url, position, signals)"
                " VALUES (:w,'research_run',:r,'https://stale.example/',0, CAST(:s AS jsonb))"
            ),
            {"w": str(ws), "r": str(run), "s": json.dumps(signals_to_json(fetched))},
        )
        await db.commit()

        try:
            monkeypatch.setattr(worker_loop, "crawl_site", one_page)
            await worker_loop._run_source(
                db,
                workspace_id=ws,
                run_id=run,
                kind=SourceKind.CRAWL,
                seeds=["https://recrawled.example/"],
                domain="recrawled.example",
            )

            await apply_workspace_scope(db, ws)
            rows = (
                await db.execute(
                    sa.text(
                        "SELECT url, captured_by, position, (superseded_at IS NULL) AS current"
                        " FROM page_signals WHERE workspace_id = :w ORDER BY current, position"
                    ),
                    {"w": str(ws)},
                )
            ).all()

            current = [r for r in rows if r.current]
            assert len(current) == 1, [r.url for r in current]
            assert current[0].url == "https://recrawled.example/"
            assert current[0].captured_by == "research_run"
            assert current[0].position == 0

            # The old row is superseded, not deleted: it is the history that
            # explains why a figure moved.
            superseded = [r for r in rows if not r.current]
            assert [r.url for r in superseded] == ["https://stale.example/"]
        finally:
            await apply_workspace_scope(db, ws)
            for statement in (
                "DELETE FROM page_signals WHERE workspace_id = :w",
                "DELETE FROM research_source WHERE workspace_id = :w",
                "DELETE FROM research_run WHERE workspace_id = :w",
                "DELETE FROM workspace WHERE id = :w",
            ):
                await db.execute(sa.text(statement), {"w": str(ws)})
            await db.execute(sa.text("DELETE FROM app_user WHERE id = :u"), {"u": str(user)})
            await db.commit()


@requires_db
async def test_a_write_that_matches_no_rows_is_refused_rather_than_ignored(
    app_db: None,
) -> None:
    """A write that matches nothing raises instead of passing silently.

    Three times in this file's history an UPDATE matched zero rows, raised
    nothing, and left a run that could never finish with nothing in any log.
    `_write_one` is the guard; this is the proof that it fires.

    **Read what this does and does not cover.** It drives the *app-role*
    session, where `research_source_workspace_isolation` is the only policy, so
    a foreign workspace id produces zero rows. On the deployed path
    `_research_job` passes a `jobs_session()`, and migration 0021 gives
    `nexus_jobs` `research_source_worker_write USING (true)` — permissive
    policies OR, so a lost GUC there still matches the row and this guard stays
    silent. What the guard catches on *every* path is a **missing row**: a run
    whose `research_source` was never inserted, or was deleted under it.
    Closing the scope-loss half needs 0021's worker policies narrowed to the
    GUC, which is tracked as finding #26 and wants its own ADR.
    """
    async with get_sessionmaker()() as db:
        user, tenant, ws = uuid4(), uuid4(), uuid4()
        await db.execute(
            sa.text("INSERT INTO app_user (id, email) VALUES (:i,:e)"),
            {"i": str(user), "e": f"dw-{user.hex[:8]}@example.com"},
        )
        await db.execute(
            sa.text("INSERT INTO tenant (id, name) VALUES (:i,'T')"), {"i": str(tenant)}
        )
        await apply_workspace_scope(db, ws)
        await db.execute(
            sa.text(
                "INSERT INTO workspace (id, workspace_id, tenant_id, name, domain,"
                " website_url, domain_verified_at)"
                " VALUES (:i,:i,:t,'W',:d,:u, now())"
            ),
            {
                "i": str(ws),
                "t": str(tenant),
                "d": f"dw-{ws.hex[:8]}.om",
                "u": f"https://dw-{ws.hex[:8]}.om",
            },
        )
        run = uuid4()
        await db.execute(
            sa.text(
                "INSERT INTO research_run (id, workspace_id, state, requested_by_user_id)"
                " VALUES (:i,:w,'running',:u)"
            ),
            {"i": str(run), "w": str(ws), "u": str(user)},
        )
        await db.execute(
            sa.text(
                "INSERT INTO research_source (workspace_id, run_id, kind, state)"
                " VALUES (:w,:r,:k,'running')"
            ),
            {"w": str(ws), "r": str(run), "k": SourceKind.CRAWL.value},
        )
        await db.commit()

        try:
            # The run belongs to `ws`; this records it as some other workspace,
            # so RLS matches nothing — the shape a commit-ended GUC produces.
            with pytest.raises(worker_loop.DiscardedWriteError, match="matched 0"):
                await worker_loop._record(
                    db,
                    workspace_id=uuid4(),
                    run_id=run,
                    kind=SourceKind.CRAWL,
                    outcome=CrawlOutcome(state=SourceState.SKIPPED),
                )

            # And the source is untouched, which is the point: the write was
            # discarded, so the only honest states are "raised" and "unchanged".
            await db.rollback()
            await apply_workspace_scope(db, ws)
            state = (
                await db.execute(
                    sa.text("SELECT state FROM research_source WHERE run_id = :r"),
                    {"r": str(run)},
                )
            ).scalar_one()
            assert state == "running"
        finally:
            await apply_workspace_scope(db, ws)
            for statement in (
                "DELETE FROM research_source WHERE workspace_id = :w",
                "DELETE FROM research_run WHERE workspace_id = :w",
                "DELETE FROM workspace WHERE id = :w",
            ):
                await db.execute(sa.text(statement), {"w": str(ws)})
            await db.execute(sa.text("DELETE FROM app_user WHERE id = :u"), {"u": str(user)})
            await db.commit()


@requires_db
async def test_the_guard_fires_on_the_role_the_worker_actually_uses(app_db: None) -> None:
    """The half that was inert until migration 0039.

    `_research_job` passes a `jobs_session()`, so every guarded write runs as
    **`nexus_jobs`** in production. Migration 0021 had given that role
    `research_source_worker_write USING (true)`, and permissive policies OR — so
    the workspace GUC could not reduce a rowcount to zero and
    `DiscardedWriteError` could never be raised on the deployed path. The guard
    fired only in tests, which drive the app role, which is the most misleading
    place for a guard to work.

    0039 dropped those two blanket policies, leaving the PUBLIC
    `research_source_workspace_isolation` to govern every role. This asserts the
    consequence on the role that matters, so re-widening the policy fails here
    rather than silently restoring the blind spot.
    """
    assert jobs_database_url() is not None, (
        "NEXUS_JOBS_DATABASE_URL is not configured — the maintenance role is "
        "not optional since ADR 0018"
    )

    async with get_sessionmaker()() as setup:
        user, tenant, ws = uuid4(), uuid4(), uuid4()
        await setup.execute(
            sa.text("INSERT INTO app_user (id, email) VALUES (:i,:e)"),
            {"i": str(user), "e": f"jr-{user.hex[:8]}@example.com"},
        )
        await setup.execute(
            sa.text("INSERT INTO tenant (id, name) VALUES (:i,'T')"), {"i": str(tenant)}
        )
        await apply_workspace_scope(setup, ws)
        await setup.execute(
            sa.text(
                "INSERT INTO workspace (id, workspace_id, tenant_id, name, domain,"
                " website_url, domain_verified_at)"
                " VALUES (:i,:i,:t,'W',:d,:u, now())"
            ),
            {
                "i": str(ws),
                "t": str(tenant),
                "d": f"jr-{ws.hex[:8]}.om",
                "u": f"https://jr-{ws.hex[:8]}.om",
            },
        )
        run = uuid4()
        await setup.execute(
            sa.text(
                "INSERT INTO research_run (id, workspace_id, state, requested_by_user_id)"
                " VALUES (:i,:w,'running',:u)"
            ),
            {"i": str(run), "w": str(ws), "u": str(user)},
        )
        await setup.execute(
            sa.text(
                "INSERT INTO research_source (workspace_id, run_id, kind, state)"
                " VALUES (:w,:r,:k,'running')"
            ),
            {"w": str(ws), "r": str(run), "k": SourceKind.CRAWL.value},
        )
        await setup.commit()

        # The application's own factory, not an engine built here: this is the
        # exact session `_research_job` hands to `process_one_run`, so the test
        # cannot pass by connecting differently from production.
        async with jobs_session() as jobs:
            # As `nexus_jobs`, scoped to the wrong workspace — the state a lost
            # GUC leaves behind. Before 0039 this matched the row anyway and
            # returned quietly.
            with pytest.raises(worker_loop.DiscardedWriteError, match="matched 0"):
                await worker_loop._record(
                    jobs,
                    workspace_id=uuid4(),
                    run_id=run,
                    kind=SourceKind.CRAWL,
                    outcome=CrawlOutcome(state=SourceState.SKIPPED),
                )
            await jobs.rollback()

            # And the worker can still do its real job on this role: the same
            # write, correctly scoped, succeeds. Without this half, dropping the
            # grant entirely would also pass.
            await worker_loop._record(
                jobs,
                workspace_id=ws,
                run_id=run,
                kind=SourceKind.CRAWL,
                outcome=CrawlOutcome(state=SourceState.SKIPPED),
            )
            await jobs.commit()

        await apply_workspace_scope(setup, ws)
        state = (
            await setup.execute(
                sa.text("SELECT state FROM research_source WHERE run_id = :r"), {"r": str(run)}
            )
        ).scalar_one()
        assert state == "skipped", "the correctly scoped write must still land"

        for statement in (
            "DELETE FROM research_source WHERE workspace_id = :w",
            "DELETE FROM research_run WHERE workspace_id = :w",
            "DELETE FROM workspace WHERE id = :w",
        ):
            await setup.execute(sa.text(statement), {"w": str(ws)})
        await setup.execute(sa.text("DELETE FROM app_user WHERE id = :u"), {"u": str(user)})
        await setup.commit()


@requires_db
def test_the_worker_holds_no_blanket_policy_on_research_source() -> None:
    """The shape ADR 0050 chose, pinned against a quiet re-widening.

    A `USING (true)` policy for `nexus_jobs` beside the GUC-keyed isolation
    policy ORs with it, which is how the guard above came to be inert on the
    deployed path for a day. The privilege is a separate concern and must
    survive: revoking the GRANT would also make this pass, and would break the
    worker instead.
    """
    import sqlalchemy as sync_sa

    url = database_url()
    assert url is not None
    engine = sync_sa.create_engine(url, poolclass=sync_sa.pool.NullPool)
    try:
        with engine.connect() as c:
            policies = {
                (r.polname, r.using_expr)
                for r in c.execute(
                    sync_sa.text(
                        "SELECT polname, pg_get_expr(polqual, polrelid) AS using_expr"
                        "  FROM pg_policy p JOIN pg_class k ON k.oid = p.polrelid"
                        " WHERE k.relname = 'research_source'"
                    )
                )
            }
            assert not [p for p, expr in policies if (expr or "").strip() == "true"], (
                f"a blanket policy is back on research_source: {sorted(policies)}"
            )

            granted = set(
                c.execute(
                    sync_sa.text(
                        "SELECT privilege_type FROM information_schema.role_table_grants"
                        " WHERE grantee = 'nexus_jobs' AND table_name = 'research_source'"
                    )
                ).scalars()
            )
            assert {"SELECT", "UPDATE"} <= granted, (
                f"the worker lost a privilege it needs: has {sorted(granted)}"
            )
    finally:
        engine.dispose()
