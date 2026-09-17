"""The same tile, on two surfaces, saying the same thing.

`doc/14` step 7's acceptance test. Moving the measured tiles onto the common
surface changes **where** a founder reads a number and must not change **what**
it says — and the way that breaks is not a crash. It is two renderings of one
figure that agree today, drift when somebody edits one, and are individually
plausible on both screens.

`figure_out` and `narration_out` were closures inside the director handler. They
are module level now and shared, so the guarantee is structural rather than
maintained by attention; these tests are what would notice if a second copy
appeared.

Against a real database, because the figure comes from a crawl and the narration
from `generation`. A hermetic version of this file would assert that two calls
to the same function return the same value, which proves nothing about the
thing at risk.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine

from app.config import get_settings
from app.db import get_engine, get_sessionmaker
from app.domain.scopes import Department, Role
from app.domain.session import ScopedSession
from app.grounding.compute import MEASURABLE
from app.main import create_app
from tests.dburl import async_database_url, database_url

requires_db = pytest.mark.requires_db

SIGNALS: dict[str, Any] = {
    "url": "https://muscat-marine.om/",
    "title": "Muscat Marine — dry dock and vessel repair",
    "title_length": 43,
    "meta_description": "Dry dock, vessel repair and marine engineering in Oman.",
    "meta_description_length": 55,
    "h1_texts": ["Muscat Marine"],
    "h2_texts": ["Services", "Contact"],
    "word_count": 640,
    "is_https": True,
    "has_canonical": True,
    "canonical_url": "https://muscat-marine.om/",
    "has_structured_data": False,
    "declared_language": "en",
    "robots_blocks_indexing": False,
    "has_open_graph": False,
    "has_viewport_meta": True,
    "has_robots_meta": False,
    "image_count": 12,
    "images_with_alt": 3,
    "internal_link_count": 18,
    "external_link_count": 4,
    "script_count": 6,
    "stylesheet_count": 3,
    "inline_style_count": 1,
    "html_bytes": 41000,
    "emails": ["hello@muscat-marine.om"],
    "has_phone": True,
    "social_profiles": ["linkedin"],
}


@pytest.fixture
def engine() -> Iterator[Engine]:
    url = database_url()
    assert url is not None
    made = create_engine(url, future=True)
    yield made
    made.dispose()


@pytest.fixture
def app_db(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("NEXUS_DATABASE_URL", async_database_url() or "")
    monkeypatch.setenv("NEXUS_STORAGE_SIGNING_SECRET", "test-secret")
    for cache in (get_settings, get_engine, get_sessionmaker):
        cache.cache_clear()
    yield
    for cache in (get_settings, get_engine, get_sessionmaker):
        cache.cache_clear()


def set_workspace(conn: sa.Connection, workspace: UUID) -> None:
    conn.execute(
        sa.text("SELECT set_config('nexus.workspace_id', :w, true)"), {"w": str(workspace)}
    )


@pytest.fixture
def workspace(engine: Engine) -> Iterator[tuple[UUID, UUID]]:
    user, tenant, ws = uuid4(), uuid4(), uuid4()
    with engine.begin() as conn:
        conn.execute(
            sa.text("INSERT INTO app_user (id, email) VALUES (:i,:e)"),
            {"i": str(user), "e": f"tiles-{user.hex[:8]}@example.com"},
        )
        conn.execute(sa.text("INSERT INTO tenant (id, name) VALUES (:i,'T')"), {"i": str(tenant)})
        set_workspace(conn, ws)
        conn.execute(
            sa.text(
                "INSERT INTO workspace (id, workspace_id, tenant_id, name, domain)"
                " VALUES (:i,:i,:t,'W',:d)"
            ),
            {"i": str(ws), "t": str(tenant), "d": f"tiles-{ws.hex[:8]}.om"},
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
                # `ck_onboarding_session_completed_at` pairs the status with the
                # timestamp, the same shape as the prose/outcome constraint on
                # `generation`: a row claiming completion with no moment of
                # completion is a claim nothing can check.
                "INSERT INTO onboarding_session"
                " (workspace_id, user_id, status, phase, completed_at)"
                " VALUES (:w,:u,'completed','ready', now())"
            ),
            {"w": str(ws), "u": str(user)},
        )
        session_id = conn.execute(
            sa.text("SELECT id FROM onboarding_session WHERE workspace_id = :w"),
            {"w": str(ws)},
        ).scalar_one()
        conn.execute(
            sa.text(
                "INSERT INTO page_signals"
                " (workspace_id, captured_by, session_id, url, position, signals, captured_at)"
                " VALUES (:w,'onboarding',:s,:u,0, CAST(:sig AS jsonb), :at)"
            ),
            {
                "w": str(ws),
                "s": str(session_id),
                "u": SIGNALS["url"],
                "sig": json.dumps(SIGNALS),
                "at": datetime(2026, 9, 16, 9, 0, tzinfo=UTC),
            },
        )
    yield user, ws
    with engine.begin() as conn:
        set_workspace(conn, ws)
        for statement in (
            "DELETE FROM page_signals WHERE workspace_id = :w",
            "DELETE FROM onboarding_session WHERE workspace_id = :w",
            "DELETE FROM membership WHERE workspace_id = :w",
            "DELETE FROM workspace WHERE id = :w",
        ):
            conn.execute(sa.text(statement), {"w": str(ws)})
        conn.execute(sa.text("DELETE FROM app_user WHERE id = :u"), {"u": str(user)})


@pytest.fixture
def client(app_db: None, workspace: tuple[UUID, UUID]) -> Iterator[TestClient]:
    from app.deps import current_scope
    from app.routes.dashboards import answered_questions, running_departments

    user, ws = workspace
    app = create_app()
    app.dependency_overrides[current_scope] = lambda: ScopedSession(
        user_id=user,
        tenant_id=uuid4(),
        workspace_id=ws,
        role=Role.OWNER,
        departments=frozenset(Department),
    )
    app.dependency_overrides[running_departments] = lambda: frozenset(Department)
    app.dependency_overrides[answered_questions] = lambda: frozenset()
    with TestClient(app) as made:
        yield made
    app.dependency_overrides.clear()


def _director_blocks(client: TestClient) -> dict[str, Any]:
    body = client.get("/dashboards/marketing")
    assert body.status_code == 200, body.text
    return {
        block["key"]: block for section in body.json()["sections"] for block in section["blocks"]
    }


@requires_db
def test_the_surface_and_the_director_page_serve_the_same_figure(client: TestClient) -> None:
    """**The acceptance test.**

    Byte-identical, field for field. Two renderings that agree today and drift
    when somebody edits one is the failure this step can actually have, and both
    screens would look perfectly plausible while it happened.
    """
    surface = client.get("/dashboards/surface")
    assert surface.status_code == 200, surface.text
    measured = {block["key"]: block for block in surface.json()["measured"]}
    director = _director_blocks(client)

    assert measured, "nothing measured, so this test proves nothing"
    for key, block in measured.items():
        assert block["figure"] == director[key]["figure"], key
        assert block["narration"] == director[key]["narration"], key
        assert block["state"] == director[key]["state"], key
        assert block["unlock"] == director[key]["unlock"], key


@requires_db
def test_only_tiles_that_carry_a_figure_reach_the_surface(client: TestClient) -> None:
    """A capability that should compute and did not is already reported by the
    brief as `unmeasured`. An empty tile here would state the same absence twice,
    in a shape that looks like a figure."""
    measured = client.get("/dashboards/surface").json()["measured"]

    assert measured
    assert all(block["figure"] is not None for block in measured)


@requires_db
def test_the_figure_carries_its_denominator_and_its_page(client: TestClient) -> None:
    """A score with no denominator is a claim a reader cannot check, and one
    whose page cannot be opened is — to a reader — indistinguishable from a
    number we invented."""
    for block in client.get("/dashboards/surface").json()["measured"]:
        figure = block["figure"]
        assert figure["max_score"] > 0
        assert figure["source_url"].startswith("http")
        assert figure["measured_at"] == "2026-09-16"
        assert figure["checks"], "a figure with no checks cannot show its working"


@requires_db
def test_a_workspace_with_no_crawl_serves_no_tiles_rather_than_empty_ones(
    client: TestClient, engine: Engine, workspace: tuple[UUID, UUID]
) -> None:
    """I10 at the surface level. No crawl means nothing was looked at, and a
    zero-scored tile would say this company scored nothing."""
    _, ws = workspace
    with engine.begin() as conn:
        set_workspace(conn, ws)
        conn.execute(sa.text("DELETE FROM page_signals WHERE workspace_id = :w"), {"w": str(ws)})

    body = client.get("/dashboards/surface").json()

    assert body["measured"] == []
    assert body["brief"]["state"] == "not_measured"
    # Coverage is about the catalogue, not the crawl, so it does not move.
    # `len(MEASURABLE)`, not a literal. This read `2` — the size of `CRAWL_AUDITS`
    # — through two slices that added dispatches, and stayed green because the
    # route injected the same single dispatch into `coverage`. The constant was
    # restating the defect. This caller holds every department, so every
    # capability with a calculator is one it can see.
    assert body["coverage"]["measuring"] == len(MEASURABLE)
