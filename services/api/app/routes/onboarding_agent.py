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
from collections.abc import Mapping, Sequence
from typing import Any

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.ai.registry import get_provider
from app.ai.runtime.commands import CommandContext
from app.ai.runtime.fields import (
    BRAIN_GROUPS,
    FIELD_CATALOGUE,
    UndeclaredFieldError,
    resolve,
)
from app.ai.runtime.hooks import get_hooks
from app.ai.runtime.runner import SkillFailedError, SkillRunner
from app.auth.csrf import require_csrf
from app.deps import CurrentScope
from app.domain import connections
from app.domain import onboarding_sessions as store
from app.domain.connections import UnknownProviderError
from app.domain.departments import label_for, selected_departments
from app.domain.onboarding_agent import (
    MAX_QUESTIONS,
    AgentState,
    OnboardingAgent,
    Turn,
    next_brain_group,
)
from app.domain.onboarding_promotion import promote
from app.domain.scopes import Department
from app.domain.session import ScopedSession
from app.logging import get_logger
from app.research.runner import crawl_site, is_prose
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

    assembly_step: int = 0
    """How many assembly stages have committed. Monotone, and the client's only
    way to tell two consecutive Brain groups apart.

    The phase alone cannot: the Brain is several committed steps that all leave
    the row at `persona`, so a loop watching only the phase sees "nothing moved"
    after the first group and stops with a half-built Brain. This counts, so
    "the phase did not change *and* neither did this" is a real stall.
    """

    site_unreadable: bool = False
    """The crawl ran and the site gave us nothing.

    Distinct from `pages_read` being empty, which is also true before the crawl
    has happened. The screen needs to tell "still fetching" from "there is
    nothing to fetch and it is your turn to talk", and only the second one may
    replace the reading bubble with three questions.
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


class DescribeIn(BaseModel):
    """The three things the crawl would have told us, from the founder instead.

    Deliberately three, and deliberately these three: they are what every later
    skill needs as grounding. `profile` becomes `company_profile`, which
    `interpret-user` and `build-persona` both declare in
    `requires_grounding` — without it the persona is assembled by a model that
    has not been told what the company does.
    """

    profile: str = Field(min_length=1, max_length=2000)
    target_customers: str = Field(min_length=1, max_length=2000)
    goals: str = Field(min_length=1, max_length=2000)


class DocumentsIn(BaseModel):
    """Leaving the documents step. `skipped` is a record, not a permission.

    The step is skippable either way — `doc/09` §6.2 — so this does not decide
    whether the phase advances. What it decides is what gets *logged*: a founder
    who pressed "Skip for now" and one who uploaded nothing and pressed
    "Continue" are the same row and two different product problems, and only the
    flag can tell them apart.
    """

    skipped: bool = False


class ToolsIn(BaseModel):
    """The systems this company runs on, by catalogue id.

    A list of ids and nothing else. In particular **no state and no
    credentials**: every row this writes is `declared`, because declaring is all
    this endpoint can honestly do until the OAuth half lands. A client that
    could send `state` could write `connected` against a system nobody has ever
    reached, and every tile downstream would then render a stale figure as live.
    """

    providers: list[str] = Field(default_factory=list, max_length=connections.MAX_DECLARED)
    skipped: bool = False


class ToolOut(BaseModel):
    id: str
    name: str
    department: str
    department_label: str
    unlocks: str
    kind: str
    declared: bool
    connectable: bool
    """Whether a connect flow exists for this tool **today**. False for all nine.

    On the wire rather than assumed by the screen, so the day one becomes true
    the button appears without a second list in TypeScript to remember to edit.
    A screen that hard-coded "we will ask you to connect this later" would go on
    saying it after it stopped being true.
    """


class ToolsOut(BaseModel):
    """The catalogue, ordered for this company, with what it already declared."""

    tools: list[ToolOut] = Field(default_factory=list)
    declared: list[str] = Field(default_factory=list)


class QuestionOut(BaseModel):
    done: bool
    question: str | None = None
    target: str | None = None
    scope: int | None = None
    choices: list[str] = Field(default_factory=list)
    reason: str | None = None


class AnswerOut(BaseModel):
    """An answer recorded and the question that follows it, in one round trip.

    The client used to post the answer and then `GET /next`, sequentially. Both
    requests opened a transaction, set the scoping GUC, loaded the session and
    all its turns, and read the same `app_user`/`membership` row — so the second
    one repeated about seven statements purely to arrive back where the first
    already was. Against a database ~340ms away that is over two seconds per
    question, spent on nothing.

    `question` is nullable, and that is load-bearing rather than defensive.
    `scoped_connection` wraps the whole handler in one transaction, so letting a
    failure in question generation raise here would roll back **the answer that
    had just been stored** — the person would retype a sentence the server had
    already accepted. Instead the failure is logged, `question` comes back null,
    and the client falls back to `GET /next`, which is the endpoint that still
    exists precisely to be retried.
    """

    state: StateOut
    question: QuestionOut | None = None


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


def _labelled_brief(brief: Mapping[str, Any]) -> dict[str, Any]:
    """The brief, with each statement carrying the field's human label.

    The screen was rendering the raw catalogue key over every statement —
    `brain.products_services` above a paragraph a founder is being asked to
    correct. That is an internal identifier and it reads like a leaked variable
    name on the first screen anybody sees.

    Resolved here rather than mapped in the browser, because the label lives in
    `fields.py` with the scope and the column, and a second copy in TypeScript
    is a second thing to keep in step. `field` stays on the wire untouched: it
    is what a correction is keyed by, and that must remain the real key.

    A statement naming a field the catalogue does not have keeps its key as the
    label. It cannot be corrected either way, and inventing a prettier name for
    a field that does not exist would hide that.
    """
    statements = brief.get("statements")
    if not isinstance(statements, list):
        return dict(brief)

    labelled: list[dict[str, Any]] = []
    for statement in statements:
        if not isinstance(statement, dict):
            continue
        key = str(statement.get("field", ""))
        spec = FIELD_CATALOGUE.get(key)
        labelled.append({**statement, "label": spec.label if spec else key})
    return {**brief, "statements": labelled}


def _assembly_step(stored: store.StoredSession) -> int:
    """A monotone count of committed assembly stages.

    Persona is one, each Brain group is one more, the context is the last. Not a
    percentage and never shown: it exists so the client's assembly loop can
    distinguish "another group just committed" from "the server returned the
    same state twice", which the phase cannot express while several steps share
    the phase `persona`.
    """
    # `documents` and `tools` sit between the interview and the assembly, so
    # nothing has been assembled while a session is in either — the same as
    # `discovery`. Listed explicitly rather than left to the fallthrough below,
    # which returns "everything is done" and would have told the client's
    # assembly loop that a journey yet to build its persona was complete.
    if stored.phase in ("analysing", "brief", "discovery", "documents", "tools"):
        return 0
    done = len(dict(stored.context).get("groups_done", []))
    if stored.phase == "persona":
        return 1 + done
    # `assembling` means every group landed, whatever the row happens to say.
    if stored.phase == "assembling":
        return 1 + len(BRAIN_GROUPS)
    return 2 + len(BRAIN_GROUPS)


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
        brief=_labelled_brief(stored.brief),
        persona=dict(stored.persona_draft),
        context=dict(stored.context),
        # The same number the ceiling is checked against — agent turns carrying
        # a target — not `len(answers)`, which also counts the brief corrections
        # and the three `/describe` turns. Every completed run reported
        # `answered: 6, ceiling: 5`, so the one field a reader would use to
        # check the ceiling said the opposite of what the code does.
        answered=sum(1 for t in stored.turns if t.role == "agent" and t.target_field),
        assembly_step=_assembly_step(stored),
        pages_read=[
            str(page.get("url", ""))
            for page in stored.research.get("crawl", {}).get("pages", [])
            if page.get("url")
        ],
        site_unreadable=bool(stored.research.get("crawl", {}).get("unreadable")),
    )


async def _state(
    db: Any,
    scope: ScopedSession,
    stored: store.StoredSession,
    who: Mapping[str, str] | None = None,
) -> StateOut:
    """`_out` plus the viewer — what every endpoint returns.

    A wrapper rather than a parameter each endpoint remembers to pass, because
    the greeting is drawn from the *latest* response and the component replaces
    its state wholesale. One handler returning a bare `_out` would blank the
    greeting the moment somebody answered a question, and only on that endpoint.

    `who` is the row a handler has already read for the agent's grounding.
    Passing it in is worth a parameter: `_user_context` and `_viewer` are the
    same query behind two names, and a handler that needed both was paying for
    it twice — a wasted round trip on the hot path of every turn.
    """
    return _out(stored, _viewer_of(who if who is not None else await _who(db, scope)))


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
    return _user_context_of(await _who(db, scope))


def _user_context_of(who: Mapping[str, str]) -> dict[str, str]:
    """The grounding half of `_who`, for a handler that already holds the row."""
    return {key: value for key, value in who.items() if key != "company"}


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


def _viewer_of(who: Mapping[str, str]) -> ViewerOut:
    """The greeting's raw material, from a row already read.

    `department` is stored as the catalogue key — `hr`, not "People" — because
    narrowing the question catalogue to a department needs the machine-readable
    form (`askable_fields`). The greeting needs the other one: "you work at
    Gusto, in hr" is not a sentence, and that is exactly what a browser showed
    when this resolution lived only in `_viewer` while `_state` built its own
    `ViewerOut` and bypassed it. **One function, both callers.**

    Anything the catalogue does not recognise passes through untouched. Rows
    written before the field became a dropdown hold free text — "Design",
    "People" — and rewriting somebody's own words into the nearest official
    department would be putting a claim in their mouth.
    """
    resolved = dict(who)
    stored = resolved.get("department")
    if stored:
        try:
            resolved["department"] = label_for(Department(stored))
        except ValueError:
            pass  # Free text from before the dropdown. Their words, kept.
    return ViewerOut(**resolved)


async def _viewer(db: Any, scope: ScopedSession) -> ViewerOut:
    """`_viewer_of` over a freshly read row. Absent fields stay `None`."""
    return _viewer_of(await _who(db, scope))


DEEP_RESEARCH_PAGE_LIMIT = 8
"""How many background-crawl pages the Brain builder is given.

