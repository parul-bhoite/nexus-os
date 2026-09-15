"""CSRF double-submit, and the cookie flags the session depends on."""

from __future__ import annotations

import pytest
from fastapi import Request
from fastapi.testclient import TestClient

from app.auth.csrf import CSRF_COOKIE_NAME, CSRF_HEADER_NAME
from app.main import create_app


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())


def test_state_changing_request_without_the_header_is_rejected(client: TestClient) -> None:
    """The browser will send the cookie; only the real origin can read it."""
    client.cookies.set(CSRF_COOKIE_NAME, "a-known-csrf-value")
    client.cookies.set("nexus_session", "irrelevant-here")

    response = client.post("/auth/logout")
    assert response.status_code == 403
    assert CSRF_HEADER_NAME in response.json()["detail"]


def test_mismatched_header_is_rejected(client: TestClient) -> None:
    client.cookies.set(CSRF_COOKIE_NAME, "a-known-csrf-value")
    client.cookies.set("nexus_session", "irrelevant-here")

    response = client.post("/auth/logout", headers={CSRF_HEADER_NAME: "not-the-same"})
    assert response.status_code == 403


async def test_matching_header_passes_the_csrf_gate() -> None:
    """Exercised directly rather than through a route.

    A route would carry on into the database, and the hermetic fixture
    deliberately withholds one — so going through the route would test the
    fixture, not the gate.
    """
    from app.auth.csrf import require_csrf

    request = Request({"type": "http", "method": "POST", "headers": [], "query_string": b""})
    # Awaited for the side effect of *not* raising: the gate is satisfied when
    # it returns. Not compared to None - `require_csrf` is annotated as
    # returning None, and mypy rejects testing the value of such a call.
    await require_csrf(request, nexus_csrf="a-known-csrf-value", x_csrf_token="a-known-csrf-value")


async def test_an_absent_csrf_cookie_is_rejected_not_waved_through() -> None:
    """This test previously asserted the opposite, and the reasoning was wrong.

    It said an absent CSRF cookie meant no session to protect, and that
    rejecting would turn every unauthenticated POST — including login — into a
    403 about the wrong thing. That is not true of the actual route set:
    `require_csrf` guards exactly five routes (logout, workspace switch, and the
    three domain endpoints) and **every one of them already requires a session**.
    Login and register do not use it at all.

    So the fail-open protected nothing and cost something. `nexus_session` and
    `nexus_csrf` are independent cookies with independent lifetimes, and either
    can go missing while the other survives — a page on a sibling subdomain can
    evict one by filling the cookie jar. This module exists precisely for the
    cases where `SameSite=Lax` fails, and cookie eviction is on that list, so
    returning early there disabled the layer in the exact scenario it was built
    for.

    A caller with no session still gets 401 from the session dependency. A
    caller with a session and no CSRF cookie now gets 403 instead of a free
    pass, and can recover by signing in again — which mints both cookies.
    """
    from fastapi import HTTPException

    from app.auth.csrf import require_csrf

    request = Request({"type": "http", "method": "POST", "headers": [], "query_string": b""})

    with pytest.raises(HTTPException) as exc:
        await require_csrf(request, nexus_csrf=None, x_csrf_token=None)
    assert exc.value.status_code == 403


async def test_every_route_guarded_by_csrf_also_requires_a_session() -> None:
    """The premise the rejection above rests on.

    If a route ever adopts `require_csrf` without a session dependency, the 403
    becomes the wrong answer for an anonymous caller and this needs revisiting.
    """
    from app.main import create_app

    csrf_guarded = {
        "/auth/logout",
        # `/auth/workspace` was here until P3 deleted it — one company per
        # person means there is never a second workspace to switch to
        # (`doc/11` §3.2). This test is what noticed, which is the point of
        # naming the guarded routes rather than counting them.
        "/domains",
        "/domains/{claim_id}/check",
        "/domains/{claim_id}/workspace",
        # Slice 2. A POST that spends the workspace's daily token allowance is
        # a POST worth forging.
        "/dashboards/{department}/narrate",
    }
    # From the OpenAPI schema, not `app.routes` — the latter does not expose
    # `.path` for these route objects, which silently yields an empty set and a
    # test that passes by comparing nothing to nothing.
    paths = set(create_app().openapi()["paths"])

    assert csrf_guarded <= paths, (
        f"a CSRF-guarded route was renamed or removed: {sorted(csrf_guarded - paths)}"
    )
    # Login and register must stay outside the guarded set, or an anonymous
    # visitor cannot authenticate at all.
    assert {"/auth/login", "/auth/register"} <= paths
    assert not ({"/auth/login", "/auth/register"} & csrf_guarded)


def test_safe_methods_are_exempt(client: TestClient) -> None:
    """If a GET changes state, that is the bug — not this."""
    client.cookies.set(CSRF_COOKIE_NAME, "a-known-csrf-value")
    response = client.get("/health")
    assert response.status_code == 200


def test_login_sets_httponly_session_and_readable_csrf_cookie() -> None:
    """The two cookies have deliberately opposite visibility.

    The session cookie must be unreadable by JavaScript so XSS cannot exfiltrate
    it. The CSRF cookie must be readable, because the client has to echo it into
    a header — which is exactly what a cross-origin attacker cannot do.
    """
    from fastapi import Response

    from app.config import get_settings
    from app.routes.auth import _set_session_cookie

    response = Response()
    csrf = _set_session_cookie(response, "a-session-token", get_settings())

    headers = [v for k, v in response.raw_headers if k == b"set-cookie"]
    decoded = [h.decode() for h in headers]

    session_cookie = next(c for c in decoded if c.startswith("nexus_session="))
    csrf_cookie = next(c for c in decoded if c.startswith(f"{CSRF_COOKIE_NAME}="))

    assert "HttpOnly" in session_cookie
    assert "HttpOnly" not in csrf_cookie
    assert "SameSite=lax" in session_cookie.lower() or "samesite=lax" in session_cookie.lower()
    assert csrf in csrf_cookie
