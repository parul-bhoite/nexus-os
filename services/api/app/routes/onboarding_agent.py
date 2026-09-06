"""The agentic onboarding journey, over HTTP.

Six endpoints, one per move a person can make. Deliberately not one endpoint with
a mode flag: each move has a different precondition, and a single handler
branching on a client-supplied phase would let a client skip one.

**Availability is checked once, at the front.** ADR 0022 makes onboarding require
a language model, so every endpoint here answers 503 with an honest detail when
no key is configured. It does not fall back to a form and it does not proceed
with defaults — the rest of the product still runs, which is the half of ADR 0011
that stands.

**The client never names a target.** `POST /answer` sends only text; the field the
answer belongs to is read from the agent's own last turn, server-side. A client
that could name the target could choose the sensitivity its answer is stored at.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.ai.registry import get_provider
from app.ai.runtime.commands import CommandContext
from app.ai.runtime.fields import UndeclaredFieldError, resolve
from app.ai.runtime.hooks import get_hooks
from app.ai.runtime.runner import SkillFailedError, SkillRunner
from app.auth.csrf import require_csrf
from app.deps import CurrentScope
from app.domain import onboarding_sessions as store
from app.domain.onboarding_agent import MAX_QUESTIONS, AgentState, OnboardingAgent, Turn
from app.domain.session import ScopedSession
from app.logging import get_logger
from app.research.runner import crawl_site
from app.retrieval.scoped import scoped_connection

router = APIRouter(prefix="/onboarding/agent", tags=["onboarding"])

ONBOARDING_PAGE_BUDGET = 3
"""Pages the foreground crawl fetches while somebody waits.

`site.PRIORITY_PATHS` orders the plan, so three pages is the home page plus the
two that most often describe the business — `/about` and `/services`. Twenty is
what the background research run takes; the difference is that nobody is
watching that one.

