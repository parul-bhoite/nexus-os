"""Document upload — the first path that writes customer content.

Three obligations converge here, and each is enforced rather than assumed.

**Consent is a precondition, not a checkbox we log.** Doc 06 §5 requires the
customer to warrant their right to use what they upload, and migration 0007
backs it with `ck_document_consent_before_indexing`: a document cannot reach
`indexed` without `consent_given_at`. The practical control this represents is
someone indexing a competitor's leaked price list — the warranty makes that
their decision rather than ours.

**Failure is visible, always.** Doc 07 M5 requires a scanned PDF with no text
layer, an over-size file and a corrupt file to each say so. A silent failure is
worse than a loud one: the customer believes the document is searchable when it
is not, and finds out when an answer omits it — which reads as the product being
wrong rather than the upload having failed.

**Classification defaults to deny (I4).** Every chunk routes through
`classify_chunk`, which withholds to L5 plus the review queue on any parse
failure, classifier failure, or confidence below threshold.

What this module deliberately does *not* do is embed. That is task 5.6, and it
is a separate step because embedding is slow, needs a model, and must not sit
between the customer and their upload confirmation.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Annotated, Any, Final, NamedTuple
from uuid import UUID, uuid4

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Response,
    UploadFile,
    status,
)
from pydantic import BaseModel
from sqlalchemy import CursorResult, text

from app.auth.csrf import require_csrf
from app.config import Settings, get_settings
from app.db import _unscoped_session
from app.deps import CurrentScope
from app.documents.chunk import Chunk, chunk_document
from app.documents.classify import (
    Classification,
    ReviewState,
    classify_chunk,
    review_state_code,
)
from app.documents.limits import (
    MAX_FILE_BYTES,
    MAX_FILES_AT_ONBOARDING,
    WORKSPACE_QUOTA_BYTES,
    check_upload,
)
from app.documents.parse import ParseOutcome, parse_document_async
from app.documents.rules import propose
from app.documents.status import DocumentStatus
from app.domain import audit
from app.domain.departments import selected_departments
from app.domain.document_asks import asks_for
from app.domain.invitations import may_administer
from app.domain.progress import progress_for
from app.domain.scopes import Scope, scope_code
from app.domain.session import ScopedSession
from app.logging import get_logger
from app.retrieval.scoped import scoped_connection
from app.storage import FilesystemObjectStore, ObjectStore, workspace_key

router = APIRouter(prefix="/documents", tags=["documents"])
log = get_logger(__name__)

CONSENT_TEXT_VERSION = "2026-08-18.v1"
"""Bumped whenever the warranty wording changes.

