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

from typing import Annotated, Any
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
from app.domain.audit import AuditAction, record
from app.domain.departments import label_for, select_departments, selected_departments
from app.domain.invitations import may_administer
from app.domain.membership import UserAlreadyInAWorkspaceError
from app.domain.question_bank import BY_DEPARTMENT as QUESTIONS_BY_DEPARTMENT
from app.domain.registration import JoinRequestState
from app.domain.registry import CapabilityKind, capabilities_for
from app.domain.reporting import (
    MAX_DECIMALS,
    SETTINGS,
    ReportingSettings,
    Scale,
    WeekStart,
    moves,
    restates_numbers,
)
from app.domain.scopes import Department, Role
from app.domain.session import ScopedSession
from app.logging import get_logger
from app.retrieval.scoped import apply_user_scope, scoped_connection
from app.routes.dashboards import AnsweredQuestions

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
    return [DepartmentChoiceOut(value=d.value, label=label_for(d)) for d in Department]


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


# ── Reporting (`doc/13` §13, ADR 0025) ────────────────────────


class SettingOut(BaseModel):
    """One field on the panel, with the sentence that makes it checkable."""

    key: str
    label: str
    changes: str
    """What it changes, in the question bank's voice."""

    moves_tiles: int
    """How many of **this company's** tiles are computed differently if it
    changes. Derived from the capability registry against the departments they
    run — a company without Operations is not told a setting moves Operations
    tiles. Zero for the two settings that only change how a figure is written."""

    moves_departments: list[str]
    restates: bool
    """Whether changing it triggers the restate rule (`doc/13` §10): affected
    tiles marked stale and re-derived, and the change logged. False for
    presentation, because logging a display preference as a restatement buries
    the changes that matter among the ones that do not."""


class ReportingOut(BaseModel):
    """The assumptions every window on every tile is cut against."""

    currency: str
    """The currency **every figure in the product is labelled in**.

    Doc 05 §1 lists it beside the fiscal year and the timezone as required
    before any dashboard renders, and until now nothing asked for it: the
    registration form dropped it (commit 78ac694, "three facts nothing reads")
    and no settings surface replaced it. `context.assemble` fell back to `OMR`,
    so a company in Dubai would have had its dirhams labelled as rials with
    nothing on screen to correct.
    """

    country: str
    """Where the company is. Not a reporting assumption — a company fact, and it
    belongs on panel 4 with the name and the website when that panel is built.
    It is here because the alternative was continuing to ask for it nowhere."""

    fiscal_year_start_month: int
    week_start: str
    timezone: str
    scale: str
    decimals: int

    changed_at: str | None
    """`None` means never changed since registration — a different fact from
    changed at the moment of registration, which is why the column is nullable."""

    settings: list[SettingOut]
    may_administer: bool


class ReportingIn(BaseModel):
    # Three letters, upper-cased on the way in. Not validated against ISO 4217:
    # a closed list would need a table and a migration to add a currency, and
    # the failure it prevents — a typo — is visible on every tile immediately.
    currency: str = Field(min_length=3, max_length=3)
    country: str = Field(min_length=2, max_length=2)
    fiscal_year_start_month: int = Field(ge=1, le=12)
    week_start: WeekStart
    timezone: str = Field(min_length=1, max_length=64)
    scale: Scale
    decimals: int = Field(ge=0, le=MAX_DECIMALS)


_REPORTING_COLUMNS = (
    "reporting_currency, country,"
    " fiscal_year_start_month, reporting_week_start, report_timezone,"
    " report_scale, report_decimals, reporting_changed_at"
)

# Built once, so the `S608` justification sits in one place — the same
# arrangement `routes/dashboards.py` uses for `BINDING_ONLY_SQL`.
# `_REPORTING_COLUMNS` is a module constant and never input; it is interpolated
# because the select and the update's `RETURNING` must name the *same* columns,
# and a second copy is how one of them ends up missing a field the reader needs.
_SELECT_REPORTING = f"SELECT {_REPORTING_COLUMNS} FROM workspace WHERE id = :w"  # noqa: S608
_UPDATE_REPORTING = (
    "UPDATE workspace SET"
    "   reporting_currency = :currency,"
    "   country = :country,"
    "   fiscal_year_start_month = :month,"
    "   reporting_week_start = :week,"
    "   report_timezone = :tz,"
    "   report_scale = :scale,"
    "   report_decimals = :decimals,"
    "   reporting_changed_at = CASE WHEN :restated"
    "     THEN now() ELSE reporting_changed_at END"
    " WHERE id = :w" + f" RETURNING {_REPORTING_COLUMNS}"
)


