"""The connector spine, and the rule that makes MCP safe to use here.

`doc/14` step 8's acceptance test, ADR 0031.

> **The API process is the client. No model ever sees a provider.**

That is the sentence the whole design rests on, and it is the one that would be
broken by a convenient shortcut rather than by a decision — somebody hands a
director the CRM's tools because it answers well, and I1 is gone while every
answer stays plausible. These tests assert it structurally.

The other thing proved here is that the two transports are interchangeable.
Vendor MCP availability moves — Pipedrive shipped a server in June 2026 that did
not exist in March — so an adapter must not be able to tell which one it has.

Hermetic. A fake provider on both transports, no network and no vendor account.
"""

from __future__ import annotations

import importlib
import inspect
import pkgutil
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest

import app.connectors
from app.connectors.contracts import (
    Fetched,
    ProviderMisconfiguredError,
    ProviderUnavailableError,
    ToolCall,
    Transport,
)
from app.connectors.mcp import McpTransport
from app.connectors.rest import RestTransport
from app.domain.dashboards import Source

DEALS: dict[str, Any] = {
    "items": [
        {"id": "1", "name": "Sohar Industrial Park", "amount": "31500", "stage": "won"},
        {"id": "2", "name": "Muscat Fit-Out LLC", "amount": "11300", "stage": "proposal"},
    ]
}

TOKEN = "secret-token-do-not-log"


# ── A fake provider, reachable both ways ──────────────────────


class FakeResult:
    """`mcp.types.CallToolResult` narrowed to the two fields that decide anything.

    Matching the SDK's attribute spelling rather than a shape of our own: the
    first version of this fake implemented an invented `send(method, params)`
    seam, and when `McpTransport` was corrected to the SDK's `call_tool` the
    fake was the only thing still speaking the old protocol. A double that
    cannot be swapped for the real object is a double that proves nothing.
    """

    def __init__(self, content: dict[str, Any] | None, *, is_error: bool = False) -> None:
        self.structured_content = content
        self.is_error = is_error


class FakeSession:
    """An MCP session that answers from a dict."""

    def __init__(self, result: FakeResult) -> None:
        self.result = result
        self.calls: list[tuple[str, Mapping[str, Any]]] = []

    async def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> FakeResult:
        self.calls.append((name, dict(arguments or {})))
        return self.result


def _rest(handler: object) -> RestTransport:
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))  # type: ignore[arg-type]
    return RestTransport(
        base_url="https://api.example.com",
        routes={"deals": ("GET", "/crm/deals")},
        token=TOKEN,
        client=client,
    )


async def _adapter_rows(transport: Transport) -> Fetched:
    """The shape every adapter has: one named call, rows out, no figure.

    Stands in for a real adapter so the test is about the spine rather than
    about any vendor's field names.
    """
    payload = await transport.call(ToolCall("deals", {"since": "2026-09-01"}))
    return Fetched(
        source=Source.CRM,
        rows=list(payload.get("items", [])),
        fetched_at=datetime(2026, 9, 17, 8, 0, tzinfo=UTC),
    )


# ── The two transports are interchangeable ────────────────────


@pytest.mark.anyio
async def test_both_transports_land_identical_rows() -> None:
    """**The acceptance test.** An adapter must not be able to tell which
    transport it has, or every vendor launch becomes a change across layers."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=DEALS)

    over_rest = await _adapter_rows(_rest(handler))
    over_mcp = await _adapter_rows(
        McpTransport(session=FakeSession(FakeResult(DEALS)), tools={"deals": "list_deals"})
    )

    assert over_rest.rows == over_mcp.rows
    assert over_rest.source is over_mcp.source is Source.CRM


@pytest.mark.anyio
async def test_a_call_the_connector_never_declared_is_a_misconfiguration() -> None:
    """Both transports refuse the same way, and refuse as a *bug* rather than a
    state — retrying on a schedule would repeat it for ever."""

    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover - never reached
        return httpx.Response(200, json={})

    for transport in (
        _rest(handler),
        McpTransport(session=FakeSession(FakeResult(None)), tools={"deals": "list_deals"}),
    ):
        with pytest.raises(ProviderMisconfiguredError):
            await transport.call(ToolCall("invoices"))


# ── Nothing computes on the way past ──────────────────────────


@pytest.mark.anyio
async def test_the_spine_returns_records_and_never_a_figure() -> None:
    """**`rows` are not figures.**

    A connector that totalled the pipeline on the way past would have produced a
    number outside `calculators/`, which is what I1 forbids — and it is exactly
    what a rushed adapter does, because the total is right there.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=DEALS)

    fetched = await _adapter_rows(_rest(handler))

    assert [row["amount"] for row in fetched.rows] == ["31500", "11300"]
    assert not hasattr(fetched, "total")
    assert all(isinstance(row, Mapping) for row in fetched.rows)


