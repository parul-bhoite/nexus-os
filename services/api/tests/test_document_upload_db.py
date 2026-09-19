"""The document upload path, against a real database.

`test_document_upload.py` proves the route's *decisions* — consent required,
failure surfaced, classification withheld — over a substituted `_record`. That
was a deliberate split, and it left a gap: twelve tests passed over a write path
that had never once touched Postgres. Both of Phase 1's certain runtime failures
lived in that gap. Every chunk INSERT violated `ck_chunk_review_state`, because
`ReviewState.NEEDS_REVIEW` is not one of the four values the column permits, and
the supersede UPDATE violated `ck_document_status`.

So this module writes for real. `_record` is **not** patched, the object store is
**not** patched, and the caller authenticates with a real session cookie against
a real `user_session` row, so `current_scope` resolves the way it does in
production and every write passes through row-level security.

What is seeded rather than driven: the tenant, user, workspace, membership and
session. Creating a workspace through the application needs a verified domain
claim, which needs a DNS or HTTP challenge to be answered — that is Phase 5's
UI and Phase 9's full-journey test (C3, C4). The subject here is the document
write path, and it is genuinely exercised end to end.
"""

from __future__ import annotations

import io
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy import Connection, Engine, create_engine

from app.auth.csrf import CSRF_COOKIE_NAME, CSRF_HEADER_NAME
from app.auth.tokens import hash_token, new_token
from app.config import get_settings
from app.db import get_engine, get_sessionmaker
from app.documents.classify import ReviewState
from app.main import create_app
from tests.dburl import async_database_url, database_url

DB_URL = database_url()
ASYNC_DB_URL = async_database_url()

# The real marker, declared in pyproject.toml. See the note in conftest.py.
requires_db = pytest.mark.requires_db

pytestmark = requires_db

CSRF = "a-known-csrf-value"
SIGNING_SECRET = "upload-db-test-signing-secret"


@dataclass(frozen=True, slots=True)
class Seed:
    tenant_id: UUID
    user_id: UUID
    workspace_id: UUID
    session_token: str


@pytest.fixture(scope="module")
def engine() -> Iterator[Engine]:
    # `requires_db` guarantees a database, so a missing URL here is a broken
    # harness rather than an absent one. Assert loudly instead of skipping.
    assert DB_URL is not None
    eng = create_engine(DB_URL, poolclass=sa.pool.NullPool)
    yield eng
    eng.dispose()


def _set_scope(conn: Connection, *, workspace: UUID | None, user: UUID | None) -> None:
    """Set the GUCs the isolation policies read, session-wide.

    Session-wide rather than transaction-local (`false`, not `true`) because
    this connection commits: seeded rows have to be visible to the
    application's own connection, so they cannot live in a transaction that is
    rolled back.
    """
    conn.execute(
        sa.text(
            "SELECT set_config('nexus.workspace_id', :ws, false),"
            "       set_config('nexus.user_id', :uid, false)"
        ),
        {"ws": str(workspace) if workspace else "", "uid": str(user) if user else ""},
    )


