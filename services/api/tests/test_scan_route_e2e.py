"""`POST/GET/DELETE /public/scans`, driven through the application. G7.

Real database, real app, mocked transport and scripted DNS — the same
"exercised end to end, but the network is not the real internet" split
`test_crawler_redirects.py` and `test_document_upload_db.py` each use for
their own halves of that problem.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable, Iterator
from datetime import UTC, datetime
from uuid import uuid4

import httpx
import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from app.config import get_settings
from app.connectors.rate_limit import SCAN_PER_DOMAIN
from app.db import get_engine, get_sessionmaker
from app.main import create_app
from app.research import crawler
from app.research import ssrf as ssrf_module
from app.scan import client_address
from tests.dburl import async_database_url, database_url

DB_URL = database_url()
ASYNC_DB_URL = async_database_url()
requires_db = pytest.mark.requires_db
pytestmark = requires_db

PUBLIC_A = "93.184.216.34"

Handler = Callable[[httpx.Request], httpx.Response]
DnsSetter = Callable[[dict[str, list[str]]], None]

GOOD_HTML = """
<html><head><title>A title that is far too long to be useful for a listing</title>
<meta name="description" content="x"></head>
<body><h1>one</h1><h1>two</h1><h2>a</h2><p>Some short body text.</p></body></html>
"""


@pytest.fixture
async def app_db(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[None]:
    assert ASYNC_DB_URL is not None
    monkeypatch.setenv("NEXUS_DATABASE_URL", ASYNC_DB_URL)
    monkeypatch.setenv("NEXUS_STORAGE_SIGNING_SECRET", "scan-e2e-test-secret")
    for cache in (get_settings, get_engine, get_sessionmaker):
        cache.cache_clear()
    yield
    await get_engine().dispose()
    for cache in (get_settings, get_engine, get_sessionmaker):
        cache.cache_clear()


@pytest.fixture
def dns(monkeypatch: pytest.MonkeyPatch) -> DnsSetter:
    def set_map(mapping: dict[str, list[str]]) -> None:
        monkeypatch.setattr(
            ssrf_module,
            "_system_resolver",
            lambda host: list(mapping.get(host.lower(), [])),
        )

    return set_map


@pytest.fixture
def seen() -> list[httpx.Request]:
    return []


@pytest.fixture
def transport(
    monkeypatch: pytest.MonkeyPatch, seen: list[httpx.Request]
) -> Callable[[Handler], None]:
    def install(handler: Handler) -> None:
        def recording(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            return handler(request)

        def fake_client(timeout: float) -> httpx.AsyncClient:
            return httpx.AsyncClient(
                transport=httpx.MockTransport(recording),
                follow_redirects=False,
                timeout=httpx.Timeout(timeout),
                headers={"User-Agent": crawler.USER_AGENT},
            )

        monkeypatch.setattr(crawler, "_client", fake_client)

    return install


def html_response(status_code: int = 200) -> httpx.Response:
    return httpx.Response(status_code, headers={"content-type": "text/html"}, content=GOOD_HTML)


def robots_ok_then_page(request: httpx.Request) -> httpx.Response:
    """No robots.txt (404) on that path; the page itself otherwise."""
    if request.url.path == "/robots.txt":
        return httpx.Response(404)
    return html_response()


@pytest.fixture(autouse=True)
def unique_client_ip(monkeypatch: pytest.MonkeyPatch) -> None:
    """`TestClient`'s `request.client.host` is a fixed constant ("testclient"),
    so without this every test in this file — and every prior run of this
    same file within the same real wall-clock hour, since `SCAN_PER_IP`'s
    counter persists in Neon between runs — increments the *same* per-IP
    bucket. Found by running this file twice in a row: the second run's
    first test got a 429 that had nothing to do with what it was testing.
    A fresh synthetic address per test makes each test's rate-limit budget
    its own, the way a fresh domain already makes its per-domain budget its
    own.
    """
    monkeypatch.setattr(client_address, "client_ip", lambda request, settings: str(uuid4()))


@pytest.fixture
def client(app_db: None) -> Iterator[TestClient]:
    with TestClient(create_app()) as c:
        yield c


def test_the_full_lifecycle(
    client: TestClient,
    dns: DnsSetter,
    transport: Callable[[Handler], None],
    seen: list[httpx.Request],
) -> None:
    domain = f"e2e-{uuid4().hex[:12]}.example"
    dns({domain: [PUBLIC_A]})
    transport(robots_ok_then_page)

    # POST a fixture domain: 201, a body, a Location header.
    first = client.post("/public/scans", json={"url": f"https://{domain}/"})
    assert first.status_code == 201, first.text
    assert first.headers["location"] == f"/public/scans/{first.json()['id']}"
    body = first.json()
    assert body["domain"] == domain
    assert body["pages_read"] == 1
    assert body["js_rendered"] is False
    assert 0 < len(body["checks"]) <= 3
    scan_id = body["id"]

    requests_after_first = len(seen)
    assert requests_after_first > 0, "the first scan must have actually fetched something"

    # POST again: 200, the SAME id, and no second page fetch — asserted on
    # the fixture's own recorded request count, not by timing.
    second = client.post("/public/scans", json={"url": f"https://{domain}/"})
    assert second.status_code == 200, second.text
    assert second.json()["id"] == scan_id
    assert len(seen) == requests_after_first, "a cache hit must not touch the network at all"

    # DELETE: 204, idempotent.
    delete_once = client.delete(f"/public/scans/{scan_id}")
    assert delete_once.status_code == 204
    delete_twice = client.delete(f"/public/scans/{scan_id}")
    assert delete_twice.status_code == 204, "deleting an already-deleted id must not error"

    # GET after delete: 404 — not the oracle-revealing "410 Gone".
    after_delete = client.get(f"/public/scans/{scan_id}")
    assert after_delete.status_code == 404

    # GET an id that never existed: also 404, same code.
    unknown = client.get(f"/public/scans/{uuid4()}")
    assert unknown.status_code == 404

    # POST again for the same domain: the old row is deleted, so this is a
    # genuinely fresh crawl — 201, and a NEW id.
    third = client.post("/public/scans", json={"url": f"https://{domain}/"})
    assert third.status_code == 201, third.text
    assert third.json()["id"] != scan_id


def test_a_malformed_url_is_422(client: TestClient) -> None:
    response = client.post("/public/scans", json={"url": "not a url at all, just words"})
    assert response.status_code == 422


def test_an_ssrf_refused_target_is_422_not_500(
    client: TestClient, dns: DnsSetter, transport: Callable[[Handler], None]
) -> None:
    domain = f"e2e-{uuid4().hex[:12]}.example"
    dns({})  # does not resolve
    transport(robots_ok_then_page)

    response = client.post("/public/scans", json={"url": f"https://{domain}/"})
    assert response.status_code == 422
    assert domain not in response.json()["detail"]


def test_the_serialised_checks_payload_carries_no_raw_page_content(
    client: TestClient, dns: DnsSetter, transport: Callable[[Handler], None]
) -> None:
    """The `page_signals.py` precedent, applied here: computed observations
    only, never an email address, never a fragment of the page's own markup."""
    domain = f"e2e-{uuid4().hex[:12]}.example"
    dns({domain: [PUBLIC_A]})
    transport(robots_ok_then_page)

    response = client.post("/public/scans", json={"url": f"https://{domain}/"})
    assert response.status_code == 201

    for check in response.json()["checks"]:
        assert "@" not in check["evidence"]
        assert "<" not in check["evidence"]
        assert "Some short body text" not in check["evidence"]


