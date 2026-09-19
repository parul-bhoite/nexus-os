"""The address to key the scan's rate limits by. G6, ADR 0046.

Restored from `app/routes/preview.py` (deleted at `dc287dd`, P2) essentially
unchanged — the trust problem is identical: `X-Forwarded-For` is
attacker-controlled by default, and believing it lets one client mint
unlimited rate-limit identities, which is exactly what
`AUDIT-FINDINGS.md`'s "the per-IP rate limit was completely bypassable"
finding was.
"""

from __future__ import annotations

from fastapi import Request

from app.config import Settings


def client_ip(request: Request, settings: Settings) -> str:
    """The address to rate-limit against.

    `X-Forwarded-For` is honoured **only** when the direct peer is a
    configured trusted proxy (`settings.trusted_proxies`). Otherwise the
    direct peer is used as-is — every visitor arriving through an
    unconfigured proxy then shares one bucket, and the per-IP limit
    collapses towards a global one. That is the safe failure, but it is a
    failure: a deployment behind a proxy must set `NEXUS_TRUSTED_PROXY_IPS`.
    """
    peer = request.client.host if request.client else "unknown"
    if peer not in settings.trusted_proxies:
        return peer

    forwarded = request.headers.get("x-forwarded-for", "")
    # Left-most entry is the original client; the rest are hops.
    original = forwarded.split(",")[0].strip()
    return original or peer
