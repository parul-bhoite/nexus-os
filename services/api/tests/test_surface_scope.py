"""Who sees what on the common surface.

ADR 0029 makes the morning brief **scope-composed from day one**, and this is
the file that holds it to that. The reasoning is worth restating, because the
guard looks unnecessary today and will be load-bearing without any code change
marking the moment:

Everything the brief can currently report comes from `page_signals` — the
company's own public website, which every member may see. So a workspace-wide
composition would pass every test that exists. The day a Finance capability
produces a finding, that same composition puts an L3 figure at the top of every
contributor's dashboard, and nothing in the diff says so. The narration
read-back had exactly this shape and needed two written-down properties to stay
honest; this one is scoped instead, which is cheaper and does not rely on
anybody reading a docstring.

The second thing asserted here is agreement: the brief must not surface a
finding from a department the left panel does not list. Two different filters
for one visibility question is how a nav and a page start disagreeing, and the
disagreement is a disclosure.

Hermetic, in `test_dashboard_scope.py`'s shape — the lattice, with no database.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.domain.scopes import Department, Role
from app.domain.session import ScopedSession
from app.grounding.compute import MEASURABLE
from app.main import create_app


@pytest.fixture
def client() -> Iterator[TestClient]:
    app = create_app()
    _no_database(app)
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _no_database(app: FastAPI) -> None:
    from app.routes.dashboards import (
        Observed,
        answered_questions,
        observed_sources,
        running_departments,
    )

    app.dependency_overrides[running_departments] = lambda: frozenset(Department)
    # `GET /dashboards` is called by the agreement test below and depends on
    # this; without the override it reaches for a database `conftest`
    # deliberately pins empty.
    app.dependency_overrides[answered_questions] = lambda: frozenset()
    # No crawl: every assertion below is about *which* capabilities are in
    # scope, and a workspace with signals would make the answers depend on a
    # page as well as on a permission.
    app.dependency_overrides[observed_sources] = lambda: Observed(crawl=None)


def as_role(client: TestClient, role: Role, departments: frozenset[Department]) -> None:
    from app.deps import current_scope

    scope = ScopedSession(
        user_id=uuid4(),
        tenant_id=uuid4(),
        workspace_id=uuid4(),
        role=role,
        departments=departments,
    )
    client.app.dependency_overrides[current_scope] = lambda: scope  # type: ignore[attr-defined]


def surface(client: TestClient) -> dict[str, Any]:
    response = client.get("/dashboards/surface")
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def brief(client: TestClient) -> dict[str, Any]:
    payload: dict[str, Any] = surface(client)["brief"]
    return payload


# ── The route exists at all ───────────────────────────────────


def test_surface_is_not_swallowed_by_the_department_wildcard() -> None:
    """`/dashboards/{department}` types its path parameter as the `Department`
    enum, so a sibling declared after it is matched as a department name and
    422s on every request. `/company` sits above the wildcard for the same
    reason, and this asserts the ordering rather than trusting it.

    Read from the OpenAPI document rather than from `app.routes`: this app
    includes its routers through a wrapper, so the top-level list holds no
    paths at all and an assertion over it would pass vacuously or, as it did
    first time, fail on an empty list while the route worked perfectly.
    """
    from app.main import create_app

    paths = list(create_app().openapi()["paths"])

    assert paths.index("/dashboards/surface") < paths.index("/dashboards/{department}")


# ── The brief is composed, not workspace-wide ─────────────────


def test_a_contributor_gets_a_brief_rather_than_a_refusal(client: TestClient) -> None:
    """The surface is common. A brief behind a department gate would have made
    `executive.morning_brief` the wrong home for it, which is the whole of
    D26 — and a contributor who gets a 403 at the top of their own dashboard has
    a broken page, not a scoped one."""
    as_role(client, Role.CONTRIBUTOR, frozenset({Department.MARKETING}))

    assert brief(client)["state"] == "not_measured"


def test_every_department_the_caller_holds_is_represented(client: TestClient) -> None:
    """With no crawl there is nothing measured, so the honest answer is the
    *absence* state for everybody — not an empty findings list, which would read
    as "we looked and found nothing"."""
    for role, departments in (
        (Role.OWNER, frozenset(Department)),
        (Role.DEPARTMENT_MANAGER, frozenset({Department.FINANCE})),
        (Role.CONTRIBUTOR, frozenset({Department.SALES})),
    ):
        as_role(client, role, departments)
        body = brief(client)

        assert body["state"] == "not_measured"
        assert body["items"] == []
        assert body["measured_on"] == ""
        assert body["message"]


def test_a_reader_is_never_told_about_a_department_they_cannot_open(
    client: TestClient,
) -> None:
    """**The guard that is not yet load-bearing and will be.**

    Today every capability that computes is Marketing's, so a Sales-only
    contributor's brief is empty either way. The assertion is written against
    the *capability ids* the brief can carry rather than against today's
    emptiness, so it starts failing the moment a second department computes
    something — which is exactly when a workspace-wide composition would begin
    leaking without a diff to show for it.
    """
    as_role(client, Role.CONTRIBUTOR, frozenset({Department.SALES}))
    items = brief(client)["items"]

    assert all(str(item["capability_id"]).startswith("sales.") for item in items)


def test_the_brief_and_the_navigation_filter_on_the_same_two_things(
    client: TestClient,
) -> None:
    """Which departments the company *runs*, and which the caller may *reach*.

    `list_dashboards` applies both; so must this. Two filters for one visibility
    question is how a nav and a page start disagreeing, and a brief naming a
    department the panel does not list is a disclosure by a different route.
    """
    as_role(client, Role.DEPARTMENT_MANAGER, frozenset({Department.MARKETING}))
    listed = {str(entry["department"]) for entry in client.get("/dashboards").json()["directors"]}
    carried = {str(item["capability_id"]).split(".", 1)[0] for item in brief(client)["items"]}

    assert carried <= listed


# ── It costs nothing ──────────────────────────────────────────


def test_the_surface_never_reaches_a_model(client: TestClient) -> None:
    """ADR 0029's central trade. The brief renders at the top of every page load,
    so it has to survive a missing API key — and `conftest` pins the settings to
    unconfigured, which means a route that reached for a provider here would
    refuse rather than return 200."""
    as_role(client, Role.OWNER, frozenset(Department))

    assert brief(client)["state"] == "not_measured"


def test_it_is_a_get_and_therefore_needs_no_csrf(client: TestClient) -> None:
    """`require_csrf` exempts safe methods on the promise that they do not change
    state. The brief spends nothing and writes no `generation` row, so it can
    honestly keep that promise — unlike `narrate`, which is a POST for exactly
    the opposite reason (ADR 0028)."""
    as_role(client, Role.OWNER, frozenset(Department))
    response = client.get("/dashboards/surface")

    assert response.status_code == 200


# ── Coverage, scoped the same way ─────────────────────────────


def test_coverage_is_counted_over_the_departments_this_reader_holds(
    client: TestClient,
) -> None:
    """The region says *where the product is, **for you***. A Marketing-only
    manager counted over all 89 would be shown a denominator of capabilities
    they cannot open — the same over-claim the whole surface exists to avoid."""
    as_role(client, Role.OWNER, frozenset(Department))
    everything = surface(client)["coverage"]

    as_role(client, Role.DEPARTMENT_MANAGER, frozenset({Department.MARKETING}))
    theirs = surface(client)["coverage"]

    assert everything["total"] == 89
    assert theirs["total"] < everything["total"]


def test_the_bands_are_served_summing_to_the_denominator(client: TestClient) -> None:
    """Three counts that do not sum still render as three plausible numbers.
    The domain object refuses to exist in that state; this asserts the serialiser
    did not reintroduce the gap on the way out."""
    as_role(client, Role.OWNER, frozenset(Department))
    bands = surface(client)["coverage"]

    assert bands["measuring"] + bands["reading_back"] + bands["not_built"] == bands["total"]
    assert bands["not_built"] > bands["measuring"] + bands["reading_back"]


def test_coverage_does_not_depend_on_whether_anything_was_crawled(
    client: TestClient,
) -> None:
    """**Coverage is about the catalogue, the brief is about the data.**

    There is no crawl in this fixture and the brief is correctly `not_measured`,
    but two capabilities still have calculators and a route serving them. A
    coverage number that fell to zero with the crawl would be answering the
    brief's question twice instead of its own.
    """
    as_role(client, Role.OWNER, frozenset(Department))
    body = surface(client)

    assert body["brief"]["state"] == "not_measured"
    # `len(MEASURABLE)`, not a literal. This read `2` — the size of `CRAWL_AUDITS`
    # — through two slices that added dispatches, and stayed green because the
    # route injected the same single dispatch into `coverage`. The constant was
    # restating the defect. This caller holds every department, so every
    # capability with a calculator is one it can see.
    assert body["coverage"]["measuring"] == len(MEASURABLE)
