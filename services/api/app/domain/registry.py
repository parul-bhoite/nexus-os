"""The capability registry: one id space, the table, and the two derived numbers.

`doc/12` P15 (D8, Q64) and `doc/13` §5. Two jobs, and they belong together
because separating them was what let them drift.

## One id space

Until this module held the table there were **two capability id spaces and no
join between them**:

    dashboards.py offerings      doc 05 numbering       "3.2", "4.5", "5.8"
    question_bank consumed_by    doc 08 dotted names    "marketing.conversion_funnel"

Neither set of strings resolved in the other, and three things followed. Q33's
guard — *a question with no consumer is not a question, it is a form field* —
proved only that a question named **a string**, never that the string named
anything. `consumers_of()` returned `()` for every fact, so the review gate's
impact ranking (Q59) ranked everything equally. And no tile could say *"you told
me this"*, which is the whole of the day-one dashboard.

**The dotted name wins** (`doc/13` §25). ADR 0020 already chose it and tested it:
*"two departments will eventually both have a forecast, and a bare name makes
the collision invisible."* Two of them already do — `executive.risk_register`
and `strategy.risk_register` are both called "Risk register" in doc 05, and
`operations.capacity_utilisation` and `people.capacity_utilisation` are the same
offering surfaced on two pages. The doc 05 number is kept on every entry as
provenance, so a tile on a screen still traces to the paragraph that specified
it.

**Validated at import, not on first use.** The same rule `skills.py` follows: a
malformed table should fail the process and be caught by CI, never surface as a
customer opening a dashboard that cannot say what it needs.

**Not `domain/capabilities.py`.** That name was taken, by the P10 scope gate —
`Locked` and `locked_unless_in_scope`, which answer *may this caller compute
this at all*. Two modules about "capabilities" for two different questions is
how a reader ends up in the wrong one, so the table lives here, where the
counting already was.

## Two flags, because they are two facts

This module used to carry one `delivered`, `dashboards.py` carried a `DELIVERED`
frozenset, and `domain/marketing.py` carried a third set of its own — three
mechanisms for one question, which is how a shipped widget renders as "not built
yet", or worse, the reverse. They are unified here, and in unifying them the gap
they were hiding became visible:

- **`implemented`** — the calculation exists in code.
- **`reachable`** — a route serves it to a person.

Marketing's two audit capabilities are `implemented` and **not** `reachable`:
`calculators/audit.py` scores them and `domain/marketing.py` decides their state,
but `marketing_state` is called from its own test and from nowhere else, so no
user can open either tile. That is why the flags are separate rather than one
optimistic boolean — the completeness meter a customer reads must count what
they can open, and `reachable` implies `implemented` is a test rather than a
convention.

## The two numbers

**No literal 6, no literal 21 or 24, anywhere.** A denominator written as a
number is a claim nobody re-checks: it was true when somebody counted, and it
stays on the screen after a seventh department becomes scoreable or a company
selects four. Deriving it means the screen cannot disagree with the product —
and a founder who counts the tiles and gets a different answer has found a
reason to distrust every other number we show them.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, replace
from enum import StrEnum
from typing import Final

from app.domain.dashboards import DIRECTORS, Source
from app.domain.question_bank import BY_DEPARTMENT as QUESTIONS_BY_DEPARTMENT
from app.domain.scopes import Department
from app.domain.sections import PLACEMENT, Block


class CapabilityRegistryError(Exception):
    """The table is malformed. Raised at import, never at call time."""


class CapabilityKind(StrEnum):
    """What a capability *is*, because not all of them are widgets.

    Two of the question bank's declared consumers are not tiles and never will
    be. `executive.recommendation_filter` reads "what is the binding
    constraint?" and "what are you deliberately not doing?" and **suppresses
    recommendations across every director** — modelling it as a tile would put a
    box on a screen for something whose entire job is to make other things not
    appear.

    A `RULE` therefore has no section, renders nothing, and is excluded from the
    completeness meter: it is not a capability a customer acquires, it is one
    that shapes what the others say.
    """

    TILE = "tile"
    RULE = "rule"


@dataclass(frozen=True, slots=True)
class Capability:
    """One capability: what it needs, what it reads, and whether it exists yet."""

    id: str
    """The canonical dotted name — `operations.on_time_dispatch`. Namespaced by
    department, enforced below, for ADR 0020's reason."""

    department: Department
    name: str
    shows: str
    required_sources: tuple[Source, ...]

    consumes_facts: tuple[str, ...]
    """Question-bank keys whose answers this capability reads. **Inverted from
    the bank, never typed here** — the question declares its consumer, so
    declaring the reverse by hand would be the same two-lists failure this
    module exists to end.

    Its length feeds the review gate's impact ranking: a fact matters because
    things depend on it (Q59)."""

    scoreable: bool
    kind: CapabilityKind = CapabilityKind.TILE

    doc05_id: str = ""
    """Doc 05's own numbering. **Empty means doc 08 only** — a capability the
    narrower cut specifies and the wider document never did. Every one of them
    is a question's declared consumer, which is why they are here rather than
    waiting for the section work."""

    section: str = ""
    """Which tab of its director's rail it sits on (`domain/sections.py`).

    **Empty is meaningful**: in the catalogue, not in `doc/08`'s cut of the
    screens — §11's deliberate gaps. It is not the same as missing, and
    `test_sections.py` holds the list so that moving one is a visible edit."""

    block: Block | None = None
    """How it renders. `None` only for a `RULE`, which renders nothing."""

    implemented: bool = False
    """The calculation exists in code."""

    reachable: bool = False
    """A route serves it to a person. Implies `implemented`, and a test says so.
    This is the flag the completeness meter counts, because it is the only one
    that answers the customer's actual question: can I open this?"""

    @property
    def doc08_only(self) -> bool:
        return not self.doc05_id


