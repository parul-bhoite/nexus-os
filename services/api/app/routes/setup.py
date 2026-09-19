"""Workspace setup: the onboarding answers, and the people invited to help.

Distinct from `routes/onboarding.py`, which is everything that happens *before*
a workspace exists — verify an email, prove a domain, create the workspace. From
here on there is a workspace, so every route in this module takes a
`ScopedSession` and every read goes through `scoped_connection`. The one
exception is invitation acceptance, and it is exactly the case that proves the
rule: the person accepting is not yet a member, so no scope can honestly be
built for them.

Two properties are worth reading the code for, because both are the kind that
quietly stop being true:

**Scope is taken from the catalogue, never from the request.** `AnswerIn` has a
`key` and a `value` and no third field. There is no scope to spoof, because the
classification is looked up in `scope_for_answer` — which raises on an unknown
key rather than defaulting (doc 06 §2.5, I4). A request cannot store its average
deal size as L1 by asking nicely.

**Answering is not authorising.** The `role` and `department` questions write
rows in `onboarding_answer`. Nothing here touches `membership`, which is the
only table `build_scope` reads. Doc 06 §2.2 calls a self-declared role privilege
escalation via dropdown; the reason it cannot happen is not that this module is
careful, but that the write it would need is not in this file at all.
"""

from __future__ import annotations

import json
import re
from typing import Annotated, Any
from urllib.parse import urlparse
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import invitations as invites
from app.auth.csrf import require_csrf
from app.auth.invitations_email import build_invitation_email
from app.auth.workspaces import UnverifiedWorkspaceError
from app.config import Settings, get_settings
from app.db import _unscoped_session
from app.deps import CurrentScope, CurrentSession
from app.domain import audit
from app.domain.access import AccessDecision, Aggregate, decide_l3_access
from app.domain.invitations import InvitationError, check_invitation, may_administer
from app.domain.membership import UserAlreadyInAWorkspaceError
from app.domain.onboarding import (
    BY_KEY,
    CATALOGUE,
    AnswerType,
    Choice,
    Question,
    scope_for_answer,
)
from app.domain.scopes import Department, Role, Scope, scope_code, scope_from_code
from app.domain.session import ScopedSession
from app.logging import get_logger
from app.mail import build_mailer, send_safely
from app.retrieval.scoped import scoped_connection

router = APIRouter(tags=["setup"])
log = get_logger(__name__)

MAX_TEXT = 300
MAX_LONG_TEXT = 4000
MAX_URL = 2048
MAX_LIST_ITEMS = 25
MAX_ITEM_LENGTH = 120


# ── Reading and writing one answer's authority ────────────────


def may_read_answer(caller: ScopedSession, scope: Scope, department: Department | None) -> bool:
    """Whether this caller may see an answer stored at this classification.

    An L3 answer is a department-wide fact — the department's average deal size,
    not one person's — so it is decided as an aggregate. That is what withholds
    it from a Contributor, per ADR 0005, and it is the same call the dashboards
    will make about the same number when they compute with it.
    """
    if scope is Scope.L3_DEPARTMENT:
        if department is None:
            # Unclassifiable: a CHECK constraint forbids storing this, so
            # reaching it means the row predates the constraint or arrived some
            # other way. Withhold rather than guess (I4).
            return False
        aggregate = Aggregate("onboarding_answer", department)
        return decide_l3_access(caller, aggregate=aggregate) is AccessDecision.ALLOW
    return caller.may_reach_scope(scope)


def ensure_may_answer(caller: ScopedSession, question: Question) -> None:
    """Refuse an answer this caller has no business setting.

    Two layers, and the second is not currently reachable past the first.

    The first is `may_administer`: the catalogue is a *company* setup flow run
    once by the founder, so writing to it is workspace administration. No source
    document says who may run it — D16 — so this is the default-deny reading.

    The second is the per-answer check. It is redundant while only Owner and
    Executive get past the first, and it is written and tested anyway: if D16
    later admits Department Managers, this is what stops one from writing an
    L3 Finance fact from a Sales seat. D15's second open question is precisely
    that failure, and a check added at the same time as the feature that needs
    it is a check nobody remembers to add.
    """
    if not may_administer(caller.role):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Workspace setup is available to owners and executives.",
        )

    if not may_read_answer(caller, question.scope, question.department):
        # 404 rather than 403: for an L3 department the caller cannot reach,
        # confirming the question exists confirms the department does.
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")


