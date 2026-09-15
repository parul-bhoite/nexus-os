"""Who may ask for a sentence, and about what.

`POST /dashboards/{department}/narrate` is the **only route in this codebase
that takes a capability id from the caller**, and that is the whole reason this
file exists. Every other surface derives the capability from the path or from
the registry; this one is handed one, and `answer.narrate` does
`BY_ID[capability_id]` with a bare `KeyError` on a miss.

So the id is checked six ways before `narrate` sees it, and the one that would
otherwise be a real hole is the department check: `enforce_department` proved
the caller may open **Marketing**, and a body naming `finance.runway_alert`
would then be narrated under that permission.

Hermetic, in `test_dashboard_scope.py`'s shape: these assert the lattice and
have no database. What a narration *costs* and what it *stores* is
`test_narration_endpoint_db.py`.
"""

from __future__ import annotations

from collections.abc import Iterator
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.domain.scopes import Department, Role
from app.domain.session import ScopedSession
from app.main import create_app

CSRF = "a-csrf-token"


def _override_departments(app: FastAPI) -> None:
    from app.routes.dashboards import (
        Observed,
        answered_questions,
        observed_sources,
        running_departments,
    )

    app.dependency_overrides[running_departments] = lambda: frozenset(Department)  # type: ignore[attr-defined]
    app.dependency_overrides[answered_questions] = lambda: frozenset()  # type: ignore[attr-defined]
    # No crawl, so nothing here reaches a model or a ledger. Every refusal
    # below happens before that would matter, which is the point: a caller who
    # may not ask must be refused without spending anything.
    app.dependency_overrides[observed_sources] = lambda: Observed(crawl=None)  # type: ignore[attr-defined]


@pytest.fixture
def client() -> Iterator[TestClient]:
    app = create_app()
    _override_departments(app)
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def as_role(client: TestClient, scope: ScopedSession) -> None:
    from app.deps import current_scope

    client.app.dependency_overrides[current_scope] = lambda: scope  # type: ignore[attr-defined]
    client.cookies.set("nexus_csrf", CSRF)


def _scope(role: Role, departments: frozenset[Department]) -> ScopedSession:
    return ScopedSession(
        user_id=uuid4(),
        tenant_id=uuid4(),
        workspace_id=uuid4(),
        role=role,
        departments=departments,
    )


def narrate(client: TestClient, department: str, key: str) -> object:
    return client.post(
        f"/dashboards/{department}/narrate",
        json={"key": key},
        headers={"X-CSRF-Token": CSRF},
    )


# ── The department gate, inherited rather than rewritten ──────


def test_a_caller_outside_the_department_cannot_narrate_its_tiles(client: TestClient) -> None:
    """Same refusal as the GET, because it is the same dependency —
    `reachable_director`. A narration endpoint with its own copy of the guard
    is a second door into the room the first one locks."""
    as_role(client, _scope(Role.DEPARTMENT_MANAGER, frozenset({Department.SALES})))

    assert narrate(client, "marketing", "marketing.seo_gaps").status_code == 404


def test_the_executive_surface_keeps_its_own_refusal(client: TestClient) -> None:
    as_role(client, _scope(Role.DEPARTMENT_MANAGER, frozenset({Department.MARKETING})))

    response = narrate(client, "executive", "executive.morning_brief")

    assert response.status_code == 403
    assert "Owner or Executive" in response.json()["detail"]


def test_an_unknown_department_is_refused_exactly_as_the_get_refuses_it(
    client: TestClient,
) -> None:
    """**Asserted as agreement, not as a number.**

    `department: Department` makes FastAPI validate the enum, so an unknown one
    is a 422 from the framework before `reachable_director` runs — not the 404
    the guard would give. That is fine, and it is *not* something this route
    should special-case: what matters is that asking to narrate a department
    fails the same way as asking to read it, because a POST that refuses
    differently from its GET is a way to enumerate what exists.

    (The browser never sees either: the BFF validates the department against
    its own list and returns 404 before the API is called.)
    """
    as_role(client, _scope(Role.OWNER, frozenset(Department)))

    post = narrate(client, "not-a-department", "marketing.seo_gaps")
    get = client.get("/dashboards/not-a-department")

    assert post.status_code == get.status_code


# ── The capability id, which only this route accepts ──────────


