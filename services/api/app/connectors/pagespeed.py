"""PageSpeed Insights — a platform API key, not a per-workspace connection.

Unlike the OAuth connectors in `registry.py`, PageSpeed needs no customer
credential: it analyses any public URL with a single platform-held API key. That
is what makes it the one free source fetchable the moment onboarding completes,
with no Connect step (ADR 0082). So it lives here as its own small client rather
than through the OAuth `WIRING`/`workspace_connection` spine.

The key is optional, and absent is a **supported** state, not a degraded one — the
language-model pattern (ADR 0011): no key means no PageSpeed insight, never a
fabricated score. `PageSpeedClient.available` is the gate every caller checks
first.

Nothing here computes a figure. The raw payload goes to `calculators/pagespeed.py`
(pure) for the reason I1 gives. The API key is a query parameter, never logged,
and never placed in an exception message — a PSI URL carries the key, so the
transport reports status codes and exception *types*, not URLs.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final, Protocol

import httpx

from app.connectors.contracts import ProviderUnavailableError
from app.logging import get_logger

log = get_logger(__name__)

PSI_ENDPOINT: Final = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"
DEFAULT_STRATEGY: Final = "mobile"
"""Mobile, because that is the profile most of these companies' customers use and
the one Google surfaces first. A constant rather than a setting: a second tunable
is a second `.env` line to document for a choice nobody is asking to make."""

TIMEOUT: Final = httpx.Timeout(30.0, connect=5.0)
"""Generous: PSI runs a live Lighthouse audit and routinely takes 10-20s. The
caller runs this off the request path (a best-effort task after completion), so a
long wait costs no founder a spinner."""


class PageSpeedTransport(Protocol):
    """How the PSI request is actually made. Real over httpx; a stub in tests."""

    async def run(self, *, url: str, api_key: str, strategy: str) -> Mapping[str, Any]: ...


class HttpPageSpeedTransport:
    """The real transport. One GET to the PSI endpoint, performance category only."""

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client

    async def run(self, *, url: str, api_key: str, strategy: str) -> Mapping[str, Any]:
        client = self._client or httpx.AsyncClient(timeout=TIMEOUT)
        try:
            response = await client.request(
                "GET",
                PSI_ENDPOINT,
                params={
                    "url": url,
                    "key": api_key,
                    "strategy": strategy,
                    "category": "performance",
                },
            )
        except httpx.HTTPError as unreachable:
            # The type, never the message: httpx puts the full URL — which carries
            # the key — into some of its error messages.
            raise ProviderUnavailableError(
                f"PageSpeed could not be reached ({type(unreachable).__name__})"
            ) from unreachable
        finally:
            if self._client is None:
                await client.aclose()

        if response.status_code >= 400:
            # No body, no URL — the URL carries the key.
            log.warning("pagespeed.http_refused", status=response.status_code)
            raise ProviderUnavailableError(f"PageSpeed answered {response.status_code}")

        try:
            body = response.json()
        except ValueError as unreadable:
            raise ProviderUnavailableError("PageSpeed's answer was not JSON") from unreadable

        if not isinstance(body, Mapping):
            raise ProviderUnavailableError("PageSpeed's answer was not a JSON object")
        return body


class PageSpeedClient:
    """The platform key and a transport. `available` is False when no key is set."""

    def __init__(self, *, api_key: str, strategy: str, transport: PageSpeedTransport) -> None:
        # Held, never logged, never put in an exception message.
        self._api_key = api_key
        self._strategy = strategy
        self._transport = transport

    @property
    def available(self) -> bool:
        return bool(self._api_key)

    async def audit(self, url: str) -> Mapping[str, Any]:
        """The raw PSI payload for one URL. Callers must check `available` first."""
        if not self.available:
            raise ProviderUnavailableError("PageSpeed is not configured (no API key)")
        return await self._transport.run(url=url, api_key=self._api_key, strategy=self._strategy)


def get_pagespeed_client(
    settings: Any, *, transport: PageSpeedTransport | None = None
) -> PageSpeedClient:
    """Build a client from settings. Returns one whose `available` is False when
    `pagespeed_api_key` is unset — the caller no-ops, nothing is fabricated."""
    return PageSpeedClient(
        api_key=settings.pagespeed_api_key.get_secret_value(),
        strategy=DEFAULT_STRATEGY,
        transport=transport or HttpPageSpeedTransport(),
    )