There was no limit, and for a company with a busy site that meant twenty full
pages of prose in one prompt. Measured: with all twenty folded in, the Brain
build ran past the 240s proxy timeout and was killed — twice, before the field
groups existed, and then again on the `market` group after they did. The
`identity` group finished in 47s on the same input, so the wall is not the field
count; it is the size of what every group has to read.

Eight is a judgement, not a measurement, and it is a real trade: pages nine to
twenty stop contributing, so a claim that only appears deep in a blog archive
will now show up as a known gap instead of a sourced value. That is the right
direction for this product — a gap names its own unlock, and a Brain nobody can
finish assembling has no values at all — but it is the kind of number to revisit
with a real corpus rather than to treat as settled.

Ordered by the query below, so the eight are the most recently finished sources'
pages rather than an arbitrary eight.
"""


async def _deep_research(db: Any, scope: ScopedSession) -> dict[str, Any]:
    """Whatever the background research run has finished, capped. Or nothing.

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
    # Capped, and the drop is logged rather than silent: "we read twenty pages"
    # and "we gave the builder twenty pages" were the same sentence in the logs
    # while only one of them was true, and that is what made the timeout hard to
    # attribute.
    kept = pages[:DEEP_RESEARCH_PAGE_LIMIT]
    log.info(
        "onboarding.deep_research.folded_in",
        pages=len(kept),
        available=len(pages),
        dropped=len(pages) - len(kept),
    )
    return {"pages": kept}


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

        # `crawl_site` is documented to return rather than raise, "including
        # when everything fails". Wrapped anyway: this is the first request of
        # a customer's life in the product, the account and the company row
        # already exist by the time it runs, and an exception here is the one
        # that leaves them with no workspace and no way to make one. If the
        # contract ever slips, it must not slip into a 500 on the signup path.
        try:
            outcome = await crawl_site([f"https://{domain}"], limit=ONBOARDING_PAGE_BUDGET)
        except Exception:
            log.exception("onboarding.crawl.raised", domain=domain)
            outcome = None

        # Filtered, not just counted. A response the fetcher could not decode
        # comes back as a non-empty string of replacement characters, so it
        # passes every "did we get anything?" test and then either kills the
        # request (`jsonb` refuses its NUL bytes) or reaches a model as the
        # company's own words. `is_prose` carries the measurement.
        fetched = list(outcome.pages) if outcome is not None else []
        pages = [page for page in fetched if is_prose(page.get("text", ""))]
        if len(pages) < len(fetched):
            log.info(
                "onboarding.crawl.undecodable_pages_dropped",
                domain=domain,
                dropped=len(fetched) - len(pages),
                kept=len(pages),
            )
        if not pages:
            # **Recorded and returned, not refused.** This used to be a 422, and
            # a 422 here is a dead end: the account exists, the company row
            # exists, and the only screen that could build a workspace has told
            # the customer their website is unreadable and offered them nothing.
            # An audit of nine real sites found two in this state — one behind
            # Cloudflare — so it is not an edge case, it is a signup funnel that
            # drops customers whose only fault is bot protection.
            #
            # The state now says the site could not be read, and `/describe`
            # lets the founder supply what the crawl would have. ADR 0022 is not
            # in the way: it rules out a scripted *alternative to the agent* when
            # no model is configured. The agent still runs here — only the source
            # of its opening facts changes, from the site to the person, which is
            # the same precedence the brief step already grants them when it says
            # "you outrank the website".
            reason = (
                (outcome.error_reason if outcome is not None else "")
                or ("nothing readable in the pages returned" if fetched else "no pages returned")
            )
            log.info("onboarding.crawl.unreadable", domain=domain, reason=reason)
            await store.save_crawl(
                db, session_id=session_id, pages=[], unreadable_reason=reason
            )
            return await _state(db, scope, await _load(db, scope))

        # Held under `research.crawl` rather than passed back through the
        # client. The pages are the grounding every claim in the brief is
        # traceable to, and grounding that made a round trip through a browser
        # is grounding a browser could have edited.
        await store.save_crawl(db, session_id=session_id, pages=[dict(p) for p in pages])
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
            # Two different states, and telling a caller to run `/start` is only
            # right for one of them. If the crawl already ran and the site gave
            # nothing, `/start` will do exactly the same thing again — the way
            # forward is `/describe`, and saying so is the difference between a
            # recoverable error and a loop.
            unreadable = bool(stored.research.get("crawl", {}).get("unreadable"))
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "error": "site_unreadable" if unreadable else "nothing_fetched",
                    "message": (
                        f"{stored.domain} could not be read; POST /describe instead."
                        if unreadable
                        else "No pages have been fetched yet; POST /start first."
                    ),
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


