"""The MCP transport — the same named call, over a vendor's own server.

ADR 0031. Five vendors publish official, vendor-hosted servers today: HubSpot,
Salesforce, Stripe, Xero, and Pipedrive since June 2026. Reaching them through
one protocol instead of five bespoke clients is the whole reason MCP is worth
having here.

## It is a transport and nothing else

The model never sees this class, and this class never sees a model. A director
that called a CRM's MCP server and reported what it found would be **fetching**,
and I1 says every number is fetched or computed in code. The rows this returns
are stored; the figures come from `calculators/` afterwards, exactly as they do
for a REST response.

## `tools/call`, and never `tools/list`

A client that listed a server's tools and then chose between them would be
composing its own calls at runtime — the thing `ToolCall`'s docstring rules out.
The adapter declares the names it uses, the same way it declares its REST
routes, and a server that stops offering one is a misconfiguration to report
rather than a menu to re-read.

## Why this is not wired to a real vendor yet

The official `mcp` SDK is **not a dependency of this service**, and hand-rolling
JSON-RPC session initialisation, protocol-version negotiation, SSE framing and
OAuth against five vendors is the kind of thing that works in a test and fails
on the third provider. So the shape is here and honest, `send` is the one seam a
real client plugs into, and **the SDK is a named blocker** rather than a quiet
TODO. `test_connector_boundary.py` holds the behaviour that must survive the
swap.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final, Protocol

from app.connectors.contracts import (
    ProviderMisconfiguredError,
    ProviderUnavailableError,
    ToolCall,
)

PROTOCOL_VERSION: Final = "2025-06-18"
"""Pinned rather than negotiated at call time.

A client that accepted whatever a server offered would change behaviour when a
vendor upgraded, which is a change to what a customer's tile says arriving
without a deploy.
"""


class Session(Protocol):
    """A live MCP session. One JSON-RPC request, one result.

    The seam the official SDK plugs into. It is a protocol rather than a
    concrete client so `test_connector_boundary.py` can assert this transport's
    behaviour — the untrusted handling, the error mapping, the absence of any
    model — without a network or a vendor account.
    """

    async def send(self, method: str, params: Mapping[str, Any]) -> Mapping[str, Any]: ...


class McpTransport:
    """One provider's MCP server, reached by named tool.

    `tools` maps a `ToolCall.name` to the server's own tool name. The indirection
    earns its keep the first time two vendors name the same operation
    differently: the adapter keeps one vocabulary and only this map changes.
    """

    def __init__(self, *, session: Session, tools: Mapping[str, str]) -> None:
        self._session = session
        self._tools = dict(tools)

    async def call(self, call: ToolCall) -> Mapping[str, Any]:
        tool = self._tools.get(call.name)
        if tool is None:
            raise ProviderMisconfiguredError(f"{call.name!r} is not a call this connector declares")

        result = await self._session.send(
            "tools/call", {"name": tool, "arguments": dict(call.arguments)}
        )

        # **`isError` is a result, not an exception.** MCP reports a tool failure
        # inside a successful response, so a client that only caught transport
        # errors would treat "this tool failed" as a successful empty fetch — and
        # an empty fetch computes a figure of zero, which is the I10 violation
        # this product exists to prevent, arriving through a protocol detail.
        if result.get("isError"):
            raise ProviderUnavailableError(f"the provider's {call.name} tool reported a failure")

        content = result.get("structuredContent")
        if isinstance(content, Mapping):
            return content

        # No structured result. Deliberately **not** parsed out of the text
        # blocks: those are prose written for a model to read, and mining a
        # number out of them would be reading a figure from generated text —
        # precisely what I1 forbids, however convenient the string looks.
        raise ProviderUnavailableError(
            f"the provider returned no structured result for {call.name}"
        )