# ── Value validation ──────────────────────────────────────────


def _text(value: Any, *, limit: int, label: str) -> str:
    if not isinstance(value, str):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"{label} must be text.")
    cleaned = value.strip()
    if not cleaned:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"{label} cannot be empty.")
    if len(cleaned) > limit:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, f"{label} is longer than {limit} characters."
        )
    return cleaned


def _string_list(value: Any, *, options: tuple[Choice, ...], label: str) -> list[str]:
    if not isinstance(value, list):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"{label} must be a list.")
    if len(value) > MAX_LIST_ITEMS:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, f"{label} takes at most {MAX_LIST_ITEMS} entries."
        )

    permitted = {c.value for c in options}
    cleaned: list[str] = []
    for item in value:
        entry = _text(item, limit=MAX_ITEM_LENGTH, label=label)
        if permitted and entry not in permitted:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"{entry!r} is not an option.")
        if entry not in cleaned:  # order-preserving dedupe; RANKED depends on order
            cleaned.append(entry)
    return cleaned


NOT_A_WEB_ADDRESS = "That does not look like a web address."

HOSTNAME = re.compile(
    r"^(?=.{1,253}$)"
    r"(?!-)[a-z0-9-]{1,63}(?<!-)"
    r"(\.(?!-)[a-z0-9-]{1,63}(?<!-))+$"
)
"""A dotted host, and nothing else.

Written out rather than leaning on `urlparse` alone, which is permissive by
design: it happily reports a hostname for `not a url` and for
`javascript:alert(1)`, both of which reached the database before this existed.
A single missing dot is the difference between a company's site and a scheme
somebody typed to see what would happen.
"""


def _web_address(raw: str) -> str:
    """A stored company URL, or a 400.

    A bare host is accepted and given `https://`, because that is how people
    type their own address. Anything with a scheme must carry one we would
    actually fetch — this value feeds the crawler, so `file:` and `javascript:`
    are not merely untidy.
    """
    if "://" in raw:
        scheme = raw.split("://", 1)[0].lower()
        if scheme not in ("http", "https"):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, NOT_A_WEB_ADDRESS)
        candidate = raw
    elif ":" in raw.split("/", 1)[0]:
        # `javascript:alert(1)` has a scheme and no `//`. Prefixing `https://`
        # would turn it into a host called `javascript` with a port that is not
        # a number, which is a strange thing to have stored.
        raise HTTPException(status.HTTP_400_BAD_REQUEST, NOT_A_WEB_ADDRESS)
    else:
        candidate = f"https://{raw}"

    parsed = urlparse(candidate)
    try:
        _ = parsed.port  # raises when the port is not a number
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, NOT_A_WEB_ADDRESS) from exc

    host = (parsed.hostname or "").lower()
    if not HOSTNAME.match(host):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, NOT_A_WEB_ADDRESS)

    return parsed.geturl()


def validate_answer(question: Question, value: Any, *, member_ids: frozenset[UUID]) -> Any:
    """The stored form of an answer, or a 400.

    Returns the value to write rather than mutating anything, so the caller can
    validate a whole submission before writing any of it.
    """
    label = question.prompt

    match question.answer_type:
        case AnswerType.TEXT:
            return _text(value, limit=MAX_TEXT, label=label)

        case AnswerType.LONG_TEXT:
            return _text(value, limit=MAX_LONG_TEXT, label=label)

        case AnswerType.URL:
            return _web_address(_text(value, limit=MAX_URL, label=label))

        case AnswerType.MONEY:
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise HTTPException(status.HTTP_400_BAD_REQUEST, f"{label} must be a number.")
            if value != value or value in (float("inf"), float("-inf")):  # NaN, ±inf
                raise HTTPException(status.HTTP_400_BAD_REQUEST, f"{label} must be a number.")
            if value < 0:
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST, f"{label} cannot be a negative number."
                )
            return float(value)

        case AnswerType.SINGLE_CHOICE:
            chosen = _text(value, limit=MAX_ITEM_LENGTH, label=label)
            if chosen not in {c.value for c in question.options}:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, f"{chosen!r} is not an option.")
            return chosen

        case AnswerType.MULTI_CHOICE | AnswerType.RANKED:
            return _string_list(value, options=question.options, label=label)

        case AnswerType.USER_LIST:
            recipients: list[str] = []
            for entry in _string_list(value, options=(), label=label):
                try:
                    user_id = UUID(entry)
                except ValueError as exc:
                    raise HTTPException(
                        status.HTTP_400_BAD_REQUEST, "Choose people from your workspace."
                    ) from exc
                if user_id not in member_ids:
                    # Doc 06 §4.10 — the brief goes to workspace users, never to
                    # a free-text address. The route is where that stops being a
                    # sentence in a document.
                    raise HTTPException(
                        status.HTTP_400_BAD_REQUEST,
                        "Everyone on this list has to be in your workspace already.",
                    )
                recipients.append(str(user_id))
            return recipients


