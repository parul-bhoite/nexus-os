"""The HubSpot adapter — `doc/14` step 9, the first real connector.

Driven through a fake MCP session rather than a sandbox: what is worth asserting
here is the **shaping**, and a vendor account would make these tests slow,
credentialed and no more truthful about the thing that can go wrong.

Three failures, and none of them looks like a bug on screen:

- **Summing on the way past.** The pipeline total is right there in the loop,
  and a connector that returned it would have produced a number outside
  `calculators/` — the thing I1 exists to forbid.
- **A `.get` default turning an absence into a zero.** A deal nobody has priced
  is not a deal worth nothing, and the tile renders those identically.
- **A silent page boundary.** A figure computed over the first hundred deals and
  presented as the pipeline is a wrong number with a plausible denominator.

`test_connector_boundary.py` holds the transport's rules; this holds HubSpot's.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from app.connectors.contracts import ProviderMisconfiguredError, ProviderUnavailableError
from app.connectors.hubspot import MCP_URL, PROVIDER, TOOLS, HubSpotDeals
from app.connectors.mcp import McpTransport
from app.domain.dashboards import Source
from app.domain.sources import source_for_provider

DEALS: dict[str, Any] = {
    "results": [
        {
            "id": "101",
            "properties": {
                "dealname": "Sohar Industrial Park",
                "amount": "31500",
                "dealstage": "closedwon",
                "closedate": "2026-08-30",
                "pipeline": "default",
            },
        },
        {
            "id": "102",
            "properties": {
                "dealname": "Muscat Fit-Out LLC",
                # Deliberately unpriced — a real state, and the one a `.get(…, 0)`
                # would quietly turn into a deal worth nothing.
                "dealstage": "proposal",
                "closedate": "2026-10-15",
                "pipeline": "default",
            },
        },
    ]
}


class FakeResult:
    def __init__(self, content: dict[str, Any] | None, *, is_error: bool = False) -> None:
        self.structured_content = content
        self.is_error = is_error


class FakeSession:
    """Records what was asked for, answers with what it was given."""

    def __init__(self, result: FakeResult) -> None:
        self.result = result
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> FakeResult:
        self.calls.append((name, dict(arguments or {})))
        return self.result


def _adapter(result: FakeResult) -> tuple[HubSpotDeals, FakeSession]:
    session = FakeSession(result)
    return HubSpotDeals(McpTransport(session=session, tools=TOOLS)), session


# ── It reads deals, and nothing else ──────────────────────────


@pytest.mark.anyio
async def test_it_returns_the_provider_s_records_and_never_a_total() -> None:
    """**The failure this adapter is most likely to have.**

    The sum is right there in the loop. A connector that returned it would have
    computed a figure outside `calculators/`, and the tile would look identical
    until somebody asked where the number came from.
    """
    adapter, _ = _adapter(FakeResult(DEALS))

    fetched = await adapter.fetch()

    assert len(fetched.rows) == 2
    assert not hasattr(fetched, "total")
    assert not any(key in fetched.rows[0] for key in ("total", "sum", "value"))


@pytest.mark.anyio
async def test_an_unpriced_deal_stays_unpriced() -> None:
    """I10 through a `.get` default. A deal nobody has priced is not a deal worth
    nothing, and `sales.pipeline_value` must be able to tell the two apart."""
    adapter, _ = _adapter(FakeResult(DEALS))

    fetched = await adapter.fetch()

    assert fetched.rows[0]["amount"] == "31500"
    assert fetched.rows[1]["amount"] is None


@pytest.mark.anyio
async def test_it_keeps_the_fields_a_calculator_will_read_and_drops_the_rest() -> None:
    """Deals, amount, stage, close date. Not contacts, notes or email threads —
    holding a customer's personal data for a figure that never reads it is a
    cost with no benefit, and the tile looks the same either way."""
    adapter, _ = _adapter(FakeResult(DEALS))

    row = (await adapter.fetch()).rows[0]

    assert set(row) == {"id", "name", "amount", "stage", "closes_on", "pipeline"}


@pytest.mark.anyio
async def test_it_asks_only_for_the_tool_it_declares() -> None:
    """The argument that a connector is safe rests on **we** choose the calls.
    A transport handed a free-form query would reach anything the credential
    can."""
    adapter, session = _adapter(FakeResult(DEALS))

    await adapter.fetch()

    assert [name for name, _ in session.calls] == ["hubspot-list-objects"]
    assert session.calls[0][1]["objectType"] == "deals"


@pytest.mark.anyio
async def test_a_since_is_passed_through_as_utc() -> None:
    """Not an optimisation: a sweep that re-read every deal each time spends a
    customer's API quota to learn nothing."""
    adapter, session = _adapter(FakeResult(DEALS))

    await adapter.fetch(since=datetime(2026, 9, 1, 12, 0, tzinfo=UTC))

    assert session.calls[0][1]["since"].startswith("2026-09-01T12:00:00")


