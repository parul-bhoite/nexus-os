"""What a connection can and cannot compute, and what happens when it stops.

`doc/12` P18. The OAuth half waits on **D3** (Google credentials) and **D10**
(the CRM choice); this is everything that does not.

**Field completeness is checked at connect, not discovered later** (doc 05 §9).
A CRM without `last_activity_at` cannot support stale-deal detection, and the
difference between saying so at connect and letting the widget come up empty is
the difference between a limitation and a bug. The customer can act on the
first — add the field, or accept the gap — and can only lose confidence in the
second.

**A revoked token degrades to stale, never to zero.** The number we last saw was
real; what has stopped is our ability to refresh it. Rendering zero would claim
their pipeline emptied overnight, which is a statement about their business made
out of a statement about our access.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from app.domain.dashboards import WidgetState


class ConnectionState(StrEnum):
    """The lifecycle of one workspace's relationship with one tool.

    One enum rather than two because it is one lifecycle: a tool is named, then
    reached, and then possibly lost. `ck_workspace_connection_state` is this
    list, and `test_constraint_enum_parity` holds the two together.
    """

    DECLARED = "declared"
    """The customer told us they run this system. We have never reached it.

    The state every row starts in, and — until the OAuth half below lands — the
    only state any row is in. It exists because *knowing* a company's pipeline
    is in HubSpot is worth something on its own: it grounds what the Brain says
    about how they work, and it turns an empty tile into a named gap with a
    named unlock rather than an absence. What it must never do is imply we can
    read anything, which is why it is a state on the row and not the row's mere
    existence — see `app/domain/connections.py`.
    """

    CONNECTED = "connected"
    REVOKED = "revoked"
    """The customer or the provider withdrew access. Not an error on their part
    and not one on ours — but everything downstream is now as old as the last
    successful read."""

    SCOPE_REDUCED = "scope_reduced"
    """Still connected, with less than we asked for.

    **The dangerous one.** A downgraded scope returns data that parses, looks
    valid, and is silently incomplete — a CRM that hands back deals but no
    activity timestamps produces a pipeline view that is right about totals and
    wrong about everything time-based, with nothing to indicate which."""


@dataclass(frozen=True, slots=True)
class Capability:
    """One thing a connector could compute, and the fields it needs."""

    id: str
    name: str
    required_fields: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Completeness:
    """What this connection supports, and what it does not — with the reason."""

    supported: tuple[str, ...]
    unsupported: tuple[tuple[str, str], ...]
    """`(capability name, why)`. The reason names the missing field, because
    "unavailable" tells a customer nothing they can act on and a field name
    tells them exactly what to fix."""

    @property
    def fully_supported(self) -> bool:
        return not self.unsupported


# The CRM capabilities that depend on fields a system may or may not carry.
# `last_activity_at` is the one that most often does not exist, which is why
# doc 05 §9 names stale-deal detection specifically.
CRM_CAPABILITIES: Final[tuple[Capability, ...]] = (
    Capability("stale_deals", "Stale deal detection", ("last_activity_at",)),
    Capability("pipeline_value", "Pipeline value", ("amount", "stage_canonical")),
    Capability("loss_analysis", "Why deals are lost", ("loss_reason",)),
    Capability("conversion", "Stage conversion", ("stage_canonical",)),
)


def check_completeness(
    available_fields: frozenset[str], capabilities: tuple[Capability, ...] = CRM_CAPABILITIES
) -> Completeness:
    """What this connection can compute. **Run at connect, reported immediately.**

    Reporting at connect rather than at render is the whole point: a customer
    who is told now can add the field or accept the gap, and a customer who
    finds out through an empty widget has learned that our widgets come up empty.
    """
    supported: list[str] = []
    unsupported: list[tuple[str, str]] = []

    for capability in capabilities:
        missing = [f for f in capability.required_fields if f not in available_fields]
        if missing:
            unsupported.append(
                (
                    capability.name,
                    f"needs {', '.join(missing)}, which this system does not provide",
                )
            )
        else:
            supported.append(capability.name)

    return Completeness(supported=tuple(supported), unsupported=tuple(unsupported))


def state_for_connection(
    connection: ConnectionState, *, had_data: bool, age_days: int, stale_after_days: int
) -> WidgetState:
    """What a tile renders as when the connection is not healthy.

    **Never `LIVE` on a revoked token**, however fresh the cached figure looks —
    "live" is a claim about now, and we no longer have access to now.

    **Never zero.** The last number we saw was real; what stopped is our ability
    to refresh it. Zero would claim their pipeline emptied overnight, which is a
    statement about their business made out of a statement about our access.
    """
    if connection is ConnectionState.CONNECTED:
        return WidgetState.STALE if age_days > stale_after_days else WidgetState.LIVE

    if not had_data:
        # Nothing was ever read, so there is nothing to go stale. `LOCKED` names
        # the missing connection rather than implying an old number exists.
        return WidgetState.LOCKED

    return WidgetState.STALE