Three rather than one because a brief written from a home page alone is thin,
and thin is what the founder is then asked to correct. Three rather than ten
because each fetch is a couple of seconds and they are sequential.
"""

log = get_logger(__name__)


# ── Wire ──────────────────────────────────────────────────────


class TurnOut(BaseModel):
    role: str
    text: str
    target: str | None = None
    scope: int | None = None


class ViewerOut(BaseModel):
    """Who is on the other side of the screen, as they described themselves.

    Every field is optional and an absent one is `null`, never `""`. The screen
    greets somebody with the parts it actually has and says nothing about the
    parts it does not — a person addressed as "as null in null" learns that the
    product is guessing, on the first line they ever read from it.

    **`designation` and `department` are claims, not grants.** They are
    `membership.designation` and `membership.stated_department` — what the user
    typed about themselves. `membership.role` and `membership.departments`, the
    authorising pair, are deliberately absent: migration 0025 names these
    columns apart precisely so that authorisation never leaks into conversational
    material, and a greeting is the most conversational material there is.
    """

    name: str | None = None
    designation: str | None = None
    department: str | None = None
    company: str | None = None


class StateOut(BaseModel):
    active: bool
    completed: bool = False
    """Distinguishes "already finished" from "never started".

    Both leave no *active* session, and treating them the same is how a second
    journey gets started over a Brain that is already built.
    """

    phase: str
    domain: str | None = None
    turns: list[TurnOut] = Field(default_factory=list)
    brief: dict[str, Any] = Field(default_factory=dict)
    persona: dict[str, Any] = Field(default_factory=dict)
    context: dict[str, Any] = Field(default_factory=dict)
    answered: int = 0
    ceiling: int = MAX_QUESTIONS
    pages_read: list[str] = Field(default_factory=list)
    """URLs the fetcher actually retrieved.

    On the wire so the screen can name them while the read runs. A list of real
    URLs is the difference between a wait that shows its working and a spinner.
    """

    viewer: ViewerOut = Field(default_factory=ViewerOut)
    """Who is asking, for the greeting.

    Present on every response, including the one that reports no journey at all,
    because the greeting is the first thing drawn and it must not wait for the
    read. It needs no model and costs one row — so the twenty seconds of crawl
    and inference happen *under* a line that already knows the person's name,
    rather than under a progress sentence.
    """


class BriefIn(BaseModel):
    corrections: dict[str, str] = Field(default_factory=dict)


class DiscoveryIn(BaseModel):
    answer: str = Field(min_length=1, max_length=4000)


class AnswerIn(BaseModel):
    text: str = Field(min_length=1, max_length=4000)


class QuestionOut(BaseModel):
    done: bool
    question: str | None = None
    target: str | None = None
    scope: int | None = None
    choices: list[str] = Field(default_factory=list)
    reason: str | None = None


# ── Guards ────────────────────────────────────────────────────


def _require_model() -> None:
    """ADR 0022. Onboarding needs a model; everything else does not."""
    provider = get_provider()
    state = provider.status()
    if not state.usable:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "error": "language_model_unavailable",
                "availability": str(state.availability),
                "message": state.detail,
                "what_this_blocks": "Guided onboarding only. Sign-in and every "
                "existing workspace are unaffected.",
            },
        )


def _context(
    scope: ScopedSession, db: Any, user_context: Mapping[str, str] | None = None
) -> CommandContext:
    hooks = get_hooks()
    return CommandContext(
        workspace_id=str(scope.workspace_id),
        session=db,
        # The runner is given the bus and the workspace so it can announce each
        # skill call itself, rather than every command remembering to.
        runner=SkillRunner(get_provider(), hooks=hooks, workspace_id=str(scope.workspace_id)),
        hooks=hooks,
        grounding={"user_context": dict(user_context)} if user_context else {},
        actor_user_id=str(scope.user_id),
    )


def _rehydrate(stored: store.StoredSession, company_name: str = "") -> AgentState:
    """Rebuild the agent's working state from what is on disk.

    The agent holds no memory between requests. Everything it needs is in the
    session row and its turns — which is also what makes a second tab, a refresh
    or a different device land on the same conversation rather than a private
    copy of it.
    """
    state = AgentState(
        session_id=stored.id,
        workspace_id=str(stored.workspace_id),
        domain=stored.domain or "",
        company_name=company_name,
        phase=stored.phase,
    )
    state.research = dict(stored.research)
    state.brief = dict(stored.brief)
    state.answers = stored.answers
    state.turns = [
        Turn(role=t.role, text=t.text, target_field=t.target_field, scope=t.scope)
        for t in stored.turns
    ]
    state.asked = sum(1 for t in stored.turns if t.role == "agent" and t.target_field)
    return state


def _out(stored: store.StoredSession, viewer: ViewerOut | None = None) -> StateOut:
    return StateOut(
        viewer=viewer or ViewerOut(),
        active=stored.status == "active",
        completed=stored.status == "completed",
        phase=stored.phase,
        domain=stored.domain,
        turns=[
            TurnOut(role=t.role, text=t.text, target=t.target_field, scope=t.scope)
            for t in stored.turns
        ],
        brief=dict(stored.brief),
        persona=dict(stored.persona_draft),
        context=dict(stored.context),
        answered=len(stored.answers),
        pages_read=[
            str(page.get("url", ""))
            for page in stored.research.get("crawl", {}).get("pages", [])
            if page.get("url")
        ],
    )


async def _state(db: Any, scope: ScopedSession, stored: store.StoredSession) -> StateOut:
    """`_out` plus the viewer — what every endpoint returns.

    A wrapper rather than a parameter each endpoint remembers to pass, because
    the greeting is drawn from the *latest* response and the component replaces
    its state wholesale. One handler returning a bare `_out` would blank the
    greeting the moment somebody answered a question, and only on that endpoint.
    """
    return _out(stored, await _viewer(db, scope))


async def _workspace_identity(db: Any, scope: ScopedSession) -> tuple[str, str]:
    """The domain and name to research, read from the workspace.

    Deliberately not from the request body. The client used to send both, which
    meant a caller could point the crawl at any domain they liked and have the
    result attached to their own workspace — the company's Brain would then
    describe somebody else's business, sourced and cited. The workspace row is
    the only authority on which company this is.
    """
    row = (
        await db.execute(
            sa.text("SELECT name, domain FROM workspace WHERE id = :w"),
            {"w": scope.workspace_id},
        )
    ).mappings().first()
    if row is None or not row["domain"]:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": "no_company_yet",
                "message": "Register your company before starting onboarding.",
            },
        )
    return str(row["domain"]), str(row["name"])


async def _user_context(db: Any, scope: ScopedSession) -> dict[str, str]:
    """Who is answering, and what they say they do.

    Read from `app_user` and `membership` rather than accepted from the client,
    for the same reason the domain is: a caller who could supply their own
    designation could supply anything, and this steers what the agent asks.

    **`role` and `departments` are deliberately not read here.** Those are the
    authorising pair, and putting them in front of a model — even to phrase a
    question — starts the habit of treating them as conversational material.
    What this returns is what the person *said about themselves*: a name to use,
    a job title, a department. None of it reaches a permission check.

    Absent values are omitted rather than sent empty, so a skill can tell "no
    name given" from "the name is an empty string" and decline to guess.
    """
    return {key: value for key, value in (await _who(db, scope)).items() if key != "company"}


async def _who(db: Any, scope: ScopedSession) -> dict[str, str]:
    """The one query behind both the grounding and the greeting.

    Two callers wanted the same row for different audiences — a model, and a
    person — and writing the join twice is how the two drift until the screen
    greets somebody by a name the agent is not using. `_user_context` drops
    `company` because the skills already carry the company through
    `state.company_name`; `_viewer` keeps it because the greeting says it out
    loud.

    Empty values are dropped rather than returned blank, so a caller can tell
    "no department given" from "the department is an empty string" and decline
    to guess. `membership` is joined, not outer-joined: no live membership means
    no answer at all, which is what the previous shape returned too.
    """
    row = (
        await db.execute(
            sa.text(
                "SELECT u.display_name, m.designation, m.stated_department, w.name AS company"
                " FROM app_user u"
                " JOIN membership m ON m.user_id = u.id AND m.workspace_id = :w"
                " JOIN workspace w ON w.id = :w"
                " WHERE u.id = :u AND m.revoked_at IS NULL"
            ),
            {"w": scope.workspace_id, "u": scope.user_id},
        )
    ).mappings().first()
    if row is None:
        return {}
    out = {
        "name": row["display_name"],
        "designation": row["designation"],
        "department": row["stated_department"],
        "company": row["company"],
    }
    return {key: str(value) for key, value in out.items() if value}


async def _viewer(db: Any, scope: ScopedSession) -> ViewerOut:
    """The greeting's raw material. Absent fields stay `None`."""
    return ViewerOut(**await _who(db, scope))


