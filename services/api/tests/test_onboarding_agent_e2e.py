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
from typing import TYPE_CHECKING, Any, cast
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.providers import ScriptedProvider
from app.config import get_settings
from app.db import get_engine, get_sessionmaker
from app.retrieval.scoped import scoped_connection
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


def _mismatched_question() -> str:
    """The audited `runway_alarm` failure, verbatim.

    A declared target, in the answerer's own department, and a question that
    cannot produce what the field means — so the shape gate is the only thing
    between it and a stored fact.
    """
    return json.dumps(
        {
            "done": False,
            # Trimmed from the audit's 23-word original so that `is_compound`
            # cannot fire first: this test is about the *shape* gate, and a
            # question rejected for its length would prove nothing about it.
            "question": "What's the gap that causes the most friction right now?",
            "target": "fact.finance.runway_alarm",
            "rationale": "cash is on their mind",
            "choices": [],
        }
    )


def _compound_question(target: str = "brain.target_customers") -> str:
    """Two complete questions in one turn — what the compound gate rejects."""
    return json.dumps(
        {
            "done": False,
            "question": "Who actually buys from you? And what do they pay?",
            "target": target,
            "rationale": "two questions, which is one too many",
            "choices": [],
        }
    )


# Wording that can actually elicit each `AnswerShape`, so a fixture targeting
# any field produces a question the shape gate accepts.
_SHAPED_QUESTION = {
    "duration": "How many days of silence before you flag it?",
    "amount": "Above what amount does that need sign-off?",
    "name": "Who signs that off?",
    "metric": "Which number in your reporting do you not trust?",
    "prose": "Who actually buys from you?",
}


