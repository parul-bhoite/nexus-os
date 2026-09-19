"""No anonymous route can reach a metered or credentialed fetch.

Phase 2 retired the unauthenticated Preview audit and moved its engine into
`app/research/`. Deleting the route removes that exposure; this test is what
stops the next one from being added by accident.

**Rewritten by ADR 0046.** The rule used to be absolute and package-shaped: no
anonymous route may reach `app.research` at all. ADR 0046 re-cuts it around the
property that actually made that package dangerous — being metered or holding a
credential — because `app/connectors/` (provider credentials, migration `0030`)
and `app/ai/` (a metered key, ADR 0011) have since grown the same danger outside
`app.research`, and the old rule did not see either of them. A rule that still
named the package in 2026 would forbid the cheap thing and permit the expensive
one.

**The rule now:** a route that does not require an authenticated session must
not be able to reach, at any import depth: `app.connectors.*` (except
`rate_limit`, which counts requests and holds no credential), `app.ai.*`,
`app.embeddings.*`, `app.retrieval.*` (it takes a `ScopedSession`; an anonymous
route reaching it is a tenancy failure whatever it costs), or
`app.research.runner` / `app.research.worker_loop` (the budgeted, workspace-
owned research run — D20).

**What this file no longer forbids:** `app.research.crawler` and
`app.research.extract` are not in the forbidden set here. They are not free —
`tests/test_scan_boundary.py` (ADR 0046) is the tighter, second test that pins
the *only* anonymous surface allowed to reach them, `app.scan.*` via
`app.routes.scan`, to an allowlist. This file states what nothing anonymous may
ever reach; that file states the one narrow exception and bounds it.

This replaces `test_preview_scope.py`, which asserted the *reduced* shape of the
one unauthenticated audit. That test could only describe the endpoint it was
written for. This one describes every endpoint that will ever exist.

**"Anonymous" here means "declares no session dependency", which is stricter
than "requires no session".** `app/routes/onboarding.py` resolves the session
itself, reading the cookie inside `_require_user` rather than depending on
`CurrentSession`, so three of its four routes are authenticated in fact and
anonymous to any structural check — including this one. That is treated as
anonymous rather than argued away: a check that cannot see an authentication
decision cannot rely on it, and the fix is to declare the dependency.

**The walk is static, over the source, not over `sys.modules`.** A runtime check
sees only what the test session happened to import, and would go quiet exactly
when a new import path was added. An `ast` walk sees the import whether or not
anything calls it — this remains true at the *file* level (the graph in
`_import_graph`/`_reachable_from`, used as the fallback below); the per-route
walk added below is usage-based (does the function's own body reference the
name), not import-presence-based, which is what makes it precise enough to
stop charging `read_preferences` with `/auth/login`'s file. An import bound to
a name the function never references at all would slip past *this* file, but
not past `ruff` — an unused import is `F401`, caught by the same gate every
other unused import is.

**The walk is per route, not per file — this was tightened alongside the ADR
0046 rewrite, and here is why.** Broadening the forbidden set from `app.research`
to metered-or-credentialed immediately failed on real code: `app/health.py`,
`app/routes/auth.py`, `app/routes/companies.py` and `app/routes/onboarding.py`
all mix an anonymous route with an authenticated one in the same file, and the
old walk treated a whole file's imports as reachable from any route in it —
`read_preferences`/`update_preferences` in `auth.py` properly declare
`scope: CurrentScope`, but the old walk still charged their `retrieval.scoped`
usage against `/auth/login` in the same file, because nothing before now made it
tell the two apart. Under the narrower old rule this coarseness never showed,
because nothing legitimate in those files reached `app.research`. It is not
hypothetical once the forbidden set includes anything a normal route touches.

So reachability starts from the **specific endpoint function** and follows every
call this walk can resolve to another function's own source — same module or a
different one, recursively — falling back to a target's whole module (via
`_reachable_from`, the original coarse behaviour) only once a name does not
resolve to a function this walk can read: a class, a constant, or a module with
no source file. That fallback is still real and still coarse; it is just no
longer the *first* thing tried, which is what let `app.domain.departments`'s
`label_for` — a pure enum-to-string lookup — stop being charged with the
`apply_workspace_scope` call an unrelated function in the same file makes.

Four exemptions came out of running this for real, each named rather than
carved out by module:

- `app.ai.registry.provider_status`, `app.embeddings.registry.embedder_status`
  — config introspection wrapped in `try/except`, never a call to the provider
  itself. ADR 0011 states the design outright: `/health/ready` reports
  `language_model: unconfigured` and must not depend on a session to say so.
- `app.connectors.domain_check` (the whole module) — proving a domain claim by
  fetching a well-known file, SSRF-guarded, pre-existing and already anonymous.
  The old rule never forbade it; it is not under `app.research`. ADR 0046 was
  written about the scanner and did not consider it.
- `app.retrieval.scoped.apply_user_scope`, `apply_workspace_scope` — setters,
  not fetchers. Login, registration and onboarding call these directly to
  establish the scope of the identity they have *just* verified; there is no
  session yet to declare as a dependency, because creating one is the route's
  purpose. `scoped_connection` and everything else that reads tenant data stays
  forbidden.

None of these were anticipated by ADR 0046 when it named `app.connectors.*` and
`app.retrieval.*` wholesale — the ADR reasoned about the scanner it was written
for, and the boundary it re-cut turned out to graze three working features it
never considered. That is not a defect in the ADR's decision, which stands; it
is what "run the acceptance test for real" is for.
"""