# ── The join: every doc 05 offering's canonical name ──────────
#
# Sixty-seven entries, one per offering, and the two totality tests in
# `test_capability_registry.py` hold this table and `DIRECTORS` together in both
# directions: an offering with no name here fails, and a name here for an
# offering that no longer exists fails too.
#
# Where the question bank already named a capability, **that name is used
# verbatim** — `marketing.conversion_funnel` for 3.2, `finance.runway_alert` for
# 5.4, `operations.bottleneck_diagnosis` for 6.6. Renaming any of them to
# something tidier would break the join this module exists to make.

_DOC05_KEYS: Final[dict[str, str]] = {
    # Chief of Staff — doc 05 §2
    "2.1": "executive.morning_brief",
    "2.2": "executive.health_score",
    "2.3": "executive.todays_priorities",
    "2.4": "executive.risk_register",
    "2.5": "executive.opportunity_radar",
    "2.6": "executive.decision_queue",
    "2.7": "executive.department_briefings",
    "2.8": "executive.brain_status",
    "2.9": "executive.board_pack",
    # Marketing — doc 05 §3
    "3.1": "marketing.score_drivers",
    "3.2": "marketing.conversion_funnel",
    "3.3": "marketing.channel_performance",
    "3.4": "marketing.growth_planner",
    "3.5": "marketing.content_calendar",
    "3.6": "marketing.content_studio",
    "3.7": "marketing.seo_gaps",
    "3.8": "marketing.brand_intelligence",
    "3.9": "marketing.competitor_war_room",
    "3.10": "marketing.social_publishing",
    "3.11": "marketing.ad_creative",
    "3.12": "marketing.landing_page_recommendations",
    # Sales — doc 05 §4
    "4.1": "sales.score_drivers",
    "4.2": "sales.pipeline_board",
    "4.3": "sales.forecast",
    "4.4": "sales.stale_deal_alert",
    "4.5": "sales.lead_intelligence",
    "4.6": "sales.push_to_crm",
    "4.7": "sales.proposal_studio",
    "4.8": "sales.outreach_drafting",
    "4.9": "sales.communication_intelligence",
    "4.10": "sales.win_loss",
    "4.11": "sales.customer_health",
    "4.12": "sales.deals_lite",
    # Finance — doc 05 §5
    "5.1": "finance.score_drivers",
    "5.2": "finance.revenue_trend",
    "5.3": "finance.margin_analysis",
    "5.4": "finance.runway_alert",
    "5.5": "finance.receivables_ageing",
    "5.6": "finance.budget_vs_actual",
    "5.7": "finance.pricing_recommendations",
    "5.8": "finance.budget_scenarios",
    "5.9": "finance.business_simulator",
    "5.10": "finance.affordability",
    # Operations — doc 05 §6
    "6.1": "operations.score_drivers",
    "6.2": "operations.projects_board",
    "6.3": "operations.milestone_timeline",
    "6.4": "operations.task_queue",
    "6.5": "operations.capacity_utilisation",
    "6.6": "operations.bottleneck_diagnosis",
    "6.7": "operations.project_profitability",
    "6.8": "operations.delivery_risk",
    "6.9": "operations.issue_register",
    "6.10": "operations.subcontractor_performance",
    "6.11": "operations.sop_library",
    "6.12": "operations.document_vault",
    # People — doc 05 §7. **Prefixed `people`, not `hr`**, because that is what
    # the question bank declares (`people.leave_liability`) and because it is
    # what the department is called to a person (finding F13).
    "7.1": "people.directory",
    "7.2": "people.capacity_utilisation",
    "7.3": "people.policy_library",
    "7.4": "people.job_descriptions",
    "7.5": "people.onboarding_checklists",
    "7.6": "people.training_plans",
    # Strategy — doc 05 §8
    "8.1": "strategy.market_position",
    "8.2": "strategy.portfolio_analysis",
    "8.3": "strategy.expansion_analysis",
    "8.4": "strategy.scenario_planning",
    "8.5": "strategy.bid_advisor",
    "8.6": "strategy.risk_register",
}