# ── Wire models ───────────────────────────────────────────────


class ChoiceOut(BaseModel):
    value: str
    label: str


class QuestionOut(BaseModel):
    key: str
    prompt: str
    stage: str
    answer_type: str
    scope: str
    department: str | None
    required: bool
    why: str
    options: list[ChoiceOut]
    free_entry: bool
    writable: bool
    """Whether this caller may set it. False renders read-only, not hidden —
    a question the caller can see the answer to but not change is a real state."""
    value: Any = None
    """The stored answer, when this caller may read it. `None` otherwise, with
    no indication of which of the two it was."""


class MemberOut(BaseModel):
    user_id: UUID
    email: str
    display_name: str | None
    role: str


class QuestionsOut(BaseModel):
    questions: list[QuestionOut]
    can_administer: bool
    members: list[MemberOut]
    """Empty unless the caller administers the workspace. The brief-recipient
    question is chosen from this list and from nowhere else."""


class AnswerIn(BaseModel):
    key: str = Field(min_length=1, max_length=100)
    value: Any
    # No scope field, and there never may be one. See the module docstring.


class AnswersIn(BaseModel):
    answers: list[AnswerIn] = Field(min_length=1, max_length=len(CATALOGUE))


class SavedOut(BaseModel):
    saved: list[str]


# ── Members ───────────────────────────────────────────────────


async def _members(session: AsyncSession) -> list[MemberOut]:
    """The workspace's people.

    Filtered to the workspace by the isolation policy on `membership`, not by
    this query. `app_user` is global and carries no policy of its own, so the
    join is the reason a caller sees only their colleagues' rows.
    """
    rows = (
        (
            await session.execute(
                text(
                    "SELECT m.user_id, u.email, u.display_name, m.role"
                    "  FROM membership m JOIN app_user u ON u.id = m.user_id"
                    " WHERE m.revoked_at IS NULL"
                    " ORDER BY lower(u.email)"
                )
            )
        )
        .mappings()
        .all()
    )
    return [
        MemberOut(
            user_id=UUID(str(r["user_id"])),
            email=r["email"],
            display_name=r["display_name"],
            role=r["role"],
        )
        for r in rows
    ]


async def store_answer(
    session: AsyncSession,
    *,
    caller: ScopedSession,
    question: Question,
    value: Any,
    is_assumption: bool = False,
    answer_state: str = "bound",
) -> None:
    """Write one answer, classified from the catalogue.

    The scope and department are looked up here, from `scope_for_answer`, and
    the caller passes neither. That is doc 06 §2.5's *"tag them at capture"* in
    one function: there is no argument to get wrong and no request field to
    trust, and a question the catalogue does not know raises rather than
    defaulting to a scope somebody guessed.

    An upsert, because onboarding is revisitable — a person correcting their
    currency in week three is the ordinary case, not a conflict. The
    classification is re-applied on update as well as insert: a question that is
    reclassified upward must not leave old rows sitting at the weaker scope
    forever because they happened to be answered first.
    """
    answer_scope, department = scope_for_answer(question.key)

    await session.execute(
        text(
            "INSERT INTO onboarding_answer"
            " (workspace_id, answered_by_user_id, question_key, value, scope,"
            "  department, is_assumption, answer_state)"
            " VALUES (:ws, :u, :k, CAST(:v AS jsonb), :s, :d, :assumed, :state)"
            " ON CONFLICT (workspace_id, question_key) DO UPDATE"
            "    SET value = EXCLUDED.value,"
            "        scope = EXCLUDED.scope,"
            "        department = EXCLUDED.department,"
            "        answered_by_user_id = EXCLUDED.answered_by_user_id,"
            # Carried on the upsert, so answering properly later clears the
            # flag. An assumption that outlives the answer correcting it would
            # keep the Brain hedging about a fact it now knows.
            "        is_assumption = EXCLUDED.is_assumption,"
            # A Manager confirming a Contributor's proposal overwrites the row
            # and its state together. Leaving the state behind would keep a
            # confirmed fact invisible to every reader using BINDING_ONLY_SQL.
            "        answer_state = EXCLUDED.answer_state,"
            "        updated_at = now()"
        ),
        {
            "ws": str(caller.workspace_id),
            "u": str(caller.user_id),
            "k": question.key,
            "v": json.dumps(value),
            "assumed": is_assumption,
            "state": answer_state,
            "s": scope_code(answer_scope),
            "d": department.value if department else None,
        },
    )


