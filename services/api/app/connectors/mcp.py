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

## `call_tool`, and never `list_tools`

A client that listed a server's tools and then chose between them would be
composing its own calls at runtime — the thing `ToolCall`'s docstring rules out.
The adapter declares the names it uses, the same way it declares its REST
routes, and a server that stops offering one is a misconfiguration to report
rather than a menu to re-read.

## The seam is the SDK's own shape

`Session` below is `mcp.ClientSession.call_tool` narrowed to what this needs.
The first draft invented a `send(method, params)` seam and had to be corrected:
the SDK's method takes a tool name and arguments, so a JSON-RPC-shaped seam
would have meant this module knowing about the wire format the SDK exists to
hide. Keeping it a protocol rather than importing `ClientSession` here is what
lets `test_connector_boundary.py` assert the behaviour — the untrusted handling,
the error mapping, the absence of any model — without a network or a vendor
account.
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
"""The version this client was written against.

Recorded rather than negotiated at call time. A client that accepted whatever a
server offered would change behaviour when a vendor upgraded, which is a change
to what a customer's tile says arriving without a deploy.
"""


class ToolResult(Protocol):
    """What `call_tool` returns, narrowed to the two fields that decide anything.

    Named after the SDK's `CallToolResult` and matching its attribute spelling,
    so the real object satisfies this without an adapter.
    """

    @property
    def is_error(self) -> bool | None: ...

    @property
    def structured_content(self) -> dict[str, Any] | None: ...


class Session(Protocol):
    """An initialised MCP session. `mcp.ClientSession` satisfies this as it is."""

    async def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> Any: ...


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

        result: ToolResult = await self._session.call_tool(tool, dict(call.arguments))

        # **`is_error` is a result, not an exception.** MCP reports a tool
        # failure inside a *successful* response, so a client that only caught
        # transport errors would treat "this tool failed" as a successful empty
        # fetch — and an empty fetch computes a figure of zero, which is the I10
        # violation this product exists to prevent, arriving through a protocol
        # detail.
        if result.is_error:
            raise ProviderUnavailableError(f"the provider's {call.name} tool reported a failure")

        content = result.structured_content
        if isinstance(content, Mapping):
            return content

        # No structured result. Deliberately **not** parsed out of the text
        # blocks: those are prose written for a model to read, and mining a
        # number out of them would be reading a figure from generated text —
        # precisely what I1 forbids, however convenient the string looks.
        raise ProviderUnavailableError(
            f"the provider returned no structured result for {call.name}"
        )
