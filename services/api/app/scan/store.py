"""`public_scan` — the only module that opens an unscoped connection for it.

ADR 0048 rule 2: named so `grep -r public_scan` is short and reviewable — a
tenantless table has no `ScopedSession` to protect it, so the discipline
that would normally come from `retrieval/` has to come from convention here
instead, and a convention only holds if there is exactly one place to check.

**Only computed signals are stored, never page content.** `checks` are the
ranked `Check`s `app.calculators.gaps.top` produced — `id`, `label`,
`evidence`, `weight` — never `PageSignals`, raw HTML, or `text_sample`
(ADR 0048 rule 1, the `SIGNALS_NOT_STORED` precedent).

**JSONB in, JSONB out, through `text()`.** SQLAlchemy's asyncpg dialect does
not know an unbound `text()` parameter is JSON — passing a raw Python `list`
for `checks` raised `'list' object has no attribute 'encode'` the first time
this was run against Neon (asyncpg's JSONB encoder wants an already-encoded
string). Fixed the way `app/domain/onboarding_sessions.py` already does it:
`json.dumps()` before binding, `CAST(:x AS jsonb)` in the SQL rather than
`::jsonb` (a literal `:` two characters later reads as a second bind
parameter to SQLAlchemy's `text()`), and `json.loads()` on the way back —
guarded by `isinstance(value, str)`, because whether asyncpg hands back a
decoded object or the raw string is not guaranteed the same way on every
read path.

**The column list is spelled out in each query, not shared as an f-string
constant.** A shared constant interpolated into `text()` trips `ruff`'s
`S608` (possible SQL injection via string-built queries) even though nothing
here is user input — ruff cannot see that. Three literal copies are worth it
to keep the rule meaningful instead of silenced.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.calculators.audit import Check


@dataclass(frozen=True, slots=True)
class ScanRow:
    id: UUID
    domain: str
    scanned_url: str
    checks: tuple[Check, ...]
    scores: tuple[dict[str, object], ...]
    pages_read: int
    js_rendered: bool
    created_at: datetime
    expires_at: datetime


def _loads_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, str):
        return list(json.loads(value))
    return list(value)


def _serialise_checks(checks: tuple[Check, ...]) -> str:
    return json.dumps(
        [{"id": c.id, "label": c.label, "evidence": c.evidence, "weight": c.weight} for c in checks]
    )


def _deserialise_checks(raw: Any) -> tuple[Check, ...]:
    return tuple(
        Check(
            id=str(c["id"]),
            label=str(c["label"]),
            passed=False,  # only failed checks are ever stored — G3, gaps.rank
            weight=int(c["weight"]),
            evidence=str(c["evidence"]),
        )
        for c in _loads_list(raw)
    )


def _row_from(row: Any) -> ScanRow:
    return ScanRow(
        id=row["id"],
        domain=row["domain"],
        scanned_url=row["scanned_url"],
        checks=_deserialise_checks(row["checks"]),
        scores=tuple(_loads_list(row["scores"])),
        pages_read=row["pages_read"],
        js_rendered=row["js_rendered"],
        created_at=row["created_at"],
        expires_at=row["expires_at"],
    )


async def get_fresh(db: AsyncSession, domain: str) -> ScanRow | None:
    """The freshest live row for `domain` — unexpired, undeleted — or `None`.

    "Freshest" rather than "first": `ix_public_scan__domain_created` orders
    by `created_at DESC`, so a re-scan after the TTL naturally supersedes an
    older row without either being deleted.
    """
    result = await db.execute(
        text(
            """
            SELECT id, domain, scanned_url, checks, scores, pages_read,
                   js_rendered, created_at, expires_at
            FROM public_scan
            WHERE domain = :domain AND expires_at > now() AND deleted_at IS NULL
            ORDER BY created_at DESC
            LIMIT 1
            """
        ),
        {"domain": domain},
    )
    row = result.mappings().first()
    return None if row is None else _row_from(row)


async def get_by_id(db: AsyncSession, scan_id: UUID) -> ScanRow | None:
    """A row by id, or `None` if it is unknown, expired or deleted.

    One `None` for all three — an id must not be an oracle for whether a
    domain was ever scanned (`doc/18` G7's own contract for the route).
    """
    result = await db.execute(
        text(
            """
            SELECT id, domain, scanned_url, checks, scores, pages_read,
                   js_rendered, created_at, expires_at
            FROM public_scan
            WHERE id = :id AND expires_at > now() AND deleted_at IS NULL
            """
        ),
        {"id": str(scan_id)},
    )
    row = result.mappings().first()
    return None if row is None else _row_from(row)


async def insert(
    db: AsyncSession,
    *,
    domain: str,
    scanned_url: str,
    checks: tuple[Check, ...],
    scores: tuple[dict[str, object], ...],
    pages_read: int,
    js_rendered: bool,
) -> ScanRow:
    """Insert one row. `expires_at` is the column's own server default
    (`now() + interval '7 days'`, migration `0037`) — not set here, so the
    seven-day TTL cannot be forgotten by a caller."""
    result = await db.execute(
        text(
            """
            INSERT INTO public_scan (domain, scanned_url, checks, scores, pages_read, js_rendered)
            VALUES (:domain, :scanned_url, CAST(:checks AS jsonb), CAST(:scores AS jsonb),
                    :pages_read, :js_rendered)
            RETURNING id, domain, scanned_url, checks, scores, pages_read,
                      js_rendered, created_at, expires_at
            """
        ),
        {
            "domain": domain,
            "scanned_url": scanned_url,
            "checks": _serialise_checks(checks),
            "scores": json.dumps(list(scores)),
            "pages_read": pages_read,
            "js_rendered": js_rendered,
        },
    )
    return _row_from(result.mappings().one())


async def soft_delete(db: AsyncSession, scan_id: UUID) -> None:
    """Idempotent — deleting an unknown or already-deleted id is not an
    error, matching the route's `DELETE` contract (always `204`)."""
    await db.execute(
        text("UPDATE public_scan SET deleted_at = now() WHERE id = :id AND deleted_at IS NULL"),
        {"id": str(scan_id)},
    )