# ── The catalogue, with this caller's answers ─────────────────


@router.get("/onboarding/questions", response_model=QuestionsOut)
async def questions(scope: CurrentScope) -> QuestionsOut:
    """Every question, plus whatever of it this caller may see.

    One request drives the whole wizard. The stages are returned together and
    ordered by the client, because the sequencing doc 04 §5 asks for — audit
    first, money questions after — is a matter of when a screen is *shown*.
    The one ordering rule that is not cosmetic, that brief recipients must be
    existing workspace users (doc 06 §4.10), is enforced on the write instead,
    where a client cannot route around it.
    """
    administers = may_administer(scope.role)

    async with scoped_connection(scope) as session:
        stored = (
            (
                await session.execute(
                    text("SELECT question_key, value, scope, department FROM onboarding_answer")
                )
            )
            .mappings()
            .all()
        )
        # Only administrators choose brief recipients, so only they need the
        # roster. Returning it to everyone would make this endpoint a company
        # directory that nothing asked for.
        members = await _members(session) if administers else []

    answers: dict[str, Any] = {}
    for row in stored:
        question = BY_KEY.get(row["question_key"])
        if question is None:
            continue  # a key retired from the catalogue; nothing can render it
        # The stored classification decides, not the catalogue's current one. If
        # a question is reclassified later, rows written under the old scope keep
        # it until something migrates them — reading them at the new, possibly
        # weaker, scope would disclose them retroactively.
        stored_scope = scope_from_code(row["scope"])
        stored_department = Department(row["department"]) if row["department"] else None
        if may_read_answer(scope, stored_scope, stored_department):
            answers[row["question_key"]] = row["value"]

    return QuestionsOut(
        can_administer=administers,
        members=members,
        questions=[
            QuestionOut(
                key=q.key,
                prompt=q.prompt,
                stage=q.stage.value,
                answer_type=q.answer_type.value,
                scope=scope_code(q.scope),
                department=q.department.value if q.department else None,
                required=q.required,
                why=q.why,
                options=[ChoiceOut(value=c.value, label=c.label) for c in q.options],
                free_entry=q.free_entry,
                writable=administers and may_read_answer(scope, q.scope, q.department),
                value=answers.get(q.key),
            )
            for q in CATALOGUE
        ],
    )


@router.post(
    "/onboarding/answers",
    response_model=SavedOut,
    dependencies=[Depends(require_csrf)],
)
async def save_answers(payload: AnswersIn, scope: CurrentScope) -> SavedOut:
    """Store a wizard step's answers, each tagged with its own classification.

    Validated in full before anything is written. A step that half-saved would
    leave the user looking at a form that disagrees with the database about what
    they just told it.
    """
    questions_to_write: list[tuple[Question, Any]] = []

    async with scoped_connection(scope) as session:
        member_ids = frozenset(m.user_id for m in await _members(session))

        for answer in payload.answers:
            question = BY_KEY.get(answer.key)
            if question is None:
                # `scope_for_answer` would raise; this is the same refusal with
                # a status code. Never store an answer at a guessed scope.
                raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Unknown question: {answer.key}")
            ensure_may_answer(scope, question)
            questions_to_write.append(
                (question, validate_answer(question, answer.value, member_ids=member_ids))
            )

        for question, value in questions_to_write:
            await store_answer(session, caller=scope, question=question, value=value)

        # One row for the step, not one per answer. A wizard step is what a
        # person did; six rows for six fields would bury the trail in a way that
        # makes the interesting entries harder to find, which is the failure
        # mode of a log nobody reads.
        if questions_to_write:
            await audit.record(
                session,
                workspace_id=scope.workspace_id,
                action=audit.AuditAction.ANSWER_WRITTEN,
                actor_user_id=scope.user_id,
                target_type="onboarding_answer",
                target_id=",".join(q.key for q, _ in questions_to_write),
            )

    log.info("onboarding.answers.saved", count=len(questions_to_write))
    return SavedOut(saved=[q.key for q, _ in questions_to_write])