def test_a_key_from_another_department_is_refused(client: TestClient) -> None:
    """**The hole this route would otherwise open.**

    `reachable_director` proved the caller may open Marketing. Without a check
    that the *body's* capability belongs to Marketing too, a Marketing-only
    manager posts `finance.runway_alert` to `/dashboards/marketing/narrate` and
    has Finance narrated under a Marketing permission.

    No other route in the codebase takes a capability id from the caller, so
    there is no precedent to inherit and nothing else would have caught it.
    """
    as_role(client, _scope(Role.DEPARTMENT_MANAGER, frozenset({Department.MARKETING})))

    assert narrate(client, "marketing", "finance.runway_alert").status_code == 404


def test_an_unknown_key_is_a_refusal_and_not_a_crash(client: TestClient) -> None:
    """`answer.narrate` does `BY_ID[capability_id]` and raises a bare
    `KeyError` on a miss — deliberately, per its own docstring. Unvalidated,
    that is a 500 on a typo."""
    as_role(client, _scope(Role.OWNER, frozenset(Department)))

    response = narrate(client, "marketing", "marketing.not_a_real_capability")

    assert response.status_code == 404
    assert response.json()["detail"]


def test_a_capability_nothing_computes_is_refused(client: TestClient) -> None:
    """`computes()` is the gate. Narrating a tile with no figure would ask the
    model to explain a number that does not exist, and the honest answer to
    "explain this" when there is nothing to explain is not to ask."""
    as_role(client, _scope(Role.OWNER, frozenset(Department)))

    assert narrate(client, "marketing", "marketing.growth_planner").status_code == 404


def test_the_read_back_is_safe_without_refusing_a_capability_that_uses_facts() -> None:
    """**The check this route deliberately does not have.**

    The first draft of `_narratable` refused any capability with
    `consumes_facts`, on the theory that a workspace-wide narration read-back
    could otherwise carry a department-scoped value out. It would have refused
    `marketing.seo_gaps` — the tile the slice exists for — which consumes
    `arabic_in_scope`, an L3 Marketing fact.

    The read is safe for two narrower reasons, and asserting *those* is what
    keeps it safe. Consuming a fact is not the risk; showing one is, and the
    narrator is never shown one.
    """
    from app.ai.runtime.skills import get_registry
    from app.grounding.answer import NARRATOR
    from app.retrieval.narration import _CURRENT

    # The model is sent six keys and none of them is a fact, so the prose
    # cannot contain a value it never saw.
    assert set(get_registry().get(NARRATOR).requires_grounding) == {
        "label",
        "value",
        "unit",
        "window",
        "sources",
        "delta",
    }

    # The consumed fact lands in `input_snapshot`, and the display read never
    # touches that column.
    assert "input_snapshot" not in str(_CURRENT).lower()


# ── CSRF, because this one spends money ───────────────────────


def test_a_narration_without_a_csrf_header_is_refused(client: TestClient) -> None:
    """A POST that costs tokens is a POST worth forging. `require_csrf` is
    declared on the route rather than checked inside it, so this asserts the
    decorator rather than a branch."""
    as_role(client, _scope(Role.OWNER, frozenset(Department)))

    response = client.post(
        "/dashboards/marketing/narrate", json={"key": "marketing.seo_gaps"}
    )

    assert response.status_code == 403


def test_a_mismatched_csrf_header_is_refused(client: TestClient) -> None:
    as_role(client, _scope(Role.OWNER, frozenset(Department)))

    response = client.post(
        "/dashboards/marketing/narrate",
        json={"key": "marketing.seo_gaps"},
        headers={"X-CSRF-Token": "not-the-cookie"},
    )

    assert response.status_code == 403


# ── No crawl is an answer, not an error ───────────────────────


def test_a_workspace_with_no_crawl_gets_a_reason_rather_than_a_failure(
    client: TestClient,
) -> None:
    """**200, not 409.**

    The tile is already `locked` with a specific unlock sentence, and that
    sentence is better copy than anything a reason map could produce. A 4xx
    would push the client into an error path and tempt it to render something
    of its own.

    No `generation` row is written either: the rule that a refusal is recorded
    governs answers we *attempted*, and here nothing ran.
    """
    as_role(client, _scope(Role.OWNER, frozenset(Department)))

    response = narrate(client, "marketing", "marketing.seo_gaps")

    assert response.status_code == 200
    body = response.json()
    assert body["outcome"] == "unavailable"
    assert body["reason"] == "missing_input"
    assert body["message"]
    assert body["narration"] is None
    assert body["generation_id"] == ""
