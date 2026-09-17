"""Sealing a provider credential — ADR 0032, D27 answered with option A.

A provider token is read-access to a customer's entire pipeline. The failures
worth guarding are the ones that leave a working-looking system:

- **A plaintext fallback.** A connector that stored an unencrypted token when no
  key was configured would be indistinguishable from one that encrypted it,
  until the day somebody read the table.
- **A secret in a message.** `str(error)` reaches logs and, summarised, a
  screen. A malformed key is very often a real key with a character missing.
- **An empty credential.** The empty string encrypts and decrypts perfectly
  well, so a connection would store a credential-shaped value, pass every check,
  and fail at the provider.
- **Rotation with nothing to rotate against.** Without a key id, *"which rows
  still hold the old key?"* can only be answered by decrypting every row with
  every historical key.

Hermetic. Fernet is in-process and needs no database; the column that holds the
output is asserted in `test_connection_credentials_db.py`.
"""

from __future__ import annotations

import pytest
from cryptography.fernet import Fernet
from pydantic import SecretStr, ValidationError

from app.config import Env, Settings, get_settings
from app.connectors.credentials import (
    CredentialSealError,
    Sealed,
    key_id_for,
    seal,
    unseal,
)

TOKEN = "rt-0aF3-a-real-looking-refresh-token"


def _settings(key: str | None = None) -> Settings:
    get_settings.cache_clear()
    made = Settings()
    return made.model_copy(
        update={
            "connector_secret_key": SecretStr(
                key if key is not None else Fernet.generate_key().decode()
            )
        }
    )


def _a_valid_production_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Everything `NEXUS_ENV=production` insists on, so a test can vary one thing.

    There are four guards, not one, and each was found by tripping over it: the
    secrets, a real mailer (the file backend writes `.eml` to disk, so every
    invitation would silently go nowhere) and an https base URL (every
    verification link is built from it, so plain http puts single-use account
    tokens on the wire). A test that set only what it cared about would be
    caught by whichever guard it forgot and prove nothing about the one it meant.
    """
    monkeypatch.setenv("NEXUS_ENV", "production")
    monkeypatch.setenv("NEXUS_DATABASE_URL", "postgresql+asyncpg://u:p@h/db")
    monkeypatch.setenv("NEXUS_STORAGE_SIGNING_SECRET", "s")
    monkeypatch.setenv("NEXUS_CONNECTOR_SECRET_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("NEXUS_MAILER_BACKEND", "smtp")
    monkeypatch.setenv("NEXUS_PUBLIC_BASE_URL", "https://app.example.com")


# ── The round trip ────────────────────────────────────────────


def test_a_sealed_credential_opens_again() -> None:
    settings = _settings()
    sealed = seal(TOKEN, settings=settings)

    assert unseal(sealed, settings=settings) == TOKEN


def test_the_ciphertext_does_not_contain_the_token() -> None:
    """Obvious, and worth an assertion anyway: an encoding that merely wrapped
    the value would pass every other test in this file."""
    sealed = seal(TOKEN, settings=_settings())

    assert TOKEN not in sealed.ciphertext
    assert "refresh" not in sealed.ciphertext


def test_sealing_the_same_token_twice_gives_different_ciphertext() -> None:
    """Fernet carries a random IV. Identical ciphertext for identical input
    would let anybody with read access tell which two workspaces connected the
    same account, without decrypting anything."""
    settings = _settings()

    assert seal(TOKEN, settings=settings).ciphertext != seal(TOKEN, settings=settings).ciphertext


# ── The key id, and why it is derived ─────────────────────────


def test_the_key_id_is_a_fingerprint_of_the_key() -> None:
    """Derived, not configured. A counter would need its own setting, its own
    migration when it drifts, and somebody to remember to increment it — and the
    one moment it matters is the one moment nobody remembered."""
    key = Fernet.generate_key().decode()

    assert key_id_for(key) == key_id_for(key)
    assert key_id_for(key) != key_id_for(Fernet.generate_key().decode())
    assert len(key_id_for(key)) == 16


def test_a_new_key_produces_a_new_id_without_anybody_saying_so() -> None:
    """The property rotation rests on: rows sealed with the old key are a query,
    not an archaeology exercise."""
    first, second = _settings(), _settings()

    assert seal(TOKEN, settings=first).key_id != seal(TOKEN, settings=second).key_id


def test_the_key_id_is_not_the_key() -> None:
    key = Fernet.generate_key().decode()

    assert key_id_for(key) not in key
    assert key not in key_id_for(key)


# ── Refusals, and what they are allowed to say ────────────────


def test_no_key_is_a_refusal_and_never_a_plaintext_fallback() -> None:
    """**The failure that would look like success.** A connector that stored the
    token unencrypted would pass every other assertion here."""
    with pytest.raises(CredentialSealError, match="NEXUS_CONNECTOR_SECRET_KEY"):
        seal(TOKEN, settings=_settings(key=""))


def test_a_malformed_key_is_never_echoed_in_the_message() -> None:
    """A malformed key is usually a real key with a character missing, so a
    message that quoted it would put most of a live secret in the logs."""
    broken = Fernet.generate_key().decode()[:-4]

    with pytest.raises(CredentialSealError) as raised:
        seal(TOKEN, settings=_settings(key=broken))

    assert broken not in str(raised.value)
    assert broken[:10] not in str(raised.value)


def test_an_empty_credential_is_refused_rather_than_sealed() -> None:
    """It encrypts and decrypts perfectly well, which is the problem: the
    connection would hold a credential-shaped value and fail at the provider."""
    with pytest.raises(CredentialSealError, match="empty"):
        seal("", settings=_settings())


def test_no_failure_path_puts_the_token_in_its_message() -> None:
    settings = _settings()
    sealed = seal(TOKEN, settings=settings)
    corrupt = Sealed(ciphertext="not-a-fernet-token", key_id=sealed.key_id)

    with pytest.raises(CredentialSealError) as raised:
        unseal(corrupt, settings=settings)

    assert TOKEN not in str(raised.value)


# ── Rotation reports itself as rotation ───────────────────────


def test_a_key_mismatch_says_re_seal_rather_than_discard() -> None:
    """**The two have different remedies.** Unfinished rotation needs
    re-sealing; a corrupt row needs discarding. A message that blurred them
    would send somebody deleting a customer's working connection."""
    sealed = seal(TOKEN, settings=_settings())

    with pytest.raises(CredentialSealError) as raised:
        unseal(sealed, settings=_settings())

    message = str(raised.value)
    assert "re-sealing" in message
    assert "not discarding" in message
    assert sealed.key_id in message, "the message must name which key is wanted"


