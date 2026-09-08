"""What listens to the onboarding agent.

Registered by importing this module — `get_hooks()` does it once, the same way
`get_commands()` loads the command registry. Handlers live here rather than in
the runtime so `app/ai/runtime` stays free of the domain layer it is meant to be
callable from.

Two handlers today, and the difference between them is the whole reason the bus
has two classes:

- **`audit-answer` is critical.** It writes, on the caller's session, inside the
  caller's transaction. If it fails the turn fails, because an answer recorded
  with no audit row is a worse outcome than a request the person can retry.
- **`telemetry` is not.** It logs and touches nothing. A broken log line must
  never cost somebody their signup.

**There is deliberately no handler on `onboarding.completed` that writes an
audit row.** `AuditAction` is a closed set of nine (`doc/12` §Phase 4) and none
of them means "a Brain was assembled". Reusing `ANSWER_WRITTEN` for it would put
a row in the log that means something other than what it says, and inventing a
member is a specification decision rather than a wiring one. Completion is
telemetry until that decision is made.

**There is also no handler that advances `onboarding_progress`.** Its stages are
`company`, `departments`, `review` — the *form* spine's. Marking `review` done
because the agent finished would assert a department-selection stage that never
ran, and `progress_for` would then report a journey nobody took.
"""

from __future__ import annotations

from uuid import UUID

from app.ai.runtime.hooks import HookEvent, HookPoint, get_hooks
from app.domain import audit
from app.logging import get_logger

log = get_logger(__name__)
hooks = get_hooks()


@hooks.on(HookPoint.ANSWER_SUBMITTED, name="audit-answer", critical=True)
async def audit_answer(event: HookEvent) -> None:
    """One `answer_written` row per answer, atomic with the answer itself.

    `target_id` is the declared field the answer was bound to, and `reason`
    carries the scope it was stored at. Those two together are what makes the
    log answerable in an incident: not "somebody typed something during
    onboarding" but "this field, at this sensitivity, by this person".

    Skips silently when there is no session on the event — a caller emitting
    without one is not writing to a database, and raising here would turn a
    unit test's convenience into a failure.
    """
    if event.session is None:
        return

    target = event.payload.get("target")
    actor = event.payload.get("actor_user_id")
    if not target:
        # An answer with no field is a free-text aside, not a fact. Nothing
        # downstream promotes it, so there is nothing to audit.
        return

    await audit.record(
        event.session,
        workspace_id=UUID(event.workspace_id),
        action=audit.AuditAction.ANSWER_WRITTEN,
        actor_user_id=UUID(str(actor)) if actor else None,
        target_type="onboarding_field",
        target_id=str(target),
        reason=f"scope=L{event.payload.get('scope')} via {event.payload.get('origin', 'agent')}",
    )


@hooks.on(HookPoint.ONBOARDING_START, name="telemetry-start")
@hooks.on(HookPoint.CONTEXT_UPDATED, name="telemetry-context")
@hooks.on(HookPoint.ONBOARDING_COMPLETED, name="telemetry-completed")
@hooks.on(HookPoint.SKILL_INVOKED, name="telemetry-skill")
def telemetry(event: HookEvent) -> None:
    """Structured counts and identifiers. Never content.

    `app/logging.py` raises on keys like `prompt`, and the same discipline
    applies to anything a person typed: the payloads emitted by the agent carry
    field keys, scopes and counts, and this handler forwards them unchanged
    rather than reaching into the event for text.
    """
    log.info(
        f"onboarding.{event.point.value}",
        workspace_id=event.workspace_id,
        **{k: v for k, v in event.payload.items() if k != "actor_user_id"},
    )
