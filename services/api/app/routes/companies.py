"""Company registration — the authenticated product's front door.

`doc/12` §Phase 5. Until now nothing here could create a workspace without a
verified domain, so a signed-up user had nowhere to go. D19 split that, and this
is the route that uses it: **register in one step, verify later.**

Two branches, and the second is the interesting one. If a *verified* workspace
already holds the domain, the honest answer is "that company is already here" —
offered as a **join request**, not a refusal and not a second workspace. Two
colleagues signing up separately is the ordinary case, and answering it with a
second company splits one business's data in half silently.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import text

from app.auth.companies import (
    CompanyDetails,
    DomainAlreadyRegisteredError,
    create_company,
    domain_of,
)
from app.auth.csrf import require_csrf
from app.auth.workspaces import find_verified_workspace_for_domain
from app.db import _unscoped_session
from app.deps import CurrentScope, CurrentSession, require_executive_surface
from app.domain.departments import label_for
from app.domain.invitations import may_administer
from app.domain.membership import UserAlreadyInAWorkspaceError
from app.domain.registration import JoinRequestState
from app.domain.scopes import Department, Role
from app.domain.session import ScopedSession
from app.logging import get_logger
from app.retrieval.scoped import apply_user_scope, scoped_connection

router = APIRouter(tags=["companies"])
log = get_logger(__name__)


class DepartmentChoiceOut(BaseModel):
    """One department a person may say they sit in."""

    value: str
    label: str
    """How to name it on screen. **Served rather than derived.**

    Finding F13 is the whole reason this endpoint exists instead of a list in
    the browser: the same department was `hr` in the API, "Hr" in an onboarding
    checkbox and "People" in the dashboard nav, because each surface
    title-cased the enum value itself. `DepartmentOut` in `spine.py` already
    says this — but that endpoint is workspace-scoped, and the company form asks
    the question *before* a workspace exists, so it cannot be the source here.
    """


@router.get("/departments", response_model=list[DepartmentChoiceOut])
async def list_departments() -> list[DepartmentChoiceOut]:
    """The department catalogue, for a form that has no workspace yet.

    Unauthenticated, and deliberately so. It is a fixed list of seven English
    nouns — the same seven the marketing site names — with no tenant data in it
    and nothing to leak. Requiring a scope would be worse than pointless:
    `/register-company` runs *between* signing up and having a workspace, which
    is precisely the window in which no scope exists.

    Includes `executive` ("Chief of Staff"). Selecting a workspace's departments
    excludes it because it is derived rather than chosen (see
    `domain/departments`), but a person can absolutely sit in the executive
    function and should be able to say so. This answers "where do you work",
    not "which dashboards exist".
    """
    return [
        DepartmentChoiceOut(value=d.value, label=label_for(d)) for d in Department
    ]

ExecutiveScope = Annotated[ScopedSession, Depends(require_executive_surface)]


class RegisterCompanyRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    # Mandatory (`doc/11` Q13). Not decoration: it is the first fact NEXUS holds
    # about the company and the input the research run is queued against.
    website_url: str = Field(min_length=3, max_length=2048)
    # `country`, `reporting_currency` and `headcount_band` were here and are
    # gone. Nothing read the columns they wrote — no SELECT in this codebase
    # names any of the three — and the currency is asked properly later, by the
    # question catalogue as a constrained choice that arrives with a scope.
    # Asking for a fact at the front door because there is a column for it is
    # backwards; the column exists to hold an answer something needs.
    #
    # `website_url` stays because it is genuinely read: `research/worker_loop`
    # selects it to queue the crawl.
    # What the founder says they do. Presentation only: these steer what the
    # agent asks and what the dashboard leads with, and reach nothing. The
    # authorising fields are `membership.role` and `membership.departments`,
    # and neither is settable from this request — the creator is `owner` by
    # construction and an invitee's role is set by whoever invited them.
    designation: str | None = Field(default=None, max_length=120)
    department: Department | None = None
    """A `Department` member, not free text.

    **An unrecognised value silently disabled the whole department scoping.**
    `askable_fields` treats anything it does not recognise as "no department
    said" and offers all 31 fields — deliberately, so a typo cannot empty the
    catalogue — which means a bad value here reproduces the exact round-1
    behaviour the narrowing was built to remove, with no error anywhere.

    An audit hit it by sending the *label* `"Operations"` where the key
    `operations` was wanted, and a Head of Operations was then led with Finance
    questions. `hr` / "Hr" / "People" is the same drift recorded as finding F13.
    The form sends the key today; this is what stops the next consumer, cached
    bundle or seeded row from reintroducing it.

    Pydantic rejects anything else with a 422 naming the field, which is the
    loud failure the silent one deserves.
    """
    # `doc/11` Q8's escape hatch. Two genuinely different businesses can share a
    # domain — an agency and its trading arm, a group with one website — so a
    # second registration is possible and must be **explicitly confirmed**.
    confirm_separate_company: bool = False


class CompanyOut(BaseModel):
    workspace_id: UUID
    domain: str
    domain_verified: bool = False


@router.post(
    "/companies", status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_csrf)]
)
async def register_company(payload: RegisterCompanyRequest, session: CurrentSession) -> CompanyOut:
    """Create the company, its workspace, its owner and its first research run.

    `CurrentSession`, not `CurrentScope` — the caller has no workspace yet, so
    `current_scope` would refuse them 403 before they could get one. The same
    position `invitations.accept` is in, and for the same reason.
    """
    async with _unscoped_session() as db:
        try:
            created = await create_company(
                db,
                user_id=session.user_id,
                details=CompanyDetails(
                    name=payload.name.strip(),
                    website_url=payload.website_url,
                    designation=payload.designation,
                    # `.value`, so the column keeps the key the catalogue
                    # matches on rather than `Department.HR`'s repr.
                    department=payload.department.value if payload.department else None,
                ),
                allow_duplicate=payload.confirm_separate_company,
            )
        except UserAlreadyInAWorkspaceError as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
        except DomainAlreadyRegisteredError as exc:
            # 409 with somewhere to go, rather than a bare refusal that leaves
            # the user retyping the domain that is exactly right.
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                {
                    "detail": str(exc),
                    "workspace_id": str(exc.workspace_id),
                    "join_request_path": "/join-requests",
                },
            ) from exc

        # Land them in the company they just made. The session row is the only
        # place the active workspace lives (doc 06 §2.1).
        await db.execute(
            text("UPDATE user_session SET active_workspace_id = :w WHERE id = :s"),
            {"w": str(created.workspace_id), "s": str(session.session_id)},
        )
        await db.commit()

    return CompanyOut(workspace_id=created.workspace_id, domain=created.domain)


class CurrentCompanyOut(BaseModel):
    """This caller's company, as a settings screen needs it."""

    workspace_id: UUID
    name: str
    domain: str
    website_url: str | None
    domain_verified: bool
    role: str
    may_administer: bool
    """Whether this caller may verify the domain and invite people. Served
    rather than inferred from the role string, so one rule decides it and the
    UI cannot drift from what the write endpoints will actually allow."""