def _reporting_out(row: Any, *, selected: frozenset[Department], role: Role) -> ReportingOut:
    settings = [
        SettingOut(
            key=setting.key,
            label=setting.label,
            changes=setting.changes,
            moves_tiles=len(moved := moves(setting, selected=selected)),
            moves_departments=sorted({label_for(c.department) for c in moved}),
            restates=restates_numbers(setting),
        )
        for setting in SETTINGS
    ]
    return ReportingOut(
        # Defaulted on read, not on write. A workspace registered before this
        # panel existed has NULLs, and answering `""` would put an empty
        # currency on every tile — the fallback is the same one
        # `context.assemble` uses, so the panel and the figures agree.
        currency=row.reporting_currency or "OMR",
        country=row.country or "OM",
        fiscal_year_start_month=row.fiscal_year_start_month,
        week_start=row.reporting_week_start,
        timezone=row.report_timezone,
        scale=row.report_scale,
        decimals=row.report_decimals,
        changed_at=row.reporting_changed_at.isoformat() if row.reporting_changed_at else None,
        settings=settings,
        may_administer=may_administer(role),
    )


@router.get("/companies/current/reporting", response_model=ReportingOut)
async def current_reporting(scope: CurrentScope) -> ReportingOut:
    """What every tile's window is cut against.

    Readable by anybody in the workspace, and writable only by an
    administrator. That asymmetry is deliberate: a Contributor cannot change the
    reporting week, and a Contributor who cannot *see* it has no way to check
    the arithmetic in a working drawer that cites it. A number is only checkable
    if the assumptions under it are visible to the person checking.
    """
    async with scoped_connection(scope) as session:
        row = (
            await session.execute(
                text(_SELECT_REPORTING),
                {"w": str(scope.workspace_id)},
            )
        ).first()
        if row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
        selected = await selected_departments(session, workspace_id=scope.workspace_id)

    return _reporting_out(row, selected=selected, role=scope.role)


@router.put(
    "/companies/current/reporting",
    response_model=ReportingOut,
    dependencies=[Depends(require_csrf)],
)
async def update_reporting(
    payload: ReportingIn, scope: CurrentScope, session: CurrentSession
) -> ReportingOut:
    """Change the assumptions, and record that they moved.

    **The stamp and the audit row are written in the same transaction as the
    change**, for `hooks.py`'s reason: an audit trail that survives a rolled-back
    write is a lie about what happened, and a stamp that does not is worse —
    every later derivation would compare itself against a change that never
    landed.

    The stamp only moves when something is actually restated. Choosing thousands
    over units changes how a figure is written and nothing else, so it is stored
    without claiming that this company's history was re-derived.
    """
    if not may_administer(scope.role):
        # 403 rather than 404: this caller can see the settings — the previous
        # endpoint serves them — so the resource's existence is not a secret.
        # What they may not do is move them, and saying so is the honest answer.
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Reporting settings are set by an owner or an executive.",
        )

    # Validated here rather than trusted from the request: `ReportingIn` bounds
    # the numbers, and this bounds the combination the way the domain does.
    ReportingSettings(
        fiscal_year_start_month=payload.fiscal_year_start_month,
        week_start=payload.week_start,
        timezone=payload.timezone,
        scale=payload.scale,
        decimals=payload.decimals,
    )

    async with scoped_connection(scope) as db:
        before = (
            await db.execute(
                text(_SELECT_REPORTING),
                {"w": str(scope.workspace_id)},
            )
        ).first()
        if before is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")

        restated = (
            # A currency change **relabels every figure in the product**, which
            # is a restatement by any reading — the number is the same and what
            # it means is not.
            (before.reporting_currency or "OMR") != payload.currency.upper()
            or before.fiscal_year_start_month != payload.fiscal_year_start_month
            or before.reporting_week_start != payload.week_start.value
            or before.report_timezone != payload.timezone
        )

        row = (
            await db.execute(
                text(_UPDATE_REPORTING),
                {
                    "currency": payload.currency.upper(),
                    "country": payload.country.upper(),
                    "month": payload.fiscal_year_start_month,
                    "week": payload.week_start.value,
                    "tz": payload.timezone,
                    "scale": payload.scale.value,
                    "decimals": payload.decimals,
                    "restated": restated,
                    "w": str(scope.workspace_id),
                },
            )
        ).one()

        if restated:
            await record(
                db,
                workspace_id=scope.workspace_id,
                action=AuditAction.REPORTING_CHANGED,
                actor_user_id=session.user_id,
                target_type="workspace",
                target_id=str(scope.workspace_id),
                reason=(
                    f"currency {payload.currency.upper()},"
                    f" financial year starts month {payload.fiscal_year_start_month},"
                    f" weeks start {payload.week_start.value},"
                    f" reports cut in {payload.timezone}"
                ),
            )

        selected = await selected_departments(db, workspace_id=scope.workspace_id)
        await db.commit()

    return _reporting_out(row, selected=selected, role=scope.role)


