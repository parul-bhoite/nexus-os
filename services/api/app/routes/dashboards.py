"""The seven director pages, and where a person lands.

Placeholders in the honest sense: the shell, the offering list and every
capability-to-source mapping are real and come from doc 05, and **no tile
carries a value**, because none has been computed yet. M8 and M9 fill them in
through `calculators/`, which is pure.

Two boundaries are enforced here rather than in the UI, and both are doc 06:

- **§2.3** — a caller reaching a department they do not hold gets a 404, via
  `enforce_department`. Not 403: *"this exists and you may not have it"* is an
  existence disclosure about how the company is organised.
- **§2.4** — the Chief of Staff page is Owner and Executive only, so a
  Department Manager's portal is six directors rather than seven. That cost is
  acknowledged in the document and is not softened here.

The list endpoint returns only the directors the caller may open. It does not
return the others marked "locked", and it carries no count of what was removed —
doc 06 §4.5, the same rule `filter_records` follows.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import text

from app.ai.runtime.fields import FIELD_CATALOGUE
from app.db import _unscoped_session
from app.deps import CurrentScope
from app.deps_scope import enforce_department
from app.domain.dashboards import (
    BY_DEPARTMENT,
    DELIVERED,
    DIRECTORS,
    Director,
    Offering,
    Source,
    landing_department,
    state_for,
    unlock_sentence,
)
from app.domain.department_answers import BINDING_ONLY_SQL
from app.domain.departments import label_for, runs_department, selected_departments

# Aliased: `BY_DEPARTMENT` already means the dashboard *offerings* here, and two
# dictionaries with one name is how the wrong one gets read.
from app.domain.question_bank import BY_DEPARTMENT as QUESTIONS_BY_DEPARTMENT
from app.domain.registry import completeness, score_denominator
from app.domain.scopes import Department
from app.retrieval.scoped import apply_workspace_scope, scoped_connection

router = APIRouter(prefix="/dashboards", tags=["dashboards"])


def connected_sources() -> frozenset[Source]:
    """What this workspace actually has wired up.

    Empty, and honestly so. Document upload exists (M5) but nothing yet reads an
    indexed document into a dashboard, and no integration exists at all before
    M10. Returning `{DOCUMENTS}` here because the upload route exists would make
    every tile that needs documents claim to be one step from working.

    This is the single place that changes as connectors land, and it takes no
    arguments today for the same reason: a per-workspace answer needs the
    integration registry that M10 introduces, and inventing a shape for it now
    would be guessing at the wrong problem.
    """
    return frozenset()


class OfferingOut(BaseModel):
    id: str
    name: str
    shows: str
    state: str
    unlock: str
    """What this needs, in words. Empty only when nothing is missing."""
    needs: list[str]
    phase: int
    note: str


class DirectorOut(BaseModel):
    department: str
    title: str
    remit: str
    scoreable: bool
    path: str
    offerings: list[OfferingOut]


class DirectorSummary(BaseModel):
    department: str
    label: str
    """The department's name for a person, so the nav does not special-case one
    of them and title-case the rest (finding F13)."""

    title: str
    remit: str
    scoreable: bool
    path: str
    offering_count: int
    unanswered_questions: int = 0
    """Q27. How many of this department's questions are still unanswered.

    The founder answers their own department during onboarding and defers the
    rest, so most directors start here with a number. It belongs on the director
    because that is where the deferral becomes concrete: a dashboard that cannot
    yet compute anything should say **what would turn it on**, not sit empty.

    Zero means the block is complete. A director with no block — the Chief of
    Staff — is always zero, because it consumes the other directors rather than
    asking anything of its own.
    """


class DashboardsOut(BaseModel):
    directors: list[DirectorSummary]
    landing: str | None
    """Where to send this caller. `None` when they hold no department — which
    happens to a Viewer, and is a state to render rather than a redirect."""

    delivered_count: int
    """How many offerings across the whole product have an implementation. Zero
    today. Shown so the page cannot imply more than exists."""


def _path(department: Department) -> str:
    return f"/dashboard/{department.value}"


def _offering_out(offering: Offering, connected: frozenset[Source]) -> OfferingOut:
    return OfferingOut(
        id=offering.id,
        name=offering.name,
        shows=offering.shows,
        state=state_for(offering, connected=connected).value,
        unlock=unlock_sentence(offering, connected=connected),
        needs=[source.value for source in offering.needs],
        phase=offering.phase,
        note=offering.note,
    )


# Built once, so the `S608` justification sits in one place. `BINDING_ONLY_SQL`
# is a module constant and never input; it is interpolated because every reader
# of department facts must use the *same* predicate, and a copy per query is how
# one ends up missing it.
_ANSWERED_SQL = (
    "SELECT department, question_key FROM onboarding_answer"  # noqa: S608
    f" WHERE department IS NOT NULL AND {BINDING_ONLY_SQL}"
)

# The other surface that answers the same questions. `fact` is where the agent
# interview lands (`domain/onboarding_promotion`), keyed by catalogue key rather
# than bank key; `FieldSpec.question_key` is the join, and it lives on the field
# so there is no third table to keep in step.
#
# Only the current Brain version counts. A superseded fact is a previous answer
# to a question that has since been answered again, and counting it would make
# a re-run of onboarding look like progress it is not.
_PROMOTED_SQL = (
    "SELECT f.key FROM fact f"
    " JOIN brain_version bv ON bv.id = f.brain_version_id"
    " WHERE f.superseded_by_id IS NULL"
    "   AND bv.version = (SELECT MAX(version) FROM brain_version"
    "                     WHERE workspace_id = bv.workspace_id)"
)


async def running_departments(scope: CurrentScope) -> frozenset[Department]:
    """Which departments this company runs (Q22/Q63).

    A dependency rather than a call inside the handler, so the route stays a
    pure function of its inputs and `tests/test_dashboard_scope.py` can keep
    asserting the *permission* lattice without standing up a database. Reading
    it inline turned four unit tests into integration tests, which is a real
    cost and not one this filter is worth.
    """
    async with _unscoped_session() as db:
        return await selected_departments(db, workspace_id=scope.workspace_id)


RunningDepartments = Annotated[frozenset[Department], Depends(running_departments)]


async def answered_questions(scope: CurrentScope) -> frozenset[tuple[str, str]]:
    """Which department questions already have a **binding** answer (Q27).

    A dependency for the same reason `running_departments` is one, and this is
    the second time that lesson has been learned in this file: reading it inline
    turns four permission unit tests into integration tests, because they assert
    the lattice and have no database.

    One query for the whole dashboard list rather than one per director — six
    round trips to render a screen is how it becomes slow before it holds any
    data.
    """
    async with _unscoped_session() as db:
        await apply_workspace_scope(db, str(scope.workspace_id))
        rows = (await db.execute(text(_ANSWERED_SQL))).all()
        promoted = (await db.execute(text(_PROMOTED_SQL))).scalars().all()

    answered = {(r.department, r.question_key) for r in rows}
    # An interview answer counts as answering its bank question. Without this
    # the counter reads one of two writers and reports the other's work as
    # outstanding — a founder who answered every operational threshold was
    # still told five questions were open.
    for key in promoted:
        spec = FIELD_CATALOGUE.get(str(key))
        if spec is not None and spec.question_key and spec.department:
            answered.add((spec.department, spec.question_key))
    return frozenset(answered)


AnsweredQuestions = Annotated[frozenset[tuple[str, str]], Depends(answered_questions)]


def _reachable(scope: CurrentScope, director: Director) -> bool:
    if director.executive_only:
        return scope.can_see_executive_surface
    return scope.may_reach_department(director.department)


@router.get("", response_model=DashboardsOut)
async def list_dashboards(
    scope: CurrentScope, chosen: RunningDepartments, answered: AnsweredQuestions
) -> DashboardsOut:
    """The directors this caller may open, and where to land them.

    **Two filters, and they answer different questions.** Which departments the
    *company runs* (Q22/Q63, chosen during onboarding) decides which directors
    exist at all; which the *caller may reach* decides who sees them. A company
    that does not run a sales function should show no Sales Director to anybody,
    including its Owner — an empty dashboard reads as broken data rather than as
    an absent department, which is the whole reason selection exists.

    A workspace that has not chosen yet gets all seven. That is the honest
    default: nothing has been said about this company, so nothing has been ruled
    out, and hiding directors from someone who never made a choice would be the
    product deciding on their behalf.
    """
    visible = [
        d for d in DIRECTORS if _reachable(scope, d) and runs_department(chosen, d.department)
    ]

    landing = landing_department(
        executive_surface=scope.can_see_executive_surface,
        departments=scope.departments,
    )

    def outstanding(department: Department) -> int:
        # A proposed answer does not count as answered. A block that looked
        # complete because a Contributor filled it in would hide the very thing
        # the review gate exists to surface.
        return sum(
            1
            for q in QUESTIONS_BY_DEPARTMENT.get(department, ())
            if (department.value, q.key) not in answered
        )

    return DashboardsOut(
        directors=[
            DirectorSummary(
                department=d.department.value,
                label=label_for(d.department),
                title=d.title,
                remit=d.remit,
                scoreable=d.scoreable,
                path=_path(d.department),
                unanswered_questions=outstanding(d.department),
                offering_count=len(d.offerings),
            )
            for d in visible
        ],
        landing=_path(landing) if landing else None,
        delivered_count=len(DELIVERED),
    )


class DepartmentSection(BaseModel):
    """One department's slice of the company dashboard."""

    department: str
    label: str
    """The department's name for a person. See `DirectorSummary.label`."""

    title: str
    remit: str
    path: str
    unanswered_questions: int
    offerings_planned: int
    is_yours: bool
    """Whether this is a department the caller is *in*, as opposed to one they
    may reach because of their role. An owner reaches all seven; only some are
    theirs, and the page leads with those."""