async def _deep_research(db: Any, scope: ScopedSession) -> dict[str, Any]:
    """Whatever the background research run has finished, or nothing.

    The interview and the twenty-page crawl race each other by design, and this
    is the moment they meet. A founder who answered quickly finishes first, and
    is not made to wait — an empty return here means the Brain is built from the
    three pages onboarding read and names what it does not yet know.

    Only `succeeded` sources are read. A `failed` one has no pages, and a
    `skipped` one is a step nobody has built; folding either in as an empty
    result would put "we found nothing" where "we have not looked" is true.
    """
    rows = (
        await db.execute(
            sa.text(
                "SELECT s.kind, s.result_json FROM research_source s"
                " JOIN research_run r ON r.id = s.run_id"
                " WHERE s.workspace_id = :w AND s.state = 'succeeded'"
                "   AND s.result_json IS NOT NULL"
                " ORDER BY r.requested_at DESC, s.finished_at DESC"
            ),
            {"w": scope.workspace_id},
        )
    ).mappings().all()

    pages: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        payload = row["result_json"]
        if isinstance(payload, str):
            payload = json.loads(payload)
        for page in (payload or {}).get("pages", []):
            url = str(page.get("url", ""))
            if url and url not in seen:
                seen.add(url)
                pages.append(page)
    if not pages:
        return {}
    log.info("onboarding.deep_research.folded_in", pages=len(pages))
    return {"pages": pages}


async def _load(db: Any, scope: ScopedSession) -> store.StoredSession:
    stored = await store.active(db, workspace_id=scope.workspace_id)
    if stored is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="no onboarding in progress; POST /onboarding/agent/start first",
        )
    return stored


# ── Endpoints ─────────────────────────────────────────────────


@router.get("/state", response_model=StateOut)
async def read_state(scope: CurrentScope) -> StateOut:
    """Where the journey is. Safe to poll, and works with no model configured."""
    async with scoped_connection(scope) as db:
        # `latest`, not `active`: a finished journey must be reported as
        # finished rather than as "none in progress".
        stored = await store.latest(db, workspace_id=scope.workspace_id)
        if stored is None:
            return StateOut(active=False, phase="analysing", viewer=await _viewer(db, scope))
        return await _state(db, scope, stored)


