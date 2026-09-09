"""Sections, and the block each capability renders as.

`doc/13` §4 and §6. A director's page is **4–6 named sections**, not one list of
sixty tiles. The current UI is a flat `<ul>` of every offering, which cannot
express "Dispatch board" or "Receivables ageing" and does not survive the
catalogue: the section is the unit of navigation, the block is the unit of
rendering, and the capability is the unit of truth.

The section names are `doc/08`'s, verbatim — §2C to §8C. They are the cut that
was extracted from the prototype, so they describe screens somebody has already
drawn rather than screens somebody would like.

## Why a capability may have no section

`doc/08` is **narrower than `doc/05`**, and its §11 lists the gaps as
deliberate: the Growth Plan, the Content Studio, the content calendar, ad
creative and the Competitor War Room are *"not present. All are generation
features; none blocked by data."* Those capabilities are real, are in the
registry, and have nowhere on the current screens to sit.

So `section` may be empty, and empty means *in this director's catalogue, not in
this cut's sections*. It does not mean forgotten, and `test_sections.py` holds
the list so that moving one into a section is a deliberate edit.

**Two of those homeless capabilities are fed by a question**, which is a
different and worse thing — see `QUESTION_FED_WITHOUT_A_SECTION` below.

## The ninth block

`doc/13` §6 specified eight. Assigning all eighty found a ninth: eleven
capabilities are **generators** — the content studio, the proposal studio, the
policy library, job descriptions, SOPs, the board pack. A generator is not a
metric, a table or a panel; it takes an instruction and produces an artefact,
and forcing it into `panel` would have made a third of the product's value
render as an explanation of itself.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from app.domain.scopes import Department


class Block(StrEnum):
    """How one capability renders. `doc/13` §6, plus `STUDIO`.

    Nine components rather than sixty bespoke screens. Each kind carries its own
    every-state rule, which is the reason this is a closed list: a tile whose
    kind is unknown has no defined behaviour when its source disconnects, and
    "what does this look like when it is `STALE`" has to have an answer before
    the tile ships.
    """

    METRIC = "metric"
    """Value, unit, delta with its basis, source chips, working drawer. **Never
    a `0`, and never a self-reported figure** — those render as `FACTS`."""

    TREND = "trend"
    """A series over 12 weeks or 12 months. Needs `HISTORY`; below the warm-up
    it states the date of the first comparison rather than drawing one point."""

    TABLE = "table"
    """Rows with computed columns. A dash where there is nothing to divide by,
    never a zero."""

    BOARD = "board"
    """Lanes with named items. **Refuses to state a percentage it cannot
    itemise** — no "88% on time" without the 12% by name."""

    CARDS = "cards"
    """Ranked items, each with its evidence. An item with no evidence trail is
    not shown at all."""

    QUEUE = "queue"
    """Requests waiting on a person, with their age. Empty is a sentence."""

    FACTS = "facts"
    """Quoted answers with attribution and date. Always available, and **never
    styled as measurement** — `doc/05` §0 requires that a number they typed and
    a number we measured never look identical."""

    PANEL = "panel"
    """A named finding or explanation, carrying its inputs."""

    STUDIO = "studio"
    """A generator: an instruction in, an artefact out, every claim cited.

    The ninth, found while assigning the other eight. Its every-state rule is
    its own: a studio with no language model renders `UNAVAILABLE` naming that,
    and a studio whose citations cannot be resolved does not offer the artefact
    at all."""


@dataclass(frozen=True, slots=True)
class Section:
    """One tab on one director's rail."""

    key: str
    label: str
    """`doc/08`'s own wording. Served rather than derived, for finding F13's
    reason: the same thing was `hr` in the API, "Hr" in a checkbox and "People"
    in the nav because each surface title-cased the value itself."""


# ── The rail, per department, in order ────────────────────────
#
# Order is the design. `doc/08` leads every department with Overview because
# that is the screen somebody opens for, and the Executive leads with the
# Morning brief for the same reason. A rail sorted alphabetically would put
# Approvals before Cash on the Finance page.