@pytest.fixture
def seeded(engine: Engine) -> Iterator[Seed]:
    """A committed tenant, user, workspace, membership and live session."""
    seed = Seed(uuid4(), uuid4(), uuid4(), new_token())

    with engine.connect() as conn:
        _set_scope(conn, workspace=seed.workspace_id, user=seed.user_id)
        conn.execute(
            sa.text("INSERT INTO tenant (id, name) VALUES (:t, 'Upload DB Test')"),
            {"t": str(seed.tenant_id)},
        )
        conn.execute(
            sa.text("INSERT INTO app_user (id, email) VALUES (:u, :e)"),
            {"u": str(seed.user_id), "e": f"upload-{seed.user_id}@example.invalid"},
        )
        conn.execute(
            sa.text(
                "INSERT INTO workspace (id, workspace_id, tenant_id, name)"
                " VALUES (:id, :id, :t, 'Upload DB Test')"
            ),
            {"id": str(seed.workspace_id), "t": str(seed.tenant_id)},
        )
        conn.execute(
            sa.text(
                "INSERT INTO membership (workspace_id, user_id, role, departments)"
                " VALUES (:ws, :u, 'owner', ARRAY['finance'])"
            ),
            {"ws": str(seed.workspace_id), "u": str(seed.user_id)},
        )
        conn.execute(
            sa.text(
                "INSERT INTO user_session"
                " (user_id, token_hash, expires_at, active_workspace_id, user_agent)"
                " VALUES (:u, :h, now() + interval '1 hour', :ws, 'pytest')"
            ),
            {
                "u": str(seed.user_id),
                "h": hash_token(seed.session_token),
                "ws": str(seed.workspace_id),
            },
        )
        conn.commit()

    yield seed

    # Torn down in dependency order, with the GUCs still set: DELETE is subject
    # to the same policy as INSERT.
    with engine.connect() as conn:
        _set_scope(conn, workspace=seed.workspace_id, user=seed.user_id)
        for statement, params in (
            ("DELETE FROM chunk WHERE workspace_id = :ws", {"ws": str(seed.workspace_id)}),
            ("DELETE FROM document WHERE workspace_id = :ws", {"ws": str(seed.workspace_id)}),
            ("DELETE FROM membership WHERE workspace_id = :ws", {"ws": str(seed.workspace_id)}),
            ("DELETE FROM workspace WHERE id = :ws", {"ws": str(seed.workspace_id)}),
            ("DELETE FROM user_session WHERE user_id = :u", {"u": str(seed.user_id)}),
            ("DELETE FROM app_user WHERE id = :u", {"u": str(seed.user_id)}),
            ("DELETE FROM tenant WHERE id = :t", {"t": str(seed.tenant_id)}),
        ):
            conn.execute(sa.text(statement), params)
        conn.commit()


@pytest.fixture
def client(seeded: Seed, monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[TestClient, Seed]]:
    """A client authenticated as the seeded owner, writing to the real database.

    `conftest` pins the URL and the signing secret to empty so no test depends
    on machine state by accident, so opting back in is explicit — and has to use
    the asyncpg spelling, because this exercises `app/` on the app's own driver.

    The engine is disposed by the application's own `lifespan` shutdown, which
    `TestClient.__exit__` runs — so it happens on the loop that opened the
    connections. Disposing from the fixture instead left asyncpg transports to
    be collected on a closed loop, and `filterwarnings = ["error"]` turned the
    resulting `PytestUnraisableExceptionWarning` into a failure of whichever
    test happened to be running next.
    """
    assert ASYNC_DB_URL is not None
    monkeypatch.setenv("NEXUS_DATABASE_URL", ASYNC_DB_URL)
    monkeypatch.setenv("NEXUS_STORAGE_SIGNING_SECRET", SIGNING_SECRET)
    for cache in (get_settings, get_engine, get_sessionmaker):
        cache.cache_clear()

    app = create_app()
    try:
        with TestClient(app) as c:
            c.cookies.set("nexus_session", seeded.session_token)
            c.cookies.set(CSRF_COOKIE_NAME, CSRF)
            yield c, seeded
    finally:
        for cache in (get_settings, get_engine, get_sessionmaker):
            cache.cache_clear()


def _upload(
    client: TestClient,
    *,
    content: bytes = b"Payroll register. Salaries by employee, monthly.",
    filename: str = "payroll.txt",
    supersedes_id: UUID | None = None,
) -> Any:
    data: dict[str, str] = {"consent": "true"}
    if supersedes_id is not None:
        data["supersedes_id"] = str(supersedes_id)
    return client.post(
        "/documents",
        files={"file": (filename, io.BytesIO(content), "text/plain")},
        data=data,
        headers={CSRF_HEADER_NAME: CSRF},
    )


def _rows(engine: Engine, workspace_id: UUID, statement: str) -> list[Any]:
    with engine.connect() as conn:
        _set_scope(conn, workspace=workspace_id, user=None)
        return list(conn.execute(sa.text(statement), {"ws": str(workspace_id)}).mappings())


# ── The write actually reaches Postgres ───────────────────────


