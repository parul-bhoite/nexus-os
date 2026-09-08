"""The crawl source returns an outcome. It never raises past its own boundary.

Q56 again, and this is where it would be lost. A crawl that raises makes "one
source failing never fails the run" the *caller's* problem to remember — the
kind of rule that holds until somebody adds a second caller.

`fetch_page` is substituted throughout. What is under test is the orchestration:
which pages, when to stop, and what outcome each ending produces. The fetching
itself, with its SSRF guard re-applied per redirect hop, has its own tests and
is deliberately not re-exercised here — a second copy of that guard is the one
thing this module must never grow.
"""

from __future__ import annotations

import pytest

from app.domain.research import SourceState
from app.research import runner
from app.research.crawler import FetchError

SITE = "https://example.om"
RICH = "<html><body>" + ("A real sentence about the company. " * 20) + "</body></html>"
SHELL = "<html><body><div id='root'></div><script>" + ("x" * 5000) + "</script></body></html>"


def _serving(pages: dict[str, str]) -> object:
    async def fake(url: str, **_: object) -> object:
        if url not in pages:
            raise FetchError("Not found.")

        class Page:
            html = pages[url]

        return Page()

    return fake


async def test_a_readable_site_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(runner, "fetch_page", _serving({SITE: RICH, f"{SITE}/about": RICH}))

    outcome = await runner.crawl_site([SITE, f"{SITE}/about"])

    assert outcome.state is SourceState.SUCCEEDED
    assert len(outcome.pages) == 2
    assert outcome.error_reason == ""


async def test_a_javascript_shell_is_reported_as_such_not_as_a_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Q51. The site is not broken and must not be told it is."""
    monkeypatch.setattr(runner, "fetch_page", _serving({SITE: SHELL}))

    outcome = await runner.crawl_site([SITE])

    assert outcome.state is SourceState.JS_RENDERED
    assert outcome.js_rendered_urls == [SITE]
    assert outcome.error_reason == "", "a shell is not a failure and carries no error"


async def test_one_unreachable_page_does_not_fail_the_crawl(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A 404 on `/pricing` means they have no pricing page — a fact about the
    company, not an error in our reading."""
    monkeypatch.setattr(runner, "fetch_page", _serving({SITE: RICH}))

    outcome = await runner.crawl_site([SITE, f"{SITE}/pricing"])

    assert outcome.state is SourceState.SUCCEEDED
    assert len(outcome.pages) == 1


async def test_an_unreachable_site_fails_with_a_reason_and_no_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The Q56 boundary: it returns, and the reason is a sentence a founder can
    read rather than a stack trace."""
    monkeypatch.setattr(runner, "fetch_page", _serving({}))

    outcome = await runner.crawl_site([SITE])

    assert outcome.state is SourceState.FAILED
    assert "could not read" in outcome.error_reason
    assert "either way" in outcome.error_reason, "it must say what happens instead"


async def test_no_seeds_is_skipped_not_failed(monkeypatch: pytest.MonkeyPatch) -> None:
    """A workspace with no website gave us nothing to crawl. Telling them our
    research broke would blame us for a question we never asked."""
    outcome = await runner.crawl_site([])
    assert outcome.state is SourceState.SKIPPED
    assert outcome.error_reason == ""


async def test_the_page_budget_is_respected(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.research import site

    everything = {f"{SITE}/p{i}": RICH for i in range(60)}
    everything[SITE] = RICH
    monkeypatch.setattr(runner, "fetch_page", _serving(everything))

    outcome = await runner.crawl_site(list(everything))

    assert len(outcome.pages) <= site.MAX_PAGES


async def test_a_spent_time_budget_stops_before_fetching(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Started already past the soft cap: nothing new begins."""
    from app.research import site

    monkeypatch.setattr(runner, "fetch_page", _serving({SITE: RICH}))

    outcome = await runner.crawl_site([SITE], elapsed=site.SOFT_CAP_SECONDS + 1)

    assert outcome.pages == []
    assert outcome.state is SourceState.FAILED, "nothing read is not a success"


# ── HTTPS is a preference, not a requirement ──────────────────
#
# Found in the field: a customer registered `prosoftinformatics.com`, which
# serves plain HTTP and refuses 443. Every caller builds `https://`, so the
# crawl reached nothing and the founder was told "we could not read any pages on
# your website" about a site that was up and serving.


async def test_a_site_with_no_https_is_read_over_http(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(runner, "fetch_page", _serving({"http://example.om": RICH}))

    outcome = await runner.crawl_site([SITE])

    assert outcome.state is SourceState.SUCCEEDED
    assert [page["url"] for page in outcome.pages] == ["http://example.om"]


async def test_https_is_tried_first_and_http_is_not_used_when_it_works(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The fallback must not become a downgrade on every crawl."""
    asked: list[str] = []

    async def fake(url: str, **_: object) -> object:
        asked.append(url)
        if url != SITE:
            raise FetchError("Not found.")

        class Page:
            html = RICH

        return Page()

    monkeypatch.setattr(runner, "fetch_page", fake)
    outcome = await runner.crawl_site([SITE])

    assert outcome.state is SourceState.SUCCEEDED
    assert not [url for url in asked if url.startswith("http://")]


async def test_a_reachable_javascript_shell_is_not_downgraded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A shell means the host answered. Retrying over HTTP would prove nothing."""
    asked: list[str] = []

    async def fake(url: str, **_: object) -> object:
        asked.append(url)
        if url != SITE:
            raise FetchError("Not found.")

        class Page:
            html = SHELL

        return Page()

    monkeypatch.setattr(runner, "fetch_page", fake)
    outcome = await runner.crawl_site([SITE])

    assert outcome.state is SourceState.JS_RENDERED
    assert not [url for url in asked if url.startswith("http://")]


async def test_a_same_host_link_follows_the_scheme_that_works(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An HTTP-only site still writes `https://` into its own navigation.

    Following those verbatim spends one guaranteed failure per link on a host
    whose HTTPS has already been shown unreachable.
    """
    home = f"<html><body><a href='{SITE}/about'>About</a>{RICH}</body></html>"
    monkeypatch.setattr(
        runner,
        "fetch_page",
        _serving({"http://example.om": home, "http://example.om/about": RICH}),
    )

    outcome = await runner.crawl_site([SITE])

    assert {page["url"] for page in outcome.pages} == {
        "http://example.om",
        "http://example.om/about",
    }