# ── Invitations ───────────────────────────────────────────────


class InviteIn(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    role: Role
    departments: list[Department] = Field(default_factory=list, max_length=len(Department))


class InvitationOut(BaseModel):
    invitation_id: UUID
    email: str
    role: str
    departments: list[str]
    state: str
    expires_at: str


class IssuedOut(InvitationOut):
    accept_path: str
    """Where to send the invited person.

    **The invitation is emailed too.** This comment used to say delivery was
    "not wired up anywhere in the product" — true when written, stale since P3
    built the mailer. A product whose answer to "add someone to your company" is
    "copy this string and send it yourself" has made the customer the transport.

    Still returned, because an owner who wants to paste it into a chat should be
    able to. Handing the link back is not a weakening: the
    inviter is the person who chose the role, and the link alone grants nothing,
    since acceptance requires being signed in as the address it names.
    """


class InvitationsOut(BaseModel):
    invitations: list[InvitationOut]


def _out(invitation: invites.Invitation) -> InvitationOut:
    return InvitationOut(
        invitation_id=invitation.id,
        email=invitation.email,
        role=invitation.role.value,
        departments=sorted(d.value for d in invitation.departments),
        state=invitation.state,
        expires_at=invitation.expires_at.isoformat(),
    )


INVITATION_SENDER_SQL = text(
    "SELECT w.name AS company,"
    "       (SELECT display_name FROM app_user WHERE id = :u) AS inviter"
    "  FROM workspace w WHERE w.id = :w"
)
"""Who the invitation is from, and which company it is for, in one round trip.

**A scalar subquery rather than a join, deliberately.** Joining `app_user` means
a missing or invisible user row drops the whole result, taking the company name
with it — and the company name is what stops the email reading as phishing. The
subquery yields `NULL` for an unknown inviter and leaves the company intact,
which is the difference between a degraded email and no email at all.

Named rather than inline so `tests/test_invitation_email.py` can drive this
exact statement instead of a second copy of it that could drift.
"""


@router.post(
    "/invitations",
    response_model=IssuedOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_csrf)],
)
async def create_invitation(
    payload: InviteIn,
    scope: CurrentScope,
    background: BackgroundTasks,
    settings: Annotated[Settings, Depends(get_settings)],
) -> IssuedOut:
    """Invite someone, at a role this caller is allowed to grant.

    Every precondition is in `check_invitation` rather than here, so there is
    one function to audit rather than one per route — the same arrangement as
    `create_workspace_for_claim`.
    """
    try:
        departments = check_invitation(scope, role=payload.role, departments=payload.departments)
    except InvitationError as exc:
        # "Not found" is the department-unreachable case, which must not confirm
        # that the department exists.
        if str(exc) == "Not found":
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found") from exc
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc)) from exc

    email = payload.email.strip().lower()
    if "@" not in email or email.startswith("@") or email.endswith("@"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "That is not an email address.")

    async with scoped_connection(scope) as session:
        try:
            issued = await invites.issue(
                session,
                workspace_id=scope.workspace_id,
                invited_by_user_id=scope.user_id,
                email=email,
                role=payload.role,
                departments=departments,
            )
        except UnverifiedWorkspaceError as exc:
            # D19's gate, translated. `issue` raises this correctly and nothing
            # caught it, so a deliberate refusal reached the user as a **500**.
            # Found by walking the flow, not by the suite — the test called
            # `require_verified_domain` directly rather than through this route.
            # Same shape as findings #9 and #10: right behaviour, wrong status
            # code, and only the status code is visible to a person.
            raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc)) from exc

    # Sent, not merely handed back. Queued so the response does not wait on the
    # transport — and after the commit, so an invitation that failed to store is
    # never one somebody received a link for.
    async with scoped_connection(scope) as session:
        # One round trip, not two. The inviter's name rides along as a scalar
        # subquery rather than a join so that a missing `app_user` row yields a
        # NULL name instead of dropping the whole row and taking the company
        # name with it — the silent-zero-rows shape this codebase has been bitten
        # by three times. `app_user` carries no RLS, so this reads cleanly.
        row = (
            await session.execute(
                INVITATION_SENDER_SQL,
                {"w": str(scope.workspace_id), "u": str(scope.user_id)},
            )
        ).first()
    background.add_task(
        send_safely,
        build_mailer(settings),
        build_invitation_email(
            to=email,
            token=issued.token,
            base_url=settings.public_base_url,
            company=row.company if row else "your company",
            # Optional by design: `display_name` is nullable, and the email
            # falls back to "You have been invited" rather than naming a blank.
            inviter=row.inviter if row else None,
        ),
    )
    log.info("invitation.queued", role=payload.role)

    # The link still comes back to the inviter. An owner who wants to paste it
    # into a chat should be able to; the email is the default, not the only way.
    return IssuedOut(
        **_out(issued.invitation).model_dump(),
        accept_path=f"/invitations/accept?token={issued.token}",
    )