Stored per document, because "they consented" means little without *what* they
consented to. A later dispute is about the wording in force at the time.
"""

CONSENT_WARRANTY = (
    "I warrant that this workspace has the right to use and index this document, "
    "and that doing so breaches no confidentiality obligation or third-party right."
)


class UploadOut(BaseModel):
    document_id: UUID
    filename: str
    status: str
    chunks_indexed: int
    chunks_held_for_review: int
    page_count: int | None
    message: str
    """Empty when the upload succeeded. Never empty when it did not."""


class DownloadOut(BaseModel):
    url: str
    expires_in_seconds: int


class DocumentSummary(BaseModel):
    document_id: UUID
    filename: str
    status: str
    page_count: int | None
    failure_reason: str | None
    created_at: datetime
    chunks_held_for_review: int


def _object_store(settings: Settings) -> ObjectStore:
    return FilesystemObjectStore(
        settings.storage_root,
        settings.require("storage_signing_secret"),
    )


class WorkspaceUsage(NamedTuple):
    bytes_used: int
    files: int
    onboarding: bool


async def workspace_usage(scope: CurrentScope) -> WorkspaceUsage:
    """Bytes stored, files stored, and whether onboarding is still running.

    **A dependency, not a call inside the handler** — the third time this file's
    neighbours have taught that lesson. Reading it inline turned seven upload
    tests into integration tests: they assert what the *route* does with a
    parsed file over a monkeypatched write, they have no database, and none of
    them is about quotas. A route that stays a pure function of its inputs can
    be tested for the thing it is actually responsible for.

    One query for the two counts, because both are read on every upload and a
    second round trip to decide a refusal is one too many.

    **Failed and quarantined documents count.** We kept the bytes — a file we
    could not parse is still the customer's file and is still on the disk — so
    excluding them would let a workspace fill the quota with files the product
    never read, which is exactly the case the quota exists for.
    """
    async with scoped_connection(scope) as db:
        row = (
            await db.execute(
                text("SELECT COALESCE(SUM(size_bytes), 0) AS used, COUNT(*) AS files FROM document")
            )
        ).one()

    async with _unscoped_session() as db:
        progress = await progress_for(db, workspace_id=scope.workspace_id)

    return WorkspaceUsage(int(row.used), int(row.files), not progress.finished)


Usage = Annotated[WorkspaceUsage, Depends(workspace_usage)]


@router.post(
    "",
    response_model=UploadOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_csrf)],
)
async def upload_document(
    scope: CurrentScope,
    settings: Annotated[Settings, Depends(get_settings)],
    usage: Usage,
    response: Response,
    file: Annotated[UploadFile, File()],
    consent: Annotated[bool, Form()] = False,
    supersedes_id: Annotated[UUID | None, Form()] = None,
) -> UploadOut:
    """Accept a document, parse it, classify every chunk, store it.

    `consent` must be true, and is a form field rather than an implicit property
    of the request: an upload that consents by virtue of being an upload is not
    a warranty anyone could rely on.

    **201 only when something was created that can be read.** Finding F11: a
    file we could not parse was recorded, quarantined, and answered
    `201 Created` with the refusal in the body — so a client checking the
    status alone read a rejected `.exe` as accepted. Keeping the row and the
    bytes is right (see `_record` below); calling it Created was not. The
    neighbouring guards already got this right: no consent is a 400, over the
    cap is a 413.
    """
    if not consent:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Confirm you have the right to use this document before uploading it.",
        )

    data = await file.read()
    if not data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "That file is empty.")

    # Q36's three limits, all decided server-side. A limit the browser enforces
    # is a suggestion: this endpoint is reachable without the browser, and the
    # one caller who skips it is the caller the limit exists for.
    breach = check_upload(
        size_bytes=len(data),
        workspace_bytes_used=usage.bytes_used,
        files_uploaded=usage.files,
        onboarding=usage.onboarding,
    )
    if breach is not None:
        log.info("document.refused", limit=breach.value)
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, breach.message)

    filename = file.filename or "untitled"
    parsed = await parse_document_async(data, filename=filename)
    digest = hashlib.sha256(data).hexdigest()

    document_id = uuid4()
    key = workspace_key(scope.workspace_id, "documents", str(document_id))

    # Stored whether or not parsing worked. A file we could not read is still
    # the customer's file, and discarding it because our parser failed would
    # lose something they believe they gave us.
    _object_store(settings).put(
        key, data, content_type=file.content_type or "application/octet-stream"
    )

    if not parsed.succeeded:
        await _record(
            document_id=document_id,
            scope=scope,
            filename=filename,
            content_type=file.content_type,
            size_bytes=len(data),
            storage_key=key,
            digest=digest,
            state=(
                DocumentStatus.QUARANTINED
                if parsed.outcome is ParseOutcome.UNSUPPORTED_TYPE
                else DocumentStatus.FAILED
            ),
            failure_reason=parsed.message,
            page_count=parsed.page_count or None,
            supersedes_id=supersedes_id,
        )
        log.info("document.parse_failed", outcome=parsed.outcome.value)
        # 422 rather than 400: the request was well formed and the guards above
        # passed. What failed is the content, which is exactly what this status
        # is for. The body is unchanged — the id and the reason are what a
        # client needs to show somebody, and the document really is on record.
        response.status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
        return UploadOut(
            document_id=document_id,
            filename=filename,
            status="failed",
            chunks_indexed=0,
            chunks_held_for_review=0,
            page_count=parsed.page_count or None,
            message=parsed.message,
        )

    classified = _classify_all(chunk_document(parsed.pages), scope=scope)

    await _record(
        document_id=document_id,
        scope=scope,
        filename=filename,
        content_type=file.content_type,
        size_bytes=len(data),
        storage_key=key,
        digest=digest,
        state=DocumentStatus.INDEXED,
        failure_reason=None,
        page_count=parsed.page_count,
        supersedes_id=supersedes_id,
        chunks=classified,
    )

    held = sum(1 for _, c in classified if c.review_state is not ReviewState.AUTO_APPROVED)
    log.info(
        "document.indexed",
        chunks=len(classified),
        held_for_review=held,
        page_count=parsed.page_count,
    )

    return UploadOut(
        document_id=document_id,
        filename=filename,
        status="indexed",
        chunks_indexed=len(classified) - held,
        chunks_held_for_review=held,
        page_count=parsed.page_count,
        message="",
    )


def _classify_all(
    chunks: list[Chunk], *, scope: ScopedSession
) -> list[tuple[Chunk, Classification]]:
    """Classify every chunk, defaulting to deny.

    **`propose` suggests; `classify_chunk` decides.** The split is the whole
    safety argument and is why connecting a classifier did not require touching
    the gate: nothing here can widen what the gate permits. Walking the four
    outcomes `rules.propose` can return against it:

    - a personal pattern (salary, passport, date of birth) → L5 at confidence
      1.0 with `Sensitivity.PERSONAL`, which `REQUIRES_HUMAN` sends to review
      *regardless* of that confidence;
    - a financial pattern (IBAN, account number) → L4, which is not in
      `ASSIGNABLE_SCOPES`, so it is withheld for a person to place;
    - a department whose vocabulary wins by at least `CONFIDENT` → L3 with that
      department, which is the **only** path that auto-approves;
    - anything weak or unrecognised → L5 with a confidence below the threshold,
      so it goes to review.

    Until this call existed the input was hardcoded to `classifier_failed=True`
    and every chunk withheld, which was I4 behaving correctly and also meant
    `chunks_indexed` was structurally always zero — a review queue holding
    100% of every upload is a queue nobody can work through. The rules and
    their calibration set were written for this call site and had no caller;
    `tests/test_classifier_calibration.py` prints the precision and recall this
    is trusting, and ADR 0051 records what those numbers do and do not support.
    """
    return [
        (chunk, classify_chunk(propose(chunk.text), uploader_id=str(scope.user_id)))
        for chunk in chunks
    ]


_INSERT_DOCUMENT = text(
    "INSERT INTO document"
    " (id, workspace_id, uploaded_by_user_id, filename, content_type, size_bytes,"
    "  storage_key, content_sha256, status, consent_given_at, consent_text_version,"
    "  failure_reason, page_count, supersedes_id)"
    " VALUES (:id, :ws, :user, :filename, :content_type, :size, :key, :digest,"
    "         :status, :consent_at, :consent_version, :failure, :pages, :supersedes)"
)

_INSERT_CHUNK = text(
    "INSERT INTO chunk"
    " (workspace_id, document_id, source_page, source_label, ordinal, content,"
    "  token_estimate, scope, department, owner_user_id, sensitivity,"
    "  classified_by, confidence, review_state)"
    " VALUES (:ws, :doc, :page, :label, :ordinal, :content, :tokens, :scope,"
    "         :department, :owner, :sensitivity, :classified_by, :confidence, :review)"
)


async def _record(
    *,
    document_id: UUID,
    scope: ScopedSession,
    filename: str,
    content_type: str | None,
    size_bytes: int,
    storage_key: str,
    digest: str,
    state: DocumentStatus,
    failure_reason: str | None,
    page_count: int | None,
    supersedes_id: UUID | None,
    chunks: list[tuple[Chunk, Classification]] | None = None,
) -> None:
    """Write the document and its chunks in one transaction, under RLS.

    Through `scoped_connection`, the architecture's mandatory path for customer
    data, which until now had no production caller. That matters beyond
    convention here: the GUCs it sets are what the WITH CHECK half of the
    isolation policy reads, so a bug aiming these rows at another workspace is
    refused by Postgres rather than by our own care.

    One transaction covers the document and every chunk. A partial write would
    leave a document claiming to be `indexed` with only part of its content
    reachable - the silent-failure shape doc 07 M5 forbids.
    """
    consent_at = datetime.now(UTC) if state is DocumentStatus.INDEXED else None

    async with scoped_connection(scope) as session:
        await session.execute(
            _INSERT_DOCUMENT,
            {
                "id": str(document_id),
                "ws": str(scope.workspace_id),
                "user": str(scope.user_id),
                "filename": filename,
                "content_type": content_type or "application/octet-stream",
                "size": size_bytes,
                "key": storage_key,
                "digest": digest,
                "status": state.value,
                # Only on the indexed path. The check constraint requires it
                # there, and a failed upload was never indexed, so recording
                # consent for it would overstate what happened.
                "consent_at": consent_at,
                "consent_version": CONSENT_TEXT_VERSION if consent_at else None,
                "failure": failure_reason,
                "pages": page_count,
                "supersedes": str(supersedes_id) if supersedes_id else None,
            },
        )

        for chunk, classification in chunks or []:
            await session.execute(
                _INSERT_CHUNK,
                {
                    "ws": str(scope.workspace_id),
                    "doc": str(document_id),
                    "page": chunk.page_number,
                    "label": chunk.page_label,
                    "ordinal": chunk.ordinal,
                    "content": chunk.text,
                    "tokens": max(1, (chunk.char_end - chunk.char_start) // 4),
                    "scope": scope_code(classification.scope),
                    "department": (
                        [classification.department.value] if classification.department else []
                    ),
                    "owner": classification.owner_user_id,
                    "sensitivity": classification.sensitivity.value,
                    "classified_by": classification.classified_by,
                    "confidence": classification.confidence,
                    "review": review_state_code(classification.review_state),
                },
            )

        await audit.record(
            session,
            workspace_id=scope.workspace_id,
            action=audit.AuditAction.DOCUMENT_UPLOADED,
            actor_user_id=scope.user_id,
            target_type="document",
            target_id=str(document_id),
        )

        if supersedes_id is not None:
            # Doc 06 s6 - a superseded document does not hand its scope to its
            # replacement. The replacement was classified from scratch above;
            # this only retires the old one, so its chunks stop being reachable
            # while the row survives for provenance.
            await session.execute(
                text(
                    "UPDATE document SET status = :superseded"
                    " WHERE id = :old AND workspace_id = :ws"
                ),
                {
                    "superseded": DocumentStatus.SUPERSEDED.value,
                    "old": str(supersedes_id),
                    "ws": str(scope.workspace_id),
                },
            )


# ── The review queue (task 5.8) ───────────────────────────────


class ReviewItem(BaseModel):
    chunk_id: UUID
    document_id: UUID
    filename: str
    source_page: int | None
    source_label: str | None
    excerpt: str
    scope: str
    sensitivity: str
    confidence: float
    classified_by: str


class ReviewQueue(BaseModel):
    items: list[ReviewItem]
    total: int
    """Total pending, which may exceed the returned list — this is paged."""


DOWNLOAD_TTL_SECONDS: Final = 300
"""Five minutes. Long enough to click, short enough that a link pasted into a
chat is dead before anyone else opens it."""


@router.get("", response_model=list[DocumentSummary])
async def list_documents(
    scope: CurrentScope, limit: Annotated[int, Query(ge=1, le=200)] = 100
) -> list[DocumentSummary]:
    """The caller's own uploads, newest first.

    **Own uploads, not the workspace's.** RLS makes `document` workspace-wide
    and that is right for the row — the storage quota is shared, so the bytes
    are everyone's business. The *filename* is not: "Salary review 2026.xlsx"
    names its own contents, and listing it to the whole company would leak
    precisely what chunk-level withholding (I4, L5 uploader-only) exists to
    protect. `chunks_held_for_review` is a personal count in the same way.

    A reviewer still sees what has been **proposed** for workspace visibility,
    through `/documents/review-queue`, which is the surface built for that. This
    route is "what have I given NEXUS", not "what does the company hold".
    """
    async with scoped_connection(scope) as db:
        rows = (
            await db.execute(
                text(
                    "SELECT d.id, d.filename, d.status, d.page_count, d.failure_reason,"
                    "       d.created_at,"
                    "       (SELECT count(*) FROM chunk c"
                    "         WHERE c.document_id = d.id AND c.review_state = :pending)"
                    "         AS held"
                    "  FROM document d"
                    " WHERE d.uploaded_by_user_id = :user"
                    " ORDER BY d.created_at DESC"
                    " LIMIT :n"
                ),
                {
                    "user": str(scope.user_id),
                    "pending": ReviewState.PENDING_REVIEW.value,
                    "n": limit,
                },
            )
        ).all()

    return [
        DocumentSummary(
            document_id=row.id,
            filename=row.filename,
            status=row.status,
            page_count=row.page_count,
            failure_reason=row.failure_reason,
            created_at=row.created_at,
            chunks_held_for_review=int(row.held),
        )
        for row in rows
    ]


class DocumentAskOut(BaseModel):
    name: str
    unlocks: str


class DepartmentAsksOut(BaseModel):
    department: str
    asks: list[DocumentAskOut]


class ConsentOut(BaseModel):
    text: str
    version: str


class UploadStageOut(BaseModel):
    """Everything the upload stage renders, in one response.

    The consent wording travels **with** its version because the version alone
    means nothing: "they consented" is only a defensible claim if we can say
    what they consented to, and the screen has to show the same words the
    document row records.

    The limits come too, so the client can say "this file is over 25 MB" before
    a founder waits for an upload to be refused. Predicting is not enforcing —
    the server checks again, from the same numbers.
    """

    consent: ConsentOut
    departments: list[DepartmentAsksOut]
    max_file_bytes: int
    max_files_at_onboarding: int
    workspace_quota_bytes: int
    bytes_used: int
    files_uploaded: int


@router.get("/asks", response_model=UploadStageOut)
async def document_asks(scope: CurrentScope, usage: Usage) -> UploadStageOut:
    """Three named documents per department this company runs (Q35).

    Declared **before** `/{document_id}/download` in this module because
    FastAPI matches routes in definition order and `asks` is a valid UUID-shaped
    path segment as far as the router is concerned — the reverse order gives a
    422 about a malformed UUID for a route that has nothing to do with one.

    Served from the selected departments rather than all seven: asking a company
    with no finance function for its chart of accounts is the same mistake as
    showing it a Finance dashboard.
    """
    async with _unscoped_session() as db:
        chosen = await selected_departments(db, workspace_id=scope.workspace_id)

    return UploadStageOut(
        consent=ConsentOut(text=CONSENT_WARRANTY, version=CONSENT_TEXT_VERSION),
        departments=[
            DepartmentAsksOut(
                department=department.value,
                asks=[DocumentAskOut(name=a.name, unlocks=a.unlocks) for a in asks],
            )
            for department, asks in asks_for(chosen).items()
        ],
        max_file_bytes=MAX_FILE_BYTES,
        max_files_at_onboarding=MAX_FILES_AT_ONBOARDING,
        workspace_quota_bytes=WORKSPACE_QUOTA_BYTES,
        bytes_used=usage.bytes_used,
        files_uploaded=usage.files,
    )


@router.get("/{document_id}/download", response_model=DownloadOut)
async def download_document(
    document_id: UUID,
    scope: CurrentScope,
    settings: Annotated[Settings, Depends(get_settings)],
) -> DownloadOut:
    """A short-lived signed URL for a document the caller uploaded.

    The URL is minted rather than the bytes streamed, because the same contract
    holds against S3 in production — `FilesystemObjectStore` exists to behave
    like the thing it will be replaced by, including the expiry.

    Authorised **here**, once, against the uploader. The signature that follows
    proves the URL was issued by us and has not expired; it says nothing about
    who is holding it, and treating possession as authorisation is how a link
    pasted into a group chat becomes an access-control decision.
    """
    async with scoped_connection(scope) as db:
        row = (
            await db.execute(
                text(
                    "SELECT storage_key FROM document"
                    " WHERE id = :id AND uploaded_by_user_id = :user"
                ),
                {"id": str(document_id), "user": str(scope.user_id)},
            )
        ).first()

    # 404 rather than 403 for a document that exists and is not the caller's:
    # "this exists and you may not have it" is itself a disclosure, and the
    # neighbouring routes already answer that way.
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such document.")

    return DownloadOut(
        url=_object_store(settings).signed_url(row.storage_key, ttl_seconds=DOWNLOAD_TTL_SECONDS),
        expires_in_seconds=DOWNLOAD_TTL_SECONDS,
    )


@router.get("/review-queue", response_model=ReviewQueue)
async def review_queue(scope: CurrentScope, limit: int = 50) -> ReviewQueue:
    """Chunks withheld from the workspace, awaiting a human.

    Reached only through `scoped_connection`, so rows are filtered to the
    caller's workspace by the database rather than by this query. The WHERE
    clause narrows *within* that; it is not what provides the isolation.

    The excerpt is truncated deliberately. A reviewer needs enough to judge the
    classification, not the whole document — and this endpoint returns content
    withheld precisely because nobody has yet decided who may see it.

    **Gated on `may_administer`, exactly as `audit.py` gates its own surface.**
    These excerpts exist specifically because they were classified PERSONAL or
    RESTRICTED — salary, passport, IBAN. Without this check any workspace member
    could read the withheld content whose whole point is that nobody has yet
    decided who may see it.
    """
    if not may_administer(scope.role):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "The review queue is available to owners and executives.",
        )

    limit = max(1, min(limit, 200))

    async with scoped_connection(scope) as session:
        rows = (
            (
                await session.execute(
                    text(
                        "SELECT c.id, c.document_id, d.filename, c.source_page,"
                        "       c.source_label, left(c.content, 400) AS excerpt,"
                        "       c.scope, c.sensitivity, c.confidence, c.classified_by"
                        "  FROM chunk c JOIN document d ON d.id = c.document_id"
                        "  WHERE c.review_state = :pending"
                        "  ORDER BY c.created_at DESC"
                        "  LIMIT :limit"
                    ),
                    {"limit": limit, "pending": review_state_code(ReviewState.PENDING_REVIEW)},
                )
            )
            .mappings()
            .all()
        )

        total = (
            await session.execute(
                text("SELECT count(*) FROM chunk WHERE review_state = :pending"),
                {"pending": review_state_code(ReviewState.PENDING_REVIEW)},
            )
        ).scalar_one()

    return ReviewQueue(
        items=[
            ReviewItem(
                chunk_id=r["id"],
                document_id=r["document_id"],
                filename=r["filename"],
                source_page=r["source_page"],
                source_label=r["source_label"],
                excerpt=r["excerpt"],
                scope=r["scope"],
                sensitivity=r["sensitivity"],
                confidence=r["confidence"],
                classified_by=r["classified_by"],
            )
            for r in rows
        ],
        total=int(total),
    )


class ReviewDecision(BaseModel):
    approve: bool
    scope: str | None = None
    """Where the chunk should sit if approved. Omitted leaves it at L5."""


@router.post(
    "/review-queue/{chunk_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_csrf)],
)
async def decide_review(
    chunk_id: UUID,
    decision: ReviewDecision,
    scope: CurrentScope,
) -> Response:
    """Approve or reject a withheld chunk.

    Doc 07 M5 task 5.8: a chunk marked `personal` or `restricted` needs human
    confirmation before anyone else can reach it.

    **Gated on `may_administer`, matching `setup.py`'s `ensure_may_answer`.**
    `may_reach_scope` alone is not enough: a Viewer's `max_scope` is L2, so a
    Viewer passes `may_reach_scope(L2)` and could approve a PERSONAL chunk
    straight to company-wide visibility. Reviewing withheld content is workspace
    administration, not merely reaching a scope, so it needs the same coarse
    gate as the rest of setup.

    The reviewer must also hold the authority for the scope they are granting,
    and `may_reach_scope` decides that rather than this handler. Without that
    second check the queue becomes a privilege-escalation route: withhold a
    chunk to L5, then promote it to L2 from an account that cannot read L2 at
    all.
    """
    if not may_administer(scope.role):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Reviewing withheld content is available to owners and executives.",
        )

    target = _parse_scope(decision.scope) if decision.approve and decision.scope else None

    if target is not None and not scope.may_reach_scope(target):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "You cannot approve a chunk into a scope you do not have access to.",
        )

    async with scoped_connection(scope) as session:
        # **L3 needs a department, and this is the second place that rule has to
        # hold.** `classify_chunk` already refuses to *classify* a chunk as L3
        # with no department, on the grounds that it is "a low-information
        # answer wearing a high-confidence number". Approving one here reached
        # the same state by another road, and the consequence is worse than the
        # docstring there feared: `retrieval/chunks.py`'s predicate matches L3
        # with `department && :depts`, and an empty array overlaps nothing — so
        # the chunk becomes readable by **nobody**, including the reviewer who
        # just published it, and the API said 204.
        #
        # Found by driving `chunks.search` against real data for the first time
        # (H1) and getting zero rows back for a chunk that had been approved.
        if target is Scope.L3_DEPARTMENT:
            placed = (
                await session.execute(
                    text(
                        "SELECT coalesce(array_length(department, 1), 0) AS n"
                        "  FROM chunk WHERE id = :id"
                    ),
                    {"id": str(chunk_id)},
                )
            ).scalar()
            if not placed:
                raise HTTPException(
                    status.HTTP_409_CONFLICT,
                    "This passage has no department, so it cannot be approved to one — "
                    "it would be readable by nobody. Keep it private instead.",
                )

        result: CursorResult[Any] = await session.execute(  # type: ignore[assignment]
            text(
                "UPDATE chunk"
                "   SET review_state = :state,"
                "       scope = COALESCE(:scope, scope),"
                "       reviewed_by_user_id = :reviewer,"
                "       reviewed_at = now()"
                " WHERE id = :id AND review_state = :pending"
            ),
            {
                "pending": review_state_code(ReviewState.PENDING_REVIEW),
                "state": review_state_code(
                    ReviewState.APPROVED if decision.approve else ReviewState.REJECTED
                ),
                "scope": scope_code(target) if target else None,
                "reviewer": str(scope.user_id),
                "id": str(chunk_id),
            },
        )

        # Inside the same transaction and the same scoped session as the
        # decision, so a logged review is a review that happened. Skipped when
        # nothing was updated — a 404 below is "no such chunk", and logging it
        # would fill the trail with rows for actions that did not occur.
        if result.rowcount:
            await audit.record(
                session,
                workspace_id=scope.workspace_id,
                action=audit.AuditAction.REVIEW_DECISION,
                actor_user_id=scope.user_id,
                target_type="chunk",
                target_id=str(chunk_id),
                reason=(
                    f"approved into {scope_code(target)}"
                    if decision.approve and target
                    else ("approved" if decision.approve else "rejected")
                ),
            )

    if result.rowcount == 0:
        # Does not exist, belongs to another workspace (RLS made it invisible),
        # or was already decided. All three are 404: telling them apart would
        # confirm the existence of a chunk the caller cannot see.
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such chunk awaiting review.")

    log.info("chunk.reviewed", approved=decision.approve)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _parse_scope(raw: str) -> Scope:
    for member in Scope:
        if member.name.split("_")[0].lower() == raw.strip().lower():
            return member
    raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Unknown scope {raw!r}.")
