"""The Payment step: quoting, paying, trialling, and the rate card itself.

`app/domain/pricing.py` computes the bill from a workspace's own facts and
reads entitlement; `app/routes/billing.py` is the thin HTTP wrapper over it.
Three things are asserted here, each against a real Postgres:

- **The quote's math** — departments and tools priced from the `price` table,
  never invented (I1), and a missing price surfaced rather than treated as free
  (I10).
- **Entitlement** — paid, live trial, expired trial, and no subscription at
  all.
- **Isolation** — `onboarding_subscription` is workspace-scoped RLS like every
  tenant table; `price` is readable under any workspace, which is the
  deliberate exception migration 0042 documents.
- **The admin gate** — an email allowlist, checked server-side, never from
  anything the client supplies.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy import Connection, Engine, create_engine
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import _unscoped_session, get_engine, get_sessionmaker
from app.domain import connections
from app.domain.departments import select_departments
from app.domain.pricing import entitlement_for, quote_for
from app.domain.scopes import Department, Role
from app.domain.session import ScopedSession
from app.main import create_app
from app.retrieval.scoped import apply_workspace_scope
from tests.dburl import async_database_url, database_url

requires_db = pytest.mark.requires_db
CSRF = "a-csrf-token"


# ── Seeding, direct-DB style (test_settings_departments.py's shape) ────────


@dataclass(frozen=True, slots=True)
class Seed:
    tenant_id: UUID
    user_id: UUID
    workspace_id: UUID
    email: str


@pytest.fixture
async def app_db(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[None]:
    url = async_database_url()
    assert url is not None
    monkeypatch.setenv("NEXUS_DATABASE_URL", url)
    monkeypatch.setenv("NEXUS_STORAGE_SIGNING_SECRET", "test-secret")
    for cache in (get_settings, get_engine, get_sessionmaker):
        cache.cache_clear()
    yield
    await get_engine().dispose()
    for cache in (get_settings, get_engine, get_sessionmaker):
        cache.cache_clear()


async def _seed(db: AsyncSession, *, email: str | None = None) -> Seed:
    seed = Seed(uuid4(), uuid4(), uuid4(), email or f"billing-{uuid4()}@example.invalid")

    await apply_workspace_scope(db, str(seed.workspace_id))
    await db.execute(
        sa.text("INSERT INTO tenant (id, name) VALUES (:t, 'Billing Test')"),
        {"t": str(seed.tenant_id)},
    )
    await db.execute(
        sa.text("INSERT INTO app_user (id, email) VALUES (:u, :e)"),
        {"u": str(seed.user_id), "e": seed.email},
    )
    await db.execute(
        sa.text(
            "INSERT INTO workspace (id, workspace_id, tenant_id, name, domain)"
            " VALUES (:id, :id, :t, 'Billing Test', :d)"
        ),
        {"id": str(seed.workspace_id), "t": str(seed.tenant_id), "d": f"{seed.workspace_id}.test"},
    )
    await db.execute(
        sa.text(
            "INSERT INTO membership (workspace_id, user_id, role, departments)"
            " VALUES (:ws, :u, 'owner', ARRAY['finance'])"
        ),
        {"ws": str(seed.workspace_id), "u": str(seed.user_id)},
    )
    return seed


async def _cleanup(db: AsyncSession, seed: Seed) -> None:
    await apply_workspace_scope(db, str(seed.workspace_id))
    for statement in (
        "DELETE FROM onboarding_subscription WHERE workspace_id = :w",
        "DELETE FROM workspace_department WHERE workspace_id = :w",
        "DELETE FROM workspace_connection WHERE workspace_id = :w",
        "DELETE FROM membership WHERE workspace_id = :w",
        "DELETE FROM workspace WHERE id = :w",
        "DELETE FROM app_user WHERE id = :u",
        "DELETE FROM tenant WHERE id = :t",
    ):
        await db.execute(
            sa.text(statement),
            {"w": str(seed.workspace_id), "u": str(seed.user_id), "t": str(seed.tenant_id)},
        )
    await db.commit()


# ── Quote math ──────────────────────────────────────────────────


@requires_db
async def test_quote_bills_selected_departments_and_declared_tools(app_db: None) -> None:
    """Marketing + Operations selected; GA4 (marketing, included) and Stripe
    (finance, not selected, additional) declared.

    marketing 25000 + operations 20000 + stripe 10000 = 55000, ga4 at 0 and
    `included`.
    """
    async with _unscoped_session() as db:
        seed = await _seed(db)
        try:
            await select_departments(
                db,
                workspace_id=seed.workspace_id,
                departments={Department.MARKETING, Department.OPERATIONS},
            )
            await connections.declare(
                db,
                workspace_id=seed.workspace_id,
                user_id=seed.user_id,
                providers=["ga4", "stripe"],
            )

            quote = await quote_for(db, workspace_id=seed.workspace_id)

            by_key = {(item["kind"], item["key"]): item for item in quote["line_items"]}
            assert by_key[("department", "marketing")]["amount_minor"] == 25_000
            assert by_key[("department", "operations")]["amount_minor"] == 20_000
            assert by_key[("tool", "ga4")]["amount_minor"] == 0
            assert by_key[("tool", "ga4")]["included"] is True
            assert by_key[("tool", "stripe")]["amount_minor"] == 10_000
            assert by_key[("tool", "stripe")]["included"] is False
            assert quote["total_minor"] == 55_000
            assert quote["currency"] == "OMR"
            assert quote["period"] == "monthly"
        finally:
            await _cleanup(db, seed)


@requires_db
async def test_quote_with_no_departments_and_no_tools_is_empty(app_db: None) -> None:
    """Nothing selected, nothing declared: no billable line, zero total.

    `selected_departments` always includes `executive`, which is never
    billed (`AUTOMATIC`) — a workspace that has chosen nothing therefore bills
    nothing, not "everything".
    """
    async with _unscoped_session() as db:
        seed = await _seed(db)
        try:
            quote = await quote_for(db, workspace_id=seed.workspace_id)

            assert quote["line_items"] == []
            assert quote["total_minor"] == 0
        finally:
            await _cleanup(db, seed)


@requires_db
async def test_an_inactive_price_is_unavailable_not_free(app_db: None) -> None:
    """I10: a missing/inactive price must not silently become zero.

    Marketing's price row is deactivated; the quote must surface it as
    `unavailable` rather than drop it or charge zero for it, and it must not
    contribute to `total_minor`.
    """
    async with _unscoped_session() as db:
        seed = await _seed(db)
        try:
            await select_departments(
                db, workspace_id=seed.workspace_id, departments={Department.MARKETING}
            )
            await db.execute(
                sa.text(
                    "UPDATE price SET active = false"
                    " WHERE kind = 'department' AND key = 'marketing'"
                )
            )

            quote = await quote_for(db, workspace_id=seed.workspace_id)

            by_key = {(item["kind"], item["key"]): item for item in quote["line_items"]}
            marketing = by_key[("department", "marketing")]
            assert marketing["unavailable"] is True
            assert marketing["amount_minor"] is None
            assert quote["total_minor"] == 0
        finally:
            await db.execute(
                sa.text(
                    "UPDATE price SET active = true WHERE kind = 'department' AND key = 'marketing'"
                )
            )
            await _cleanup(db, seed)


# ── Entitlement ─────────────────────────────────────────────────


@requires_db
async def test_a_paid_subscription_is_entitled(app_db: None) -> None:
    async with _unscoped_session() as db:
        seed = await _seed(db)
        try:
            await apply_workspace_scope(db, str(seed.workspace_id))
            await db.execute(
                sa.text(
                    "INSERT INTO onboarding_subscription"
                    " (workspace_id, status, amount_minor, currency, line_items)"
                    " VALUES (:w, 'paid', 55000, 'OMR', '[]'::jsonb)"
                ),
                {"w": str(seed.workspace_id)},
            )

            entitlement = await entitlement_for(db, workspace_id=seed.workspace_id)

            assert entitlement.entitled is True
            assert entitlement.kind == "paid"
        finally:
            await _cleanup(db, seed)


@requires_db
async def test_a_live_trial_is_entitled(app_db: None) -> None:
    async with _unscoped_session() as db:
        seed = await _seed(db)
        try:
            await apply_workspace_scope(db, str(seed.workspace_id))
            future = datetime.now(UTC) + timedelta(days=3)
            await db.execute(
                sa.text(
                    "INSERT INTO onboarding_subscription"
                    " (workspace_id, status, amount_minor, currency, line_items, trial_expires_at)"
                    " VALUES (:w, 'trial', 0, 'OMR', '[]'::jsonb, :exp)"
                ),
                {"w": str(seed.workspace_id), "exp": future},
            )

            entitlement = await entitlement_for(db, workspace_id=seed.workspace_id)

            assert entitlement.entitled is True
            assert entitlement.kind == "trial"
        finally:
            await _cleanup(db, seed)


@requires_db
async def test_an_expired_trial_is_not_entitled(app_db: None) -> None:
    async with _unscoped_session() as db:
        seed = await _seed(db)
        try:
            await apply_workspace_scope(db, str(seed.workspace_id))
            past = datetime.now(UTC) - timedelta(days=1)
            await db.execute(
                sa.text(
                    "INSERT INTO onboarding_subscription"
                    " (workspace_id, status, amount_minor, currency, line_items, trial_expires_at)"
                    " VALUES (:w, 'trial', 0, 'OMR', '[]'::jsonb, :exp)"
                ),
                {"w": str(seed.workspace_id), "exp": past},
            )

            entitlement = await entitlement_for(db, workspace_id=seed.workspace_id)

            assert entitlement.entitled is False
            assert entitlement.kind == "trial"
        finally:
            await _cleanup(db, seed)


@requires_db
async def test_no_subscription_at_all_is_not_entitled(app_db: None) -> None:
    async with _unscoped_session() as db:
        seed = await _seed(db)
        try:
            entitlement = await entitlement_for(db, workspace_id=seed.workspace_id)

            assert entitlement.entitled is False
            assert entitlement.kind is None
            assert entitlement.trial_expires_at is None
        finally:
            await _cleanup(db, seed)


# ── RLS: direct-SQL style (test_tenant_isolation.py's shape) ───────────────


@pytest.fixture(scope="module")
def sync_engine() -> Iterator[Engine]:
    url = database_url()
    assert url is not None
    eng = create_engine(url, poolclass=sa.pool.NullPool)
    yield eng
    eng.dispose()


@pytest.fixture
def conn(sync_engine: Engine) -> Iterator[Connection]:
    connection = sync_engine.connect()
    trans = connection.begin()
    try:
        yield connection
    finally:
        trans.rollback()
        connection.close()


def _set_workspace(conn: Connection, workspace_id: UUID | None) -> None:
    if workspace_id is None:
        conn.execute(sa.text("SELECT set_config('nexus.workspace_id', '', true)"))
    else:
        conn.execute(
            sa.text("SELECT set_config('nexus.workspace_id', :w, true)"), {"w": str(workspace_id)}
        )


@requires_db
def test_a_subscription_row_is_invisible_from_another_workspace(conn: Connection) -> None:
    tenant_a, tenant_b = uuid4(), uuid4()
    ws_a, ws_b = uuid4(), uuid4()

    conn.execute(
        sa.text("INSERT INTO tenant (id, name) VALUES (:a, 'T A'), (:b, 'T B')"),
        {"a": str(tenant_a), "b": str(tenant_b)},
    )
    for tenant, ws in ((tenant_a, ws_a), (tenant_b, ws_b)):
        _set_workspace(conn, ws)
        conn.execute(
            sa.text(
                "INSERT INTO workspace (id, workspace_id, tenant_id, name, domain)"
                " VALUES (:id, :id, :t, 'W', :d)"
            ),
            {"id": str(ws), "t": str(tenant), "d": f"{ws}.test"},
        )
        conn.execute(
            sa.text(
                "INSERT INTO onboarding_subscription"
                " (workspace_id, status, amount_minor, currency, line_items)"
                " VALUES (:w, 'paid', 1000, 'OMR', '[]'::jsonb)"
            ),
            {"w": str(ws)},
        )

    _set_workspace(conn, ws_a)
    visible = conn.execute(sa.text("SELECT workspace_id FROM onboarding_subscription")).all()

    assert [str(row.workspace_id) for row in visible] == [str(ws_a)], (
        "a scoped read must return only this workspace's own row"
    )


@requires_db
def test_price_rows_are_readable_under_any_workspace(conn: Connection) -> None:
    """The deliberate exception migration 0042 documents: no workspace scope."""
    _set_workspace(conn, uuid4())

    count = conn.execute(sa.text("SELECT count(*) FROM price WHERE active = true")).scalar_one()

    assert count > 0, "price is reference data, readable regardless of which workspace is set"


# ── HTTP: admin gate and CSRF (test_ops_write_db.py's shape) ───────────────
#
# Seeded through the sync engine, not `_unscoped_session`: `TestClient` drives
# the app's own async pool on its own event loop, and an `async def` test body
# sharing that pool through a *second* loop is exactly the
# "attached to a different loop" failure asyncpg raises — mixing the two
# within one test is the bug, not either tool on its own.


@pytest.fixture
def client(app_db: None) -> Iterator[TestClient]:
    app = create_app()
    with TestClient(app) as made:
        yield made
    app.dependency_overrides.clear()


def _as(client: TestClient, user_id: UUID, workspace_id: UUID) -> None:
    from app.deps import current_scope

    scope = ScopedSession(
        user_id=user_id,
        tenant_id=uuid4(),
        workspace_id=workspace_id,
        role=Role.OWNER,
        departments=frozenset({Department.FINANCE}),
    )
    client.app.dependency_overrides[current_scope] = lambda: scope  # type: ignore[attr-defined]
    client.cookies.set("nexus_csrf", CSRF)


def _seed_sync(engine: Engine, *, email: str, departments: tuple[str, ...] = ()) -> Seed:
    """Seeded and **committed** — `engine.begin()` closes over its own
    transaction, unlike the `conn` fixture above, which holds one open for the
    whole test and rolls it back. A row the `TestClient`'s own connection must
    see cannot stay uncommitted on a connection of ours.
    """
    seed = Seed(uuid4(), uuid4(), uuid4(), email)
    with engine.begin() as conn:
        _set_workspace(conn, seed.workspace_id)
        conn.execute(
            sa.text("INSERT INTO tenant (id, name) VALUES (:t, 'Billing Admin Test')"),
            {"t": str(seed.tenant_id)},
        )
        conn.execute(
            sa.text("INSERT INTO app_user (id, email) VALUES (:u, :e)"),
            {"u": str(seed.user_id), "e": seed.email},
        )
        conn.execute(
            sa.text(
                "INSERT INTO workspace (id, workspace_id, tenant_id, name, domain)"
                " VALUES (:id, :id, :t, 'Billing Admin Test', :d)"
            ),
            {
                "id": str(seed.workspace_id),
                "t": str(seed.tenant_id),
                "d": f"{seed.workspace_id}.test",
            },
        )
        conn.execute(
            sa.text(
                "INSERT INTO membership (workspace_id, user_id, role, departments)"
                " VALUES (:ws, :u, 'owner', ARRAY['finance'])"
            ),
            {"ws": str(seed.workspace_id), "u": str(seed.user_id)},
        )
        for department in departments:
            conn.execute(
                sa.text(
                    "INSERT INTO workspace_department (workspace_id, department) VALUES (:w, :d)"
                ),
                {"w": str(seed.workspace_id), "d": department},
            )
    return seed


def _cleanup_sync(engine: Engine, seed: Seed) -> None:
    with engine.begin() as conn:
        _set_workspace(conn, seed.workspace_id)
        for statement in (
            "DELETE FROM onboarding_subscription WHERE workspace_id = :w",
            "DELETE FROM workspace_department WHERE workspace_id = :w",
            "DELETE FROM membership WHERE workspace_id = :w",
            "DELETE FROM workspace WHERE id = :w",
            "DELETE FROM app_user WHERE id = :u",
            "DELETE FROM tenant WHERE id = :t",
        ):
            conn.execute(
                sa.text(statement),
                {"w": str(seed.workspace_id), "u": str(seed.user_id), "t": str(seed.tenant_id)},
            )


@requires_db
def test_a_non_allowlisted_caller_is_refused_the_admin_endpoint(
    client: TestClient, sync_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("NEXUS_PLATFORM_ADMIN_EMAILS", "someone-else@example.com")
    get_settings.cache_clear()

    seed = _seed_sync(sync_engine, email="not-an-admin@example.test")
    try:
        _as(client, seed.user_id, seed.workspace_id)

        response = client.put(
            "/admin/prices/department/marketing",
            json={"amount_minor": 26_000, "active": True},
            headers={"X-CSRF-Token": CSRF},
        )

        assert response.status_code == 403
    finally:
        _cleanup_sync(sync_engine, seed)
        get_settings.cache_clear()


@requires_db
def test_an_allowlisted_caller_can_edit_a_price_and_the_quote_reflects_it(
    client: TestClient, sync_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    seed = _seed_sync(sync_engine, email="billing-admin@example.test", departments=("marketing",))

    monkeypatch.setenv("NEXUS_PLATFORM_ADMIN_EMAILS", seed.email)
    get_settings.cache_clear()
    try:
        _as(client, seed.user_id, seed.workspace_id)

        update = client.put(
            "/admin/prices/department/marketing",
            json={"amount_minor": 26_000, "active": True},
            headers={"X-CSRF-Token": CSRF},
        )
        assert update.status_code == 200
        assert update.json()["amount_minor"] == 26_000

        quote = client.get("/billing/quote")
        assert quote.status_code == 200
        marketing = next(item for item in quote.json()["line_items"] if item["key"] == "marketing")
        assert marketing["amount_minor"] == 26_000
    finally:
        with sync_engine.begin() as conn:
            conn.execute(
                sa.text(
                    "UPDATE price SET amount_minor = 25000, active = true"
                    " WHERE kind = 'department' AND key = 'marketing'"
                )
            )
        _cleanup_sync(sync_engine, seed)
        get_settings.cache_clear()