from __future__ import annotations

import ast
from collections.abc import Iterator
from functools import cache
from pathlib import Path

from fastapi.routing import APIRoute

from app.deps import current_scope, current_session
from app.main import create_app

APP_DIR = Path(__file__).resolve().parents[1] / "app"

# The two dependencies that establish who is calling. `current_session` proves
# an identity; `current_scope` proves an identity *and* a workspace. Either is
# enough to make a route non-anonymous, which is what this file is about.
AUTHENTICATING = frozenset({current_scope, current_session})

# The forbidden set, per ADR 0046: metered or credentialed, not "in
# app.research". Each prefix names the property that makes it dangerous, and
# the comment beside it is that property, not a description of the module.
FORBIDDEN_PREFIXES: tuple[str, ...] = (
    "app.connectors.",  # credentials, OAuth, provider adapters — except rate_limit, below
    "app.ai.",  # metered (ADR 0011)
    "app.embeddings.",  # ~2GB of weights, and a cost even when the model is absent
    "app.retrieval.",  # takes a ScopedSession — reaching it anonymously is a tenancy failure
)

# The single exemption inside a forbidden prefix: rate_limit counts requests
# and holds no credential. It is what bounds the anonymous surface this file
# now permits elsewhere (ADR 0046) — forbidding it would leave that surface
# with no limiter to use.
RATE_LIMIT_EXEMPTION = "app.connectors.rate_limit"

# A second exemption inside `app.connectors.`: proving a domain claim by
# fetching a well-known file, pre-existing and already anonymous — the old
# rule never forbade it, because it is not under `app.research`. It is
# SSRF-guarded (the same guard the scan module will use) and unrelated to
# ADR 0046, which was written about the scanner and did not consider it.
DOMAIN_CHECK_EXEMPTION = "app.connectors.domain_check"

# The budgeted, workspace-owned research run. Not under a forbidden prefix
# above, so it is named directly: it belongs to a workspace (D20) and an
# anonymous route reaching it is the same tenancy failure as reaching
# `app.retrieval`, just spelled with a different package.
FORBIDDEN_EXACT: tuple[str, ...] = (
    "app.research.runner",
    "app.research.worker_loop",
)

# The two exemptions inside `app.retrieval.`: setters, not fetchers. Login,
# registration and onboarding call these directly to establish the scope of
# the identity they have *just* verified — there is no session yet to declare
# as a dependency, because establishing one is the route's whole purpose.
# `scoped_connection` and everything else in `app.retrieval.*` that reads
# tenant data stays forbidden; setting a GUC for the caller's own just-proven
# identity is not the tenancy failure the general rule exists to catch.
RETRIEVAL_SCOPE_SETTER_EXEMPTIONS = frozenset(
    {
        "app.retrieval.scoped.apply_user_scope",
        "app.retrieval.scoped.apply_workspace_scope",
    }
)

# `app.research.crawler` and `app.research.extract` are deliberately NOT
# forbidden here as of ADR 0046 — see the module docstring. They are bounded
# instead by tests/test_scan_boundary.py's allowlist for app.scan.*.