@dataclass(frozen=True, slots=True)
class _Declared:
    """A capability doc 08 specifies that doc 05 never did."""

    id: str
    department: Department
    name: str
    shows: str
    required_sources: tuple[Source, ...]
    kind: CapabilityKind = CapabilityKind.TILE


# ── The doc-08-only capabilities ──────────────────────────────
#
# **Every one is a question's declared consumer.** That is the admission rule:
# a capability enters this list because something already asks a
# founder for the answer it reads, not because doc 08 draws a section for it.
# Doc 08's remaining sections — payables, cash accounts, the enquiries table —
# arrive with the section work (`doc/13` step D), and adding them now would be
# guessing at their sources before anything consumes them.
#
# The pattern in what is here is worth naming: doc 05 wrote Operations as a
# **contracting** business (projects, milestones, subcontractors) and doc 08
# wrote it as a **distribution** one (dispatch, stock, suppliers). Neither is
# wrong and the product needs both, so these are additions rather than
# corrections — but it is why most of this list is Operations and People.

_DOC08_ONLY: Final[tuple[_Declared, ...]] = (
    _Declared(
        id="executive.recommendation_filter",
        department=Department.EXECUTIVE,
        name="Recommendation filter",
        shows="Nothing of its own — it suppresses recommendations the company has ruled out",
        required_sources=(Source.ONBOARDING,),
        kind=CapabilityKind.RULE,
    ),
    _Declared(
        id="sales.lead_routing",
        department=Department.SALES,
        name="Lead routing",
        shows="Who a new lead belongs to, and whether unassigned is an error state",
        required_sources=(Source.CRM,),
    ),
    _Declared(
        id="sales.quota_attainment",
        department=Department.SALES,
        name="Quota attainment",
        shows="Won against target per person, over the quota period",
        required_sources=(Source.CRM,),
    ),
    _Declared(
        id="finance.approvals_queue",
        department=Department.FINANCE,
        name="Approvals queue",
        shows="Spend requests above the threshold, who asked, and how long they have waited",
        required_sources=(Source.ACCOUNTING,),
    ),
    _Declared(
        id="operations.on_time_dispatch",
        department=Department.OPERATIONS,
        name="On-time dispatch",
        shows="What went out on time against the promised lead time — and which did not",
        required_sources=(Source.OPS_LAYER,),
    ),
    _Declared(
        id="operations.stock_levels",
        department=Department.OPERATIONS,
        name="Stock levels",
        shows="On hand against minimums, ordered by consequence rather than alphabetically",
        required_sources=(Source.OPS_LAYER,),
    ),
    _Declared(
        id="operations.supplier_risk",
        department=Department.OPERATIONS,
        name="Supplier risk",
        shows="Concentration and on-time delivery per supplier",
        required_sources=(Source.OPS_LAYER,),
    ),
    _Declared(
        id="people.leave_liability",
        department=Department.HR,
        name="Accrued leave liability",
        shows="What accrued leave is worth, computed the way this company accrues it",
        required_sources=(Source.ROSTER,),
    ),
    _Declared(
        id="people.requisition_routing",
        department=Department.HR,
        name="Requisition routing",
        shows="Where a new-hire request goes, and what is waiting on whom",
        required_sources=(Source.ROSTER,),
    ),
    _Declared(
        id="people.review_calendar",
        department=Department.HR,
        name="Review calendar",
        shows="When reviews are due, or nothing at all where there is no cycle",
        required_sources=(Source.ROSTER,),
    ),
    _Declared(
        id="people.document_expiry",
        department=Department.HR,
        name="Visa and document expiry",
        shows="What expires when, for the documents this company asked us to track",
        required_sources=(Source.ROSTER,),
    ),
    _Declared(
        id="strategy.competitor_watch",
        department=Department.STRATEGY,
        name="Competitor watch",
        shows="Observed movement per competitor, labelled rather than named until confirmed",
        required_sources=(Source.CRAWL,),
    ),
    _Declared(
        id="strategy.goal_alignment",
        department=Department.STRATEGY,
        name="Goal alignment",
        shows="What every opportunity is ranked against — the company's own definition of success",
        required_sources=(Source.ONBOARDING,),
    ),
)