@pytest.mark.anyio
async def test_no_since_means_no_since_rather_than_the_epoch() -> None:
    adapter, session = _adapter(FakeResult(DEALS))

    await adapter.fetch()

    assert "since" not in session.calls[0][1]


# ── Truncation is reported, never hidden ──────────────────────


@pytest.mark.anyio
async def test_a_further_page_is_reported() -> None:
    """A figure over the first hundred deals, presented as the pipeline, is a
    wrong number with a plausible denominator — worse than no number."""
    adapter, _ = _adapter(FakeResult({**DEALS, "paging": {"next": {"after": "100"}}}))

    assert (await adapter.fetch()).truncated is True


@pytest.mark.anyio
async def test_a_complete_page_is_not_reported_as_truncated() -> None:
    adapter, _ = _adapter(FakeResult(DEALS))

    assert (await adapter.fetch()).truncated is False


@pytest.mark.anyio
async def test_no_deals_is_an_empty_fetch_and_not_a_failure() -> None:
    """A workspace with an empty pipeline is a real state. The calculator decides
    what an empty list means; the adapter does not get to call it an error."""
    adapter, _ = _adapter(FakeResult({"results": []}))

    fetched = await adapter.fetch()

    assert fetched.rows == []
    assert fetched.source is Source.CRM


# ── Failures arrive as the right kind ─────────────────────────


@pytest.mark.anyio
async def test_a_tool_failure_is_not_an_empty_pipeline() -> None:
    """MCP reports a tool failure inside a successful response. Read as an empty
    fetch it computes a pipeline of zero — which says this company has no deals
    where the truth is that nobody could look."""
    adapter, _ = _adapter(FakeResult(None, is_error=True))

    with pytest.raises(ProviderUnavailableError):
        await adapter.fetch()


@pytest.mark.anyio
async def test_a_tool_the_map_does_not_hold_is_a_misconfiguration() -> None:
    session = FakeSession(FakeResult(DEALS))
    adapter = HubSpotDeals(McpTransport(session=session, tools={}))

    with pytest.raises(ProviderMisconfiguredError):
        await adapter.fetch()


# ── It agrees with the rest of the model ──────────────────────


def test_the_adapter_satisfies_the_source_the_ledger_says_it_does() -> None:
    """Declared on the class and joined in `domain/sources.py`. An adapter wired
    to the wrong source would populate a tile with another system's shape of
    data, and nothing else would notice."""
    assert HubSpotDeals.source is source_for_provider(PROVIDER) is Source.CRM


def test_the_provider_url_is_fixed_rather_than_configurable() -> None:
    """A settable provider URL is how a connector ends up talking to somebody's
    proxy. A customer does not get to point us at a different HubSpot."""
    assert MCP_URL.startswith("https://")
    assert "hubspot.com" in MCP_URL