# The three fields, in catalogue order, paired with the sentence the transcript
# shows for each. Declared keys, so what a founder types here is stored at the
# same sensitivity and with the same provenance machinery as any interview
# answer — a manual brief is a different *source*, not a different kind of fact.
_DESCRIBE_FIELDS: tuple[tuple[str, str, str], ...] = (
    ("brain.profile", "profile", "In a sentence or two, what does the company do?"),
    ("brain.target_customers", "target_customers", "Who actually buys from you?"),
    ("brain.goals", "goals", "What would make the next twelve months a success?"),
)


@router.post("/describe", response_model=StateOut, dependencies=[Depends(require_csrf)])
async def describe(payload: DescribeIn, scope: CurrentScope) -> StateOut:
    """The brief, from the founder, when the site could not be read.

    **Only reachable when the crawl produced nothing.** Offering it otherwise
    would be offering a way to skip the read, and the read is what makes the
    brief correctable rather than merely typed.

    **It goes straight to `discovery`, skipping the brief step.** That step
    exists so a person can correct what a machine claimed about them; there is
    nothing to correct in three sentences they wrote ten seconds ago, and
    asking "is this right?" about their own words is the kind of small
    absurdity that makes the rest of the screen harder to believe.

    No model call. The three answers are already the values — they are written
    into `research` in the shape `company-research` produces so every later
    skill's grounding is satisfied, and into the turn log against their declared
    fields so `state.answers` carries them at the same precedence a brief
    correction gets. Running a summariser over prose the author just typed would
    spend twenty seconds to paraphrase them back.
    """
    _require_model()
    async with scoped_connection(scope) as db:
        stored = await _load(db, scope)
        if not stored.research.get("crawl", {}).get("unreadable"):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "error": "site_was_readable",
                    "message": "This workspace's site was read; confirm the brief instead.",
                },
            )
        if stored.turns:
            # Already described. Returning the state is the right answer to a
            # repeat, and it keeps a double submit from doubling the transcript.
            return await _state(db, scope, stored)

        values = {name: getattr(payload, name).strip() for _, name, _ in _DESCRIBE_FIELDS}

        # Written in `company-research`'s own output shape. `confidence` is
        # "stated" — a third value alongside its "read" and "inferred", and the
        # honest one: nobody read this and nobody inferred it. `source` is the
        # person rather than a URL, because a citation has to point at something
        # and here it points at them.
        research = {
            "profile": {
                "found": True, "value": values["profile"],
                "confidence": "stated", "source": "you",
            },
            "products_services": {"found": False},
            "brand_voice": {"found": False},
            "technology_seen": [],
            "could_not_determine": [
                {
                    "topic": "Everything the website would have said",
                    "why": f"{stored.domain} could not be read: "
                    f"{stored.research.get('crawl', {}).get('reason', 'no pages returned')}",
                }
            ],
            "pages_read": 0,
        }
        await store.save_research(db, session_id=stored.id, research=research)

        agent_line = (
            f"I could not read {stored.domain} — it may be behind bot protection, or "
            "there may be nothing there yet. That is not a problem: tell me the three "
            "things I would have looked for and we can carry on."
        )
        stored.turns.append(
            await store.append_turn(
                db, session_id=stored.id, workspace_id=scope.workspace_id,
                role="agent", text=agent_line,
            )
        )
        for key, name, question in _DESCRIBE_FIELDS:
            stored.turns.append(
                await store.append_turn(
                    db, session_id=stored.id, workspace_id=scope.workspace_id,
                    # **No `target_field` on the agent turn, deliberately.**
                    # `_rehydrate` counts `asked` as "agent turns carrying a
                    # target", so tagging these three spent three of the five
                    # interview questions before the interview began — and the
                    # people on this path are the ones whose site could not be
                    # read, so they are exactly who needs the full five. An
                    # audit measured it: `answered: 6, ceiling: 5` after two
                    # real questions.
                    #
                    # The target belongs on the *user* turn, which is what
                    # `StoredSession.answers` reads, so nothing is lost: the
                    # answers still land against their declared fields at the
                    # catalogue's scope. The question still shows in the
                    # transcript — an agent turn with no target renders as an
                    # ordinary bubble.
                    role="agent", text=question,
                )
            )
            stored.turns.append(
                await store.append_turn(
                    db, session_id=stored.id, workspace_id=scope.workspace_id,
                    role="user", text=values[name], target_field=key,
                )
            )

        await store.set_phase(db, session_id=stored.id, phase=store.Phase.DISCOVERY)
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