async def test_an_upload_writes_a_document_and_its_chunks(
    client: tuple[TestClient, Seed], engine: Engine
) -> None:
    """The test whose absence let two check-constraint violations reach `main`.

    Before migration 0010 this fails: every chunk carries
    `review_state = 'needs_review'`, which `ck_chunk_review_state` does not
    permit, so the whole transaction rolls back and the route 500s.
    """
    c, seed = client
    response = _upload(c)

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "indexed"

    documents = _rows(
        engine,
        seed.workspace_id,
        "SELECT id, status, consent_given_at FROM document WHERE workspace_id = :ws",
    )
    assert len(documents) == 1
    assert documents[0]["status"] == "indexed"
    assert documents[0]["consent_given_at"] is not None

    chunks = _rows(
        engine,
        seed.workspace_id,
        "SELECT scope, review_state, owner_user_id FROM chunk WHERE workspace_id = :ws",
    )
    assert chunks, "an indexed document with no chunk rows is a silent failure"
    assert body["chunks_held_for_review"] == len(chunks)


async def test_withheld_chunks_land_in_the_vocabulary_the_column_permits(
    client: tuple[TestClient, Seed], engine: Engine
) -> None:
    """`pending_review`, and it is the same string the queue and index filter on.

    The drift this pins down was not that one spelling was wrong. It was that
    the Python enum and the SQL constraint were two independent lists, so
    `ix_chunk_pending_review` and both review-queue queries selected a value
    nothing could ever write.
    """
    c, seed = client
    assert _upload(c).status_code == 201

    chunks = _rows(
        engine,
        seed.workspace_id,
        "SELECT scope, review_state, owner_user_id FROM chunk WHERE workspace_id = :ws",
    )
    for chunk in chunks:
        assert chunk["review_state"] == ReviewState.PENDING_REVIEW.value
        assert chunk["scope"] == "L5", "no classifier exists, so everything withholds (I4)"
        assert chunk["owner_user_id"] == seed.user_id, "L5 is uploader-only"


async def test_the_withheld_chunks_appear_in_the_review_queue(
    client: tuple[TestClient, Seed],
) -> None:
    """The other half of the same defect: a queue nothing could ever fill.

    This is the phase's acceptance test — an upload reaching Postgres and then
    being visible to the human who has to decide about it.
    """
    c, _ = client
    upload = _upload(c)
    assert upload.status_code == 201

    queue = c.get("/documents/review-queue")
    assert queue.status_code == 200, queue.text
    body = queue.json()

    assert body["total"] >= 1
    assert body["items"], "chunks were withheld but the queue is empty"
    assert body["items"][0]["filename"] == "payroll.txt"
    assert body["items"][0]["scope"] == "L5"


# ── Superseding (doc 06 §6, task 5.10) ────────────────────────


async def test_superseding_retires_the_earlier_document(
    client: tuple[TestClient, Seed], engine: Engine
) -> None:
    """Before migration 0010, `'superseded'` is not in `ck_document_status`.

    The status is what stops the old document's chunks being reachable, so the
    failure is not cosmetic: without it the replacement and the thing it
    replaced are both live.
    """
    c, seed = client
    first = _upload(c, content=b"Version one of the handbook.", filename="handbook.txt")
    assert first.status_code == 201
    first_id = UUID(first.json()["document_id"])

    second = _upload(
        c,
        content=b"Version two of the handbook, revised.",
        filename="handbook-v2.txt",
        supersedes_id=first_id,
    )
    assert second.status_code == 201, second.text

    statuses = {
        row["id"]: row["status"]
        for row in _rows(
            engine, seed.workspace_id, "SELECT id, status FROM document WHERE workspace_id = :ws"
        )
    }
    assert statuses[first_id] == "superseded"
    assert statuses[UUID(second.json()["document_id"])] == "indexed"


