"""HubSpot, over its own MCP server — the first real connector.

`doc/14` step 9. HubSpot is chosen ahead of accounting for a reason that is not
about HubSpot: **D7 is open.** Whether Finance brings accounting in at all is
undecided, so building that connector first would be building on a decision
nobody has made. CRM has no such question hanging over it, and HubSpot publishes
an official vendor-hosted MCP server.

## What it fetches, and what it deliberately does not

Deals, with their amount, stage and close date. That is what
`sales.pipeline_value` needs and nothing more. A connector that also pulled
contacts, notes and email threads "while it was there" would be holding a great
deal of a customer's personal data for a figure that never reads it — and the
tile would look identical either way, which is what makes the temptation worth
naming.

## Rows, never figures

`fetch` returns the deals as the provider described them, normalised only enough
to store. **Summing the pipeline here would be a number produced outside
`calculators/`**, which is exactly what I1 forbids and exactly what a rushed
adapter does, because the total is right there in the loop. The sum happens in
`calculators/pipeline.py`, from the stored rows, where it can be shown its
working.

## Everything here is untrusted

A deal name is whatever a salesperson typed. `ARCHITECTURE-HLD`'s untrusted
boundary covers it for the same reason it covers a crawled page, and an MCP
result invites the opposite assumption more strongly than HTML does because it
arrives shaped like a tool result.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any, Final

from app.connectors.contracts import Fetched, ToolCall, Transport
from app.domain.dashboards import Source

PROVIDER: Final = "hubspot"
MCP_URL: Final = "https://mcp.hubspot.com/anthropic"
"""HubSpot's hosted MCP endpoint.

A constant rather than configuration: a customer does not get to point us at a
different HubSpot, and a settable provider URL is how a connector ends up
talking to somebody's proxy. If HubSpot moves it, that is a deploy.
"""

TOOLS: Final[Mapping[str, str]] = {
    # Our vocabulary on the left, the server's on the right. The indirection
    # earns its keep the first time a second CRM names the same operation
    # differently: the adapter keeps one word and only this map changes.
    "deals": "hubspot-list-objects",
}

PAGE_LIMIT: Final = 100
"""One page, and `Fetched.truncated` says so when there was more.

A connector that silently stopped at a page would produce a figure computed over
part of the pipeline and presented as the whole of it — a wrong number with a
plausible denominator, which is worse than no number.
"""


def _row(deal: Mapping[str, Any]) -> dict[str, Any]:
    """One deal, flattened to what the calculator will read.

    Missing keys stay missing rather than becoming zero. An absent `amount` is a
    deal somebody has not priced, and a zero would make it a deal worth nothing —
    the substitution I10 exists to forbid, arriving through a `.get` default.
    """
    properties = deal.get("properties") or {}
    return {
        "id": str(deal.get("id", "")),
        "name": properties.get("dealname"),
        "amount": properties.get("amount"),
        "stage": properties.get("dealstage"),
        "closes_on": properties.get("closedate"),
        "pipeline": properties.get("pipeline"),
    }


class HubSpotDeals:
    """Reads a workspace's deals. Satisfies `Source.CRM`.

    Declared rather than inferred, so an adapter wired to the wrong source fails
    where somebody can see it instead of by populating a tile with the wrong
    company's shape of data. `PROVIDER_SOURCES` in `domain/sources.py` is the
    join this must agree with, and `test_hubspot_adapter.py` asserts it does.
    """

    source = Source.CRM
    provider = PROVIDER

    def __init__(self, transport: Transport) -> None:
        self._transport = transport

    async def fetch(self, *, since: datetime | None = None) -> Fetched:
        arguments: dict[str, Any] = {"objectType": "deals", "limit": PAGE_LIMIT}
        if since is not None:
            # Incremental where the provider supports it. Not an optimisation:
            # a sweep that re-read every deal every time would spend a
            # customer's API quota to learn nothing.
            arguments["since"] = since.astimezone(UTC).isoformat()

        payload = await self._transport.call(ToolCall("deals", arguments))
        results: Sequence[Mapping[str, Any]] = payload.get("results") or []

        return Fetched(
            source=self.source,
            rows=[_row(deal) for deal in results],
            # The provider's clock would be better and it does not offer one, so
            # this is ours and is honest about being the moment we asked rather
            # than the moment the data was true.
            fetched_at=datetime.now(UTC),
            # `paging.next` is HubSpot's cursor. Its presence means there was
            # more, and the figure computed from these rows must say so.
            truncated=bool((payload.get("paging") or {}).get("next")),
        )