def _outstanding_question(stored: store.StoredSession) -> store.StoredTurn | None:
    """The last agent question, if nobody has answered it yet.

    "Unanswered" means no *later* turn carries the same target — not merely that
    the transcript ends on an agent turn. A brief correction or the opening
    discovery answer can land after a question is asked without answering it.
    """
    last = next(
        (t for t in reversed(stored.turns) if t.role == "agent" and t.target_field),
        None,
    )
    if last is None:
        return None
    answered = any(
        t.role == "user" and t.target_field == last.target_field and t.seq > last.seq
        for t in stored.turns
    )
    return None if answered else last


async def _ask_next(
    db: Any,
    scope: ScopedSession,
    stored: store.StoredSession,
    who: Mapping[str, str],
) -> QuestionOut:
    """Generate the next question, record it, and add it to `stored` in place.

    Shared by `/next`, `/answer` and `/discovery` so that "ask the next thing"
    is written once. Mutating `stored.turns` rather than re-reading the session
    is the point: the caller is holding the row it just wrote to, and fetching
    it again to discover the turn it appended itself is two round trips to learn
    something already known.

    Raises `SkillFailedError`. The caller decides what that means, because it
    differs: `/next` is the retry endpoint and turns it into a 502, while
    `/answer` has an answer committed in the same transaction and must not let
    it roll back.

    **An outstanding question is re-served, never regenerated.** This used to
    generate unconditionally, and `AgentOnboarding` calls `nextQuestion()` on
    every resume into `discovery` — so any page refresh mid-question wrote a
    second agent turn for the same field. An audited transcript shows the cost:

        11. agent  fact.hr.leave_basis   Is leave accrued monthly or granted annually?
        12. agent  fact.hr.leave_basis   Is leave accrued monthly or granted annually?

    `submit_answer` reads the target from the *last* agent turn, so turn 11 was
    orphaned and unanswerable. Worse, `asked` counts agent turns carrying a
    target, so five turns for three real questions tripped the ceiling — the
    person was told "that is the 5 questions I get to ask" after answering
    three, one of them twice. Each duplicate also spent a model call.
    """
    outstanding = _outstanding_question(stored)
    if outstanding is not None:
        log.info("onboarding.question.reserved", target=outstanding.target_field)
        spec = resolve(str(outstanding.target_field))
        return QuestionOut(
            done=False,
            question=outstanding.text,
            target=spec.key,
            scope=spec.scope,
            choices=[],
        )

    agent = OnboardingAgent(_context(scope, db, _user_context_of(who)))
    result = await agent.next_question(_rehydrate(stored))
    if result.get("done"):
        # The interview is over, so the phase moves on here rather than waiting
        # for a click. Two reasons it belongs on this side of the wire.
        #
        # **The client cannot be the one to say the interview ended.** Every
        # other transition in this journey is decided by the server from state
        # it holds — the target of an answer, which assembly stage runs next —
        # for the same reason: a client that could name the next phase could
        # name `persona` and skip the two steps in between, which is exactly
        # the ordering the feature exists to guarantee.
        #
        # **A refresh must not undo it.** `AgentOnboarding` used to hold "the
        # interview is done" only in the `question.done` it had in memory, so
        # reloading the page dropped it and the screen came back to a composer
        # over a closed interview. The phase is on the row, so the reload lands
        # on the documents step.
        #
        # Guarded on the current phase rather than written unconditionally:
        # `/next` is the resume endpoint and is called again on a session
        # already past discovery, where this would drag the phase backwards.
        if stored.phase == store.Phase.DISCOVERY.value:
            await store.set_phase(
                db, session_id=stored.id, phase=store.Phase.DOCUMENTS.value
            )
            stored.phase = store.Phase.DOCUMENTS.value
            log.info(
                "onboarding.interview_closed",
                session_id=str(stored.id),
                asked=sum(1 for t in stored.turns if t.role == "agent" and t.target_field),
            )
        # The agent's reason, never a house string. See `next_question`.
        return QuestionOut(done=True, reason=str(result.get("reason", "")))

    stored.turns.append(
        await store.append_turn(
            db, session_id=stored.id, workspace_id=scope.workspace_id,
            role="agent", text=str(result["question"]),
            target_field=str(result["target"]),
            skill=str(result.get("skill", "")),
            skill_version=str(result.get("skill_version", "")),
        )
    )
    return QuestionOut(
        done=False,
        question=str(result["question"]),
        target=str(result["target"]),
        scope=int(result["scope"]),
        choices=list(result.get("choices", [])),
    )


