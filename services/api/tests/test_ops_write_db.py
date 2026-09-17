"""Recording work, and the isolation a write surface needs.

`doc/15` S10.1's acceptance test. **This is the first place a customer writes into
NEXUS**, and a write surface fails differently from a read one: a read that
escapes its workspace shows somebody another company's data, while a write that
escapes *puts* data in another company — and the victim has no reason to doubt
it, because it appears in their own board alongside their own records.

`nexus_app` is `NOBYPASSRLS`, so an unscoped statement returns **zero rows rather
than an error** (CLAUDE.md). That is what makes these worth running against a
real Postgres: a hermetic version would assert a predicate string and prove
nothing about the policy.

Against Neon, with the sync-SQLAlchemy fixtures `test_surface_tiles.py` uses.
"""

from __future__ import annotations

from collections.abc import Iterator
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from httpx2 import Response
from sqlalchemy import Engine, create_engine

from app.config import get_settings
from app.db import get_engine, get_sessionmaker
from app.domain.scopes import Department, Role
from app.domain.session import ScopedSession
from app.main import create_app
from tests.dburl import async_database_url, database_url

requires_db = pytest.mark.requires_db
CSRF = "a-csrf-token"


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


def _workspace(conn: sa.Connection) -> tuple[UUID, UUID]:
    user, tenant, ws = uuid4(), uuid4(), uuid4()
    conn.execute(
        sa.text("INSERT INTO app_user (id, email) VALUES (:i,:e)"),
        {"i": str(user), "e": f"ops-{user.hex[:8]}@example.com"},
    )
    conn.execute(sa.text("INSERT INTO tenant (id, name) VALUES (:i,'T')"), {"i": str(tenant)})
    conn.execute(sa.text("SELECT set_config('nexus.workspace_id', :w, true)"), {"w": str(ws)})
    conn.execute(
        sa.text(
            "INSERT INTO workspace (id, workspace_id, tenant_id, name, domain)"
            " VALUES (:i,:i,:t,'W',:d)"
        ),
        {"i": str(ws), "t": str(tenant), "d": f"ops-{ws.hex[:8]}.om"},
    )
    conn.execute(
        sa.text(
            "INSERT INTO membership (workspace_id, user_id, role, departments)"
            " VALUES (:w,:u,'owner', ARRAY['operations']::text[])"
        ),
        {"w": str(ws), "u": str(user)},
    )
    return user, ws


@pytest.fixture
def two_workspaces(engine: Engine) -> Iterator[tuple[tuple[UUID, UUID], tuple[UUID, UUID]]]:
    with engine.begin() as conn:
        first = _workspace(conn)
    with engine.begin() as conn:
        second = _workspace(conn)
    yield first, second
    for user, ws in (first, second):
        with engine.begin() as conn:
            conn.execute(
                sa.text("SELECT set_config('nexus.workspace_id', :w, true)"), {"w": str(ws)}
            )
            for statement in (
                "DELETE FROM ops_completeness WHERE workspace_id = :w",
                "DELETE FROM ops_dispatch WHERE workspace_id = :w",
                "DELETE FROM ops_issue WHERE workspace_id = :w",
                "DELETE FROM ops_milestone WHERE workspace_id = :w",
                "DELETE FROM ops_task WHERE workspace_id = :w",
                "DELETE FROM ops_project WHERE workspace_id = :w",
                "DELETE FROM membership WHERE workspace_id = :w",
                "DELETE FROM workspace WHERE id = :w",
            ):
                conn.execute(sa.text(statement), {"w": str(ws)})
            conn.execute(sa.text("DELETE FROM app_user WHERE id = :u"), {"u": str(user)})


@pytest.fixture
def client(app_db: None) -> Iterator[TestClient]:
    app = create_app()
    with TestClient(app) as made:
        yield made
    app.dependency_overrides.clear()


