"""Fetching pages from a user-supplied domain.

Every request goes through `validate_url` first, and **every redirect hop is
re-validated** — doc 06 §1.2. Redirects are followed manually rather than by the
HTTP client, because a client following them itself would connect to hops this
guard never saw.

Three caps, all required by doc 06 §1.2:

- **size** — read incrementally and abort past the limit, so a multi-gigabyte
  response cannot exhaust memory. Trusting `Content-Length` is not enough; it is
  supplied by the server being fetched.
- **time** — a total budget across the whole chain, not per request, so a slow
  server cannot hold a worker indefinitely.
- **hops** — a bounded redirect chain.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Final
from urllib.parse import urlsplit

import httpx

from app.logging import get_logger
from app.research.ssrf import (
    UrlNotAllowedError,
    ValidatedTarget,
    resolve_redirect,
    validate_url,
)

log = get_logger(__name__)

USER_AGENT = "NexusOS-Audit/0.1 (+https://nexusos.example/crawler)"
ALLOWED_CONTENT_TYPES = ("text/html", "application/xhtml+xml", "text/plain")


class FetchError(Exception):
    """The page could not be fetched. Carries a reason safe to show a user."""

    def __init__(self, reason: str, *, blocked: bool = False) -> None:
        super().__init__(reason)
        self.reason = reason
        self.blocked = blocked
        """True when refused by the SSRF guard rather than by the network."""


@dataclass(frozen=True, slots=True)
class FetchedPage:
    url: str
    final_url: str
    status_code: int
    content_type: str
    html: str
    elapsed_ms: int
    redirect_chain: tuple[str, ...] = field(default=())
    truncated: bool = False


CONNECT_TIMEOUT_SECONDS: Final = 4.0
"""Separate from the read timeout, and much shorter.

`httpx.Timeout(n)` sets every phase to `n`, so an unreachable host held a slot
for the full page timeout. The two deserve different patience: a server taking
twelve seconds to render a page is slow, and worth waiting for; a host that has
not completed a TCP and TLS handshake in four seconds is not answering, and
waiting longer only adds up. It added up most on the sites that need the crawl
to be forgiving — a company on plain HTTP pays this once per scheme before the
fallback even begins.
"""


def _client(timeout: float) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        # Redirects are followed by hand so each hop can be re-validated.
        follow_redirects=False,
        timeout=httpx.Timeout(timeout, connect=CONNECT_TIMEOUT_SECONDS),
        headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"},
        # No cookies: nothing about this fetch should carry state between hops
        # or between targets.
        cookies=None,
    )


async def fetch_page(
    raw_url: str,
    *,
    max_bytes: int,
    timeout_seconds: int,
    max_redirects: int,
) -> FetchedPage:
    """Fetch one page, following redirects with the guard applied at each hop."""
    import time

    started = time.monotonic()
    chain: list[str] = []
    current = raw_url

    async with _client(timeout_seconds) as client:
        for hop in range(max_redirects + 1):
            if time.monotonic() - started > timeout_seconds:
                raise FetchError("The site took too long to respond.")

            try:
                target = validate_url(current)
            except UrlNotAllowedError as exc:
                # Logged with the reason, surfaced without it: the reason can
                # confirm internal network shape to whoever supplied the URL.
                log.info("crawl.blocked", hop=hop, reason=str(exc))
                raise FetchError("That address cannot be analysed.", blocked=True) from exc

            try:
                response = await _request(client, target)
            except httpx.TimeoutException as exc:
                raise FetchError("The site took too long to respond.") from exc
            except httpx.HTTPError as exc:
                raise FetchError("The site could not be reached.") from exc

            if response.status_code in (301, 302, 303, 307, 308):
                location = response.headers.get("location")
                if not location:
                    raise FetchError("The site redirected without a destination.")
                chain.append(current)
                current = resolve_redirect(current, location)
                await response.aclose()
                continue

            content_type = response.headers.get("content-type", "").split(";")[0].strip()
            if content_type and not content_type.startswith(ALLOWED_CONTENT_TYPES):
                await response.aclose()
                raise FetchError(f"That address returned {content_type}, not a web page.")

            html, truncated = await _read_capped(response, max_bytes)
            await response.aclose()

            return FetchedPage(
                url=raw_url,
                final_url=current,
                status_code=response.status_code,
                content_type=content_type or "text/html",
                html=html,
                elapsed_ms=int((time.monotonic() - started) * 1000),
                redirect_chain=tuple(chain),
                truncated=truncated,
            )

    raise FetchError("The site redirected too many times.")


async def _request(client: httpx.AsyncClient, target: ValidatedTarget) -> httpx.Response:
    """Issue the request against the **validated address**, not the hostname.

    Connecting by name would resolve DNS a second time, after validation, which
    is precisely the rebinding window `validate_url` pins the address to close.
    The original host travels in the `Host` header (and SNI) so virtual hosting
    and certificate validation still work.
    """
    parts = urlsplit(target.url)
    netloc_ip = f"[{target.ip}]" if ":" in target.ip else target.ip
    if target.port not in (80, 443):
        netloc_ip = f"{netloc_ip}:{target.port}"

    by_ip = parts._replace(netloc=netloc_ip).geturl()

    request = client.build_request(
        "GET",
        by_ip,
        headers={"Host": target.host},
        extensions={"sni_hostname": target.host},
    )
    return await client.send(request, stream=True)


async def _read_capped(response: httpx.Response, max_bytes: int) -> tuple[str, bool]:
    """Read up to `max_bytes`, then stop.

    `Content-Length` is not consulted for the decision — it is supplied by the
    server being fetched, so a hostile one can understate it.
    """
    chunks: list[bytes] = []
    total = 0
    truncated = False

    async for chunk in response.aiter_bytes():
        chunks.append(chunk)
        total += len(chunk)
        if total >= max_bytes:
            truncated = True
            break

    body = b"".join(chunks)[:max_bytes]
    return body.decode(response.encoding or "utf-8", errors="replace"), truncated