def test_a_domain_pointed_scan_is_rate_limited_per_domain(
    client: TestClient, dns: DnsSetter, transport: Callable[[Handler], None]
) -> None:
    """Not a full run to the per-domain ceiling (5/day, `SCAN_PER_DOMAIN`) —
    that belongs to `test_scan_rate_limits.py`, which proves the bucket
    itself against real concurrency. This proves the *route* consults it: a
    domain whose bucket is already exhausted is refused with 429, without
    ever reaching `engine.scan`.
    """
    domain = f"e2e-{uuid4().hex[:12]}.example"
    dns({domain: [PUBLIC_A]})
    transport(robots_ok_then_page)

    # A plain sync connection for setup, not `check_and_increment` through a
    # fresh `anyio.run()` loop — that loop is not the one `TestClient`'s own
    # engine/pool is bound to, and asyncpg raises "attached to a different
    # loop" the moment a connection from one is awaited on the other. Found
    # by running this test, not assumed; `test_scan_rate_limits.py`'s
    # `consume()` helper already uses this same sync-connection shape for
    # exactly this reason.
    assert DB_URL is not None

    # The window boundary must match `rate_limit._window_start`'s own
    # arithmetic exactly — `date_trunc('hour', now())` was tried first and
    # landed in a different bucket than the app's fixed-window formula
    # (epoch minus epoch-mod-window-seconds, which for a 24-hour window is
    # UTC-midnight-aligned, not hour-aligned), so the route saw an empty
    # bucket and returned 201 instead of 429. Found by running this test.
    now = datetime.now(UTC)
    seconds = int(SCAN_PER_DOMAIN.window.total_seconds())
    epoch = int(now.timestamp())
    window_start = datetime.fromtimestamp(epoch - (epoch % seconds), tz=UTC)

    sync_engine = create_engine(DB_URL, poolclass=sa.pool.NullPool)
    try:
        with sync_engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO rate_limit_counter (bucket, window_start, count)
                    VALUES (:bucket, :window_start, :count)
                    ON CONFLICT (bucket, window_start)
                    DO UPDATE SET count = :count
                    """
                ),
                {
                    "bucket": f"{SCAN_PER_DOMAIN.bucket_prefix}:{domain}",
                    "window_start": window_start,
                    "count": SCAN_PER_DOMAIN.max_count,
                },
            )
    finally:
        sync_engine.dispose()

    response = client.post("/public/scans", json={"url": f"https://{domain}/"})
    assert response.status_code == 429
    assert "Retry-After" in response.headers
