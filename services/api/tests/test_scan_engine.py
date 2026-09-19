"""`app.scan.engine` — one page, scored. G4.

The transport is mocked and DNS is scripted, the same convention
`test_crawler_redirects.py` uses and for the same reason: there is no way to
exercise "a public host is unreachable" or "a redirect targets a private
address" against the real network, and a real socket-bound fixture server
would prove the same thing with more moving parts.

`fetch_page` already carries the safe/unsafe distinction for a refusal reason
(`test_crawler_redirects.py` proves that once); this file's job is to prove
`engine.scan` relays it rather than inventing its own, and that the
JS-shell and ranking paths behave as G4 requires.
"""

from __future__ import annotations

from collections.abc import Callable

import httpx
import pytest

from app.research import crawler
from app.research import ssrf as ssrf_module
from app.scan import budget, engine, robots

PUBLIC_A = "93.184.216.34"

Handler = Callable[[httpx.Request], httpx.Response]
DnsSetter = Callable[[dict[str, list[str]]], None]

GOOD_HTML = """
<html><head><title>A title that is far too long to be useful for a listing</title>
<meta name="description" content="x"></head>
<body><h1>one</h1><h1>two</h1><h2>a</h2><p>Some short body text.</p></body></html>
"""

JS_SHELL_HTML = (
    '<html><head><title>App</title></head><body><div id="root"></div>'
    "<script>" + ("x" * 5000) + "</script></body></html>"
)


@pytest.fixture
def dns(monkeypatch: pytest.MonkeyPatch) -> DnsSetter:
    def set_map(mapping: dict[str, list[str]]) -> None:
        monkeypatch.setattr(
            ssrf_module,
            "_system_resolver",
            lambda host: list(mapping.get(host.lower(), [])),
        )

    return set_map


@pytest.fixture
def transport(monkeypatch: pytest.MonkeyPatch) -> Callable[[Handler], None]:
    def install(handler: Handler) -> None:
        def fake_client(timeout: float) -> httpx.AsyncClient:
            return httpx.AsyncClient(
                transport=httpx.MockTransport(handler),
                follow_redirects=False,
                timeout=httpx.Timeout(timeout),
                headers={"User-Agent": crawler.USER_AGENT},
            )

        monkeypatch.setattr(crawler, "_client", fake_client)

    return install


def html_response(body: str, *, content_type: str = "text/html") -> httpx.Response:
    return httpx.Response(200, headers={"content-type": content_type}, content=body.encode())


# ── The happy path — one page in, ranked gaps out ──────────────


async def test_a_scanned_page_yields_ranked_gaps_matching_the_calculator(
    dns: DnsSetter, transport: Callable[[Handler], None]
) -> None:
    dns({"public.example": [PUBLIC_A]})
    transport(lambda _request: html_response(GOOD_HTML))

    result = await engine.scan("https://public.example/")

    assert result.js_rendered is False
    assert result.pages_read == 1
    assert result.scanned_url == "https://public.example/"
    assert 0 < len(result.gap_checks) <= 3
    # Byte-identical to what the calculator produced — not a re-derived label.
    assert all(check.label and check.evidence for check in result.gap_checks)
    assert not any(check.passed for check in result.gap_checks)
    assert len(result.category_scores) == 3  # brand, technical_seo, performance


async def test_a_bare_domain_with_no_scheme_is_scanned_as_https(
    dns: DnsSetter, transport: Callable[[Handler], None]
) -> None:
    """A visitor types `public.example`, the way a founder types
    `website_url` in onboarding — not `https://public.example`."""
    dns({"public.example": [PUBLIC_A]})
    transport(lambda _request: html_response(GOOD_HTML))

    result = await engine.scan("public.example")

    assert result.scanned_url == "https://public.example"


async def test_a_url_already_carrying_a_scheme_is_untouched(
    dns: DnsSetter, transport: Callable[[Handler], None]
) -> None:
    dns({"public.example": [PUBLIC_A]})
    transport(lambda _request: html_response(GOOD_HTML))

    result = await engine.scan("http://public.example/")

    assert result.scanned_url == "http://public.example/"


