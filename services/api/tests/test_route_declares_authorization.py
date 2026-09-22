"""Every route either declares authorization or is explicitly allowlisted.

This is the guard that keeps A-01..A-05 from regressing silently: a new route
added without `CurrentScope`, `CurrentSession` or an equivalent dependency is a
route nobody checked, and it is easy to miss in review because the missing
thing is the absence of a line rather than the presence of a wrong one.

**"Declares authorization" means the route's dependency graph — `dependant`,
walked recursively through every `Depends()` including parameter-injected ones
like `scope: CurrentScope` — reaches one of the auth dependencies in
`app.deps`: `current_scope` (workspace + role scope, most routes),
`current_session` (identity only, for the pre-workspace window),
`current_user_id` (identity only, narrower still) or
`require_executive_surface` (which itself depends on `current_scope`, so this
is really belt-and-braces).** `may_administer`/`may_write`-style checks are
not separately recognised because every one of them today is called on a
`scope: CurrentScope` the route already received as a parameter — so the
`CurrentScope` dependency is what this test actually sees, and the coarse-vs-
fine distinction `security-and-authz` draws (router does the coarse gate,
service/route body does the decision) is preserved: this test only asks
whether the *caller's identity* was established, never whether the right
decision was then made with it.

No route is exempt by name or by module — the exemption is a closed,
commented allowlist keyed on `(method, path)`, read from this file. A route
this test has never seen before is guilty until proven public.
"""

from __future__ import annotations

from typing import Final

import pytest
from fastapi.routing import APIRoute

from app.deps import current_scope, current_session, current_user_id, require_executive_surface
from app.main import create_app

# The callables that count as "this route knows who is calling". Walked
# transitively, so a route depending on `require_executive_surface` is found
# through its own dependency on `current_scope` even without the explicit
# entry here — this is belt-and-braces, not the only path.
_AUTH_DEPENDENCIES: Final = frozenset(
    {current_scope, current_session, current_user_id, require_executive_surface}
)

# ── The allowlist ────────────────────────────────────────────
#
# Every entry names the route and says, in one line, why it is intentionally
# reachable with no session. Keyed on `(method, path)` — the path exactly as
# FastAPI reports it, template segments and all — rather than on the function
# name, because the function name is not what a client sends.
_ALLOWED_PUBLIC_ROUTES: Final = frozenset(
    {
        # Liveness/readiness probes. `observability-and-logging`: neither may
        # require authentication, and neither returns anything an attacker
        # could use — no dependency versions, no hostnames.
        ("GET", "/health"),
        ("GET", "/health/ready"),
        # Credential endpoints — there is no session to check yet, or the
        # request's whole purpose is to establish or replace one. Every one
        # of these is separately rate-limited (`security-and-authz`'s
        # per-account/per-source rule) inside the handler.
        ("POST", "/auth/register"),
        ("POST", "/auth/login"),
        ("POST", "/auth/password-reset/request"),
        ("POST", "/auth/password-reset/confirm"),
        ("POST", "/auth/verify-email"),
        # Logout reads the session cookie itself (optionally — a missing or
        # already-invalid cookie is a no-op, not a 401) rather than depending
        # on `current_session`. Idempotent and safe to call unauthenticated:
        # there is nothing an anonymous caller gains by hitting it, and CSRF
        # still applies (`dependencies=[Depends(require_csrf)]`).
        ("POST", "/auth/logout"),
        # A fixed, non-tenant list of the seven department names, served
        # before a workspace exists so the registration form has something to
        # render. `list_departments`'s own docstring: "a fixed list of seven
        # English nouns ... with no tenant data in it and nothing to leak."
        ("GET", "/departments"),
        # The anonymous Instant Gap Analysis surface, ADR 0046. Declares no
        # session dependency deliberately — a visitor gets three real gaps
        # before signing up — and is rate-limited per-IP/per-domain/globally
        # instead. `app/routes/scan.py`'s module docstring is the ADR pointer.
        ("POST", "/public/scans"),
        ("GET", "/public/scans/{scan_id}"),
        ("DELETE", "/public/scans/{scan_id}"),
        # The one signed-URL route in the product. Authorization already
        # happened once, at `/documents/{id}/download`, which minted this URL
        # against the uploader's session; the signature covering the key and
        # the expiry *is* the authorization here, checked inside the handler
        # rather than via a session dependency. `app/routes/files.py`'s
        # module docstring: "Unauthenticated on purpose, and that is the
        # whole design."
        ("GET", "/files/{key:path}"),
        # `POST /domains`, `POST /domains/{claim_id}/check` and
        # `POST /domains/{claim_id}/workspace` all DO require a signed-in
        # caller — `_require_user(nexus_session)` in `app/routes/onboarding.py`
        # 401s on a missing or expired session exactly as `current_session`
        # does. They are allowlisted here not because they are public but
        # because they read the `nexus_session` cookie as a bare parameter and
        # call `resolve_session` inline, rather than going through the
        # `current_scope`/`current_session` FastAPI dependency this test can
        # see. That is a real inconsistency with the rest of the codebase's
        # DI-based auth and worth a follow-up to route through
        # `CurrentSession` — flagged rather than fixed here, since it is a
        # refactor of working auth code outside this test's scope. It is not
        # the A-01..A-05 regression this test exists to catch: every one of
        # the three 401s a request with no cookie.
        ("POST", "/domains"),
        ("POST", "/domains/{claim_id}/check"),
        ("POST", "/domains/{claim_id}/workspace"),
    }
)


