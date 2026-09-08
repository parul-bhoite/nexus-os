"""FastAPI application entry point."""

from __future__ import annotations

import logging
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

from app.config import Env, get_settings
from app.db import get_engine, warm_pool
from app.health import router as health_router
from app.http_limits import BodySizeLimit
from app.jobs.scheduler import build_scheduler
from app.logging import configure_logging, get_logger, request_id_var
from app.routes.audit import router as audit_router
from app.routes.auth import router as auth_router
from app.routes.companies import router as companies_router
from app.routes.dashboards import router as dashboards_router
from app.routes.documents import router as documents_router
from app.routes.files import router as files_router
from app.routes.onboarding import router as onboarding_router
from app.routes.onboarding_agent import router as onboarding_agent_router
from app.routes.research import router as research_router
from app.routes.review import router as review_router
from app.routes.setup import router as setup_router
from app.routes.spine import router as spine_router

log = get_logger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(
        json_output=settings.env is not Env.local,
        level=logging.DEBUG if settings.debug else logging.INFO,
    )
    log.info("api.startup", env=settings.env.value, embedding_dim=settings.embedding_dim)

    # The maintenance role, checked here rather than in `Settings` (ADR 0018).
    #
    # Without it the process boots happily and then fails at the **first company
    # registration** — a 500 on the product's front door, from a variable
    # nothing had mentioned — because the duplicate-domain lookup runs as
    # `nexus_jobs`. ADR 0018 says refuse rather than fall back; this refuses
    # earlier, which is the same rule with a better error.
    #
    # In `lifespan` and not in the model validator because `Settings` is built
    # at import by tests and tooling, on machines whose `.env` legitimately has
    # a database and no jobs URL. A validator there stops the suite collecting;
    # this stops the *server* starting, which is the thing that actually needs
    # the role.
    if (
        settings.database_url.get_secret_value()
        and not settings.jobs_database_url.get_secret_value()
    ):
        raise RuntimeError(
            "NEXUS_DATABASE_URL is set but NEXUS_JOBS_DATABASE_URL is not. "
            "Company registration checks whether a domain is already claimed as "
            "the nexus_jobs role, because `workspace` is row-level secured and "
            "the application role cannot see another company's row (ADR 0018). "
            "Run db/bootstrap.sql to create the role, then set the second URL."
        )

    # Fill the pool before the first request rather than during it. A
    # connection costs ~7s to establish against a remote database, so without
    # this the slowest requests the application ever serves are the ones made
    # immediately after it starts — and it never raises, because a database
    # that is down must not stop `/health` from coming up to say so.
    await warm_pool()

    # **Off unless this process is the worker** (`NEXUS_RUN_SCHEDULER`).
    #
    # Every API process used to run every job. With one container that is merely
    # untidy; with three behind a proxy it is three copies of every sweep, and
    # because the jobs are idempotent rather than exclusive the symptom is
    # triple the load and no error anyone sees. `docker-compose.yml` turns it on
    # for the worker and off for the API, which is the whole difference between
    # the two containers.
    #
    # Still also conditional on a database: starting a sweep that cannot connect
    # would log a failure every hour.
    scheduler = None
    if settings.run_scheduler and settings.database_url.get_secret_value():
        scheduler = build_scheduler()
        scheduler.start()
        log.info("scheduler.started", jobs=[j.id for j in scheduler.get_jobs()])

    yield

    if scheduler is not None:
        scheduler.shutdown(wait=False)

    # Close the connection pool on the way out. The process previously exited
    # with its connections open and let the operating system reap them, which
    # on a serverless Postgres billed by connection-time is a cost, and in a
    # test is worse: the engine's transports were created on this loop, so
    # anything closing them afterwards does so on a loop that no longer exists
    # and Python reports an unraisable exception from `__del__`.
    #
    # Guarded on the cache being populated rather than on the setting, so a
    # process that never touched the database does not construct an engine
    # purely to dispose of it.
    if get_engine.cache_info().currsize:
        await get_engine().dispose()

    log.info("api.shutdown")


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="NEXUS OS API",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs" if settings.docs_enabled else None,
        redoc_url=None,
        openapi_url="/openapi.json" if settings.docs_enabled else None,
    )

    # Outermost of the two, so a body over the ceiling is refused before the
    # request id is minted and before anything reads it. `add_middleware`
    # inserts at the front of the user stack and the last one added runs
    # outermost, so this line must stay *below* `request_context` to sit above
    # it at runtime — which reads backwards and is why it is said out loud.
    #
    # A refusal from here therefore carries no `x-request-id`. That is the
    # trade: correlating a 413 matters less than not buffering the body that
    # earned it, and the log line above records the path and the size.
    app.add_middleware(BodySizeLimit)

    @app.middleware("http")
    async def request_context(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        """Attach a request id to every log line and response.

        Workspace and user are bound later by the auth dependency (M1) — never
        from a client-supplied header, per doc 06 §2.1.
        """
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex

        # On the scope as well as in the ContextVar, and the scope is the half
        # that matters for a failure. When `call_next` raises, the `finally`
        # below resets the ContextVar *before* Starlette's ServerErrorMiddleware
        # — which sits outside this middleware — invokes the exception handler,
        # so a handler reading the var sees nothing. `request.state` is backed by
        # the ASGI scope, which both share.
        #
        # The header is also never set on that path, because the line after
        # `call_next` is never reached. The exception handler sets it instead.
        request.state.request_id = request_id

        token = request_id_var.set(request_id)
        try:
            response = await call_next(request)
        finally:
            request_id_var.reset(token)
        response.headers["x-request-id"] = request_id
        return response

    @app.exception_handler(Exception)
    async def unhandled_exception(request: Request, exc: Exception) -> JSONResponse:
        """Return a correlatable 500 that gives nothing away.

        Two requirements pulling in opposite directions. The response must carry
        **enough** to find the log line — before this there was no handler at
        all, so a customer reporting "it broke" could only be matched to a log
        entry by timestamp. And it must carry **nothing else**: an error body is
        the one place a stack trace reaches an unauthenticated stranger, and in
        this product an exception message can name a customer's file, column or
        table. `exc` is therefore logged and never rendered.

        `exc_info` is passed explicitly so the traceback reaches the log through
        `format_exc_info`, which is the processor that would otherwise drop it.

        Registered for `Exception` only. FastAPI's own `HTTPException` keeps its
        handler, because this product's refusals are load-bearing — routing a
        deliberate 403 through a generic 500 would hide the thing the
        permission tests exist to prove.
        """
        # From the scope, not the ContextVar: see the note in `request_context`.
        # Generated as a last resort so that a 500 is always correlatable, even
        # if the failure happened before the middleware ran — and it is logged
        # with the same value, because a reference number that appears in no log
        # line is a reference to nothing.
        request_id = str(getattr(request.state, "request_id", "") or uuid.uuid4().hex)

        log.error(
            "request.unhandled_exception",
            request_id=request_id,
            method=request.method,
            path=request.url.path,
            exc_info=exc,
        )
        return JSONResponse(
            status_code=500,
            content={
                "detail": (
                    "Something went wrong on our side. Quote the request_id "
                    "below if you contact us."
                ),
                "request_id": request_id,
            },
            headers={"x-request-id": request_id},
        )

    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(companies_router)
    app.include_router(audit_router)
    app.include_router(onboarding_router)
    app.include_router(onboarding_agent_router)
    app.include_router(documents_router)
    app.include_router(files_router)
    app.include_router(research_router)
    app.include_router(review_router)
    app.include_router(setup_router)
    app.include_router(spine_router)
    app.include_router(dashboards_router)
    return app


app = create_app()
