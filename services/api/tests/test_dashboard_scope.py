"""Who lands where, who may open which director, and what a tile may say.

Doc 07 M4's validation step is *"log in as each role and confirm the surface
matches doc 06 §2.3"*. These are that, for the seven director pages: a Sales
manager cannot open Finance, a Department Manager's portal is six directors
rather than seven, and the list of what they cannot open carries no count.

The last group is about honesty rather than access. Doc 04 §6 rule 1 — *"every
locked tile states its unlock… the tile is a call to action, not a failure"* —
and I10, never a zero. A placeholder dashboard is exactly where both get broken,
because a tile with nothing behind it is the easiest place to put a plausible
number.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.deps import current_scope
from app.domain.dashboards import (
    BY_DEPARTMENT,
    DIRECTORS,
    WidgetState,
    landing_department,
    state_for,
    unlock_sentence,
)
from app.domain.registry import is_reachable
from app.domain.scopes import Department, Role
from app.domain.session import ScopedSession
from app.main import create_app

USER = UUID("11111111-1111-1111-1111-111111111111")


def caller(role: Role, departments: set[Department] | None = None) -> ScopedSession:
    return ScopedSession(
        user_id=USER,
        tenant_id=uuid4(),
        workspace_id=uuid4(),
        role=role,
        departments=frozenset(departments or set()),
    )


def _override_departments(app: object) -> None:
    """Say "this company runs everything" for these tests.

    They assert the **permission** lattice — who may reach which director — and
    P6 added a second, independent filter for which departments the company
    runs at all. Overriding it keeps these tests about the one thing they were
    written for; `tests/test_onboarding_spine.py` covers the other.
    """
    from app.domain.scopes import Department
    from app.routes.dashboards import (
        Observed,
        answered_questions,
        observed_sources,
        running_departments,
    )

    app.dependency_overrides[running_departments] = lambda: frozenset(Department)  # type: ignore[attr-defined]
    # Q27's counter reads the database too. Overridden for the same reason: these
    # tests are about the permission lattice, and `test_question_bank.py` covers
    # what the counter counts.
    # A lambda, not `frozenset` itself — FastAPI introspects the signature of
    # an override, and a builtin type has none.
    app.dependency_overrides[answered_questions] = lambda: frozenset()  # type: ignore[attr-defined]
    # Slice 1's crawl read, overridden for the third time and the same reason.
    # `crawl=None` is the honest default for a workspace nobody has crawled, so
    # every tile here renders `locked` or `planned` and no figure appears — the
    # figure has its own tests, and these are about who may see the page at all.
    app.dependency_overrides[observed_sources] = lambda: Observed(crawl=None)  # type: ignore[attr-defined]


@pytest.fixture
def client() -> Iterator[TestClient]:
    app = create_app()
    _override_departments(app)
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def as_role(client: TestClient, scope: ScopedSession) -> None:
    client.app.dependency_overrides[current_scope] = lambda: scope  # type: ignore[attr-defined]


# ── Landing ───────────────────────────────────────────────────


def test_an_owner_lands_on_the_chief_of_staff() -> None:
    assert (
        landing_department(executive_surface=True, departments=frozenset({Department.EXECUTIVE}))
        is Department.EXECUTIVE
    )


def test_a_manager_lands_on_their_own_department() -> None:
    assert (
        landing_department(executive_surface=False, departments=frozenset({Department.SALES}))
        is Department.SALES
    )


def test_someone_with_no_department_lands_nowhere() -> None:
    """A Viewer holds no department. Picking one for them would put a person in
    a department nobody assigned them to, and the next request would 404."""
    assert landing_department(executive_surface=False, departments=frozenset()) is None


def test_landing_is_decided_by_membership_not_by_an_onboarding_answer() -> None:
    """`landing_department` takes the scope's departments and nothing else.

    The wizard asks "which department are you in?" and stores the answer as an
    L2 fact. If landing read *that*, someone who typed Finance while holding a
    Sales membership would be sent to a page their scope refuses — and the fix
    would be tempting to apply in the wrong direction.
    """
    import inspect

    from app.domain import dashboards

    source = inspect.getsource(dashboards.landing_department)
    assert "onboarding" not in source.lower().replace("onboarding.", "")


# ── Who may open which director ───────────────────────────────


def test_a_sales_manager_cannot_open_finance(client: TestClient) -> None:
    as_role(client, caller(Role.DEPARTMENT_MANAGER, {Department.SALES}))
    assert client.get("/dashboards/finance").status_code == 404


def test_a_sales_manager_can_open_sales(client: TestClient) -> None:
    as_role(client, caller(Role.DEPARTMENT_MANAGER, {Department.SALES}))
    response = client.get("/dashboards/sales")
    assert response.status_code == 200
    assert response.json()["title"] == "AI Sales Director"


def test_a_manager_portal_is_six_directors_not_seven(client: TestClient) -> None:
    """Doc 06 §2.4, stated as a cost rather than hidden: the Chief of Staff page,
    the Morning Brief and the composite score are Owner and Executive only."""
    as_role(client, caller(Role.DEPARTMENT_MANAGER, {Department.SALES}))
    assert client.get("/dashboards/executive").status_code == 403


def test_an_owner_sees_all_seven(client: TestClient) -> None:
    as_role(client, caller(Role.OWNER, {Department.EXECUTIVE}))
    payload = client.get("/dashboards").json()
    assert len(payload["directors"]) == len(DIRECTORS) == 7
    assert payload["landing"] == "/dashboard/executive"


def test_a_contributor_sees_only_their_own(client: TestClient) -> None:
    as_role(client, caller(Role.CONTRIBUTOR, {Department.MARKETING}))
    payload = client.get("/dashboards").json()
    assert [d["department"] for d in payload["directors"]] == ["marketing"]
    assert payload["landing"] == "/dashboard/marketing"


def test_the_list_carries_no_count_of_what_was_removed(client: TestClient) -> None:
    """Doc 06 §4.5 — "3 directors hidden" is the disclosure the rule forbids."""
    as_role(client, caller(Role.CONTRIBUTOR, {Department.MARKETING}))
    payload = client.get("/dashboards").json()

    for key, value in payload.items():
        if key == "directors":
            continue
        assert not isinstance(value, int) or key == "delivered_count", (
            f"{key} could disclose how many directors were filtered out"
        )


def test_a_viewer_reaches_no_director(client: TestClient) -> None:
    """A Viewer has no L3 at all — the lattice is monotonic (M1)."""
    as_role(client, caller(Role.VIEWER))
    payload = client.get("/dashboards").json()
    assert payload["directors"] == []
    assert payload["landing"] is None


# ── What a tile is allowed to say ─────────────────────────────


def test_an_unreachable_tile_says_planned_and_never_locked() -> None:
    """The honesty mechanism, asserted rather than trusted.

    **This test used to be called `test_nothing_is_reachable_yet`** and asserted
    exactly that of every offering. Slice 1 made `3.7` and `3.8` reachable, so
    the universal claim is gone — but the claim it was protecting is not, and it
    is the one that matters: an *unreachable* offering must render `PLANNED` and
    never `LOCKED`, because `LOCKED` tells a customer that connecting something
    turns on a widget that does not exist (`doc/04` §6 rule 1).

    `is_reachable` is asked per offering rather than compared against a set,
    because the set is not here to compare against — `domain/registry` holds
    it, and this asserts the outcome a person sees rather than the bookkeeping
    behind it.
    """
    checked = 0
    for director in DIRECTORS:
        for offering in director.offerings:
            if is_reachable(offering.id):
                continue
            checked += 1
            assert (
                state_for(offering, connected=frozenset(), reachable=False)
                is WidgetState.PLANNED
            )
            # And connecting everything it names still does not move it. This is
            # the assertion that would have caught a `LOCKED` leaking through.
            assert (
                state_for(offering, connected=frozenset(offering.needs), reachable=False)
                is WidgetState.PLANNED
            )

    assert checked > 50, "most of the catalogue is still unbuilt; this should be checking it"


def test_a_reachable_offering_with_nothing_connected_locks(client: TestClient) -> None:
    """And the state it moves to is `LOCKED`, with its unlock intact.

    No module global is reassigned to get there any more. Reachability is an
    argument, so the test states the hypothesis directly — *if this were built* —
    instead of mutating the module under test and restoring it in a `finally`
    that a failing assertion used to skip.
    """
    growth_plan = BY_DEPARTMENT[Department.MARKETING].offerings[3]
    assert growth_plan.id == "3.4"
    assert state_for(growth_plan, connected=frozenset(), reachable=False) is WidgetState.PLANNED

    assert state_for(growth_plan, connected=frozenset(), reachable=True) is WidgetState.LOCKED
    assert (
        state_for(growth_plan, connected=frozenset(growth_plan.needs), reachable=True)
        is WidgetState.LIVE
    )


def test_every_offering_that_needs_something_says_what(client: TestClient) -> None:
    """Doc 04 §6 rule 1. A tile with an outline and no sentence is the failure
    state that rule exists to prevent."""
    for director in DIRECTORS:
        for offering in director.offerings:
            if not offering.needs:
                continue
            sentence = unlock_sentence(offering, connected=frozenset())
            assert sentence, f"{offering.id} {offering.name} states no unlock"
            assert sentence.endswith("."), f"{offering.id} unlock is not a sentence"


def test_no_tile_carries_a_number(client: TestClient) -> None:
    """I10 — never a zero, and here not any figure at all.

    `phase` is the one integer, and it is a roadmap marker rather than a
    measurement, so it is named explicitly instead of being allowed through by a
    loose check.
    """
    as_role(client, caller(Role.OWNER, {Department.EXECUTIVE}))

    for director in DIRECTORS:
        payload: dict[str, Any] = client.get(f"/dashboards/{director.department.value}").json()
        for tile in payload["offerings"]:
            numeric = {
                key: value
                for key, value in tile.items()
                if isinstance(value, (int, float)) and not isinstance(value, bool)
            }
            assert set(numeric) <= {"phase"}, f"{tile['id']} carries a figure: {numeric}"


def test_every_department_has_a_director() -> None:
    """ADR 0010 — all seven get a page, not the two doc 07 schedules."""
    assert set(BY_DEPARTMENT) == set(Department)


def test_the_two_synthesis_directors_are_never_scored() -> None:
    """Doc 05 §10 — which is why the composite is out of six, not seven."""
    unscored = {d.department for d in DIRECTORS if not d.scoreable}
    assert unscored == {Department.EXECUTIVE, Department.STRATEGY}


def test_a_director_the_list_omits_cannot_be_opened_directly() -> None:
    """Finding #21. The list and the detail must agree about what exists.

    `GET /dashboards` filters to the departments the company chose at stage 4.
    `GET /dashboards/{department}` checked only whether the caller *holds* the
    department — and an owner holds all seven — so People was absent from the
    list and served at its own URL. Two endpoints contradicting each other
    about what a company runs, and a place to write answers no surface reads
    back.
    """
    from app.routes.dashboards import running_departments

    app = create_app()
    _override_departments(app)
    # Finance *and* the Chief of Staff, because `selected_departments` always
    # includes the latter — a set of one means the company has chosen nothing,
    # and then every director is shown on purpose.
    app.dependency_overrides[running_departments] = lambda: frozenset(
        {Department.FINANCE, Department.EXECUTIVE}
    )

    with TestClient(app) as client:
        as_role(client, caller(Role.OWNER, {Department.FINANCE}))

        assert client.get("/dashboards/finance").status_code == 200
        listed = {d["department"] for d in client.get("/dashboards").json()["directors"]}
        assert "hr" not in listed

        assert client.get("/dashboards/hr").status_code == 404, (
            "the list omits it, so opening it directly must 404 too"
        )

    app.dependency_overrides.clear()


# ── The rail (`doc/13` §4, step C) ────────────────────────────


def test_a_director_serves_a_rail_and_not_only_a_flat_list(client: TestClient) -> None:
    """`doc/08` §4C: Overview, Cash & runway, Receivables, Payables, Approvals.

    The flat `offerings` list is still served while the web adopts this — two
    shapes of one list, and the older one goes when nothing reads it.
    """
    as_role(client, caller(Role.OWNER, {Department.FINANCE}))
    body = client.get("/dashboards/finance").json()

    assert body["offerings"], "the flat catalogue is still there"

    labels = [section["label"] for section in body["sections"]]
    assert labels[0] == "Overview", "the rail is ordered, not sorted"
    assert "Cash & runway" in labels
    assert "Payables" not in labels, (
        "doc 08 draws Payables and no capability fills it yet — a tab somebody"
        " clicks into to find nothing is worse than a tab that is not there"
    )


def test_every_block_names_which_of_the_nine_components_draws_it(
    client: TestClient,
) -> None:
    """The section is the unit of navigation, the block is the unit of
    rendering. A block with no kind has no defined behaviour when its source
    disconnects."""
    as_role(client, caller(Role.OWNER, {Department.FINANCE}))
    body = client.get("/dashboards/finance").json()

    blocks = [block for section in body["sections"] for block in section["blocks"]]
    assert blocks

    for block in blocks:
        assert block["block"], block["key"]
        assert block["key"].startswith("finance."), "namespaced by department (ADR 0020)"

        if block["state"] == "planned":
            # An unbuilt widget cannot be unlocked by connecting anything, so it
            # offers nothing — but the API still carries the sentence, and the
            # card is what withholds it.
            assert block["unlock"], "doc 04 §6 rule 1 — every tile states its unlock"
        else:
            # Step D's Setup tab. It reads answers the founder already gave, so
            # it needs no source and has no unlock to state — and an unlock here
            # would be an instruction to supply the thing it exists to show back.
            assert block["key"] == "finance.setup"
            assert block["state"] == "live"
            assert block["unlock"] == ""


def test_the_catalogue_is_served_apart_from_the_rail(client: TestClient) -> None:
    """`doc/08` §11's deliberate gaps: real capabilities with no section in this
    cut. Shown apart and labelled as planned, because they are neither locked
    nor coming."""
    as_role(client, caller(Role.OWNER, {Department.FINANCE}))
    body = client.get("/dashboards/finance").json()

    catalogue = {block["key"] for block in body["catalogue"]}
    railed = {block["key"] for section in body["sections"] for block in section["blocks"]}

    assert catalogue, "doc 05 is wider than doc 08's cut"
    assert not (catalogue & railed), "a capability is on the rail or in the catalogue, never both"
    assert "finance.business_simulator" in catalogue


def test_the_assistant_panel_is_reserved_and_names_what_it_will_answer(
    client: TestClient,
) -> None:
    """Q67. A blank region where a feature is coming reads as a bug and a fake
    one reads as a lie, so the panel names the director and lists the questions
    it will answer — `doc/08` §4E, in the customer's own words."""
    as_role(client, caller(Role.OWNER, {Department.FINANCE}))
    assistant = client.get("/dashboards/finance").json()["assistant"]

    assert assistant["available"] is False
    assert assistant["director"] == "AI Finance Advisor"
    assert "What is our cash position?" in assistant["questions"]