# ── Step D's two sections, as capabilities ────────────────────
#
# Setup and Watchlist are on the rail, so they are capabilities: they get a
# state, they are counted, and they render through the same path as everything
# else. Building them as a special case in the route would have made them the
# one part of the page whose behaviour nobody could look up.
#
# **`consumes_facts` stays empty for both, deliberately.** That field is
# inverted from the question bank and means *a calculation reads this*. Setup
# displays answers verbatim and the Watchlist quotes one back with what will
# measure it; neither computes anything from them. Declaring the keys here would
# put a second, hand-written source of that relationship beside the bank's — the
# exact failure this module exists to end.


_PREFIXES: Final[dict[Department, str]] = {
    Department.EXECUTIVE: "executive",
    Department.MARKETING: "marketing",
    Department.SALES: "sales",
    Department.FINANCE: "finance",
    Department.OPERATIONS: "operations",
    Department.HR: "people",
    Department.STRATEGY: "strategy",
}


def _our_sections() -> tuple[_Declared, ...]:
    """Setup and Watchlist, for the departments that earned them.

    Derived from the rail rather than listed, so a department that gains a
    question block gains its Setup tab and its capability in one edit.
    """
    from app.domain.sections import RAILS

    declared: list[_Declared] = []
    for department, sections in RAILS.items():
        keys = {section.key for section in sections}
        prefix = _PREFIXES[department]

        if "setup" in keys:
            declared.append(
                _Declared(
                    id=f"{prefix}.setup",
                    department=department,
                    name="What you told us",
                    shows=(
                        "This department's answers, in your words, with the date you"
                        " gave them and the insight each one feeds"
                    ),
                    # **No required source, and that is the point.** It reads
                    # what the workspace already holds, so there is nothing to
                    # connect and nothing to wait for. Declaring `ONBOARDING`
                    # rendered it `locked` on *"needs your setup answers"* — an
                    # instruction to supply the very thing it exists to show
                    # back, which is the opposite of a call to action.
                    #
                    # An empty Setup tab is therefore a fact about the founder's
                    # answers, never about our access.
                    required_sources=(),
                )
            )
        if "watchlist" in keys:
            declared.append(
                _Declared(
                    id=f"{prefix}.watchlist",
                    department=department,
                    name="Watchlist",
                    shows="The risk you named, and what will confirm or refute it",
                    required_sources=(),
                )
            )
    return tuple(declared)