SECTIONS: Final[dict[Department, tuple[Section, ...]]] = {
    Department.EXECUTIVE: (
        Section("brief", "Morning brief"),
        Section("health", "Business health"),
        Section("depts", "All departments"),
        Section("decisions", "Decisions"),
        Section("brain", "Company Brain"),
        Section("admin", "Admin portal"),
    ),
    Department.MARKETING: (
        Section("overview", "Overview"),
        Section("channels", "Channels"),
        Section("content", "Content & pages"),
        Section("campaigns", "Campaigns"),
        Section("enquiries", "Enquiries"),
    ),
    Department.SALES: (
        Section("overview", "Overview"),
        Section("pipeline", "Pipeline"),
        Section("accounts", "Accounts"),
        Section("team", "My team"),
        Section("forecast", "Forecast"),
    ),
    Department.FINANCE: (
        Section("overview", "Overview"),
        Section("cash", "Cash & runway"),
        Section("receivables", "Receivables"),
        Section("payables", "Payables"),
        Section("approvals", "Approvals"),
    ),
    Department.OPERATIONS: (
        Section("overview", "Overview"),
        Section("dispatch", "Dispatch board"),
        Section("stock", "Stock"),
        Section("suppliers", "Suppliers"),
    ),
    Department.HR: (
        Section("overview", "Overview"),
        Section("hiring", "Hiring"),
        Section("people", "People"),
        Section("leave", "Leave"),
    ),
    Department.STRATEGY: (
        Section("opportunities", "Opportunities"),
        Section("competitors", "Competitors"),
        Section("signals", "Market signals"),
        Section("bets", "Strategic bets"),
    ),
}

_DOC08_SECTIONS: Final[dict[Department, tuple[Section, ...]]] = SECTIONS
"""`doc/08`'s rail alone, before step D appends ours. Kept because "which of
these sections did the specification draw?" is a real question, asked by the
test that holds the five empty ones."""


# ── Where each capability sits, and how it draws ──────────────
#
# `capability id -> (section key, block)`. An empty section key means the
# capability is in the director's catalogue and not in `doc/08`'s cut of the
# screens — §11's deliberate gaps, listed there rather than lost here.

