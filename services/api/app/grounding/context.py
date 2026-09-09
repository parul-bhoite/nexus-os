"""The Company Context, assembled in one place.

`doc/12` P14: *"the Company Context assembler as the **single** path. No widget
builds its own context."* The word doing the work is *single*. Every tile, every
director and every assistant turn is answered from the same object, so the
question *"why are you telling me this?"* has one answer rather than one per
surface.

**What goes wrong without it** is not that contexts differ — it is that they
differ *slightly*. Two widgets that each fetch the brain and the department
facts will agree until one of them forgets the superseded-fact filter, and then
one tile cites last month's payment terms while the tile beside it cites this
month's. Both look right. Nobody can tell which to believe, and the product's
whole claim is that you can check.

## What it holds, and what it refuses to hold

It holds **facts and settings**, never figures. There is no `values` field:
numbers come from `calculators/`, which is pure, and the context is what the
calculators and the prose are grounded *in*. A context carrying a computed
number would be a second place numbers come from, which is I1's failure mode
written as a dataclass.

It holds only what the **caller** may see. The department facts are filtered to
the departments on their session, so a Marketing manager's context cannot cite a
Finance threshold even if the prose would read better for it. That filter is
here rather than at the point of use for the same reason the retrieval predicate
is in the `WHERE`: filtering afterwards means the rows were already fetched, and
every count taken before the filter has leaked their existence.

## Scope travels with the context

`scope_key` is what the `generation` row inherits (migration 0023: *"the
snapshot inherits its inputs' scope tag and retention"*). It is derived from the
inputs rather than from the caller: a snapshot of Finance facts is a Finance
artefact whoever asked for it, and tagging it with the asker's role would make
an Owner's snapshot of the same inputs less sensitive than a manager's.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Final
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import company_brain
from app.domain.company_brain import Brain
from app.domain.department_answers import BINDING_ONLY_SQL
from app.domain.reporting import ReportingSettings, Scale, WeekStart
from app.domain.scopes import Department
from app.domain.session import ScopedSession


def _plain(value: object) -> str:
    """`onboarding_answer.value` is jsonb, so a stored string arrives quoted.

    The same unwrapping `company_brain._plain` does, and for the same reason: a
    citation reading `"30 days"` with the quotes in it is a citation somebody
    stops trusting.
    """
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return ", ".join(str(item) for item in value)
    return str(value)


COMPANY_SCOPE_KEY: Final = "L2"
"""A context holding only company-wide facts. Company-internal, not public:
what a company sells is L1, what it decided about approvals is not."""


@dataclass(frozen=True, slots=True)
class Fact:
    """One fact, with the source that makes it checkable.

    `source_ref` is precise enough to open — a page, a document, an answer. A
    fact whose source cannot be opened is a fact nobody can check, which is the
    thing this product exists not to produce.
    """

    key: str
    value: str
    source_ref: str
    source_kind: str
    unit: str | None = None

    answered_at: str = ""
    """When the founder said it, ISO-8601, or empty for a fact that is not an
    answer.

    The Setup section is *"your answers, with the date you gave them"*, and the
    date is not decoration: an answer from four months ago and one from
    yesterday warrant different confidence, and a founder cannot tell which they
    are looking at without it."""


@dataclass(frozen=True, slots=True)
class CompanyContext:
    """Everything a capability is grounded in, and nothing it computes."""

    workspace_id: UUID
    company_name: str
    currency: str
    reporting: ReportingSettings

    brain: Brain | None = None
    """The current brain, whole rather than flattened to a summary.

    Whole, because different capabilities need different parts of it: the growth
    planner reads `goals`, the content studio reads `brand_voice`, competitor
    watch reads `competitors`. Reducing it to one string here would mean each of
    them re-reading the brain for the part it needed, which is the second path
    this module exists to prevent.

    `None` is a supported state and means onboarding has not finished. A brain
    with `generated_by = 'answers'` is a *complete* brain built without a model
    (ADR 0011), and must never be treated as a degraded one."""

    facts: tuple[Fact, ...] = ()
    """Company-wide facts from the current brain version, superseded ones
    excluded."""

    department_facts: dict[str, tuple[Fact, ...]] = field(default_factory=dict)
    """Keyed by department value, and **only the caller's departments**."""

    scope_key: str = COMPANY_SCOPE_KEY

    def facts_for(self, keys: tuple[str, ...]) -> tuple[Fact, ...]:
        """The facts a capability declares it consumes, in the order declared.

        `Capability.consumes_facts` is the question-bank keys inverted from the
        bank, so this is the join from a tile to the answers behind it — the
        thing that lets a tile say *"you told us a lead is X"*.

        A key with no fact is **omitted rather than defaulted**. The caller has
        to notice the absence, because substituting a plausible value here is
        exactly how an unanswered question turns into a confident number.
        """
        held = {fact.key: fact for group in self._all_groups() for fact in group}
        return tuple(held[key] for key in keys if key in held)

    def missing_facts(self, keys: tuple[str, ...]) -> tuple[str, ...]:
        """Which of them are not here. What a tile's named state is built from."""
        held = {fact.key for group in self._all_groups() for fact in group}
        return tuple(key for key in keys if key not in held)

    def _all_groups(self) -> tuple[tuple[Fact, ...], ...]:
        return (self.facts, *self.department_facts.values())