def as_member(client: TestClient, who: tuple[UUID, UUID], role: Role = Role.OWNER) -> None:
    from app.deps import current_scope

    user, ws = who
    scope = ScopedSession(
        user_id=user,
        tenant_id=uuid4(),
        workspace_id=ws,
        role=role,
        departments=frozenset() if role is Role.VIEWER else frozenset({Department.OPERATIONS}),
    )
    # Still needed: `TestClient.app` is typed as the ASGI callable, which has no
    # `dependency_overrides`. Unlike the `.json()`/`.status_code` ignores this
    # replaced, that one is a real gap in Starlette's types rather than a helper
    # of ours returning `object`.
    client.app.dependency_overrides[current_scope] = lambda: scope  # type: ignore[attr-defined]
    client.cookies.set("nexus_csrf", CSRF)


def _post(client: TestClient, path: str, body: dict[str, object]) -> Response:
    """`Response`, not `object`.

    From `httpx2`, which is what Starlette's `TestClient` actually returns —
    `httpx.Response` is a different class here and mypy says so.

    Typed as `object` when this file was written, which made every `.json()` and
    `.status_code` below need a `# type: ignore[attr-defined]` — eleven of them,
    each hiding the same thing, and each also able to hide a real mistake at the
    same call site. `mypy app tests` only surfaced it when S10.2's tests pushed
    the count past where it had been noticed.
    """
    return client.post(path, json=body, headers={"X-CSRF-Token": CSRF})


# ── Recording, and reading back ───────────────────────────────


@requires_db
def test_a_project_and_a_task_are_recorded_and_read_back(
    client: TestClient, two_workspaces: tuple[tuple[UUID, UUID], tuple[UUID, UUID]]
) -> None:
    """`doc/15` S10.1's acceptance: a founder records work through the app and
    the tiles have something to count."""
    mine, _ = two_workspaces
    as_member(client, mine)

    project = _post(client, "/ops/projects", {"name": "Sohar fit-out", "status": "active"})
    assert project.status_code == 201, project.text
    project_id = project.json()["id"]

    task = _post(
        client,
        "/ops/tasks",
        {"title": "Order the steel", "project_id": project_id, "due_on": "2026-09-01"},
    )
    assert task.status_code == 201, task.text

    body = client.get("/ops").json()
    assert [p["name"] for p in body["projects"]] == ["Sohar fit-out"]
    assert [t["title"] for t in body["tasks"]] == ["Order the steel"]
    assert body["recorded_at"], "a recorded workspace must carry a date"


@requires_db
def test_a_workspace_that_has_recorded_nothing_says_so(
    client: TestClient, two_workspaces: tuple[tuple[UUID, UUID], tuple[UUID, UUID]]
) -> None:
    """**Not an empty board.** Never having used the layer leaves the tiles
    `locked`; having used it and closed everything is a different state, and
    `recorded_at` is what tells them apart."""
    mine, _ = two_workspaces
    as_member(client, mine)

    body = client.get("/ops").json()

    # Asserted as a property, not as a literal dict. It was the literal, and it
    # broke twice for entirely correct changes — S10.2 adding `completeness` and
    # S10.3 adding `milestones` and `issues` — with three more record types to
    # come in S10.5. A test that has to be edited every time the payload grows
    # correctly costs more than the stray field it was catching.
    assert body["recorded_at"] == "", "a date on a workspace that recorded nothing"
    assert body.keys() >= {"projects", "tasks", "milestones", "issues", "dispatches"}

    # Every collection empty. Written as "every list", not "every value except
    # `recorded_at`", which is what it said until S10.4 added a scalar and broke
    # it for the third time — the payload keeps growing correctly and the test
    # has to stop guessing at its shape.
    assert all(value == [] for value in body.values() if isinstance(value, list)), body

    # And nothing set. `grace_days` is `None` rather than `0` on a fresh
    # workspace, which is D32's whole point: a default would be a threshold we
    # chose, and `on_time_dispatch` refuses until somebody sets one (ADR 0036).
    assert body["grace_days"] is None


@requires_db
def test_a_task_needs_no_project(
    client: TestClient, two_workspaces: tuple[tuple[UUID, UUID], tuple[UUID, UUID]]
) -> None:
    """ "Call the supplier" is work without being a project. Requiring one would
    make somebody invent a project to record a task — and an invented project
    then counts on the board."""
    mine, _ = two_workspaces
    as_member(client, mine)

    assert _post(client, "/ops/tasks", {"title": "Call the supplier"}).status_code == 201