PLACEMENT: Final[dict[str, tuple[str, Block]]] = {
    # Chief of Staff — doc 08 §8C
    "executive.morning_brief": ("brief", Block.CARDS),
    "executive.todays_priorities": ("brief", Block.CARDS),
    "executive.health_score": ("health", Block.METRIC),
    "executive.department_briefings": ("depts", Block.TABLE),
    "executive.decision_queue": ("decisions", Block.QUEUE),
    "executive.brain_status": ("brain", Block.TABLE),
    # Doc 05 offerings the executive cut has no section for. The board pack is
    # a generator; the other two are the Crisis-Detector-shaped work the tools
    # sheet describes as "the engine behind the Risks/Opportunities".
    "executive.risk_register": ("", Block.CARDS),
    "executive.opportunity_radar": ("", Block.CARDS),
    "executive.board_pack": ("", Block.STUDIO),
    # Marketing — doc 08 §2C
    "marketing.score_drivers": ("overview", Block.METRIC),
    "marketing.conversion_funnel": ("overview", Block.METRIC),
    "marketing.channel_performance": ("channels", Block.TABLE),
    "marketing.seo_gaps": ("content", Block.PANEL),
    "marketing.brand_intelligence": ("content", Block.PANEL),
    "marketing.landing_page_recommendations": ("content", Block.CARDS),
    # §11: "Growth Plan, Content Studio, Content Calendar, ad-creative
    # generation, social publishing — not present. All are generation features;
    # none blocked by data."
    "marketing.growth_planner": ("", Block.STUDIO),
    "marketing.content_studio": ("", Block.STUDIO),
    "marketing.ad_creative": ("", Block.STUDIO),
    "marketing.content_calendar": ("", Block.TABLE),
    "marketing.social_publishing": ("", Block.QUEUE),
    "marketing.competitor_war_room": ("", Block.CARDS),
    # Sales — doc 08 §3C
    "sales.score_drivers": ("overview", Block.METRIC),
    "sales.stale_deal_alert": ("overview", Block.TABLE),
    "sales.pipeline_board": ("pipeline", Block.BOARD),
    "sales.lead_routing": ("accounts", Block.TABLE),
    "sales.quota_attainment": ("team", Block.METRIC),
    "sales.forecast": ("forecast", Block.METRIC),
    "sales.win_loss": ("forecast", Block.TABLE),
    "sales.customer_health": ("accounts", Block.TABLE),
    # §11: "Deals-lite manual entry — not present. The cut assumes a connected
    # CRM." The rest are generators or need enrichment.
    "sales.deals_lite": ("", Block.TABLE),
    "sales.lead_intelligence": ("", Block.CARDS),
    "sales.push_to_crm": ("", Block.QUEUE),
    "sales.proposal_studio": ("", Block.STUDIO),
    "sales.outreach_drafting": ("", Block.STUDIO),
    "sales.communication_intelligence": ("", Block.PANEL),
    # Finance — doc 08 §4C
    "finance.score_drivers": ("overview", Block.METRIC),
    "finance.margin_analysis": ("overview", Block.METRIC),
    "finance.runway_alert": ("cash", Block.METRIC),
    "finance.revenue_trend": ("cash", Block.TREND),
    "finance.receivables_ageing": ("receivables", Block.TABLE),
    "finance.approvals_queue": ("approvals", Block.QUEUE),
    # §11: "Finance: budget vs actual — locked, with upload as the named
    # unlock." The simulator and the pricing work are later.
    "finance.budget_vs_actual": ("", Block.TABLE),
    "finance.budget_scenarios": ("", Block.TABLE),
    "finance.pricing_recommendations": ("", Block.CARDS),
    "finance.business_simulator": ("", Block.STUDIO),
    "finance.affordability": ("", Block.PANEL),
    # Operations — doc 08 §5C
    "operations.score_drivers": ("overview", Block.METRIC),
    "operations.on_time_dispatch": ("overview", Block.METRIC),
    "operations.bottleneck_diagnosis": ("overview", Block.PANEL),
    "operations.task_queue": ("dispatch", Block.BOARD),
    "operations.stock_levels": ("stock", Block.TABLE),
    "operations.supplier_risk": ("suppliers", Block.TABLE),
    "operations.subcontractor_performance": ("suppliers", Block.TABLE),
    # Doc 05 wrote Operations as a contracting business — projects, milestones,
    # profitability — and doc 08 wrote it as a distribution one. Both are real
    # and the cut only draws the second, so the project-shaped half waits.
    "operations.projects_board": ("", Block.BOARD),
    "operations.milestone_timeline": ("", Block.TREND),
    "operations.capacity_utilisation": ("", Block.TABLE),
    "operations.project_profitability": ("", Block.TABLE),
    "operations.delivery_risk": ("", Block.CARDS),
    "operations.issue_register": ("", Block.TABLE),
    "operations.sop_library": ("", Block.STUDIO),
    "operations.document_vault": ("", Block.TABLE),
    # People — doc 08 §6C
    "people.leave_liability": ("overview", Block.METRIC),
    "people.requisition_routing": ("hiring", Block.QUEUE),
    "people.job_descriptions": ("hiring", Block.STUDIO),
    "people.directory": ("people", Block.TABLE),
    "people.review_calendar": ("people", Block.TABLE),
    "people.document_expiry": ("people", Block.TABLE),
    "people.capacity_utilisation": ("", Block.TABLE),
    "people.policy_library": ("", Block.STUDIO),
    "people.onboarding_checklists": ("", Block.STUDIO),
    "people.training_plans": ("", Block.STUDIO),
    # Strategy — doc 08 §7C
    "strategy.goal_alignment": ("opportunities", Block.CARDS),
    "strategy.expansion_analysis": ("opportunities", Block.CARDS),
    "strategy.competitor_watch": ("competitors", Block.TABLE),
    "strategy.market_position": ("signals", Block.METRIC),
    "strategy.portfolio_analysis": ("bets", Block.TABLE),
    "strategy.scenario_planning": ("bets", Block.STUDIO),
    "strategy.bid_advisor": ("", Block.PANEL),
    "strategy.risk_register": ("", Block.CARDS),
}