def test_a_department_the_caller_cannot_reach_serves_no_rail(client: TestClient) -> None:
    """Reach decides presence, and it decides it for the rail too. The sections
    are computed after `enforce_department`, so a 404 carries no tab names —
    which would disclose how the company is organised."""
    as_role(client, caller(Role.DEPARTMENT_MANAGER, {Department.OPERATIONS}))
    response = client.get("/dashboards/finance")

    assert response.status_code == 404
    assert "sections" not in response.json()


# ── Step D: the Setup tab is lazily loaded, and gated the same ─


def test_setup_refuses_a_department_the_caller_cannot_open(client: TestClient) -> None:
    """The bug a lazily-loaded tab invites.

    The rail is served without a database round trip and the Setup tab fetches
    its own content, which means there are now **two doors** into a
    department's data. A caller who gets 404 on the director page must get 404
    here, in the same order, for the same reason.
    """
    as_role(client, caller(Role.DEPARTMENT_MANAGER, {Department.OPERATIONS}))

    assert client.get("/dashboards/finance").status_code == 404
    assert client.get("/dashboards/finance/setup").status_code == 404


def test_setup_refuses_the_chief_of_staff_to_a_manager(client: TestClient) -> None:
    """Doc 06 §2.4, through the second door. The executive check is a different
    rule with a different answer — the Chief of Staff is not a department
    somebody might be added to, so naming the requirement is safe."""
    as_role(client, caller(Role.DEPARTMENT_MANAGER, {Department.SALES}))

    assert client.get("/dashboards/executive/setup").status_code == 403


def test_the_rail_no_longer_carries_the_setup_content(client: TestClient) -> None:
    """Finding #23 is that `GET /dashboards` already spends 25 to 30 round trips.
    The fix for that is not to add a context assembly to every director page —
    most visits never open Setup."""
    as_role(client, caller(Role.OWNER, {Department.FINANCE}))
    body = client.get("/dashboards/finance").json()

    setup = next(s for s in body["sections"] if s["key"] == "setup")
    assert "facts" not in setup
    assert setup["available"] == 1, "the tab reports that it has something on it"


def test_the_page_can_tell_which_tab_has_something_on_it(client: TestClient) -> None:
    """What `available` is for. Opening on Overview would greet a new customer
    with five tiles that all say "not built yet", when the one tab with content
    is two along."""
    as_role(client, caller(Role.OWNER, {Department.FINANCE}))
    sections = client.get("/dashboards/finance").json()["sections"]

    with_content = [s["key"] for s in sections if s["available"] > 0]

    assert with_content == ["setup"], (
        "on a day-one dashboard Setup is the only tab with anything on it"
    )