async def test_an_unreadable_file_is_recorded_but_not_reported_as_created(
    client: tuple[TestClient, Seed], engine: Engine
) -> None:
    """Finding F11. Keeping the file is right; calling it Created is not.

    An unsupported type is refused on the merits, and the row and the bytes are
    deliberately kept — a file we could not parse is still the customer's file,
    and discarding it because our parser failed loses something they believe
    they gave us. What was wrong was the status line: `201 Created` with the
    refusal buried in the body, so a client checking the status alone read a
    rejected `.exe` as accepted.

    422 rather than 400, because the request was well formed and every guard
    above it passed — no consent is a 400 and over the cap is a 413, and both
    of those were already right. What failed here is the content.
    """
    c, seed = client
    response = _upload(c, content=b"MZ\x90\x00 not a document", filename="evil.exe")

    assert response.status_code == 422, response.text

    # The body is unchanged: the id and the reason are what a client needs in
    # order to tell somebody what happened.
    body = response.json()
    assert body["status"] == "failed"
    assert body["chunks_indexed"] == 0
    assert body["message"], "the refusal carries no reason"

    # And it really is on record, quarantined rather than dropped.
    documents = _rows(
        engine,
        seed.workspace_id,
        "SELECT filename, status FROM document WHERE workspace_id = :ws",
    )
    assert len(documents) == 1
    assert documents[0]["filename"] == "evil.exe"
    assert documents[0]["status"] == "quarantined"


# ── L3 needs a department, on both roads into it ──────────────


async def test_approving_to_a_department_the_chunk_does_not_have_is_refused(
    client: tuple[TestClient, Seed], engine: Engine
) -> None:
    """The gap between the two ways a chunk becomes L3.

    `classify_chunk` refuses to *classify* something L3 with no department — "a
    low-information answer wearing a high-confidence number". The review queue
    reached the same state by another road and nobody had closed it, because
    `decide_review` only ever set `scope`.

    **The consequence is worse than being over-shared.**
    `retrieval/chunks.py`'s predicate matches L3 on `department && :depts`, and
    an empty array overlaps nothing — so the chunk becomes readable by *nobody*,
    including the reviewer who just published it, and the API answered 204.
    Found by running `chunks.search` against real data for the first time and
    getting no rows for a chunk that had been approved.
    """
    c, seed = client
    assert _upload(c).status_code == 201

    queue = c.get("/documents/review-queue").json()
    assert queue["items"], "the payroll fixture must withhold something to review"
    chunk_id = queue["items"][0]["chunk_id"]

    # The fixture is personal-pattern material, so the classifier named no
    # department. Approving it *to* a department is the move under test.
    placed = _rows(
        engine,
        seed.workspace_id,
        "SELECT coalesce(array_length(department, 1), 0) AS n FROM chunk WHERE workspace_id = :ws",
    )
    assert all(row["n"] == 0 for row in placed), "fixture assumption: no department was identified"

    refused = c.post(
        f"/documents/review-queue/{chunk_id}",
        json={"approve": True, "scope": "l3"},
        headers={CSRF_HEADER_NAME: CSRF},
    )

    assert refused.status_code == 409, refused.text
    assert "readable by nobody" in refused.json()["detail"]

    # And nothing moved: a refusal that had already written would be worse than
    # the bug, because the reviewer would be told no and the row would say yes.
    after = _rows(
        engine,
        seed.workspace_id,
        "SELECT scope, review_state FROM chunk WHERE workspace_id = :ws",
    )
    assert all(row["review_state"] == ReviewState.PENDING_REVIEW.value for row in after)
    assert all(row["scope"] == "L5" for row in after)


async def test_keeping_it_private_is_still_allowed_for_the_same_chunk(
    client: tuple[TestClient, Seed],
) -> None:
    """The refusal above must not strand the reviewer.

    Approving with no scope leaves the chunk where it is and marks it decided,
    which is the honest outcome for material that has no department to go to —
    and it is the option the queue offers beside the one that is refused.
    """
    c, _ = client
    assert _upload(c).status_code == 201
    chunk_id = c.get("/documents/review-queue").json()["items"][0]["chunk_id"]

    kept = c.post(
        f"/documents/review-queue/{chunk_id}",
        json={"approve": True},
        headers={CSRF_HEADER_NAME: CSRF},
    )

    assert kept.status_code == 204, kept.text
