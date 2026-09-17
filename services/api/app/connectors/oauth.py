"""The authorisation round trip, and what `state` is actually protecting.

`doc/14` step 9. Turning *"we use HubSpot"* into a refresh token this service
can seal (ADR 0032) and read with (ADR 0031).

## `state` is not a nonce for its own sake

The callback is a **cross-site GET**: the browser arrives from HubSpot, so there
is no CSRF header to check and `require_csrf` exempts safe methods anyway. The
attack `state` prevents is specific and worth naming, because a signed random
string would look like it prevented it and would not:

> An attacker starts an authorisation against **their own** HubSpot, captures the
> `code`, and gets a victim to open the callback with it. Without binding, the
> victim's workspace is now reading the attacker's CRM — and every figure on
> their dashboard is about somebody else's company, individually plausible.

So the state carries **which workspace and which person** began the flow, signed
and time-limited, and the callback refuses unless the session opening it is that
same person in that same workspace. `itsdangerous` gives the signature and the
age; the comparison is ours.

## Read-only, and narrower than HubSpot offers

`crm.objects.deals.read` and nothing else. `SourceEntry.read_only` is `True`
everywhere and A5 makes write a separate, heavier ask — a scope granted "while
we are here" is one nobody decided to grant.

## The refresh token is the only thing kept

HubSpot returns both. The access token expires within the hour, so storing it
widens what a database read is worth and buys nothing (ADR 0032, option C).
"""

from __future__ import annotations

from typing import Final
from urllib.parse import urlencode
from uuid import UUID

import httpx
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from app.config import Settings
from app.connectors.contracts import ProviderMisconfiguredError, ProviderUnavailableError
from app.logging import get_logger

log = get_logger(__name__)

AUTHORIZE_URL: Final = "https://app.hubspot.com/oauth/authorize"
# `noqa: S105` — ruff's hardcoded-password heuristic matches the value, not the
# name, and this URL's path ends in `/token`. It is a public endpoint printed in
# HubSpot's own documentation. Suppressed narrowly rather than by renaming,
# because the rule would flag any accurate name for it.
TOKEN_ENDPOINT: Final = "https://api.hubapi.com/oauth/v1/token"  # noqa: S105

SCOPES: Final = ("crm.objects.deals.read",)
"""Deals, read. Nothing else.

Every extra scope is data we hold and never compute from, and HubSpot's consent
screen shows the customer exactly this list — so a scope added for convenience
is a sentence they read and did not agree to.
"""

STATE_SALT: Final = "connector-oauth-state"
"""Namespaced so a token minted here cannot be replayed anywhere else that signs
with the same secret. A shared salt makes two unrelated signatures
interchangeable."""

STATE_MAX_AGE: Final = 600
"""Ten minutes. Long enough to read a consent screen, short enough that a state
captured from a browser's history is no longer a key to anything."""

TIMEOUT: Final = httpx.Timeout(20.0, connect=5.0)


def _serializer(settings: Settings) -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(settings.require("storage_signing_secret"), salt=STATE_SALT)


def sign_state(*, workspace_id: UUID, user_id: UUID, provider: str, settings: Settings) -> str:
    """Mint the `state` this flow will be checked against."""
    return _serializer(settings).dumps({"w": str(workspace_id), "u": str(user_id), "p": provider})


def verify_state(
    state: str, *, workspace_id: UUID, user_id: UUID, provider: str, settings: Settings
) -> None:
    """Refuse unless this callback belongs to the flow that started it.

    Four things must match, and the last three are the point: a valid signature
    alone proves only that *somebody* began a flow, not that it was this person
    in this workspace for this provider.
    """
    try:
        payload = _serializer(settings).loads(state, max_age=STATE_MAX_AGE)
    except SignatureExpired:
        raise ProviderMisconfiguredError(
            "that authorisation took too long to come back. Start it again."
        ) from None
    except BadSignature:
        # Deliberately the same shape of message as the mismatch below. A
        # distinct one would tell somebody probing whether their forged state
        # got as far as being parsed.
        raise ProviderMisconfiguredError("that authorisation could not be verified.") from None

    if (
        payload.get("w") != str(workspace_id)
        or payload.get("u") != str(user_id)
        or payload.get("p") != provider
    ):
        log.warning(
            "connector.oauth_state_mismatch",
            provider=provider,
            # The ids are not logged. A mismatch is interesting; whose it was is
            # not, and this line would otherwise correlate two workspaces.
        )
        raise ProviderMisconfiguredError("that authorisation could not be verified.")


def authorize_url(*, provider: str, state: str, settings: Settings) -> str:
    """Where to send the customer's browser.

    Raises if the provider is not configured rather than building a URL with an
    empty `client_id` — HubSpot would answer that with its own error page, and
    the customer would be looking at a vendor's failure for our missing setting.
    """
    if provider != "hubspot" or not settings.hubspot_configured:
        raise ProviderMisconfiguredError(
            f"{provider} is not configured on this deployment, so there is nothing to authorise."
        )

    return f"{AUTHORIZE_URL}?" + urlencode(
        {
            "client_id": settings.hubspot_client_id,
            "redirect_uri": settings.hubspot_redirect_uri,
            "scope": " ".join(SCOPES),
            "state": state,
        }
    )


async def exchange_code(
    *, provider: str, code: str, settings: Settings, client: httpx.AsyncClient | None = None
) -> str:
    """Trade the one-time code for a refresh token, and return only that.

    The access token is discarded here rather than returned and dropped by a
    caller: a value that never leaves this function cannot be stored by
    accident, and ADR 0032 says the only thing worth keeping is the refresh
    token.
    """
    if provider != "hubspot" or not settings.hubspot_configured:
        raise ProviderMisconfiguredError(f"{provider} is not configured on this deployment.")

    made = client or httpx.AsyncClient(timeout=TIMEOUT)
    try:
        response = await made.post(
            TOKEN_ENDPOINT,
            data={
                "grant_type": "authorization_code",
                "client_id": settings.hubspot_client_id,
                "client_secret": settings.hubspot_client_secret.get_secret_value(),
                "redirect_uri": settings.hubspot_redirect_uri,
                "code": code,
            },
        )
    except httpx.HTTPError as unreachable:
        raise ProviderUnavailableError(
            f"the provider could not be reached ({type(unreachable).__name__})"
        ) from unreachable
    finally:
        if client is None:
            await made.aclose()

    if response.status_code >= 400:
        # No body in the log and none in the message. A token endpoint's error
        # body echoes the request on some providers, and the request carries the
        # client secret.
        log.warning(
            "connector.oauth_exchange_refused", provider=provider, status=response.status_code
        )
        raise ProviderMisconfiguredError(
            "the provider refused that authorisation. It may have already been "
            "used, or the redirect URI may not match the one registered."
        )

    refresh_token = response.json().get("refresh_token")
    if not refresh_token:
        # A 200 with no refresh token is a configuration that will work exactly
        # once and then stop — the access token expires and nothing can renew
        # it. Better to refuse the connection than to store a credential that
        # dies within the hour.
        raise ProviderMisconfiguredError(
            "the provider returned no refresh token, so this connection could "
            "not be renewed after an hour."
        )
    return str(refresh_token)
