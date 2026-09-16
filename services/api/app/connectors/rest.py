"""The HTTP transport — the fallback, and the one most providers will use.

ADR 0031 calls REST a **first-class path rather than a stopgap**, and the count
is why: Google Analytics, Search Console, QuickBooks, ad platforms, enrichment
and tender feeds have no confirmed official MCP server between them, which is
most of the connectable surface. A design treating REST as degraded would be
degraded for the majority of what it connects.

## A named call, not a URL

`ToolCall.name` is looked up in a route table the adapter owns. A transport that
took a path would let a caller reach anything the credential can reach, and the
argument that a connector is safe rests on **we** choosing the calls rather than
the caller composing them.

## What is never logged

The credential, and the response body. The first is obvious; the second is not,
and matters more in practice — a provider's payload carries the customer's own
contacts, invoices and notes, and a debug log that dumped it would put personal
data into an operational store nobody scoped for it.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

import httpx

from app.connectors.contracts import (
    ConnectorError,
    ProviderMisconfiguredError,
    ProviderUnavailableError,
    ToolCall,
)
from app.logging import get_logger

log = get_logger(__name__)

TIMEOUT: Final = httpx.Timeout(20.0, connect=5.0)
"""Short, and shorter to connect.

A connector runs on a worker rather than in a request, so a long timeout costs
nobody a spinner — but a provider that has stopped answering should be reported
as unavailable within a sweep rather than holding a slot until something else
gives up.
"""


class RestTransport:
    """One provider's HTTP API, reached by named call.

    `routes` maps a `ToolCall.name` to `(method, path)`. It is passed in rather
    than declared here because the names belong to the adapter — this class
    knows how to make a request and nothing about what any provider offers.
    """

    def __init__(
        self,
        *,
        base_url: str,
        routes: Mapping[str, tuple[str, str]],
        token: str,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._routes = dict(routes)
        # Held, never logged and never put in an exception message. `str(error)`
        # reaches logs and, summarised, a screen.
        self._token = token
        self._client = client

    async def call(self, call: ToolCall) -> Mapping[str, Any]:
        route = self._routes.get(call.name)
        if route is None:
            # A bug, not a state: the adapter asked for something it never
            # declared, so retrying on a schedule would repeat it for ever.
            raise ProviderMisconfiguredError(f"{call.name!r} is not a call this connector declares")

        method, path = route
        client = self._client or httpx.AsyncClient(timeout=TIMEOUT)
        try:
            response = await client.request(
                method,
                f"{self._base_url}/{path.lstrip('/')}",
                params=dict(call.arguments) if method == "GET" else None,
                json=dict(call.arguments) if method != "GET" else None,
                headers={"Authorization": f"Bearer {self._token}", "Accept": "application/json"},
            )
        except httpx.HTTPError as unreachable:
            # The class name, not the message: httpx puts the full URL in some
            # of its messages, and a URL can carry a token in a query string.
            raise ProviderUnavailableError(
                f"the provider could not be reached ({type(unreachable).__name__})"
            ) from unreachable
        finally:
            if self._client is None:
                await client.aclose()

        return self._payload(call, response)

    def _payload(self, call: ToolCall, response: httpx.Response) -> Mapping[str, Any]:
        if response.status_code in (401, 403):
            # Not retryable. A revoked token or a missing scope is fixed by the
            # customer reconnecting, and a sweep that kept trying would burn the
            # provider's rate limit to no effect.
            raise ProviderMisconfiguredError(
                "the provider refused our credentials — the connection needs renewing"
            )
        if response.status_code >= 400:
            log.warning(
                "connector.rest_refused",
                call=call.name,
                status=response.status_code,
                # Deliberately no body. A provider's payload carries the
                # customer's own contacts and invoices, and a log line is not a
                # store anybody scoped for personal data.
            )
            raise ProviderUnavailableError(
                f"the provider answered {response.status_code} for {call.name}"
            )

        try:
            body = response.json()
        except ValueError as unreadable:
            raise ProviderUnavailableError(
                f"the provider's answer to {call.name} was not JSON"
            ) from unreadable

        if not isinstance(body, Mapping):
            # A list at the top level is common and legitimate; it is wrapped
            # rather than rejected so every transport returns one shape.
            return {"items": body}
        return body


__all__ = ["TIMEOUT", "ConnectorError", "RestTransport"]
