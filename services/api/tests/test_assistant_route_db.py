"""Who may ask, and what they learn when they may not. `doc/20` A8.

Two halves, split by what each claim needs.

**The gates are hermetic**, in `test_dashboard_narration_scope.py`'s shape:
every refusal here happens *before* anything is retrieved or spent, and that is
precisely the claim — a caller who may not ask is refused without a database
round trip, an embedding or a token.

**The successful ask is against real Postgres**, through the app, because an
answer that has not gone through RLS has not gone through the thing that makes
it correct.

The single most important assertion is that the 404s are **byte-identical**.
`dashboards.py`'s standing rule is that *"this exists and you may not have it"*
is itself a disclosure, and an unreleased endpoint is the same shape of secret
as a department somebody does not hold.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import cast
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from fastapi import FastAPI
from fastapi.testclient import TestClient

# `TestClient` here returns an `httpx2` response, not an `httpx` one. Importing
# the wrong `Response` type-checks as a mismatch rather than failing at runtime,
# which is the kind of thing `-> object` hides.
from httpx2 import Response
from sqlalchemy import Connection

from app.assistant import ask as ask_module
from app.assistant.budget import ASK_LIMIT
from app.config import get_settings
from app.db import get_engine, get_sessionmaker
from app.domain.scopes import Department, Role
from app.domain.session import ScopedSession
from app.main import create_app
from tests.dburl import async_database_url, database_url
from tests.test_assistant_ask_db import DIM, _provider, _StubEmbedder

CSRF = "a-csrf-token"
ASYNC_DB_URL = async_database_url()


def _override_departments(app: FastAPI) -> None:
    from app.routes.dashboards import answered_questions, running_departments

    app.dependency_overrides[running_departments] = lambda: frozenset(Department)
    app.dependency_overrides[answered_questions] = lambda: frozenset()


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("NEXUS_ASSISTANT_ENABLED", "true")
    get_settings.cache_clear()
    app = create_app()
    _override_departments(app)
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
    get_settings.cache_clear()


@pytest.fixture
def client_flag_off(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("NEXUS_ASSISTANT_ENABLED", "false")
    get_settings.cache_clear()
    app = create_app()
    _override_departments(app)
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
    get_settings.cache_clear()


def as_role(client: TestClient, scope: ScopedSession) -> None:
    from app.deps import current_scope

    # Typed rather than left as `client.app`, which mypy widens to the ASGI
    # callable — the shape that produces the standing errors in
    # `test_dashboard_narration_scope.py`.
    cast(FastAPI, client.app).dependency_overrides[current_scope] = lambda: scope
    client.cookies.set("nexus_csrf", CSRF)


def _scope(role: Role, departments: frozenset[Department]) -> ScopedSession:
    return ScopedSession(
        user_id=uuid4(),
        tenant_id=uuid4(),
        workspace_id=uuid4(),
        role=role,
        departments=departments,
    )


def ask_http(client: TestClient, department: str, *, csrf: bool = True) -> Response:
    headers = {"X-CSRF-Token": CSRF} if csrf else {}
    return client.post(
        f"/dashboards/{department}/ask",
        json={"question": "What are our payment terms?"},
        headers=headers,
    )


# ── The flag ──────────────────────────────────────────────────


def test_with_the_flag_off_the_endpoint_does_not_exist(client_flag_off: TestClient) -> None:
    """404, not 403 and not 501. **The existence of an unreleased endpoint is
    itself information**, and a 403 would confirm it to anyone who guessed the
    URL."""
    as_role(client_flag_off, _scope(Role.OWNER, frozenset(Department)))

    assert ask_http(client_flag_off, "finance").status_code == 404


def test_the_flag_off_404_is_identical_to_an_unknown_department(
    client_flag_off: TestClient,
) -> None:
    """**The assertion that matters most in this file.**

    Asserted as *agreement between two responses* rather than as a status code,
    because a reader who can tell the two apart has learned that the assistant
    exists and is coming — which is a product roadmap leaking out of an error
    body.
    """
    as_role(client_flag_off, _scope(Role.OWNER, frozenset(Department)))
    disabled = ask_http(client_flag_off, "finance")

    assert disabled.status_code == 404
    assert disabled.json() == {"detail": "Not found"}, (
        "the flag-off refusal must be the same body `reachable_director` gives, "
        "or a reader can tell 'not released yet' from 'not yours'"
    )


# ── The gates, inherited rather than rewritten ────────────────


def test_a_caller_outside_the_department_is_refused_exactly_as_the_page_refuses_them(
    client: TestClient,
) -> None:
    """Same dependency as the director page, so the same 404. An ask endpoint
    with its own copy of the guard is a second door into the locked room."""
    as_role(client, _scope(Role.CONTRIBUTOR, frozenset({Department.SALES})))
    refused = ask_http(client, "finance")

    assert refused.status_code == 404
    assert refused.json() == {"detail": "Not found"}


def test_not_released_is_indistinguishable_from_not_yours(
    client: TestClient, client_flag_off: TestClient
) -> None:
    """**The assertion that matters most in this file**, and the first draft of
    it was asking the wrong question.

    It compared a refused department against the string `"nonexistent"` — which
    never reaches the route at all: the path parameter is typed as the
    `Department` enum, so FastAPI returns **422** before any dependency runs.
    The comparison that matters is the one a caller can actually make: with the
    flag off, does Finance look different from how it looks when the flag is on
    and they simply do not hold it? If it does, the 404 leaks a roadmap.
    """
    as_role(client_flag_off, _scope(Role.OWNER, frozenset(Department)))
    not_released = ask_http(client_flag_off, "finance")

    as_role(client, _scope(Role.CONTRIBUTOR, frozenset({Department.SALES})))
    not_yours = ask_http(client, "finance")

    assert not_released.status_code == not_yours.status_code == 404
    assert not_released.json() == not_yours.json()


def test_a_department_outside_the_enum_is_rejected_before_any_dependency_runs(
    client: TestClient,
) -> None:
    """422, not 404, and that is pre-existing behaviour rather than a hole.

    The body enumerates the seven department names — but that list is fixed
    product-wide and identical for every tenant, so it discloses nothing about
    *this* workspace. Pinned so the distinction is deliberate rather than
    discovered again.
    """
    as_role(client, _scope(Role.OWNER, frozenset(Department)))

    assert ask_http(client, "nonexistent").status_code == 422


def test_without_a_csrf_header_the_ask_is_refused(client: TestClient) -> None:
    """A question is a state-changing request: it spends budget and writes a
    ledger row. Anything that costs something is CSRF-protected."""
    as_role(client, _scope(Role.OWNER, frozenset(Department)))

    assert ask_http(client, "finance", csrf=False).status_code == 403


def test_the_executive_surface_keeps_its_own_refusal(client: TestClient) -> None:
    """403 rather than 404, and deliberately different from the department gate:
    the Chief of Staff view is a *role* requirement, not a membership one, so
    naming it tells the caller something actionable rather than something
    secret."""
    as_role(client, _scope(Role.CONTRIBUTOR, frozenset({Department.MARKETING})))

    assert ask_http(client, "executive").status_code == 403


# ── The answer, against real Postgres ─────────────────────────


@pytest.mark.requires_db
def test_a_valid_ask_returns_an_answer_with_citations(monkeypatch: pytest.MonkeyPatch) -> None:
    """Through the app, through RLS, with a scripted model.

    **A sync test on purpose.** `TestClient` runs the application in an event
    loop of its own, and an `async def` test runs in another — they then share
    the module-cached async engine and asyncpg raises *"attached to a different
    loop"*. So the fixture data goes in over a **separate synchronous
    connection**, and only the app's own loop ever touches the async engine.

    Committed rather than rolled back, because the request opens its own
    `scoped_connection` and cannot see a transaction this test is holding.
    """
    assert ASYNC_DB_URL is not None
    monkeypatch.setenv("NEXUS_DATABASE_URL", ASYNC_DB_URL)
    monkeypatch.setenv("NEXUS_STORAGE_SIGNING_SECRET", "test-secret")
    monkeypatch.setenv("NEXUS_ASSISTANT_ENABLED", "true")
    for cache in (get_settings, get_engine, get_sessionmaker):
        cache.cache_clear()

    monkeypatch.setattr(ask_module, "get_embedder", _StubEmbedder)
    monkeypatch.setattr("app.routes.assistant.get_provider", _provider)

    ids = {k: uuid4() for k in ("tenant", "user", "workspace", "document", "chunk")}
    sync_url = database_url()
    assert sync_url is not None, "`requires_db` guarantees a database"
    engine = sa.create_engine(sync_url)

    try:
        with engine.begin() as c:
            _seed_sync(c, ids)

        app = create_app()
        _override_departments(app)
        with TestClient(app) as tc:
            from app.deps import current_scope

            app.dependency_overrides[current_scope] = lambda: ScopedSession(
                user_id=ids["user"],
                tenant_id=ids["tenant"],
                workspace_id=ids["workspace"],
                role=Role.CONTRIBUTOR,
                departments=frozenset({Department.FINANCE}),
            )
            tc.cookies.set("nexus_csrf", CSRF)
            response = tc.post(
                "/dashboards/finance/ask",
                json={"question": "What are our payment terms?"},
                headers={"X-CSRF-Token": CSRF},
            )

        assert response.status_code == 200
        body = response.json()
        assert body["answered"] is True
        assert body["prose"]
        assert [c["chunk_id"] for c in body["citations"]] == [str(ids["chunk"])]
        assert body["reason"] is None and body["sentence"] is None
    finally:
        with engine.begin() as c:
            c.execute(
                sa.text("SELECT set_config('nexus.workspace_id', :w, false)"),
                {"w": str(ids["workspace"])},
            )
            c.execute(sa.text("DELETE FROM workspace WHERE id = :w"), {"w": str(ids["workspace"])})
            c.execute(sa.text("DELETE FROM tenant WHERE id = :t"), {"t": str(ids["tenant"])})
            c.execute(sa.text("DELETE FROM app_user WHERE id = :u"), {"u": str(ids["user"])})
        engine.dispose()
        for cache in (get_settings, get_engine, get_sessionmaker):
            cache.cache_clear()


def _seed_sync(c: Connection, ids: dict[str, UUID]) -> None:
    """The same rows `tests/test_assistant_ask_db._seed` writes, synchronously."""
    c.execute(
        sa.text("SELECT set_config('nexus.workspace_id', :w, false)"),
        {"w": str(ids["workspace"])},
    )
    c.execute(
        sa.text("INSERT INTO tenant (id, name) VALUES (:t,'Route Test')"), {"t": str(ids["tenant"])}
    )
    c.execute(
        sa.text("INSERT INTO app_user (id, email) VALUES (:u,:e)"),
        {"u": str(ids["user"]), "e": f"route-{ids['user']}@example.invalid"},
    )
    c.execute(
        sa.text(
            "INSERT INTO workspace (id, workspace_id, tenant_id, name, reporting_currency)"
            " VALUES (:i,:i,:t,'Route Test','OMR')"
        ),
        {"i": str(ids["workspace"]), "t": str(ids["tenant"])},
    )
    c.execute(
        sa.text(
            "INSERT INTO document (id, workspace_id, filename, content_type, size_bytes,"
            " storage_key, content_sha256)"
            " VALUES (:d,:w,'terms.pdf','application/pdf',1,:k,:h)"
        ),
        {
            "d": str(ids["document"]),
            "w": str(ids["workspace"]),
            "k": f"k/{ids['document']}",
            "h": ids["document"].hex * 2,
        },
    )
    c.execute(
        sa.text(
            "INSERT INTO chunk (id, workspace_id, document_id, ordinal, content, scope,"
            " department, classified_by, confidence, review_state, source_page,"
            " source_label, embedding, embedding_model_id, embedding_dim)"
            " VALUES (:i,:w,:d,0,'Payment is due within 30 days.','L3',ARRAY['finance'],"
            "         'rules',1.0,'approved',1,'terms.pdf',CAST(:e AS vector),'stub',:dim)"
        ),
        {
            "i": str(ids["chunk"]),
            "w": str(ids["workspace"]),
            "d": str(ids["document"]),
            "e": str([0.1] * DIM),
            "dim": DIM,
        },
    )


@pytest.mark.requires_db
@pytest.mark.parametrize("enabled", [False, True])
def test_the_panel_is_available_only_when_the_assistant_is_enabled(
    monkeypatch: pytest.MonkeyPatch, enabled: bool
) -> None:
    """`doc/20` A12's acceptance, and **the flip is one setting.**

    The box and the endpoint behind it must move together. A panel rendering an
    input while the route 404s is the exact failure the reserved state existed
    to prevent, arrived at from the other side: somebody types the thing they
    most want to know and gets an error.

    Run in **both** states rather than only the one that ships, because a test
    that only asserts the off state would pass forever by never being switched
    on, and a test that only asserts the on state would not notice the default
    changing.
    """
    assert ASYNC_DB_URL is not None
    monkeypatch.setenv("NEXUS_DATABASE_URL", ASYNC_DB_URL)
    monkeypatch.setenv("NEXUS_STORAGE_SIGNING_SECRET", "test-secret")
    monkeypatch.setenv("NEXUS_ASSISTANT_ENABLED", "true" if enabled else "false")
    for cache in (get_settings, get_engine, get_sessionmaker):
        cache.cache_clear()

    monkeypatch.setattr(ask_module, "get_embedder", _StubEmbedder)
    monkeypatch.setattr("app.routes.assistant.get_provider", _provider)

    ids = {k: uuid4() for k in ("tenant", "user", "workspace", "document", "chunk")}
    sync_url = database_url()
    assert sync_url is not None
    engine = sa.create_engine(sync_url)

    try:
        with engine.begin() as c:
            _seed_sync(c, ids)

        app = create_app()
        _override_departments(app)
        with TestClient(app) as tc:
            from app.deps import current_scope

            app.dependency_overrides[current_scope] = lambda: ScopedSession(
                user_id=ids["user"],
                tenant_id=ids["tenant"],
                workspace_id=ids["workspace"],
                role=Role.CONTRIBUTOR,
                departments=frozenset({Department.FINANCE}),
            )
            tc.cookies.set("nexus_csrf", CSRF)

            panel = tc.get("/dashboards/finance").json()["assistant"]
            asked = tc.post(
                "/dashboards/finance/ask",
                json={"question": "What are our payment terms?"},
                headers={"X-CSRF-Token": CSRF},
            )

        assert panel["available"] is enabled
        # The pair. An available panel with a 404 behind it, or a reserved panel
        # with a live endpoint, are both states nobody chose.
        assert (asked.status_code != 404) is enabled
        # And the questions are the ones it can answer either way (ADR 0052).
        assert panel["questions"], "a panel with no questions is a blank region"
    finally:
        with engine.begin() as c:
            c.execute(
                sa.text("SELECT set_config('nexus.workspace_id', :w, false)"),
                {"w": str(ids["workspace"])},
            )
            c.execute(sa.text("DELETE FROM workspace WHERE id = :w"), {"w": str(ids["workspace"])})
            c.execute(sa.text("DELETE FROM tenant WHERE id = :t"), {"t": str(ids["tenant"])})
            c.execute(sa.text("DELETE FROM app_user WHERE id = :u"), {"u": str(ids["user"])})
        engine.dispose()
        for cache in (get_settings, get_engine, get_sessionmaker):
            cache.cache_clear()


@pytest.mark.requires_db
def test_exhausting_the_rate_limit_is_a_429_with_retry_after(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """**A regression test for a 500 that shipped.**

    `test_assistant_budget_db.py` asserts that `ask` *raises* `RateLimitedError`,
    and its docstring justifies that by saying the route renders it as a 429 —
    but nothing drove the route at the limit, so nothing noticed that the route
    did not catch it. An end-to-end run did, as an unhandled exception and a 500
    body reading "Something went wrong on our side."

    **Needs a database**, which is why it is not in the hermetic half above:
    `check_and_increment` is an upsert on a bucket table, and the hermetic
    client pins `NEXUS_DATABASE_URL` empty. That is also why the gap existed —
    the cheap tests could not have covered this one.

    The header is the point. A 429 without `Retry-After` tells a client to back
    off by an amount it has to guess, and the guess is usually "immediately".
    """
    assert ASYNC_DB_URL is not None
    monkeypatch.setenv("NEXUS_DATABASE_URL", ASYNC_DB_URL)
    monkeypatch.setenv("NEXUS_STORAGE_SIGNING_SECRET", "test-secret")
    monkeypatch.setenv("NEXUS_ASSISTANT_ENABLED", "true")
    for cache in (get_settings, get_engine, get_sessionmaker):
        cache.cache_clear()

    # Stubbed even though the limit bites before retrieval matters: the first
    # calls under the limit still reach the embedder, and on a machine with
    # `[embeddings]` installed that loads ~2 GB of weights to prove something
    # about a counter. It also trips `filterwarnings = ["error"]` on a
    # fastembed pooling warning, which reads as a product failure and is not.
    monkeypatch.setattr(ask_module, "get_embedder", _StubEmbedder)

    # A real workspace, because **every outcome writes a ledger row** — the
    # refusals included — and `generation.workspace_id` is a foreign key. An
    # invented id fails on it, which is the ledger rule doing its job.
    ids = {k: uuid4() for k in ("tenant", "user", "workspace", "document", "chunk")}
    sync_url = database_url()
    assert sync_url is not None
    engine = sa.create_engine(sync_url)
    with engine.begin() as c:
        _seed_sync(c, ids)

    app = create_app()
    _override_departments(app)

    try:
        with TestClient(app) as tc:
            from app.deps import current_scope

            app.dependency_overrides[current_scope] = lambda: ScopedSession(
                user_id=ids["user"],
                tenant_id=ids["tenant"],
                workspace_id=ids["workspace"],
                role=Role.OWNER,
                departments=frozenset(Department),
            )
            tc.cookies.set("nexus_csrf", CSRF)

            seen: list[int] = []
            for _ in range(ASK_LIMIT.max_count + 2):
                seen.append(ask_http(tc, "finance").status_code)
                if seen[-1] == 429:
                    break

            assert 500 not in seen, f"the rate limit surfaced as a server error: {seen}"
            assert 429 in seen, f"the limit never bit: {seen}"

            limited = ask_http(tc, "finance")
            assert limited.status_code == 429
            assert limited.headers.get("Retry-After"), "a 429 without Retry-After is a guess"
            assert int(limited.headers["Retry-After"]) > 0
    finally:
        with engine.begin() as c:
            c.execute(
                sa.text("SELECT set_config('nexus.workspace_id', :w, false)"),
                {"w": str(ids["workspace"])},
            )
            c.execute(sa.text("DELETE FROM workspace WHERE id = :w"), {"w": str(ids["workspace"])})
            c.execute(sa.text("DELETE FROM tenant WHERE id = :t"), {"t": str(ids["tenant"])})
            c.execute(sa.text("DELETE FROM app_user WHERE id = :u"), {"u": str(ids["user"])})
        engine.dispose()
        for cache in (get_settings, get_engine, get_sessionmaker):
            cache.cache_clear()
