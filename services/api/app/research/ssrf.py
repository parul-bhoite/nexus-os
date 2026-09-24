"""SSRF guard for every server-side fetch of a user-influenced URL.

Doc 06 §1.2. This applies to the pre-registration crawl **and** to discovered
competitor URLs, which are shaped by search results and by the model and are
therefore not trusted input either.

The design decision that matters most: `validate_url` returns the **resolved IP**
and the caller connects to that address. Validating a hostname and then handing
the hostname to an HTTP client resolves DNS twice — once for the check, once for
the connection — and an attacker's nameserver is free to answer publicly the
first time and `169.254.169.254` the second. Pinning closes that window.

Everything here fails closed. An address we cannot classify is not public.
"""

from __future__ import annotations

import ipaddress
import socket
from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit

MAX_URL_LENGTH = 2048

ALLOWED_SCHEMES = frozenset({"http", "https"})

# Deliberately a small allowlist rather than a blocklist of dangerous ports.
# A blocklist is a guess about which services are reachable; an allowlist is a
# statement about which are legitimate for a website crawl.
ALLOWED_PORTS = frozenset({80, 443, 8080, 8443})

# Blocked by name as well as by address. If a resolver is ever misconfigured, or
# a future code path skips resolution, the name alone must still be refused.
BLOCKED_HOSTNAMES = frozenset(
    {
        "metadata",
        "metadata.google.internal",
        "metadata.goog",
        "instance-data",
        "localhost",
        "localhost.localdomain",
        "169.254.169.254",
    }
)
BLOCKED_HOST_SUFFIXES = (".internal", ".local", ".localdomain", ".localhost")

Resolver = Callable[[str], list[str]]

# RFC 6052 §2.1. A DNS64 resolver on a NAT64 network synthesises an AAAA record
# under this prefix for every IPv4-only host, embedding the v4 address in the low
# 32 bits. Recognised so the embedded address can be classified on its own
# merits — see `_unwrap_embedded_ipv4`.
#
# Only the well-known prefix. RFC 6052 also permits Network-Specific Prefixes,
# which are chosen per site and cannot be identified from the address alone; one
# of those is indistinguishable from ordinary global unicast and is treated as
# such.
NAT64_WELL_KNOWN_PREFIX = ipaddress.ip_network("64:ff9b::/96")


def _unwrap_embedded_ipv4(ip: ipaddress.IPv6Address) -> ipaddress.IPv4Address | None:
    """The IPv4 address an IPv6 address carries, if it carries one.

    Three encodings put an IPv4 address inside an IPv6 one, and all three let it
    slip past IPv6-shaped checks. IPv4-mapped and 6to4 were handled from the
    start; NAT64 was not, and it is the one that shows up in practice — this
    machine's network runs DNS64, so `omantel.om` resolved to
    `64:ff9b::d448:ad3` alongside its real A record and every fetch was refused.

    Python reports the whole `64:ff9b::/96` block as `is_reserved`, so those
    addresses were being rejected — correct-looking, but by accident rather than
    by decision. Unwrapping makes it a decision: a NAT64 address wrapping
    `127.0.0.1` is refused because loopback is refused, and one wrapping a real
    public address is allowed because that address is allowed. The alternative,
    trusting the prefix, would have been a clean SSRF bypass.
    """
    if ip.ipv4_mapped is not None:
        return ip.ipv4_mapped
    if ip.sixtofour is not None:
        return ip.sixtofour
    if ip in NAT64_WELL_KNOWN_PREFIX:
        return ipaddress.ip_address(int(ip) & 0xFFFFFFFF)  # type: ignore[return-value]
    return None


class UrlNotAllowedError(ValueError):
    """The URL may not be fetched. The message is safe to log, not to display."""


@dataclass(frozen=True, slots=True)
class ValidatedTarget:
    url: str
    scheme: str
    host: str
    port: int
    ip: str
    """The address that was validated. Connect to *this*, not to `host`."""