def test_a_deployed_environment_refuses_to_boot_without_a_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """**Asserted as behaviour, not as membership of a tuple.**

    A deployment that starts without the key accepts an OAuth callback it cannot
    store, and fails on the first sweep instead of at boot. The first cut of
    this read `Settings._DEPLOYED_REQUIRES` off the class and got pydantic's
    `ModelPrivateAttr` descriptor — which was a useful accident, because the
    list is an implementation detail and the refusal is the thing that matters.
    """
    _a_valid_production_env(monkeypatch)
    monkeypatch.setenv("NEXUS_CONNECTOR_SECRET_KEY", "")
    get_settings.cache_clear()

    # The message names the **environment variable**, not the field: it is read
    # by whoever is configuring the deployment, and they are looking at a list
    # of `NEXUS_*` names rather than at `Settings`.
    with pytest.raises(ValidationError, match="NEXUS_CONNECTOR_SECRET_KEY"):
        Settings()


def test_a_missing_language_model_key_still_boots(monkeypatch: pytest.MonkeyPatch) -> None:
    """The contrast that makes the rule above legible. ADR 0011 makes an absent
    model a *supported* state, so listing it beside the connector key would turn
    "no AI yet" into a refusal to start.

    **Asserted as "it constructs", never by reading the key back.** The first
    cut compared `anthropic_api_key` to `""` and, on a developer machine with a
    real key in `.env`, pytest printed the live secret into the diff. A test
    that can echo a credential on failure is a test that will, and the claim
    here was never about the value — it is that an absent key does not stop the
    process booting.

    `setenv("", ...)` rather than `delenv`: `Settings` reads `.env` through
    pydantic-settings, so removing the variable falls through to the file. An
    explicit empty value is what actually overrides it.
    """
    _a_valid_production_env(monkeypatch)
    monkeypatch.setenv("NEXUS_ANTHROPIC_API_KEY", "")
    get_settings.cache_clear()

    assert Settings().env is Env.production
