"""Narration end to end, against Neon, through the application.

**This file is slice 2's acceptance test**, and the case it exists for is the
last one: a stored sentence must stop being served the moment the figure beside
it changes. Every other test in the slice can pass while that is broken, because
the staleness rule only fires when the query, the comparison and the recompute
are all wired together — which is exactly the seam a unit test cannot reach.

Driven with `ScriptedProvider` so it needs no API key, except where the point is
that no key is a supported state.

Two things here are deliberately awkward and both earn it:

**The committed row is re-read on a *new connection*.** `narrate` does not
commit and `ledger.record` does not commit; `scoped_connection`'s
`session.begin()` commits on clean exit, and the route relies on that. Reading
the row back on the same session would prove the INSERT ran, not that anybody
else will ever see it — the single most likely way this slice ships
broken-but-green.

**The figure is changed by superseding `page_signals` directly.** Re-crawling
through the application would be a second model call and a live fetch; what is
under test is the comparison, not the crawler.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy import Connection, Engine, create_engine

from app.main import create_app
from tests.dburl import async_database_url, database_url

ASYNC_DB_URL = async_database_url()
DB_URL = database_url()

if TYPE_CHECKING:
    from app.domain.session import ScopedSession

requires_db = pytest.mark.requires_db

CSRF = "a-csrf-token"
SENTENCE = "Most of the technical checks pass on the page we fetched."

SIGNALS: dict[str, Any] = {
    "url": "https://muscat-marine.om/",
    "is_https": True,
    "title": "Marine engine repair in Muscat",
    "title_length": 31,
    "meta_description": "Dry-dock maintenance for Omani fleets.",
    "meta_description_length": 38,
    "h1_texts": ["Marine engine repair"],
    "has_canonical": True,
    "declared_language": "en",
    "internal_link_count": 18,
    "word_count": 640,
}


@pytest.fixture(scope="module")
def engine() -> Iterator[Engine]:
    """A **sync** engine, deliberately.

    `TestClient` drives the app on an event loop of its own, and the app's
    async engine has its own pool bound to whichever loop first touched it.
    Seeding through that same async engine from a pytest-asyncio fixture puts
    two loops on one pool and produces `cannot perform operation: another
    operation is in progress` — the shape `test_onboarding_agent_e2e.py`
    records as an unraisable-warning artifact.

    So the fixtures speak psycopg2 and the application speaks asyncpg, and they
    never share a connection. `test_page_signals_isolation.py` and
    `test_tenant_isolation.py` already do this for the same reason.
    """
    assert DB_URL is not None
    eng = create_engine(DB_URL, poolclass=sa.pool.NullPool)
    yield eng
    eng.dispose()


def set_workspace(conn: Connection, workspace_id: UUID) -> None:
    conn.execute(
        sa.text("SELECT set_config('nexus.workspace_id', :w, true)"), {"w": str(workspace_id)}
    )


@pytest.fixture
def user_and_workspace(engine: Engine) -> Iterator[tuple[UUID, UUID]]:
    """A workspace, an owner, and one crawled page for Marketing to score."""
    user, tenant, ws, session = uuid4(), uuid4(), uuid4(), uuid4()

    with engine.begin() as conn:
        conn.execute(
            sa.text("INSERT INTO app_user (id, email) VALUES (:i,:e)"),
            {"i": str(user), "e": f"narr-e2e-{user.hex[:8]}@example.com"},
        )
        conn.execute(sa.text("INSERT INTO tenant (id, name) VALUES (:i,'T')"), {"i": str(tenant)})
        set_workspace(conn, ws)
        conn.execute(
            sa.text(
                "INSERT INTO workspace (id, workspace_id, tenant_id, name, domain)"
                " VALUES (:i,:i,:t,'W',:d)"
            ),
            {"i": str(ws), "t": str(tenant), "d": f"narr-{ws.hex[:8]}.om"},
        )
        conn.execute(
            sa.text(
                "INSERT INTO membership (workspace_id, user_id, role, departments)"
                " VALUES (:w,:u,'owner', ARRAY['marketing']::text[])"
            ),
            {"w": str(ws), "u": str(user)},
        )
        conn.execute(
            sa.text(
                "INSERT INTO onboarding_session"
                " (id, workspace_id, user_id, status, phase, domain)"
                " VALUES (:i,:w,:u,'active','analysing',:d)"
            ),
            {"i": str(session), "w": str(ws), "u": str(user), "d": f"narr-{ws.hex[:8]}.om"},
        )
        conn.execute(
            sa.text(
                "INSERT INTO page_signals"
                " (workspace_id, captured_by, session_id, url, position, signals)"
                " VALUES (:w,'onboarding',:s,:u,0, CAST(:sig AS jsonb))"
            ),
            {
                "w": str(ws),
                "s": str(session),
                "u": "https://muscat-marine.om/",
                "sig": json.dumps(SIGNALS),
            },
        )

    yield user, ws

    with engine.begin() as conn:
        set_workspace(conn, ws)
        for statement in (
            "DELETE FROM generation WHERE workspace_id = :w",
            "DELETE FROM page_signals WHERE workspace_id = :w",
            "DELETE FROM onboarding_session WHERE workspace_id = :w",
            "DELETE FROM membership WHERE workspace_id = :w",
            "DELETE FROM workspace WHERE id = :w",
        ):
            conn.execute(sa.text(statement), {"w": str(ws)})
        conn.execute(sa.text("DELETE FROM app_user WHERE id = :u"), {"u": str(user)})


def _scope(user: UUID, ws: UUID) -> ScopedSession:
    from app.domain.scopes import Department, Role
    from app.domain.session import ScopedSession

    return ScopedSession(
        user_id=user,
        tenant_id=uuid4(),
        workspace_id=ws,
        role=Role.OWNER,
        departments=frozenset(Department),
    )


@pytest.fixture
def provider() -> Any:
    from app.ai.providers import ScriptedProvider

    return ScriptedProvider({"narrate-metric": json.dumps({"sentence": SENTENCE})})


@pytest.fixture
def client(
    monkeypatch: pytest.MonkeyPatch,
    user_and_workspace: tuple[UUID, UUID],
    provider: Any,
) -> Iterator[TestClient]:
    """The real app against the real database, with identity and the provider
    substituted and nothing else.

    `running_departments` is overridden because the company has chosen no
    departments in this fixture and the point here is narration, not stage 4.
    """
    from app.config import get_settings
    from app.db import get_engine, get_sessionmaker
    from app.deps import current_scope
    from app.domain.scopes import Department
    from app.routes.dashboards import running_departments

    assert ASYNC_DB_URL is not None
    monkeypatch.setenv("NEXUS_DATABASE_URL", ASYNC_DB_URL)
    monkeypatch.setenv("NEXUS_STORAGE_SIGNING_SECRET", "test-secret")
    for cache in (get_settings, get_engine, get_sessionmaker):
        cache.cache_clear()

    user, ws = user_and_workspace
    app = create_app()
    app.dependency_overrides[current_scope] = lambda: _scope(user, ws)
    app.dependency_overrides[running_departments] = lambda: frozenset(Department)
    # **Monkeypatched, not dependency-overridden.** `narrate_block` calls
    # `get_provider()` directly rather than through `Depends`, matching the one
    # other production construction site in `routes/onboarding_agent.py`. A
    # `dependency_overrides` entry is therefore inert: FastAPI only intercepts
    # what it resolves, and the first version of this fixture used one, got the
    # real `UnavailableProvider` and failed with `model_unavailable`.
    monkeypatch.setattr("app.routes.dashboards.get_provider", lambda: provider)

    with TestClient(app) as c:
        c.cookies.set("nexus_csrf", CSRF)
        yield c

    app.dependency_overrides.clear()
    for cache in (get_settings, get_engine, get_sessionmaker):
        cache.cache_clear()


def narrate(client: TestClient, key: str = "marketing.seo_gaps") -> Any:
    return client.post(
        "/dashboards/marketing/narrate", json={"key": key}, headers={"X-CSRF-Token": CSRF}
    )


def block(client: TestClient, key: str = "marketing.seo_gaps") -> Any:
    payload = client.get("/dashboards/marketing").json()
    for section in payload["sections"]:
        for candidate in section["blocks"]:
            if candidate["key"] == key:
                return candidate
    raise AssertionError(f"{key} is not on the Marketing rail")


# ── The whole path ────────────────────────────────────────────


@requires_db
def test_a_narration_is_written_and_then_served_on_the_dashboard(client: TestClient) -> None:
    """The happy path, both halves.

    The POST returns the sentence it just wrote; the GET serves the same
    sentence on the next page load, which is the entire reason there is a
    column for it.
    """
    posted = narrate(client)

    assert posted.status_code == 200
    body = posted.json()
    assert body["outcome"] == "answered"
    assert body["narration"]["prose"] == SENTENCE
    assert body["generation_id"]
    assert body["measured_at"]

    served = block(client)
    assert served["narration"]["prose"] == SENTENCE
    assert served["figure"]["score"] > 0, "the sentence must arrive beside its figure"


@requires_db
def test_the_row_is_committed_and_not_merely_inserted(
    client: TestClient, engine: Engine, user_and_workspace: tuple[UUID, UUID]
) -> None:
    """**Re-read on a new connection, deliberately.**

    `narrate` does not commit and `ledger.record` does not commit — both say so
    and both mean it. The route relies on `scoped_connection`'s `session.begin()`
    committing on clean exit. Asserting the row on the same session would prove
    an INSERT happened, not that anybody else will ever see it, which is the
    likeliest way this ships broken-but-green.
    """
    narrate(client)
    _, ws = user_and_workspace

    # A **different connection, and a different driver**. Reading it back on
    # the app's own session would prove an INSERT happened, not that it is
    # visible to anybody else.
    with engine.begin() as conn:
        set_workspace(conn, ws)
        row = conn.execute(
            sa.text(
                "SELECT prose, outcome, module, input_tokens FROM generation"
                " WHERE workspace_id = :w"
            ),
            {"w": str(ws)},
        ).one()

    assert row.prose == SENTENCE
    assert row.outcome == "answered"
    assert row.module == "marketing.seo_gaps"


# ── The rule this slice exists for ────────────────────────────


@requires_db
def test_a_sentence_stops_being_served_when_the_figure_changes(
    client: TestClient, engine: Engine, user_and_workspace: tuple[UUID, UUID]
) -> None:
    """**The acceptance test.**

    Narrate, then re-crawl to a different score, then reload. The figure must
    be the new one and the sentence must be **gone** — not shown with a warning,
    not greyed out. Prose written about 45 out of 65 rendered beside a fresh 39
    out of 65 is the worst failure this product can have: both halves
    individually true, nothing on screen saying they describe different
    measurements, and a reader who would act on it.

    Every other test in the slice can pass while this is broken.
    """
    narrate(client)
    before = block(client)
    assert before["narration"]["prose"] == SENTENCE

    _, ws = user_and_workspace
    with engine.begin() as conn:
        set_workspace(conn, ws)
        session_id = conn.execute(
            sa.text("SELECT id FROM onboarding_session WHERE workspace_id = :w"),
            {"w": str(ws)},
        ).scalar_one()
        conn.execute(
            sa.text(
                "UPDATE page_signals SET superseded_at = now()"
                " WHERE workspace_id = :w AND superseded_at IS NULL"
            ),
            {"w": str(ws)},
        )
        # A worse page: no canonical, no description, no declared language — a
        # different score for the same capability on the same URL, which is the
        # case `describes` has to catch on `numerator` alone.
        worse = dict(
            SIGNALS,
            has_canonical=False,
            meta_description=None,
            meta_description_length=0,
            declared_language=None,
        )
        conn.execute(
            sa.text(
                "INSERT INTO page_signals"
                " (workspace_id, captured_by, session_id, url, position, signals)"
                " VALUES (:w,'onboarding',:s,:u,0, CAST(:sig AS jsonb))"
            ),
            {
                "w": str(ws),
                "s": str(session_id),
                "u": "https://muscat-marine.om/",
                "sig": json.dumps(worse),
            },
        )

    after = block(client)

    assert after["figure"]["score"] != before["figure"]["score"], (
        "the fixture did not actually change the figure, so this proves nothing"
    )
    assert after["narration"] is None, (
        "a sentence written about the previous score is still being served beside "
        "the new one — the exact failure this slice exists to prevent"
    )


@requires_db
def test_a_refusal_does_not_resurrect_on_the_next_page_load(
    client: TestClient, provider: Any
) -> None:
    """`outcome = 'answered'` is in the reader's `WHERE`, not filtered after.

    Without it, a founder who hit an exhausted budget yesterday opens the
    dashboard today and reads that their allowance is spent — hours after it
    reset. A refusal belongs to the attempt somebody just made.
    """
    from app.ai.contracts import LlmUnavailableError

    async def refuse(_request: object) -> object:
        raise LlmUnavailableError("no model here")

    provider.complete = refuse

    posted = narrate(client)
    assert posted.json()["outcome"] == "unavailable"

    assert block(client)["narration"] is None


# ── ADR 0011: no key is a supported state ─────────────────────


@requires_db
def test_with_no_model_configured_the_tile_says_so_and_the_row_is_still_written(
    client: TestClient, provider: Any
) -> None:
    """A 200 carrying a named reason, not a 503.

    `narrate` catches `LlmUnavailableError`, maps it to `MODEL_UNAVAILABLE` and
    **still writes the row** — with zero tokens, which is what proves migration
    0029's CHECK permits a refusal with no prose. The figure beside it was
    computed without a model and is unaffected, and the copy says so.
    """
    from app.ai.contracts import LlmUnavailableError

    async def refuse(_request: object) -> object:
        raise LlmUnavailableError("no language model is configured")

    provider.complete = refuse

    response = narrate(client)

    assert response.status_code == 200
    body = response.json()
    assert body["outcome"] == "unavailable"
    assert body["reason"] == "model_unavailable"
    assert body["narration"] is None
    assert body["generation_id"], "the refusal is recorded, not swallowed"
    for word in ("error", "failed", "broken"):
        assert word not in body["message"].lower(), body["message"]


@requires_db
def test_a_refusal_is_recorded_with_no_tokens_and_no_prose(
    client: TestClient, engine: Engine, user_and_workspace: tuple[UUID, UUID], provider: Any
) -> None:
    from app.ai.contracts import LlmUnavailableError

    async def refuse(_request: object) -> object:
        raise LlmUnavailableError("no language model is configured")

    provider.complete = refuse
    narrate(client)
    _, ws = user_and_workspace

    with engine.begin() as conn:
        set_workspace(conn, ws)
        row = conn.execute(
            sa.text(
                "SELECT prose, outcome, unavailable_reason, input_tokens, output_tokens"
                " FROM generation WHERE workspace_id = :w"
            ),
            {"w": str(ws)},
        ).one()

    assert row.prose == ""
    assert row.outcome == "unavailable"
    assert row.unavailable_reason == "model_unavailable"
    assert row.input_tokens == 0
    assert row.output_tokens == 0


# ── Isolation, on the display path ────────────────────────────


@requires_db
def test_another_workspaces_sentence_never_reaches_this_dashboard(
    client: TestClient, engine: Engine
) -> None:
    """The read-back is workspace-wide by design — no `scope_key` filter, because
    an Owner's key and a manager's differ for the same tile. Workspace-wide is
    not tenant-wide, and this is the line that proves it."""
    other = uuid4()
    tenant = uuid4()

    with engine.begin() as conn:
        conn.execute(
            sa.text("INSERT INTO tenant (id, name) VALUES (:i,'Other')"), {"i": str(tenant)}
        )
        set_workspace(conn, other)
        conn.execute(
            sa.text(
                "INSERT INTO workspace (id, workspace_id, tenant_id, name, domain)"
                " VALUES (:i,:i,:t,'Other',:d)"
            ),
            {"i": str(other), "t": str(tenant), "d": f"other-{other.hex[:8]}.om"},
        )
        conn.execute(
            sa.text(
                "INSERT INTO generation"
                " (workspace_id, module, prompt_version, input_snapshot, calculation_trace,"
                "  scope_key, outcome, unavailable_reason, prose, cost_micros)"
                " VALUES (:w,'marketing.seo_gaps','1', CAST('{}' AS json), CAST('{}' AS json),"
                "  'L2','answered','','Belongs to somebody else entirely.',0)"
            ),
            {"w": str(other)},
        )

    try:
        assert block(client)["narration"] is None
    finally:
        with engine.begin() as conn:
            set_workspace(conn, other)
            conn.execute(
                sa.text("DELETE FROM generation WHERE workspace_id = :w"), {"w": str(other)}
            )
            conn.execute(sa.text("DELETE FROM workspace WHERE id = :w"), {"w": str(other)})


# ── The figure is never a model's business ────────────────────


@requires_db
def test_the_figure_is_identical_whether_or_not_a_sentence_exists(
    client: TestClient,
) -> None:
    """I1, seen from the endpoint. Narrating must change the prose on a tile
    and nothing else — a model that could move a figure by explaining it would
    be the whole product's central claim undone."""
    before = block(client)["figure"]
    narrate(client)
    after = block(client)["figure"]

    assert after == before
