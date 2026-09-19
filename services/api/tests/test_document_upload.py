"""Upload, consent, visible failure, and the review gate.

Doc 07 M5's acceptance is *"a low-confidence document lands in L5 and the review
queue, and nothing is silently visible"*, and its validation step is *"upload a
payroll-like file; confirm it is not workspace-visible until reviewed."* These
are that, at the level the route actually decides things.

Hermetic: the storage write and the database write are substituted, because what
is under test is the route's decisions — consent required, failure surfaced,
classification withheld — not whether Postgres accepts an INSERT. The isolation
those writes rely on is proved separately, against a real database, in
`test_tenant_isolation.py`.
"""

from __future__ import annotations

import io
from collections.abc import Iterator
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.auth.csrf import CSRF_COOKIE_NAME, CSRF_HEADER_NAME
from app.deps import current_scope
from app.documents.classify import ReviewState
from app.domain.scopes import Department, Role, Scope
from app.domain.session import ScopedSession
from app.main import create_app
from app.routes.documents import WorkspaceUsage, workspace_usage

WORKSPACE = UUID("22222222-2222-2222-2222-222222222222")
USER = UUID("11111111-1111-1111-1111-111111111111")
CSRF = "a-known-csrf-value"


def scope_for(role: Role = Role.OWNER) -> ScopedSession:
    return ScopedSession(
        user_id=USER,
        workspace_id=WORKSPACE,
        tenant_id=uuid4(),
        role=role,
        departments=frozenset({Department.FINANCE}),
    )


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[TestClient, list[dict[str, Any]]]]:
    """A client whose writes are captured rather than performed.

    `recorded` receives one dict per `_record` call, which is the assertion
    surface: what status the document was given, and what scope and review state
    every chunk landed in.
    """
    recorded: list[dict[str, Any]] = []

    async def fake_record(**kwargs: Any) -> None:
        recorded.append(kwargs)

    class FakeStore:
        def put(self, key: str, data: bytes, *, content_type: str) -> None:
            return None

    monkeypatch.setattr("app.routes.documents._record", fake_record)
    monkeypatch.setattr("app.routes.documents._object_store", lambda settings: FakeStore())

    app = create_app()
    app.dependency_overrides[current_scope] = scope_for
    # An empty workspace. These tests assert what the route does with a parsed
    # file, not what the quota does — and reading usage from the database would
    # make every one of them need a database to answer a question none of them
    # asks. `tests/test_upload_limits.py` owns the limits.
    app.dependency_overrides[workspace_usage] = lambda: WorkspaceUsage(0, 0, True)

    with TestClient(app) as c:
        c.cookies.set(CSRF_COOKIE_NAME, CSRF)
        yield c, recorded

    app.dependency_overrides.clear()


def upload(
    client: TestClient,
    *,
    content: bytes = b"Payroll register. Salaries by employee.",
    filename: str = "payroll.txt",
    consent: str | None = "true",
) -> Any:
    data: dict[str, str] = {} if consent is None else {"consent": consent}
    return client.post(
        "/documents",
        files={"file": (filename, io.BytesIO(content), "text/plain")},
        data=data,
        headers={CSRF_HEADER_NAME: CSRF},
    )


# ── Consent is a precondition ─────────────────────────────────


def test_an_upload_without_consent_is_refused(client) -> None:  # type: ignore[no-untyped-def]
    """Doc 06 §5. The warranty is the control that makes indexing a competitor's
    leaked price list the customer's decision rather than ours."""
    c, recorded = client
    response = upload(c, consent="false")

    assert response.status_code == 400
    assert "right to use" in response.json()["detail"]
    assert recorded == [], "nothing may be written without consent"


def test_consent_must_be_supplied_not_assumed(client) -> None:  # type: ignore[no-untyped-def]
    """An upload that consents by virtue of being an upload is not a warranty
    anyone could rely on, so the field defaults to false rather than absent."""
    c, recorded = client
    assert upload(c, consent=None).status_code == 400
    assert recorded == []


