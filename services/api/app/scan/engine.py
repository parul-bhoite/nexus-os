"""One page, scored — G4. No route, no database, no rate limiting.

Callable from a test and from nothing else until `app.routes.scan` (G7)
wires it to an endpoint. `doc/18` §0's pipeline, minus the parts that are not
this module's job:

    validate -> fetch_page (this module's caps) -> extract -> score -> rank

Every failure `fetch_page` already distinguishes — unreachable, timeout, a
redirect loop, a non-HTML response, an SSRF refusal — is relayed as-is via
`ScanRefusedError`, carrying the same safe-to-show reason and the same `blocked`
flag `FetchError` already computes. This module invents no reason of its own
and leaks no more than `fetch_page` already decided was safe to leak.

**A JavaScript shell is not a failure** (Q51, `app/research/site.py`). A page
whose text is thin while its script content dominates returns a `ScanResult`
with zero gaps and `js_rendered=True` — nothing errored, there was simply
nothing on the page to score.

**`robots.txt` is checked first** (G5, confirmed by Parul before building).
A disallow is relayed as `ScanRefusedError` the same way every other refusal
is — the caller sees one refusal shape, not two.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.calculators import gaps
from app.calculators.audit import CategoryScore, Check, build_preview_audit
from app.research.crawler import FetchError, fetch_page
from app.research.extract import extract_signals, extract_text
from app.research.site import looks_javascript_rendered
from app.scan import budget, robots


class ScanRefusedError(Exception):
    """The scan cannot proceed. Same shape as `FetchError` on purpose — this
    module relays the crawler's reason rather than composing its own."""

    def __init__(self, reason: str, *, blocked: bool = False) -> None:
        super().__init__(reason)
        self.reason = reason
        """Safe to show a visitor. Never confirms internal network shape —
        that guarantee is `fetch_page`'s, not re-derived here."""
        self.blocked = blocked
        """True when the SSRF guard refused the target, rather than an
        ordinary network failure."""


@dataclass(frozen=True, slots=True)
class ScanResult:
    scanned_url: str
    """The final URL actually read, after redirects — may differ from what
    the visitor typed."""

    pages_read: int
    """Always `1` on a result that reached this far: exactly one successful
    fetch produced it. Stored rather than inferred by the reader from
    `budget.MAX_PAGES`, which is the cap, not a count of what happened."""

    gap_checks: tuple[Check, ...]
    """Up to 3, ranked. Empty on a JavaScript-rendered page or a page with
    nothing wrong — never padded (I10)."""

    category_scores: tuple[dict[str, object], ...]
    """One summary per scored category (`category`, `score`, `max_score`,
    `percentage`) — `store.py`'s `scores` column. Empty on a
    JavaScript-rendered page: nothing was scored, so there is nothing to
    summarise, and an empty tuple says that plainly rather than a category
    reporting a score it never computed."""

    js_rendered: bool


def _summarise(categories: tuple[CategoryScore, ...]) -> tuple[dict[str, object], ...]:
    return tuple(
        {
            "category": c.category,
            "score": c.score,
            "max_score": c.max_score,
            "percentage": c.percentage,
        }
        for c in categories
    )


def _with_scheme(raw_url: str) -> str:
    """`abc-construction.om` -> `https://abc-construction.om`.

    Mirrors `app.research.runner._with_scheme` (not importable here — that
    module is off `app.scan`'s allowlist on purpose, D20's budgeted run).
    A visitor types a bare domain, the same way a founder types
    `workspace.website_url` in onboarding; only a bare `host[/path]` is
    rewritten, so anything already carrying a scheme reaches the SSRF guard
    exactly as typed.
    """
    if "://" in raw_url or raw_url.startswith("//"):
        return raw_url
    return f"https://{raw_url}"


async def scan(raw_url: str) -> ScanResult:
    """Fetch one page under the scan's own caps, then rank what failed."""
    raw_url = _with_scheme(raw_url.strip())

    try:
        await robots.check_allowed(raw_url)
    except robots.ScanDisallowedError as exc:
        raise ScanRefusedError(str(exc)) from exc

    try:
        page = await fetch_page(
            raw_url,
            max_bytes=budget.MAX_BYTES,
            timeout_seconds=budget.TIMEOUT_SECONDS,
            max_redirects=budget.MAX_REDIRECTS,
        )
    except FetchError as exc:
        raise ScanRefusedError(exc.reason, blocked=exc.blocked) from exc

    text = extract_text(page.html)
    if looks_javascript_rendered(page.html, text):
        return ScanResult(
            scanned_url=page.final_url,
            pages_read=1,
            gap_checks=(),
            category_scores=(),
            js_rendered=True,
        )

    signals = extract_signals(page.html, url=page.final_url)
    audit = build_preview_audit(signals)

    return ScanResult(
        scanned_url=page.final_url,
        pages_read=1,
        gap_checks=gaps.top(audit.categories, 3),
        category_scores=_summarise(audit.categories),
        js_rendered=False,
    )
