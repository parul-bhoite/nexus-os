"""The authorisation round trip, and the attack `state` exists to stop.

`doc/14` step 9. The callback is a cross-site GET — the browser arrives from
HubSpot, so there is no CSRF header and `require_csrf` exempts safe methods
anyway. `state` is the whole of the defence, and a signed random string would
*look* like a defence while providing none:

> An attacker begins an authorisation against **their own** HubSpot, captures
> the `code`, and gets a victim to open the callback with it. Unbound, the
> victim's workspace now reads the attacker's CRM, and every figure on their
> dashboard is about somebody else's company — individually plausible, and
> wrong in a way nobody can see.

So the binding is asserted four ways: a forged state, another workspace's state,
another person's state, and another provider's state. Each is a real path and
each would otherwise succeed.

Hermetic: the lattice and the signing, with no database and no vendor.
"""

from __future__ import annotations

from collections.abc import Iterator
from uuid import UUID, uuid4

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.config import Settings, get_settings
from app.connectors.oauth import STATE_MAX_AGE, sign_state
from app.domain.scopes import Department, Role
from app.domain.session import ScopedSession
from app.main import create_app

CSRF = "a-csrf-token"
WORKSPACE = uuid4()
OWNER = uuid4()


def _settings() -> Settings:
    get_settings.cache_clear()
    return Settings().model_copy(
        update={
            "storage_signing_secret": SecretStr("a-signing-secret"),
            "connector_secret_key": SecretStr(Fernet.generate_key().decode()),
            "hubspot_client_id": "an-id",
            "hubspot_client_secret": SecretStr("a-secret"),
            "hubspot_redirect_uri": "https://app.example.com/connections/hubspot/callback",
        }
    )


SETTINGS = _settings()


@pytest.fixture
def client() -> Iterator[TestClient]:
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: SETTINGS
    with TestClient(app) as made:
        yield made
    app.dependency_overrides.clear()


def as_role(
    client: TestClient,
    role: Role = Role.OWNER,
    *,
    workspace: UUID = WORKSPACE,
    user: UUID = OWNER,
) -> None:
    from app.deps import current_scope

    scope = ScopedSession(
        user_id=user,
        tenant_id=uuid4(),
        workspace_id=workspace,
        role=role,
        departments=frozenset(Department),
    )
    client.app.dependency_overrides[current_scope] = lambda: scope  # type: ignore[attr-defined]
    client.cookies.set("nexus_csrf", CSRF)


def _state(**overrides: object) -> str:
    fields: dict[str, object] = {
        "workspace_id": WORKSPACE,
        "user_id": OWNER,
        "provider": "hubspot",
        "settings": SETTINGS,
    }
    fields.update(overrides)
    return sign_state(**fields)  # type: ignore[arg-type]


def _callback(client: TestClient, state: str, provider: str = "hubspot") -> int:
    return client.get(
        f"/connections/{provider}/callback", params={"code": "a-code", "state": state}
    ).status_code


# ── The binding, four ways ────────────────────────────────────


def test_a_forged_state_is_refused(client: TestClient) -> None:
    as_role(client)

    assert _callback(client, "not-a-signed-state") == 400


def test_another_workspaces_state_is_refused(client: TestClient) -> None:
    """**The attack, in one line.** A valid signature proves somebody began a
    flow, not that it was this workspace."""
    as_role(client)

    assert _callback(client, _state(workspace_id=uuid4())) == 400


def test_another_persons_state_is_refused(client: TestClient) -> None:
    """Two colleagues in one workspace are not interchangeable here: the person
    who consented is the person whose HubSpot account authorised us."""
    as_role(client)

    assert _callback(client, _state(user_id=uuid4())) == 400


def test_a_state_minted_for_another_provider_is_refused(client: TestClient) -> None:
    """Otherwise a state from a Xero flow completes a HubSpot one, and the
    workspace ends up connected to whichever vendor answered first."""
    as_role(client)

    assert _callback(client, _state(provider="xero")) == 400


