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
from app.domain.registry import BY_ID


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
class FieldRequirement:
    """What one capability needs from the connected system, field by field.

    **Keyed by the capability's canonical id, not by a name of its own.** This
    was a third capability namespace — `stale_deals`, `pipeline_value`,
    `loss_analysis`, `conversion` — beside doc 05's numbers and doc 08's dotted
    names, and it produced a specific failure at the customer's eye level: the
    connect screen said *"Stale deal detection is unsupported"* and the tile it
    referred to was called *"Stale and at-risk deals"*. Two names for one thing
    reads as two features, one of which is broken.

    So the name is read from `domain/registry.py` and cannot drift from the
    tile's, and `_validate` refuses an id that is not a capability.
    """

    capability_id: str
    required_fields: tuple[str, ...]

    @property
    def name(self) -> str:
        return BY_ID[self.capability_id].name


@dataclass(frozen=True, slots=True)
class Completeness:
    """What this connection supports, and what it does not — with the reason."""

    supported: tuple[str, ...]
    unsupported: tuple[tuple[str, str], ...]
    """`(capability name, why)`, and the name is the tile's own.

    The reason names the missing field, because "unavailable" tells a customer
    nothing they can act on and a field name tells them exactly what to fix."""

    @property
    def fully_supported(self) -> bool:
        return not self.unsupported


# The CRM capabilities that depend on fields a system may or may not carry.
# `last_activity_at` is the one that most often does not exist, which is why
# doc 05 §9 names stale-deal detection specifically.
#
# Stage conversion sits under the forecast because that is where doc 08 §3C puts
# it: *"the stage-conversion table those weights come from"*. It is not a tile of
# its own, and inventing one to hold a field requirement would put a box on a
# screen to satisfy a mapping.
CRM_FIELD_REQUIREMENTS: Final[tuple[FieldRequirement, ...]] = (
    FieldRequirement("sales.stale_deal_alert", ("last_activity_at",)),
    FieldRequirement("sales.pipeline_board", ("amount", "stage_canonical")),
    FieldRequirement("sales.win_loss", ("loss_reason",)),
    FieldRequirement("sales.forecast", ("stage_canonical",)),
)


def _validate(requirements: tuple[FieldRequirement, ...]) -> None:
    """Every id names a capability. Import-time, for `skills.py`'s reason."""
    for requirement in requirements:
        if requirement.capability_id not in BY_ID:
            raise ValueError(
                f"{requirement.capability_id!r} is not a capability, so the connect"
                " screen would refuse a tile that does not exist."
            )


_validate(CRM_FIELD_REQUIREMENTS)


def check_completeness(
    available_fields: frozenset[str],
    requirements: tuple[FieldRequirement, ...] = CRM_FIELD_REQUIREMENTS,
) -> Completeness:
    """What this connection can compute. **Run at connect, reported immediately.**

    Reporting at connect rather than at render is the whole point: a customer
    who is told now can add the field or accept the gap, and a customer who
    finds out through an empty widget has learned that our widgets come up empty.
    """
    supported: list[str] = []
    unsupported: list[tuple[str, str]] = []

    for requirement in requirements:
        missing = [f for f in requirement.required_fields if f not in available_fields]
        if missing:
            unsupported.append(
                (
                    requirement.name,
                    f"needs {', '.join(missing)}, which this system does not provide",
                )
            )
        else:
            supported.append(requirement.name)

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