# ── Isolation, which is what a write surface gets wrong ───────


@requires_db
def test_another_workspaces_records_are_invisible(
    client: TestClient, two_workspaces: tuple[tuple[UUID, UUID], tuple[UUID, UUID]]
) -> None:
    mine, theirs = two_workspaces
    as_member(client, mine)
    _post(client, "/ops/projects", {"name": "Mine"})

    as_member(client, theirs)
    body = client.get("/ops").json()

    assert body["projects"] == []


@requires_db
def test_a_task_cannot_be_attached_to_another_workspaces_project(
    client: TestClient, two_workspaces: tuple[tuple[UUID, UUID], tuple[UUID, UUID]]
) -> None:
    """**The failure a write surface has that a read one does not.**

    Succeeding here would put a task in another company's project — and the
    victim has no reason to doubt it, because it appears on their own board
    beside their own records. RLS hides the parent row, so without this check the
    insert fails as a foreign-key error naming a constraint; with it, a 404
    naming the project.
    """
    mine, theirs = two_workspaces
    as_member(client, mine)
    project_id = _post(client, "/ops/projects", {"name": "Mine"}).json()["id"]

    as_member(client, theirs)
    response = _post(client, "/ops/tasks", {"title": "Sneak", "project_id": project_id})

    assert response.status_code == 404


@requires_db
def test_archiving_another_workspaces_project_changes_nothing(
    client: TestClient, two_workspaces: tuple[tuple[UUID, UUID], tuple[UUID, UUID]]
) -> None:
    """The delete is idempotent and scoped, so this is a no-op rather than a
    refusal — and the row must survive. An unscoped `UPDATE` would silently
    archive somebody else's project and return 204 either way, which is exactly
    the shape `nexus_app` being NOBYPASSRLS protects against."""
    mine, theirs = two_workspaces
    as_member(client, mine)
    project_id = _post(client, "/ops/projects", {"name": "Mine"}).json()["id"]

    as_member(client, theirs)
    client.delete(f"/ops/projects/{project_id}", headers={"X-CSRF-Token": CSRF})

    as_member(client, mine)
    assert [p["name"] for p in client.get("/ops").json()["projects"]] == ["Mine"]


@requires_db
def test_an_archived_project_stops_counting_without_being_deleted(
    client: TestClient,
    engine: Engine,
    two_workspaces: tuple[tuple[UUID, UUID], tuple[UUID, UUID]],
) -> None:
    """Archive, not delete: a founder who put something away by accident has a
    way back, and the row keeps its tasks' history."""
    mine, _ = two_workspaces
    as_member(client, mine)
    project_id = _post(client, "/ops/projects", {"name": "Put away"}).json()["id"]

    client.delete(f"/ops/projects/{project_id}", headers={"X-CSRF-Token": CSRF})

    assert client.get("/ops").json()["projects"] == []
    with engine.begin() as conn:
        conn.execute(
            sa.text("SELECT set_config('nexus.workspace_id', :w, true)"), {"w": str(mine[1])}
        )
        row = conn.execute(
            sa.text("SELECT archived_at FROM ops_project WHERE id = :p"), {"p": project_id}
        ).one()
    assert row.archived_at is not None


# ── Who may write ─────────────────────────────────────────────


@requires_db
def test_a_viewer_may_not_record_work(
    client: TestClient, two_workspaces: tuple[tuple[UUID, UUID], tuple[UUID, UUID]]
) -> None:
    """Doc 06 §2.3 gives a Viewer company-wide material and no department.
    Writing is not reading."""
    mine, _ = two_workspaces
    as_member(client, mine, Role.VIEWER)

    assert _post(client, "/ops/projects", {"name": "No"}).status_code == 403


@requires_db
def test_a_contributor_may_record_work(
    client: TestClient, two_workspaces: tuple[tuple[UUID, UUID], tuple[UUID, UUID]]
) -> None:
    """**Deliberately wider than `/connections`.** Connecting a tool grants a read
    of the whole company's data; recording a task is the work itself. A layer only
    managers could write to is a layer nobody uses — and this source fails on
    adoption."""
    mine, _ = two_workspaces
    as_member(client, mine, Role.CONTRIBUTOR)

    assert _post(client, "/ops/projects", {"name": "Mine to do"}).status_code == 201


