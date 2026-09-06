"""The guided onboarding, end to end, against a real database.

Everything below the model is real: the routes, the agent, the commands, the
skill files on disk with their actual prompts and schemas, the SQL, the check
constraints and row-level security. Only the provider is a double, and it has to
be — a test that called Anthropic would be non-deterministic, slow, billed, and
would pass or fail for reasons that have nothing to do with this code.

`ScriptedProvider` raises on any skill a test did not script, so nothing here can
pass against output nobody wrote.

The three tests that matter are not the happy path:

- `test_a_generated_question_naming_an_undeclared_field_never_reaches_the_person`
  is ADR 0021's condition, exercised through HTTP and the database rather than
  asserted in a unit.
- `test_the_scope_stored_is_the_catalogue_s_not_the_model_s` is the same
  mechanism from the other side: the model says L1, the row says L3.
- `test_a_brain_value_with_no_provenance_is_dropped` is the NOT NULL column
  meeting the rule that produces it.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.providers import ScriptedProvider
from app.config import get_settings
from app.db import get_engine, get_sessionmaker
from tests.dburl import async_database_url

if TYPE_CHECKING:
    from app.domain.session import ScopedSession

ASYNC_DB_URL = async_database_url()
requires_db = pytest.mark.requires_db

DOMAIN = "nakhla-trading.om"
"""Only the fixture pages' URLs. The domain the agent actually researches is
read from the workspace row, never from the request — so each test's workspace
keeps its own unique domain (the partial unique index on a verified domain
would reject a shared one)."""

PAGES = [
    {"url": f"https://{DOMAIN}/about", "text": "Industrial supplies to contractors in Muscat."},
    {"url": f"https://{DOMAIN}/products", "text": "Valves, fittings, fasteners, PPE."},
]


# ── Scripted skill output, valid against the real schemas ─────


def _research() -> str:
    return json.dumps(
        {
            "profile": {"found": True, "value": "Industrial supplies and distribution.",
                        "confidence": "read", "source": "/about"},
            "products_services": {"found": True, "value": "Valves, fittings, fasteners, PPE.",
                                  "confidence": "read", "source": "/products"},
            "brand_voice": {"found": True, "value": "Plain and technical.",
                            "confidence": "inferred", "reasoning": "tone across pages"},
            "technology_seen": [],
            "could_not_determine": [{"topic": "Target customers", "why": "not stated"}],
            "pages_read": 2,
        }
    )


def _summary() -> str:
    return json.dumps(
        {
            "statements": [
                {"field": "brain.profile", "text": "You sell industrial supplies.",
                 "confidence": "read", "source": "/about"},
            ],
            "needs_you": [{"topic": "Target customers", "why_only_you": "only you know"}],
            "assumptions": [{"text": "Currency is OMR", "evidence": ".om domain"}],
            "opening_line": "I have read your site.",
        }
    )


def _discovery() -> str:
    # `evidence` must be a literal span of the submitted answer — the command
    # drops anything that is not, because the panel shows these back as
    # "you said this".
    return json.dumps(
        {
            "stated_purpose": {"value": "Runs the company", "evidence": "I run the company"},
            "priority_topics": [{"topic": "cash", "evidence": "worried about cash"}],
            "signals": [],
            "declined_to_infer_role": False,
        }
    )


def _question(target: str = "brain.target_customers") -> str:
    return json.dumps(
        {
            "done": False,
            "question": "Who actually buys from you?",
            "target": target,
            "rationale": "the brief could not determine it",
            "choices": [],
        }
    )


def _persona() -> str:
    return json.dumps(
        {
            "fields": [
                {"key": "persona.priority_topics", "value": "cash",
                 "derived_from": "worried about cash", "confidence": "stated"},
            ],
            "summary": "Wants cash first.",
        }
    )


def _brain(with_unsourced: bool = False) -> str:
    values: list[dict[str, Any]] = [
        {"key": "brain.profile", "value": "Industrial supplies.",
         "source_kind": "crawl", "provenance": "/about"},
    ]
    if with_unsourced:
        values.append(
            {"key": "brain.goals", "value": "Grow 40%", "source_kind": "inference",
             "provenance": ""}
        )
    return json.dumps(
        {"values": values, "assumptions": [], "unavailable": [], "generated_by": "model"}
    )


def _context() -> str:
    return json.dumps(
        {
            "preamble": "Nakhla Trading sells industrial supplies.",
            "facts": [{"key": "brain.profile", "value": "Industrial supplies.", "scope": 1}],
            "known_gaps": [{"topic": "Cash position", "unlocked_by": "Connect accounting"}],
        }
    )


def _provider(**overrides: Any) -> ScriptedProvider:
    script: dict[str, Any] = {
        "company-research": _research(),
        "company-summary": _summary(),
        "user-discovery": _discovery(),
        "question-generation": _question(),
        "persona-builder": _persona(),
        "company-brain-builder": _brain(),
        "context-personalization": _context(),
    }
    script.update(overrides)
    return ScriptedProvider(script)


# ── The fixtures must match the real schemas ──────────────────


def test_the_scripted_fixtures_match_the_real_skill_schemas() -> None:
    """Runs with no database, so schema drift is caught even when the DB tests skip.

    Without this, a schema edit that the fixtures do not follow shows up as the
    runner retrying twice and raising `SkillOutputInvalidError` deep inside a
    journey test — which reads as "the agent is broken" rather than "the test
    data is stale". Here it fails on the line that is actually wrong.
    """
    from app.ai.runtime.runner import validate
    from app.ai.runtime.skills import SkillRegistry

    registry = SkillRegistry().load()
    scripted = {
        "company-research": _research(),
        "company-summary": _summary(),
        "user-discovery": _discovery(),
        "question-generation": _question(),
        "persona-builder": _persona(),
        "company-brain-builder": _brain(),
        "context-personalization": _context(),
    }
    assert set(scripted) == set(registry.names()), "a skill has no scripted fixture"

    for name, payload in scripted.items():
        schema = registry.get(name).schema
        assert schema is not None, f"{name} has no schema"
        problems = validate(json.loads(payload), schema)
        assert not problems, f"{name} fixture does not match its schema: {problems}"


def test_every_scripted_target_is_a_declared_field() -> None:
    """The targets these tests drive through must exist, or the test proves nothing."""
    from app.ai.runtime.fields import resolve

    for key in ("brain.target_customers", "fact.finance.approval_threshold",
                "brain.profile", "brain.goals", "persona.priority_topics"):
        assert resolve(key).key == key


# ── Fixtures ──────────────────────────────────────────────────


@pytest.fixture
async def app_db(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[None]:
    assert ASYNC_DB_URL is not None
    monkeypatch.setenv("NEXUS_DATABASE_URL", ASYNC_DB_URL)
    monkeypatch.setenv("NEXUS_STORAGE_SIGNING_SECRET", "test-secret")
    for cache in (get_settings, get_engine, get_sessionmaker):
        cache.cache_clear()
    yield
    await get_engine().dispose()
    for cache in (get_settings, get_engine, get_sessionmaker):
        cache.cache_clear()


def _wire(monkeypatch: pytest.MonkeyPatch, provider: ScriptedProvider) -> None:
    """Swap the provider and the crawler for doubles, at the route module.

    The crawl is stubbed for the same reason as the model: a test that reached
    out to a real site would fail when the site changed, which is not a fact
    about this code.
    """
    import app.routes.onboarding_agent as routes
    from app.domain.research import SourceState
    from app.research.runner import CrawlOutcome

    monkeypatch.setattr(routes, "get_provider", lambda: provider)

    async def fake_crawl(seeds: list[str], **_: Any) -> CrawlOutcome:
        return CrawlOutcome(state=SourceState.SUCCEEDED, pages=list(PAGES))

    monkeypatch.setattr(routes, "crawl_site", fake_crawl)


async def _workspace(
    db: AsyncSession,
    *,
    display_name: str | None = None,
    designation: str | None = None,
    stated_department: str | None = None,
) -> tuple[UUID, UUID]:
    user, tenant, ws = uuid4(), uuid4(), uuid4()
    await db.execute(
        sa.text("INSERT INTO app_user (id, email, display_name) VALUES (:i,:e,:n)"),
        {"i": str(user), "e": f"agent-{user.hex[:8]}@example.com", "n": display_name},
    )
    await db.execute(sa.text("INSERT INTO tenant (id, name) VALUES (:i,'T')"), {"i": str(tenant)})
    await db.execute(sa.text("SELECT set_config('nexus.workspace_id', :w, true)"), {"w": str(ws)})
    await db.execute(
        sa.text(
            "INSERT INTO workspace (id, workspace_id, tenant_id, name, domain,"
            " domain_verified_at) VALUES (:i,:i,:t,'W',:d, now())"
        ),
        {"i": str(ws), "t": str(tenant), "d": f"agent-{ws.hex[:8]}.om"},
    )
    await db.execute(
        sa.text(
            "INSERT INTO membership (workspace_id, user_id, role, departments,"
            " designation, stated_department)"
            " VALUES (:w,:u,'owner', ARRAY['executive']::text[], :desig, :dept)"
        ),
        {"w": str(ws), "u": str(user), "desig": designation, "dept": stated_department},
    )
    await db.commit()
    return user, ws


def _scope(user: UUID, ws: UUID) -> ScopedSession:
    from app.domain.scopes import Department, Role
    from app.domain.session import ScopedSession

    return ScopedSession(
        user_id=user, tenant_id=uuid4(), workspace_id=ws,
        role=Role.OWNER, departments=frozenset(Department),
    )


async def _cleanup(db: AsyncSession, user: UUID, ws: UUID) -> None:
    await db.execute(sa.text("SELECT set_config('nexus.workspace_id', :w, true)"), {"w": str(ws)})
    # Read the tenant before the workspace that points at it is deleted.
    # Without this the tenant row survives every run — 341 of them had
    # accumulated against 122 users before anyone looked.
    tenant = (
        await db.execute(sa.text("SELECT tenant_id FROM workspace WHERE id = :w"), {"w": str(ws)})
    ).scalar_one_or_none()
    for statement in (
        # audit_log first: the audit handler writes a row per answer, and the
        # workspace delete below would fail on the reference.
        "DELETE FROM audit_log WHERE workspace_id = :w",
        "DELETE FROM onboarding_turn WHERE workspace_id = :w",
        "DELETE FROM onboarding_session WHERE workspace_id = :w",
        "DELETE FROM membership WHERE workspace_id = :w",
        "DELETE FROM workspace WHERE id = :w",
    ):
        await db.execute(sa.text(statement), {"w": str(ws)})
    await db.execute(sa.text("DELETE FROM app_user WHERE id = :u"), {"u": str(user)})
    if tenant is not None:
        await db.execute(sa.text("DELETE FROM tenant WHERE id = :t"), {"t": str(tenant)})
    await db.commit()


async def _assemble(routes: Any, scope: ScopedSession) -> Any:
    """Drive the assembly to completion. Three calls, one stage each.

    `/finish` advances the phase by one step per request so that each stage
    commits on its own — see the route. A test that called it once would assert
    against a session sitting in `persona`, which is not a failure but a third
    of the work.

    Bounded and asserted rather than `while True`: a route that stopped
    advancing would otherwise hang the suite instead of failing it.
    """
    state = await routes.finish(scope)
    for _ in range(3):
        if state.phase == "ready":
            return state
        before = state.phase
        state = await routes.finish(scope)
        assert state.phase != before, f"/finish did not advance from {before}"
    assert state.phase == "ready", f"assembly stalled in {state.phase}"
    return state


async def _turns(db: AsyncSession, ws: UUID) -> list[dict[str, Any]]:
    await db.execute(sa.text("SELECT set_config('nexus.workspace_id', :w, true)"), {"w": str(ws)})
    rows = await db.execute(
        sa.text(
            "SELECT seq, role, text, target_field, scope FROM onboarding_turn"
            " WHERE workspace_id = :w ORDER BY seq"
        ),
        {"w": str(ws)},
    )
    return [dict(r) for r in rows.mappings().all()]


# ── The journey ───────────────────────────────────────────────


@requires_db
async def test_the_whole_journey_completes_and_persists(
    app_db: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Start to finish: crawl, brief, discovery, one question, assemble."""
    import app.routes.onboarding_agent as routes

    provider = _provider()
    _wire(monkeypatch, provider)

    async with get_sessionmaker()() as db:
        user, ws = await _workspace(db)
        scope = _scope(user, ws)
        try:
            # Two calls, and the split is the assertion. `start` fetches and
            # returns in a few seconds so the screen has something true to show;
            # `read` is the pair of model calls behind it. A test that called
            # one and expected the other's result is how the split would rot.
            fetched = await routes.start(scope)
            assert fetched.phase == "analysing"
            assert fetched.pages_read, "the fetch must report what it retrieved"

            state = await routes.read(scope)
            assert state.phase == "brief"
            assert state.brief["opening_line"] == "I have read your site."

            state = await routes.confirm_brief(
                routes.BriefIn(corrections={"brain.profile": "We sell valves, not services."}),
                scope,
            )
            assert state.phase == "discovery"

            answer = "I run the company and I am worried about cash"
            state = await routes.open_discovery(routes.DiscoveryIn(answer=answer), scope)

            question = await routes.next_question(scope)
            assert question.done is False
            assert question.target == "brain.target_customers"

            state = await routes.submit_answer(
                routes.AnswerIn(text="Contractors and facilities teams"), scope
            )
            assert state.answered >= 2

            state = await _assemble(routes, scope)
            assert state.phase == "ready"
            assert state.context["preamble"].startswith("Nakhla Trading")

            # The session is closed, and closed sessions are not resumable —
            # `ux_onboarding_session_active` only constrains active ones.
            #
            # The GUC has to be set again here. `set_config(..., true)` is
            # transaction-local, so the one `_workspace` set went with its
            # commit — without this the policy hides the row and the assertion
            # fails as "no such session", which is RLS working, not a bug.
            await db.execute(
                sa.text("SELECT set_config('nexus.workspace_id', :w, true)"), {"w": str(ws)}
            )
            row = (
                await db.execute(
                    sa.text(
                        "SELECT status, completed_at FROM onboarding_session"
                        " WHERE workspace_id = :w"
                    ),
                    {"w": str(ws)},
                )
            ).mappings().one()
            assert row["status"] == "completed"
            assert row["completed_at"] is not None

            # Each answer left an audit row, written inside the same
            # transaction as the answer itself. This is the whole point of the
            # `critical` handler class — a recorded answer with no audit row
            # would be a silent gap in the trail.
            audited = (
                await db.execute(
                    sa.text(
                        "SELECT target_id, reason FROM audit_log"
                        " WHERE workspace_id = :w AND action = 'answer_written'"
                        " ORDER BY target_id"
                    ),
                    {"w": str(ws)},
                )
            ).mappings().all()
            assert len(audited) >= 2, f"expected an audit row per answer, got {len(audited)}"
            targets = {r["target_id"] for r in audited}
            assert "brain.target_customers" in targets
            # The scope on the row is the catalogue's, carried through the hook.
            assert all("scope=L" in r["reason"] for r in audited)

            # Every skill ran exactly once, and none was improvised.
            assert {c.skill for c in provider.calls} == {
                "company-research", "company-summary", "user-discovery",
                "question-generation", "persona-builder", "company-brain-builder",
                "context-personalization",
            }
        finally:
            await _cleanup(db, user, ws)