# ── Departments (`doc/13` §14, panel 7) ───────────────────────


class DepartmentStateOut(BaseModel):
    """One department, and what turning it on or off would do."""

    value: str
    label: str
    running: bool

    capabilities: int
    """How many capabilities this department brings. Derived from the registry,
    so the sentence on the screen cannot disagree with the product."""

    answered: int
    unanswered: int
    """Its question block, which is what makes its figures this company's rather
    than generic. Shown here because adding a department is also adding
    questions, and a founder should know that before they tick it."""


class DepartmentsOut(BaseModel):
    departments: list[DepartmentStateOut]
    may_administer: bool


class RunningDepartmentsIn(BaseModel):
    departments: list[str] = Field(min_length=1)


@router.get("/companies/current/departments", response_model=DepartmentsOut)
async def current_departments(scope: CurrentScope, answered: AnsweredQuestions) -> DepartmentsOut:
    """Which departments this company runs, and what each one carries.

    **Not the onboarding route.** `POST /onboarding/departments` calls
    `complete_stage`, so reusing it here would re-advance a finished spine every
    time somebody changed their mind in Settings — and the selection would look
    like onboarding progress in the audit trail.

    Readable by anybody in the workspace: which departments a company runs is
    what the nav already shows them. Writable by an administrator only.
    """
    async with scoped_connection(scope) as db:
        chosen = await selected_departments(db, workspace_id=scope.workspace_id)

    return DepartmentsOut(
        departments=[
            DepartmentStateOut(
                value=department.value,
                label=label_for(department),
                running=department in chosen,
                capabilities=len(
                    [
                        capability
                        for capability in capabilities_for(department)
                        if capability.kind is CapabilityKind.TILE
                    ]
                ),
                answered=sum(
                    1
                    for question in QUESTIONS_BY_DEPARTMENT.get(department, ())
                    if (department.value, question.key) in answered
                ),
                unanswered=sum(
                    1
                    for question in QUESTIONS_BY_DEPARTMENT.get(department, ())
                    if (department.value, question.key) not in answered
                ),
            )
            # Sorted, and the Chief of Staff excluded: it is not a department a
            # company chooses to run. `selected_departments` always adds it,
            # because it reads the others — offering it as a tick box would
            # invite somebody to turn off the page that reads everything.
            for department in sorted(Department, key=lambda d: d.value)
            if department is not Department.EXECUTIVE
        ],
        may_administer=may_administer(scope.role),
    )


@router.put(
    "/companies/current/departments",
    response_model=DepartmentsOut,
    dependencies=[Depends(require_csrf)],
)
async def update_departments(
    payload: RunningDepartmentsIn,
    scope: CurrentScope,
    session: CurrentSession,
    answered: AnsweredQuestions,
) -> DepartmentsOut:
    """Change which departments the company runs, and record the change.

    **Removing one is a scope change, not a tidy-up**, so it is audited with
    what was removed. A department that stops running keeps its answers — Q32:
    an answer records what was true for the department it was asked about, and a
    company that stops running Sales has not made its old Sales answers untrue,
    it has made them historical. Deleting them would lose the evidence a later
    disagreement needs.

    The floor of one is finding F1's, and it is the same rule the onboarding
    route enforces: `selected_departments` always adds the Chief of Staff, so a
    stored selection of none and a company that has not chosen yet both arrive
    at `runs_department` as a set of one — which reads as *"nothing has been
    ruled out"* and hands back all seven directors. Refusing zero is what keeps
    the two states tellable apart.
    """
    if not may_administer(scope.role):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Which departments the company runs is set by an owner or an executive.",
        )

    try:
        wanted = {Department(value) for value in payload.departments}
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Unknown department.") from exc

    if not {d for d in wanted if d is not Department.EXECUTIVE}:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Keep at least one department. Each one gets a director and a "
            "dashboard, and the Chief of Staff reads the others — with none "
            "chosen there is nothing for it to read.",
        )

    async with scoped_connection(scope) as db:
        before = await selected_departments(db, workspace_id=scope.workspace_id)
        await select_departments(db, workspace_id=scope.workspace_id, departments=wanted)

        added = sorted(d.value for d in wanted - before if d is not Department.EXECUTIVE)
        removed = sorted(d.value for d in before - wanted if d is not Department.EXECUTIVE)

        if added or removed:
            await record(
                db,
                workspace_id=scope.workspace_id,
                action=AuditAction.DEPARTMENTS_CHANGED,
                actor_user_id=session.user_id,
                target_type="workspace",
                target_id=str(scope.workspace_id),
                reason=(
                    f"added {', '.join(added) or 'none'}; removed {', '.join(removed) or 'none'}"
                ),
            )
        await db.commit()

    return await current_departments(scope, answered)


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