# Named, not modular: `provider_status`/`embedder_status` inspect configuration
# and never call the provider they report on (ADR 0011). Exempting the module
# would exempt anything else added to it later; exempting the symbol exempts
# exactly what was checked.
STATUS_INTROSPECTION_EXEMPTION = frozenset(
    {
        "app.ai.registry.provider_status",
        "app.embeddings.registry.embedder_status",
    }
)


def _module_name(path: Path) -> str:
    relative = path.relative_to(APP_DIR).with_suffix("")
    parts = [p for p in relative.parts if p != "__init__"]
    return ".".join(["app", *parts])


def _imports_of(path: Path) -> set[str]:
    """Every `app.*` module this file names, whether or not it uses it."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names if alias.name.startswith("app."))
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            if not node.module.startswith("app"):
                continue
            found.add(node.module)
            # `from app.research import crawler` names a module in the alias,
            # not in `node.module` — miss this and a package-level import of the
            # crawler reads as an import of the package only.
            found.update(f"{node.module}.{alias.name}" for alias in node.names)

    return found


def _import_graph() -> dict[str, set[str]]:
    return {_module_name(path): _imports_of(path) for path in sorted(APP_DIR.rglob("*.py"))}


def _module_path(module: str) -> Path:
    """The inverse of `_module_name`: `app.retrieval.scoped` -> its file."""
    parts = module.split(".")[1:]  # drop the leading "app"
    as_module = APP_DIR.joinpath(*parts).with_suffix(".py")
    if as_module.exists():
        return as_module
    as_package = APP_DIR.joinpath(*parts, "__init__.py")
    if as_package.exists():
        return as_package
    raise FileNotFoundError(f"no source file for module {module!r}")


@cache
def _parsed(module: str) -> ast.Module:
    path = _module_path(module)
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


@cache
def _alias_map(module: str) -> dict[str, str]:
    """Local name -> the fully-qualified `app.*` symbol it refers to, collected
    from every import in the file regardless of nesting — `app/health.py`'s
    imports live inside the function body, not at module level, and both must
    resolve the same way."""
    aliases: dict[str, str] = {}
    for node in ast.walk(_parsed(module)):
        if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            if not node.module.startswith("app"):
                continue
            for alias in node.names:
                aliases[alias.asname or alias.name] = f"{node.module}.{alias.name}"
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("app."):
                    # A bare `import app.x.y` binds the top-level name `app` and
                    # is reached through attribute access this map does not
                    # resolve. Rare here (the codebase overwhelmingly uses
                    # `from app.x import y`) — fall back to treating the name
                    # as always used, which is the old, coarser behaviour and
                    # never less safe than the precision below.
                    aliases[alias.asname or alias.name.split(".")[0]] = alias.name

    return aliases


@cache
def _function_defs(module: str) -> dict[str, ast.AST]:
    return {
        node.name: node
        for node in ast.walk(_parsed(module))
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def _referenced_symbols(fn: ast.AST, aliases: dict[str, str]) -> set[str]:
    """Every `app.*` symbol this function's body names, resolving `alias.attr`
    (`from app.domain import audit` then `audit.record(...)`) to
    `app.domain.audit.record`, not the bare `app.domain.audit` a plain-`Name`
    walk would stop at. `logout` calling `audit.record`, which itself calls the
    already-exempt `apply_workspace_scope`, only resolves cleanly once this
    walk can tell `audit.record` from `audit.anything_else`.

    A `Name` consumed as the base of a resolved attribute is not *also*
    returned bare — `audit.record` must not register a second, module-only use
    of `audit` that a bare-name lookup would immediately fall back on.
    """
    consumed: set[int] = set()
    symbols: set[str] = set()

    for node in ast.walk(fn):
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            base = aliases.get(node.value.id)
            if base is not None:
                symbols.add(f"{base}.{node.attr}")
                consumed.add(id(node.value))

    for node in ast.walk(fn):
        if isinstance(node, ast.Name) and id(node) not in consumed:
            symbols.add(node.id)

    return symbols


def _resolve_symbol_function(symbol: str) -> tuple[str, str] | None:
    """If `symbol` (e.g. `app.domain.departments.label_for`) names a function
    defined in that module, `(module, func_name)`; otherwise `None`.

    A class, a constant, or a symbol this walk cannot parse (no source file —
    a third-party or namespace package) returns `None`, and the caller falls
    back to that module's whole import surface, exactly as `_reachable_from`
    always has. A resolvable function is instead followed into its own body,
    which is what stops the walk mistaking "this pure lookup's module also
    contains an unrelated scoped write" for the lookup itself doing one —
    `label_for` and `apply_workspace_scope` sit in the same file, and only one
    of them touches `app.retrieval`.
    """
    module, _, name = symbol.rpartition(".")
    if not module.startswith("app"):
        return None
    try:
        functions = _function_defs(module)
    except FileNotFoundError:
        return None
    return (module, name) if name in functions else None


_INERT_BASES = frozenset(
    {
        # Fixed values — a member read runs no code.
        "Enum",
        "StrEnum",
        "IntEnum",
        "Flag",
        "IntFlag",
        # Control-flow signals — raising one runs only the base constructor,
        # *provided* the subclass adds no method of its own. `AuthError` and
        # `EmailAlreadyRegisteredError` are both `class X(Exception): pass`
        # (or a docstring in place of `pass`) — nothing to execute beyond
        # storing the arguments `Exception.__init__` always stores.
        "Exception",
        "BaseException",
    }
)


def _is_inert_class(module: str, class_name: str, _seen: frozenset[str] = frozenset()) -> bool:
    """A class cannot make an anonymous route reach `app.*` merely by being
    named, instantiated, or having a member read off it, *provided* none of
    its own methods reference an `app.*` symbol themselves. `AuditAction.LOGIN`
    runs no code at all; `UserAlreadyInAWorkspaceError.__init__` runs one, but
    that method only formats a default string and calls `super().__init__` —
    checked directly against its own AST node, not by a by-name lookup that
    could collide with an unrelated class's `__init__` elsewhere.

    Still restricted to the closed base-class set above, kept as a second,
    independent narrowing: a class with no `app.*`-touching method today could
    still be a Pydantic model or similar whose validators run on
    construction — this file does not attempt to know that a base class adds
    no behaviour of its own, only that *this* codebase's own code does not.

    Follows a same-module base chain — `DomainDisputedError(DomainClaimError)`
    is inert because `DomainClaimError(Exception)` is — but does not cross a
    module boundary to do it: a base imported from elsewhere falls back to the
    coarse check for that module, same as any other unresolved symbol.
    """
    if class_name in _seen:
        return False
    try:
        tree = _parsed(module)
    except FileNotFoundError:
        return False
    aliases = _alias_map(module)
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            methods = [
                n for n in node.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
            ]
            method_names = {n.id for m in methods for n in ast.walk(m) if isinstance(n, ast.Name)}
            if method_names & aliases.keys():
                return False
            bases = {b.id for b in node.bases if isinstance(b, ast.Name)}
            if bases & _INERT_BASES:
                return True
            seen = _seen | {class_name}
            return any(_is_inert_class(module, base, seen) for base in bases)
    return False


def _is_inert_class_reference(symbol: str) -> bool:
    """`symbol` may be `module.Class` (the class itself referenced or raised)
    or `module.Class.MEMBER` (one member read off it, e.g.
    `Availability.DISABLED` reached through `from app.ai.contracts import
    Availability` then `Availability.DISABLED`). Try the member-access split
    first — the more specific interpretation — then the class-only split.
    """
    parts = symbol.split(".")
    for split in (-2, -1):
        if len(parts) + split < 2:
            continue
        module, class_name = ".".join(parts[:split]), parts[split]
        if module.startswith("app") and _is_inert_class(module, class_name):
            return True
    return False


def _locally_reachable_app_symbols(
    module: str, func_name: str, _seen: frozenset[str] = frozenset()
) -> tuple[set[str], set[str]]:
    """`(every app.* symbol referenced, the subset this walk could not resolve
    to a function)`.

    Following any call this walk can resolve to another function's own
    source — same module or a different one — recursively, so a name that
    *did* resolve is fully traced and must not also trigger the coarse
    whole-module fallback: that is the earlier bug, where resolving
    `apply_user_scope` precisely still let its *module* — which also holds
    `scoped_connection` — get charged back against the caller because every
    symbol, resolved or not, went through the same fallback loop. Only the
    second element of this tuple should ever reach that loop.
    """
    key = f"{module}.{func_name}"
    if key in _seen:
        return set(), set()

    fn = _function_defs(module).get(func_name)
    if fn is None:
        return set(), set()

    aliases = _alias_map(module)
    seen = _seen | {key}
    found: set[str] = set()
    unresolved: set[str] = set()

    def follow(symbol: str) -> None:
        found.add(symbol)
        if _is_exempt(symbol):
            # Vetted as a whole, not merely permitted: `provider_status`'s own
            # body legitimately references `ProviderStatus`/`AnthropicProvider`
            # as types, and re-flagging those from inside an already-exempt
            # call would make the exemption pointless. Do not trace further,
            # and do not fall back to its module either.
            return
        if _is_inert_class_reference(symbol):
            return  # a pure Enum reference runs no code — nothing to fall back on
        resolved = _resolve_symbol_function(symbol)
        if resolved is not None:
            sub_found, sub_unresolved = _locally_reachable_app_symbols(*resolved, _seen=seen)
            found.update(sub_found)
            unresolved.update(sub_unresolved)
            return
        unresolved.add(symbol)

    for name in _referenced_symbols(fn, aliases):
        if name in aliases:
            follow(aliases[name])
        elif name in _function_defs(module):
            sub_found, sub_unresolved = _locally_reachable_app_symbols(module, name, _seen=seen)
            found |= sub_found
            unresolved |= sub_unresolved
        elif name.startswith("app."):
            # A qualified symbol `_referenced_symbols` already resolved via an
            # `alias.attr` access (e.g. `audit.record` -> `app.domain.audit.record`)
            # — not a bare local name, so neither branch above applies to it.
            follow(name)

    return found, unresolved


def _reachable_from(start: str, graph: dict[str, set[str]]) -> set[str]:
    """Transitive closure, resolving each name to the module that defines it.

    `from app.research.crawler import fetch_page` yields `app.research.crawler`
    directly; `from app.config import Settings` yields `app.config.Settings`,
    which is a symbol rather than a module and is folded back to `app.config`.
    """
    seen: set[str] = set()
    queue = [start]

    while queue:
        current = queue.pop()
        for name in graph.get(current, set()):
            module = name if name in graph else name.rsplit(".", 1)[0]
            if module in graph and module not in seen:
                seen.add(module)
                queue.append(module)

    return seen


def _dependency_calls(dependant: object) -> Iterator[object]:
    call = getattr(dependant, "call", None)
    if call is not None:
        yield call
    for sub in getattr(dependant, "dependencies", []):
        yield from _dependency_calls(sub)


def _served_routes(router: object) -> Iterator[tuple[str, object, object]]:
    """Every route the app actually serves, as (path, endpoint, dependant).

    `include_router` does not flatten in this version of FastAPI — an included
    router appears in `app.routes` as one object holding its own routes, so a
    flat pass over `app.routes` sees three documentation endpoints and nothing
    else. That is exactly the empty set that
    `test_some_routes_are_anonymous_or_this_test_proves_nothing` exists to
    catch, and it caught it.

    The *effective* contexts are used rather than the original routes because
    they carry the dependencies added at include time. A router mounted with
    `dependencies=[Depends(current_scope)]` protects routes whose own
    signatures say nothing about a session, and reading the unresolved route
    would report those as anonymous.
    """
    for route in getattr(router, "routes", []):
        contexts = getattr(route, "effective_route_contexts", None)
        if contexts is not None:
            for context in contexts():
                yield context.path, context.endpoint, context.dependant
        elif isinstance(route, APIRoute):
            yield route.path, route.endpoint, route.dependant
        else:
            yield from _served_routes(route)


def _anonymous_routes() -> list[tuple[str, str, str]]:
    """`(path, module, function_name)` for every route that needs no session.

    Per route, not per module — grouping by module was the coarseness that made
    `read_preferences`/`update_preferences` (properly declared, `CurrentScope`)
    charge their imports against `/auth/login` in the same file. Each route is
    now traced from its own function."""
    anonymous: list[tuple[str, str, str]] = []

    for path, endpoint, dependant in _served_routes(create_app()):
        if AUTHENTICATING.intersection(_dependency_calls(dependant)):
            continue
        anonymous.append((path, endpoint.__module__, getattr(endpoint, "__name__", "")))

    return anonymous


def test_the_research_package_is_where_the_crawler_lives() -> None:
    """Guards the test itself. If `app/research/` were ever renamed away, every
    assertion below would pass by finding nothing, and the file would sit in the
    suite reporting green over an invariant it had stopped checking."""
    graph = _import_graph()

    assert "app.research.crawler" in graph
    assert "app.research.ssrf" in graph
    assert "app.research.extract" in graph


def test_some_routes_are_anonymous_or_this_test_proves_nothing() -> None:
    """The other half of the same guard. Health and sign-in are anonymous by
    design; if the detection above silently classified everything as
    authenticated, the real assertion would be checking an empty set."""
    assert _anonymous_routes(), "no anonymous route was detected — the walk is broken"


def _is_exempt(name: str) -> bool:
    """`name` itself, or a symbol of it, is one of the two named carve-outs.
    `startswith(x + ".")` rather than a prefix tuple — each is one module or one
    symbol, not a family, and the boundary between "is the exemption" and
    "merely starts with the same characters" matters at exactly one point:
    `app.connectors.rate_limit_something_else` must not slip through."""
    for exemption in (RATE_LIMIT_EXEMPTION, DOMAIN_CHECK_EXEMPTION):
        if name == exemption or name.startswith(exemption + "."):
            return True
    if name in STATUS_INTROSPECTION_EXEMPTION:
        return True
    return name in RETRIEVAL_SCOPE_SETTER_EXEMPTIONS


def _is_forbidden(name: str) -> bool:
    if _is_exempt(name) or _is_inert_class_reference(name):
        return False
    if name in FORBIDDEN_EXACT:
        return True
    return any(name.startswith(prefix) for prefix in FORBIDDEN_PREFIXES)


def _forbidden_reachable_from_route(
    module: str, func_name: str, graph: dict[str, set[str]]
) -> set[str]:
    """What this specific route can reach that it should not.

    Every referenced symbol is checked directly. Only the *unresolved* ones —
    the ones this walk could not trace into a function's own body — fall back
    to their module's whole import surface, and only if they are not
    themselves exempt: an exempt symbol does not propagate its module's
    reachability either, or exempting `provider_status` would still flag
    `app.ai.contracts` and `app.ai.anthropic_provider`, which is everything
    `app.ai.registry` imports to build the registry `provider_status` reads.
    """
    found, unresolved = _locally_reachable_app_symbols(module, func_name)
    forbidden = {name for name in found if _is_forbidden(name)}

    for name in unresolved:
        if _is_exempt(name):
            continue
        target_module = name if name in graph else name.rsplit(".", 1)[0]
        if target_module in graph:
            forbidden |= {n for n in _reachable_from(target_module, graph) if _is_forbidden(n)}

    return forbidden


def test_no_anonymous_route_can_reach_a_metered_or_credentialed_fetch() -> None:
    """The invariant, rewritten by ADR 0046 and made route-level by the module
    docstring's coarseness note above.

    Fails if you add `from app.ai import registry` or
    `from app.connectors.hubspot import ...` (or anything under `app.embeddings`,
    `app.retrieval`, or the two research-runner modules) to a function an
    anonymous route actually calls into — at any depth, through any number of
    intermediate helpers, whether in the route's own module or another.
    `app.connectors.rate_limit` and the two named status-introspection functions
    are exempt.

    This does **not** forbid `app.research.crawler` or `app.research.extract` —
    see the module docstring and `tests/test_scan_boundary.py`, which is the
    tighter test that bounds the one anonymous surface permitted to reach them.
    """
    graph = _import_graph()
    offenders: list[str] = []

    for path, module, func_name in sorted(_anonymous_routes()):
        forbidden = sorted(_forbidden_reachable_from_route(module, func_name, graph))
        if forbidden:
            offenders.append(f"{module}.{func_name} (serving {path}) reaches {forbidden}")

    assert offenders == [], (
        "an unauthenticated route can reach a metered or credentialed module:\n  "
        + "\n  ".join(offenders)
        + "\nA metered or credentialed call on an anonymous path lets a stranger "
        "exhaust a paid quota or a workspace's own connection. Put the route "
        "behind CurrentSession, or — if it genuinely needs an anonymous crawl — "
        "route it through app.scan, not through this module."
    )


def test_the_preview_endpoint_is_gone() -> None:
    """The entry point itself, checked through the app rather than by grep.

    A router can be re-registered in `main.py` by anyone restoring a file from
    history, and the import-graph test above would not notice: a resurrected
    `app/routes/preview.py` importing the crawler would be caught, but one
    rebuilt against a different module would not. This asserts the observable
    fact the acceptance test names — nothing answers at `/preview`.
    """
    from fastapi.testclient import TestClient

    with TestClient(create_app()) as client:
        assert client.get("/preview").status_code == 404
        assert client.post("/preview", json={"url": "https://example.com"}).status_code == 404
