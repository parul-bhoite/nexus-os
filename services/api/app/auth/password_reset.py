"""Password reset.

The same machinery as `email_verification` — hashed at rest, single-use,
expiring — with three differences that come from the blast radius. A stolen
verification token confirms an address. **A stolen reset token is the account.**

- **A shorter life.** One hour, not twenty-four. The window in which a token
  sitting in an inbox, a proxy log or a browser history is redeemable is the
  window this exists to make small.
- **Requesting one supersedes any outstanding token.** Otherwise every reset a
  user has ever requested stays live until it expires, and the oldest forwarded
  email still works.
- **Confirming one revokes every live session.** The ordinary reason to reset a
  password is that somebody else has it. Leaving their session alive makes the
  reset a formality: they keep exactly the access it was performed to remove.

Nothing here tells a caller whether an address exists. That is the *route's*
job — see `app/routes/auth.py` — but it constrains this module too: `request`
returns `None` for an unknown address rather than raising, so the caller has no
exception to accidentally turn into a distinguishable response.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.passwords import hash_password_async
from app.auth.tokens import hash_token, new_token
from app.mail import Email

TOKEN_TTL = timedelta(hours=1)


@dataclass(frozen=True, slots=True)
class IssuedReset:
    token: str
    email: str
    expires_at: datetime


async def request(db: AsyncSession, *, email: str) -> IssuedReset | None:
    """Issue a reset token, or `None` if no such account exists.

    `None`, not an exception. An exception is a control-flow difference the
    route would have to handle, and the whole design of this endpoint is that
    the two cases are indistinguishable from outside — so the fewer places they
    diverge inside, the fewer chances to leak the difference.
    """
    normalised = email.strip().lower()
    user_id = (
        await db.execute(
            text("SELECT id FROM app_user WHERE lower(email) = :e AND disabled_at IS NULL"),
            {"e": normalised},
        )
    ).scalar()

    if user_id is None:
        return None

    token = new_token()
    expires_at = datetime.now(UTC) + TOKEN_TTL

    # Supersede any outstanding token, so a forwarded older email stops working.
    await db.execute(
        text(
            "UPDATE password_reset SET consumed_at = now()"
            " WHERE user_id = :u AND consumed_at IS NULL"
        ),
        {"u": str(user_id)},
    )
    await db.execute(
        text("INSERT INTO password_reset (user_id, token_hash, expires_at) VALUES (:u, :h, :x)"),
        {"u": str(user_id), "h": hash_token(token), "x": expires_at},
    )

    return IssuedReset(token=token, email=normalised, expires_at=expires_at)


async def confirm(db: AsyncSession, *, token: str, new_password: str) -> UUID | None:
    """Burn the token and set the password. Returns the user id, or `None`.

    The update is conditional and returns the row, so two simultaneous clicks
    cannot both succeed — the database decides, not our read-then-write. Same
    shape as `email_verification.consume`, and for the same reason.
    """
    row = (
        await db.execute(
            text(
                "UPDATE password_reset SET consumed_at = now()"
                " WHERE token_hash = :h AND consumed_at IS NULL AND expires_at > now()"
                " RETURNING user_id"
            ),
            {"h": hash_token(token)},
        )
    ).first()

    if row is None:
        return None

    user_id = UUID(str(row.user_id))

    await db.execute(
        text("UPDATE app_user SET password_hash = :p WHERE id = :u"),
        {"p": await hash_password_async(new_password), "u": str(user_id)},
    )

    # Every live session, including the one that asked. Someone resetting a
    # password they still know is mildly inconvenienced; someone resetting one
    # that was stolen gets what they came for.
    await db.execute(
        text(
            "UPDATE user_session SET revoked_at = now() WHERE user_id = :u AND revoked_at IS NULL"
        ),
        {"u": str(user_id)},
    )

    return user_id


def build_email(*, to: str, token: str, base_url: str) -> Email:
    link = f"{base_url.rstrip('/')}/reset-password?token={token}"
    return Email(
        to=to,
        subject="Reset your NEXUS OS password",
        text_body=(
            "Someone asked to reset the password for this NEXUS OS account.\n\n"
            f"{link}\n\n"
            "This link works once and expires in one hour. Using it will sign "
            "you out everywhere.\n\n"
            "If this was not you, you can ignore this email — your password has "
            "not changed, and nobody has been told whether this address has an "
            "account here."
        ),
    )
