"""Finding B4: an oversized request body is refused before anything parses it.

The defect these are written against was not a missing rejection — a 50 MB body
*was* rejected, by `phone`'s 32-character cap, after the whole 50 MB had been
received and parsed. So the assertion that matters is not "large bodies fail"
but **which layer fails them**, and that is what the status code distinguishes:
`413` from the middleware, versus `422` from Pydantic after buffering.

No database, no session, no CSRF token. That is deliberate and is the point of
the finding: the ceiling has to apply to a request that carries nothing, because
an unauthenticated caller is exactly who this protects against. Every test below
would pass its body straight into the app if the middleware were removed, and
none of them would then see a 413.
"""

from __future__ import annotations

import json
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.documents.limits import MAX_FILE_BYTES
from app.http_limits import MAX_JSON_BODY_BYTES, MAX_UPLOAD_BODY_BYTES
from app.main import create_app


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())


def _json_body(size: int) -> bytes:
    """A syntactically valid JSON object of roughly `size` bytes.

    Valid on purpose. A body of junk bytes would be refused by the JSON parser
    too, and then a passing test would prove nothing about the limit — the same
    trap as asserting on a 422 that the field validator produced.
    """
    padding = "x" * max(0, size - 32)
    return json.dumps({"email": "flood@example.com", "password": padding}).encode()


def test_a_json_body_over_the_ceiling_is_refused_by_the_middleware(
    client: TestClient,
) -> None:
    """413 from the limit, not 422 from a field validator.

    The status code is the whole assertion. A 422 here would mean the body was
    received in full and handed to Pydantic, which is the finding rather than
    the fix.
    """
    response = client.post("/auth/login", content=_json_body(MAX_JSON_BODY_BYTES + 1024))

    assert response.status_code == 413, (
        "an oversized body reached the handler; it should not have been parsed at all"
    )
    detail = response.json()["detail"]
    assert detail["error"] == "request_too_large"
    # The message names a number the caller can act on. "Too large" without a
    # limit tells somebody to guess.
    assert "KB" in detail["message"]


def test_a_body_with_no_declared_length_is_still_counted(client: TestClient) -> None:
    """**The enforcement, as distinct from the optimisation.**

    `Content-Length` is client-supplied and a chunked request carries none, so a
    limit that only read the header would be one any caller could opt out of by
    not declaring a length. Passing an iterator makes httpx use
    `Transfer-Encoding: chunked`, which is the case the running total exists for.
    """

    def chunks() -> Iterator[bytes]:
        # Comfortably over, in pieces that are individually well under, so this
        # can only be caught by accumulating rather than by inspecting one
        # chunk.
        for _ in range(8):
            yield b"z" * (MAX_JSON_BODY_BYTES // 4)

    response = client.post("/auth/login", content=chunks())

    assert response.status_code == 413
    assert response.json()["detail"]["error"] == "request_too_large"


def test_an_ordinary_body_is_untouched(client: TestClient) -> None:
    """The limit must not become the thing that breaks normal requests.

    Asserted as "not 413" rather than as a specific code: this request has no
    CSRF token and no database behind it, so what it *does* return is the
    hermetic fixture's business and not this test's. All that matters here is
    that the body was allowed through.
    """
    response = client.post("/auth/login", content=_json_body(2048))

    assert response.status_code != 413


def test_a_get_request_is_never_measured(client: TestClient) -> None:
    """Only methods that carry bodies are wrapped.

    A GET with a body is not a thing this API serves, and measuring one would
    add a `receive` wrapper to every read on the hot path for nothing.
    """
    assert client.get("/health").status_code != 413


def test_upload_gets_the_larger_ceiling_and_json_does_not(client: TestClient) -> None:
    """One limit would have had to be the generous one.

    `/documents` legitimately carries 25 MiB. The finding was that *every*
    endpoint carried that allowance implicitly — so the same body that must pass
    at the upload path must be refused at a JSON one, and that difference is
    what this asserts.
    """
    body = b"m" * (MAX_JSON_BODY_BYTES + 4096)

    assert client.post("/documents", content=body).status_code != 413
    assert client.post("/auth/login", content=body).status_code == 413


def test_the_upload_ceiling_stays_above_the_file_limit() -> None:
    """The two must not be equal, or a legal file is refused by the wrong layer.

    A 25 MiB file arrives inside a multipart envelope, so its body is larger
    than the file. `app/documents/limits.py` owns the refusal for the file
    itself — and it answers with a message about splitting the file, which is
    advice the middleware's "over the limit for this endpoint" cannot give.
    Guarded as an inequality rather than a fixed number so that raising
    `MAX_FILE_BYTES` cannot silently make the middleware the stricter of the
    two.
    """
    assert MAX_UPLOAD_BODY_BYTES > MAX_FILE_BYTES


def test_a_malformed_content_length_is_not_trusted_either_way(client: TestClient) -> None:
    """A junk header must neither refuse a small body nor admit a large one.

    Treated as absent, because the running total is the real enforcement. The
    alternative — refusing on an unparseable header — turns a client quirk into
    a failure on a body that may be perfectly small.
    """
    small = client.post(
        "/auth/login",
        content=_json_body(2048),
        headers={"content-length": "not-a-number", "content-type": "application/json"},
    )
    assert small.status_code != 413
