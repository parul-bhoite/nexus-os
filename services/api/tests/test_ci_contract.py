"""The contract CI must satisfy before any other test in this suite means anything.

Ninety-two tests in this suite need a real PostgreSQL. Until this file existed,
a run with no database configured reported **92 skipped, exit code 0** — green,
and proving nothing. Row-level security is a database behaviour: the twelve
tests in `test_tenant_isolation.py` are worthless unless they *execute*.

Two halves, and both are needed:

- **here** — a database must be configured, reachable, and migrated to head, and
  the application role must be unprivileged;
- **`conftest.py`** — the one place a `requires_db` test may be skipped, paired
  with a `pytest_sessionfinish` guard that fails the session if it ever fires.

`test_a_skipped_database_test_fails_the_run` proves that guard rather than
asserting it exists, because a guard nobody has watched fail is a decoration.
"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

import pytest
import sqlalchemy as sa
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine

from tests.dburl import database_url

pytest_plugins = ["pytester"]

API_ROOT = Path(__file__).resolve().parents[1]


def _pytest_ini() -> dict[str, Any]:
    """`[tool.pytest.ini_options]`, read from the file rather than the running config.

    Read from disk deliberately: `pytestconfig` reports the *effective* settings,
    which a command-line flag can supply. The point is that the repository
    configures this, so every invocation gets it.
    """
    raw = tomllib.loads((API_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    options: dict[str, Any] = raw["tool"]["pytest"]["ini_options"]
    return options


# ── A database must be configured ─────────────────────────────


def test_a_database_is_configured() -> None:
    """Unconditional, and it is meant to be.

    This is the test that fails when `NEXUS_DATABASE_URL` is unset — locally and
    in CI alike. There is no environment in which this suite may report green
    without a database, because there is no environment in which it proves
    isolation without one.
    """
    assert database_url() is not None, (
        "No database is configured, so 92 tests would skip and the run would "
        "still report green. Set NEXUS_DATABASE_URL (CI does this from the "
        "postgres service container) or put it in .env for local runs."
    )


@pytest.mark.requires_db
def test_the_database_is_reachable_as_an_unprivileged_role() -> None:
    """Reachable, and connected as a role that row-level security applies to.

    `test_tenant_isolation.py` asserts these two flags as well. It is repeated
    here because this is the file that says what CI must provide, and a CI job
    that bootstrapped the wrong role should fail on the contract rather than on
    a policy test twenty minutes later.
    """
    url = database_url()
    assert url is not None

    engine = create_engine(url, poolclass=sa.pool.NullPool)
    try:
        with engine.connect() as conn:
            row = conn.execute(
                sa.text(
                    "SELECT rolname, rolsuper, rolbypassrls "
                    "FROM pg_roles WHERE rolname = current_user"
                )
            ).one()
    finally:
        engine.dispose()

    assert row.rolsuper is False, (
        f"connected as {row.rolname}, which is a superuser — every RLS policy "
        "is inert and every isolation test would pass while proving nothing"
    )
    assert row.rolbypassrls is False, (
        f"connected as {row.rolname}, which has BYPASSRLS — same outcome. "
        "Neon's neondb_owner is such a role; the application must never use it."
    )


@pytest.mark.requires_db
def test_the_schema_is_migrated_to_head() -> None:
    """The database CI hands to the suite has had `alembic upgrade head` run on it.

    Without this, a job that bootstrapped the role but skipped the migration
    would fail in scattered, confusing ways instead of saying what went wrong.
    """
    heads = set(ScriptDirectory(str(API_ROOT / "migrations")).get_heads())

    url = database_url()
    assert url is not None
    engine = create_engine(url, poolclass=sa.pool.NullPool)
    try:
        with engine.connect() as conn:
            applied = {
                row[0] for row in conn.execute(sa.text("SELECT version_num FROM alembic_version"))
            }
    finally:
        engine.dispose()

    assert applied == heads, (
        f"the database is at {sorted(applied) or 'no revision'} but the "
        f"migrations on disk head at {sorted(heads)} — run alembic upgrade head"
    )


# ── A skipped database test must break the build ──────────────


def test_requires_db_is_a_registered_marker_and_markers_are_strict() -> None:
    """`requires_db` is a declared marker, and a typo in one is an error.

    Before this, `requires_db` was a local variable in nine modules holding a
    `skipif`. Misspelling it in a tenth would have silently applied nothing.
    """
    options = _pytest_ini()

    markers = options.get("markers", [])
    assert any(marker.startswith("requires_db") for marker in markers), (
        f"requires_db is not declared in [tool.pytest.ini_options] markers: {markers}"
    )

    addopts = options.get("addopts", "")
    assert "--strict-markers" in addopts, (
        "--strict-markers is not in addopts, so a misspelled marker would be "
        f"silently ignored: {addopts!r}"
    )


def test_a_skipped_database_test_fails_the_run(pytester: pytest.Pytester) -> None:
    """The guard in `conftest.py`, watched failing.

    Runs a throwaway suite containing one `requires_db` test that skips, with
    only the two guard hooks loaded, and asserts the run exits non-zero. This is
    the automated version of the manual demonstration: plant a skip, watch red.
    """
    pytester.makeini("[pytest]\nmarkers =\n    requires_db: needs a database\n")
    pytester.makeconftest(
        "import sys\n"
        f"sys.path.insert(0, {str(API_ROOT)!r})\n"
        "from tests.conftest import (  # noqa: F401\n"
        "    pytest_runtest_logreport,\n"
        "    pytest_sessionfinish,\n"
        ")\n"
    )
    pytester.makepyfile(
        "import pytest\n"
        "\n"
        "@pytest.mark.requires_db\n"
        "def test_pretends_there_is_no_database() -> None:\n"
        "    pytest.skip('no database')\n"
    )

    result = pytester.runpytest_subprocess("-q")

    assert result.ret != 0, (
        "a skipped requires_db test left the run green — the conftest guard is "
        "not doing its job, and 92 unproved tests could vanish from CI silently"
    )
    result.stderr.fnmatch_lines(["*requires_db test(s) were skipped*"])


@pytest.mark.requires_db
def test_the_jobs_role_can_write_page_signals() -> None:
    """Migration 0028's grant, proved rather than assumed.

    The grant sits inside an `IF EXISTS (SELECT 1 FROM pg_roles ...)` guard, so
    on a database where `db/bootstrap.sql` never created `nexus_jobs` it emits a
    `NOTICE` and silently does nothing. The failure then appears only when a
    background crawl runs, as `permission denied for table page_signals` inside
    `_run_source`'s deliberately broad Q56 `except` — which reaches the founder
    as *"This step did not finish"* and names nothing at all.

    So this asserts the privilege in the catalogue. It belongs in this file
    rather than beside the worker's tests for the same reason everything else
    here does: a missing grant is a property of the *deployment*, and CI is
    where a deployment fact has to fail.
    """
    from tests.dburl import jobs_database_url

    jobs_url = jobs_database_url()
    assert jobs_url is not None, (
        "NEXUS_JOBS_DATABASE_URL is not exported. ADR 0018 makes the role "
        "non-optional, so this asserts rather than skips."
    )

    engine = sa.create_engine(jobs_url, poolclass=sa.pool.NullPool)
    try:
        with engine.connect() as conn:
            granted = {
                row[0]
                for row in conn.execute(
                    sa.text(
                        "SELECT privilege_type FROM information_schema.table_privileges"
                        " WHERE table_name = 'page_signals' AND grantee = current_user"
                    )
                )
            }
    finally:
        engine.dispose()

    # SELECT to read back, INSERT to store a fresh crawl, UPDATE to supersede
    # the previous one. No DELETE, deliberately: superseded rows are the history
    # that explains why a figure moved.
    assert {"SELECT", "INSERT", "UPDATE"} <= granted, (
        f"nexus_jobs holds {sorted(granted)} on page_signals. The background "
        f"crawl will fail with `permission denied` inside a broad except that "
        f"names nothing — re-run migration 0028 against a database where the "
        f"role exists."
    )