def _setup_and_watchlist_ids() -> frozenset[str]:
    """The ids of step D's sections, so `_REACHABLE` names them without a literal."""
    return frozenset(declared.id for declared in _our_sections())


# ── What exists, and what a person can open ───────────────────

_IMPLEMENTED: Final[frozenset[str]] = frozenset(
    {
        # Step D's sections. `reachable` implies `implemented`, and a test says
        # so — a route cannot serve a calculation that does not exist.
        *_setup_and_watchlist_ids(),
        # `calculators/audit.py` scores these and `domain/marketing.py` decides
        # their state. Both are real; neither is wired to a route (P16's
        # remaining half), which is why they are not `_REACHABLE`.
        "marketing.seo_gaps",
        "marketing.brand_intelligence",
    }
)

_REACHABLE: Final[frozenset[str]] = _setup_and_watchlist_ids()
"""**The first capabilities a person can actually open.**

Everything else is `planned`: no route serves a computed figure yet. These two
per department are different in kind — they read answers that already exist, so
there is nothing to connect and nothing to compute. A founder who finished
onboarding can open them today, which is why the completeness meter stops
reading zero here rather than at the first connector.
"""
"""Nothing yet, and the completeness meter says so.

This is the set that fills in one capability at a time as the section work wires
tiles to routes. Until an id appears here, its tile says it is not built —
anything else puts a widget outline on a screen that a screenshot cannot be
distinguished from a working one.
"""


# ── Assembly ──────────────────────────────────────────────────


def _facts_by_capability() -> dict[str, tuple[str, ...]]:
    """Invert the question bank: capability id -> the question keys it reads.

    The bank is the source. A question declares the capability that consumes it
    (Q33), so the reverse is derived here and never written down — two
    hand-maintained halves of one relationship is what produced the break this
    module repairs.
    """
    found: dict[str, list[str]] = {}
    for questions in QUESTIONS_BY_DEPARTMENT.values():
        for question in questions:
            found.setdefault(question.consumed_by, []).append(question.key)
    return {capability: tuple(keys) for capability, keys in found.items()}


def _placement(capability_id: str, kind: CapabilityKind) -> tuple[str, Block | None]:
    """Where this capability sits and how it draws.

    A `RULE` gets `("", None)` and is expected to have no entry: it renders
    nothing, so a section and a block would be two fields describing a screen it
    never appears on.

    A `TILE` with no entry **raises**. A tile that renders *somewhere
    undecided* would appear in whichever tab the loop was on, and the point of
    the rail is that a person can predict where a thing lives.
    """
    if kind is CapabilityKind.RULE:
        if capability_id in PLACEMENT:
            raise CapabilityRegistryError(
                f"{capability_id} is a rule and has a placement. A rule renders"
                " nothing, so a section and a block describe a screen it is never on."
            )
        return "", None

    try:
        return PLACEMENT[capability_id]
    except KeyError as absent:
        raise CapabilityRegistryError(
            f"{capability_id} has no placement. Add it to `sections.PLACEMENT`"
            " — with an empty section if it is outside doc 08's cut."
        ) from absent


