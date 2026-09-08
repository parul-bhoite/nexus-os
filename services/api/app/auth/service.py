"""Registration, login, and session lifecycle.

These queries deliberately run outside `retrieval/`. Authentication happens
*before* a workspace context exists — resolving which workspace the caller is in
is the outcome of this module, not an input to it — so it uses the unscoped
session on the three tables that carry no workspace column (`app_user`,
`user_session`, `tenant`). Everything workspace-scoped goes through
`retrieval.scoped_connection`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.passwords import (
    hash_password_async,
    needs_rehash,
    spend_dummy_verification_async,
    verify_password_async,
)
from app.auth.tokens import hash_token, new_token
from app.config import get_settings
from app.domain.scopes import Department, Role
from app.domain.session import ScopedSession
from app.retrieval.scoped import apply_user_scope


class AuthError(Exception):
    """Authentication failed. Deliberately undifferentiated — see `login`."""


class EmailAlreadyRegisteredError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class IssuedSession:
    token: str
    session_id: UUID
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class Membership:
    workspace_id: UUID
    tenant_id: UUID
    workspace_name: str
    role: Role
    departments: frozenset[Department]


def _blank_to_none(value: str | None) -> str | None:
    """An empty optional field is absent, not present-and-empty.

    The check constraints reject `''`, so a form that posts a skipped field as
    the empty string would 500 on a value the user never entered.
    """
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


# ── Registration ──────────────────────────────────────────────


async def register_user(
    db: AsyncSession,
    *,
    email: str,
    password: str,
    display_name: str | None = None,
    phone: str | None = None,
) -> UUID:
    """Create the account.

    `phone` is stored and nothing more: not verified, not an identifier, and not
    a second way to sign in. Email remains the only unique key, because a phone
    number is reassigned between people and reformatted between countries, and a
    second identity column is a second way for two humans to become one row.
    """
    normalised = email.strip().lower()
    password_hash = await hash_password_async(password)

    existing = await db.execute(
        text("SELECT 1 FROM app_user WHERE lower(email) = :email"), {"email": normalised}
    )
    if existing.first() is not None:
        raise EmailAlreadyRegisteredError(normalised)

    # Finding #10. The SELECT above is a check-then-act, and between the two a
    # concurrent registration of the same address wins the unique index — so the
    # INSERT raised `IntegrityError`, which reached the client as a **500**.
    #
    # That is not merely an ugly error. `POST /auth/register` answers identically
    # for a new and a known address *precisely* so it cannot be used to discover
    # who has an account; a 500 on exactly the addresses that already exist is
    # the distinguishable reply that design exists to prevent, handed out under
    # load. The race is narrow and the oracle is not — an attacker can widen it
    # by registering the same address twice concurrently on purpose.
    #
    # Caught and converted to the same refusal the sequential path raises, so
    # both orderings produce the one response the route knows how to answer.
    try:
        row = await db.execute(
            text(
                "INSERT INTO app_user (email, password_hash, display_name, phone)"
                " VALUES (:email, :hash, :name, :phone) RETURNING id"
            ),
            {
                "email": normalised,
                "hash": password_hash,
                "name": _blank_to_none(display_name),
                "phone": _blank_to_none(phone),
            },
        )
    except IntegrityError as exc:
        raise EmailAlreadyRegisteredError(normalised) from exc
    return UUID(str(row.scalar_one()))


# ── Login ─────────────────────────────────────────────────────


async def authenticate(db: AsyncSession, *, email: str, password: str) -> UUID:
    """Return the user id, or raise `AuthError`.

    The error is deliberately identical for "no such account", "wrong password"
    and "account disabled". Distinguishing them turns login into a user
    enumeration oracle, and the timing is equalised for the same reason.
    """
    normalised = email.strip().lower()
    row = (
        await db.execute(
            text("SELECT id, password_hash, disabled_at FROM app_user WHERE lower(email) = :email"),
            {"email": normalised},
        )
    ).first()

    if row is None or row.password_hash is None:
        # Spend comparable time so absence is not measurably faster.
        await spend_dummy_verification_async()
        raise AuthError("invalid credentials")

    if not await verify_password_async(row.password_hash, password):
        raise AuthError("invalid credentials")

    if row.disabled_at is not None:
        raise AuthError("invalid credentials")

    if needs_rehash(row.password_hash):
        await db.execute(
            text("UPDATE app_user SET password_hash = :hash WHERE id = :id"),
            {"hash": await hash_password_async(password), "id": str(row.id)},
        )

    return UUID(str(row.id))


# ── Sessions ──────────────────────────────────────────────────


async def issue_session(
    db: AsyncSession,
    *,
    user_id: UUID,
    ttl_seconds: int,
    active_workspace_id: UUID | None = None,
    user_agent: str | None = None,
) -> IssuedSession:
    """Mint a new session. Always a *new* row — never reuse an existing id.

    Session fixation is prevented by construction: because login always issues
    a fresh token, a token an attacker planted before authentication is never
    the token that ends up authenticated.
    """
    token = new_token()
    expires_at = datetime.now(UTC) + timedelta(seconds=ttl_seconds)

    row = await db.execute(
        text(
            "INSERT INTO user_session"
            " (user_id, token_hash, expires_at, active_workspace_id, user_agent)"
            " VALUES (:uid, :hash, :exp, :ws, :ua) RETURNING id"
        ),
        {
            "uid": str(user_id),
            "hash": hash_token(token),
            "exp": expires_at,
            "ws": str(active_workspace_id) if active_workspace_id else None,
            "ua": (user_agent or "")[:500] or None,
        },
    )
    return IssuedSession(token=token, session_id=UUID(str(row.scalar_one())), expires_at=expires_at)


@dataclass(frozen=True, slots=True)
class ResolvedSession:
    session_id: UUID
    user_id: UUID
    active_workspace_id: UUID | None


async def resolve_session(
    db: AsyncSession, *, token: str, ttl_seconds: int | None = None
) -> ResolvedSession | None:
    """Look a session up by token hash, and extend it if it is running out.

    The lookup is by hash, so the plaintext token is never compared in SQL and
    never stored.

    **Rolling refresh** (`doc/11` §5.2). Twelve hours alone is the wrong shape
    for both parties: someone working a long day is signed out mid-task, and a
    fixed window is one an attacker can simply wait out.

    Three things make this safe and affordable, and each is in the statement
    below rather than in a comment asking a caller to be careful:

    - **It is one statement.** An `UPDATE ... RETURNING` that carries its own
      `revoked_at IS NULL AND expires_at > now()`, so resolving and refreshing
      cannot disagree. A read followed by a write could extend a session revoked
      between the two — which is how a logout, a password reset or an
      administrator ending a session gets quietly undone.
    - **It only writes when there is something to gain.** The extension applies
      once more than half the window is spent. Refreshing on every request would
      turn every authenticated read into a write, which on a serverless Postgres
      billed per statement is a cost bug wearing a security feature's clothes.
    - **A dead session is never revived.** The `WHERE` is the same predicate the
      old read used, so an expired or revoked row matches nothing and is neither
      returned nor extended.
    """
    window = ttl_seconds if ttl_seconds is not None else get_settings().session_max_age_seconds

    row = (
        await db.execute(
            text(
                "UPDATE user_session"
                "   SET expires_at = CASE"
                "         WHEN expires_at < now() + make_interval(secs => :half)"
                "           THEN now() + make_interval(secs => :window)"
                "         ELSE expires_at"
                "       END"
                " WHERE token_hash = :hash"
                "   AND revoked_at IS NULL"
                "   AND expires_at > now()"
                " RETURNING id, user_id, active_workspace_id"
            ),
            {"hash": hash_token(token), "half": window / 2, "window": window},
        )
    ).first()

    if row is None:
        return None

    return ResolvedSession(
        session_id=UUID(str(row.id)),
        user_id=UUID(str(row.user_id)),
        active_workspace_id=(
            UUID(str(row.active_workspace_id)) if row.active_workspace_id else None
        ),
    )


async def revoke_session(db: AsyncSession, *, session_id: UUID) -> None:
    await db.execute(
        text("UPDATE user_session SET revoked_at = now() WHERE id = :id"),
        {"id": str(session_id)},
    )


async def revoke_all_sessions_for_user(db: AsyncSession, *, user_id: UUID) -> None:
    """Used on password change and on offboarding (doc 06 §4.15)."""
    await db.execute(
        text(
            "UPDATE user_session SET revoked_at = now() WHERE user_id = :uid AND revoked_at IS NULL"
        ),
        {"uid": str(user_id)},
    )


# ── Membership resolution ─────────────────────────────────────


async def memberships_for_user(db: AsyncSession, *, user_id: UUID) -> list[Membership]:
    """Every workspace this user belongs to.

    Relies on the `membership_own_rows` policy from migration 0003, so the GUC
    `nexus.user_id` must be set on this connection. It discloses only the
    caller's own memberships — never another person's.
    """
    await apply_user_scope(db, user_id)
    rows = (
        await db.execute(
            text(
                "SELECT m.workspace_id, m.role, m.departments,"
                "       w.tenant_id, w.name"
                "  FROM membership m"
                "  JOIN workspace w ON w.id = m.workspace_id"
                " WHERE m.user_id = :uid AND m.revoked_at IS NULL"
                " ORDER BY w.name"
            ),
            {"uid": str(user_id)},
        )
    ).all()

    return [
        Membership(
            workspace_id=UUID(str(r.workspace_id)),
            tenant_id=UUID(str(r.tenant_id)),
            workspace_name=r.name,
            role=Role(r.role),
            departments=frozenset(Department(d) for d in (r.departments or [])),
        )
        for r in rows
    ]


async def set_active_workspace(db: AsyncSession, *, session_id: UUID, workspace_id: UUID) -> None:
    await db.execute(
        text("UPDATE user_session SET active_workspace_id = :ws WHERE id = :sid"),
        {"ws": str(workspace_id), "sid": str(session_id)},
    )


def build_scope(*, user_id: UUID, membership: Membership) -> ScopedSession:
    """Assemble the caller's authority from server-side facts only.

    Every field comes from the session row and the membership row. Nothing here
    is read from a header, a body or a query string — doc 06 §2.1 requires the
    active workspace to be resolved server-side per request, because a
    client-supplied value plus claim-based RLS is a cross-tenant read waiting to
    happen.
    """
    return ScopedSession(
        user_id=user_id,
        tenant_id=membership.tenant_id,
        workspace_id=membership.workspace_id,
        role=membership.role,
        departments=membership.departments,
        named_l4_item_ids=frozenset(),
    )