@requires_db
async def test_the_scope_stored_is_the_catalogue_s_not_the_model_s(
    app_db: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The model asked for a field; the row carries the catalogue's sensitivity.

    `fact.finance.approval_threshold` is L3. Nothing the model returns can make
    it anything else, because the scope is never read from model output.
    """
    import app.routes.onboarding_agent as routes
    from app.ai.runtime.fields import resolve

    provider = _provider(**{
        "question-generation": _question("fact.finance.approval_threshold")
    })
    _wire(monkeypatch, provider)

    async with get_sessionmaker()() as db:
        user, ws = await _workspace(db)
        scope = _scope(user, ws)
        try:
            await routes.start(scope)
            await routes.read(scope)
            await routes.confirm_brief(routes.BriefIn(corrections={}), scope)
            await routes.open_discovery(
                routes.DiscoveryIn(answer="I run the company and I am worried about cash"), scope
            )
            question = await routes.next_question(scope)
            assert question.target == "fact.finance.approval_threshold"

            await routes.submit_answer(routes.AnswerIn(text="OMR 1,000"), scope)

            rows = await _turns(db, ws)
            answered = [r for r in rows if r["role"] == "user" and r["target_field"]
                        == "fact.finance.approval_threshold"]
            assert len(answered) == 1
            assert answered[0]["scope"] == resolve("fact.finance.approval_threshold").scope == 3
        finally:
            await _cleanup(db, user, ws)


@requires_db
async def test_a_generated_question_naming_an_undeclared_field_never_reaches_the_person(
    app_db: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ADR 0021's condition, through HTTP and the database.

    The model invents `brain.annual_revenue`. It is not in the catalogue, so the
    question is refused before it is asked, the model is retried, and after
    `MAX_REJECTIONS` the interview ends rather than storing an answer whose
    sensitivity nobody decided. No turn is written and no answer is recorded.

    **Read this together with `test_the_scope_stored_is_the_catalogue_s_not_the_model_s`.**
    On its own this test passes if the gate rejects *everything*, which is
    exactly the bug it shipped with: the gate called `check_target`, which asks
    whether a skill may *write* a field, and `question-generation` declares no
    writes — so every target was refused and this assertion held for the wrong
    reason. The paired test supplies the positive case. A negative test with no
    positive beside it proves only that something is broken somewhere.
    """
    import app.routes.onboarding_agent as routes

    provider = _provider(**{"question-generation": _question("brain.annual_revenue")})
    _wire(monkeypatch, provider)

    async with get_sessionmaker()() as db:
        user, ws = await _workspace(db)
        scope = _scope(user, ws)
        try:
            await routes.start(scope)
            await routes.read(scope)
            await routes.confirm_brief(routes.BriefIn(corrections={}), scope)
            await routes.open_discovery(
                routes.DiscoveryIn(answer="I run the company and I am worried about cash"), scope
            )

            question = await routes.next_question(scope)
            assert question.done is True, "an undeclared target must not be asked"

            rows = await _turns(db, ws)
            assert not [r for r in rows if r["target_field"] == "brain.annual_revenue"]

            # Retried rather than accepted once — the refusal is a real loop.
            attempts = [c for c in provider.calls if c.skill == "question-generation"]
            assert len(attempts) >= 2
        finally:
            await _cleanup(db, user, ws)


@requires_db
async def test_a_brain_value_with_no_provenance_is_dropped(
    app_db: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`company_brain.provenance` is NOT NULL, and this is the rule behind it.

    An unsourced value is not given a placeholder to satisfy the column — it is
    dropped. Satisfying the constraint with 'unknown' would keep the schema
    happy and defeat the reason it exists.
    """
    import app.routes.onboarding_agent as routes

    provider = _provider(**{"company-brain-builder": _brain(with_unsourced=True)})
    _wire(monkeypatch, provider)

    async with get_sessionmaker()() as db:
        user, ws = await _workspace(db)
        scope = _scope(user, ws)
        try:
            await routes.start(scope)
            await routes.read(scope)
            await routes.confirm_brief(routes.BriefIn(corrections={}), scope)
            await routes.open_discovery(
                routes.DiscoveryIn(answer="I run the company and I am worried about cash"), scope
            )
            state = await _assemble(routes, scope)

            keys = {f["key"] for f in state.context.get("facts", [])}
            assert "brain.goals" not in keys, "an unsourced value was stored"
        finally:
            await _cleanup(db, user, ws)


# ── The database's own guards ─────────────────────────────────


@requires_db
async def test_row_level_security_hides_another_workspace_s_transcript(app_db: None) -> None:
    """A transcript contains everything a founder said. RLS is what keeps it theirs."""
    async with get_sessionmaker()() as db:
        user_a, ws_a = await _workspace(db)
        user_b, ws_b = await _workspace(db)
        try:
            await db.execute(
                sa.text("SELECT set_config('nexus.workspace_id', :w, true)"), {"w": str(ws_a)}
            )
            sid = (
                await db.execute(
                    sa.text(
                        "INSERT INTO onboarding_session (workspace_id, user_id, domain)"
                        " VALUES (:w,:u,'a.om') RETURNING id"
                    ),
                    {"w": str(ws_a), "u": str(user_a)},
                )
            ).scalar_one()
            await db.execute(
                sa.text(
                    "INSERT INTO onboarding_turn (session_id, workspace_id, seq, role, text)"
                    " VALUES (:s,:w,1,'user','our margin is terrible')"
                ),
                {"s": str(sid), "w": str(ws_a)},
            )
            await db.commit()

            assert len(await _turns(db, ws_a)) == 1
            assert await _turns(db, ws_b) == []
        finally:
            await _cleanup(db, user_a, ws_a)
            await _cleanup(db, user_b, ws_b)


@requires_db
async def test_a_targeted_turn_without_a_scope_is_rejected_by_the_database(
    app_db: None,
) -> None:
    """`ck_onboarding_turn_scoped_answer`.

    The application always sets both. This proves the claim is about the data
    and not only about code that could change.
    """
    async with get_sessionmaker()() as db:
        user, ws = await _workspace(db)
        try:
            await db.execute(
                sa.text("SELECT set_config('nexus.workspace_id', :w, true)"), {"w": str(ws)}
            )
            sid = (
                await db.execute(
                    sa.text(
                        "INSERT INTO onboarding_session (workspace_id, user_id, domain)"
                        " VALUES (:w,:u,'a.om') RETURNING id"
                    ),
                    {"w": str(ws), "u": str(user)},
                )
            ).scalar_one()
            with pytest.raises(Exception, match="ck_onboarding_turn_scoped_answer"):
                await db.execute(
                    sa.text(
                        "INSERT INTO onboarding_turn"
                        " (session_id, workspace_id, seq, role, text, target_field)"
                        " VALUES (:s,:w,1,'user','x','brain.profile')"
                    ),
                    {"s": str(sid), "w": str(ws)},
                )
            await db.rollback()
        finally:
            await _cleanup(db, user, ws)


@requires_db
async def test_only_one_journey_may_be_open_per_workspace(app_db: None) -> None:
    """`ux_onboarding_session_active`.

    Two live sessions would race to promote their own drafts into one Brain.
    """
    async with get_sessionmaker()() as db:
        user, ws = await _workspace(db)
        try:
            await db.execute(
                sa.text("SELECT set_config('nexus.workspace_id', :w, true)"), {"w": str(ws)}
            )
            insert = sa.text(
                "INSERT INTO onboarding_session (workspace_id, user_id, domain)"
                " VALUES (:w,:u,'a.om')"
            )
            await db.execute(insert, {"w": str(ws), "u": str(user)})
            with pytest.raises(Exception, match="ux_onboarding_session_active"):
                await db.execute(insert, {"w": str(ws), "u": str(user)})
            await db.rollback()
        finally:
            await _cleanup(db, user, ws)


@requires_db
async def test_the_greeting_reads_the_claim_and_never_the_grant(app_db: None) -> None:
    """`viewer` carries what the person said about themselves, and nothing else.

    The greeting is the first line of the product, and it is the easiest place
    for authorisation to start being treated as small talk. `designation` and
    `stated_department` are claims typed at sign-up and reach nothing;
    `membership.role` and `membership.departments` are the pair the retrieval
    predicate runs on. Migration 0025 names the columns one letter apart in
    intent for exactly this reason, so the wire is asserted rather than trusted.

    Read off `/state`, which needs no model and no session — the greeting has to
    be on screen while the crawl runs, not after it.
    """
    import app.routes.onboarding_agent as routes

    async with get_sessionmaker()() as db:
        user, ws = await _workspace(
            db,
            display_name="Parul Bhoite",
            designation="Lead Designer",
            stated_department="Design",
        )
        try:
            out = await routes.read_state(_scope(user, ws))
            assert out.active is False
            assert out.viewer.name == "Parul Bhoite"
            assert out.viewer.designation == "Lead Designer"
            assert out.viewer.department == "Design"
            assert out.viewer.company == "W"

            # The authorising pair, by value. `owner` and `executive` are what
            # this membership actually holds, and neither may appear.
            assert "owner" not in out.viewer.model_dump_json()
            assert "executive" not in out.viewer.model_dump_json()
            assert not hasattr(out.viewer, "role")
        finally:
            await _cleanup(db, user, ws)


@requires_db
async def test_an_unstated_job_is_absent_rather_than_blank(app_db: None) -> None:
    """All three columns are nullable, and an invited user may have typed none.

    `None`, never `""`: the screen gates each clause on its own value, so a
    blank string would put "as  in " into the first sentence somebody reads.
    """
    import app.routes.onboarding_agent as routes

    async with get_sessionmaker()() as db:
        user, ws = await _workspace(db, display_name="Parul Bhoite")
        try:
            out = await routes.read_state(_scope(user, ws))
            assert out.viewer.name == "Parul Bhoite"
            assert out.viewer.designation is None
            assert out.viewer.department is None
        finally:
            await _cleanup(db, user, ws)


@requires_db
async def test_a_failed_stage_keeps_the_stages_before_it(
    app_db: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The whole reason `/finish` runs one stage per request.

    All three model calls used to happen inside one handler, and
    `scoped_connection` opens a single transaction around a handler — so the
    persona and Brain writes were rolled back by a failure in the third call,
    or by the process dying, and the retry paid for them again. That happened
    in a browser: a 503 from the proxy, clicked twice, six model calls, no rows.

    Here the Brain builder is unscripted, so stage two raises inside the runner.
    The assertion is not that it failed — it is that `persona_draft` from stage
    one is **on the row afterwards**, and that the phase is sitting at the stage
    that broke rather than back at the beginning.
    """
    import app.routes.onboarding_agent as routes

    # The Brain builder is scripted with output that does not match its schema,
    # so the runner retries and raises `SkillOutputInvalidError` — a
    # `SkillFailedError`, which the route turns into the 502 asserted below.
    # Deliberately not "leave the skill unscripted": that path raises
    # `AssertionError` out of the provider, which is a broken test rather than
    # the product's own failure mode.
    provider = _provider(**{"company-brain-builder": json.dumps({"values": "not a list"})})
    _wire(monkeypatch, provider)

    async with get_sessionmaker()() as db:
        user, ws = await _workspace(db)
        scope = _scope(user, ws)
        try:
            await routes.start(scope)
            await routes.read(scope)
            await routes.confirm_brief(routes.BriefIn(corrections={}), scope)
            await routes.open_discovery(routes.DiscoveryIn(answer="I run the company"), scope)

            # Stage one commits.
            state = await routes.finish(scope)
            assert state.phase == "persona"
            assert state.persona["fields"], "stage one produced no persona"

            # Stage two fails.
            with pytest.raises(HTTPException) as raised:
                await routes.finish(scope)
            assert raised.value.status_code == 502

            await db.execute(
                sa.text("SELECT set_config('nexus.workspace_id', :w, true)"), {"w": str(ws)}
            )
            row = (
                await db.execute(
                    sa.text(
                        "SELECT phase, status, persona_draft FROM onboarding_session"
                        " WHERE workspace_id = :w"
                    ),
                    {"w": str(ws)},
                )
            ).mappings().one()

            # The point: stage one survived a stage-two failure.
            assert row["phase"] == "persona"
            assert row["status"] == "active"
            draft = row["persona_draft"]
            if isinstance(draft, str):
                draft = json.loads(draft)
            assert draft["fields"], "the committed persona was rolled back with stage two"
        finally:
            await _cleanup(db, user, ws)