@router.get("/invitations", response_model=InvitationsOut)
async def list_invitations(scope: CurrentScope) -> InvitationsOut:
    """Who has been invited, and what became of it.

    Administrators only. An invitation names a person and the role someone chose
    for them, which is not a fact the rest of the workspace is owed.
    """
    if not may_administer(scope.role):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")

    async with scoped_connection(scope) as session:
        found = await invites.list_for_workspace(session)

    return InvitationsOut(invitations=[_out(i) for i in found])


@router.post(
    "/invitations/{invitation_id}/revoke",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_csrf)],
)
async def revoke_invitation(invitation_id: UUID, scope: CurrentScope) -> Response:
    if not may_administer(scope.role):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")

    async with scoped_connection(scope) as session:
        changed = await invites.revoke(session, invitation_id=invitation_id)

    if not changed:
        # Either it is not in this workspace, or it is already accepted or
        # revoked. One answer for all three: the first is an isolation boundary
        # and the other two are simply nothing to do.
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")

    return Response(status_code=status.HTTP_204_NO_CONTENT)


class AcceptIn(BaseModel):
    token: str = Field(min_length=16, max_length=512)
    # No role. No department. No workspace. Doc 06 §2.2 — acceptance copies what
    # the inviter set, and a field here is the escalation it warns about.


class AcceptOut(BaseModel):
    outcome: str
    workspace_id: UUID | None
    workspace_name: str | None
    role: str | None


@router.post(
    "/invitations/accept",
    response_model=AcceptOut,
    dependencies=[Depends(require_csrf)],
)
async def accept_invitation(payload: AcceptIn, session: CurrentSession) -> AcceptOut:
    """Join a workspace.

    Depends on `current_session`, not `current_scope`, and that is the whole
    shape of the problem: the caller has no workspace yet, so `current_scope`
    would refuse them 403 before they could get one. `current_session` grants
    authority over nothing but their own identity, and no `ScopedSession` can be
    built from it — so this route structurally cannot read workspace data,
    which is exactly the guarantee wanted for a route that takes a token from a
    stranger.
    """
    async with _unscoped_session() as db:
        try:
            result = await invites.accept(db, token=payload.token, user_id=session.user_id)
        except UserAlreadyInAWorkspaceError as exc:
            # `doc/11` §3.2. Raised only after the invitation has been shown to
            # name this account, so it discloses nothing to somebody holding a
            # forwarded link.
            raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc

        if result.outcome is invites.AcceptOutcome.ACCEPTED and result.workspace_id:
            # Land them in the workspace they just joined. The session row is the
            # only place the active workspace lives (doc 06 §2.1).
            await db.execute(
                text("UPDATE user_session SET active_workspace_id = :ws WHERE id = :sid"),
                {"ws": str(result.workspace_id), "sid": str(session.session_id)},
            )

        await db.commit()

    if result.outcome is invites.AcceptOutcome.UNUSABLE:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "That invitation link is no longer valid. Ask for a new one.",
        )
    if result.outcome is invites.AcceptOutcome.WRONG_ACCOUNT:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "This invitation was sent to a different email address. "
            "Sign in with that address to accept it.",
        )

    return AcceptOut(
        outcome=result.outcome.value,
        workspace_id=result.workspace_id,
        workspace_name=result.workspace_name,
        role=result.role.value if result.role else None,
    )