@router.post("/start", response_model=StateOut, dependencies=[Depends(require_csrf)])
async def start(scope: CurrentScope) -> StateOut:
    """Open the session and fetch the site. Fast — about three seconds.

    Reading what was fetched is `POST /read`, and the split is the point.

    The two were one request that took twenty-five seconds behind a single
    unchanging line, which reads as a hang. Almost all of that was two
    sequential model calls; the fetch itself is ~3s. Returning here lets the
    screen say something true and specific — *these six pages, from this
    domain* — while the slow half runs, instead of a spinner over an empty page.

    It also takes the model calls out of this transaction. The old shape held
    the session row uncommitted across the whole crawl-and-read, which is what
    made a concurrent Start queue on the single-active-session index until the
    statement timed out.
    """
    _require_model()
    async with scoped_connection(scope) as db:
        previous = await store.latest(db, workspace_id=scope.workspace_id)
        if previous is not None and previous.status == "completed":
            # Not an error the caller can fix by retrying, and not something to
            # do silently: a second run would build a second Brain over the one
            # this workspace is already using.
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "error": "already_onboarded",
                    "message": "This workspace has already been set up.",
                },
            )
        # The name is not needed until `/read`; this call is here for the domain
        # and for its refusal when no company exists yet.
        domain, _ = await _workspace_identity(db, scope)
        try:
            session_id = await store.start(
                db, workspace_id=scope.workspace_id, user_id=scope.user_id, domain=domain
            )
        except store.StartInFlightError as exc:
            # A second Start arrived while the first was still crawling and
            # reading. Refusing immediately is the kind answer: the alternative
            # is queueing behind a transaction that runs for half a minute and
            # then reporting a statement timeout as if the caller broke something.
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "error": "already_starting",
                    "message": "This workspace is already being set up. Try again in a moment.",
                },
            ) from exc
        stored = await _load(db, scope)
        if stored.turns:
            # Already started. Returning the state is the right answer to a
            # repeated Start — re-crawling would spend tokens to arrive here.
            return await _state(db, scope, stored)

        if stored.research.get("crawl"):
            # Already fetched. Re-crawling on a repeated Start would spend the
            # company's bandwidth to arrive exactly here.
            return await _state(db, scope, stored)

        outcome = await crawl_site([f"https://{domain}"], limit=ONBOARDING_PAGE_BUDGET)
        if not outcome.pages:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "error": "nothing_to_read",
                    "message": f"Could not read any pages at {domain}.",
                    "reason": outcome.error_reason or "no pages returned",
                },
            )

        # Held under `research.crawl` rather than passed back through the
        # client. The pages are the grounding every claim in the brief is
        # traceable to, and grounding that made a round trip through a browser
        # is grounding a browser could have edited.
        await store.save_crawl(
            db, session_id=session_id, pages=[dict(page) for page in outcome.pages]
        )
        return await _state(db, scope, await _load(db, scope))


@router.post("/read", response_model=StateOut, dependencies=[Depends(require_csrf)])
async def read(scope: CurrentScope) -> StateOut:
    """Read the fetched pages and write the brief. The slow half — ~17s.

    Separate from `/start` so the screen has the fetch to show while this runs.
    Idempotent: called twice, the second returns the brief the first wrote
    rather than paying for it again.
    """
    _require_model()
    async with scoped_connection(scope) as db:
        stored = await _load(db, scope)
        if stored.turns:
            return await _state(db, scope, stored)

        pages = list(stored.research.get("crawl", {}).get("pages", []))
        if not pages:
            # `/read` before `/start`, or after a session was opened and the
            # crawl never landed. Nothing to read is a sequencing error, not a
            # failure of the site.
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "error": "nothing_fetched",
                    "message": "No pages have been fetched yet; POST /start first.",
                },
            )

        domain, company_name = await _workspace_identity(db, scope)
        agent = OnboardingAgent(_context(scope, db, await _user_context(db, scope)))
        state = AgentState(
            session_id=stored.id,
            workspace_id=str(scope.workspace_id),
            domain=domain,
            company_name=company_name,
        )
        try:
            state = await agent.start(state, pages=pages)
        except SkillFailedError as exc:
            raise _unusable(exc) from exc

        for turn in state.turns:
            await store.append_turn(
                db, session_id=stored.id, workspace_id=scope.workspace_id,
                role=turn.role, text=turn.text, target_field=turn.target_field,
                skill=turn.skill, skill_version=turn.skill_version,
            )
        return await _state(db, scope, await _load(db, scope))


@router.post("/brief", response_model=StateOut, dependencies=[Depends(require_csrf)])
async def confirm_brief(payload: BriefIn, scope: CurrentScope) -> StateOut:
    """Confirm the brief, correcting any line. A correction outranks the crawl."""
    _require_model()
    async with scoped_connection(scope) as db:
        stored = await _load(db, scope)
        agent = OnboardingAgent(_context(scope, db, await _user_context(db, scope)))
        state = _rehydrate(stored)
        # Reject a correction to a field the catalogue does not declare before
        # anything is written — the same gate a generated question passes.
        for key in payload.corrections:
            try:
                resolve(key)
            except UndeclaredFieldError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc

        await agent.confirm_brief(state, payload.corrections)
        for key, value in payload.corrections.items():
            await store.append_turn(
                db, session_id=stored.id, workspace_id=scope.workspace_id,
                role="user", text=value, target_field=key,
            )
        await db.execute(
            sa.text(
                "UPDATE onboarding_session SET phase = 'discovery', updated_at = now()"
                " WHERE id = :sid"
            ),
            {"sid": stored.id},
        )
        return await _state(db, scope, await _load(db, scope))


