"""The onboarding spine: resumable, department-driven, and honest about doubt.

`doc/12` §Phase 6. Three properties, and each replaces something the
single-page wizard could not do.

**Resumable** (Q28). Onboarding asks a founder for things they have to go and
find — a fiscal year start, a list of goals they have not written down. Any flow
that demands it in one sitting will be abandoned in the middle, and the abandoned
state has to be worth returning to.

**Department selection drives the product** (Q22, Q63). The seven directors are
not a menu of features; the selected set decides which dashboards exist at all.
Chief of Staff is automatic (Q24) because it consumes the others — a company
that selected none of them would have nothing for it to read.

**"Not sure yet" records an assumption, not a null.** This is the one that
matters most and is easiest to get wrong. A null says nobody was asked. An
assumption says somebody was asked, did not know, and the product proceeded on a
stated basis — which is a fact the Brain can later contradict with evidence, and
a null is not. It is also the difference between a blank dashboard tile and one
that says what it is assuming.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import get_engine, get_sessionmaker
from tests.dburl import async_database_url

if TYPE_CHECKING:
    from app.domain.session import ScopedSession

ASYNC_DB_URL = async_database_url()
requires_db = pytest.mark.requires_db


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


async def _workspace(db: AsyncSession) -> tuple[UUID, UUID]:
    """A workspace and its owner, committed."""
    user, tenant, ws = uuid4(), uuid4(), uuid4()
    await db.execute(
        sa.text("INSERT INTO app_user (id, email) VALUES (:i,:e)"),
        {"i": str(user), "e": f"spine-{user.hex[:8]}@example.com"},
    )
    await db.execute(sa.text("INSERT INTO tenant (id, name) VALUES (:i,'T')"), {"i": str(tenant)})
    await db.execute(sa.text("SELECT set_config('nexus.workspace_id', :w, true)"), {"w": str(ws)})
    await db.execute(
        sa.text(
            "INSERT INTO workspace (id, workspace_id, tenant_id, name, domain,"
            " domain_verified_at) VALUES (:i,:i,:t,'W',:d, now())"
        ),
        {"i": str(ws), "t": str(tenant), "d": f"spine-{ws.hex[:8]}.om"},
    )
    await db.execute(
        sa.text(
            "INSERT INTO membership (workspace_id, user_id, role, departments)"
            " VALUES (:w,:u,'owner', ARRAY['executive']::text[])"
        ),
        {"w": str(ws), "u": str(user)},
    )
    await db.commit()
    return user, ws


def _owner_scope(user: UUID, ws: UUID) -> ScopedSession:
    """The founder, in their own workspace, holding every department.

    Owner rather than a manager because these three tests are about the
    *company's* shape — which departments it runs, and what a blank answer
    means — and an owner is the caller for whom the permission lattice never
    refuses. If a check still fires for an owner, it is not a permission check.
    """
    from app.domain.scopes import Department, Role
    from app.domain.session import ScopedSession

    return ScopedSession(
        user_id=user,
        tenant_id=uuid4(),
        workspace_id=ws,
        role=Role.OWNER,
        departments=frozenset(Department),
    )


async def _cleanup(db: AsyncSession, user: UUID, ws: UUID) -> None:
    await db.execute(sa.text("SELECT set_config('nexus.workspace_id', :w, true)"), {"w": str(ws)})
    # Same leak as the agent suite: the tenant outlives the workspace unless
    # it is read before the row pointing at it is removed.
    tenant = (
        await db.execute(sa.text("SELECT tenant_id FROM workspace WHERE id = :w"), {"w": str(ws)})
    ).scalar_one_or_none()
    for statement in (
        "DELETE FROM onboarding_progress WHERE workspace_id = :w",
        "DELETE FROM workspace_department WHERE workspace_id = :w",
        "DELETE FROM onboarding_answer WHERE workspace_id = :w",
        "DELETE FROM audit_log WHERE workspace_id = :w",
        "DELETE FROM membership WHERE workspace_id = :w",
        "DELETE FROM workspace WHERE id = :w",
    ):
        await db.execute(sa.text(statement), {"w": str(ws)})
    await db.execute(sa.text("DELETE FROM app_user WHERE id = :u"), {"u": str(user)})
    if tenant is not None:
        await db.execute(sa.text("DELETE FROM tenant WHERE id = :t"), {"t": str(tenant)})
    await db.commit()


# ── Resumable ─────────────────────────────────────────────────


@requires_db
async def test_onboarding_progress_is_resumable(app_db: None) -> None:
    """Q28. Complete a stage, throw the session away, come back.

    The session is deliberately discarded rather than reused: progress that
    lived in memory or in a cookie would pass a test that kept them, and fail
    the founder who closed the tab.
    """
    from app.db import _unscoped_session
    from app.domain.progress import complete_stage, progress_for

    async with _unscoped_session() as db:
        user, ws = await _workspace(db)
        try:
            await complete_stage(db, workspace_id=ws, stage="company")
            await db.commit()
        finally:
            pass

    # A completely new session — nothing carried over but the database.
    async with _unscoped_session() as db:
        try:
            state = await progress_for(db, workspace_id=ws)
            assert "company" in state.completed
            assert state.current != "company", "resumed onto the stage just finished"
        finally:
            await _cleanup(db, user, ws)


@requires_db
async def test_progress_does_not_go_backwards_on_a_repeat(app_db: None) -> None:
    """A double-clicked Continue, or a replayed POST, must not undo a stage.

    The obvious implementation — set `current` to the next stage — reverses a
    founder who has since moved on, which is the same class of defect as the
    double-click that broke workspace creation (finding #9).
    """
    from app.db import _unscoped_session
    from app.domain.progress import complete_stage, progress_for

    async with _unscoped_session() as db:
        user, ws = await _workspace(db)
        try:
            await complete_stage(db, workspace_id=ws, stage="company")
            await complete_stage(db, workspace_id=ws, stage="departments")
            await db.commit()
            ahead = (await progress_for(db, workspace_id=ws)).current

            await complete_stage(db, workspace_id=ws, stage="company")
            await db.commit()
            assert (await progress_for(db, workspace_id=ws)).current == ahead
        finally:
            await _cleanup(db, user, ws)


# ── Department selection drives the product ───────────────────


@requires_db
async def test_department_selection_drives_the_director_list(app_db: None) -> None:
    """Q22/Q63. Select two, and the product has three directors — those two and
    the Chief of Staff, which is automatic (Q24).

    Automatic because it *consumes* the others: a company that selected none
    would leave it reading nothing, so it is not a choice to offer.
    """
    from app.db import _unscoped_session
    from app.domain.departments import select_departments, selected_departments
    from app.domain.scopes import Department

    async with _unscoped_session() as db:
        user, ws = await _workspace(db)
        try:
            await select_departments(
                db, workspace_id=ws, departments={Department.MARKETING, Department.SALES}
            )
            await db.commit()

            chosen = await selected_departments(db, workspace_id=ws)
            assert Department.MARKETING in chosen
            assert Department.SALES in chosen
            assert Department.EXECUTIVE in chosen, "Chief of Staff must be automatic"
            assert Department.FINANCE not in chosen
        finally:
            await _cleanup(db, user, ws)


@requires_db
async def test_reselecting_replaces_rather_than_accumulates(app_db: None) -> None:
    """Changing your mind must remove what you deselected. Adding without
    removing would leave a director on the dashboard that nobody chose, and no
    screen through which to get rid of it."""
    from app.db import _unscoped_session
    from app.domain.departments import select_departments, selected_departments
    from app.domain.scopes import Department

    async with _unscoped_session() as db:
        user, ws = await _workspace(db)
        try:
            await select_departments(
                db, workspace_id=ws, departments={Department.MARKETING, Department.SALES}
            )
            await db.commit()
            await select_departments(db, workspace_id=ws, departments={Department.FINANCE})
            await db.commit()

            chosen = await selected_departments(db, workspace_id=ws)
            assert Department.FINANCE in chosen
            assert Department.MARKETING not in chosen
        finally:
            await _cleanup(db, user, ws)


# ── "Not sure yet" is an assumption, not a null ───────────────


def test_the_company_stage_asks_five_questions() -> None:
    """Q19. Five, and they are the five a founder can answer without going to
    look anything up except the fiscal year."""
    from app.domain.onboarding import COMPANY_QUESTIONS

    keys = [q.key for q in COMPANY_QUESTIONS]
    assert len(keys) == 5, f"expected five company questions, got {keys}"
    assert set(keys) == {
        "what_you_sell",
        "ideal_customer",
        "top_goals",
        "biggest_challenges",
        "fiscal_year_start",
    }


def test_every_company_question_offers_not_sure_yet() -> None:
    """Because a founder who cannot answer must be able to proceed *and* leave a
    trace of what was assumed on their behalf."""
    from app.domain.onboarding import COMPANY_QUESTIONS

    missing = [q.key for q in COMPANY_QUESTIONS if not q.assumption_when_unsure]
    assert missing == [], f"these have no assumption to fall back on: {missing}"


def test_not_sure_yet_records_an_assumption_not_a_null() -> None:
    """The property this whole design turns on.

    A null says nobody was asked. An assumption says somebody was asked, did not
    know, and the product proceeded on a stated basis — which the Brain can
    later contradict with evidence, and a null cannot. It is also the difference
    between a blank tile and one that says what it is assuming.
    """
    from app.domain.onboarding import BY_KEY, resolve_answer

    stored = resolve_answer(BY_KEY["ideal_customer"], value=None, unsure=True)

    assert stored.value is not None, "'not sure yet' stored a null"
    assert stored.is_assumption is True
    assert stored.value == BY_KEY["ideal_customer"].assumption_when_unsure
    # And an actual answer is not marked as one.
    given = resolve_answer(BY_KEY["ideal_customer"], value="Mid-market logistics", unsure=False)
    assert given.is_assumption is False
    assert given.value == "Mid-market logistics"


def test_a_crawl_confirmable_question_is_not_asked_here() -> None:
    """Q20's crawl-then-confirm posture. Industry is the first such field.

    Asking a founder something the crawl will tell us anyway spends the scarcest
    thing onboarding has — their patience — on a question we can answer
    ourselves and have them *confirm* at the review gate.
    """
    from app.domain.onboarding import COMPANY_QUESTIONS, CONFIRMABLE_FROM_CRAWL

    assert CONFIRMABLE_FROM_CRAWL, "nothing is marked confirmable; Q20 is unimplemented"
    asked = {q.key for q in COMPANY_QUESTIONS}
    for question in CONFIRMABLE_FROM_CRAWL:
        assert question.key not in asked, (
            f"{question.key} is confirmable from the crawl and is still being asked"
        )


# ── Skipping is first-class, and a blank is not an answer ─────


@requires_db
async def test_a_blank_block_answer_is_refused_rather_than_stored(app_db: None) -> None:
    """Finding #19. A department question you cannot answer is **skipped**, and
    an empty string is not the way to say so.

    `doc/11` stage 4 settles the mechanism: *"Blocks are skippable and
    resumable"*, and each unanswered block is what turns its director on. That
    is deliberately unlike the company stage, where "not sure yet" stores the
    question's stated assumption — there, five questions feed a review gate and
    a null would be indistinguishable from never having asked; here, the
    unanswered state **is** the signal, and the product already renders it.

    So the bug was never a missing "not sure yet". It was that a blank was
    accepted and marked the question `answered`: the director's count fell, the
    thing that turns it on reported itself done, and a capability downstream
    would read an empty string as a configured value. That is the product
    inventing an answer, which is the one thing it sells against.
    """
    from app.db import _unscoped_session
    from app.domain.departments import select_departments
    from app.domain.scopes import Department
    from app.routes.spine import BlockAnswer, BlockAnswersIn

    async with _unscoped_session() as db:
        user, ws = await _workspace(db)
        try:
            await select_departments(db, workspace_id=ws, departments={Department.FINANCE})
            await db.commit()

            for blank in ("", "   ", "\t\n"):
                with pytest.raises(ValueError):
                    BlockAnswersIn(answers=[BlockAnswer(key="approver", value=blank)])
        finally:
            await _cleanup(db, user, ws)


@requires_db
async def test_the_block_returns_what_was_answered(app_db: None) -> None:
    """Finding #20. `answered: true` beside an empty box is not a resumable form.

    Q28 makes onboarding resumable, and a founder who comes back to a block has
    to be able to read what they said before deciding whether it is still true.
    Without the value the badge is the only evidence an answer exists, saving
    again silently overwrites it, and correcting a wrong answer means
    remembering it.
    """
    from app.db import _unscoped_session
    from app.domain.departments import select_departments
    from app.domain.scopes import Department
    from app.routes.spine import (
        BlockAnswer,
        BlockAnswersIn,
        answer_department_block,
        read_department_block,
    )

    async with _unscoped_session() as db:
        user, ws = await _workspace(db)
        try:
            await select_departments(db, workspace_id=ws, departments={Department.FINANCE})
            await db.commit()
            scope = _owner_scope(user, ws)

            await answer_department_block(
                "finance",
                BlockAnswersIn(answers=[BlockAnswer(key="approver", value="The founder")]),
                scope,
            )
            block = await read_department_block("finance", scope)

            answered = {q.key: q for q in block.questions}
            assert answered["approver"].answer == "The founder", (
                "the stored answer must come back, or the form cannot be resumed"
            )
            assert answered["payment_terms"].answer is None, "an unanswered question has no value"
        finally:
            await _cleanup(db, user, ws)


@requires_db
async def test_a_department_the_company_does_not_run_has_no_block(app_db: None) -> None:
    """Finding #21. The 404 asked whether the *bank* had questions, never
    whether this company runs the department.

    An owner reaches every department they hold, and holding is not running. So
    a company on Finance alone was served a full People block with
    `may_answer: true`, and the answers written into it were invisible from
    every surface — `/dashboards` lists the chosen set, so nothing would ever
    read them back.
    """
    from fastapi import HTTPException

    from app.db import _unscoped_session
    from app.domain.departments import select_departments
    from app.domain.scopes import Department
    from app.routes.spine import read_department_block

    async with _unscoped_session() as db:
        user, ws = await _workspace(db)
        try:
            await select_departments(db, workspace_id=ws, departments={Department.FINANCE})
            await db.commit()
            scope = _owner_scope(user, ws)

            assert (await read_department_block("finance", scope)).may_answer

            with pytest.raises(HTTPException) as caught:
                await read_department_block("hr", scope)
            assert caught.value.status_code == 404
        finally:
            await _cleanup(db, user, ws)


# ── The founder's answers have to bind (F1, F2) ───────────────


def test_a_blank_company_answer_is_not_the_same_as_not_sure_yet() -> None:
    """Finding F2. Two ways to leave a question, and they mean opposite things.

    The E2E pass pressed Continue with all five boxes empty and nothing ticked.
    It saved, the stage was marked complete, and five stated assumptions were
    written that the founder had never read — because `resolve_answer` treated
    a blank exactly as it treated the checkbox. The Company Brain is assembled
    from these answers, so an empty set means an empty brain, reached silently
    and reported as success.

    The assumption is only shown *beside* the checkbox, which makes ticking it
    the only place anyone can agree to it. A blank is therefore an unfinished
    form, not consent, and it is refused.
    """
    from app.domain.onboarding import BY_KEY, BlankAnswerError, resolve_answer

    question = BY_KEY["what_you_sell"]

    for blank in (None, "", "   ", "\t\n"):
        with pytest.raises(BlankAnswerError):
            resolve_answer(question, value=blank, unsure=False)

    # The checkbox still works, and still records an assumption rather than a
    # null. That property is the whole point of the design and must survive
    # the fix to the one beside it.
    stored = resolve_answer(question, value=None, unsure=True)
    assert stored.is_assumption is True
    assert stored.value == question.assumption_when_unsure


def test_a_required_question_cannot_be_left_out_of_the_request() -> None:
    """The other half of F2, and the one a browser cannot reach.

    The wizard posts all five keys every time, so the blank case above is what
    a person hits. Anything else speaking to this endpoint could simply omit
    `what_you_sell` — the question the bank marks `required` — and the stage
    would complete without it ever being asked about. A rule enforced only for
    the client that happens to be well behaved is not enforced.
    """
    from app.domain.onboarding import COMPANY_QUESTIONS

    required = [q.key for q in COMPANY_QUESTIONS if q.required]
    assert required, "no company question is marked required; F2's premise is gone"
    assert "what_you_sell" in required


def test_running_nothing_is_not_the_same_as_having_chosen_nothing() -> None:
    """Finding F1, at the function that made it possible.

    `selected_departments` always adds the Chief of Staff, so a workspace that
    stored no rows arrives here as a set of one — and `runs_department` reads a
    set of one as *"this company has not chosen yet, so nothing is ruled out"*.
    That default is right for a founder who has not reached the step. It was
    catastrophic for one who reached it and ticked nothing: the E2E pass
    selected zero departments, was told the step was complete, and then found
    all seven directors present and every one of their pages answering 200 —
    the exact opposite of what the screen had promised.

    The floor in `POST /onboarding/departments` is what keeps the two states
    tellable apart. This asserts the reading that floor depends on.
    """
    from app.domain.departments import AUTOMATIC, runs_department
    from app.domain.scopes import Department

    nothing_stored = frozenset({AUTOMATIC})
    assert runs_department(nothing_stored, Department.HR) is True, (
        "a company that has not chosen yet should still reach everything"
    )

    chose_two = frozenset({AUTOMATIC, Department.SALES, Department.FINANCE})
    assert runs_department(chose_two, Department.SALES) is True
    assert runs_department(chose_two, Department.HR) is False, (
        "a department the company did not choose is reachable — F1 is back"
    )


def test_every_department_has_a_label_and_none_is_the_raw_key() -> None:
    """Finding F13. One department read three ways.

    `hr` in the API, "Hr" wherever a client title-cased the key, and "People"
    in the dashboard nav — three spellings for one thing. The label is now a
    served fact rather than something each surface derives, and the test that
    matters is that nothing fell back to `.title()`, which is what produced the
    middle one.
    """
    from app.domain.departments import LABELS, label_for
    from app.domain.scopes import Department

    missing = [d.value for d in Department if d not in LABELS]
    assert missing == [], f"these departments have no label: {missing}"

    assert all(label_for(d).strip() for d in Department), "a department has a blank label"

    # Most keys happen to title-case correctly, which is why the two that do
    # not were the ones that produced three spellings. These are the assertions
    # with teeth: `hr` must never render as "Hr", and `executive` is the Chief
    # of Staff everywhere the product speaks to a person.
    assert label_for(Department.HR) == "People"
    assert label_for(Department.EXECUTIVE) == "Chief of Staff"


@requires_db
async def test_choosing_no_departments_is_refused(app_db: None) -> None:
    """Finding F1, at the route.

    The floor `runs_department` now depends on. Zero departments is the one
    count that does not describe a business: the Chief of Staff consumes the
    other directors, so a company that chose none leaves it reading nothing —
    and, before this, was silently granted all seven instead.

    A request naming only `executive` is the same request wearing a hat.
    `select_departments` filters the automatic department out, so the check has
    to run on what would actually be stored rather than on what was asked.
    """
    from fastapi import HTTPException

    from app.db import _unscoped_session
    from app.routes.spine import DepartmentsIn, save_departments

    async with _unscoped_session() as db:
        user, ws = await _workspace(db)
    scope = _owner_scope(user, ws)

    try:
        for payload in ([], ["executive"]):
            with pytest.raises(HTTPException) as refused:
                await save_departments(DepartmentsIn(departments=payload), scope)
            assert refused.value.status_code == 400
            assert "at least one" in str(refused.value.detail).lower()

        # And a real selection still goes through, still advances the stage,
        # and still binds — the fix must not have turned into a wall.
        stage = await save_departments(DepartmentsIn(departments=["sales", "finance"]), scope)
        assert "departments" in stage.completed

        from app.domain.departments import runs_department, selected_departments
        from app.domain.scopes import Department

        async with _unscoped_session() as db:
            chosen = await selected_departments(db, workspace_id=ws)
        assert runs_department(chosen, Department.SALES) is True
        assert runs_department(chosen, Department.HR) is False, (
            "an unchosen department is still reachable — F1 is back"
        )
    finally:
        async with _unscoped_session() as db:
            await _cleanup(db, user, ws)


@requires_db
async def test_the_company_stage_refuses_a_blank_and_an_omission(app_db: None) -> None:
    """Finding F2, at the route.

    Both ways past a `required` question, closed together: five empty boxes,
    and a request that simply leaves the key out. The first is what the E2E
    pass did through the browser; the second is what anything else could do.

    The refusal names the questions rather than saying "some answers are
    missing", because the way out is a specific checkbox beside a specific
    question.
    """
    from fastapi import HTTPException

    from app.db import _unscoped_session
    from app.domain.onboarding import COMPANY_QUESTIONS
    from app.routes.spine import CompanyAnswer, CompanyAnswersIn, save_company_stage

    async with _unscoped_session() as db:
        user, ws = await _workspace(db)
    scope = _owner_scope(user, ws)

    try:
        all_blank = CompanyAnswersIn(
            answers=[CompanyAnswer(key=q.key, value=None, unsure=False) for q in COMPANY_QUESTIONS]
        )
        with pytest.raises(HTTPException) as refused:
            await save_company_stage(all_blank, scope)
        assert refused.value.status_code == 400

        without_the_required_one = CompanyAnswersIn(
            answers=[
                CompanyAnswer(key=q.key, value="something", unsure=False)
                for q in COMPANY_QUESTIONS
                if not q.required
            ]
        )
        with pytest.raises(HTTPException) as omitted:
            await save_company_stage(without_the_required_one, scope)
        assert omitted.value.status_code == 400

        # Nothing was written by either refusal. A stage that half-saves leaves
        # the founder looking at a form that disagrees with the database.
        from app.domain.progress import progress_for

        async with _unscoped_session() as db:
            progress = await progress_for(db, workspace_id=ws)
        assert "company" not in progress.completed

        # Answered properly — one typed, the rest skipped explicitly — it saves.
        proper = CompanyAnswersIn(
            answers=[
                CompanyAnswer(
                    key=q.key,
                    value="Freight forwarding" if q.required else None,
                    unsure=not q.required,
                )
                for q in COMPANY_QUESTIONS
            ]
        )
        stage = await save_company_stage(proper, scope)
        assert "company" in stage.completed
    finally:
        async with _unscoped_session() as db:
            await _cleanup(db, user, ws)


@requires_db
async def test_the_company_stage_hands_back_what_was_stored(app_db: None) -> None:
    """Finding F13's other half: a route back that is worth taking.

    The stage rail's pills were inert, so a founder past a step could not
    return to correct an answer. Making them clickable is only half a fix — a
    form that reopens empty and overwrites on save looks like it worked and
    quietly discards what was there. So `/onboarding/state` returns the stored
    answer, and says which of them were assumptions rather than statements.
    """
    from app.db import _unscoped_session
    from app.domain.onboarding import COMPANY_QUESTIONS
    from app.routes.spine import CompanyAnswer, CompanyAnswersIn, read_state, save_company_stage

    async with _unscoped_session() as db:
        user, ws = await _workspace(db)
    scope = _owner_scope(user, ws)

    try:
        await save_company_stage(
            CompanyAnswersIn(
                answers=[
                    CompanyAnswer(
                        key=q.key,
                        value="Refrigerated freight" if q.required else None,
                        unsure=not q.required,
                    )
                    for q in COMPANY_QUESTIONS
                ]
            ),
            scope,
        )

        state = await read_state(scope)
        by_key = {q.key: q for q in state.company_questions}

        typed = by_key["what_you_sell"]
        assert typed.answer == "Refrigerated freight"
        assert typed.is_assumption is False

        skipped = [q for q in state.company_questions if q.key != "what_you_sell"]
        assert skipped, "every company question is required; this test asserts nothing"
        for question in skipped:
            assert question.answer is not None, f"{question.key} came back empty"
            assert question.is_assumption is True, (
                f"{question.key} was skipped and is not marked as an assumption"
            )
    finally:
        async with _unscoped_session() as db:
            await _cleanup(db, user, ws)
