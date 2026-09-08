"""Hooks: the points where the rest of the application observes the agent.

A hook is how onboarding tells the system something happened without knowing who
is listening. `context.updated` fires when the Brain or the Persona changes;
whether that triggers an embedding pass, an audit row, or nothing at all is not
onboarding's business.

Two rules, both learned rather than assumed:

**Hooks fire inside the caller's transaction, and handlers join it.** An earlier
version of this file claimed the opposite — that hooks fire after the commit —
and the code never did. Firing after would be wrong here anyway: `audit.record`
writes on the caller's session by design (see `apply_workspace_scope`), so an
audit row must be atomic with the thing it records. An audit trail that survives
a rolled-back write is a lie about what happened.

**Two classes of handler, because "isolated" is not always achievable.** A
handler that only logs can have its exception swallowed safely. A handler that
issued a failed statement cannot: Postgres marks the transaction aborted and
every later statement fails with `InFailedSQLTransactionError`, so swallowing
buys a confusing failure two calls downstream instead of a clear one here.

- `critical=False` (default) — telemetry, and anything without a database. The
  exception is logged and the turn continues.
- `critical=True` — audit, and anything that writes. The exception propagates and
  the transaction rolls back, which is the honest outcome: the answer and its
  audit row are one fact, and half of it is worse than neither.
"""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from app.logging import get_logger

log = get_logger(__name__)


class HookPoint(StrEnum):
    ONBOARDING_START = "onboarding.start"
    """A workspace has entered onboarding. Payload: workspace_id, user_id, domain."""

    ANSWER_SUBMITTED = "answer.submitted"
    """A person answered. Payload: workspace_id, target field key, scope, skill."""

    CONTEXT_UPDATED = "context.updated"
    """The Brain or the Persona changed. Payload: workspace_id, kind, keys."""

    ONBOARDING_COMPLETED = "onboarding.completed"
    """The journey finished. Payload: workspace_id, brain_version, counts."""

    SKILL_INVOKED = "skill.invoked"
    """Any skill ran. Payload: skill, version, attempts, tokens. Observability."""


@dataclass(frozen=True, slots=True)
class HookEvent:
    point: HookPoint
    workspace_id: str
    payload: Mapping[str, Any] = field(default_factory=dict)

    session: Any = None
    """The caller's open session, for handlers that write.

    Deliberately the *same* session rather than a fresh one. A handler that
    opened its own connection would not see the uncommitted write it is
    reacting to, and would record something that may never land.
    """


Handler = Callable[[HookEvent], Any | Awaitable[Any]]


@dataclass(frozen=True, slots=True)
class _Registration:
    name: str
    handler: Handler
    priority: int
    critical: bool


class HookBus:
    """Registration and dispatch. One per process."""

    def __init__(self) -> None:
        self._handlers: dict[HookPoint, list[_Registration]] = {}

    def on(
        self,
        point: HookPoint,
        *,
        name: str,
        priority: int = 100,
        critical: bool = False,
    ) -> Callable[[Handler], Handler]:
        """Register a handler. Lower priority runs first.

        `critical=True` means a failure here fails the turn. Reserve it for
        handlers that write — the module docstring explains why swallowing
        those does not work.
        """

        def decorate(handler: Handler) -> Handler:
            registrations = self._handlers.setdefault(point, [])
            if any(existing.name == name for existing in registrations):
                # Names are how a handler is identified in logs and how a test
                # asserts it ran. Two handlers sharing one is a silent override.
                raise ValueError(f"a handler named {name!r} is already registered for {point}")
            registrations.append(
                _Registration(name=name, handler=handler, priority=priority, critical=critical)
            )
            # Critical first: an audit write should be attempted before a
            # telemetry handler gets the chance to fail and mask it.
            registrations.sort(key=lambda r: (0 if r.critical else 1, r.priority, r.name))
            return handler

        return decorate

    def handlers_for(self, point: HookPoint) -> tuple[str, ...]:
        return tuple(r.name for r in self._handlers.get(point, ()))

    async def emit(self, event: HookEvent) -> None:
        """Run every handler. Isolate the ones that can be isolated."""
        registrations = self._handlers.get(event.point, ())
        for registration in registrations:
            try:
                result = registration.handler(event)
                if inspect.isawaitable(result):
                    await result
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                if registration.critical:
                    log.warning(
                        "hook.failed.critical",
                        point=str(event.point),
                        handler=registration.name,
                        error=type(exc).__name__,
                    )
                    raise
                log.warning(
                    "hook.failed",
                    point=str(event.point),
                    handler=registration.name,
                    error=type(exc).__name__,
                )


_bus: HookBus | None = None


def get_hooks() -> HookBus:
    global _bus
    if _bus is None:
        _bus = HookBus()
        # Imported for the side effect of registering. Assigned above first, so
        # the handlers module calling back into `get_hooks()` sees the bus that
        # is already being built rather than recursing into a second one.
        from app.domain import onboarding_hooks  # noqa: F401
    return _bus
