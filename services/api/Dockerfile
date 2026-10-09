# The API image. Also the worker image — same build, different command.
#
# One image rather than two because they are the same application: the worker
# runs the scheduler and (from P11) the research jobs, and building a second
# image from the same source is a second thing to keep in step with the first.
# `docker-compose.yml` gives them different commands and that is the whole
# difference.

FROM python:3.12-slim AS base

# `PYTHONDONTWRITEBYTECODE` because the filesystem is read-only in effect and
# `.pyc` files written at import are noise in the layer diff. `PYTHONUNBUFFERED`
# because a crash that loses the last buffered log line is a crash you cannot
# diagnose.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# `curl` is here for the healthcheck and nothing else. `libpq5` is asyncpg's
# runtime dependency; the `-dev` package is a build dependency and does not
# belong in the final image.
RUN apt-get update \
 && apt-get install -y --no-install-recommends curl libpq5 \
 && rm -rf /var/lib/apt/lists/*

# Dependencies before source, so a code change does not reinstall 72 packages.
#
# **`--require-hashes` against the lockfile** (finding #16). `pyproject.toml`
# states ranges — what the code *supports*. The lockfile states what CI ran and
# what this image contains, and they are different claims. An image resolved
# from ranges is an image nobody tested.
COPY requirements-dev.lock ./
RUN pip install --require-hashes -r requirements-dev.lock

COPY pyproject.toml ./
COPY app ./app
COPY migrations ./migrations
COPY alembic.ini ./
RUN pip install -e . --no-deps

# The optional Anthropic SDK (the `[ai]` extra). Base deps above install with
# `--no-deps`, so the vendor package is pulled here explicitly. It is imported
# lazily in `app/ai/anthropic_provider.py`; `NEXUS_ANTHROPIC_API_KEY` activates
# it at runtime (ADR 0011). Installed in a separate, non-hashed invocation on
# purpose — the lockfile above deliberately omits it.
RUN pip install "anthropic>=0.40"

# Declared runtime deps that are missing from requirements-dev.lock (finding #16
# lock drift): the image installs the lock with `--no-deps`, so anything the lock
# omits never lands. `cryptography` (connector credential sealing) and
# `defusedxml` (document XML parsing) are imported at startup, so their absence
# crash-loops the container. Their own transitive deps (cffi, pycparser) are
# already in the lock, so no core version is disturbed. `mcp` is also missing but
# is imported lazily (CRM connector sessions only), so it is left out here rather
# than force a pydantic/starlette bump into the image. The real fix is to
# regenerate requirements-dev.lock from pyproject; this unblocks the deploy.
RUN pip install "cryptography>=44.0" "defusedxml>=0.7"

# Non-root, and the directory is owned rather than merely writable: the app
# writes uploads and mail under /app when the filesystem drivers are in use.
RUN useradd --create-home --uid 10001 nexus \
 && mkdir -p /app/.storage /app/.mail \
 && chown -R nexus:nexus /app
USER nexus

EXPOSE 8000

# Hits `/health`, not `/health/ready`. Readiness reports the database, the
# object store and the optional models; a container that is *up* with its
# database briefly unreachable is healthy and should not be restarted into a
# loop. `depends_on` and the app's own retries handle that.
HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=3 \
  CMD curl -fsS http://127.0.0.1:8000/health || exit 1

# No `--reload`, no `--workers`. One process per container; the process manager
# is the orchestrator, not uvicorn.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