QUESTION_FED_WITHOUT_A_SECTION: Final[frozenset[str]] = frozenset(
    {
        # Question 2.3, "monthly budget you are willing to spend on
        # acquisition". Its declared consumer is the Growth Plan, which `doc/08`
        # §11 cut from the screens — so a founder answers a question whose
        # answer has nowhere to appear.
        "marketing.growth_planner",
        # Question 6.3, "what is your biggest people risk right now?". Its
        # consumer is the Executive risk register, and the executive cut has no
        # risk section — brief, health, departments, decisions, brain, admin.
        "executive.risk_register",
    }
)
"""Two questions whose answers the current cut cannot show anywhere.

ADR 0020's rule for a question nothing consumes is *cut it*. This is the
neighbouring case and it needs the same decision made deliberately: **either the
section arrives, or the question goes.** Answering a question and never using
the answer is worse than not asking — the founder spent the effort and now
believes the product is watching something it is not.

Recorded here rather than fixed, because inventing an executive risk section is
a product decision and `doc/13` §25's rule is that those go to Parul.
"""

EMPTY_SECTIONS: Final[frozenset[tuple[str, str]]] = frozenset(
    {
        # `doc/08` draws these and no capability in the registry produces them.
        # Each needs a capability before its tab can render, and each is
        # therefore part of step D's work list rather than a defect.
        ("marketing", "campaigns"),
        ("marketing", "enquiries"),
        ("finance", "payables"),
        ("hr", "leave"),
        ("executive", "admin"),
    }
)
"""Sections `doc/08` specifies that nothing yet fills.

A tab with nothing behind it cannot render, so the rail has to know. Held as a
set rather than discovered at request time so that filling one is a visible edit
and adding a *sixth* empty tab fails a test instead of shipping a blank screen.
"""


def sections_for(department: Department) -> tuple[Section, ...]:
    """`doc/08`'s tabs, then ours. Order is the specification's, then step D's."""
    return RAILS.get(department, ())


def placement_of(capability_id: str) -> tuple[str, Block]:
    """Where this capability sits and how it draws.

    Raises for an unknown id rather than defaulting to a section: a capability
    with no placement would render in whichever tab the loop happened to be on.
    """
    return PLACEMENT[capability_id]


# ── The reserved assistant panel ──────────────────────────────
#
# `doc/13` §13 and Q67. The panel is reserved in P15 and its empty state is not
# "coming soon": it names the director and lists the questions it will answer,
# in the customer's own language. A reserved region that says what it will do is
# a preview of value; a blank one reads as a bug and a fake one reads as a lie.
#
# The questions are `doc/08` §2E–§8E verbatim. They were written as what a
# founder would actually type, which is why they are not paraphrased here.

ASSISTANT_QUESTIONS: Final[dict[Department, tuple[str, ...]]] = {
    Department.EXECUTIVE: (
        "Why is business health 72 and not higher?",
        "What should worry me most this week?",
        "How long is our runway?",
        "What is waiting on a decision from me?",
    ),
    Department.MARKETING: (
        "Where did this month's enquiries come from?",
        "What is working best right now?",
        "Should I cut the paid budget?",
        "What are we missing?",
    ),
    Department.SALES: (
        "What is in the pipeline?",
        "Which deals are at risk?",
        "What will we actually close this quarter?",
        "How is the team tracking?",
    ),
    Department.FINANCE: (
        "What is our cash position?",
        "Who owes us and how late are they?",
        "Is margin holding up?",
        "What needs approving?",
    ),
    Department.OPERATIONS: (
        "Why are we shipping late?",
        "What is about to run out?",
        "Which supplier is causing problems?",
        "What is on the floor today?",
    ),
    Department.HR: (
        "What is our headcount?",
        "Where are we on hiring?",
        "Any leave I should worry about?",
        "Is attrition a problem?",
    ),
    Department.STRATEGY: (
        "What is the biggest opportunity?",
        "What are competitors doing?",
        "Are we gaining or losing ground?",
        "What is holding us back?",
    ),
}