class ShellOut(BaseModel):
    """The global shell (`doc/12` P15), with every number derived.

    **The denominator travels with the score**, and that is the point of this
    object. A score shown alone is a claim the founder cannot check; "out of
    three" lets them count their own departments and agree. It is also why
    `score` is `None` rather than `0` when nothing is computable — zero is a
    statement about their business, and absence is a statement about our data
    (I10).
    """

    score: float | None
    score_denominator: int
    """Derived from the registry against the departments this company runs. No
    literal 6 anywhere — see finding #27 for what deriving it turned up."""

    capabilities_delivered: int
    capabilities_total: int
    """A pair, not a percentage. A percentage hides the denominator, and the
    denominator is the part that makes the claim checkable."""

    assistant_reserved: bool = True
    """Q67. The panel is reserved and renders an honest empty state naming what
    it will do — a blank region where a feature is coming reads as a bug, and a
    fake one reads as a lie."""


class CompanyDashboardOut(BaseModel):
    """**The** company dashboard — one page, the same URL for everybody.

    `doc/05`'s shape is one company view whose *content* changes with who is
    looking, not seven separate pages behind seven separate permissions. So
    every member of a workspace opens the same thing and sees their own slice
    of it, which is what makes "ask your colleague about the finance tile" a
    conversation rather than a support ticket.

    **Segregation is by omission, not by greying out.** A department the caller
    may not reach is absent from `departments` entirely — not listed as locked,
    not counted, not named. Rendering it disabled would disclose that the
    company runs a department this person was not told about, and how a company
    is organised is itself a fact about it.
    """

    company: str
    brain_available: bool
    """Whether the company brain has anything in it yet. A flag rather than the
    brain itself: this page says what exists, and `/onboarding/brain` serves the
    content to whoever asks for it."""

    shell: ShellOut
    departments: list[DepartmentSection]
    yours: list[str]
    """The departments this caller is in. The page leads with these."""

    landing: str | None