def _question(target: str = "brain.target_customers") -> str:
    """A scripted question **whose wording matches its target's shape.**

    It used to be "Who actually buys from you?" for every target, which was
    fine until questions started being checked against the field they are bound
    to. `test_the_scope_stored_is_the_catalogue_s_not_the_model_s` targets
    `fact.finance.approval_threshold` — an amount — and that question asks for a
    name, so the gate rejected the fixture and the test failed on a defect it
    was not testing.

    The fixture was the thing that was wrong. Deriving the wording from the
    catalogue keeps every call site working and makes a fixture that cannot
    drift out of agreement with the rule again.
    """
    from app.ai.runtime.fields import FIELD_CATALOGUE

    shape = FIELD_CATALOGUE[target].answer_shape.value if target in FIELD_CATALOGUE else "prose"
    return json.dumps(
        {
            "done": False,
            "question": _SHAPED_QUESTION[shape],
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
    """One scripted response, replayed for every Brain group.

    `ScriptedProvider` answers per skill, not per call, so both groups see this.
    That is fine and mildly useful: `brain.profile` is in `identity` and
    `brain.goals` is in `market`, so each call keeps the key that belongs to it
    and the out-of-group filter drops the other — which is the filter being
    exercised on every run rather than only in the test written for it.
    """
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
        "DELETE FROM workspace_connection WHERE workspace_id = :w",
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


async def _reach_assembly(routes: Any, scope: ScopedSession) -> Any:
    """Walk a journey to the point where `/finish` will run, and no further.

    Three steps stand between a mid-interview session and the assembly: the
    interview has to close, then documents, then tools. `/finish` refuses to
    run before all three — so any test that calls it has to get here first,
    whether it goes on to drive the whole assembly (`_assemble`) or to break one
    stage of it deliberately.

    **The interview is closed by answering, not by writing the phase.** A helper
    that set `phase = 'documents'` directly would keep passing after the route
    stopped moving it, which is the one thing these tests exist to notice. The
    two collection steps are *skipped* rather than exercised, because no test
    that calls this is about uploading a file; the ordering itself is asserted
    in `test_the_collection_steps_come_before_the_assembly`.

    Idempotent, and safe on a journey that has already got here — each step is
    guarded on the phase, so a test that drove its own interview to close simply
    skips the first block.
    """
    from app.domain.onboarding_agent import MAX_QUESTIONS

    state = await routes.read_state(scope)

    if state.phase == "discovery":
        question = await routes.next_question(scope)
        for _ in range(MAX_QUESTIONS + 2):
            if question.done:
                break
            answered = await routes.submit_answer(
                routes.AnswerIn(text="Whatever the field is asking for"), scope
            )
            # `question` comes back null when the answer was stored but the next
            # one could not be generated — see `AnswerOut`. `/next` is the
            # endpoint that exists to be retried there.
            question = answered.question or await routes.next_question(scope)
        assert question.done, "the interview never closed, so the assembly cannot start"
        state = await routes.read_state(scope)

    if state.phase == "documents":
        state = await routes.documents_done(routes.DocumentsIn(skipped=True), scope)
    if state.phase == "tools":
        state = await routes.declare_tools(routes.ToolsIn(providers=[], skipped=True), scope)
    return state


async def _assemble(routes: Any, scope: ScopedSession) -> Any:
    """Drive the assembly to completion. One committed stage per call.

    `/finish` advances by one step per request so that each stage commits on its
    own — see the route. A test that called it once would assert against a
    session sitting in `persona`, which is not a failure but a fraction of the
    work.

    **Progress is `assembly_step`, not the phase.** The Brain is built one field
    group at a time and every group but the last leaves the row at `persona`, so
    an assertion that the phase moves on every call fails on a perfectly healthy
    second group. The counter is monotone across all of it, which is the whole
    reason it is on the wire.

    Bounded and asserted rather than `while True`: a route that stopped
    advancing would otherwise hang the suite instead of failing it.

    **It calls `_reach_assembly` first**, because `/finish` refuses to run until
    the interview has closed and both collection steps are done. Without that,
    every test that reaches the end fails on a 409 about a step it is not
    testing.
    """
    await _reach_assembly(routes, scope)
    state = await routes.finish(scope)
    for _ in range(6):
        if state.phase == "ready":
            return state
        before, step = state.phase, state.assembly_step
        state = await routes.finish(scope)
        assert (state.phase, state.assembly_step) != (before, step), (
            f"/finish did not advance from {before} at step {step}"
        )
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


def _generated(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The agent's questions, excluding the house opener.

    `/discovery` writes "What are you responsible for, day to day?" into the
    transcript as a real agent turn against `persona.stated_purpose`, so that
    the opener is counted, rendered and recoverable like every other question.
    It is not a *generated* question, though — no skill wrote it and no gate
    judged it — so a test about what the model produced must not count it.

    Filtering it here rather than in each test because the three call sites all
    assert "exactly one question was asked, and it was the fallback", and an
    off-by-one against the opener reads as the fallback logic misfiring.
    """
    return [
        r
        for r in rows
        if r["role"] == "agent"
        and r["target_field"]
        and r["target_field"] != "persona.stated_purpose"
    ]


# ── The journey ───────────────────────────────────────────────


@requires_db
async def test_the_whole_journey_completes_and_persists(
    app_db: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Start to finish: crawl, brief, discovery, one question, assemble."""
    import app.routes.onboarding_agent as routes
    from app.domain.onboarding_agent import MAX_QUESTIONS

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
            # One request, not two. The question comes back *with* the turn that
            # provoked it — `GET /next` is now only for a resumed journey or a
            # generation that failed after the answer was already stored. The
            # second request used to repeat the scope GUC, the session load, the
            # turn load and the user row purely to arrive where this one already
            # is, which against Neon is over two seconds a question.
            turn = await routes.open_discovery(routes.DiscoveryIn(answer=answer), scope)
            assert turn.question is not None
            assert turn.question.done is False
            assert turn.question.target == "brain.target_customers"

            turn = await routes.submit_answer(
                routes.AnswerIn(text="Contractors and facilities teams"), scope
            )
            state = turn.state
            assert state.answered >= 2
            # The answer is appended to the session *before* the next question is
            # generated, so the field just filled is in `already_known` and is
            # not asked again — the scripted provider only knows that one target,
            # so every later attempt is refused.
            #
            # **It does not close here, and it should not.** Refusals used to end
            # the interview, which is how an audited run asked a Head of
            # Operations nothing at all and completed. Hand-written wording is
            # served instead, so the journey continues to the ceiling. Driven to
            # whatever end it reaches rather than asserting a particular one:
            # this test is about the journey completing, and pinning the reason
            # it stopped is what made it fail on a change that fixed it.
            for _ in range(MAX_QUESTIONS + 2):
                assert turn.question is not None
                if turn.question.done:
                    break
                turn = await routes.submit_answer(
                    routes.AnswerIn(text="Whatever the field is asking for"), scope
                )
            assert turn.question is not None
            assert turn.question.done is True, "the interview never closed"
            assert (turn.question.reason or "").strip(), "closed without saying why"
            # The close moves the phase itself, and this response carries the
            # moved one. `submit_answer` evaluates the question *before* the
            # state for exactly this reason: read the other way round it
            # serialised `phase: discovery` beside `done: true`, and the screen
            # drew a composer over a finished interview.
            assert turn.state.phase == "documents"

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
        finally:
            await _cleanup(db, user, ws)


@requires_db
async def test_the_collection_steps_come_before_the_assembly(
    app_db: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Nothing is assembled until the documents and the tools steps are done.

    **The ordering is the feature, and this is where it is asserted.** The
    Persona and the Company Brain are built from whatever is in hand when
    `/finish` runs, and that call is the moment a draft becomes the artefact
    every later agent reads. Reaching it before the person has supplied their
    files and named their systems produces a Brain that has never seen either,
    and the only repair is assembling a second time — every model call paid for
    twice to arrive somewhere one pass could have reached.

    So it is a precondition read off the phase column under `FOR UPDATE`, not a
    sequence the client is trusted to follow. Four refusals and one success:

    - `/finish` from `documents` is a 409, because the steps are outstanding.
    - `/tools` from `documents` is a 409, because the documents step is first.
    - `/documents` twice is **not** an error — a double-clicked Continue is not
      a reason to refuse anybody.
    - `/tools` with a provider the catalogue does not declare is a 400, and
      writes nothing at all.
    - and after both steps, `/finish` builds the persona.

    The declarations land as `declared`, never `connected`. No OAuth flow
    exists, and a row claiming otherwise would let a tile downstream render a
    figure we have never actually read.
    """
    import app.routes.onboarding_agent as routes
    from app.domain.onboarding_agent import MAX_QUESTIONS

    _wire(monkeypatch, _provider())

    async with get_sessionmaker()() as db:
        user, ws = await _workspace(db)
        scope = _scope(user, ws)
        try:
            await routes.start(scope)
            await routes.read(scope)
            await routes.confirm_brief(routes.BriefIn(corrections={}), scope)
            turn = await routes.open_discovery(
                routes.DiscoveryIn(answer="I run the company"), scope
            )
            for _ in range(MAX_QUESTIONS + 2):
                if turn.question is None or turn.question.done:
                    break
                turn = await routes.submit_answer(routes.AnswerIn(text="Contractors"), scope)

            assert turn.question is not None and turn.question.done is True
            assert turn.state.phase == "documents"

            # 1. The assembly refuses to start.
            with pytest.raises(HTTPException) as raised:
                await routes.finish(scope)
            assert raised.value.status_code == 409
            detail = cast(dict[str, str], raised.value.detail)
            assert detail["error"] == "steps_outstanding"
            assert detail["phase"] == "documents"

            # 2. And the steps cannot be taken out of order either.
            with pytest.raises(HTTPException) as raised:
                await routes.declare_tools(routes.ToolsIn(providers=["xero"]), scope)
            assert raised.value.status_code == 409
            assert cast(dict[str, str], raised.value.detail)["error"] == "not_at_tools"

            # 3. Skipped, twice. The second is a double-click, not a fault.
            state = await routes.documents_done(routes.DocumentsIn(skipped=True), scope)
            assert state.phase == "tools"
            assert (
                await routes.documents_done(routes.DocumentsIn(skipped=True), scope)
            ).phase == "tools"

            # 4. An unknown provider is refused, and nothing is written — a
            #    partial write would leave the person unable to tell which of
            #    their five ticks failed.
            with pytest.raises(HTTPException) as raised:
                await routes.declare_tools(
                    routes.ToolsIn(providers=["hubspot", "our-internal-thing"]), scope
                )
            assert raised.value.status_code == 400
            await db.execute(
                sa.text("SELECT set_config('nexus.workspace_id', :w, true)"), {"w": str(ws)}
            )
            assert (
                await db.execute(
                    sa.text("SELECT count(*) FROM workspace_connection WHERE workspace_id = :w"),
                    {"w": str(ws)},
                )
            ).scalar_one() == 0, "a refused declaration wrote a row anyway"

            # 5. The real declaration.
            state = await routes.declare_tools(
                routes.ToolsIn(providers=["hubspot", "xero"]), scope
            )
            # The phase deliberately stays put: `/finish` is what starts the
            # assembly, and inventing a phase between the two would be
            # inventing a state whose only purpose is to be passed through.
            assert state.phase == "tools"

            await db.execute(
                sa.text("SELECT set_config('nexus.workspace_id', :w, true)"), {"w": str(ws)}
            )
            rows = (
                await db.execute(
                    sa.text(
                        "SELECT provider, state, connected_at FROM workspace_connection"
                        " WHERE workspace_id = :w ORDER BY provider"
                    ),
                    {"w": str(ws)},
                )
            ).mappings().all()
            assert [r["provider"] for r in rows] == ["hubspot", "xero"]
            assert {r["state"] for r in rows} == {"declared"}
            assert all(r["connected_at"] is None for r in rows), (
                "a declaration must never claim to be a live connection"
            )

            # Unticking one is believed. The write replaces rather than
            # appends, or a tool somebody told us they had stopped using would
            # stay on record forever.
            await routes.declare_tools(routes.ToolsIn(providers=["xero"]), scope)
            await db.execute(
                sa.text("SELECT set_config('nexus.workspace_id', :w, true)"), {"w": str(ws)}
            )
            assert (
                await db.execute(
                    sa.text(
                        "SELECT provider FROM workspace_connection WHERE workspace_id = :w"
                    ),
                    {"w": str(ws)},
                )
            ).scalars().all() == ["xero"]

            # 6. Only now does anything get built.
            assert (await routes.finish(scope)).phase == "persona"
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
            turn = await routes.open_discovery(
                routes.DiscoveryIn(answer="I run the company and I am worried about cash"), scope
            )
            assert turn.question is not None
            assert turn.question.target == "fact.finance.approval_threshold"

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
    question is refused before it is asked and the model is retried. **The
    invented field never appears in the transcript** — that is ADR 0021's
    condition and the whole assertion.

    What happens *after* the retries run out is deliberately not asserted here:
    it used to be "the interview ends", and since the fallback path was added it
    is "hand-written wording is asked instead". Both satisfy this test's
    invariant, and pinning the side effect is what made three tests fail on a
    change that improved every one of them.

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
            # Whatever is asked, it is not the invented field.
            assert question.target != "brain.annual_revenue"

            rows = await _turns(db, ws)
            assert not [r for r in rows if r["target_field"] == "brain.annual_revenue"]
            assert not [r for r in rows if "annual_revenue" in (r["text"] or "")]

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
            # The interview and the two collection steps come before any of
            # this. They are not what this test is about — see `_reach_assembly`
            # — but `/finish` will not run a stage until they are done.
            await _reach_assembly(routes, scope)

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


@requires_db
async def test_a_compound_question_is_rejected_and_regenerated(
    app_db: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two question marks in one turn never reach a person.

    An audit measured ~43% of asked questions as compound, several of them two
    complete questions with a mark each. It costs answer quality in a specific
    way — people answer the second half and drop the first, so the field is
    filled with an answer to a question it did not ask — and the skill's prompt
    already forbade it in prose. A rule ignored that often has to be a filter.

    Scripted to return the compound form every time, so the retry loop
    exhausts. What is asserted is that the two-part question never reaches the
    transcript — and, since the fallback path was added, that the hand-written
    wording is asked instead of the interview closing.
    """
    import app.routes.onboarding_agent as routes

    provider = _provider(**{"question-generation": _compound_question()})
    _wire(monkeypatch, provider)

    async with get_sessionmaker()() as db:
        user, ws = await _workspace(db)
        scope = _scope(user, ws)
        try:
            await routes.start(scope)
            await routes.read(scope)
            await routes.confirm_brief(routes.BriefIn(corrections={}), scope)
            turn = await routes.open_discovery(
                routes.DiscoveryIn(answer="I run the company and I am worried about cash"), scope
            )

            assert turn.question is not None
            assert turn.question.done is False, "the interview must not end on a rejection"

            rows = await _turns(db, ws)
            asked = _generated(rows)
            assert len(asked) == 1
            assert "And what do they pay" not in asked[0]["text"], (
                f"the compound question reached the transcript: {asked[0]['text']}"
            )

            # Retried rather than refused once — the same loop the
            # undeclared-target gate uses.
            attempts = [c for c in provider.calls if c.skill == "question-generation"]
            assert len(attempts) >= 2
        finally:
            await _cleanup(db, user, ws)


@requires_db
async def test_the_interview_never_closes_on_the_phrase_the_prompt_forbids(
    app_db: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`done` carries the agent's own reason, not a house string.

    All seven runs in the audit closed on the literal "nothing further worth
    asking" — the one phrasing `question-generation`'s prompt rules out: *"Say
    what you have enough of — not 'no further questions'."* The model was
    writing a real reason; the route was discarding it and substituting that
    line. Asserted on the ceiling path, which is the exit a completed interview
    actually takes.
    """
    import app.routes.onboarding_agent as routes
    from app.domain.onboarding_agent import MAX_QUESTIONS

    provider = _provider()
    _wire(monkeypatch, provider)

    async with get_sessionmaker()() as db:
        user, ws = await _workspace(db)
        scope = _scope(user, ws)
        try:
            await routes.start(scope)
            await routes.read(scope)
            await routes.confirm_brief(routes.BriefIn(corrections={}), scope)
            turn = await routes.open_discovery(
                routes.DiscoveryIn(answer="I run the company and I am worried about cash"), scope
            )

            # Answer until the interview closes, however it closes.
            for _ in range(MAX_QUESTIONS + 2):
                if turn.question is None or turn.question.done:
                    break
                turn = await routes.submit_answer(routes.AnswerIn(text="Contractors"), scope)

            assert turn.question is not None
            assert turn.question.done is True
            reason = (turn.question.reason or "").strip()
            assert reason, "a done verdict with no reason tells the person nothing"
            assert "nothing further worth asking" not in reason.lower()
        finally:
            await _cleanup(db, user, ws)


# ── A site that cannot be read is not a dead end ──────────────
#
# An audit of nine real company sites found two that could not be onboarded at
# all: `gusto.com` returned zero pages (bot protection) and `/start` answered
# 422. By then the account and the company row exist, so the customer was left
# permanently half-set-up with nothing on the screen to do — a signup funnel
# dropping people whose only fault is a WAF.


def _unreadable(monkeypatch: pytest.MonkeyPatch, provider: ScriptedProvider) -> None:
    """`_wire`, but the crawler finds nothing — the `gusto.com` case."""
    import app.routes.onboarding_agent as routes
    from app.domain.research import SourceState
    from app.research.runner import CrawlOutcome

    _wire(monkeypatch, provider)

    async def barren(seeds: list[str], **_: Any) -> CrawlOutcome:
        return CrawlOutcome(state=SourceState.FAILED, pages=[], error_reason="403 from the edge")

    monkeypatch.setattr(routes, "crawl_site", barren)


@requires_db
async def test_an_unreadable_site_is_reported_on_the_state_not_as_a_refusal(
    app_db: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`/start` records the failure and returns. It used to raise 422."""
    import app.routes.onboarding_agent as routes

    _unreadable(monkeypatch, _provider())

    async with get_sessionmaker()() as db:
        user, ws = await _workspace(db)
        scope = _scope(user, ws)
        try:
            state = await routes.start(scope)
            assert state.site_unreadable is True
            assert state.pages_read == []
            # Still `analysing`: nothing has been established yet, and the
            # screen distinguishes the two on the flag rather than the phase.
            assert state.phase == "analysing"

            # `/read` must not send them round the loop `/start` just finished.
            with pytest.raises(HTTPException) as raised:
                await routes.read(scope)
            assert raised.value.status_code == 409
            # `HTTPException.detail` is annotated `str`, but every refusal in
            # this router sends a dict of `{error, message}` — see `_unusable`.
            # Cast rather than reshape the route: the dict is the contract the
            # web client reads (`messageFrom` handles exactly this shape).
            detail = cast(dict[str, str], raised.value.detail)
            assert detail["error"] == "site_unreadable"
        finally:
            await _cleanup(db, user, ws)


@requires_db
async def test_a_described_company_reaches_the_interview_with_its_facts_stored(
    app_db: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The founder supplies the brief and the interview carries on.

    Three assertions, and the third is the point: the answers are stored
    against their **declared** fields, so a manual brief is a different
    *source* rather than a different kind of fact. It goes straight to
    `discovery` — there is nothing to confirm in three sentences somebody just
    typed.
    """
    import app.routes.onboarding_agent as routes

    _unreadable(monkeypatch, _provider())

    async with get_sessionmaker()() as db:
        user, ws = await _workspace(db)
        scope = _scope(user, ws)
        try:
            await routes.start(scope)
            state = await routes.describe(
                routes.DescribeIn(
                    profile="We sell industrial valves to contractors in Muscat.",
                    target_customers="Mechanical contractors and facilities teams.",
                    goals="Double the service contract base.",
                ),
                scope,
            )

            assert state.phase == "discovery", "the brief step has nothing to confirm here"

            # **The full interview, not two questions.** These three answers
            # must not count against `MAX_QUESTIONS`: an audit measured
            # `answered: 6, ceiling: 5` after two real questions, because the
            # describe agent turns carried a target and `asked` counts those.
            # The customers on this path are the ones whose site could not be
            # read — least is known about them, so they need more questions,
            # not three fewer.
            from app.domain.onboarding_agent import MAX_QUESTIONS
            from app.routes.onboarding_agent import _load, _rehydrate

            async with scoped_connection(scope) as probe:
                rehydrated = _rehydrate(await _load(probe, scope))
            assert rehydrated.asked == 0, (
                f"describe spent {rehydrated.asked} of {MAX_QUESTIONS} interview questions"
            )

            rows = await _turns(db, ws)
            stored = {
                r["target_field"]: r["text"]
                for r in rows
                if r["role"] == "user" and r["target_field"]
            }
            assert stored["brain.profile"].startswith("We sell industrial valves")
            assert "contractors" in stored["brain.target_customers"].lower()
            assert "service contract" in stored["brain.goals"].lower()

            # The scope is the catalogue's, exactly as for an interview answer.
            from app.ai.runtime.fields import resolve

            for row in rows:
                if row["role"] == "user" and row["target_field"]:
                    assert row["scope"] == resolve(row["target_field"]).scope

            # And the interview proceeds: `company_profile` grounding exists, so
            # discovery has something to interpret against.
            turn = await routes.open_discovery(
                routes.DiscoveryIn(answer="I run the company and I am worried about cash"), scope
            )
            assert turn.state.phase == "discovery"
        finally:
            await _cleanup(db, user, ws)


@requires_db
async def test_describe_is_refused_when_the_site_was_readable(
    app_db: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """It is a fallback, not a way to skip the read.

    The read is what makes the brief *correctable* rather than merely typed, so
    a caller who could reach `/describe` on a readable site could opt out of
    the one step that grounds the Brain in something checkable.
    """
    import app.routes.onboarding_agent as routes

    _wire(monkeypatch, _provider())

    async with get_sessionmaker()() as db:
        user, ws = await _workspace(db)
        scope = _scope(user, ws)
        try:
            await routes.start(scope)
            with pytest.raises(HTTPException) as raised:
                await routes.describe(
                    routes.DescribeIn(profile="x", target_customers="y", goals="z"), scope
                )
            assert raised.value.status_code == 409
            assert cast(dict[str, str], raised.value.detail)["error"] == "site_was_readable"
        finally:
            await _cleanup(db, user, ws)


@requires_db
async def test_a_crawler_that_raises_is_treated_as_an_unreadable_site(
    app_db: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`crawl_site` is documented never to raise. This is the net under that.

    The audit's second unonboardable site returned a 500 twice. This is the
    first request of a customer's life in the product and the account already
    exists by the time it runs, so an exception here is the one that cannot be
    allowed to become a dead end — whatever the crawler's contract says today.
    """
    import app.routes.onboarding_agent as routes

    _wire(monkeypatch, _provider())

    async def explode(seeds: list[str], **_: Any) -> Any:
        raise RuntimeError("the edge hung up")

    monkeypatch.setattr(routes, "crawl_site", explode)

    async with get_sessionmaker()() as db:
        user, ws = await _workspace(db)
        scope = _scope(user, ws)
        try:
            state = await routes.start(scope)
            assert state.site_unreadable is True
        finally:
            await _cleanup(db, user, ws)


def test_undecodable_page_text_is_not_mistaken_for_prose() -> None:
    """`berkshirehathaway.com`, measured.

    The audit's second unonboardable site. The crawl **succeeded** — one page,
    no error — and returned 1459 characters of which 624 were U+FFFD and six
    were NUL. Postgres refused the row (`jsonb` cannot hold `\u0000`) and
    onboarding answered 500, twice. Had it stored, a model would have been
    handed it as the company's own description of itself.
    """
    from app.research.runner import is_prose

    assert is_prose("We sell industrial valves to contractors in Muscat.")
    # One bad character in real prose is still prose, and worth keeping.
    assert is_prose("We sell valves\ufffd to contractors in Muscat, Oman, and beyond.")

    assert not is_prose("")
    assert not is_prose("   ")
    # A NUL is not a ratio question: it is also what makes the row unstorable.
    assert not is_prose("hello\x00world")
    # The shape actually measured: about half the string unusable.
    assert not is_prose("a\ufffd" * 50)


@requires_db
async def test_a_page_of_undecodable_bytes_reaches_the_manual_brief_not_a_500(
    app_db: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The whole `berkshirehathaway.com` path, through the route.

    A crawl that "succeeds" with an unreadable body must land in exactly the
    same place as one that returns nothing: the founder is asked. The `try`
    around `crawl_site` cannot catch this on its own, because nothing raised
    until the write.
    """
    import app.routes.onboarding_agent as routes
    from app.domain.research import SourceState
    from app.research.runner import CrawlOutcome

    _wire(monkeypatch, _provider())

    async def binary(seeds: list[str], **_: Any) -> CrawlOutcome:
        return CrawlOutcome(
            state=SourceState.SUCCEEDED,
            pages=[{"url": "https://berkshirehathaway.com", "text": "\x13\ufffd\x15\x00" * 60}],
        )

    monkeypatch.setattr(routes, "crawl_site", binary)

    async with get_sessionmaker()() as db:
        user, ws = await _workspace(db)
        scope = _scope(user, ws)
        try:
            state = await routes.start(scope)
            assert state.site_unreadable is True
            assert state.pages_read == [], "undecodable bytes must not be offered as a page read"

            # And it recovers, rather than needing the account thrown away.
            state = await routes.describe(
                routes.DescribeIn(
                    profile="A holding company.",
                    target_customers="Shareholders and acquired operating businesses.",
                    goals="Compound book value.",
                ),
                scope,
            )
            assert state.phase == "discovery"
        finally:
            await _cleanup(db, user, ws)


async def _set_stated_department(
    db: AsyncSession, *, user: UUID, ws: UUID, value: str
) -> None:
    """Write `membership.stated_department`, with the scoping GUC set.

    `membership` is under row-level security and `nexus_app` is `NOBYPASSRLS`,
    so an `UPDATE` with no `nexus.workspace_id` matches **zero rows and raises
    nothing** — it reports success having changed nothing. The first version of
    these tests did exactly that and failed on a `None` that looked like a bug
    in the resolver rather than a missing GUC. `set_config(..., true)` is
    transaction-local, which is why it cannot be inherited from `_workspace`.
    """
    await db.execute(
        sa.text("SELECT set_config('nexus.workspace_id', :w, true)"), {"w": str(ws)}
    )
    await db.execute(
        sa.text(
            "UPDATE membership SET stated_department = :d"
            " WHERE user_id = :u AND workspace_id = :w"
        ),
        {"d": value, "u": str(user), "w": str(ws)},
    )
    # Read back rather than trusting `rowcount`: the async `Result` does not
    # expose it, and a silent no-op is the failure being guarded against —
    # `membership` is under RLS and `nexus_app` is `NOBYPASSRLS`, so an UPDATE
    # with no `nexus.workspace_id` matches zero rows and raises nothing.
    written = (
        await db.execute(
            sa.text(
                "SELECT stated_department FROM membership"
                " WHERE user_id = :u AND workspace_id = :w"
            ),
            {"u": str(user), "w": str(ws)},
        )
    ).scalar_one_or_none()
    assert written == value, "the update did not land — is the scoping GUC set?"
    await db.commit()


@requires_db
async def test_the_greeting_says_the_department_label_not_its_key(
    app_db: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """"in People", never "in hr".

    The stored value is the catalogue key, because narrowing the question
    catalogue needs the machine-readable form. The greeting needs the other
    one, and a browser caught this reading **"you work at Gusto as Head of
    People, in hr"** — the resolution existed but lived only in `_viewer`,
    while `_state` built its own `ViewerOut` and bypassed it. Asserted on
    `/start`, which goes through `_state`.
    """
    import app.routes.onboarding_agent as routes

    _wire(monkeypatch, _provider())

    async with get_sessionmaker()() as db:
        user, ws = await _workspace(db)
        # `hr` is the pair that proves it: the key and the label differ.
        await _set_stated_department(db, user=user, ws=ws, value="hr")
        scope = _scope(user, ws)
        try:
            state = await routes.start(scope)
            assert state.viewer.department == "People"
        finally:
            await _cleanup(db, user, ws)


@requires_db
async def test_free_text_from_before_the_dropdown_is_left_alone(
    app_db: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Somebody who typed "Design" is still in Design.

    The field was free text before it was a select, so rows hold words that are
    not catalogue keys. Rewriting one into the nearest official department
    would put a claim in that person's mouth on the first line they read.
    """
    import app.routes.onboarding_agent as routes

    _wire(monkeypatch, _provider())

    async with get_sessionmaker()() as db:
        user, ws = await _workspace(db)
        await _set_stated_department(db, user=user, ws=ws, value="Design")
        scope = _scope(user, ws)
        try:
            state = await routes.start(scope)
            assert state.viewer.department == "Design"
        finally:
            await _cleanup(db, user, ws)


@requires_db
async def test_a_question_that_cannot_elicit_its_field_never_reaches_the_person(
    app_db: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """F3, through the routes and the database.

    `fact.finance.runway_alarm` means "how many months of runway would change
    your plans". The audited question asked what causes the most friction — so a
    free-text complaint would have been stored as a runway threshold, with full
    provenance, and the next turn quoted it back as "that nine-month runway
    threshold": a number the person never gave.

    The target is declared and in this turn's offered set, so neither existing
    gate catches it. What is asserted is that **this** question never reaches
    the transcript — and, since the fallback path was added, that the person is
    asked the hand-written wording instead of nothing.
    """
    import app.routes.onboarding_agent as routes

    provider = _provider(**{"question-generation": _mismatched_question()})
    _wire(monkeypatch, provider)

    async with get_sessionmaker()() as db:
        user, ws = await _workspace(db)
        # Finance, so the target is in this user's own department and the
        # narrowing cannot be what rejects it.
        await _set_stated_department(db, user=user, ws=ws, value="finance")
        scope = _scope(user, ws)
        try:
            await routes.start(scope)
            await routes.read(scope)
            await routes.confirm_brief(routes.BriefIn(corrections={}), scope)
            turn = await routes.open_discovery(
                routes.DiscoveryIn(answer="I run finance and cash visibility is the problem"),
                scope,
            )

            assert turn.question is not None
            assert turn.question.done is False, "the interview must not end on a rejection"

            rows = await _turns(db, ws)
            asked = _generated(rows)
            assert len(asked) == 1
            assert "friction" not in asked[0]["text"], (
                f"the mismatched question was stored: {asked[0]['text']}"
            )

            from app.ai.runtime.fields import FIELD_CATALOGUE

            target = asked[0]["target_field"]
            assert asked[0]["text"] == FIELD_CATALOGUE[target].fallback_question

            # Retried, using the same loop the undeclared-target gate uses.
            attempts = [c for c in provider.calls if c.skill == "question-generation"]
            assert len(attempts) >= 2
        finally:
            await _cleanup(db, user, ws)


@requires_db
async def test_an_interview_never_ends_because_the_model_kept_failing(
    app_db: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The Operations case: asked nothing, and completed anyway.

    Round 2 of the audit found three of six interviews ending on rejection
    exhaustion — Finance after one question, Chief of Staff after two,
    **Operations after none** — each reported to the person as a decision to
    stop rather than a failure to ask.

    Scripted so the model can *never* produce an acceptable question: every
    attempt returns the audited compound question, so both the compound and the
    shape gates fire on every try. What is asserted is that the person is still
    asked something, that it belongs to their own department, and that it is the
    hand-written wording.
    """
    import app.routes.onboarding_agent as routes

    provider = _provider(**{"question-generation": _compound_question()})
    _wire(monkeypatch, provider)

    async with get_sessionmaker()() as db:
        user, ws = await _workspace(db)
        await _set_stated_department(db, user=user, ws=ws, value="operations")
        scope = _scope(user, ws)
        try:
            await routes.start(scope)
            await routes.read(scope)
            await routes.confirm_brief(routes.BriefIn(corrections={}), scope)
            turn = await routes.open_discovery(
                routes.DiscoveryIn(answer="I run operations and shipments keep slipping"),
                scope,
            )

            assert turn.question is not None
            assert turn.question.done is False, (
                "the interview ended without asking anything — this is the Operations case"
            )
            assert turn.question.target is not None
            assert turn.question.target.startswith("fact.operations."), (
                f"a fallback served {turn.question.target}, not an Operations field"
            )

            from app.ai.runtime.fields import FIELD_CATALOGUE

            expected = FIELD_CATALOGUE[turn.question.target].fallback_question
            assert turn.question.question == expected, "not the hand-written wording"

            # It reached the person, at the catalogue's scope.
            rows = await _turns(db, ws)
            asked = _generated(rows)
            assert len(asked) == 1
            assert asked[0]["scope"] == FIELD_CATALOGUE[turn.question.target].scope

            # And the model was genuinely given more than three chances first.
            attempts = [c for c in provider.calls if c.skill == "question-generation"]
            assert len(attempts) >= 4, f"only {len(attempts)} attempts before falling back"
        finally:
            await _cleanup(db, user, ws)


@pytest.mark.requires_db
@pytest.mark.anyio
async def test_the_opening_question_is_in_the_transcript(
    app_db: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The one question everybody is asked was the one question never recorded.

    It was rendered by `AgentOnboarding.tsx` and never stored, which cost three
    things at once and each looked like a different bug:

    - the transcript opened on an answer with no question above it;
    - `_rehydrate` counts `asked` as agent turns carrying a target, so the
      opener went uncounted and `MAX_QUESTIONS = 5` allowed a sixth question —
      observed live, with `onboarding.ceiling asked=5` logged after the sixth;
    - the progress rail read "Question 5 of 5" with the sixth on screen.

    All three are the same missing row, so this asserts the row: the opener is
    an agent turn, it carries the field its answer is stored against, and the
    answer follows it immediately.
    """
    import app.routes.onboarding_agent as routes
    from app.ai.runtime.fields import FIELD_CATALOGUE

    _wire(monkeypatch, _provider())

    async with get_sessionmaker()() as db:
        user, ws = await _workspace(db)
        scope = _scope(user, ws)
        try:
            await routes.start(scope)
            await routes.read(scope)
            await routes.confirm_brief(routes.BriefIn(corrections={}), scope)
            await routes.open_discovery(
                routes.DiscoveryIn(answer="I run the depot network and chase customs"), scope
            )

            rows = await _turns(db, ws)
            pair = [r for r in rows if r["target_field"] == "persona.stated_purpose"]
            assert [r["role"] for r in pair] == ["agent", "user"], (
                f"expected the opener then its answer, got {[r['role'] for r in pair]}"
            )
            assert pair[0]["text"] == FIELD_CATALOGUE["persona.stated_purpose"].fallback_question
            assert pair[1]["seq"] == pair[0]["seq"] + 1, "the answer must follow its question"
        finally:
            await _cleanup(db, user, ws)


# ── Promotion: the answers reach tables other agents read ─────
#
# Two audits found the same thing: `INSERT INTO fact` existed nowhere in the
# repository, `company_brain` was fed only from `onboarding_answer` (whose sole
# writer is the retired wizard), `persona` only from the spine's own chat route,
# and stage three of the assembly *overwrote* the one place the built Brain was
# held. Everything the interview collected terminated in a draft column.


@requires_db
async def test_a_finished_journey_writes_the_brain_the_facts_and_the_persona(
    app_db: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The whole point of asking the questions.

    Driven through the routes to `ready`, then read straight from the
    authoritative tables — not from the session row, which is exactly what used
    to be mistaken for having stored something.
    """
    import app.routes.onboarding_agent as routes
    from app.domain.onboarding_agent import MAX_QUESTIONS

    _wire(monkeypatch, _provider())

    async with get_sessionmaker()() as db:
        user, ws = await _workspace(db)
        await _set_stated_department(db, user=user, ws=ws, value="finance")
        scope = _scope(user, ws)
        try:
            await routes.start(scope)
            await routes.read(scope)
            await routes.confirm_brief(routes.BriefIn(corrections={}), scope)
            turn = await routes.open_discovery(
                routes.DiscoveryIn(answer="I run finance and cash visibility is the problem"),
                scope,
            )
            for _ in range(MAX_QUESTIONS + 2):
                assert turn.question is not None
                if turn.question.done:
                    break
                turn = await routes.submit_answer(routes.AnswerIn(text="OMR 25,000"), scope)

            state = await _assemble(routes, scope)
            assert state.phase == "ready"

            await db.execute(
                sa.text("SELECT set_config('nexus.workspace_id', :w, true)"), {"w": str(ws)}
            )

            # ── company_brain ──
            brain = (
                await db.execute(
                    sa.text(
                        "SELECT version, profile, provenance, generated_by, superseded_at"
                        " FROM company_brain WHERE workspace_id = :w"
                    ),
                    {"w": str(ws)},
                )
            ).mappings().all()
            assert len(brain) == 1, "a finished journey must leave exactly one current brain"
            assert brain[0]["superseded_at"] is None
            # `ck_company_brain_grounded_has_provenance`: a brain that cannot
            # point at anything is only allowed to exist as `unavailable`.
            if brain[0]["generated_by"] != "unavailable":
                assert brain[0]["provenance"], "a grounded brain with no provenance"

            # ── brain_version, and the fact rows hanging off it ──
            version = (
                await db.execute(
                    sa.text(
                        "SELECT id, version FROM brain_version WHERE workspace_id = :w"
                    ),
                    {"w": str(ws)},
                )
            ).mappings().one()
            assert version["version"] == brain[0]["version"], (
                "the fact layer and the prose brain must name the same generation"
            )

            facts = (
                await db.execute(
                    sa.text(
                        "SELECT key, value, source_kind, precedence, confidence,"
                        "       source_ref, brain_version_id, confirmed_by_user_id,"
                        "       confirmed_at"
                        " FROM fact WHERE workspace_id = :w"
                    ),
                    {"w": str(ws)},
                )
            ).mappings().all()
            assert facts, "the interview collected department facts and stored none"

            from app.domain.facts import SourceKind, rank

            for fact in facts:
                assert fact["key"].startswith("fact.")
                # A person typed it, so it outranks a crawl, an inference and a
                # document — read from the rank, never a written-out number.
                assert fact["source_kind"] == SourceKind.USER_CONFIRMED.value
                assert fact["precedence"] == rank(SourceKind.USER_CONFIRMED)
                assert fact["confidence"] == 1.0
                assert fact["source_ref"].startswith("onboarding_session:")
                assert fact["brain_version_id"] == version["id"]
                # `ck_fact_confirmation_is_whole` — both or neither.
                assert (fact["confirmed_by_user_id"] is None) == (
                    fact["confirmed_at"] is None
                )
                assert fact["confirmed_by_user_id"] == user

            # ── persona ──
            persona = (
                await db.execute(
                    sa.text(
                        "SELECT stated_purpose, priority_topics, language, timezone"
                        " FROM persona WHERE workspace_id = :w AND user_id = :u"
                    ),
                    {"w": str(ws), "u": str(user)},
                )
            ).mappings().one()
            assert persona["priority_topics"], "the persona reached no row"
            # NOT NULL columns with defaults must not be nulled by an insert
            # that names them — the spine route learned this the hard way.
            assert persona["language"]
            assert persona["timezone"]
        finally:
            await _cleanup(db, user, ws)


@requires_db
async def test_a_failed_assembly_stage_does_not_claim_nothing_was_saved(
    app_db: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """V5. The message used to be a lie, and the lie cost work.

    `/finish` commits one stage per request precisely so a later failure keeps
    the earlier ones — `test_a_failed_stage_keeps_the_stages_before_it` proves
    that half. But every 502 said "Nothing was saved", which invites the person
    to start over, and starting over is the only thing that would actually lose
    the persona and Brain already on the row.

    Asserted on the *third* stage, so there is real committed progress behind
    the failure.
    """
    import app.routes.onboarding_agent as routes
    from app.domain.onboarding_agent import MAX_QUESTIONS

    provider = _provider()
    _wire(monkeypatch, provider)

    async with get_sessionmaker()() as db:
        user, ws = await _workspace(db)
        scope = _scope(user, ws)
        try:
            await routes.start(scope)
            await routes.read(scope)
            await routes.confirm_brief(routes.BriefIn(corrections={}), scope)
            turn = await routes.open_discovery(
                routes.DiscoveryIn(answer="I run the company and I am worried about cash"), scope
            )
            for _ in range(MAX_QUESTIONS + 2):
                assert turn.question is not None
                if turn.question.done:
                    break
                turn = await routes.submit_answer(routes.AnswerIn(text="Contractors"), scope)

            # Documents and tools first: `/finish` will not build anything until
            # they are done. Both skipped — this test is about a failing
            # assembly stage, not about either step.
            await _reach_assembly(routes, scope)

            # Persona, then the Brain groups — every stage but the last.
            state = await routes.finish(scope)
            for _ in range(6):
                if state.phase == "assembling":
                    break
                state = await routes.finish(scope)
            assert state.phase == "assembling", "did not reach the last stage"

            # Now break only that stage. `ScriptedProvider` raises on a skill it
            # was not given, which is the failure this is about.
            monkeypatch.setattr(
                routes,
                "get_provider",
                lambda: _provider(**{"context-personalization": "{ not json"}),
            )
            with pytest.raises(HTTPException) as raised:
                await routes.finish(scope)

            assert raised.value.status_code == 502
            detail = cast(dict[str, Any], raised.value.detail)
            assert detail["error"] == "skill_failed"
            assert "Nothing was saved" not in detail["message"], (
                "the persona and the Brain are on the row; saying otherwise costs work"
            )
            assert "saved" in detail["message"], "it must say the earlier steps are kept"
            assert detail["retryable"] is True

            # And the progress really is still there.
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
            assert row["phase"] == "assembling", "the failure moved the phase backwards"
            assert row["status"] == "active"
            assert row["persona_draft"], "the committed persona was lost"
        finally:
            await _cleanup(db, user, ws)


@requires_db
async def test_next_re_serves_an_outstanding_question_instead_of_asking_twice(
    app_db: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R2. A refresh mid-question used to duplicate it and orphan the first.

    `AgentOnboarding` calls `nextQuestion()` on every resume into `discovery`,
    and `_ask_next` generated unconditionally. An audited transcript shows two
    agent turns for `fact.hr.leave_basis` in a row: `submit_answer` reads the
    target from the *last* agent turn, so the first became unanswerable, and
    `asked` counts agent turns carrying a target, so five turns for three real
    questions tripped the ceiling.

    Asserted three ways — the same question comes back, no second turn is
    written, and no extra model call is spent.
    """
    import app.routes.onboarding_agent as routes

    provider = _provider()
    _wire(monkeypatch, provider)

    async with get_sessionmaker()() as db:
        user, ws = await _workspace(db)
        scope = _scope(user, ws)
        try:
            await routes.start(scope)
            await routes.read(scope)
            await routes.confirm_brief(routes.BriefIn(corrections={}), scope)
            turn = await routes.open_discovery(
                routes.DiscoveryIn(answer="I run the company and I am worried about cash"), scope
            )
            assert turn.question is not None and turn.question.done is False
            first = turn.question

            calls_before = len([c for c in provider.calls if c.skill == "question-generation"])
            rows_before = await _turns(db, ws)

            # What a page refresh does.
            again = await routes.next_question(scope)
            once_more = await routes.next_question(scope)

            assert again.target == first.target
            assert again.question == first.question
            assert once_more.target == first.target

            rows_after = await _turns(db, ws)
            assert len(rows_after) == len(rows_before), "a refresh wrote a duplicate turn"

            calls_after = len([c for c in provider.calls if c.skill == "question-generation"])
            assert calls_after == calls_before, "a refresh spent a model call"

            # And the answer still binds to it.
            turn = await routes.submit_answer(routes.AnswerIn(text="Contractors"), scope)
            answered = [
                r for r in await _turns(db, ws)
                if r["role"] == "user" and r["target_field"] == first.target
            ]
            assert len(answered) == 1
        finally:
            await _cleanup(db, user, ws)


@requires_db
async def test_no_field_is_ever_asked_twice_in_one_interview(
    app_db: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The transcript-level invariant, which is what a person actually sees.

    Round 3 found `fact.hr.leave_basis` asked three times and answered twice.
    Driven with a `/next` between every answer — the pattern that produced it.
    """
    import app.routes.onboarding_agent as routes
    from app.domain.onboarding_agent import MAX_QUESTIONS

    _wire(monkeypatch, _provider())

    async with get_sessionmaker()() as db:
        user, ws = await _workspace(db)
        await _set_stated_department(db, user=user, ws=ws, value="hr")
        scope = _scope(user, ws)
        try:
            await routes.start(scope)
            await routes.read(scope)
            await routes.confirm_brief(routes.BriefIn(corrections={}), scope)
            turn = await routes.open_discovery(
                routes.DiscoveryIn(answer="I run people ops and attrition is the problem"), scope
            )
            for _ in range(MAX_QUESTIONS + 3):
                assert turn.question is not None
                if turn.question.done:
                    break
                # A refresh before every answer.
                await routes.next_question(scope)
                turn = await routes.submit_answer(routes.AnswerIn(text="Monthly"), scope)

            rows = await _turns(db, ws)
            asked = [r["target_field"] for r in rows if r["role"] == "agent" and r["target_field"]]
            assert len(asked) == len(set(asked)), f"a field was asked twice: {asked}"
            answered = [
                r["target_field"] for r in rows if r["role"] == "user" and r["target_field"]
            ]
            assert len(answered) == len(set(answered)), f"a field was answered twice: {answered}"
        finally:
            await _cleanup(db, user, ws)


@requires_db
async def test_the_dashboard_sees_what_the_interview_collected(
    app_db: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R1, the highest-value defect of round 3.

    Promotion writes `fact`; the dashboard's "questions still unanswered"
    counter read `onboarding_answer`, whose only writer is the retired setup
    wizard. So a Head of Operations answered every operational threshold in the
    interview and was then told five questions were outstanding — three rounds
    of work on which questions to ask, invisible to the person answering them.

    Driven all the way to `ready`, because the counter must move only once the
    answers are *promoted*, not merely typed.
    """
    import app.routes.dashboards as dashboards
    import app.routes.onboarding_agent as routes
    from app.domain.onboarding_agent import MAX_QUESTIONS

    _wire(monkeypatch, _provider())

    async with get_sessionmaker()() as db:
        user, ws = await _workspace(db)
        await _set_stated_department(db, user=user, ws=ws, value="operations")
        scope = _scope(user, ws)
        try:
            before = await dashboards.answered_questions(scope)
            assert not any(d == "operations" for d, _ in before)

            await routes.start(scope)
            await routes.read(scope)
            await routes.confirm_brief(routes.BriefIn(corrections={}), scope)
            turn = await routes.open_discovery(
                routes.DiscoveryIn(answer="I run operations and shipments keep slipping"), scope
            )
            for _ in range(MAX_QUESTIONS + 3):
                assert turn.question is not None
                if turn.question.done:
                    break
                turn = await routes.submit_answer(
                    routes.AnswerIn(text="Forty-eight hours"), scope
                )

            # Still nothing: the answers are on the session, not promoted.
            mid = await dashboards.answered_questions(scope)
            assert not any(d == "operations" for d, _ in mid), (
                "the counter moved before the answers were promoted"
            )

            state = await _assemble(routes, scope)
            assert state.phase == "ready"

            after = await dashboards.answered_questions(scope)
            ops = {q for d, q in after if d == "operations"}
            assert ops, "the dashboard still cannot see a promoted interview answer"

            # Every pair names a real bank question, or the counter would never
            # reach zero however many questions were answered.
            from app.domain.question_bank import BY_DEPARTMENT

            bank = {q.key for q in BY_DEPARTMENT["operations"]}
            assert ops <= bank, f"answered keys that no bank question has: {ops - bank}"
        finally:
            await _cleanup(db, user, ws)


def test_every_bank_mapping_names_a_real_question() -> None:
    """`FieldSpec.question_key` is the join between two answering surfaces.

    A typo here is silent in the worst way: the fact is stored, the dashboard
    never marks the question answered, and the founder is asked again for
    something they already told us.
    """
    from app.ai.runtime.fields import askable_fields
    from app.domain.question_bank import BY_DEPARTMENT

    mapped = [s for s in askable_fields(None) if s.question_key]
    assert len(mapped) >= 15, "too few mappings for this to prove anything"
    for spec in mapped:
        assert spec.department, f"{spec.key} maps to a bank question but has no department"
        bank = {q.key for q in BY_DEPARTMENT.get(spec.department, ())}
        assert spec.question_key in bank, (
            f"{spec.key} -> {spec.question_key!r} is not a question in {spec.department}"
        )


def test_promoted_facts_reach_the_preamble_without_being_reworded() -> None:
    """R3. The thresholds were in `fact` and absent from the context.

    Every later agent is handed the preamble before it answers anything. A
    completed journey's `context.facts` held only brain and persona keys, so an
    agent reading it did not know the promised lead time — the single most
    actionable thing the interview collected.

    Added in code, not asked of the model: a threshold must not be paraphrased.
    """
    from app.routes.onboarding_agent import _with_promoted_facts

    context = {
        "preamble": "…",
        "facts": [
            {"key": "brain.profile", "value": "Container logistics.", "scope": 1},
            # The duplicate an audited preamble actually carried.
            {"key": "persona.priority_topics", "value": "Delays", "scope": 5},
            {"key": "persona.priority_topics", "value": "Delays", "scope": 5},
        ],
    }
    answers = {
        "fact.operations.lead_time": "Forty-eight hours from vessel discharge.",
        "fact.operations.late_rule": "Twelve hours past the promised window.",
        "brain.goals": "Schedule reliability.",  # not a fact.* key
        "fact.operations.supplier_risk": "   ",  # empty, so nothing to say
    }

    out = _with_promoted_facts(dict(context), answers)
    by_key = {f["key"]: f for f in out["facts"]}

    assert by_key["fact.operations.lead_time"]["value"] == (
        "Forty-eight hours from vessel discharge."
    ), "the threshold was reworded"
    assert by_key["fact.operations.late_rule"]["scope"] == 3, "the catalogue scope travels with it"
    assert "brain.goals" not in by_key, "only fact.* is promoted here"
    assert "fact.operations.supplier_risk" not in by_key, "an empty answer is not a fact"

    keys = [f["key"] for f in out["facts"]]
    assert len(keys) == len(set(keys)), f"duplicate key in the preamble: {keys}"
    # What the personalisation already said about a key wins.
    assert by_key["brain.profile"]["value"] == "Container logistics."


@requires_db
async def test_a_department_cannot_finish_with_none_of_its_own_facts(
    app_db: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R6. The floor was only on the rejection path.

    `next_fallback` prefers the answerer's department, so exhausting the retries
    could not leave Operations with nothing — but the model saying `done` and
    the ceiling tripping both returned without looking at what was collected.

    Scripted so the model always targets a *shared* field, which is legal and
    which a real model can do for all five turns: nine of the twelve fields a
    department is shown are shared. Without a floor this run ends with zero
    `fact.operations.*` and `_record_facts` writes nothing.
    """
    import app.routes.onboarding_agent as routes
    from app.domain.onboarding_agent import MAX_QUESTIONS

    _wire(monkeypatch, _provider(**{"question-generation": _question("brain.goals")}))

    async with get_sessionmaker()() as db:
        user, ws = await _workspace(db)
        await _set_stated_department(db, user=user, ws=ws, value="operations")
        scope = _scope(user, ws)
        try:
            await routes.start(scope)
            await routes.read(scope)
            await routes.confirm_brief(routes.BriefIn(corrections={}), scope)
            turn = await routes.open_discovery(
                routes.DiscoveryIn(answer="I run operations and shipments keep slipping"), scope
            )
            for _ in range(MAX_QUESTIONS + 4):
                assert turn.question is not None
                if turn.question.done:
                    break
                turn = await routes.submit_answer(routes.AnswerIn(text="Forty-eight hours"), scope)

            rows = await _turns(db, ws)
            answered = {
                r["target_field"] for r in rows if r["role"] == "user" and r["target_field"]
            }
            own = {k for k in answered if k.startswith("fact.operations.")}
            assert own, (
                "the interview ended with no operational fact at all — "
                f"answered: {sorted(answered)}"
            )
        finally:
            await _cleanup(db, user, ws)
