"""Connecting a provider: start the authorisation, and take the callback.

`doc/14` step 9. Two routes, and they are asymmetric on purpose.

## Why `authorize` is a POST and `callback` is a GET

`authorize` mints a signed `state` bound to the caller and is therefore
CSRF-protected like every other state-changing route here. `callback` is a
**browser redirect from HubSpot** — a cross-site top-level GET, with no header
anybody can attach — so it cannot carry a CSRF token and `require_csrf` exempts
it by method anyway.

That is exactly why `state` has to do real work rather than be a random string.
`connectors/oauth.verify_state` refuses unless the session opening the callback
is the same person, in the same workspace, for the same provider that began the
flow. Without that, an attacker authorises **their own** HubSpot, captures the
code, and gets a victim to open the callback — after which the victim's
dashboard reports on somebody else's company, every figure individually
plausible.

## Who may connect

An Owner or an Executive. Connecting grants a read of the whole company's CRM,
which is not a department-scoped act, and `doc/05` §9 puts tool connection with
the people who answer for the company rather than with whoever happens to run
Sales.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from app.auth.csrf import require_csrf
from app.config import Settings, get_settings
from app.connectors.contracts import ConnectorError, ProviderMisconfiguredError
from app.connectors.credentials import CredentialSealError, seal
from app.connectors.oauth import authorize_url, exchange_code, sign_state, verify_state
from app.connectors.registry import wiring_for
from app.deps import CurrentScope
from app.logging import get_logger
from app.retrieval.connections import connect, connected_providers, revoke
from app.retrieval.scoped import scoped_connection

router = APIRouter(prefix="/connections", tags=["connections"])
log = get_logger(__name__)

CurrentSettings = Annotated[Settings, Depends(get_settings)]


class AuthorizeOut(BaseModel):
    url: str
    """Where to send the browser. Returned rather than redirected from here: the
    caller is `fetch`ing this from a page, and a 307 to a third party would be
    followed by the fetch instead of by the person."""


class ConnectionOut(BaseModel):
    provider: str
    state: str
    message: str
    """Server-authored, never empty — the rule `unlock` already follows."""


class ConnectedOut(BaseModel):
    providers: list[str]


def _may_connect(scope: CurrentScope) -> None:
    """Owner or Executive only.

    A 403 with a sentence rather than a 404: unlike a department a caller cannot
    reach, the *existence* of connections is not a disclosure — every member can
    see that the company has a CRM. What they may not do is grant a read of it.
    """
    if not scope.can_see_executive_surface:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Connecting a tool grants a read of the whole company's data, so it "
            "is an Owner or Executive decision.",
        )


def _refuse(error: ConnectorError) -> HTTPException:
    """A connector's own sentence, at the right status.

    `ProviderMisconfiguredError` is a 400: something about this deployment or
    this request will not work and retrying will not fix it. Anything else is a
    502 — the provider, not us.
    """
    if isinstance(error, ProviderMisconfiguredError):
        return HTTPException(status.HTTP_400_BAD_REQUEST, str(error))
    return HTTPException(status.HTTP_502_BAD_GATEWAY, str(error))


@router.get("", response_model=ConnectedOut)
async def list_connections(scope: CurrentScope) -> ConnectedOut:
    """Which providers this workspace can currently be read from."""
    async with scoped_connection(scope) as db:
        return ConnectedOut(providers=sorted(await connected_providers(db, scope)))


@router.post(
    "/{provider}/authorize",
    response_model=AuthorizeOut,
    dependencies=[Depends(require_csrf)],
)
async def start_authorization(
    provider: str, scope: CurrentScope, settings: CurrentSettings
) -> AuthorizeOut:
    """Begin an authorisation, and mint the state it will be checked against."""
    _may_connect(scope)

    try:
        # Refuse a provider with no adapter *before* sending anybody to a
        # consent screen. Authorising us to read a system nothing reads is a
        # permission granted for nothing, and the customer cannot tell.
        wiring_for(provider)
        state = sign_state(
            workspace_id=scope.workspace_id,
            user_id=scope.user_id,
            provider=provider,
            settings=settings,
        )
        return AuthorizeOut(url=authorize_url(provider=provider, state=state, settings=settings))
    except ConnectorError as refused:
        raise _refuse(refused) from refused


@router.get("/{provider}/callback", response_model=ConnectionOut)
async def finish_authorization(
    provider: str,
    scope: CurrentScope,
    settings: CurrentSettings,
    code: Annotated[str, Query()],
    state: Annotated[str, Query()],
) -> ConnectionOut:
    """Take HubSpot's redirect, exchange the code, and store the sealed token."""
    _may_connect(scope)

    try:
        verify_state(
            state,
            workspace_id=scope.workspace_id,
            user_id=scope.user_id,
            provider=provider,
            settings=settings,
        )
        refresh_token = await exchange_code(provider=provider, code=code, settings=settings)
        sealed = seal(refresh_token, settings=settings)
    except ConnectorError as refused:
        raise _refuse(refused) from refused
    except CredentialSealError as unsealable:
        # The deployment cannot store what the customer just granted. A 500
        # rather than a 400: nothing about their request was wrong, and telling
        # them to try again would send them round a loop that cannot close.
        log.error("connector.seal_failed", provider=provider)
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "That authorisation succeeded and could not be stored. Nothing was "
            "connected, and this is ours to fix rather than yours to retry.",
        ) from unsealable

    async with scoped_connection(scope) as db:
        await connect(db, scope, provider=provider, sealed=sealed)
        await db.commit()

    log.info("connector.connected", provider=provider)
    return ConnectionOut(
        provider=provider,
        state="connected",
        message=f"{provider} is connected. Nothing reads it until a capability needs it.",
    )


@router.post(
    "/{provider}/revoke", response_model=ConnectionOut, dependencies=[Depends(require_csrf)]
)
async def revoke_connection(provider: str, scope: CurrentScope) -> ConnectionOut:
    """Stop reading a provider, and discard the credential.

    Idempotent, and deliberately does not 404 on a provider that was never
    connected: the caller's intent is *"do not read this"*, and that is already
    true. A refusal would make disconnecting feel riskier than connecting.
    """
    _may_connect(scope)

    async with scoped_connection(scope) as db:
        await revoke(db, scope, provider=provider)
        await db.commit()

    log.info("connector.revoked", provider=provider)
    return ConnectionOut(
        provider=provider,
        state="revoked",
        message=(
            f"{provider} is disconnected and the credential is deleted. "
            "Reconnecting asks for your permission again."
        ),
    )
