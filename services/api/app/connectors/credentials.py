"""Sealing a provider's refresh token, and the key id that makes rotation possible.

ADR 0032, answering **D27 with option A**: an encrypted column keyed from the
environment. The alternatives and why they lost are argued there; what matters
here is the shape.

## Only the refresh token is ever sealed

An access token expires within the hour, so storing one buys nothing and widens
what a database read is worth. The refresh token is exchanged for an access
token at the start of a sweep and the access token lives in memory for the life
of that sweep — ADR 0032's option C, which costs one extra call and removes a
class of exposure.

## The key id is a fingerprint of the key, not a number somebody assigns

Rotation without a key id means decrypting every row with every historical key
and guessing. A counter would need its own configuration, its own migration when
it drifts, and somebody to remember to increment it. A fingerprint of the key
itself cannot drift: **a new key has a new id by construction**, so the rows
still holding the old one are a query rather than an archaeology exercise.

Truncated to sixteen hex characters. It identifies a key among the handful a
deployment will ever hold; it is not a secret and is not a checksum of anything
worth attacking, and the full digest would just be noise in every row.

## What this module refuses to do

It does not log, and it does not put plaintext, ciphertext or the key into an
exception message. `str(error)` reaches logs and, summarised, a screen — the
same rule `connectors/rest.py` follows about tokens in URLs, applied to the
thing the token is made of.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Final

from cryptography.fernet import Fernet, InvalidToken

from app.config import Settings

KEY_ID_LENGTH: Final = 16


class CredentialSealError(Exception):
    """A credential could not be sealed or opened. Carries no secret, ever."""


@dataclass(frozen=True, slots=True)
class Sealed:
    """A credential as it is stored: ciphertext, and which key made it.

    Two columns rather than one blob with the id baked in. A row whose key id is
    queryable is a row a rotation can find; one that has to be decrypted to
    discover it cannot be found without the very key that may be gone.
    """

    ciphertext: str
    key_id: str


def key_id_for(key: str) -> str:
    """A stable identifier for a key, derived from the key.

    SHA-256 of the key material, truncated. Deriving it rather than configuring
    it is what makes *"which rows use the old key?"* answerable without anybody
    having remembered to write the answer down at the time.
    """
    return hashlib.sha256(key.encode()).hexdigest()[:KEY_ID_LENGTH]


def _cipher(settings: Settings) -> tuple[Fernet, str]:
    key = settings.connector_secret_key.get_secret_value()
    if not key:
        # Deployed environments cannot reach here — `_DEPLOYED_REQUIRES` stops
        # the process booting without it. This is the local case, and it is a
        # loud failure rather than a silent plaintext fallback: a connector that
        # quietly stored an unencrypted token would be indistinguishable from
        # one that encrypted it until the day somebody read the table.
        raise CredentialSealError(
            "NEXUS_CONNECTOR_SECRET_KEY is not set, so no provider credential "
            "can be stored. Generate one with Fernet.generate_key()."
        )
    try:
        return Fernet(key.encode()), key_id_for(key)
    except (ValueError, TypeError):
        # The exception is deliberately not chained with the key in it: a
        # malformed key often *is* a real key with a character missing, and a
        # traceback that echoed it would put most of a live secret in the logs.
        raise CredentialSealError(
            "NEXUS_CONNECTOR_SECRET_KEY is not a valid Fernet key — it must be "
            "32 bytes, url-safe base64 encoded."
        ) from None


def seal(refresh_token: str, *, settings: Settings) -> Sealed:
    """Encrypt a refresh token for storage.

    Rejects an empty token rather than sealing one. An empty string encrypts
    perfectly well and decrypts to nothing, so a connection would store a
    credential-shaped value, pass every check, and fail at the provider — which
    is the state the whole ledger exists to make impossible to reach quietly.
    """
    if not refresh_token:
        raise CredentialSealError("refusing to seal an empty credential")

    cipher, identifier = _cipher(settings)
    return Sealed(ciphertext=cipher.encrypt(refresh_token.encode()).decode(), key_id=identifier)


def unseal(sealed: Sealed, *, settings: Settings) -> str:
    """Decrypt a stored refresh token.

    **A key mismatch is reported as a key mismatch**, not as a corrupt
    credential. The two have different remedies — one is rotation the deployment
    has not finished, the other is a row to discard — and a message that blurred
    them would send somebody deleting a customer's working connection.
    """
    cipher, identifier = _cipher(settings)
    if sealed.key_id != identifier:
        raise CredentialSealError(
            f"this credential was sealed with key {sealed.key_id} and the "
            f"deployment now holds {identifier}; it needs re-sealing, not discarding"
        )

    try:
        return cipher.decrypt(sealed.ciphertext.encode()).decode()
    except InvalidToken:
        raise CredentialSealError(
            "the stored credential could not be opened with the key that sealed it"
        ) from None