async def _next_or_none(
    db: Any,
    scope: ScopedSession,
    stored: store.StoredSession,
    who: Mapping[str, str],
) -> QuestionOut | None:
    """`_ask_next`, but a failure returns None instead of unwinding the request.

    The answer that precedes it in this transaction is the thing being
    protected. Raising here would roll it back and ask the person to retype a
    sentence the server had already accepted and audited — a worse outcome than
    one extra request, which is what returning None costs.
    """
    try:
        return await _ask_next(db, scope, stored, who)
    except SkillFailedError as exc:
        log.warning("onboarding.next_question.deferred", error=str(exc))
        return None


@router.post("/discovery", response_model=AnswerOut, dependencies=[Depends(require_csrf)])
async def open_discovery(payload: DiscoveryIn, scope: CurrentScope) -> AnswerOut:
    """The one free-text turn — what they are responsible for, in their words."""
    _require_model()
    async with scoped_connection(scope) as db:
        stored = await _load(db, scope)
        who = await _who(db, scope)
        agent = OnboardingAgent(_context(scope, db, _user_context_of(who)))
        state = _rehydrate(stored)
        try:
            await agent.open_discovery(state, payload.answer)
        except SkillFailedError as exc:
            raise _unusable(exc) from exc
        # The opening question, written before the answer that replies to it.
        #
        # It used to be rendered on the client and never stored, which cost three
        # things at once. The transcript showed an answer with no question above
        # it. `_rehydrate` counts `asked` as agent turns carrying a target, so the
        # opener was uncounted — `MAX_QUESTIONS = 5` let six questions be asked,
        # and the rail read "Question 5 of 5" while the sixth was on screen. And
        # the one question every person is asked was the one question absent from
        # the record of what they were asked.
        #
        # Both turns land in the same transaction, so the agent turn is never
        # outstanding: `_outstanding_question` looks for a *later* turn with the
        # same target and finds the answer immediately below it.
        for role, text in (
            ("agent", resolve("persona.stated_purpose").fallback_question),
            ("user", payload.answer),
        ):
            stored.turns.append(
                await store.append_turn(
                    db, session_id=stored.id, workspace_id=scope.workspace_id,
                    role=role, text=text, target_field="persona.stated_purpose",
                    skill="user-discovery",
                )
            )
        # **The question first, then the state.** Keyword arguments are
        # evaluated in source order, and `_next_or_none` is what closes the
        # interview — it moves the phase to `documents` when the agent says
        # there is nothing left worth asking. Reading the state before it
        # therefore serialised the phase the session was in a moment ago, so a
        # response could carry `question.done: true` beside `phase: discovery`
        # and the screen would render a composer over a finished interview.
        question = await _next_or_none(db, scope, stored, who)
        return AnswerOut(
            state=await _state(db, scope, stored, who),
            question=question,
        )


@router.get("/next", response_model=QuestionOut)
async def next_question(scope: CurrentScope) -> QuestionOut:
    """The next question, chosen and worded by the model, bound to a declared field.

    Still here, and still its own endpoint, even though `/answer` now returns
    the question with the answer. Two callers need it: a resumed journey, which
    has a transcript and no outstanding question, and a `/answer` whose question
    generation failed after the answer was safely stored.
    """
    _require_model()
    async with scoped_connection(scope) as db:
        stored = await _load(db, scope)
        try:
            return await _ask_next(db, scope, stored, await _who(db, scope))
        except SkillFailedError as exc:
            raise _unusable(exc) from exc


