"""One person, one company.

`doc/11` §3.2 reversed the M:N assumption. A NEXUS account belongs to exactly
one company: a user with a live membership cannot create a second workspace, and
cannot accept an invitation into another one.

**The `membership` table stays many-to-many.** The rule is enforced here rather
than by a unique index, for two reasons:

- doc 06 §2.1's agency case — one operator, several client workspaces — is
  explicitly deferred rather than deleted, and a unique index would have to be
  migrated away again to bring it back.
- The rule is about *live* memberships. Someone who left a company must be able
  to join another, and a `UNIQUE (user_id)` cannot express "unless revoked"
  without becoming a partial index that then has to agree with application code
  anyway.

It lives in `app/domain/` and not in the two callers because a rule enforced at
each call site is a convention: the third caller forgets. Here there is one
place to attack and one place to audit — the same argument
`create_workspace_for_claim` makes for itself.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.retrieval.scoped import apply_user_scope


class UserAlreadyInAWorkspaceError(Exception):
    """**Retained and no longer raised** (ADR 0026).

    One person belonged to one company (Q9/Q17) until multi-entity was built at
    MVP. Three routes still catch this, and the class survives so that a reader
    tracing why they do finds this note rather than an import error — and so
    that if a *different* one-workspace rule is ever wanted, it is argued for on
    its own terms rather than by reviving a guard whose reason was reversed.

    The message is kept for the same reason: it is what the product used to say,
    and it reads as a decision rather than a conflict.
    """

    def __init__(
        self,
        message: str = (
            "This account is already part of a company on NEXUS OS. "
            "A NEXUS account belongs to one company — ask an administrator "
            "there to change your role, or use a different email address to "
            "set up a separate company."
        ),
    ) -> None:
        super().__init__(message)


async def live_membership_count(
    db: AsyncSession, *, user_id: UUID, other_than: UUID | None = None
) -> int:
    """How many workspaces this user currently belongs to.

    `other_than` excludes one workspace from the count. It existed so that
    re-accepting an invitation to the workspace you are *already* in was
    idempotent rather than a refusal. The guard that needed it is gone (ADR
    0026) and the parameter stays, because *"how many other entities does this
    person hold?"* is the question the group view asks — and it is now a real
    question rather than the setup for a refusal.

    Reads through the `membership_own_rows` policy from migration 0003, so
    `nexus.user_id` is set first — the same contract `memberships_for_user`
    documents. Without it the policy matches nothing and this would answer `0`
    for everybody, which fails **open**: every caller would be waved through.

    `revoked_at IS NULL` is the whole meaning of "live". See the class docstring.
    """
    await apply_user_scope(db, user_id)
    count = (
        await db.execute(
            text(
                "SELECT count(*) FROM membership"
                " WHERE user_id = :uid AND revoked_at IS NULL"
                "   AND (:skip = '' OR workspace_id <> CAST(:skip AS uuid))"
            ),
            {"uid": str(user_id), "skip": str(other_than) if other_than else ""},
        )
    ).scalar_one()
    return int(count)

# `assert_no_live_membership` was here, and ADR 0026 removed it. It refused a
# second `membership` row for a user, which is what made "one person, one
# company" true — and multi-entity is that decision reversed.
#
# **The schema never needed changing.** `membership` was left many-to-many
# deliberately (`doc/11` §3.2: *"keep the schema, constrain the product"*), so
# lifting the constraint is a deletion rather than a migration. That foresight
# is the whole reason this step was six days and not thirty.
#
# What replaces the guard is a test rather than nothing:
# `test_reachable_workspaces_are_exactly_the_callers_memberships`. A rule that
# is removed without its replacement asserted is a rule nobody notices the
# absence of.