# ── Step D: the two sections that are ours ────────────────────
#
# `doc/13` §4. Every department with a question block gets a **Setup** section,
# and every department that asked a risk question gets a **Watchlist**. Neither
# is in `doc/08`, and the reason they exist is the cold start: with no connector
# the rest of the rail is honest and empty, and these two are the only things on
# a day-one dashboard that have content.
#
# They are appended after `doc/08`'s sections rather than promoted above them.
# The rail's order is the specification's for the measured screens, and a
# founder who connects a CRM next month should not find their Overview has
# moved. What changes instead is which tab **opens** by default — the API
# reports how much of each section is actually available, and the page leads
# with the first one that has something on it.

SETUP = Section("setup", "Setup")
"""This department's own answers, read back as cited facts.

The founder typed these during onboarding and has not seen them since. Reading
them back does three things at once: it proves what the product holds, it shows
which insight each answer feeds, and it is the only place a wrong answer can be
noticed — an answer nobody ever sees again is an answer nobody can correct.
"""

WATCHLIST = Section("watchlist", "Watchlist")
"""The risks the founder named, turned into things being watched.

Four of the twenty-nine questions are not thresholds or definitions. They are
somebody describing what is currently wrong — who they lose to, which supplier
they are exposed to, their biggest people risk, the constraint binding them
today. A threshold configures a calculation; these are statements about the
business, and a product that collects them and never mentions them again has
taken a confidence and filed it.
"""


@dataclass(frozen=True, slots=True)
class WatchItem:
    """One stated risk, and what would confirm or refute it."""

    question_key: str
    department: Department
    label: str
    """What is being watched, as a heading. Not the question — the *subject*."""

    measured_by: str
    """What we will measure against what they told us. The bridge from
    self-report to measurement, and the reason a watch card is not just their
    answer quoted back."""

    needs: str
    """What that measurement needs. Named, because a watch item with no route to
    being measured is a worry with our logo on it."""


WATCH_ITEMS: Final[tuple[WatchItem, ...]] = (
    WatchItem(
        question_key="lost_to",
        department=Department.MARKETING,
        label="Who you lose to",
        measured_by="Observed movement on the competitors you named — new pages, new offers, ranking changes.",
        needs="the crawl, which runs already, plus keyword data for the ranking half",
    ),
    WatchItem(
        question_key="supplier_concentration",
        department=Department.OPERATIONS,
        label="Supplier concentration",
        measured_by="What share of purchases actually goes to that supplier, and their on-time rate.",
        needs="purchase history in the operations layer",
    ),
    WatchItem(
        question_key="people_risk",
        department=Department.HR,
        label="Your biggest people risk",
        measured_by="Whether the vacancy or the gap you named is still open, and what it is holding back.",
        needs="the roster, and the operations layer for the impact half",
    ),
    WatchItem(
        question_key="binding_constraint",
        department=Department.STRATEGY,
        label="What is binding you",
        measured_by=(
            "Nothing measures this — it filters. Recommendations that need the constraint you"
            " named are suppressed rather than shown and ignored."
        ),
        needs="nothing. It is in force the moment you answer it",
    ),
)
"""**Four, not five.** `doc/13` §9's table lists a fifth from question 8.3 —
*"what decision have you been putting off?"* — feeding the Executive decision
queue. That question is in `doc/08` §8A and **is not in the question bank**:
ADR 0020 cut the bank to six departments with a block, and the Chief of Staff
asks nothing of its own because it consumes the other directors.

So the Executive watch card described in the design does not exist, and cannot
until either the bank gains an executive block or the card is dropped. Named
here rather than quietly built from a question nobody was asked.
"""

WATCHED_DEPARTMENTS: Final[frozenset[Department]] = frozenset(
    item.department for item in WATCH_ITEMS
)
"""Sales and Finance are absent, and that is a property of their questions
rather than an oversight: every one of them is a threshold or a definition —
payment terms, the stale-deal window, the quota period. Useful, and not a
statement about what is currently wrong."""


@dataclass(frozen=True, slots=True)
class NotAsked:
    """A figure we refuse to ask for, and where it comes from instead."""

    what: str
    source: str


