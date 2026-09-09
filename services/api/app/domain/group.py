"""The group roll-up, and the one read in this product that spans tenants.

ADR 0026 and `doc/13` §4.1. One login may hold several entities, each with its
own Brain, tools, departments and directors — and a group view across the ones
they hold.

**Everything else in this codebase is built so that a cross-tenant read cannot
happen.** `retrieval/` takes a `ScopedSession` scoped to exactly one
`nexus.workspace_id`; `nexus_app` is `NOBYPASSRLS`, so a query with no
workspace set returns **zero rows rather than an error**, which reads as an
empty table. That is the property this module must not break, and the way it
would break is obvious and tempting: loosen the predicate, add `IN (:ids)`, and
let one query answer for several workspaces.

So it does not do that. The shape is:

1. resolve the caller's memberships — from `membership_own_rows`, not from a
   list anybody supplied;
2. open **one scoped session per workspace**, and compute each entity's figures
   inside its own scope;
3. aggregate **outside** the database, in `calculators/`, which is pure;
4. carry per-entity provenance, so a group number always breaks back down into
   the entities it came from.

Slower, and deliberately. A single loosened query would be one round trip
instead of N, and the first bug in it would be invisible: a workspace id
appearing in a list it should not be in returns rows rather than an error, and
nothing on the screen would say so.

## Three rules the surface holds

**The denominator travels, at group level too.** *"Four entities, three
scored"* — and it names the unscored one and what it needs. Never an average
that hides an absence.

**Departments are per entity, not per person.** Somebody may be Finance at one
entity and Operations at another, so a per-entity figure is computed under that
entity's own scope. This is where ADR 0026's cache-invalidation consequence
would bite if anything were cached across a switch.

**The group view is a property of memberships, never of a role.** An invitation
names one entity. Being an Owner of one company grants nothing at another, and
there is no group-level role — `EntityFigure` is built from a membership or it
is not built.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.service import Membership, build_scope, memberships_for_user
from app.domain.scopes import Department
from app.domain.session import ScopedSession
from app.logging import get_logger

log = get_logger(__name__)


class UnscopedGroupReadError(Exception):
    """A group read was attempted without resolving memberships first.

    Raised rather than returning nothing, because returning nothing is what an
    unscoped query already does — silently, and indistinguishably from a group
    that genuinely holds no entities.
    """


@dataclass(frozen=True, slots=True)
class EntityFigure[TValue]:
    """One entity's answer, and which entity it came from.

    Generic over the value so this module computes nothing itself. What an
    entity's "figure" is belongs to the caller — a score, a count, a context —
    and a module that decided would be a second place numbers come from.
    """

    workspace_id: UUID
    scope: ScopedSession
    value: TValue

    @property
    def departments(self) -> frozenset[Department]:
        """This entity's departments for this person, not the group's.

        Read off the scope built from *this* entity's membership. Somebody may
        be Finance at one and Operations at another, and a group view that
        reported one person's departments as a single set would be wrong about
        every entity but one.
        """
        return self.scope.departments


@dataclass(frozen=True, slots=True)
class GroupReading[TValue]:
    """What every entity answered, and what could not be asked."""

    entities: tuple[EntityFigure[TValue], ...]
    unreadable: tuple[UUID, ...]
    """Entities whose figure could not be computed. **Named, never dropped** —
    a group total quietly missing one company is the failure this field exists
    to prevent, and it is indistinguishable from a smaller group otherwise."""

    @property
    def covered(self) -> int:
        return len(self.entities)

    @property
    def total(self) -> int:
        """The denominator, which travels with every group figure.

        *"Three of four"* is checkable by somebody who can count their own
        companies. A bare average is not.
        """
        return len(self.entities) + len(self.unreadable)

    @property
    def complete(self) -> bool:
        return not self.unreadable


async def read_across_entities[TValue](
    *,
    user_id: UUID,
    session_factory: Callable[[], AbstractAsyncContextManager[AsyncSession]],
    open_scoped: Callable[[ScopedSession], Awaitable[TValue]],
) -> GroupReading[TValue]:
    """Compute one figure per entity, each inside its own scope.

    `open_scoped` receives a `ScopedSession` for one entity and returns that
    entity's value. It is passed in rather than imported so this module names no
    capability and computes nothing — and so the caller cannot hand it a
    workspace id, only a scope that was built from a membership.

    **One session per entity.** Reusing one connection across workspaces would
    mean resetting `nexus.workspace_id` between reads, and a read that ran
    before the reset would answer for the previous entity. That failure is
    silent: rows come back, they are simply the wrong company's.

    An entity that raises is recorded in `unreadable` rather than aborting the
    group. One company's accounting being unreachable should not blank the other
    three — but it must not quietly shrink the denominator either.
    """
    async with session_factory() as db:
        memberships = await memberships_for_user(db, user_id=user_id)

    if not memberships:
        # Not an error: a person with no membership has no group, and
        # `current_scope` has already refused them anything workspace-scoped.
        return GroupReading(entities=(), unreadable=())

    entities: list[EntityFigure[TValue]] = []
    unreadable: list[UUID] = []

    for membership in _ordered(memberships):
        scope = build_scope(user_id=user_id, membership=membership)
        try:
            value = await open_scoped(scope)
        except Exception:
            log.warning(
                "group.entity_unreadable",
                workspace_id=str(membership.workspace_id),
                exc_info=True,
            )
            unreadable.append(membership.workspace_id)
            continue

        entities.append(
            EntityFigure(
                workspace_id=membership.workspace_id,
                scope=scope,
                value=value,
            )
        )

    return GroupReading(entities=tuple(entities), unreadable=tuple(unreadable))


def _ordered(memberships: list[Membership]) -> list[Membership]:
    """Sorted by workspace id.

    Stable, so the same group produces the same order on every read — a roll-up
    whose rows move between page loads reads as data changing when only the
    iteration did.
    """
    return sorted(memberships, key=lambda m: str(m.workspace_id))
