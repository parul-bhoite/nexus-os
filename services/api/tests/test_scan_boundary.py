"""`app.scan`'s own boundary — the second, tighter test ADR 0046 decided on.

`tests/test_no_unauthenticated_crawl.py` states what nothing anonymous may
ever reach (anything metered or credentialed). This file states the one
narrow exception ADR 0046 carved into that rule, and bounds it two ways:

1. **The allowlist.** `app.scan.*` may import only what is named below — an
   allowlist rather than a denylist, because it fails on anything nobody
   thought of. `app.research.crawler` and `app.research.extract` are safe
   *here* only because this is the one package permitted to reach them; the
   sibling file still forbids everything metered or credentialed regardless
   of which package asks.
2. **The named route.** Exactly one anonymous route module may reach
   `app.research.crawler` — `app.routes.scan` — asserted by name, so a second
   anonymous crawl path cannot appear without editing a test that says what
   it is doing.

**As of G1** (`doc/18-GAP-ANALYSIS-BUILD-PLAN.md`), `app/scan/` holds only
`budget.py` — constants, no fetch, no route. Both checks below are true and
currently vacuous: the allowlist has nothing outside it to catch yet, and no
anonymous route reaches the crawler yet. Vacuous truth is not the same as an
untested assumption, which is why `test_the_scan_package_exists` guards the
walk itself — the same failure mode
`test_the_research_package_is_where_the_crawler_lives` exists for in the
sibling file: if `app/scan/` or `app.research.crawler` were ever renamed
away, the assertions below would pass by finding nothing to check.
"""

from __future__ import annotations

from pathlib import Path

from tests.test_no_unauthenticated_crawl import (
    _anonymous_routes,
    _import_graph,
    _imports_of,
    _module_name,
    _reachable_from,
)

SCAN_DIR = Path(__file__).resolve().parents[1] / "app" / "scan"

# Every module (or symbol within one) `app.scan.*` may import. `app.scan.`
# itself is a prefix because the package will grow more modules than this one
# file; everything else is named exactly, because "a module in this package"
# is not the same license as "a whole other package".
#
# `app.research.site` was added during G4, not decided in ADR 0046 or `doc/18`
# §2 — `looks_javascript_rendered` (Q51's JS-shell detection) is the one piece
# of `app/research/` outside ssrf/crawler/extract that G4 legitimately needs,
# reused rather than duplicated for the same reason `gaps.py` was extracted
# instead of re-ranking independently: two implementations of "is this page a
# JS shell" would disagree eventually, and only one is what the workspace
# crawl actually uses.
ALLOWED_EXACT = frozenset(
    {
        "app.research.ssrf",
        "app.research.crawler",
        "app.research.extract",
        "app.research.site",
        "app.domain.page_signals",
        "app.config",
        "app.logging",
        "app.connectors.rate_limit",
        "app.db",
    }
)
ALLOWED_PREFIXES = ("app.scan.", "app.calculators.")


def _is_allowed(name: str) -> bool:
    # A prefix also allows its own bare package name — `from app.scan import
    # budget` names both `app.scan.budget` and, via `_imports_of`'s package
    # tracking, the bare `app.scan`. Checking only `startswith("app.scan.")`
    # missed that second form entirely: it would have let a genuinely
    # forbidden bare package name slip past unnoticed, but it just as
    # thoughtlessly failed the harmless one.
    if any(name.startswith(prefix) or name == prefix.rstrip(".") for prefix in ALLOWED_PREFIXES):
        return True
    return any(name == exact or name.startswith(f"{exact}.") for exact in ALLOWED_EXACT)


def test_the_scan_package_exists() -> None:
    """Guards the walk below — see the module docstring."""
    graph = _import_graph()
    assert "app.scan.budget" in graph
    assert "app.research.crawler" in graph
    assert "app.research.extract" in graph


def test_app_scan_imports_only_the_allowlist() -> None:
    """Fails if any module under `app/scan/` names an `app.*` import outside
    `ALLOWED_EXACT`/`ALLOWED_PREFIXES` — at the import statement, whether or
    not anything calls it, the same standard the sibling file's general rule
    holds everything else to.
    """
    offenders: list[str] = []

    for path in sorted(SCAN_DIR.rglob("*.py")):
        module = _module_name(path)
        for name in _imports_of(path):
            if not _is_allowed(name):
                offenders.append(f"{module} imports {name}")

    assert offenders == [], (
        "app.scan.* imported something outside its allowlist:\n  "
        + "\n  ".join(offenders)
        + "\nIf this is deliberate, it is a decision about what the anonymous "
        "scanner is allowed to touch, not a one-line fix — widen ALLOWED_EXACT "
        "here with the reason, or reconsider whether app.scan is the right home "
        "for it."
    )


def test_only_app_routes_scan_may_reach_the_crawler() -> None:
    """The named-route rule.

    Fails if any anonymous route module other than `app.routes.scan` imports
    `app.research.crawler`, at any depth. Currently the set this computes is
    empty — no route module exists under that name yet (G1 builds only
    constants) — and an empty set is one of the two values this assertion
    accepts, not a bypass of it: the moment any anonymous module other than
    `app.routes.scan` starts reaching the crawler, this fails.
    """
    graph = _import_graph()
    modules = {module for _, module, _ in _anonymous_routes()}
    reaching = {
        module for module in modules if "app.research.crawler" in _reachable_from(module, graph)
    }

    assert reaching in (set(), {"app.routes.scan"}), (
        "an anonymous route module other than app.routes.scan reaches "
        f"app.research.crawler: {sorted(reaching - {'app.routes.scan'})}\n"
        "A second anonymous crawl path appeared. If it is deliberate, name it "
        "in this test rather than letting it pass silently."
    )