# `doc/08` §2B–§8B, verbatim. **Showing the customer what NEXUS refuses to ask
# them is a product surface, not an internal rule** (§11's second addition) —
# and it is the highest-intent place in the application to put a Connect
# button, because the person is reading the list of things they will not have to
# type.
NOT_ASKED: Final[dict[Department, tuple[NotAsked, ...]]] = {
    Department.MARKETING: (
        NotAsked("Sessions, sources and conversion rate", "Google Analytics"),
        NotAsked("Keyword positions and impressions", "Search Console"),
        NotAsked("Ad spend and cost per click", "Google Ads"),
    ),
    Department.SALES: (
        NotAsked("Deals, values, stages and activity dates", "your CRM"),
        NotAsked("Win rate and median cycle length", "CRM history"),
        NotAsked("Quota attainment per person", "your CRM"),
    ),
    Department.FINANCE: (
        NotAsked("Bank balances, invoices and ledger detail", "your accounting system"),
        NotAsked("Receivables ageing and payment history", "your accounting system"),
        NotAsked("Gross margin and cost lines", "your accounting system"),
    ),
    Department.OPERATIONS: (
        NotAsked("Order status, dispatch dates and lateness", "the operations layer"),
        NotAsked("Stock levels against minimums", "the operations layer"),
        NotAsked("Supplier on-time delivery", "purchase history"),
    ),
    Department.HR: (
        NotAsked("Headcount, start dates and contract types", "an HR system"),
        NotAsked("Leave balances and accruals", "an HR system"),
        NotAsked("Open requisitions and time to hire", "an HR system"),
    ),
    Department.STRATEGY: (
        NotAsked("Competitor pages and observed changes", "the web crawl"),
        NotAsked("Share of search against a tracked set", "Search Console"),
        NotAsked("Category search volume", "keyword data"),
    ),
    Department.EXECUTIVE: (
        NotAsked("Every department score and the composite", "all connected sources"),
        NotAsked("What changed since yesterday", "change detection"),
        NotAsked("Decisions waiting on you", "your managers"),
    ),
}


def _with_our_sections() -> dict[Department, tuple[Section, ...]]:
    """Append Setup and Watchlist to the departments that have earned them.

    **The Chief of Staff gets neither.** It has no question block — it consumes
    the other directors rather than asking anything of its own — so a Setup tab
    there would be empty and a Watchlist would have nothing to watch. An empty
    tab is the thing this rail already refuses to render.
    """
    from app.domain.question_bank import BY_DEPARTMENT as QUESTIONS

    rails: dict[Department, tuple[Section, ...]] = {}
    for department, sections in SECTIONS.items():
        extra: list[Section] = []
        if QUESTIONS.get(department):
            extra.append(SETUP)
        if department in WATCHED_DEPARTMENTS:
            extra.append(WATCHLIST)
        rails[department] = (*sections, *extra)
    return rails


def _our_placements() -> dict[str, tuple[str, Block]]:
    """Where Setup and Watchlist sit, and how they draw.

    `FACTS` for Setup — quoted answers with attribution, and **never styled as
    measurement**, which is the whole reason that block kind exists. `CARDS` for
    the Watchlist, because a watch item is a ranked thing carrying its own
    evidence: what you said, what will measure it, what that needs.
    """
    prefixes = {
        Department.EXECUTIVE: "executive",
        Department.MARKETING: "marketing",
        Department.SALES: "sales",
        Department.FINANCE: "finance",
        Department.OPERATIONS: "operations",
        Department.HR: "people",
        Department.STRATEGY: "strategy",
    }
    placements: dict[str, tuple[str, Block]] = {}
    for department, sections in _with_our_sections().items():
        keys = {section.key for section in sections}
        prefix = prefixes[department]
        if "setup" in keys:
            placements[f"{prefix}.setup"] = ("setup", Block.FACTS)
        if "watchlist" in keys:
            placements[f"{prefix}.watchlist"] = ("watchlist", Block.CARDS)
    return placements


PLACEMENT.update(_our_placements())

RAILS: Final[dict[Department, tuple[Section, ...]]] = _with_our_sections()
"""The rail every caller reads: `doc/08`'s sections, then Setup and Watchlist
where the department has questions to show and risks to watch."""

BY_DEPARTMENT_AND_KEY: Final[dict[tuple[Department, str], Section]] = {
    (department, section.key): section
    for department, sections in RAILS.items()
    for section in sections
}