def _build() -> tuple[Capability, ...]:
    facts = _facts_by_capability()
    built: list[Capability] = []

    for director in DIRECTORS:
        for offering in director.offerings:
            key = _DOC05_KEYS.get(offering.id)
            if key is None:
                raise CapabilityRegistryError(
                    f"offering {offering.id} ({offering.name}) has no canonical name."
                    " Add it to `_DOC05_KEYS` — an offering with no name cannot be"
                    " reached by a question, a tool or a skill."
                )
            section, block = _placement(key, CapabilityKind.TILE)
            built.append(
                Capability(
                    id=key,
                    department=director.department,
                    name=offering.name,
                    shows=offering.shows,
                    required_sources=offering.needs,
                    consumes_facts=facts.get(key, ()),
                    scoreable=director.scoreable,
                    doc05_id=offering.id,
                    section=section,
                    block=block,
                )
            )

    for declared in (*_DOC08_ONLY, *_our_sections()):
        scoreable = next(d.scoreable for d in DIRECTORS if d.department is declared.department)
        declared_section, declared_block = _placement(declared.id, declared.kind)
        built.append(
            Capability(
                id=declared.id,
                department=declared.department,
                name=declared.name,
                shows=declared.shows,
                required_sources=declared.required_sources,
                consumes_facts=facts.get(declared.id, ()),
                section=declared_section,
                block=declared_block,
                # A rule is never scored. It shapes what the scored things say.
                scoreable=scoreable and declared.kind is CapabilityKind.TILE,
                kind=declared.kind,
            )
        )

    return tuple(
        replace(
            capability,
            implemented=capability.id in _IMPLEMENTED,
            reachable=capability.id in _REACHABLE,
        )
        for capability in built
    )


def _validate(capabilities: tuple[Capability, ...]) -> None:
    """Six checks, each for a failure that has already happened once here.

    Import-time, so a malformed table fails the process rather than a customer's
    dashboard — `skills.py`'s rule, for `skills.py`'s reason.
    """
    by_id = {c.id: c for c in capabilities}

    if len(by_id) != len(capabilities):
        counted = Counter(c.id for c in capabilities)
        duplicates = sorted(name for name, count in counted.items() if count > 1)
        raise CapabilityRegistryError(f"duplicate capability ids: {duplicates}")

    for capability in capabilities:
        prefix = _PREFIXES[capability.department]
        if not capability.id.startswith(f"{prefix}."):
            raise CapabilityRegistryError(
                f"{capability.id} is in {capability.department.value} and must be"
                f" prefixed `{prefix}.` — ADR 0020: a bare name makes a collision"
                " between two departments' capabilities invisible."
            )

    # Q33's missing half. The bank proved a question named a string; this proves
    # the string names something.
    for questions in QUESTIONS_BY_DEPARTMENT.values():
        for question in questions:
            if question.consumed_by not in by_id:
                raise CapabilityRegistryError(
                    f"question {question.key!r} declares consumer"
                    f" {question.consumed_by!r}, which is not a capability."
                    " Either the capability is missing or the question is a form"
                    " field — ADR 0020 says cut it."
                )

    for missing in sorted(_IMPLEMENTED - by_id.keys()):
        raise CapabilityRegistryError(f"{missing} is marked implemented and does not exist")

    for missing in sorted(_REACHABLE - by_id.keys()):
        raise CapabilityRegistryError(f"{missing} is marked reachable and does not exist")

    for capability in capabilities:
        if capability.reachable and not capability.implemented:
            raise CapabilityRegistryError(
                f"{capability.id} is reachable but not implemented — a route"
                " cannot serve a calculation that does not exist."
            )


CAPABILITIES: Final[tuple[Capability, ...]] = _build()
_validate(CAPABILITIES)

BY_ID: Final[dict[str, Capability]] = {c.id: c for c in CAPABILITIES}
BY_DOC05_ID: Final[dict[str, Capability]] = {c.doc05_id: c for c in CAPABILITIES if c.doc05_id}

