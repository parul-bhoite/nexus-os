"""Opening a real MCP session against a vendor's hosted server.

The one place the official SDK is imported. Everything above it depends on
`mcp.Session`, the protocol in `connectors/mcp.py`, so this file is the whole
blast radius of the SDK's API changing — and it already has once: `mcp` 2.x
renamed `streamablehttp_client` to `streamable_http_client` and moved
`CallToolResult.structuredContent` to `structured_content`.

## Two HTTP client libraries, and why that is accepted rather than fixed

The official SDK depends on **`httpx2`**, a different package from the `httpx`
the rest of this service uses — not a different version of one, a different
distribution. So installing it puts two HTTP clients in the process.

They are not reconciled, and the boundary is this file. `streamable_http_client`
takes no headers of its own, so the credential can only be set on a client
handed to it, which means one `httpx2` import — here and nowhere else.
`connectors/rest.py` and the crawler keep `httpx` untouched. Migrating the
service to `httpx2` to have one of them would be a large change made for tidiness
on a path with no shared state, and the cost of the split is a second package in
the image.

## Why a context manager rather than a pool

An MCP session is stateful — it initialises, negotiates and then answers — so it
is not a connection you borrow per call. A sweep opens one, makes the handful of
calls the adapter declares, and closes it. That also means **the access token
only has to live as long as the sweep**, which is what makes ADR 0032's option C
worth anything: the refresh token is sealed at rest, and the thing that can
actually read a customer's CRM exists for a few seconds in memory.

## The credential goes in a header, never in the URL

Same rule `connectors/rest.py` states: a URL reaches access logs, proxies and
error trackers; a header does not reach most of them. The MCP server is a plain
HTTPS endpoint, so this is not a protocol nicety — it is the same exposure.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Final

# The one `httpx2` import in the service. See the note above: it is the SDK's
# HTTP client, not the one `connectors/rest.py` and the crawler use.
import httpx2
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from app.connectors.contracts import ProviderUnavailableError
from app.logging import get_logger

log = get_logger(__name__)

TIMEOUT: Final = httpx2.Timeout(30.0, connect=10.0)
"""Longer than `rest.py`'s twenty seconds, and deliberately so.

An MCP session pays for initialisation before it answers anything, so the first
call carries a round trip the REST client does not. Still bounded: a provider
that has stopped answering must be reported within a sweep rather than holding a
worker until something else gives up.
"""


@asynccontextmanager
async def open_session(*, url: str, access_token: str) -> AsyncIterator[ClientSession]:
    """An initialised session against one vendor's MCP server.

    Raises `ProviderUnavailableError` rather than letting an httpx or anyio
    exception escape: above this line the caller knows about *providers*, not
    about transports, and an adapter that had to catch three libraries' error
    types would grow a second copy of this mapping.
    """
    headers = {"Authorization": f"Bearer {access_token}"}

    try:
        async with httpx2.AsyncClient(timeout=TIMEOUT, headers=headers) as http:
            async with streamable_http_client(url=url, http_client=http) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    yield session
    except ProviderUnavailableError:
        raise
    except Exception as unreachable:
        # The class name, not the message. Some transports put the full URL in
        # theirs, and a URL can carry a token if anybody ever builds one that
        # way — this is the belt to `headers`' braces.
        log.warning("connector.mcp_unreachable", kind=type(unreachable).__name__)
        raise ProviderUnavailableError(
            f"the provider's MCP server could not be reached ({type(unreachable).__name__})"
        ) from unreachable
