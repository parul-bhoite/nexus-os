"""Running the crawl source: seed, discover, fetch, record.

Joins three things that already exist and adds no new judgement of its own.
`fetch_page` fetches one page with the SSRF guard re-applied at every redirect
hop; `site.plan` decides which twenty pages are worth the budget; `site.Budget`
decides when to stop. **None of that is reimplemented here** — a second copy of
the guard is the one thing this module must never grow.

The shape it does own is Q56's: **this returns an outcome, it never raises past
its own boundary.** A crawl that fails must leave the other five sources of the
run untouched, so every failure inside becomes a `SourceState` and a sentence,
and the caller writes it beside whatever the others produced.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Final

from app.domain.page_signals import PageSignals
from app.domain.research import SourceState
from app.logging import get_logger
from app.research import site
from app.research.crawler import FetchError, fetch_page
from app.research.extract import extract_signals, extract_text

log = get_logger(__name__)

MAX_BYTES: Final = 2 * 1024 * 1024
PAGE_TIMEOUT_SECONDS: Final = 15
MAX_REDIRECTS: Final = 5


@dataclass(slots=True)
class CrawlOutcome:
    """What the crawl produced, and what to write to `research_source`."""

    state: SourceState
    error_reason: str = ""
    pages: list[dict[str, str]] = field(default_factory=list)
    signals: dict[str, PageSignals] = field(default_factory=dict)
    """What each fetched page demonstrably contained, keyed by url.

    **The reason this exists at all:** the HTML is in hand exactly once, here,
    and every consumer downstream is days later. `extract_signals` was written
    in M2 and had no caller for a year because nothing kept the HTML long
    enough to call it — so `calculators/audit.py`, fully written and 16 tests
    green, could never be fed. One line in `_crawl` closes that.

    A dict keyed by url rather than a list parallel to `pages`, because
    `routes/onboarding_agent.py` filters `pages` by `is_prose` *after* this
    returns. An index-aligned list would then pair a kept page with a dropped
    page's signals — silently, and only for sites that already have trouble.
    `visited` guarantees one fetch per url, so the key is unique.
    """
    js_rendered_urls: list[str] = field(default_factory=list)


def is_prose(text: str, *, max_replacement_ratio: float = 0.05) -> bool:
    """Whether extracted text is language rather than mis-decoded bytes.

    A real page is almost entirely printable characters. A response the fetcher
    could not decode — the wrong charset, or a compressed body read as text —
    comes back as a wall of `U+FFFD` replacement characters with NUL bytes
    scattered through it, and it is still a non-empty string, so every
    "did we get anything?" check passes.

    Measured on `berkshirehathaway.com`, which produced this exactly:
    1459 characters, **624 of them U+FFFD** (43%) and six NUL bytes. Postgres
    then refused to store it — `jsonb` cannot hold `\u0000` — so onboarding
    raised a 500 on the first request of that customer's life, twice, with no
    way forward. Before that it would have been handed to a model as the
    company's own description of itself.

    Five per cent is deliberately loose. A page with the odd bad character is
    still readable prose and worth keeping; the failure this catches is not
    marginal, it is half the string.
    """
    if not text.strip():
        return False
    if "\x00" in text:
        # Not a ratio: a NUL means this was never text, and it is also the
        # character that makes the row unstorable.
        return False
    return text.count("\ufffd") / len(text) <= max_replacement_ratio


async def _fetch(url: str) -> tuple[str, str] | None:
    """One page's html and text, or `None` if it could not be read.

    Swallows `FetchError` deliberately: one unreachable page out of twenty is
    not a failed crawl. A 404 on `/pricing` means they have no pricing page,
    which is a fact about the company rather than an error in our reading.
    """
    try:
        page = await fetch_page(
            url,
            max_bytes=MAX_BYTES,
            timeout_seconds=PAGE_TIMEOUT_SECONDS,
            max_redirects=MAX_REDIRECTS,
        )
    except FetchError as exc:
        log.info("crawl.page_skipped", reason=str(exc))
        return None
    return page.html, extract_text(page.html)


def _with_scheme(seed: str) -> str:
    """`books.toscrape.com` -> `https://books.toscrape.com`.

    `origin` is `seeds[0]`, and `workspace.website_url` is stored exactly as the
    founder typed it — usually without a scheme, because that is how people write
    a domain. `urlparse` on a schemeless string puts the host in `path` and
    leaves `hostname` as `None`, so `same_site` rejected every candidate against
    it, `plan` returned nothing, and the background crawl failed with "we could
    not read any pages on your website" about a site that was up.

    Only a bare `host[/path]` is rewritten. Anything already carrying a scheme is
    passed through untouched so the SSRF guard sees, and refuses, exactly what it
    would have before — and a protocol-relative `//host` is left alone rather
    than promoted, since guessing at those is how a guard gets talked around.
    """
    if "://" in seed or seed.startswith("//"):
        return seed
    return f"https://{seed}"


def _to_origin_scheme(url: str, origin: str) -> str:
    """Point a same-host link at the scheme we know works.

    A site served over plain HTTP still writes `https://` into its own canonical
    links and navigation. Following those means one guaranteed failure per link
    on a host whose HTTPS we have *already established* is unreachable — on a
    server answering in six seconds, that is most of the crawl spent proving the
    same thing repeatedly.

    Only the scheme moves, and only for the origin's own host, so this cannot
    redirect the crawl anywhere new. Every rewritten URL still goes through the
    SSRF guard exactly as it would have.
    """
    scheme = origin.split("://", 1)[0]
    other = "https" if scheme == "http" else "http"
    prefix = f"{other}://"
    if not url.startswith(prefix):
        return url
    candidate = f"{scheme}://{url.removeprefix(prefix)}"
    return candidate if site.same_site(candidate, origin) else url


async def crawl_site(
    seeds: list[str], *, elapsed: float = 0.0, limit: int = site.MAX_PAGES
) -> CrawlOutcome:
    """Crawl a company's site and report what happened.

    **Returns rather than raises**, including when everything fails. Q56: one
    source failing must never fail the run, and a function that raises makes
    that the caller's problem to remember — which is the kind of rule that holds
    until somebody adds a second caller.

    `limit` caps the pages fetched, and exists because there are two callers who
    want opposite things. Onboarding is waiting on a person: it asks for a
    couple of pages so the brief arrives in seconds. The background research run
    is waiting on nobody and takes the full twenty. Same crawler, same priority
    order, different budget — rather than two crawlers that drift apart.

    **HTTPS first, then plain HTTP if nothing at all was reachable.** Every
    caller here builds `https://` — the onboarding route from the domain,
    `_with_scheme` from a bare hostname — so a company whose site serves HTTP
    only could not be onboarded at all, and was told "we could not read any
    pages on your website" about a site that was up and serving. Small business
    sites without TLS are common enough that refusing them is refusing the
    customer.

    The retry is narrow on purpose. It happens only when the HTTPS pass reached
    *nothing* — no page and not even a JavaScript shell — because anything
    reachable over HTTPS means the site is there and a second pass would only be
    slower. It is logged, so a Brain built over plaintext is a fact somebody can
    find rather than a silent downgrade.
    """
    if not seeds:
        return CrawlOutcome(state=SourceState.SKIPPED, error_reason="")

    seeds = [_with_scheme(seed) for seed in seeds]
    secure = await _crawl(seeds, elapsed=elapsed, limit=limit)
    if secure.pages or secure.js_rendered_urls:
        return secure

    downgraded = [
        "http://" + seed.removeprefix("https://") for seed in seeds if seed.startswith("https://")
    ]
    if not downgraded:
        return secure

    log.info("crawl.https_unreachable_retrying_http", origin=seeds[0])
    plain = await _crawl(downgraded, elapsed=elapsed, limit=limit)
    if not plain.pages:
        # Keep the HTTPS outcome. It is the one that describes what a browser
        # would do, and reporting the HTTP failure instead would send somebody
        # looking at the wrong protocol.
        return secure
    log.info("crawl.read_over_http", origin=downgraded[0], pages=len(plain.pages))
    return plain


async def _crawl(
    seeds: list[str], *, elapsed: float = 0.0, limit: int = site.MAX_PAGES
) -> CrawlOutcome:
    """One pass over one scheme. `crawl_site` decides which.

    Returns rather than raises, including when everything fails (Q56).
    """
    origin = seeds[0]
    outcome = CrawlOutcome(state=SourceState.RUNNING)
    budget = site.Budget(pages_fetched=0, elapsed_seconds=elapsed)

    # The sitemap first: it is the site telling us what it considers a page,
    # rather than us inferring it from navigation. Failure here is ordinary —
    # most small-business sites do not have one.
    discovered = list(seeds)
    sitemap = await _fetch(f"{origin.rstrip('/')}/sitemap.xml")
    if sitemap is not None:
        discovered.extend(site.urls_in_sitemap(sitemap[0]))
    discovered = [_to_origin_scheme(url, origin) for url in discovered]

    planned = site.plan(discovered, origin=origin, limit=limit)
    shells = 0
    visited: set[str] = set()

    # A worklist, not `for url in planned`.
    #
    # `for` binds the list object once. The link-following below rebinds
    # `planned` to a *new* list, which the loop then never looks at — so on any
    # site without a sitemap the crawl fetched the home page, discovered every
    # link on it, planned them, and stopped. One page, every time, silently: the
    # outcome was `succeeded` and the Brain was built from a single page.
    #
    # Taking the best unvisited target each time preserves what the old shape
    # was reaching for — `plan` re-sorts by priority, so a better page found on
    # the home page is fetched before a worse one found in the sitemap.
    while not budget.exhausted:
        remaining = [url for url in planned if url not in visited]
        if not remaining:
            break
        url = remaining[0]
        visited.add(url)

        fetched = await _fetch(url)
        budget = site.Budget(
            pages_fetched=budget.pages_fetched + 1, elapsed_seconds=budget.elapsed_seconds
        )
        if fetched is None:
            continue

        html, text = fetched
        if site.looks_javascript_rendered(html, text):
            shells += 1
            outcome.js_rendered_urls.append(url)
            continue

        outcome.pages.append({"url": url, "text": text})
        # Here and nowhere else: this is the only moment the HTML exists.
        outcome.signals[url] = extract_signals(html, url=url)

        # Links are a fallback, not a second pass: they extend the plan only
        # while there is budget left to use them.
        if len(planned) < limit:
            found = [_to_origin_scheme(u, origin) for u in site.links_in(html, base_url=url)]
            planned = site.plan(planned + found, origin=origin, limit=limit)
    else:
        log.info("crawl.budget_spent", pages=budget.pages_fetched)

    if outcome.pages:
        outcome.state = SourceState.SUCCEEDED
        return outcome

    if shells:
        # Q51. The site is not broken and must not be told it is.
        outcome.state = SourceState.JS_RENDERED
        return outcome

    outcome.state = SourceState.FAILED
    outcome.error_reason = (
        "We could not read any pages on your website. It may be temporarily "
        "unreachable — your answers and any documents you upload are used either way."
    )
    return outcome