@router.get("/companies/current", response_model=CurrentCompanyOut)
async def current_company(scope: CurrentScope) -> CurrentCompanyOut:
    """The company the caller is in.

    Finding F3 is why this exists. Three screens told the user to go to
    Settings, and the invitation refusal told them Settings has the DNS record
    to add — but there was no Settings page, in part because nothing served the
    two facts one would need: which domain this company claims, and whether it
    is proved. Both were reachable only as a side effect of registering.
    """
    async with scoped_connection(scope) as session:
        row = (
            await session.execute(
                text(
                    "SELECT name, domain, website_url, domain_verified_at"
                    "  FROM workspace WHERE id = :w"
                ),
                {"w": str(scope.workspace_id)},
            )
        ).first()

    if row is None:
        # The isolation policy filtered it, which means it is not this caller's
        # workspace. Same answer as one that does not exist.
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")

    return CurrentCompanyOut(
        workspace_id=scope.workspace_id,
        name=row.name,
        domain=row.domain,
        website_url=row.website_url,
        domain_verified=row.domain_verified_at is not None,
        role=scope.role.value,
        may_administer=may_administer(scope.role),
    )


# ── Join requests (`doc/11` Q8) ───────────────────────────────


class JoinRequestIn(BaseModel):
    website_url: str = Field(min_length=3, max_length=2048)
    message: str | None = Field(default=None, max_length=500)


