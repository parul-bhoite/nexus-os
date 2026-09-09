"""Issuing and accepting invitations.

The rule this exists to make structural is doc 06 §2.2: *"Every subsequent
user's role is set by the inviter, never self-declared at acceptance."*

Look at `accept` and note what it does **not** take. There is no `role`
parameter and no `departments` parameter, so there is no version of this
function that a caller could talk into granting something the inviter did not
set. The role is read from the row the inviter wrote and copied into the
membership. That is the difference between a rule and a convention.

Tokens are hashed at rest and single-use, for the same reason session and
verification tokens are: a leaked database must not yield working invitation
links, and an accepted link must not seat a second person.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any
from uuid import UUID

from sqlalchemy import CursorResult, RowMapping, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.tokens import hash_token, new_token
from app.auth.workspaces import require_verified_domain
from app.domain import audit
from app.domain.scopes import Department, Role
from app.logging import get_logger
from app.retrieval.scoped import apply_invitation_token_scope, apply_workspace_scope

log = get_logger(__name__)

TOKEN_TTL = timedelta(days=7)
"""Long enough to survive a weekend and a forwarded email; short enough that a
link found in an old inbox a year later is inert."""


@dataclass(frozen=True, slots=True)
class Invitation:
    id: UUID
    workspace_id: UUID
    email: str
    role: Role
    departments: frozenset[Department]
    invited_by_user_id: UUID | None
    created_at: datetime
    expires_at: datetime
    accepted_at: datetime | None
    revoked_at: datetime | None

    @property
    def state(self) -> str:
        """One word for the UI. Order matters — a revoked invitation that has
        also expired is revoked, because that is the fact someone acted on."""
        if self.accepted_at is not None:
            return "accepted"
        if self.revoked_at is not None:
            return "revoked"
        if self.expires_at <= datetime.now(UTC):
            return "expired"
        return "pending"


@dataclass(frozen=True, slots=True)
class IssuedInvitation:
    invitation: Invitation
    token: str
    """Returned once, to the inviter, and never stored in plaintext."""


class AcceptOutcome(StrEnum):
    ACCEPTED = "accepted"
    ALREADY_A_MEMBER = "already_a_member"
    UNUSABLE = "unusable"
    """Expired, revoked, already accepted, or never existed. Deliberately one
    value: telling them apart tells a stranger which tokens were once real."""
    WRONG_ACCOUNT = "wrong_account"


@dataclass(frozen=True, slots=True)
class Accepted:
    outcome: AcceptOutcome
    workspace_id: UUID | None = None
    workspace_name: str | None = None
    role: Role | None = None


def _row_to_invitation(row: RowMapping) -> Invitation:
    invited_by = row["invited_by_user_id"]
    return Invitation(
        id=UUID(str(row["id"])),
        workspace_id=UUID(str(row["workspace_id"])),
        email=str(row["email"]),
        role=Role(row["role"]),
        departments=frozenset(Department(d) for d in (row["departments"] or [])),
        invited_by_user_id=UUID(str(invited_by)) if invited_by else None,
        created_at=row["created_at"],
        expires_at=row["expires_at"],
        accepted_at=row["accepted_at"],
        revoked_at=row["revoked_at"],
    )


# ── Issuing (scoped: the inviter is in the workspace) ─────────


async def issue(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    invited_by_user_id: UUID,
    email: str,
    role: Role,
    departments: frozenset[Department],
    ttl: timedelta = TOKEN_TTL,
) -> IssuedInvitation:
    """Create an invitation. `role` and `departments` are the inviter's decision.

    Runs on a session already scoped to the workspace, so the isolation policy's
    WITH CHECK is what stops a row being aimed at another workspace — not this
    function's care with its parameters.

    Any outstanding invitation to the same address is revoked first. Two live
    links for one person is two different roles they might end up with,
    depending on which email they happen to open.
    """
    # D19. Creation no longer waits for verification, but **inviting does** —
    # an invitation adds somebody to a company, and the only evidence that this
    # is your company is the domain. Without it anyone could register `acme.om`,
    # invite `finance@acme.om`, and receive whatever that person brought along.
    await require_verified_domain(db, workspace_id=workspace_id, action="inviting people")

    token = new_token()
    normalised = email.strip().lower()

    await db.execute(
        text(
            "UPDATE invitation SET revoked_at = now()"
            " WHERE workspace_id = :ws AND lower(email) = :e"
            "   AND accepted_at IS NULL AND revoked_at IS NULL"
        ),
        {"ws": str(workspace_id), "e": normalised},
    )

    row = (
        (
            await db.execute(
                text(
                    "INSERT INTO invitation"
                    " (workspace_id, email, role, departments, invited_by_user_id,"
                    "  token_hash, expires_at)"
                    " VALUES (:ws, :e, :r, CAST(:d AS text[]), :by, :h, :x)"
                    " RETURNING id, workspace_id, email, role, departments,"
                    "           invited_by_user_id, created_at, expires_at,"
                    "           accepted_at, revoked_at"
                ),
                {
                    "ws": str(workspace_id),
                    "e": normalised,
                    "r": role.value,
                    "d": sorted(d.value for d in departments),
                    "by": str(invited_by_user_id),
                    "h": hash_token(token),
                    "x": datetime.now(UTC) + ttl,
                },
            )
        )
        .mappings()
        .one()
    )

    log.info("invitation.issued", role=role.value, departments=len(departments))
    await audit.record(
        db,
        workspace_id=workspace_id,
        action=audit.AuditAction.INVITATION_ISSUED,
        actor_user_id=invited_by_user_id,
        target_type="invitation",
        target_id=str(row["id"]),
        # The role, because that is the part an administrator is asked about
        # later. Not the address: the log is read by people who can already see
        # the member list, but a trail is a place data outlives its purpose.
        reason=f"role {role.value}",
    )

    return IssuedInvitation(invitation=_row_to_invitation(row), token=token)


async def list_for_workspace(db: AsyncSession) -> list[Invitation]:
    """Every invitation in the caller's workspace.

    Takes no `workspace_id`: the session it runs on is already scoped, and the
    isolation policy is what limits the rows. A parameter here would be a second
    source of truth for the same fact, and the weaker one.
    """
    rows = (
        (
            await db.execute(
                text(
                    "SELECT id, workspace_id, email, role, departments,"
                    "       invited_by_user_id, created_at, expires_at,"
                    "       accepted_at, revoked_at"
                    "  FROM invitation ORDER BY created_at DESC"
                )
            )
        )
        .mappings()
        .all()
    )
    return [_row_to_invitation(r) for r in rows]


async def revoke(db: AsyncSession, *, invitation_id: UUID) -> bool:
    """Withdraw an unaccepted invitation. Returns whether anything changed.

    An accepted invitation cannot be revoked — the person is a member, and
    removing them is offboarding (doc 06 §4.15), a different act with different
    fan-out. Silently doing half of it here would be worse than refusing.
    """
    result: CursorResult[Any] = await db.execute(  # type: ignore[assignment]
        text(
            "UPDATE invitation SET revoked_at = now()"
            " WHERE id = :id AND accepted_at IS NULL AND revoked_at IS NULL"
        ),
        {"id": str(invitation_id)},
    )
    return bool(result.rowcount)


# ── Accepting (unscoped: the accepter has no workspace yet) ───


async def accept(db: AsyncSession, *, token: str, user_id: UUID) -> Accepted:
    """Turn an invitation into a membership, on an **unscoped** session.

    Unscoped because the accepter is by definition not yet in the workspace, so
    no `ScopedSession` can honestly be built for them — the same position
    `create_workspace_for_claim` is in. Visibility of the one row comes from the
    token-hash policy in migration 0009; every write after that runs with the
    workspace GUC set from the row itself.

    Note the signature once more: `token` and `user_id`. Nothing about the role.
    """
    await apply_invitation_token_scope(db, hash_token(token))

    row = (
        (
            await db.execute(
                text(
                    "SELECT id, workspace_id, email, role, departments,"
                    "       invited_by_user_id, created_at, expires_at,"
                    "       accepted_at, revoked_at"
                    "  FROM invitation WHERE token_hash = :h"
                ),
                {"h": hash_token(token)},
            )
        )
        .mappings()
        .first()
    )

    if row is None:
        return Accepted(outcome=AcceptOutcome.UNUSABLE)

    invitation = _row_to_invitation(row)
    if invitation.state != "pending":
        return Accepted(outcome=AcceptOutcome.UNUSABLE)

    # The invitation names an address. Accepting it while signed in as somebody
    # else would seat the wrong person in a role chosen for the invited one —
    # and a forwarded link is the ordinary way that happens, not an attack.
    #
    # Known gap, recorded rather than hidden: this proves the account *claims*
    # the address, not that the address was ever confirmed. Nothing in the
    # product sends a verification email yet (see `RegisterForm`), so requiring
    # `email_verified_at` here would make every invitation unusable. When
    # delivery lands, this predicate is where the check belongs.
    email = (
        await db.execute(
            text("SELECT lower(email) FROM app_user WHERE id = :u"), {"u": str(user_id)}
        )
    ).scalar()

    if email is None or email != invitation.email.lower():
        return Accepted(outcome=AcceptOutcome.WRONG_ACCOUNT)

    # `doc/11` §3.2. Checked after the address matches, not before: telling
    # somebody holding a forwarded link that the *invited* account already
    # belongs to a company would answer a question they were never entitled to
    # ask. By this line the caller has proved the invitation names them.

    await apply_workspace_scope(db, str(invitation.workspace_id))

    result: CursorResult[Any] = await db.execute(  # type: ignore[assignment]
        text(
            "INSERT INTO membership (workspace_id, user_id, role, departments)"
            " VALUES (:ws, :u, :r, CAST(:d AS text[]))"
            " ON CONFLICT ON CONSTRAINT uq_membership_workspace_user DO NOTHING"
        ),
        {
            "ws": str(invitation.workspace_id),
            "u": str(user_id),
            # Copied from the row the inviter wrote. Never supplied here.
            "r": invitation.role.value,
            "d": sorted(d.value for d in invitation.departments),
        },
    )

    already_member = not result.rowcount

    if not already_member:
        await audit.record(
            db,
            workspace_id=invitation.workspace_id,
            action=audit.AuditAction.INVITATION_ACCEPTED,
            actor_user_id=user_id,
            target_type="invitation",
            target_id=str(invitation.id),
            reason=f"role {invitation.role.value}",
        )

    # Burn the token either way. A link that has been through this once must not
    # work again, whether or not it changed anything.
    await db.execute(
        text("UPDATE invitation SET accepted_at = now() WHERE id = :id"),
        {"id": str(invitation.id)},
    )

    name = (
        await db.execute(
            text("SELECT name FROM workspace WHERE id = :ws"),
            {"ws": str(invitation.workspace_id)},
        )
    ).scalar()

    if already_member:
        # An existing member keeps the role they already hold. Changing it from
        # a link is a role change (doc 06 §4.15), which is immediate for every
        # live session and is not something an invitation should do silently.
        log.info("invitation.accepted.already_member")
        return Accepted(
            outcome=AcceptOutcome.ALREADY_A_MEMBER,
            workspace_id=invitation.workspace_id,
            workspace_name=name,
        )

    log.info("invitation.accepted", role=invitation.role.value)
    return Accepted(
        outcome=AcceptOutcome.ACCEPTED,
        workspace_id=invitation.workspace_id,
        workspace_name=name,
        role=invitation.role,
    )
