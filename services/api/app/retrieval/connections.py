"""Reading and writing a workspace's connections, scoped.

I2/I3: the only path to `workspace_connection`, taking a `ScopedSession` and
never a `user_id`. The RLS policy on the table is the floor; the explicit
`workspace_id = :w` doubles it for the reason `retrieval/crawl.py` gives — it is
what makes the index usable, and it is the same value the policy compares, so
the two cannot disagree.

## The sealed credential never leaves as plaintext

`credential_for` returns a `Sealed`, not a token. Opening it is
`connectors.credentials.unseal`, which needs the key, and keeping the two apart
means a caller that only wanted to know *whether* a connection exists cannot
accidentally hold the thing that reads a customer's CRM.
"""

from __future__ import annotations

from typing import Final

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.connectors.credentials import Sealed
from app.domain.session import ScopedSession

_UPSERT: Final = sa.text(
    """
    INSERT INTO workspace_connection
           (workspace_id, provider, state, declared_by, connected_at,
            credentials, credential_key_id, last_error)
    VALUES (:w, :provider, 'connected', :user, now(), :ciphertext, :key_id, NULL)
    ON CONFLICT (workspace_id, provider) DO UPDATE
       SET state             = 'connected',
           connected_at      = now(),
           credentials       = EXCLUDED.credentials,
           credential_key_id = EXCLUDED.credential_key_id,
           -- Cleared on a successful reconnect. A stale error beside a working
           -- connection is worse than none: it tells a founder to fix something
           -- they already fixed.
           last_error        = NULL
    """
)
"""Connect, or re-connect.

`ON CONFLICT` targets `uq_workspace_connection_provider`, which migration 0026
already declared on `(workspace_id, provider)`.

**An upsert rather than an insert**, because re-authorising is the ordinary way
out of a revoked token and a customer doing it should not hit a uniqueness
error. `declared_by` is deliberately not updated: it records who first said this
company runs HubSpot, which is a different fact from who most recently
authorised it.
"""

_CREDENTIAL: Final = sa.text(
    """
    SELECT credentials, credential_key_id
      FROM workspace_connection
     WHERE workspace_id = :w AND provider = :provider AND state = 'connected'
    """
)
"""`state = 'connected'` is in the WHERE, not checked afterwards.

A revoked row keeps its ciphertext — revocation is a state change, not a
deletion, because a workspace that reconnects should not lose the record that it
was connected before. Reading one back and using it would be reading a customer's
CRM after they told us to stop.
"""


async def connect(db: AsyncSession, scope: ScopedSession, *, provider: str, sealed: Sealed) -> None:
    """Record a provider as connected, with its sealed credential.

    Does not commit — the route owns the transaction, the same way `narrate` and
    `ledger.record` leave it to their caller.
    """
    await db.execute(
        _UPSERT,
        {
            "w": str(scope.workspace_id),
            "provider": provider,
            "user": str(scope.user_id),
            "ciphertext": sealed.ciphertext,
            "key_id": sealed.key_id,
        },
    )


async def credential_for(db: AsyncSession, scope: ScopedSession, *, provider: str) -> Sealed | None:
    """The sealed credential for a connected provider, or `None`.

    `None` means *no usable connection*, which covers never-connected and
    revoked alike — the caller's behaviour is identical for both, and a
    distinction nothing acts on is a distinction that grows a branch nobody
    tests.
    """
    row = (
        await db.execute(_CREDENTIAL, {"w": str(scope.workspace_id), "provider": provider})
    ).one_or_none()

    if row is None or row.credentials is None:
        return None
    return Sealed(ciphertext=row.credentials, key_id=row.credential_key_id)


async def revoke(db: AsyncSession, scope: ScopedSession, *, provider: str) -> None:
    """Stop reading a provider, and forget how.

    **The ciphertext is cleared, not merely the state.** A row that kept its
    credential after revocation would be a token we hold and have been told not
    to use, sitting in a table anybody with a backup can read. The CHECK pairs
    the two columns, so both go together.
    """
    await db.execute(
        sa.text(
            "UPDATE workspace_connection"
            "   SET state = 'revoked', credentials = NULL, credential_key_id = NULL"
            " WHERE workspace_id = :w AND provider = :provider"
        ),
        {"w": str(scope.workspace_id), "provider": provider},
    )


async def connected_providers(db: AsyncSession, scope: ScopedSession) -> frozenset[str]:
    """Which providers this workspace can currently be read from."""
    rows = await db.execute(
        sa.text(
            "SELECT provider FROM workspace_connection"
            " WHERE workspace_id = :w AND state = 'connected'"
        ),
        {"w": str(scope.workspace_id)},
    )
    return frozenset(str(row.provider) for row in rows)


__all__ = ["connect", "connected_providers", "credential_for", "revoke"]