class JoinRequestOut(BaseModel):
    id: UUID
    state: str


@router.post(
    "/join-requests",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_csrf)],
)
async def request_to_join(payload: JoinRequestIn, session: CurrentSession) -> JoinRequestOut:
    """Ask the company that already holds this domain to let you in.

    The workspace is resolved from the **domain**, never taken from the request
    body. A workspace id in a body is a thing a caller can guess, and a join
    request naming an arbitrary one would be a way to enumerate them: every id
    either produces a request or does not.
    """
    domain = domain_of(payload.website_url)
    workspace_id = await find_verified_workspace_for_domain(domain)
    if workspace_id is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "No company on NEXUS OS has verified that domain."
        )

    async with _unscoped_session() as db:
        # The policy from migration 0014 permits an insert where `user_id` is
        # the caller — which is why this sets the user GUC and not the workspace
        # one. The requester is by definition not a member of the target.
        await apply_user_scope(db, session.user_id)
        row = (
            await db.execute(
                text(
                    "INSERT INTO join_request (workspace_id, user_id, message)"
                    " VALUES (:w, :u, :m)"
                    " ON CONFLICT (workspace_id, user_id) WHERE state = 'pending'"
                    " DO UPDATE SET message = EXCLUDED.message"
                    " RETURNING id, state"
                ),
                {"w": str(workspace_id), "u": str(session.user_id), "m": payload.message},
            )
        ).one()
        await db.commit()

    log.info("join_request.created")
    return JoinRequestOut(id=UUID(str(row.id)), state=row.state)


class PendingJoinRequest(BaseModel):
    id: UUID
    user_id: UUID
    message: str | None


@router.get("/join-requests", response_model=list[PendingJoinRequest])
async def list_join_requests(scope: ExecutiveScope) -> list[PendingJoinRequest]:
    """The approval surface. Owner and Executive only.

    Deciding who joins a company is the same authority as inviting them, so it
    reuses the dependency that already encodes that pair rather than growing a
    second opinion about roles.
    """
    async with scoped_connection(scope) as db:
        rows = (
            await db.execute(
                text(
                    "SELECT id, user_id, message FROM join_request"
                    " WHERE state = 'pending' ORDER BY created_at"
                )
            )
        ).all()

    return [
        PendingJoinRequest(id=UUID(str(r.id)), user_id=UUID(str(r.user_id)), message=r.message)
        for r in rows
    ]


class DecisionIn(BaseModel):
    approve: bool


@router.post(
    "/join-requests/{request_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_csrf)],
)
async def decide_join_request(
    request_id: UUID, decision: DecisionIn, scope: ExecutiveScope
) -> None:
    """Approve or decline. Approving creates the membership.

    The role is **not** taken from the request. An approver decides that someone
    may join; what they may then do is the role model's business, and the safe
    default for a person nobody has described yet is the narrowest one. Doc 06
    §2.2 makes changing it a separate, deliberate act.
    """
    async with scoped_connection(scope) as db:
        row = (
            await db.execute(
                text(
                    "UPDATE join_request"
                    "   SET state = :state, decided_by_user_id = :by, decided_at = now()"
                    " WHERE id = :i AND state = 'pending'"
                    " RETURNING user_id"
                ),
                {
                    "state": (
                        JoinRequestState.APPROVED if decision.approve else JoinRequestState.DECLINED
                    ).value,
                    "by": str(scope.user_id),
                    "i": str(request_id),
                },
            )
        ).first()

        if row is None:
            # Absent, already decided, or another workspace's (RLS hid it). All
            # three are 404: telling them apart confirms a request exists.
            raise HTTPException(status.HTTP_404_NOT_FOUND, "No such pending request.")

        if decision.approve:
            await db.execute(
                text(
                    "INSERT INTO membership (workspace_id, user_id, role)"
                    " VALUES (:w, :u, :r)"
                    " ON CONFLICT ON CONSTRAINT uq_membership_workspace_user DO NOTHING"
                ),
                {
                    "w": str(scope.workspace_id),
                    "u": str(row.user_id),
                    "r": Role.CONTRIBUTOR.value,
                },
            )

    log.info("join_request.decided", approved=decision.approve)
