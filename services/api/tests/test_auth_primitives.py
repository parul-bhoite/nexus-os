"""Password and token handling.

These are pure functions, so they are tested without a database. The cases that
matter are the ones that fail *closed* — a malformed hash must not authenticate,
and a token comparison must not short-circuit.
"""

from __future__ import annotations

import pytest

from app.auth.passwords import (
    MAX_PASSWORD_LENGTH,
    MIN_PASSWORD_LENGTH,
    WeakPasswordError,
    hash_password,
    needs_rehash,
    verify_password,
)
from app.auth.tokens import csrf_matches, hash_token, new_csrf_token, new_token, tokens_match

PASSWORD = "Correct-horse-battery-staple1"


# ── Passwords ─────────────────────────────────────────────────


def test_hash_and_verify_round_trip() -> None:
    h = hash_password(PASSWORD)
    assert verify_password(h, PASSWORD) is True


def test_wrong_password_is_rejected() -> None:
    h = hash_password(PASSWORD)
    assert verify_password(h, PASSWORD + "!") is False


def test_hash_is_salted() -> None:
    """Two hashes of the same password must differ, or the store leaks reuse."""
    assert hash_password(PASSWORD) != hash_password(PASSWORD)


def test_hash_is_argon2id() -> None:
    assert hash_password(PASSWORD).startswith("$argon2id$")


def test_plaintext_never_appears_in_the_hash() -> None:
    assert PASSWORD not in hash_password(PASSWORD)


@pytest.mark.parametrize(
    "bad_hash",
    ["", "not-a-hash", "$argon2id$truncated", "$2b$12$bcrypt-style-hash-value-here"],
)
def test_malformed_stored_hash_fails_closed(bad_hash: str) -> None:
    """A corrupt hash is a data problem, never an authentication success."""
    assert verify_password(bad_hash, PASSWORD) is False


def test_short_password_is_rejected() -> None:
    with pytest.raises(WeakPasswordError):
        hash_password("X1" + "x" * (MIN_PASSWORD_LENGTH - 3))


def test_password_without_a_capital_is_rejected() -> None:
    # Long enough and has a digit, but no uppercase letter.
    with pytest.raises(WeakPasswordError):
        hash_password("lowercase-only-1")


def test_password_without_a_number_is_rejected() -> None:
    # Long enough and has a capital, but no digit.
    with pytest.raises(WeakPasswordError):
        hash_password("No-Digits-Here")


def test_minimum_compliant_password_is_accepted() -> None:
    # Exactly the floor: eight characters, one capital, one number.
    assert hash_password("Abcdefg1").startswith("$argon2id$")


def test_absurdly_long_password_is_rejected() -> None:
    """Unbounded input plus argon2's memory cost is a free CPU burn."""
    with pytest.raises(WeakPasswordError):
        hash_password("x" * (MAX_PASSWORD_LENGTH + 1))


def test_current_hash_does_not_need_rehash() -> None:
    assert needs_rehash(hash_password(PASSWORD)) is False


def test_unparseable_hash_is_treated_as_needing_rehash() -> None:
    assert needs_rehash("garbage") is True


# ── Tokens ────────────────────────────────────────────────────


def test_tokens_are_unique() -> None:
    assert len({new_token() for _ in range(200)}) == 200


def test_token_has_meaningful_entropy() -> None:
    # 32 random bytes, urlsafe-base64 encoded.
    assert len(new_token()) >= 40


def test_only_the_hash_is_storable() -> None:
    """A leaked database must not yield usable session tokens."""
    token = new_token()
    stored = hash_token(token)
    assert token not in stored
    assert len(stored) == 64  # sha256 hex


def test_token_match_is_by_hash() -> None:
    token = new_token()
    assert tokens_match(hash_token(token), token) is True
    assert tokens_match(hash_token(token), new_token()) is False


def test_csrf_token_comparison() -> None:
    token = new_csrf_token()
    assert csrf_matches(token, token) is True
    assert csrf_matches(token, "wrong") is False
    assert csrf_matches(token, None) is False
    assert csrf_matches(token, "") is False
