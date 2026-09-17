"""Which adapter reads which provider, and how one is built for a workspace.

The join between `workspace_connection.provider` — a string a customer chose —
and the code that can read that system. Two things it exists to prevent:

**A provider nobody can read.** `domain/sources.py` already refuses to place a
provider that satisfies no source, on the grounds that it is a row no tile will
ever read. This is the same guard one layer out: a provider the ledger offers
and no adapter implements is a Connect button that leads nowhere, and the
customer finds out after authorising us.

**An adapter reading with the wrong customer's credential.** `build` takes the
sealed credential rather than a workspace id, so it cannot reach for one itself.
The scoping is the caller's, done through `retrieval/` under a `ScopedSession`,
and an adapter that could load its own credential would be a second path to the
same data with no permission predicate on it (I2/I3).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final, Protocol

from app.connectors.contracts import ProviderMisconfiguredError, SourceAdapter, Transport
from app.connectors.hubspot import MCP_URL as HUBSPOT_MCP_URL
from app.connectors.hubspot import PROVIDER as HUBSPOT
from app.connectors.hubspot import TOOLS as HUBSPOT_TOOLS
from app.connectors.hubspot import HubSpotDeals
from app.connectors.mcp import McpTransport, Session


class AdapterFactory(Protocol):
    def __call__(self, transport: Transport) -> SourceAdapter: ...


class Wiring:
    """Everything needed to reach one provider: where, which tools, what reads it.

    A frozen record rather than four parallel dictionaries keyed by provider id.
    Parallel maps are how a provider ends up with HubSpot's URL and Pipedrive's
    tool names, which would fail at the vendor with a message about an unknown
    tool and send somebody looking in the wrong file.
    """

    __slots__ = ("adapter", "mcp_url", "tools")

    def __init__(self, *, mcp_url: str, tools: Mapping[str, str], adapter: AdapterFactory) -> None:
        self.mcp_url = mcp_url
        self.tools = dict(tools)
        self.adapter = adapter


WIRING: Final[Mapping[str, Wiring]] = {
    HUBSPOT: Wiring(mcp_url=HUBSPOT_MCP_URL, tools=HUBSPOT_TOOLS, adapter=HubSpotDeals),
}
"""One entry. `doc/14` step 11 adds the rest, each paired with a calculator.

Deliberately not pre-populated with the four other vendors that publish an MCP
server. An entry here says *this can be read today*, and four entries with no
adapter behind them would be four Connect buttons that authorise us and then do
nothing.
"""


def wiring_for(provider: str) -> Wiring:
    """How to reach a provider, or a refusal naming it.

    Raises rather than returning `None`, for the reason `source_for_provider`
    gives about the same class of miss: a provider we cannot place is a row no
    tile will ever read, and returning nothing lets that pass as an ordinary
    absence.
    """
    try:
        return WIRING[provider]
    except KeyError as unknown:
        raise ProviderMisconfiguredError(
            f"{provider!r} has no adapter, so connecting it would authorise a read nothing performs"
        ) from unknown


def adapter_over(provider: str, session: Session) -> SourceAdapter:
    """Bind an open MCP session to the adapter that knows what to ask it.

    The session is passed in rather than opened here so that the caller owns its
    lifetime — one session per sweep, closed when the sweep ends, which is what
    keeps an access token in memory for seconds rather than for as long as the
    process lives.
    """
    wiring = wiring_for(provider)
    return wiring.adapter(McpTransport(session=session, tools=wiring.tools))