def scope_key_for(departments: frozenset[Department]) -> str:
    """The scope tag a snapshot of these inputs inherits.

    Sorted, so the same set of departments always produces the same key — an
    unsorted join would give two different tags to identical inputs and make the
    retention and export queries that read this column miss rows.
    """
    if not departments:
        return COMPANY_SCOPE_KEY
    return "L3:" + ",".join(sorted(d.value for d in departments))


# Only the current brain version counts, and a superseded fact is a previous
# answer to a question that has since been answered again. Counting one would
# make a re-run of onboarding look like new knowledge, and citing one would
# quote a founder back to themselves on a position they have already changed.
_FACTS_SQL: Final = """
    SELECT f.key, f.value, f.unit, f.source_ref, f.source_kind
      FROM fact f
      JOIN brain_version bv ON bv.id = f.brain_version_id
     WHERE f.superseded_by_id IS NULL
       AND bv.version = (SELECT MAX(version) FROM brain_version
                          WHERE workspace_id = bv.workspace_id)
"""

_ANSWERS_SQL: Final = (
    "SELECT department, question_key, value, created_at"  # noqa: S608
    "  FROM onboarding_answer"
    f" WHERE department IS NOT NULL AND {BINDING_ONLY_SQL}"
)
"""A **proposed** answer is not a fact (Q31/D22). A Contributor's answer is
kept and waits for a manager at the review gate; grounding prose in it would
let somebody whose own scope is their own records decide what is true for their
whole department."""


def _reachable_departments(scope: ScopedSession) -> tuple[Department, ...]:
    """Which departments' facts this caller may be grounded in.

    **Not `scope.departments`, which is the membership.** An Owner or an
    Executive reaches every department *by role* and usually has none listed on
    their membership at all — `ROLE_GRANTS` calls that `all_departments`, and
    `may_reach_department` has always honoured it.

    Reading the membership here produced a specific and quiet failure: a founder
    who had just registered opened Finance, and the Setup tab said nobody had
    answered anything. Four answers were in the table. The director page let
    them in on their role and the context handed back facts for the departments
    on their membership, which was the empty set — so the page was right about
    their access and wrong about their data.

    Sorted, so a snapshot of the same inputs always produces the same
    `scope_key` and the export queries that read that column cannot miss rows.
    """
    if scope.has_all_departments:
        return tuple(sorted(Department, key=lambda d: d.value))
    return tuple(sorted(scope.departments, key=lambda d: d.value))


async def assemble(db: AsyncSession, scope: ScopedSession) -> CompanyContext:
    """Read everything a capability may be grounded in, once.

    Takes a session that is **already scoped** and the caller's resolved
    authority — never a `workspace_id` argument. That is I2 exactly: a
    `workspace_id` parameter here would make scope something the caller supplies,
    and every RLS policy in the schema exists because it is not.

    Four reads rather than one join. The brain, the facts, the answers and the
    workspace row have different shapes and different lifetimes, and a single
    query returning the cross product of all four would need unpicking in Python
    anyway — at which point the join has bought a wider lock and a query nobody
    can read.
    """
    row = (
        await db.execute(
            text(
                "SELECT name, reporting_currency, fiscal_year_start_month,"
                "       reporting_week_start, report_timezone, report_scale, report_decimals"
                "  FROM workspace WHERE id = :w"
            ),
            {"w": str(scope.workspace_id)},
        )
    ).first()

    if row is None:
        # The isolation policy filtered it, so it is not this caller's
        # workspace. Same answer as one that does not exist.
        raise LookupError("no workspace in scope")

    reporting = ReportingSettings(
        fiscal_year_start_month=row.fiscal_year_start_month,
        week_start=WeekStart(row.reporting_week_start),
        timezone=row.report_timezone,
        scale=Scale(row.report_scale),
        decimals=row.report_decimals,
    )

    brain = await company_brain.current(db, workspace_id=scope.workspace_id)

    facts = tuple(
        Fact(
            key=fact.key,
            value=fact.value,
            unit=fact.unit,
            source_ref=fact.source_ref,
            source_kind=fact.source_kind,
        )
        for fact in (await db.execute(text(_FACTS_SQL))).all()
    )

    answered = (await db.execute(text(_ANSWERS_SQL))).all()
    department_facts: dict[str, tuple[Fact, ...]] = {}
    for department in _reachable_departments(scope):
        department_facts[department.value] = tuple(
            Fact(
                key=answer.question_key,
                value=_plain(answer.value),
                # The answer itself is the source. It is not an inference and it
                # is not a crawl: a founder typed it, and the citation a tile
                # shows is *"you told us, and here is when"*.
                source_ref=f"onboarding_answer:{department.value}:{answer.question_key}",
                source_kind="user_confirmed",
                answered_at=answer.created_at.isoformat() if answer.created_at else "",
            )
            for answer in answered
            if answer.department == department.value
        )

    return CompanyContext(
        workspace_id=scope.workspace_id,
        company_name=row.name,
        currency=row.reporting_currency or "OMR",
        reporting=reporting,
        brain=brain,
        facts=facts,
        department_facts=department_facts,
        scope_key=scope_key_for(frozenset(_reachable_departments(scope))),
    )