def test_consent_is_recorded_with_the_wording_in_force(client) -> None:  # type: ignore[no-untyped-def]
    """ "They consented" means little without *what* they consented to."""
    from app.routes.documents import CONSENT_TEXT_VERSION, CONSENT_WARRANTY

    c, _ = client
    assert upload(c).status_code == 201
    assert CONSENT_TEXT_VERSION
    assert "right to use" in CONSENT_WARRANTY


# ── The acceptance criterion ──────────────────────────────────


def test_a_sensitive_document_is_not_workspace_visible_until_reviewed(client) -> None:  # type: ignore[no-untyped-def]
    """M5's stated validation, asserted rather than performed by hand.

    **This assertion got stronger without changing.** It used to hold for a
    weak reason — no classifier ran, so everything withheld and a test that
    uploaded a payroll register proved nothing about payroll registers. Since
    ADR 0051 wired `rules.propose` in, the fixture's "Payroll"/"Salaries" hits
    `PERSONAL_PATTERNS`, so the classifier now actively recognises the material
    as personal and the gate withholds it on `REQUIRES_HUMAN` — at confidence
    1.0, which is the case worth proving. See
    `test_a_confident_departmental_document_is_indexed_without_review` for the
    other side: withholding everything is only a safety property if something
    is ever released.
    """
    c, recorded = client
    response = upload(c)

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "indexed"
    assert body["chunks_indexed"] == 0, "nothing may be visible without a decision"
    assert body["chunks_held_for_review"] > 0

    chunks = recorded[0]["chunks"]
    assert chunks, "a readable document must produce chunks"
    for _, classification in chunks:
        assert classification.scope.name.startswith("L5"), "withheld chunks sit at L5"
        assert classification.review_state is ReviewState.PENDING_REVIEW
        assert classification.owner_user_id == str(USER), (
            "an L5 chunk with no owner is visible to nobody, or to everyone if a "
            "predicate treats NULL as a wildcard"
        )


def test_the_uploader_is_the_only_owner_of_a_withheld_chunk(client) -> None:  # type: ignore[no-untyped-def]
    c, recorded = client
    upload(c)

    owners = {cls.owner_user_id for _, cls in recorded[0]["chunks"]}
    assert owners == {str(USER)}


# ── The classifier is connected (ADR 0051) ───────────────────


def test_a_confident_departmental_document_is_indexed_without_review(client) -> None:  # type: ignore[no-untyped-def]
    """The half that was missing until `propose` was wired in.

    Every assertion above this line is about material being *withheld*, and all
    of them passed for a year while `_classify_all` hardcoded
    `classifier_failed=True` — because a product that indexes nothing withholds
    everything correctly. This is the test that would have failed, and the
    reason the wiring is observable rather than a refactor.

    Finance vocabulary, no personal or financial pattern: the one route through
    the gate that auto-approves.
    """
    c, recorded = client
    response = upload(
        c,
        content=b"Invoice ledger reconciliation. The receivable ageing and the payable ledger.",
        filename="ledger.txt",
    )

    assert response.status_code == 201
    body = response.json()
    assert body["chunks_indexed"] > 0, (
        "a confidently-departmental, non-sensitive document must reach the "
        "workspace without a human in the loop"
    )
    assert body["chunks_held_for_review"] == 0

    for _, classification in recorded[0]["chunks"]:
        assert classification.review_state is ReviewState.AUTO_APPROVED
        assert classification.scope is Scope.L3_DEPARTMENT
        assert classification.department is Department.FINANCE
        assert classification.owner_user_id is None, (
            "an auto-approved chunk belongs to the department, not the uploader"
        )


def test_a_bank_account_is_withheld_even_though_it_is_obviously_finance(client) -> None:  # type: ignore[no-untyped-def]
    """Confidence is not permission.

    The pattern match is certain — an IBAN is a fact about the characters — and
    that certainty is precisely why it must not auto-publish. This is the case
    where a naive classifier does the most damage, because it is *sure*.
    """
    c, recorded = client
    response = upload(
        c,
        content=b"Remit to account number GB29NWBK60161331926819 against the invoice ledger.",
        filename="remittance.txt",
    )

    assert response.status_code == 201
    assert response.json()["chunks_indexed"] == 0
    for _, classification in recorded[0]["chunks"]:
        assert classification.review_state is ReviewState.PENDING_REVIEW