def is_public_ip(candidate: str) -> bool:
    """True only for addresses that are unambiguously on the public internet."""
    try:
        ip = ipaddress.ip_address(candidate)
    except ValueError:
        return False

    # IPv4-mapped, 6to4 and NAT64 forms all smuggle IPv4 addresses through IPv6
    # checks, so unwrap before classifying.
    if isinstance(ip, ipaddress.IPv6Address):
        embedded = _unwrap_embedded_ipv4(ip)
        if embedded is not None:
            ip = embedded

    # `is_global` is the authoritative test and the primary gate: it is False
    # for every non-globally-routable range, including ones the individual
    # flags miss. Carrier-grade NAT (100.64.0.0/10, RFC 6598) is the example
    # that caught this — `is_private` is False for it, but it is emphatically
    # not the public internet.
    if not ip.is_global:
        return False

    # Redundant given the above, and kept deliberately: these name the specific
    # threats, so a future change to `is_global` semantics cannot silently
    # reopen loopback or the metadata range.
    return not (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def _system_resolver(host: str) -> list[str]:
    try:
        infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    except socket.gaierror:
        return []
    except UnicodeError:
        # A malformed host — an empty or >63-char DNS label, e.g. `foo..com` —
        # makes getaddrinfo raise UnicodeError from the stdlib idna codec rather
        # than gaierror. Treat it as unresolvable: validate_url turns [] into a
        # clean UrlNotAllowedError refusal, not an unhandled 500.
        return []
    # sockaddr[0] is the address for both AF_INET and AF_INET6; the annotation
    # is a union because the tuple shapes differ.
    return list({str(info[4][0]) for info in infos})


def _is_blocked_hostname(host: str) -> bool:
    lowered = host.lower().rstrip(".")
    if lowered in BLOCKED_HOSTNAMES:
        return True
    return any(lowered.endswith(suffix) for suffix in BLOCKED_HOST_SUFFIXES)


def validate_url(raw: str, *, resolve: Resolver | None = None) -> ValidatedTarget:
    """Validate a URL and pin the address it resolved to.

    Raises `UrlNotAllowedError` for anything that is not plainly a public
    website. The resolver is injectable so this is testable without DNS.
    """
    resolver = resolve or _system_resolver

    if not raw or not raw.strip():
        raise UrlNotAllowedError("empty url")
    if len(raw) > MAX_URL_LENGTH:
        raise UrlNotAllowedError("url too long")

    try:
        parts = urlsplit(raw.strip())
    except ValueError as exc:
        raise UrlNotAllowedError("unparseable url") from exc

    scheme = parts.scheme.lower()
    if scheme not in ALLOWED_SCHEMES:
        raise UrlNotAllowedError(f"scheme not allowed: {scheme or '(none)'}")

    # Credentials in the authority let `http://expected.com@evil.com/` read as
    # one host to a human and connect to another.
    if parts.username or parts.password or "@" in (parts.netloc or ""):
        raise UrlNotAllowedError("credentials in url")

    try:
        host = parts.hostname
        port = parts.port or (443 if scheme == "https" else 80)
    except ValueError as exc:
        raise UrlNotAllowedError("invalid host or port") from exc

    if not host:
        raise UrlNotAllowedError("missing host")
    if port not in ALLOWED_PORTS:
        raise UrlNotAllowedError(f"port not allowed: {port}")
    if _is_blocked_hostname(host):
        raise UrlNotAllowedError(f"host not allowed: {host}")

    # A literal address skips DNS entirely — classify it directly. This also
    # covers octal, decimal and hex forms, which `ip_address` normalises.
    literal = _as_literal_ip(host)
    if literal is not None:
        if not is_public_ip(literal):
            raise UrlNotAllowedError(f"non-public address: {host}")
        return ValidatedTarget(raw.strip(), scheme, host, port, literal)

    answers = resolver(host)
    if not answers:
        raise UrlNotAllowedError(f"host does not resolve: {host}")

    # Every answer must be public. Cherry-picking a public record from a mixed
    # answer leaves the connection free to use the private one, and makes the
    # outcome depend on resolver ordering.
    for answer in answers:
        if not is_public_ip(answer):
            raise UrlNotAllowedError(f"resolves to a non-public address: {host}")

    return ValidatedTarget(raw.strip(), scheme, host, port, answers[0])


def _as_literal_ip(host: str) -> str | None:
    """Normalise a literal address, including octal, decimal and hex forms.

    `0177.0.0.1`, `2130706433` and `0x7f.0x0.0x0.0x1` are all 127.0.0.1 to a
    permissive network stack, so they must be recognised as literals rather
    than passed to DNS as names.
    """
    stripped = host.strip("[]")
    try:
        return str(ipaddress.ip_address(stripped))
    except ValueError:
        pass

    # Bare decimal, e.g. 2130706433
    if stripped.isdigit():
        try:
            return str(ipaddress.ip_address(int(stripped)))
        except ValueError:
            return None

    # Dotted octal or hex, e.g. 0177.0.0.1 or 0x7f.0x0.0x0.0x1
    labels = stripped.split(".")
    if len(labels) == 4:
        octets = []
        for label in labels:
            try:
                if label.lower().startswith("0x"):
                    octets.append(int(label, 16))
                elif label.startswith("0") and len(label) > 1:
                    octets.append(int(label, 8))
                elif label.isdigit():
                    octets.append(int(label))
                else:
                    return None
            except ValueError:
                return None
        if all(0 <= o <= 255 for o in octets):
            return ".".join(str(o) for o in octets)

    return None


def resolve_redirect(current_url: str, location: str) -> str:
    """Absolutise a `Location` header against the hop it came from.

    Returned as a plain string so the caller must pass it back through
    `validate_url` — doc 06 §1.2 requires redirect chains to be re-validated at
    every hop, and validating only the first URL is the most common way this
    guard is got wrong.
    """
    return urljoin(current_url, location)