@router.get("/company", response_model=CompanyDashboardOut)
async def company_dashboard(
    scope: CurrentScope, chosen: RunningDepartments, answered: AnsweredQuestions
) -> CompanyDashboardOut:
    """One dashboard for the company, segregated by department.

    Declared **before** `/{department}` because FastAPI matches in definition
    order and `company` is a valid department-shaped path segment as far as the
    router is concerned — the reverse order answers this with "no such
    department", which is a confusing 404 for a route that exists.
    """
    visible = [
        d for d in DIRECTORS if _reachable(scope, d) and runs_department(chosen, d.department)
    ]
    connected = connected_sources()

    def outstanding(department: Department) -> int:
        return sum(
            1
            for q in QUESTIONS_BY_DEPARTMENT.get(department, ())
            if (department.value, q.key) not in answered
        )

    async with scoped_connection(scope) as db:
        name = (
            await db.execute(
                text("SELECT name FROM workspace WHERE id = :w"),
                {"w": str(scope.workspace_id)},
            )
        ).scalar_one_or_none()
        has_brain = bool(
            (
                await db.execute(
                    text(
                        "SELECT 1 FROM company_brain"
                        " WHERE workspace_id = :w AND superseded_at IS NULL"
                        "   AND generated_by <> 'unavailable'"
                    ),
                    {"w": str(scope.workspace_id)},
                )
            ).first()
        )

    sections = [
        DepartmentSection(
            department=d.department.value,
            label=label_for(d.department),
            title=d.title,
            remit=d.remit,
            path=_path(d.department),
            unanswered_questions=outstanding(d.department),
            # Computed through `state_for`, not read off the offering — an
            # offering has no state of its own; it has a state *given what is
            # connected*, and hard-coding "planned" here would stop telling the
            # truth the first time something is delivered.
            offerings_planned=sum(
                1 for o in d.offerings if state_for(o, connected=connected).value == "planned"
            ),
            is_yours=d.department in scope.departments,
        )
        for d in visible
    ]
    # Theirs first. Not a sort by name or by size — the department you work in
    # is the one you came here for.
    sections.sort(key=lambda s: (not s.is_yours, s.department))

    delivered, total = completeness(chosen)
    return CompanyDashboardOut(
        shell=ShellOut(
            # `None`, never `0`. Nothing is delivered, so nothing is computable,
            # and a zero would be a statement about their business (I10).
            score=None,
            score_denominator=score_denominator(chosen),
            capabilities_delivered=delivered,
            capabilities_total=total,
        ),
        company=name or "Your company",
        brain_available=has_brain,
        departments=sections,
        yours=[d.value for d in sorted(scope.departments, key=lambda x: x.value)],
        landing=_path(
            landing_department(
                executive_surface=scope.can_see_executive_surface,
                departments=scope.departments,
            )
            or Department.EXECUTIVE
        )
        if visible
        else None,
    )