def _reaches_an_auth_dependency(dependant: object, seen: set[int] | None = None) -> bool:
    """Whether this dependant, or anything it depends on, is one of ours.

    Recursive rather than a single-level check: `require_executive_surface`'s
    own dependant is what carries `current_scope`, not the route's top-level
    one, and a route depending on it only indirectly would otherwise read as
    ungated. `seen` guards against a dependency graph FastAPI has already
    deduplicated by `use_cache` looping back on itself.
    """
    seen = seen if seen is not None else set()
    if id(dependant) in seen:
        return False
    seen.add(id(dependant))

    if getattr(dependant, "call", None) in _AUTH_DEPENDENCIES:
        return True
    return any(
        _reaches_an_auth_dependency(sub, seen) for sub in getattr(dependant, "dependencies", [])
    )


def _api_routes() -> list[APIRoute]:
    """Every `APIRoute` in the app, found by walking the routing tree.

    `app.routes` no longer holds a flat list on this FastAPI — `include_router`
    wraps each mounted router in an `_IncludedRouter` whose actual routes sit
    on `.original_router.routes`. Recursing through both that and the ordinary
    `.routes` attribute is what makes this survive a router nested inside a
    router, which does not happen here today but would otherwise silently stop
    this test from seeing anything mounted that way.
    """
    routes: list[APIRoute] = []

    def _walk(nodes: object) -> None:
        for node in nodes:  # type: ignore[attr-defined]
            if isinstance(node, APIRoute):
                routes.append(node)
                continue
            sub_router = getattr(node, "original_router", None)
            if sub_router is not None:
                _walk(sub_router.routes)
            elif hasattr(node, "routes"):
                _walk(node.routes)

    _walk(create_app().routes)
    return routes


def test_every_route_declares_authorization_or_is_explicitly_allowlisted() -> None:
    routes = _api_routes()
    assert routes, "found no APIRoute at all — the walk itself is broken"

    unguarded = [
        (sorted(route.methods or set()), route.path, route.name)
        for route in routes
        for method in sorted(route.methods or set())
        if not _reaches_an_auth_dependency(route.dependant)
        and (method, route.path) not in _ALLOWED_PUBLIC_ROUTES
    ]

    assert not unguarded, (
        "route(s) with no authorization dependency and no allowlist entry — "
        "either add the missing `CurrentScope`/`CurrentSession` dependency, "
        "or add a commented entry to `_ALLOWED_PUBLIC_ROUTES` explaining why "
        f"it is intentionally public: {unguarded}"
    )


def test_the_allowlist_contains_no_stale_entries() -> None:
    """A route that stopped existing, or that gained a real auth dependency,
    should have its allowlist entry removed rather than left to shrink the
    set of routes this test actually checks."""
    routes = _api_routes()
    live = {(method, route.path) for route in routes for method in sorted(route.methods or set())}

    stale = _ALLOWED_PUBLIC_ROUTES - live
    assert not stale, f"allowlist entries with no matching route: {stale}"


@pytest.mark.parametrize(
    ("method", "path"),
    sorted(_ALLOWED_PUBLIC_ROUTES),
)
def test_allowlisted_route_is_still_undeclared(method: str, path: str) -> None:
    """The inverse check: an allowlist entry for a route that has since grown
    a real auth dependency is a stale exemption hiding a route that no longer
    needs it — harmless today, but worth catching so the allowlist stays a
    true list of what is public rather than a ratchet that only grows."""
    routes = {
        (m, route.path): route for route in _api_routes() for m in sorted(route.methods or set())
    }
    route = routes.get((method, path))
    assert route is not None, f"{method} {path} is allowlisted but no longer exists"