TILES: Final[tuple[Capability, ...]] = tuple(
    c for c in CAPABILITIES if c.kind is CapabilityKind.TILE
)


def canonical_id(doc05_id: str) -> str:
    """The dotted name for a doc 05 offering number.

    Exists so a caller holding an `Offering` can reach its capability without
    every route learning the mapping.
    """
    return _DOC05_KEYS[doc05_id]


def is_reachable(doc05_id: str) -> bool:
    """Whether a person can open this offering's tile.

    Takes the doc 05 number because that is what an `Offering` carries, and
    `dashboards.py` must not import this module — the offerings are what this
    table is built *from*, and the cycle would be real.
    """
    capability = BY_DOC05_ID.get(doc05_id)
    return capability is not None and capability.reachable


REGISTRY: Final[tuple[Capability, ...]] = CAPABILITIES
"""The name every caller already imports. `CAPABILITIES` is the definition and
this is the alias — the counting functions below read better against a name that
says what it is."""


# A department may be structurally scoreable and still have nothing to score
# with. `doc/05` §3.1: **Marketing is not scoreable without GA4**, and the brand
# and SEO audit scores must not be merged into a Marketing score to manufacture
# one — they measure the website, not the marketing.
#
# Declared as data so the exception is visible next to the rule rather than
# buried in a branch. An empty tuple means "nothing required beyond the
# department existing", which is the common case.
REQUIRED_FOR_SCORING: Final[dict[Department, tuple[Source, ...]]] = {
    Department.MARKETING: (Source.GA4,),
}


class ScoreableUnit(StrEnum):
    """What the composite score is out of. **Not the same set as `Department`.**

    ADR 0010: *"Customers is scoreable but lives inside the Sales director
    rather than having a page."* That sentence is the whole reason this type
    exists separately.

    Customers is deliberately **not** a `Department`. A department is something
    a person belongs to: it appears in onboarding selection, it goes on a
    membership, and it scopes L3 rows through RLS. Customers is none of those —
    nobody is "in Customers", and adding it to that enum would make it
    selectable, assignable and permission-bearing to fix a counting problem.

    So: six units, five of which happen to be departments with pages, and one
    which is scored inside Sales. Finding #27, resolved this way rather than by
    widening `Department` — the blast radius of that enum is ten modules and
    every RLS policy that reads a department array.
    """

    MARKETING = "marketing"
    SALES = "sales"
    FINANCE = "finance"
    OPERATIONS = "operations"
    HR = "hr"

    CUSTOMERS = "customers"
    """Retention, satisfaction, concentration. Scored, and shown on the Sales
    director's page because that is where the people who act on it already are."""


# Which department has to be running for a unit to be scored. Customers is the
# only entry that differs from its own name, and it is why this is a mapping
# rather than an identity function.
UNIT_REQUIRES_DEPARTMENT: Final[dict[ScoreableUnit, Department]] = {
    ScoreableUnit.MARKETING: Department.MARKETING,
    ScoreableUnit.SALES: Department.SALES,
    ScoreableUnit.FINANCE: Department.FINANCE,
    ScoreableUnit.OPERATIONS: Department.OPERATIONS,
    ScoreableUnit.HR: Department.HR,
    ScoreableUnit.CUSTOMERS: Department.SALES,
}


def scoreable_units(
    selected: frozenset[Department], *, connected: frozenset[Source] | None = None
) -> frozenset[ScoreableUnit]:
    """The units this company is scored out of.

    A company running Sales is scored on **Sales and Customers** — two units,
    one department. That is ADR 0010's arrangement made real, and it is why the
    denominator was never going to equal the number of director pages.

    Marketing still needs GA4 (`REQUIRED_FOR_SCORING`), and the connector rule
    is applied per **unit** against the department it depends on.
    """
    return frozenset(
        unit
        for unit, department in UNIT_REQUIRES_DEPARTMENT.items()
        if department in selected
        and (
            connected is None
            or all(source in connected for source in REQUIRED_FOR_SCORING.get(department, ()))
        )
    )


