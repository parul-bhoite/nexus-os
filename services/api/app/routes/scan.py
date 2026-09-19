"""`POST/GET/DELETE /public/scans` — the Instant Gap Analysis endpoint. G7.

**Declares no session dependency, deliberately.** This is the whole point of
ADR 0046: a visitor gets three real gaps before signing up. No cookie is read
and none is set, so CSRF does not apply — `require_csrf` guards a request
that rides on a cookie the browser attaches automatically; this one attaches
nothing, and there is no session for a forged request to act inside.

**Named by ADR 0046 as the one anonymous route module permitted to reach
`app.research.crawler`** — `tests/test_scan_boundary.py`'s named-route
assertion depends on this module being exactly `app.routes.scan`, and depends
on it going through `app.scan.engine` rather than importing the crawler
directly.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field

from app.config import Settings, get_settings
from app.connectors.domain_check import normalise_domain
from app.connectors.rate_limit import (
    SCAN_GLOBAL_DAILY,
    SCAN_PER_DOMAIN,
    SCAN_PER_IP,
    RateLimitedError,
    check_and_increment,
    hash_bucket_key,
)
from app.db import _unscoped_session
from app.logging import get_logger
from app.scan import client_address, engine, store

log = get_logger(__name__)

router = APIRouter(prefix="/public/scans", tags=["scan"])

# Every domain shares this one bucket — it is the ceiling on total load, not
# on any one caller or target, so it needs no per-request key.
_GLOBAL_KEY = "global"


class ScanRequest(BaseModel):
    url: str = Field(min_length=1, max_length=2048)


class CheckOut(BaseModel):
    id: str
    label: str
    evidence: str
    weight: int


class CategoryScoreOut(BaseModel):
    category: str
    score: int
    max_score: int
    percentage: int


class ScanResponse(BaseModel):
    id: UUID
    domain: str
    scanned_url: str
    checks: list[CheckOut]
    scores: list[CategoryScoreOut]
    pages_read: int
    js_rendered: bool
    created_at: datetime
    expires_at: datetime


def _to_response(row: store.ScanRow) -> ScanResponse:
    return ScanResponse(
        id=row.id,
        domain=row.domain,
        scanned_url=row.scanned_url,
        checks=[
            CheckOut(id=c.id, label=c.label, evidence=c.evidence, weight=c.weight)
            for c in row.checks
        ],
        scores=[CategoryScoreOut(**s) for s in row.scores],
        pages_read=row.pages_read,
        js_rendered=row.js_rendered,
        created_at=row.created_at,
        expires_at=row.expires_at,
    )


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_scan(
    payload: ScanRequest,
    request: Request,
    response: Response,
    settings: Annotated[Settings, Depends(get_settings)],
) -> ScanResponse:
    """`{ url }` -> **201** when freshly crawled, **200** when served from a
    live cached row (no second fetch, no rate limit consumed — nothing was
    fetched), **429** when limited, **422** when the url is malformed or the
    target refuses the scan (SSRF-blocked, unreachable, not a web page, or
    `robots.txt`)."""
    domain = normalise_domain(payload.url)
    if not domain or "." not in domain:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "That does not look like a website address."
        )

    async with _unscoped_session() as db:
        cached = await store.get_fresh(db, domain)
    if cached is not None:
        response.status_code = status.HTTP_200_OK
        return _to_response(cached)

    secret = settings.require("storage_signing_secret")
    ip_key = hash_bucket_key(client_address.client_ip(request, settings), secret=secret)
    try:
        async with _unscoped_session() as db:
            await check_and_increment(db, SCAN_PER_IP, ip_key)
            await check_and_increment(db, SCAN_PER_DOMAIN, domain)
            await check_and_increment(db, SCAN_GLOBAL_DAILY, _GLOBAL_KEY)
            await db.commit()
    except RateLimitedError as exc:
        log.info("scan.rate_limited", scope=exc.scope)
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Too many scans right now — try again shortly.",
            headers={"Retry-After": str(exc.retry_after_seconds)},
        ) from exc

    try:
        result = await engine.scan(payload.url)
    except engine.ScanRefusedError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, exc.reason) from exc

    async with _unscoped_session() as db:
        row = await store.insert(
            db,
            domain=domain,
            scanned_url=result.scanned_url,
            checks=result.gap_checks,
            scores=result.category_scores,
            pages_read=result.pages_read,
            js_rendered=result.js_rendered,
        )
        await db.commit()

    response.headers["Location"] = f"/public/scans/{row.id}"
    return _to_response(row)


@router.get("/{scan_id}")
async def read_scan(scan_id: UUID) -> ScanResponse:
    """**200**, or **404** when expired, deleted or unknown — one code for
    all three, so the id is not an oracle for whether a domain was ever
    scanned."""
    async with _unscoped_session() as db:
        row = await store.get_by_id(db, scan_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found.")
    return _to_response(row)


@router.delete("/{scan_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_scan(scan_id: UUID) -> Response:
    """**204**, idempotent — deleting an unknown or already-deleted id is not
    an error. Soft: `deleted_at`, not a row removal."""
    async with _unscoped_session() as db:
        await store.soft_delete(db, scan_id)
        await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