def test_the_refusals_are_indistinguishable_from_each_other(client: TestClient) -> None:
    """A distinct message per failure tells somebody probing how far their
    forged state got. All four say the same thing."""
    as_role(client)
    messages = {
        client.get("/connections/hubspot/callback", params={"code": "c", "state": state}).json()[
            "detail"
        ]
        for state in ("nonsense", _state(workspace_id=uuid4()), _state(user_id=uuid4()))
    }

    assert len(messages) == 1


def test_the_state_expires(client: TestClient) -> None:
    """Ten minutes: long enough to read a consent screen, short enough that a
    state left in a browser's history is no longer a key to anything."""
    assert STATE_MAX_AGE <= 900


# ── Who may connect ───────────────────────────────────────────


@pytest.mark.parametrize("role", [Role.DEPARTMENT_MANAGER, Role.CONTRIBUTOR])
def test_only_an_owner_or_executive_may_start_an_authorisation(
    client: TestClient, role: Role
) -> None:
    """Connecting grants a read of the whole company's CRM. That is not a
    department-scoped act, whatever department the person runs."""
    as_role(client, role)

    response = client.post("/connections/hubspot/authorize", headers={"X-CSRF-Token": CSRF})

    assert response.status_code == 403
    assert "Owner or Executive" in response.json()["detail"]


def test_the_callback_is_gated_too(client: TestClient) -> None:
    """The gate is on both halves. A contributor who obtained a valid state —
    by starting a flow before a role change, say — must still not complete it."""
    as_role(client, Role.CONTRIBUTOR)

    assert _callback(client, _state()) == 403


def test_starting_an_authorisation_needs_csrf(client: TestClient) -> None:
    """It mints a credential-bearing state, so it is state-changing and carries
    the same protection as every other POST here."""
    as_role(client)

    assert client.post("/connections/hubspot/authorize").status_code == 403


# ── What the authorise URL says ───────────────────────────────


def test_it_sends_the_customer_to_the_vendor_with_a_bound_state(
    client: TestClient,
) -> None:
    as_role(client)

    body = client.post("/connections/hubspot/authorize", headers={"X-CSRF-Token": CSRF}).json()

    assert body["url"].startswith("https://app.hubspot.com/oauth/authorize?")
    assert "state=" in body["url"]
    assert "client_id=an-id" in body["url"]


def test_it_asks_for_read_scope_and_nothing_more(client: TestClient) -> None:
    """Every extra scope is data we hold and never compute from, and HubSpot's
    consent screen shows the customer exactly this list — so one added for
    convenience is a sentence they read and did not agree to."""
    as_role(client)

    url = client.post("/connections/hubspot/authorize", headers={"X-CSRF-Token": CSRF}).json()[
        "url"
    ]

    assert "crm.objects.deals.read" in url
    assert "write" not in url


def test_the_client_secret_never_reaches_the_authorize_url(client: TestClient) -> None:
    """It belongs in the server-to-server exchange. In the URL it would be in
    the customer's address bar, their history and HubSpot's referrer."""
    as_role(client)

    url = client.post("/connections/hubspot/authorize", headers={"X-CSRF-Token": CSRF}).json()[
        "url"
    ]

    assert "a-secret" not in url


def test_a_provider_with_no_adapter_is_refused_before_the_consent_screen(
    client: TestClient,
) -> None:
    """**Refused early, deliberately.** Salesforce publishes an MCP server and
    has no adapter here. Sending somebody to consent first would take a real
    permission for a read nothing performs, and they could not tell."""
    as_role(client)

    response = client.post("/connections/salesforce/authorize", headers={"X-CSRF-Token": CSRF})

    assert response.status_code == 400
    assert "no adapter" in response.json()["detail"]


def test_an_unconfigured_deployment_says_so_rather_than_building_a_broken_url(
    client: TestClient,
) -> None:
    """With no client id, HubSpot answers its own error page and the customer is
    looking at a vendor's failure for our missing setting."""
    as_role(client)
    bare = SETTINGS.model_copy(update={"hubspot_client_id": ""})
    client.app.dependency_overrides[get_settings] = lambda: bare  # type: ignore[attr-defined]

    response = client.post("/connections/hubspot/authorize", headers={"X-CSRF-Token": CSRF})

    assert response.status_code == 400
    assert "not configured" in response.json()["detail"]