@router.post("/answer", response_model=AnswerOut, dependencies=[Depends(require_csrf)])
async def submit_answer(payload: AnswerIn, scope: CurrentScope) -> AnswerOut:
    """Answer the outstanding question, and get the next one back with it.

    The body carries text and nothing else. The field it belongs to is the one
    the agent's own last turn declared — read server-side, never accepted from
    the client.

    **One request where there were two.** See `AnswerOut` for what the second
    one was spending, and why the question it returns is allowed to be null.
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
        who = await _who(db, scope)
        agent = OnboardingAgent(_context(scope, db, _user_context_of(who)))
        await agent.submit_answer(_rehydrate(stored), target=target, text=payload.text)
        stored.turns.append(
            await store.append_turn(
                db, session_id=stored.id, workspace_id=scope.workspace_id,
                role="user", text=payload.text, target_field=target,
            )
        )
        # Appended above *before* this runs, so the generator sees the answer in
        # `already_known` and does not re-ask the field just filled.
        # **The question first, then the state.** Keyword arguments are
        # evaluated in source order, and `_next_or_none` is what closes the
        # interview — it moves the phase to `documents` when the agent says
        # there is nothing left worth asking. Reading the state before it
        # therefore serialised the phase the session was in a moment ago, so a
        # response could carry `question.done: true` beside `phase: discovery`
        # and the screen would render a composer over a finished interview.
        question = await _next_or_none(db, scope, stored, who)
        return AnswerOut(
            state=await _state(db, scope, stored, who),
            question=question,
        )


# ── The two steps between the interview and the assembly ──────
#
# They exist because of *when* they are, not because of what they collect. The
# Persona and the Company Brain are assembled from whatever is in hand when
# `/finish` runs, and that assembly is the moment a draft becomes the artefact
# every later agent reads. Collect the price list afterwards and the Brain
# quoting from it has never seen it; the only repair is assembling a second
# time, paying for every model call again.
#
# So `/finish` refuses to start from either of them (see its own guard), and the
# phase column is what carries the ordering. Neither step *requires* anything —
# both are skippable, `doc/09` §6.2 — but leaving one is an explicit move rather
# than a silence the server has to interpret.


async def _uploaded(db: Any) -> int:
    """How many documents this workspace has. Scoped by the connection's GUC.

    No `workspace_id` parameter, deliberately: this runs inside
    `scoped_connection`, where row-level security already answers "whose
    documents" — and a count that took a workspace id would be a count that
    could be asked about somebody else's.
    """
    return int(
        (await db.execute(sa.text("SELECT COUNT(*) FROM document"))).scalar_one()
    )


@router.post("/documents", response_model=StateOut, dependencies=[Depends(require_csrf)])
async def documents_done(payload: DocumentsIn, scope: CurrentScope) -> StateOut:
    """Leave the documents step. Uploading happens at `POST /documents`.

    **This endpoint moves no files.** The upload path already exists, enforces
    the consent warranty, parses, chunks and classifies — this is only the
    person saying they are finished with that step, which is a different act and
    a different precondition. Folding the two together would mean the last
    upload of a batch also advanced the phase, and a founder who wanted to add a
    fourth file would find the step closed behind them.

    Skipping is permitted and is recorded. What it must not do is pretend: a
    workspace that skipped has no price list, so nothing downstream may imply it
    quoted from one.

    Idempotent past its own step. Called on a session already in `tools` it
    returns the state unchanged, because a double-click on Continue is not a
    reason to refuse anybody.
    """
    _require_model()
    async with scoped_connection(scope) as db:
        stored = await _load(db, scope)

        if stored.phase in (store.Phase.TOOLS.value, store.Phase.PERSONA.value,
                            store.Phase.ASSEMBLING.value, store.Phase.READY.value):
            return await _state(db, scope, stored)

        if stored.phase != store.Phase.DOCUMENTS.value:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "error": "not_at_documents",
                    "message": "The interview is not finished yet.",
                },
            )

        count = await _uploaded(db)
        await store.set_phase(db, session_id=stored.id, phase=store.Phase.TOOLS.value)
        # Both numbers, because the interesting case is the disagreement. A skip
        # with files already uploaded is somebody who added what they had and
        # moved on; a skip with none is the step failing to earn its place, and
        # only these two fields together can tell an operator which happened.
        log.info(
            "onboarding.documents_step_left",
            session_id=str(stored.id),
            uploaded=count,
            skipped=payload.skipped,
        )
        return await _state(db, scope, await _load(db, scope))


@router.get("/tools", response_model=ToolsOut)
async def tools(scope: CurrentScope) -> ToolsOut:
    """The tool catalogue, this company's departments first, and what it declared.

    Ordered rather than filtered — `connections.for_departments` explains why.
    Every tool is offered to every company: a company that runs no formal
    finance function may still run Stripe, and hiding it would be the product
    deciding it knows their stack better than they do.

    `connectable` is false for all nine today, and comes from the server so that
    the screen stops promising a later connect flow on the day one arrives.

    **No `_require_model()`, on purpose.** It is the one exception this router
    already makes, and for the same reason `read_state` makes it: this is a
    read of a fixed catalogue and a set of rows, and it works with no model
    configured. The two *writes* below it do require one — there is no point
    collecting a stack into a journey that cannot assemble.
    """
    async with scoped_connection(scope) as db:
        chosen = await selected_departments(db, workspace_id=scope.workspace_id)
        on_record = set(await connections.declared(db, workspace_id=scope.workspace_id))

    return ToolsOut(
        tools=[
            ToolOut(
                id=tool.id,
                name=tool.name,
                department=tool.department.value,
                department_label=label_for(tool.department),
                unlocks=tool.unlocks,
                kind=tool.kind,
                declared=tool.id in on_record,
                connectable=tool.id in connections.OAUTH_READY,
            )
            for tool in connections.for_departments(chosen)
        ],
        declared=sorted(on_record),
    )


@router.post("/tools", response_model=StateOut, dependencies=[Depends(require_csrf)])
async def declare_tools(payload: ToolsIn, scope: CurrentScope) -> StateOut:
    """Record which systems this company runs on. The last step before assembly.

    **The phase does not advance here.** It stays at `tools`, and `/finish` is
    what starts the assembly from it. That is not an omission: the assembly is
    several committed stages the client already drives in a loop, and giving
    this endpoint a phase to advance to would mean inventing one that says
    "tools are done but the persona has not started" — a state whose only
    purpose would be to be passed through. Staying put also makes a refresh
    land on this step with the boxes as they were left, which is the right
    place to land.

    Replaces rather than appends, so a person who returns and unticks something
    is believed. A `connected` row survives an untick — see `connections.declare`
    for why unticking a checkbox must not throw away live credentials.
    """
    _require_model()
    async with scoped_connection(scope) as db:
        stored = await _load(db, scope)

        if stored.phase != store.Phase.TOOLS.value:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "error": "not_at_tools",
                    "message": "The documents step comes first.",
                },
            )

        try:
            on_record = await connections.declare(
                db,
                workspace_id=scope.workspace_id,
                user_id=scope.user_id,
                providers=payload.providers,
            )
        except UnknownProviderError as exc:
            # 400 rather than 422: the body is well formed and the schema
            # accepted it. What is wrong is the value, checked against a
            # catalogue the client can read from `GET /tools` — the same shape
            # as `confirm_brief` refusing a field the catalogue does not
            # declare.
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        log.info(
            "onboarding.tools_declared",
            session_id=str(stored.id),
            declared=len(on_record),
            skipped=payload.skipped,
        )
        return await _state(db, scope, await _load(db, scope))


@router.post("/finish", response_model=StateOut, dependencies=[Depends(require_csrf)])
async def finish(scope: CurrentScope) -> StateOut:
    """Run **one** stage of the assembly and commit it. Call until `ready`.

    Three model calls used to happen inside this one request — persona, brain,
    context, at high, high and medium effort — and `scoped_connection` opens a
    single transaction around the whole handler, so all three stages committed
    together or not at all. Two to four minutes of work with nothing durable
    until the end: a failure at the third call discarded the first two, and the
    retry paid for them again. The client's 240s abort and a killed process
    both land there, and both did.

    So this now advances the phase by exactly one step and returns. Three
    requests, three transactions, three commits. A stage that fails leaves
    every stage before it on the row, and the next call resumes at the one that
    failed rather than at the beginning.

    **The client does not choose the stage.** It is read from the phase on the
    row, under a `FOR UPDATE` lock taken before the read — the same rule as
    `/answer`, where the target comes from the agent's own last turn. A client
    that could name the stage could skip one, and a Brain assembled with no
    persona is not a shorter journey but a different artefact. The lock is what
    makes a double-click harmless: the second request waits, then reads the
    phase the first one advanced and moves on to the next stage instead of
    repeating the last.

    Idempotent at the end: called on a session that is already `ready`, it
    returns the state and spends nothing.
    """
    _require_model()
    async with scoped_connection(scope) as db:
        stored = await _load(db, scope)

        # Locked before the phase is read, not after. `_load` above read a phase
        # that a concurrent request may already have advanced; acting on it
        # would run the same stage twice and pay for the model call twice.
        locked = (
            await db.execute(
                sa.text(
                    "SELECT phase, status FROM onboarding_session"
                    " WHERE id = :sid FOR UPDATE"
                ),
                {"sid": stored.id},
            )
        ).mappings().first()
        if locked is None:  # pragma: no cover - _load just returned this row
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="session vanished")

        phase = str(locked["phase"])
        if str(locked["status"]) == store.SessionStatus.COMPLETED.value or phase == "ready":
            done = await store.by_id(db, session_id=stored.id)
            assert done is not None
            return await _state(db, scope, done)

        # **The ordering, enforced where the client cannot reach it.** The two
        # collection steps sit between the interview and the assembly precisely
        # so that the Persona and the Brain are built with the documents and the
        # declared stack in hand. A client that could call this from `discovery`
        # would get a Brain assembled without them, and the only repair would be
        # to assemble a second time — every model call paid for twice to reach a
        # state that could have been reached once.
        #
        # Read from the locked row rather than from the request, the same as the
        # stage choice below. There is nothing in the body to trust.
        #
        # A journey already in flight when this shipped is sitting at
        # `discovery`, and this refuses it. It is not stuck: the client asks
        # `GET /next` on every resume into `discovery`, the interview reports
        # done, and that endpoint moves the phase to `documents`.
        if phase in (
            store.Phase.ANALYSING.value,
            store.Phase.BRIEF.value,
            store.Phase.DISCOVERY.value,
            store.Phase.DOCUMENTS.value,
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "error": "steps_outstanding",
                    "message": (
                        "Your documents and tools come before this. "
                        "Nothing is built until they do."
                    ),
                    "phase": phase,
                },
            )

        # The name the Brain is assembled under. `_rehydrate` defaults it to the
        # empty string and the old single-call path never passed it, so
        # `company-brain-builder` — which declares `company_name` in
        # `requires_grounding` — was being handed "" on every run.
        _, company_name = await _workspace_identity(db, scope)
        agent = OnboardingAgent(_context(scope, db, await _user_context(db, scope)))
        state = _rehydrate(stored, company_name)

        try:
            if phase == "persona":
                # One group per request. `next_brain_group` reads which are
                # already committed off the row, so this is also the resume
                # point: a run killed mid-Brain restarts at the group that did
                # not finish, not at the first one.
                group = next_brain_group(dict(stored.context))
                if group is None:  # pragma: no cover - the command advances the phase
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="the Brain is complete but the phase did not advance",
                    )
                await agent.build_brain(
                    state,
                    group=group,
                    so_far=dict(stored.context),
                    deep_research=await _deep_research(db, scope),
                )
            elif phase == "assembling":
                # Read back off the row rather than carried in memory — which is
                # exactly what lets this be its own request. `context` holds the
                # Brain at this point; stage three overwrites it with the
                # preamble, which is the artefact the journey exists to produce.
                assembled_brain = dict(stored.context)
                context = await agent.build_context(
                    state,
                    brain=assembled_brain,
                    persona=dict(stored.persona_draft),
                    role_reach={"role": str(scope.role)},
                )
                context = _with_tool_gaps(
                    dict(context),
                    await connections.declared(db, workspace_id=scope.workspace_id),
                )

                # **The only moment the assembled Brain still exists.** The
                # `store.complete` below replaces `context` with the preamble,
                # and until this call nothing in the agent path had ever written
                # `company_brain`, `fact` or `persona` — `INSERT INTO fact`
                # appeared nowhere in the repository. Two audits of *which*
                # questions to ask were landing in a column that this very
                # function then overwrote.
                #
                # Before `complete`, and in its transaction, so a workspace is
                # never marked finished with nothing behind it and never left
                # holding a promoted Brain against an unfinished session.
                promoted = await promote(
                    db,
                    workspace_id=scope.workspace_id,
                    user_id=scope.user_id,
                    session_id=stored.id,
                    brain=assembled_brain,
                    persona_draft=dict(stored.persona_draft),
                    answers=stored.answers,
                )
                await store.complete(
                    db,
                    session_id=stored.id,
                    context=_with_promoted_facts(dict(context), stored.answers),
                )
                log.info(
                    "onboarding.promotion.committed",
                    workspace_id=str(scope.workspace_id),
                    brain_version=promoted.brain_version,
                    facts=promoted.facts,
                    persona_fields=promoted.persona_fields,
                )
            else:
                await agent.build_persona(state)
        except SkillFailedError as exc:
            # Per-stage commits mean a failure here keeps every stage before it,
            # and clicking again resumes at the one that broke.
            raise _unusable(exc, keeps_progress=True) from exc

        # By id, not by `active`: the last stage marks the session `completed`,
        # and `_load` would report no journey in progress on the request that
        # finished it.
        latest = await store.by_id(db, session_id=stored.id)
        assert latest is not None
        return await _state(db, scope, latest)


def _with_tool_gaps(context: dict[str, Any], providers: Sequence[str]) -> dict[str, Any]:
    """Name every declared-but-unconnected tool in the gap list, with its unlock.

    This is what the tools step *does* to the artefact. The declarations
    themselves live in `workspace_connection`, which is where a connect flow
    will find them; what belongs in the preamble every later agent reads is the
    consequence — "I cannot see your traffic until Analytics is connected" —
    because an agent that does not know a source is missing answers as though it
    were merely empty.

    Added in code rather than asked of `context-personalization`, for the same
    reason `_with_promoted_facts` is: the unlock is an instruction a person will
    act on, and a model's paraphrase of "Connecting Google Analytics" is a
    different instruction wearing the same meaning.

    De-duplicated by topic, existing entries winning. The personalisation may
    already have said something more useful about the same gap, and this is
    adding what is missing rather than overwriting what is there.
    """
    gaps: list[dict[str, Any]] = []
    seen: set[str] = set()
    for entry in context.get("known_gaps", []):
        if not isinstance(entry, dict):
            continue
        topic = str(entry.get("topic"))
        if topic in seen:
            continue
        seen.add(topic)
        gaps.append(entry)

    for gap in connections.gaps_for(providers):
        if gap["topic"] in seen:
            continue
        seen.add(gap["topic"])
        gaps.append(dict(gap))

    return {**context, "known_gaps": gaps}


def _with_promoted_facts(
    context: dict[str, Any], answers: Mapping[str, str]
) -> dict[str, Any]:
    """Put the department thresholds into the preamble every later agent reads.

    **They were missing.** A completed journey's `context.facts` held the brain
    and persona keys and not one `fact.*` — so the three thresholds the
    interview worked hardest to get were in the `fact` table and absent from the
    context any downstream agent is handed before it answers anything. An agent
    reading the preamble rather than querying `fact` did not know the promised
    lead time.

    Added in code rather than asked of `context-personalization`, because a
    threshold must not be paraphrased. "Forty-eight hours from vessel discharge"
    is the answer; a model's rendering of it is a different fact wearing the
    same key.

    De-duplicated by key on the way through, which also fixes
    `persona.priority_topics` appearing twice in an audited preamble. Existing
    entries win: the personalisation may have said something more useful about a
    key than the raw answer, and this is adding what is missing rather than
    overwriting what is there.
    """
    # De-duplicated on the way *in*, not only on the way out. The duplicate an
    # audit found — `persona.priority_topics` twice — came from
    # `context-personalization` itself, so filtering only what this function
    # adds would leave the reported defect exactly where it was.
    facts: list[dict[str, Any]] = []
    seen: set[str] = set()
    for entry in context.get("facts", []):
        if not isinstance(entry, dict):
            continue
        key = str(entry.get("key"))
        if key in seen:
            continue
        seen.add(key)
        facts.append(entry)

    for key, value in answers.items():
        if not key.startswith("fact.") or key in seen:
            continue
        spec = FIELD_CATALOGUE.get(key)
        text = str(value or "").strip()
        if spec is None or not text:
            continue
        seen.add(key)
        facts.append({"key": key, "value": text, "scope": spec.scope})

    context["facts"] = facts
    return context


def _unusable(exc: SkillFailedError, *, keeps_progress: bool = False) -> HTTPException:
    """A skill ran and produced nothing usable.

    502 rather than 500: the provider answered, the answer was unusable. Never a
    plausible default — a fabricated brief is the thing this product exists not
    to produce, and it would be indistinguishable from a real one on screen.

    **`keeps_progress` exists because the old message was a lie.** Every caller
    said "Nothing was saved", which is true of `/read` and false of `/finish`:
    the assembly commits one stage per request precisely so a later failure
    keeps the earlier ones. Telling somebody nothing was saved when their
    persona and Brain are both on the row invites them to start over, and
    starting over is the one thing that would actually lose work.
    """
    log.warning("onboarding.skill_failed", error=str(exc), keeps_progress=keeps_progress)
    return HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail={
            "error": "skill_failed",
            "message": (
                "The assistant could not finish this step. Everything before it is "
                "saved — try again."
                if keeps_progress
                else "The assistant could not produce a usable answer. Nothing was saved."
            ),
            # The client renders a Retry rather than deciding for itself whether
            # this class of failure is worth another request.
            "retryable": True,
        },
    )