@requires_db
def test_recording_needs_csrf(
    client: TestClient, two_workspaces: tuple[tuple[UUID, UUID], tuple[UUID, UUID]]
) -> None:
    mine, _ = two_workspaces
    as_member(client, mine)

    assert client.post("/ops/projects", json={"name": "No"}).status_code == 403


@requires_db
def test_an_unknown_status_is_refused_at_the_edge(
    client: TestClient, two_workspaces: tuple[tuple[UUID, UUID], tuple[UUID, UUID]]
) -> None:
    """Postgres would reject it too — as an IntegrityError reaching the client as
    a 500 naming a constraint. The same refusal at the edge names the field and
    what it accepts."""
    mine, _ = two_workspaces
    as_member(client, mine)

    response = _post(client, "/ops/projects", {"name": "X", "status": "nearly"})

    assert response.status_code == 422
    assert "planned" in response.json()["detail"]


# ── Completeness — `doc/15` S10.2, ADR 0035 (D29) ─────────────


@requires_db
def test_confirming_completeness_is_recorded_and_read_back(
    client: TestClient, two_workspaces: tuple[tuple[UUID, UUID], tuple[UUID, UUID]]
) -> None:
    """**The one fact the database cannot hold about itself.** Every project row
    is evidence a project exists; nothing in the table is evidence that no other
    project does."""
    mine, _ = two_workspaces
    as_member(client, mine)
    _post(client, "/ops/projects", {"name": "Muscat fit-out", "status": "active"})

    response = _post(client, "/ops/completeness", {"entity": "projects"})
    assert response.status_code == 201, response.text
    assert response.json()["entity"] == "projects"

    body = client.get("/ops").json()
    assert [entry["entity"] for entry in body["completeness"]] == ["projects"]
    assert body["completeness"][0]["complete_as_of"]


@requires_db
def test_confirming_one_entity_does_not_vouch_for_the_other(
    client: TestClient, two_workspaces: tuple[tuple[UUID, UUID], tuple[UUID, UUID]]
) -> None:
    """The reason it is asked per entity: somebody can have recorded every
    project and a third of the tasks."""
    mine, _ = two_workspaces
    as_member(client, mine)
    _post(client, "/ops/projects", {"name": "Muscat fit-out", "status": "active"})
    _post(client, "/ops/tasks", {"title": "Order the glazing", "status": "todo"})
    _post(client, "/ops/completeness", {"entity": "projects"})

    entities = [entry["entity"] for entry in client.get("/ops").json()["completeness"]]

    assert entities == ["projects"]


@requires_db
def test_confirming_again_appends_and_the_newest_is_read(
    client: TestClient, two_workspaces: tuple[tuple[UUID, UUID], tuple[UUID, UUID]]
) -> None:
    """**Append-only.** The question is asked again as the business changes, and
    when somebody last vouched for the record is what a reader of a rate needs.
    An upsert would keep the claim and destroy its history."""
    mine, ws = two_workspaces[0], two_workspaces[0][1]
    as_member(client, mine)
    _post(client, "/ops/projects", {"name": "Muscat fit-out", "status": "active"})
    _post(client, "/ops/completeness", {"entity": "projects", "complete_as_of": "2026-09-11"})
    _post(client, "/ops/completeness", {"entity": "projects", "complete_as_of": "2026-09-15"})

    body = client.get("/ops").json()

    assert len(body["completeness"]) == 1, "one row per entity is read, the newest"
    assert body["completeness"][0]["complete_as_of"] == "2026-09-15"
    assert ws  # the fixture's teardown removes both confirmations


@requires_db
def test_a_future_confirmation_is_refused(
    client: TestClient, two_workspaces: tuple[tuple[UUID, UUID], tuple[UUID, UUID]]
) -> None:
    """ "Complete as of next Tuesday" is not a thing anybody can know, and a
    figure carrying it would report a confirmation that has not happened."""
    mine, _ = two_workspaces
    as_member(client, mine)

    response = _post(
        client, "/ops/completeness", {"entity": "projects", "complete_as_of": "2099-01-01"}
    )

    assert response.status_code == 422, response.text