@router.get("/{department}", response_model=DirectorOut)
async def director_dashboard(
    department: Department, scope: CurrentScope, chosen: RunningDepartments
) -> DirectorOut:
    """One director's page.

    `enforce_department` is what refuses a department the caller does not hold,
    and it 404s. The executive check is separate because it is a different rule
    with a different answer: the Chief of Staff page is not a department someone
    might be added to, so naming the requirement is safe and useful.
    """
    director = BY_DEPARTMENT.get(department)
    if director is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")

    if director.executive_only and not scope.can_see_executive_surface:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "The Chief of Staff view requires an Owner or Executive role.",
        )

    enforce_department(scope, director.department)

    # Finding #21. `enforce_department` asks whether the *caller* holds this
    # department; `chosen` asks whether the *company runs* it, and an owner
    # holds all seven while running only the ones they picked at stage 4.
    # Without this the list and the detail disagreed: `GET /dashboards` omitted
    # People and `GET /dashboards/hr` served it. `chosen` empty means the
    # company has not chosen yet, which the list treats as "show everything"
    # rather than "show nothing" — the same reading, so the two agree before
    # stage 4 as well as after it.
    if not runs_department(chosen, director.department):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")

    connected = connected_sources()
    return DirectorOut(
        department=director.department.value,
        title=director.title,
        remit=director.remit,
        scoreable=director.scoreable,
        path=_path(director.department),
        offerings=[_offering_out(offering, connected) for offering in director.offerings],
    )