@router.post("/discovery", response_model=StateOut, dependencies=[Depends(require_csrf)])
async def open_discovery(payload: DiscoveryIn, scope: CurrentScope) -> StateOut:
    """The one free-text turn — what they are responsible for, in their words."""
    _require_model()
    async with scoped_connection(scope) as db:
        stored = await _load(db, scope)
        agent = OnboardingAgent(_context(scope, db, await _user_context(db, scope)))
        state = _rehydrate(stored)
        try:
            await agent.open_discovery(state, payload.answer)
        except SkillFailedError as exc:
            raise _unusable(exc) from exc
        await store.append_turn(
            db, session_id=stored.id, workspace_id=scope.workspace_id,
            role="user", text=payload.answer, target_field="persona.stated_purpose",
            skill="user-discovery",
        )
        return await _state(db, scope, await _load(db, scope))


@router.get("/next", response_model=QuestionOut)
async def next_question(scope: CurrentScope) -> QuestionOut:
    """The next question, chosen and worded by the model, bound to a declared field."""
    _require_model()
    async with scoped_connection(scope) as db:
        stored = await _load(db, scope)
        agent = OnboardingAgent(_context(scope, db, await _user_context(db, scope)))
        state = _rehydrate(stored)
        try:
            result = await agent.next_question(state)
        except SkillFailedError as exc:
            raise _unusable(exc) from exc

        if result is None:
            return QuestionOut(done=True, reason="nothing further worth asking")

        await store.append_turn(
            db, session_id=stored.id, workspace_id=scope.workspace_id,
            role="agent", text=str(result["question"]),
            target_field=str(result["target"]),
            skill=str(result.get("skill", "")),
            skill_version=str(result.get("skill_version", "")),
        )
        return QuestionOut(
            done=False,
            question=str(result["question"]),
            target=str(result["target"]),
            scope=int(result["scope"]),
            choices=list(result.get("choices", [])),
        )


@router.post("/answer", response_model=StateOut, dependencies=[Depends(require_csrf)])
async def submit_answer(payload: AnswerIn, scope: CurrentScope) -> StateOut:
    """Answer the outstanding question.

    The body carries text and nothing else. The field it belongs to is the one
    the agent's own last turn declared — read server-side, never accepted from
    the client.
    """
    _require_model()
    async with scoped_connection(scope) as db:
        stored = await _load(db, scope)
        target = next(
            (
                t.target_field
                for t in reversed(stored.turns)
                if t.role == "agent" and t.target_field
            ),
            None,
        )
        if target is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="no outstanding question; GET /onboarding/agent/next first",
            )
        agent = OnboardingAgent(_context(scope, db, await _user_context(db, scope)))
        await agent.submit_answer(_rehydrate(stored), target=target, text=payload.text)
        await store.append_turn(
            db, session_id=stored.id, workspace_id=scope.workspace_id,
            role="user", text=payload.text, target_field=target,
        )
        return await _state(db, scope, await _load(db, scope))


@router.post("/finish", response_model=StateOut, dependencies=[Depends(require_csrf)])
async def finish(scope: CurrentScope) -> StateOut:
    """Assemble the Persona, the Brain and the context every later agent reads."""
    _require_model()
    async with scoped_connection(scope) as db:
        stored = await _load(db, scope)
        agent = OnboardingAgent(_context(scope, db, await _user_context(db, scope)))
        state = _rehydrate(stored)
        try:
            result = await agent.finish(
                state,
                role_reach={"role": str(scope.role)},
                deep_research=await _deep_research(db, scope),
            )
        except SkillFailedError as exc:
            raise _unusable(exc) from exc
        await store.complete(db, session_id=stored.id, context=dict(result["context"]))
        # By id, not by `active`: the session is `completed` now, and `_load`
        # would report no journey in progress on the request that finished it.
        closed = await store.by_id(db, session_id=stored.id)
        assert closed is not None
        return await _state(db, scope, closed)


def _unusable(exc: SkillFailedError) -> HTTPException:
    """A skill ran and produced nothing usable.

    502 rather than 500: the provider answered, the answer was unusable. Never a
    plausible default — a fabricated brief is the thing this product exists not
    to produce, and it would be indistinguishable from a real one on screen.
    """
    log.warning("onboarding.skill_failed", error=str(exc))
    return HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail={
            "error": "skill_failed",
            "message": "The assistant could not produce a usable answer. Nothing was saved.",
        },
    )