def scoreable_departments(
    selected: frozenset[Department], *, connected: frozenset[Source] | None = None
) -> frozenset[Department]:
    """The departments with a director page that count toward the composite.

    Both filters matter. A department the company does not run cannot be scored
    — judging them on a function they told us they do not have is worse than
    showing no score. And Chief of Staff and Strategy are never scored: they are
    synthesis layers reading the others, so including them counts the same work
    twice.

    **This is not what the score is out of** — `scoreable_units` is. It returns
    the five departments that have a director page and are scored; Customers is
    a sixth *unit* with no page (ADR 0010), which is what finding #27 turned out
    to be. Kept because "which department pages carry a score" is still a real
    question, asked by the shell when it decides where to show one.
    """
    structural = {
        capability.department
        for capability in TILES
        if capability.scoreable and capability.department in selected
    }

    if connected is None:
        # No connector information supplied: report what could be scored, which
        # is what the registry alone can honestly say. Callers that know what is
        # connected pass it and get the narrower, truer answer.
        return frozenset(structural)

    return frozenset(
        department
        for department in structural
        if all(source in connected for source in REQUIRED_FOR_SCORING.get(department, ()))
    )


def score_denominator(
    selected: frozenset[Department], *, connected: frozenset[Source] | None = None
) -> int:
    """The number under the composite score. **Derived, never written down.**

    A company running three departments is scored out of three. Showing them
    "out of six" reports a number that is low for a reason having nothing to do
    with their business.

    Counts only what has a director page — see `scoreable_departments` and
    finding #27 for why that is five and not six, and why the honest thing is to
    show the number the product can actually justify.
    """
    return len(scoreable_units(selected, connected=connected))


def completeness(selected: frozenset[Department]) -> tuple[int, int]:
    """`(openable, total)` for the capabilities this company can reach.

    Returned as a pair rather than a percentage so the caller can render "0 of
    24" — a percentage hides the denominator, and the denominator is the part
    that makes the claim checkable.

    **Counts `reachable`, not `implemented`.** The two came apart when the three
    delivery mechanisms were unified: Marketing's audit capabilities have a real
    calculation behind them and no route serving it, so counting `implemented`
    here would tell a founder they have two capabilities they cannot open. The
    meter answers their question — *what can I open?* — and nothing else.

    **Tiles only.** A `RULE` shapes what other capabilities say and is not
    something a customer acquires; putting `executive.recommendation_filter` in
    the denominator would make the meter unreachable by one for ever.
    """
    theirs = [c for c in TILES if c.department in selected]
    return sum(1 for c in theirs if c.reachable), len(theirs)


def openable_count() -> int:
    """How many capabilities anybody can open, across the whole product.

    The shell's honesty number, and it is deliberately not `len(_REACHABLE)`
    read from the other module: a count taken from the assembled table cannot
    drift from a set that names an id which no longer exists, because the table
    refuses to build in that case.
    """
    return sum(1 for c in TILES if c.reachable)


def capabilities_for(department: Department) -> tuple[Capability, ...]:
    """Every capability belonging to one department, rules included.

    Rules are included because a caller asking "what does this department have?"
    is usually a reviewer or an agent, and both need to see the filter. The
    completeness meter is the one caller that must not, and it filters."""
    return tuple(c for c in REGISTRY if c.department is department)


def consumers_of(fact_key: str) -> tuple[str, ...]:
    """Which capabilities declare a dependency on a fact.

    Q59's impact score: a fact matters because things depend on it, and the
    dependency is declared by the question rather than guessed from how often
    the fact is mentioned. This returned `()` for everything until the id spaces
    were joined, which made the review gate rank every fact equally — a bug that
    looked exactly like a working feature.
    """
    return tuple(c.id for c in CAPABILITIES if fact_key in c.consumes_facts)