@requires_db
def test_an_unknown_entity_is_refused_at_the_edge(
    client: TestClient, two_workspaces: tuple[tuple[UUID, UUID], tuple[UUID, UUID]]
) -> None:
    """A 422 naming the field, not an `IntegrityError` reaching the client as a
    500 naming a CHECK constraint."""
    mine, _ = two_workspaces
    as_member(client, mine)

    response = _post(client, "/ops/completeness", {"entity": "invoices"})

    assert response.status_code == 422
    assert "entity" in response.text


@requires_db
def test_another_workspaces_confirmation_is_invisible(
    client: TestClient, two_workspaces: tuple[tuple[UUID, UUID], tuple[UUID, UUID]]
) -> None:
    """A confirmation crossing a workspace boundary would vouch for somebody
    else's record — and unlock a rate over it."""
    mine, theirs = two_workspaces
    as_member(client, mine)
    _post(client, "/ops/projects", {"name": "Muscat fit-out", "status": "active"})
    _post(client, "/ops/completeness", {"entity": "projects"})

    as_member(client, theirs)
    _post(client, "/ops/projects", {"name": "Their project", "status": "active"})

    assert client.get("/ops").json()["completeness"] == []


@requires_db
def test_a_viewer_may_not_confirm_completeness(
    client: TestClient, two_workspaces: tuple[tuple[UUID, UUID], tuple[UUID, UUID]]
) -> None:
    """Vouching for a record is a claim about the company, not a reading of it."""
    mine, _ = two_workspaces
    as_member(client, mine, role=Role.VIEWER)

    assert _post(client, "/ops/completeness", {"entity": "projects"}).status_code == 403


@requires_db
def test_confirming_needs_csrf(
    client: TestClient, two_workspaces: tuple[tuple[UUID, UUID], tuple[UUID, UUID]]
) -> None:
    mine, _ = two_workspaces
    as_member(client, mine)

    assert client.post("/ops/completeness", json={"entity": "projects"}).status_code == 403


# ── Milestones and issues — `doc/15` S10.3 ────────────────────


@requires_db
def test_a_milestone_needs_a_project_in_this_workspace(
    client: TestClient, two_workspaces: tuple[tuple[UUID, UUID], tuple[UUID, UUID]]
) -> None:
    """A milestone is a point in a project's plan. **RLS is what makes the write
    safe**; this check is what makes a mismatched id a 404 naming the project
    rather than a foreign-key error naming a constraint, since the policy hides
    the row the FK points at."""
    mine, _ = two_workspaces
    as_member(client, mine)

    response = _post(
        client,
        "/ops/milestones",
        {"title": "Orphan", "project_id": str(uuid4()), "planned_on": "2026-12-01"},
    )

    assert response.status_code == 404


@requires_db
def test_a_milestone_cannot_hang_off_another_workspaces_project(
    client: TestClient, two_workspaces: tuple[tuple[UUID, UUID], tuple[UUID, UUID]]
) -> None:
    """The isolation that matters most for a child record: it would put a row in
    somebody else's project, and it would appear on their timeline."""
    mine, theirs = two_workspaces
    as_member(client, theirs)
    theirs_project = _post(client, "/ops/projects", {"name": "Theirs"}).json()["id"]

    as_member(client, mine)
    response = _post(
        client,
        "/ops/milestones",
        {"title": "Sneak", "project_id": theirs_project, "planned_on": "2026-12-01"},
    )

    assert response.status_code == 404


@requires_db
def test_an_issue_needs_no_project(
    client: TestClient, two_workspaces: tuple[tuple[UUID, UUID], tuple[UUID, UUID]]
) -> None:
    """`ops_task`'s reason: requiring one would make somebody invent a project to
    record a snag, and an invented project then counts on `projects_board`."""
    mine, _ = two_workspaces
    as_member(client, mine)

    response = _post(client, "/ops/issues", {"title": "Leak in the store room"})

    assert response.status_code == 201, response.text
    assert response.json()["project_id"] is None


