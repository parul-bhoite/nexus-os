"""The audit trail — I9's substrate.

Doc 07 I9: every state-changing action leaves a record naming who did it, to
what, and when. `audit_log` has existed since migration 0002 and **nothing has
ever written to it**, which is the ordinary way an audit requirement dies: the
table is there, the schema review passes, and the log is empty.

Three properties, and each is a decision rather than a detail.

**One row per action, written in the same transaction as the action.** Not
after, and not best-effort. A log written on a separate connection is a log that
disagrees with the data whenever one of the two fails — and the disagreement is
silent, which is worse than no log, because a reader trusts it.

**The workspace owns the record.** `audit_log.workspace_id` is `NOT NULL` and
carries the same isolation policy as every other workspace-scoped table, so the
log a workspace can read is exactly its own. That has a consequence worth
stating plainly rather than discovering later: **an action taken before any
workspace exists cannot be logged here.** Registering, verifying an email,
resetting a password and signing in with no membership all happen to an account
rather than to a company, and there is no tenant to own the row. A NULL
`workspace_id` would not fix it — the isolation predicate compares against the
GUC, so a NULL row is invisible to everyone, which is a log entry that exists
and cannot be read. Account-level auditing needs its own stream, and this
module deliberately does not pretend to be it.

**Reading it is a privilege.** Owner and Executive, nobody else — enforced in
`app/routes/audit.py`, not here, for the same reason `retrieval/` owns the
permission predicate: the boundary is the query, not the caller's manners.
"""

from __future__ import annotations

from enum import StrEnum
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.retrieval.scoped import apply_workspace_scope


class AuditAction(StrEnum):
    """The vocabulary. A closed set, so a typo is an error rather than a row
    nobody will ever query for.

    `doc/12` §Phase 4 names nine. They are the state changes a workspace
    administrator would be asked about in an incident: who got in, who was given
    what, and what entered the Brain.
    """

    LOGIN = "login"
    LOGOUT = "logout"
    ROLE_CHANGED = "role_changed"
    INVITATION_ISSUED = "invitation_issued"
    INVITATION_ACCEPTED = "invitation_accepted"
    ANSWER_WRITTEN = "answer_written"
    DOCUMENT_UPLOADED = "document_uploaded"
    REVIEW_DECISION = "review_decision"
    WORKSPACE_CREATED = "workspace_created"

    WORKSPACE_SWITCHED = "workspace_switched"
    """Somebody moved their session to another entity they hold (ADR 0026).

    Recorded against the workspace being **entered**, so each entity's own log
    shows who arrived. It is not a permission change and grants nothing — but
    when a group holds several companies, "who was looking at this one, and
    when" is the first question an incident asks."""

    DEPARTMENTS_CHANGED = "departments_changed"
    """Which departments the company runs. **Removing one is a scope change**,
    so the row names what went as well as what arrived — a department that stops
    running takes its director off every nav, and the question of why it went is
    one somebody asks later."""

    REPORTING_CHANGED = "reporting_changed"
    """`doc/13` §10's restate rule. Recorded only when a setting that actually
    restates numbers moves — the fiscal year, the reporting week, the report
    timezone. Choosing thousands over units changes how a figure is written and
    nothing else, and logging that as a restatement would bury the three that
    matter in a list of the two that do not."""


async def record(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    action: AuditAction,
    actor_user_id: UUID | None = None,
    target_type: str | None = None,
    target_id: str | None = None,
    reason: str | None = None,
    impersonated_user_id: UUID | None = None,
) -> None:
    """Write one row, on the caller's session and inside their transaction.

    **The GUC is set here.** `audit_log` carries `FORCE ROW LEVEL SECURITY` and
    a `WITH CHECK` on `workspace_id`, so an insert without
    `nexus.workspace_id` set is refused outright — which is the correct
    behaviour and an unhelpful error at three in the morning. Setting it from
    the argument makes the write succeed for exactly the workspace being
    recorded against, and makes it impossible to log an action into somebody
    else's workspace by passing the wrong id: the row and the policy read the
    same value.

    `actor_user_id` is nullable because some actions have no human actor — a
    scheduled sweep, a system-initiated review. It is never NULL merely because
    the caller did not bother.
    """
    await apply_workspace_scope(db, str(workspace_id))
    await db.execute(
        text(
            "INSERT INTO audit_log"
            " (workspace_id, actor_user_id, action, target_type, target_id,"
            "  reason, impersonated_user_id)"
            " VALUES (:ws, :actor, :action, :ttype, :tid, :reason, :imp)"
        ),
        {
            "ws": str(workspace_id),
            "actor": str(actor_user_id) if actor_user_id else None,
            "action": action.value,
            "ttype": target_type,
            "tid": target_id,
            "reason": reason,
            "imp": str(impersonated_user_id) if impersonated_user_id else None,
        },
    )
