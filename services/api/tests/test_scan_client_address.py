"""Which address the scan's rate limiter counts against.

Restored from `tests/test_client_ip.py` (deleted at `dc287dd`, P2) with the
import path updated from `app.routes.preview` to `app.scan.client_address` —
the function itself is unchanged, because the trust problem is unchanged.

This is a small function with an outsized failure mode. Believe
`X-Forwarded-For` unconditionally and one client mints unlimited identities,
defeating the per-IP limit and, through it, the cost ceiling doc 06 §1.2
exists to protect. Ignore it unconditionally and every visitor behind the web
proxy shares one bucket, so the per-IP limit becomes a global 5/hour and the
product breaks for everyone.

The rule is therefore conditional: honour the header only when the direct
peer is a configured trusted proxy.
"""

from __future__ import annotations

from fastapi import Request

from app.config import Settings
from app.scan.client_address import client_ip

PROXY = "10.0.0.7"
VISITOR = "203.0.113.9"


def make_request(*, peer: str, forwarded: str | None = None) -> Request:
    headers = []
    if forwarded is not None:
        headers.append((b"x-forwarded-for", forwarded.encode()))
    return Request(
        {
            "type": "http",
            "method": "POST",
            "headers": headers,
            "client": (peer, 12345),
            "query_string": b"",
        }
    )


def settings_trusting(*proxies: str) -> Settings:
    return Settings(trusted_proxy_ips=",".join(proxies))


def test_untrusted_peer_forwarded_header_is_ignored() -> None:
    """The attack: spoof the header, get a fresh bucket on every request."""
    request = make_request(peer="198.51.100.4", forwarded="1.2.3.4")
    assert client_ip(request, settings_trusting()) == "198.51.100.4"


def test_spoofed_header_cannot_mint_identities() -> None:
    settings = settings_trusting()
    seen = {
        client_ip(make_request(peer="198.51.100.4", forwarded=f"9.9.9.{i}"), settings)
        for i in range(20)
    }
    assert seen == {"198.51.100.4"}, "spoofed headers produced distinct rate-limit keys"


def test_trusted_proxy_forwarded_header_is_honoured() -> None:
    request = make_request(peer=PROXY, forwarded=VISITOR)
    assert client_ip(request, settings_trusting(PROXY)) == VISITOR


def test_leftmost_entry_is_the_original_client() -> None:
    request = make_request(peer=PROXY, forwarded=f"{VISITOR}, 10.0.0.8, 10.0.0.9")
    assert client_ip(request, settings_trusting(PROXY)) == VISITOR


def test_trusted_proxy_without_a_header_falls_back_to_the_peer() -> None:
    request = make_request(peer=PROXY)
    assert client_ip(request, settings_trusting(PROXY)) == PROXY


def test_trusted_proxy_with_an_empty_header_falls_back_to_the_peer() -> None:
    request = make_request(peer=PROXY, forwarded="   ")
    assert client_ip(request, settings_trusting(PROXY)) == PROXY


def test_a_request_with_no_client_still_yields_a_key() -> None:
    """Rate limiting must never crash the endpoint it protects."""
    request = Request({"type": "http", "method": "POST", "headers": [], "query_string": b""})
    assert client_ip(request, settings_trusting()) == "unknown"


def test_trusted_proxy_list_parsing() -> None:
    settings = Settings(trusted_proxy_ips=" 10.0.0.7 , 10.0.0.8 ,, ")
    assert settings.trusted_proxies == frozenset({"10.0.0.7", "10.0.0.8"})


def test_default_is_to_trust_nothing() -> None:
    """The safe default. A deployment behind a proxy must opt in explicitly."""
    assert Settings().trusted_proxies == frozenset()