@requires_db
def test_an_unknown_severity_is_refused_at_the_edge(
    client: TestClient, two_workspaces: tuple[tuple[UUID, UUID], tuple[UUID, UUID]]
) -> None:
    mine, _ = two_workspaces
    as_member(client, mine)

    response = _post(client, "/ops/issues", {"title": "Bad", "severity": "catastrophic"})

    assert response.status_code == 422
    assert "severity" in response.text


@requires_db
def test_milestones_and_issues_are_read_back_and_isolated(
    client: TestClient, two_workspaces: tuple[tuple[UUID, UUID], tuple[UUID, UUID]]
) -> None:
    mine, theirs = two_workspaces
    as_member(client, mine)
    project = _post(client, "/ops/projects", {"name": "Mine"}).json()["id"]
    _post(
        client,
        "/ops/milestones",
        {"title": "Handover", "project_id": project, "planned_on": "2026-12-01"},
    )
    _post(client, "/ops/issues", {"title": "Snag", "severity": "high", "project_id": project})

    body = client.get("/ops").json()
    assert [m["title"] for m in body["milestones"]] == ["Handover"]
    assert [i["severity"] for i in body["issues"]] == ["high"]

    as_member(client, theirs)
    other = client.get("/ops").json()
    assert other["milestones"] == []
    assert other["issues"] == []


@requires_db
def test_archiving_a_project_takes_its_milestones_with_it(
    client: TestClient, two_workspaces: tuple[tuple[UUID, UUID], tuple[UUID, UUID]]
) -> None:
    """**Archiving a project does not cascade**, unlike deleting one — the row is
    still there and so are its children. This asserts what actually happens
    rather than what the FK would do, because the two differ and the tile reads
    the archived flag on each table separately."""
    mine, _ = two_workspaces
    as_member(client, mine)
    project = _post(client, "/ops/projects", {"name": "Mine"}).json()["id"]
    _post(
        client,
        "/ops/milestones",
        {"title": "Handover", "project_id": project, "planned_on": "2026-12-01"},
    )

    client.delete(f"/ops/projects/{project}", headers={"X-CSRF-Token": CSRF})
    body = client.get("/ops").json()

    assert body["projects"] == []
    assert len(body["milestones"]) == 1, (
        "archiving a project leaves its milestones; only a DELETE would cascade"
    )


@requires_db
def test_an_archived_issue_stops_counting_without_being_deleted(
    client: TestClient, two_workspaces: tuple[tuple[UUID, UUID], tuple[UUID, UUID]]
) -> None:
    mine, _ = two_workspaces
    as_member(client, mine)
    issue = _post(client, "/ops/issues", {"title": "Snag", "severity": "low"}).json()["id"]

    assert client.delete(f"/ops/issues/{issue}", headers={"X-CSRF-Token": CSRF}).status_code == 204
    assert client.get("/ops").json()["issues"] == []


@requires_db
def test_completeness_accepts_the_two_new_entities(
    client: TestClient, two_workspaces: tuple[tuple[UUID, UUID], tuple[UUID, UUID]]
) -> None:
    """`ENTITIES` and `ck_ops_completeness_entity` are kept in step by hand. A
    value legal in Python and refused by the constraint is a 500 on a write
    somebody was told was fine."""
    mine, _ = two_workspaces
    as_member(client, mine)

    for entity in ("milestones", "issues"):
        assert _post(client, "/ops/completeness", {"entity": entity}).status_code == 201, entity


# ── Dispatches and the rule — `doc/15` S10.4, ADR 0036 ────────


@requires_db
def test_an_order_is_recorded_and_read_back(
    client: TestClient, two_workspaces: tuple[tuple[UUID, UUID], tuple[UUID, UUID]]
) -> None:
    mine, _ = two_workspaces
    as_member(client, mine)

    response = _post(client, "/ops/dispatches", {"reference": "SO-1", "promised_on": "2026-09-10"})

    assert response.status_code == 201, response.text
    assert response.json()["dispatched_on"] is None, "not sent is the ordinary state"
    assert [d["reference"] for d in client.get("/ops").json()["dispatches"]] == ["SO-1"]


