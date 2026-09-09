"""The onboarding spine, over HTTP.

`doc/12` §Phase 6. Three things the single-page wizard had no way to express:
where a founder is, what they have finished, and which departments they run.

**Progress is read and written server-side.** The client asks where it should be
rather than deciding — otherwise a stale tab, a Back button or a second device
each hold their own opinion, and the one that writes last wins. There is one
answer and the database holds it.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import text

from app.auth.csrf import require_csrf
from app.db import _unscoped_session
from app.deps import CurrentScope
from app.domain import audit, persona_chat
from app.domain import company_brain as brain
from app.domain.department_answers import (
    AnswerState,
    may_answer_department_question,
    state_for_answer,
)
from app.domain.departments import (
    AUTOMATIC,
    RECOMMENDED_MAX,
    RECOMMENDED_MIN,
    SELECTABLE,
    label_for,
    runs_department,
    select_departments,
    selected_departments,
)
from app.domain.onboarding import (
    BY_KEY,
    COMPANY_QUESTIONS,
    BlankAnswerError,
    Question,
    ResolvedAnswer,
    resolve_answer,
)
from app.domain.progress import STAGES, complete_stage, progress_for
from app.domain.question_bank import BY_DEPARTMENT
from app.domain.registry import consumers_of
from app.domain.scopes import Department
from app.domain.session import ScopedSession
from app.logging import get_logger
from app.retrieval.scoped import scoped_connection
from app.routes.setup import store_answer

router = APIRouter(prefix="/onboarding", tags=["onboarding"])
log = get_logger(__name__)


class StageOut(BaseModel):
    current: str
    completed: list[str]
    stages: list[str]
    finished: bool


class CompanyQuestionOut(BaseModel):
    key: str
    prompt: str
    why: str
    required: bool
    assumption_when_unsure: str | None
    answer: str | None = None
    """What was stored, so the step can be returned to (Q28).

    The same reasoning as `BlockQuestionOut.answer`, and finding F13 is why it
    is here too: the stage rail's pills were inert, so there was no route back
    to a company answer at all — and once there is one, a form that reopens
    empty and overwrites on save is worse than no route back, because it looks
    like it worked.

    An assumption comes back as its own text, with `is_assumption` alongside.
    The founder should see what was recorded on their behalf, and be able to
    replace it with something they actually know."""

    is_assumption: bool = False


class DepartmentOut(BaseModel):
    value: str
    label: str
    """How to name it on screen. Served rather than derived — a client that
    title-cases `value` renders "Hr" (finding F13)."""

    selected: bool


class SpineOut(BaseModel):
    """Everything the flow needs to render itself, in one call.

    One request rather than three, because a stage rail that renders before it
    knows which stages are done shows the wrong one and then corrects itself,
    and a founder reads that as the product losing their place.
    """

    stage: StageOut
    company_questions: list[CompanyQuestionOut]
    departments: list[DepartmentOut]
    recommended: dict[str, int]


@router.get("/state", response_model=SpineOut)
async def read_state(scope: CurrentScope) -> SpineOut:
    async with _unscoped_session() as db:
        progress = await progress_for(db, workspace_id=scope.workspace_id)
        chosen = await selected_departments(db, workspace_id=scope.workspace_id)

    # The company answers, so a founder returning to the step reads what they
    # said rather than an empty form that will overwrite it on save. Scoped,
    # unlike the two reads above, because this is workspace content rather than
    # workspace progress.
    async with scoped_connection(scope) as db:
        stored = {
            r.question_key: r
            for r in (
                await db.execute(
                    text(
                        "SELECT question_key, value, is_assumption FROM onboarding_answer"
                        " WHERE department IS NULL"
                    )
                )
            ).all()
        }

    # `value` is jsonb and every company answer is stored as a JSON string.
    # Anything else came from the wider catalogue and is not this step's to
    # render, so it is reported as unanswered rather than stringified.
    answers = {
        key: (row.value, row.is_assumption)
        for key, row in stored.items()
        if isinstance(row.value, str)
    }

    return SpineOut(
        stage=StageOut(
            current=progress.current,
            completed=sorted(progress.completed),
            stages=list(STAGES),
            finished=progress.finished,
        ),
        company_questions=[
            CompanyQuestionOut(
                key=q.key,
                prompt=q.prompt,
                why=q.why,
                required=q.required,
                assumption_when_unsure=q.assumption_when_unsure,
                answer=answers.get(q.key, (None, False))[0],
                is_assumption=answers.get(q.key, (None, False))[1],
            )
            for q in COMPANY_QUESTIONS
        ],
        # `SELECTABLE` excludes the Chief of Staff, which is automatic (Q24) and
        # must never appear as a checkbox somebody can clear.
        departments=[
            DepartmentOut(value=d.value, label=label_for(d), selected=d in chosen)
            for d in SELECTABLE
        ],
        recommended={"min": RECOMMENDED_MIN, "max": RECOMMENDED_MAX},
    )


class CompanyAnswer(BaseModel):
    key: str
    value: str | None = Field(default=None, max_length=4000)
    unsure: bool = False


class CompanyAnswersIn(BaseModel):
    answers: list[CompanyAnswer]


@router.post("/company", response_model=StageOut, dependencies=[Depends(require_csrf)])
async def save_company_stage(payload: CompanyAnswersIn, scope: CurrentScope) -> StageOut:
    """Store the five company answers and advance.

    Every answer goes through `resolve_answer`, so **"not sure yet" can never
    store a null** — it stores the question's stated assumption instead, flagged
    as one. A null would be indistinguishable from a question nobody reached,
    and those two want different behaviour everywhere downstream.

    **A question the bank marks required has to be answered one way or the
    other** — with a value, or with "not sure yet" and the assumption it
    states. Two ways to dodge that were open and both are closed below: leaving
    the box empty, and leaving the key out of the request altogether. The second
    is not reachable from the wizard, which always posts all five; it was
    reachable from anything else that speaks to this endpoint, which is the
    caller a rule exists for.
    """
    unknown = [a.key for a in payload.answers if a.key not in BY_KEY]
    if unknown:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, f"Unknown question keys: {sorted(unknown)}"
        )

    sent = {a.key for a in payload.answers}
    absent = [q for q in COMPANY_QUESTIONS if q.required and q.key not in sent]
    if absent:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "These cannot be left out: " + "; ".join(q.prompt for q in absent),
        )

    # Resolved in full before anything is written, so a stage that one blank
    # would reject cannot half-save — the same reason `/onboarding/answers`
    # validates before it writes.
    resolved: list[tuple[Question, ResolvedAnswer]] = []
    blank: list[str] = []
    for answer in payload.answers:
        question = BY_KEY[answer.key]
        try:
            resolved.append(
                (question, resolve_answer(question, value=answer.value, unsure=answer.unsure))
            )
        except BlankAnswerError:
            blank.append(question.key)

    if blank:
        # Finding F2. The question bank marks `what_you_sell` required and
        # nothing enforced it at either end, so five empty boxes advanced the
        # stage and the Brain was assembled from nothing. Naming the questions
        # rather than saying "some answers are missing" matters here: the way
        # out is a specific checkbox beside a specific question.
        missing = [BY_KEY[key].prompt for key in blank]
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Answer these, or tick “Not sure yet” to record the stated "
            f"assumption instead: {'; '.join(missing)}",
        )

    # Stored through the same `store_answer` the wizard uses, so scope tagging
    # at capture (doc 06 §2.5) still happens in exactly one place — and through
    # `resolve_answer`, so "not sure yet" becomes a flagged assumption rather
    # than a null.
    async with scoped_connection(scope) as session:
        for question, stored in resolved:
            await store_answer(
                session,
                caller=scope,
                question=question,
                value=stored.value,
                is_assumption=stored.is_assumption,
            )

    async with _unscoped_session() as db:
        progress = await complete_stage(db, workspace_id=scope.workspace_id, stage="company")
        await audit.record(
            db,
            workspace_id=scope.workspace_id,
            action=audit.AuditAction.ANSWER_WRITTEN,
            actor_user_id=scope.user_id,
            target_type="onboarding_stage",
            target_id="company",
            reason=f"{len(payload.answers)} answers",
        )
        await db.commit()

    return StageOut(
        current=progress.current,
        completed=sorted(progress.completed),
        stages=list(STAGES),
        finished=progress.finished,
    )


class BrainOut(BaseModel):
    """The company brain, and what it is made of.

    `provenance` and `assumptions` are part of the response rather than an
    internal detail: a brain the founder cannot audit is a brain they have to
    take on trust, and this product's whole claim is that they never have to.
    """

    version: int
    generated_by: str
    unavailable_reason: str
    profile: str | None
    products_services: str | None
    target_customers: str | None
    goals: str | None
    assumptions: list[str]
    provenance: list[str]


@router.post("/brain", response_model=BrainOut, dependencies=[Depends(require_csrf)])
async def rebuild_brain(scope: CurrentScope) -> BrainOut:
    """Rebuild the brain from the workspace's current answers.

    A POST because it writes a new version, and versioned because a founder who
    changes an answer should be able to see that the brain changed with it. The
    old one is superseded rather than deleted — `ux_company_brain_current`
    guarantees exactly one is live.
    """
    async with scoped_connection(scope) as db:
        built = await brain.build(db, workspace_id=scope.workspace_id)
        version = await brain.store(db, workspace_id=scope.workspace_id, brain=built)
        await db.commit()

    log.info("brain.rebuilt", version=version, generated_by=built.generated_by)
    return _brain_out(built, version)


@router.get("/brain", response_model=BrainOut)
async def read_brain(scope: CurrentScope) -> BrainOut:
    """The current brain, built on demand if it has never been built.

    Built rather than 404 because the brain is derived: everything it needs is
    already in the workspace, so "not built yet" is an implementation detail the
    founder has no way to act on and no reason to see.
    """
    async with scoped_connection(scope) as db:
        held = await brain.current(db, workspace_id=scope.workspace_id)
        if held is None:
            built = await brain.build(db, workspace_id=scope.workspace_id)
            version = await brain.store(db, workspace_id=scope.workspace_id, brain=built)
            await db.commit()
            return _brain_out(built, version)

    row = None
    async with scoped_connection(scope) as db:
        row = (
            await db.execute(
                text(
                    "SELECT version FROM company_brain"
                    " WHERE workspace_id = :w AND superseded_at IS NULL"
                ),
                {"w": str(scope.workspace_id)},
            )
        ).scalar_one()
    return _brain_out(held, int(row))


def _brain_out(built: brain.Brain, version: int) -> BrainOut:
    return BrainOut(
        version=version,
        generated_by=built.generated_by,
        unavailable_reason=built.unavailable_reason,
        profile=built.profile,
        products_services=built.products_services,
        target_customers=built.target_customers,
        goals=built.goals,
        assumptions=built.assumptions,
        provenance=built.provenance,
    )


class PersonaTurnOut(BaseModel):
    """One turn of the interview: what is being asked, and what is known so far."""

    question: dict[str, object] | None
    """`None` when the interview is finished."""
    answered: dict[str, str]
    complete: bool


class PersonaAnswerIn(BaseModel):
    key: str
    value: str = Field(min_length=1, max_length=2000)


def _turn(answered: dict[str, str]) -> PersonaTurnOut:
    question = persona_chat.next_question(answered)
    built = persona_chat.apply(answered)
    return PersonaTurnOut(
        question=(
            {
                "key": question.key,
                "prompt": question.prompt,
                "why": question.why,
                "choices": list(question.choices),
                "free_text": question.free_text,
            }
            if question
            else None
        ),
        answered=answered,
        complete=built.complete,
    )


async def _persona_answers(scope: ScopedSession) -> dict[str, str]:
    async with scoped_connection(scope) as db:
        row = (
            await db.execute(
                text(
                    "SELECT stated_purpose, priority_topics, communication_style, language"
                    "  FROM persona WHERE user_id = :u"
                ),
                {"u": str(scope.user_id)},
            )
        ).first()
    if row is None:
        return {}
    return {
        k: v
        for k, v in {
            "stated_purpose": row.stated_purpose or "",
            "priority_topics": ", ".join(row.priority_topics or []),
            "communication_style": row.communication_style or "",
            "language": row.language or "",
        }.items()
        if v
    }


@router.get("/persona/chat", response_model=PersonaTurnOut)
async def persona_chat_state(scope: CurrentScope) -> PersonaTurnOut:
    """Where this person is in the interview.

    Derived from what is stored rather than from a cursor the client holds, so
    closing the tab loses nothing — the same reason onboarding is resumable.
    """
    return _turn(await _persona_answers(scope))


@router.post("/persona/chat", response_model=PersonaTurnOut, dependencies=[Depends(require_csrf)])
async def persona_chat_answer(payload: PersonaAnswerIn, scope: CurrentScope) -> PersonaTurnOut:
    """Answer one question and get the next.

    **Nothing here can widen access** (`doc/05` §2.6). Unknown keys are refused
    rather than stored, and the four that are accepted are presentation only —
    `ScopedSession` carries none of them, so a persona cannot reach a query even
    if somebody later tries. Role and departments come from the invitation,
    which somebody else issued: typing "I'm the CFO" into a chat is not a
    promotion.
    """
    if payload.key not in persona_chat.ANSWERABLE:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"{payload.key} is not part of this conversation.",
        )

    answered = await _persona_answers(scope)
    answered[payload.key] = payload.value.strip()
    built = persona_chat.apply(answered)

    async with scoped_connection(scope) as db:
        await db.execute(
            text(
                "INSERT INTO persona (workspace_id, user_id, stated_purpose, priority_topics,"
                "                     communication_style, language)"
                " VALUES (:w, :u, :purpose, :topics, :style, :lang)"
                " ON CONFLICT (workspace_id, user_id) DO UPDATE SET"
                "   stated_purpose = EXCLUDED.stated_purpose,"
                "   priority_topics = EXCLUDED.priority_topics,"
                "   communication_style = EXCLUDED.communication_style,"
                "   language = EXCLUDED.language"
            ),
            {
                "w": str(scope.workspace_id),
                "u": str(scope.user_id),
                "purpose": built.stated_purpose,
                "topics": built.priority_topics,
                "style": built.communication_style,
                # `language` is NOT NULL with a default of `en`, and an INSERT
                # naming the column overrides the default with NULL rather than
                # falling back to it. Mid-interview the answer legitimately does
                # not exist yet, so the default has to be written explicitly.
                "lang": built.language or "en",
            },
        )
        await db.commit()

    log.info("persona.answered", key=payload.key, complete=built.complete)
    return _turn(answered)


class DepartmentsIn(BaseModel):
    departments: list[str]


@router.post("/departments", response_model=StageOut, dependencies=[Depends(require_csrf)])
async def save_departments(payload: DepartmentsIn, scope: CurrentScope) -> StageOut:
    """Select the departments, and advance.

    **No maximum, and a minimum of one.** Q23 recommends three to five; a
    company that runs two functions should be able to say two, and refusing that
    would make the product's tidiness more important than the customer's
    reality. Zero is the one count that is not a description of a business.

    Finding F1 is why the floor exists. `selected_departments` always adds the
    Chief of Staff, so a workspace that stored no rows and a workspace that
    stored none *on purpose* both arrived at `runs_department` as a set of one —
    and that function reads a set of one as "this company has not chosen yet, so
    nothing has been ruled out". A founder who ticked nothing was therefore
    given all seven directors, which is the exact opposite of what the screen
    they were standing on had just promised them.

    Refusing zero here is what makes the two states tellable apart, so
    `runs_department`'s default is now true by construction rather than by
    hope: after this route, a stored selection always has at least one row.
    """
    try:
        chosen = {Department(d) for d in payload.departments}
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Unknown department.") from exc

    # `select_departments` drops the Chief of Staff, so a request naming only it
    # is a request for nothing — checked after the filter rather than on the raw
    # list, which would let `["executive"]` through as a count of one.
    if not {d for d in chosen if d is not AUTOMATIC}:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Choose at least one department. Each one you choose gets a "
            "director and a dashboard, and the Chief of Staff reads the "
            "others — with none chosen there is nothing for it to read.",
        )

    async with _unscoped_session() as db:
        await select_departments(db, workspace_id=scope.workspace_id, departments=chosen)
        progress = await complete_stage(db, workspace_id=scope.workspace_id, stage="departments")
        await db.commit()

    log.info("onboarding.departments.selected", count=len(chosen))
    return StageOut(
        current=progress.current,
        completed=sorted(progress.completed),
        stages=list(STAGES),
        finished=progress.finished,
    )


# ── Department blocks (P7) ────────────────────────────────────


class BlockQuestionOut(BaseModel):
    key: str
    prompt: str
    why: str
    answer_type: str
    consumed_by: str
    answered: bool
    proposed: bool
    answer: str | None = None
    """What was stored, so the form can be resumed (Q28).

    `answered` alone made the badge the only evidence an answer existed: a
    founder returning to a block could not read what they had said, saving
    again silently overwrote it, and correcting a wrong answer meant
    remembering it. `None` here means unanswered, not withheld — every caller
    served this block may already see `answered`."""


class BlockOut(BaseModel):
    department: str
    may_answer: bool
    binds: bool
    questions: list[BlockQuestionOut]


async def _require_running(scope: ScopedSession, target: Department) -> None:
    """404 unless this **company** runs the department (finding #21).

    Not the same question as whether the caller may reach it. `may_answer` asks
    who you are; this asks what the company chose at stage 4, and an owner holds
    every department while running only the ones they picked. Without it a
    company on Finance alone was served a full People block with
    `may_answer: true`, and answers written into it were reachable from nothing:
    `GET /dashboards` lists the chosen set, so no surface would ever read them
    back.

    404 rather than 403 to match the neighbouring refusals — which department
    a company runs is its own business, and this route already answers 404 for
    a department that does not exist.
    """
    async with _unscoped_session() as db:
        chosen = await selected_departments(db, workspace_id=scope.workspace_id)
    if not runs_department(chosen, target):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "This company does not run that department.")


@router.get("/departments/{department}/block", response_model=BlockOut)
async def read_department_block(department: str, scope: CurrentScope) -> BlockOut:
    """One department's questions, and whether this caller may answer them.

    `may_answer` and `binds` are returned rather than left for the client to
    infer. A UI deciding for itself would be guessing at an authority rule, and
    the guesses that matter are the wrong ones — a Contributor shown a form that
    binds, or a Manager shown a read-only block for their own department.

    Served to callers who **may not** answer it, with `may_answer: false`.
    Hiding it would leave a Contributor unable to see what their own department
    has been asked, which is information they are entitled to and which the
    stored answers already carry.
    """
    try:
        target = Department(department)
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such department.") from exc

    questions = BY_DEPARTMENT.get(target, ())
    if not questions:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No block for that department.")

    await _require_running(scope, target)

    async with scoped_connection(scope) as db:
        rows = {
            r.question_key: r
            for r in (
                await db.execute(
                    text(
                        "SELECT question_key, answer_state, value FROM onboarding_answer"
                        " WHERE department = :d"
                    ),
                    {"d": target.value},
                )
            ).all()
        }

    return BlockOut(
        department=target.value,
        may_answer=may_answer_department_question(
            role=scope.role, caller_departments=scope.departments, department=target
        ),
        binds=state_for_answer(role=scope.role, caller_departments=scope.departments)
        is AnswerState.BOUND,
        questions=[
            BlockQuestionOut(
                key=q.key,
                prompt=q.prompt,
                why=q.why,
                answer_type=q.answer_type.value,
                consumed_by=q.consumed_by,
                answered=q.key in rows,
                proposed=q.key in rows and rows[q.key].answer_state == AnswerState.PROPOSED.value,
                answer=rows[q.key].value if q.key in rows else None,
            )
            for q in questions
        ],
    )


class BlockAnswer(BaseModel):
    key: str
    value: str = Field(min_length=1, max_length=4000)

    @field_validator("value")
    @classmethod
    def reject_a_blank(cls, value: str) -> str:
        """A department question you cannot answer is **skipped**, not blanked.

        `doc/11` stage 4: *"Blocks are skippable and resumable"*, and each
        unanswered block is what turns its director on. So the way to say
        nothing is to send nothing — and a blank had to stop being the other
        way, because it marked the question `answered`, dropped the director's
        count, and left a capability downstream reading an empty string as a
        configured value.

        Deliberately unlike the company stage, where "not sure yet" stores the
        question's stated assumption. Five questions there feed a review gate
        and a null cannot be told from never having asked; here the unanswered
        state *is* the signal and the product already renders it.
        """
        if not value.strip():
            raise ValueError(
                "An empty answer is not an answer. Leave the question out of the "
                "request to skip it — blocks are skippable, and its director will "
                "keep saying so."
            )
        return value.strip()


class BlockAnswersIn(BaseModel):
    answers: list[BlockAnswer]


@router.post(
    "/departments/{department}/block",
    response_model=BlockOut,
    dependencies=[Depends(require_csrf)],
)
async def answer_department_block(
    department: str, payload: BlockAnswersIn, scope: CurrentScope
) -> BlockOut:
    """Answer a department's questions.

    Two checks, and they are not the same check (Q30, Q31). **May you answer at
    all** depends on which department this is — a Sales Manager may not
    configure Finance. **Does your answer bind** depends on your role alone — a
    Contributor's is proposed and waits for the review gate.

    A Contributor reaches this route legitimately, because proposing *is*
    answering. So the check permits them for their own department and
    `state_for_answer` decides what the row means, rather than the route
    refusing and the product losing a proposal it asked for.
    """
    try:
        target = Department(department)
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such department.") from exc

    binding = state_for_answer(role=scope.role, caller_departments=scope.departments)

    permitted = may_answer_department_question(
        role=scope.role, caller_departments=scope.departments, department=target
    ) or (binding is AnswerState.PROPOSED and target in scope.departments)

    if not permitted:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            f"You cannot answer the {target.value} questions. A department's "
            "questions are answered by its manager, or by an owner.",
        )

    await _require_running(scope, target)

    bank = {q.key: q for q in BY_DEPARTMENT.get(target, ())}
    unknown = [a.key for a in payload.answers if a.key not in bank]
    if unknown:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, f"Not questions in this block: {sorted(unknown)}"
        )

    async with scoped_connection(scope) as db:
        # Read what is there **before** the upsert. `store_answer` is an upsert
        # by design — onboarding is revisitable — so after it runs there is no
        # way to tell a first answer from a correction, and only the second is a
        # restatement (`doc/13` §10).
        held = {
            row.question_key: row.value
            for row in (
                await db.execute(
                    text("SELECT question_key, value FROM onboarding_answer WHERE department = :d"),
                    {"d": target.value},
                )
            ).all()
        }

        changed: list[str] = []
        for answer in payload.answers:
            before = held.get(answer.key)
            if before is not None and before != answer.value:
                changed.append(answer.key)

            await store_answer(
                db,
                caller=scope,
                question=bank[answer.key],
                value=answer.value,
                answer_state=binding.value,
            )

        # **The restate rule** (`doc/13` §10). A first answer is an answer; a
        # changed one moves figures somebody may already have acted on, so it is
        # recorded with the capabilities that read it named.
        #
        # Named rather than counted, because `consumers_of` can say exactly
        # which — the question bank declares each question's consumer and the
        # registry inverts it. "Three tiles were affected" is a number nobody
        # can check; "finance.receivables_ageing was" is one they can open.
        #
        # Marking those tiles stale and re-deriving them is P14's, and there is
        # nothing computed to mark today. What lands now is the record a later
        # derivation compares itself against — the same cut step A made for the
        # reporting settings, for the same reason.
        for key in changed:
            reads_it = consumers_of(key)
            await audit.record(
                db,
                workspace_id=scope.workspace_id,
                action=audit.AuditAction.ANSWER_WRITTEN,
                actor_user_id=scope.user_id,
                target_type="onboarding_answer",
                target_id=f"{target.value}:{key}",
                reason=(
                    f"restated; read by {', '.join(reads_it)}"
                    if reads_it
                    else "restated; no capability reads it yet"
                ),
            )

        if changed:
            await db.commit()

    log.info(
        "onboarding.block.answered",
        department=target.value,
        binding=binding.value,
        count=len(payload.answers),
        restated=len(changed),
    )
    return await read_department_block(target.value, scope)