# ── Failure is visible (task 5.9) ─────────────────────────────


def test_a_scan_with_no_text_layer_says_so(client) -> None:  # type: ignore[no-untyped-def]
    """The failure doc 07 M5 names explicitly.

    Silence here is worse than an error: the customer believes the document is
    searchable, and discovers otherwise when an answer omits it — which reads as
    the product being wrong rather than the upload having failed.
    """
    c, recorded = client
    # A PDF header with no extractable text is the shape a scan takes.
    response = upload(c, content=b"%PDF-1.4\n%empty\n", filename="scan.pdf")

    # 422, not 201 — finding F11. The row and the bytes are still kept, and the
    # message is still the point of the test; what changed is that the status
    # line no longer says "Created" about a document with nothing readable in
    # it. A client that checks the status alone was reading this as accepted.
    assert response.status_code == 422
    body = response.json()
    assert body["status"] == "failed"
    assert body["message"], "a failure must always carry a message"
    assert body["chunks_indexed"] == 0
    assert recorded[0]["failure_reason"], "the reason is persisted, not only returned"


def test_an_unsupported_type_is_quarantined_rather_than_failed(client) -> None:  # type: ignore[no-untyped-def]
    """Distinguished because they call for different actions: a corrupt file
    should be re-saved, an unsupported one converted."""
    c, recorded = client
    response = upload(c, content=b"\x00\x01\x02binary", filename="archive.zip")

    # Finding F11, as above: quarantining it is right, calling it Created was
    # not. The distinction this test exists for — quarantined rather than
    # failed — is unaffected and is still asserted below.
    assert response.status_code == 422
    assert response.json()["message"]
    assert recorded[0]["state"] == "quarantined"


def test_an_empty_file_is_refused_before_anything_is_stored(client) -> None:  # type: ignore[no-untyped-def]
    c, recorded = client
    assert upload(c, content=b"").status_code == 400
    assert recorded == []


def test_an_oversize_file_is_refused_with_its_limit(client) -> None:  # type: ignore[no-untyped-def]
    from app.documents.parse import MAX_FILE_BYTES

    c, recorded = client
    response = upload(c, content=b"x" * (MAX_FILE_BYTES + 1))

    assert response.status_code == 413
    assert "MB" in response.json()["detail"], "the limit must be stated, not implied"
    assert recorded == []


# ── Supersession re-classifies (task 5.10) ────────────────────


def test_a_replacement_is_classified_from_scratch(client) -> None:  # type: ignore[no-untyped-def]
    """Doc 06 §6 — a superseded document does not hand its scope to its
    replacement. Inheriting would let a document promoted to L2 by review launder
    that scope onto whatever replaced it, without anyone deciding again."""
    c, recorded = client
    old = uuid4()

    response = c.post(
        "/documents",
        files={"file": ("v2.txt", io.BytesIO(b"Updated payroll register."), "text/plain")},
        data={"consent": "true", "supersedes_id": str(old)},
        headers={CSRF_HEADER_NAME: CSRF},
    )

    assert response.status_code == 201
    assert recorded[0]["supersedes_id"] == old
    for _, classification in recorded[0]["chunks"]:
        assert classification.review_state is ReviewState.PENDING_REVIEW


# ── The route is guarded ──────────────────────────────────────


def test_upload_requires_csrf(client) -> None:  # type: ignore[no-untyped-def]
    c, recorded = client
    response = c.post(
        "/documents",
        files={"file": ("x.txt", io.BytesIO(b"hello"), "text/plain")},
        data={"consent": "true"},
    )

    assert response.status_code == 403
    assert recorded == []


def test_upload_requires_a_workspace_scope() -> None:
    """`CurrentScope`, not `CurrentSession`. Uploading writes workspace-scoped
    rows, so a caller without a workspace has nowhere to put them."""
    with TestClient(create_app()) as anonymous:
        anonymous.cookies.set(CSRF_COOKIE_NAME, CSRF)
        response = anonymous.post(
            "/documents",
            files={"file": ("x.txt", io.BytesIO(b"hello"), "text/plain")},
            data={"consent": "true"},
            headers={CSRF_HEADER_NAME: CSRF},
        )

    assert response.status_code in {401, 403}