def test_no_module_in_the_spine_can_reach_a_model() -> None:
    """**The rule this package exists to hold**, asserted against the source.

    A director handed a provider's tools answers well and fetches its own
    numbers, and I1 is gone while every answer stays plausible. Checked as an
    import graph rather than by review, because the shortcut is one line and
    reads as an improvement.
    """
    forbidden = ("app.ai", "app.grounding")

    for info in pkgutil.walk_packages(
        app.connectors.__path__, prefix=f"{app.connectors.__name__}."
    ):
        module = importlib.import_module(info.name)
        source = inspect.getsource(module)
        for name in forbidden:
            assert f"import {name}" not in source, f"{info.name} reaches into {name}"
            assert f"from {name}" not in source, f"{info.name} reaches into {name}"


# ── Failures say which kind they are ──────────────────────────


@pytest.mark.anyio
async def test_a_refused_credential_is_never_retried() -> None:
    """401 and 403 are the customer's to fix by reconnecting. A sweep that kept
    trying would burn the provider's rate limit to no effect."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "token revoked"})

    with pytest.raises(ProviderMisconfiguredError):
        await _rest(handler).call(ToolCall("deals"))


@pytest.mark.anyio
async def test_an_mcp_tool_failure_is_not_an_empty_success() -> None:
    """**The protocol detail that would become an I10 violation.**

    MCP reports a tool failure inside a *successful* response. A client that only
    caught transport errors would read `isError` as a successful empty fetch —
    and an empty fetch computes a figure of zero, which says this company scored
    nothing where the truth is that nobody could look.
    """
    transport = McpTransport(
        session=FakeSession(FakeResult(None, is_error=True)),
        tools={"deals": "list_deals"},
    )

    with pytest.raises(ProviderUnavailableError):
        await transport.call(ToolCall("deals"))


@pytest.mark.anyio
async def test_a_number_is_never_read_out_of_an_mcp_text_block() -> None:
    """Text blocks are prose written for a model to read. Mining a figure out of
    one is reading a number from generated text, however convenient the string
    looks — so a result with no `structuredContent` is unavailable, not parsed."""
    transport = McpTransport(
        # A text-only answer: prose written for a model to read. Mining "42" out
        # of it would be reading a figure from generated text.
        session=FakeSession(FakeResult(None)),
        tools={"deals": "list_deals"},
    )

    with pytest.raises(ProviderUnavailableError):
        await transport.call(ToolCall("deals"))


# ── Credentials stay out of everything a human reads ──────────


@pytest.mark.anyio
async def test_no_failure_path_puts_the_credential_in_its_message() -> None:
    """`str(error)` reaches logs and, summarised, a screen. A token interpolated
    into a message is in both, and no care at the call site takes it back out."""

    def refuses(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "boom"})

    def breaks(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("failed connecting to https://api.example.com?key=" + TOKEN)

    for handler, error in ((refuses, ProviderUnavailableError), (breaks, ProviderUnavailableError)):
        with pytest.raises(error) as raised:
            await _rest(handler).call(ToolCall("deals"))
        assert TOKEN not in str(raised.value)


@pytest.mark.anyio
async def test_the_credential_travels_in_a_header_and_not_a_query_string() -> None:
    """A URL reaches access logs, proxies and error trackers; a header does not
    reach most of them. Asserted because the convenient version of this — a
    `?key=` parameter — is what several provider docs show."""
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=DEALS)

    await _rest(handler).call(ToolCall("deals", {"since": "2026-09-01"}))

    assert seen[0].headers["Authorization"] == f"Bearer {TOKEN}"
    assert TOKEN not in str(seen[0].url)
