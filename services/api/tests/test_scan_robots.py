"""`app.scan.robots` — G5, confirmed by Parul before building.

Same mocked-transport, scripted-DNS convention as `test_crawler_redirects.py`
and `test_scan_engine.py`.
"""

from __future__ import annotations

from collections.abc import Callable

import httpx
import pytest

from app.research import crawler
from app.research import ssrf as ssrf_module
from app.scan import robots

PUBLIC_A = "93.184.216.34"

Handler = Callable[[httpx.Request], httpx.Response]
DnsSetter = Callable[[dict[str, list[str]]], None]


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
def seen() -> list[httpx.Request]:
    return []


@pytest.fixture
def transport(
    monkeypatch: pytest.MonkeyPatch, seen: list[httpx.Request]
) -> Callable[[Handler], None]:
    def install(handler: Handler) -> None:
        def recording(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            return handler(request)

        def fake_client(timeout: float) -> httpx.AsyncClient:
            return httpx.AsyncClient(
                transport=httpx.MockTransport(recording),
                follow_redirects=False,
                timeout=httpx.Timeout(timeout),
                headers={"User-Agent": crawler.USER_AGENT},
            )

        monkeypatch.setattr(crawler, "_client", fake_client)

    return install


def text_response(body: str, *, status_code: int = 200) -> httpx.Response:
    return httpx.Response(status_code, headers={"content-type": "text/plain"}, content=body)


async def test_a_disallow_all_refuses_before_any_page_fetch(
    dns: DnsSetter, transport: Callable[[Handler], None], seen: list[httpx.Request]
) -> None:
    dns({"public.example": [PUBLIC_A]})

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            # Written the way a real site would: the bare product token, not
            # the full descriptive User-Agent string with version and URL.
            return text_response(f"User-agent: {robots.USER_AGENT_TOKEN}\nDisallow: /")
        return text_response("should never be requested")

    transport(handler)

    with pytest.raises(robots.ScanDisallowedError):
        await robots.check_allowed("https://public.example/")

    assert [str(r.url.path) for r in seen] == ["/robots.txt"], (
        "the page path must never be requested once robots.txt disallows it"
    )


async def test_no_robots_txt_scans_normally(
    dns: DnsSetter, transport: Callable[[Handler], None]
) -> None:
    dns({"public.example": [PUBLIC_A]})
    transport(lambda request: text_response("not found", status_code=404))

    await robots.check_allowed("https://public.example/")  # must not raise


async def test_a_robots_txt_that_does_not_resolve_does_not_block_the_scan(
    dns: DnsSetter, transport: Callable[[Handler], None]
) -> None:
    """A `robots.txt` fetch that fails for any reason — here, the host does
    not resolve at all — is absence, not refusal. `FetchError` (raised for a
    timeout the same way) is caught the same way; there is nothing timeout-
    specific to exercise beyond what `check_allowed`'s `except FetchError`
    already covers uniformly."""
    dns({})
    transport(lambda request: text_response("unreachable"))

    await robots.check_allowed("https://nowhere.example/")  # must not raise


async def test_a_disallow_on_a_different_path_permits_this_one(
    dns: DnsSetter, transport: Callable[[Handler], None]
) -> None:
    dns({"public.example": [PUBLIC_A]})
    transport(
        lambda request: (
            text_response("User-agent: *\nDisallow: /private/")
            if request.url.path == "/robots.txt"
            else text_response("ok")
        )
    )

    await robots.check_allowed("https://public.example/")  # must not raise