@requires_db
def test_the_grace_starts_unset_and_that_is_the_gate(
    client: TestClient, two_workspaces: tuple[tuple[UUID, UUID], tuple[UUID, UUID]]
) -> None:
    """**The whole of D32.** `NULL`, not `0`. A default of zero would be a
    threshold we set for every workspace, silently, and it would produce a
    confident percentage under a rule the customer never agreed to."""
    mine, _ = two_workspaces
    as_member(client, mine)
    _post(client, "/ops/dispatches", {"reference": "SO-1", "promised_on": "2026-09-10"})

    assert client.get("/ops").json()["grace_days"] is None


@requires_db
def test_setting_the_rule_replaces_rather_than_appends(
    client: TestClient, two_workspaces: tuple[tuple[UUID, UUID], tuple[UUID, UUID]]
) -> None:
    """Unlike a completeness confirmation, which is append-only because *when
    somebody last vouched* is what a reader of a rate needs. This is a rule with
    one current value, and a figure computed under it says which rule it used."""
    mine, _ = two_workspaces
    as_member(client, mine)
    _post(client, "/ops/dispatches", {"reference": "SO-1", "promised_on": "2026-09-10"})

    client.put("/ops/dispatch-rule", json={"grace_days": 2}, headers={"X-CSRF-Token": CSRF})
    client.put("/ops/dispatch-rule", json={"grace_days": 5}, headers={"X-CSRF-Token": CSRF})

    assert client.get("/ops").json()["grace_days"] == 5


@requires_db
def test_a_negative_grace_is_refused(
    client: TestClient, two_workspaces: tuple[tuple[UUID, UUID], tuple[UUID, UUID]]
) -> None:
    """It would turn "late" into "early" without anybody noticing. Refused at the
    edge, and the CHECK constraint says the same thing at the other end."""
    mine, _ = two_workspaces
    as_member(client, mine)

    response = client.put(
        "/ops/dispatch-rule", json={"grace_days": -1}, headers={"X-CSRF-Token": CSRF}
    )

    assert response.status_code == 422


@requires_db
def test_another_workspaces_rule_is_not_ours(
    client: TestClient, two_workspaces: tuple[tuple[UUID, UUID], tuple[UUID, UUID]]
) -> None:
    """A rule crossing a boundary would change what "late" means for somebody
    else's figure."""
    mine, theirs = two_workspaces
    as_member(client, mine)
    _post(client, "/ops/dispatches", {"reference": "SO-1", "promised_on": "2026-09-10"})
    client.put("/ops/dispatch-rule", json={"grace_days": 7}, headers={"X-CSRF-Token": CSRF})

    as_member(client, theirs)
    _post(client, "/ops/dispatches", {"reference": "THEIRS", "promised_on": "2026-09-10"})

    assert client.get("/ops").json()["grace_days"] is None


@requires_db
def test_a_viewer_may_not_set_the_rule(
    client: TestClient, two_workspaces: tuple[tuple[UUID, UUID], tuple[UUID, UUID]]
) -> None:
    """Defining what late means is a claim about the company, not a reading."""
    mine, _ = two_workspaces
    as_member(client, mine, role=Role.VIEWER)

    response = client.put(
        "/ops/dispatch-rule", json={"grace_days": 1}, headers={"X-CSRF-Token": CSRF}
    )

    assert response.status_code == 403


@requires_db
def test_setting_the_rule_needs_csrf(
    client: TestClient, two_workspaces: tuple[tuple[UUID, UUID], tuple[UUID, UUID]]
) -> None:
    mine, _ = two_workspaces
    as_member(client, mine)

    assert client.put("/ops/dispatch-rule", json={"grace_days": 1}).status_code == 403


@requires_db
def test_dispatches_are_isolated_between_workspaces(
    client: TestClient, two_workspaces: tuple[tuple[UUID, UUID], tuple[UUID, UUID]]
) -> None:
    mine, theirs = two_workspaces
    as_member(client, mine)
    _post(client, "/ops/dispatches", {"reference": "SO-1", "promised_on": "2026-09-10"})

    as_member(client, theirs)

    assert client.get("/ops").json()["dispatches"] == []
