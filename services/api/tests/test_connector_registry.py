"""Which providers can actually be read, and the gap that must never open.

A Connect button is an authorisation request. A customer who presses one hands
us read access to their CRM, and the worst outcome is not an error — it is that
nothing happens, because the provider was offered by the ledger and implemented
by nobody. They authorised us and got a tile that still says `locked`, with no
way to tell that from a connection that failed.

So these assert the three lists agree: what `domain/connections.py` offers a
customer, what `domain/sources.py` can place against a capability, and what
`connectors/registry.py` can actually read.

Hermetic — all three are tables built at import.
"""

from __future__ import annotations

import pytest

from app.connectors.contracts import ProviderMisconfiguredError
from app.connectors.hubspot import HubSpotDeals
from app.connectors.registry import WIRING, adapter_over, wiring_for
from app.domain.connections import PROVIDERS
from app.domain.sources import PROVIDER_SOURCES, source_for_provider


class _Session:
    async def call_tool(self, name: str, arguments: dict[str, object] | None = None) -> object:
        raise AssertionError("nothing in this file should reach a provider")


# ── The three lists agree ─────────────────────────────────────


def test_every_wired_provider_is_one_a_customer_can_actually_declare() -> None:
    """An adapter for a provider the connect screen never offers is dead code
    that reads as coverage — it would make `WIRING` look twice the size it is."""
    offered = {tool.id for tool in PROVIDERS}

    assert set(WIRING) <= offered, sorted(set(WIRING) - offered)


def test_every_wired_provider_satisfies_a_source() -> None:
    """`source_for_provider` raises for a provider that satisfies nothing, on
    the grounds that it is a row no tile will ever read. An adapter for one
    would be the same dead end with more code behind it."""
    for provider in WIRING:
        assert source_for_provider(provider) is not None


def test_the_adapter_declares_the_source_the_ledger_places_it_in() -> None:
    """The failure this catches has no symptom: an adapter bound to the wrong
    source populates a tile with another system's shape of data, and the tile
    renders it."""
    for provider in WIRING:
        adapter = adapter_over(provider, _Session())
        assert adapter.source is PROVIDER_SOURCES[provider]
        assert adapter.provider == provider


# ── A provider with no adapter is refused, loudly ─────────────


def test_an_unwired_provider_raises_rather_than_returning_nothing() -> None:
    """Returning `None` would let a provider nobody implemented pass as an
    ordinary absence — and the customer finds out after authorising us."""
    with pytest.raises(ProviderMisconfiguredError, match="no adapter"):
        wiring_for("salesforce")


def test_the_refusal_names_the_provider_and_what_it_would_have_cost() -> None:
    with pytest.raises(ProviderMisconfiguredError) as raised:
        wiring_for("not_a_crm")

    message = str(raised.value)
    assert "not_a_crm" in message
    assert "authorise" in message


# ── Only what is genuinely readable is wired ──────────────────


def test_only_hubspot_is_wired_today() -> None:
    """**Pinned deliberately.**

    Four other vendors publish an official MCP server, and adding them here is
    one line each. It would also be four Connect buttons that authorise us and
    then do nothing, because an entry in `WIRING` claims *this can be read
    today* and only HubSpot has an adapter. `doc/14` step 11 adds the rest, each
    paired with a calculator.
    """
    assert set(WIRING) == {"hubspot"}


def test_hubspot_is_wired_to_its_own_url_and_its_own_tool_names() -> None:
    """Parallel maps keyed by provider are how one ends up with HubSpot's URL
    and another vendor's tool names — a failure that surfaces at the vendor, as
    a message about an unknown tool, pointing at the wrong file."""
    wiring = wiring_for("hubspot")

    assert "hubspot.com" in wiring.mcp_url
    assert wiring.mcp_url.startswith("https://")
    assert all(name.startswith("hubspot-") for name in wiring.tools.values())
    assert wiring.adapter is HubSpotDeals