# ── The JavaScript-shell case is not a failure ─────────────────


async def test_a_javascript_shell_yields_no_gaps_and_is_not_an_error(
    dns: DnsSetter, transport: Callable[[Handler], None]
) -> None:
    dns({"public.example": [PUBLIC_A]})
    transport(lambda _request: html_response(JS_SHELL_HTML))

    result = await engine.scan("https://public.example/")

    assert result.js_rendered is True
    assert result.gap_checks == ()
    assert result.category_scores == (), "nothing was scored — nothing to summarise"
    assert result.pages_read == 1


# ── Failure paths relay fetch_page's reason, unchanged ─────────


async def test_an_ssrf_refusal_is_relayed_without_the_reason(
    dns: DnsSetter, transport: Callable[[Handler], None]
) -> None:
    """The reason cannot confirm internal network shape to whoever supplied
    the URL — the same guarantee `test_crawler_redirects.py` proves about
    `FetchError` itself, checked here at the boundary `engine.scan` presents
    to whatever calls it."""
    dns({})  # does not resolve — refused before any request is sent
    transport(lambda _request: html_response(GOOD_HTML))

    with pytest.raises(engine.ScanRefusedError) as exc:
        await engine.scan("https://nowhere.example/")

    assert exc.value.blocked is True
    assert "nowhere.example" not in exc.value.reason


async def test_an_unreachable_host_is_refused_and_not_blocked(
    dns: DnsSetter, transport: Callable[[Handler], None]
) -> None:
    dns({"public.example": [PUBLIC_A]})

    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    transport(handler)

    with pytest.raises(engine.ScanRefusedError) as exc:
        await engine.scan("https://public.example/")

    assert exc.value.blocked is False
    assert "could not be reached" in exc.value.reason


async def test_a_redirect_to_a_private_address_is_refused(
    dns: DnsSetter, transport: Callable[[Handler], None]
) -> None:
    dns({"public.example": [PUBLIC_A]})
    transport(lambda _request: httpx.Response(302, headers={"location": "http://169.254.169.254/"}))

    with pytest.raises(engine.ScanRefusedError) as exc:
        await engine.scan("https://public.example/")

    assert exc.value.blocked is True
    assert "169.254" not in exc.value.reason


# ── Caps — the scan's own, not D20's research budget ───────────


async def test_scan_calls_fetch_page_with_the_scans_own_caps(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`engine.scan` must pass `app.scan.budget`'s constants to `fetch_page`,
    not `app.research.site`'s 20-page/5-minute research budget — the two are
    deliberately separate (`doc/18` §3). Asserted on the call itself rather
    than by fetching an oversized body and observing truncation: `fetch_page`
    already proves its own truncation behaviour
    (`test_crawler_redirects.py::test_an_oversized_body_is_capped_on_bytes_actually_read`);
    parsing a multi-megabyte page here to re-prove it would only add a slow,
    redundant test.
    """
    captured: dict[str, object] = {}

    async def fake_fetch_page(raw_url: str, **kwargs: object) -> crawler.FetchedPage:
        captured.update(kwargs)
        return crawler.FetchedPage(
            url=raw_url,
            final_url=raw_url,
            status_code=200,
            content_type="text/html",
            html=GOOD_HTML,
            elapsed_ms=1,
        )

    async def fake_check_allowed(_raw_url: str) -> None:
        return None

    monkeypatch.setattr(engine, "fetch_page", fake_fetch_page)
    # Otherwise `check_allowed` would attempt a real DNS lookup for
    # "public.example" via the unpatched crawler — fast-failing, but a real
    # network dependency this unit test has no business carrying.
    monkeypatch.setattr(robots, "check_allowed", fake_check_allowed)

    await engine.scan("https://public.example/")

    assert captured == {
        "max_bytes": budget.MAX_BYTES,
        "timeout_seconds": budget.TIMEOUT_SECONDS,
        "max_redirects": budget.MAX_REDIRECTS,
    }
    assert budget.MAX_BYTES == 1_000_000
