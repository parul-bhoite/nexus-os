"""The seven directors and what each of their dashboards offers.

Doc 05 specifies every offering and, for each one, the sources it needs. ADR 0010
settles that all seven get a page rather than the two doc 07 schedules. This file
is that specification as **data**, for the same reason `ROLE_GRANTS` is data: a
capability-to-source map spread across React components cannot be audited, and
doc 04 §6 rule 1 — *"every locked tile states its unlock"* — is only true if the
unlock is stored next to the tile rather than written into a string by whoever
built the screen.

**Nothing here holds a value, and nothing here computes one.** An offering knows
its name, what it will show, and what it needs before it can show anything. The
numbers arrive in M8 and M9 through `calculators/`, which is pure and contains no
model (I1).

**Deliveredness lives in `domain/registry.py`, not here.** This module once
carried a `DELIVERED` frozenset, `registry.py` carried a `delivered` flag, and
`domain/marketing.py` carried a third set — three mechanisms for one question,
which is how a shipped widget renders as "not built yet" or, worse, the reverse.
`state_for` now takes `reachable` as an argument, so the fact has exactly one
home and this file keeps exactly one job: what an offering *is*.

The distinction that flag protects is still the point. An unbuilt tile renders
`PLANNED` — *"not built yet"* — rather than `LOCKED`, which would say "connect
Google Analytics and this works" about a widget that does not exist. Both are
truthful and only one of them is true today; collapsing them would make the page
a promise instead of a placeholder.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from app.domain.scopes import Department


class Source(StrEnum):
    """What an offering needs before it can show anything.

    Taken from doc 05's *"Information assumptions"* column. Split finely enough
    that a gap banner can name one connection rather than "some data" — doc 05
    §1's banner is *"connect X to unlock 4 more capabilities here"*, which
    requires knowing which X.
    """

    CRAWL = "crawl"
    """The customer's own website, already fetched by Preview."""

    ONBOARDING = "onboarding"
    """Answers from the setup wizard — goals, budget, brand terms, currency."""

    DOCUMENTS = "documents"
    """Uploaded and indexed files (M5)."""

    ROSTER = "roster"
    """The people in the workspace, from membership."""

    LANGUAGE_MODEL = "language_model"
    """Generation. Unconfigured is a supported state (ADR 0011), so an offering
    that needs it renders unavailable rather than failing."""

    OPS_LAYER = "ops_layer"
    """NEXUS's own first-party records: projects, milestones, tasks, cost lines."""

    GA4 = "ga4"
    SEARCH_CONSOLE = "search_console"
    PAGESPEED = "pagespeed"
    DATAFORSEO = "dataforseo"
    CRM = "crm"
    ACCOUNTING = "accounting"
    ADS = "ads"
    ENRICHMENT = "enrichment"
    """Apollo / Clearbit. Phase 2."""

    TENDER_FEED = "tender_feed"
    """Doc 05 §2.5 and §12 — no provider is identified in any source document."""

    HISTORY = "history"
    """Enough elapsed periods to compare. Doc 04 §6 rule 3: week one is a
    baseline, not a brief."""


LABELS: dict[Source, str] = {
    Source.CRAWL: "your website",
    Source.ONBOARDING: "your setup answers",
    Source.DOCUMENTS: "uploaded documents",
    Source.ROSTER: "your team list",
    Source.LANGUAGE_MODEL: "a language model API key",
    Source.OPS_LAYER: "projects and tasks in NEXUS",
    Source.GA4: "Google Analytics",
    Source.SEARCH_CONSOLE: "Search Console",
    Source.PAGESPEED: "PageSpeed",
    Source.DATAFORSEO: "keyword data",
    Source.CRM: "your CRM",
    Source.ACCOUNTING: "your accounting system",
    Source.ADS: "an ad platform",
    Source.ENRICHMENT: "a contact enrichment provider",
    Source.TENDER_FEED: "a tender feed",
    Source.HISTORY: "a few weeks of history",
}


class WidgetState(StrEnum):
    """Doc 05 §0's four states, plus one this milestone needs.

    `PLANNED` is the addition, and it exists because the other four all describe
    a *built* widget. Rendering an unbuilt Growth Planner as `LOCKED` would tell
    the customer that answering some questions unlocks it, which is not true
    yet — and doc 04 §6 rule 1 makes the locked tile a call to action, so a
    false one is worse than no tile.
    """

    LIVE = "live"
    PARTIAL = "partial"
    LOCKED = "locked"

    WARMING = "warming"
    """Connected, but not enough history to say anything yet.

    Distinct from `PARTIAL` because the fix is different and only one of them
    asks something of the customer: `PARTIAL` means connect another source,
    `WARMING` means wait. Telling somebody to connect something they already
    connected is how a product loses their trust in its own instructions."""

    SELF_REPORTED = "self_reported"
    """Computed from what the founder told us, with no connected system behind
    it. Labelled because a number they typed and a number we measured must never
    look identical — the second can contradict them, and the first cannot."""

    STALE = "stale"
    """The data arrived, and it is too old to act on.

    Not `LIVE` with a quiet timestamp: a figure that was true last quarter reads
    as current unless the tile says otherwise, and someone will make a decision
    on it. Not `UNAVAILABLE` either — the number is real and still worth seeing,
    with its age attached."""

    UNAVAILABLE = "unavailable"
    """The pipeline could not produce an answer (P14). Carries the reason from
    `UnavailableReason`, because "unavailable" alone tells a founder nothing
    about whether to wait, connect something, or ask us."""

    PLANNED = "planned"


@dataclass(frozen=True, slots=True)
class Offering:
    """One widget on one director's page."""

    id: str
    """Doc 05's own numbering — `3.4` is the Growth Plan. Kept so a tile on the
    screen can be traced to the paragraph that specified it."""

    name: str
    shows: str
    needs: tuple[Source, ...]
    phase: int = 1
    """1 is MVP. Doc 05 marks some offerings Phase 2 or 3; they are listed so the
    page shows the shape of the product, and they are never presented as
    imminent."""

    note: str = ""
    """A constraint from doc 05 worth carrying to the screen — 'never estimated',
    'deterministic model in code; AI narrates only'."""


WARMUP_DAYS: Final = 14
"""Below this much history a trend is noise. Two weeks is enough to see a
weekly cycle once, which is the shortest period over which "up" or "down" means
anything for a business."""

STALE_AFTER_DAYS: Final = 7
"""Older than this and the tile says so. A week is chosen because it is the
period a founder plans in — a figure from last week is context, and a figure
from last month presented as current is a decision made on the wrong data."""

@dataclass(frozen=True, slots=True)
class Director:
    department: Department
    title: str
    remit: str
    scoreable: bool
    """Doc 05 §10. Chief of Staff and Strategy are synthesis layers and are never
    scored — which is why the composite is out of six, not seven (ADR 0010)."""

    executive_only: bool
    """Doc 06 §2.4 — the Chief of Staff page, the Morning Brief and the composite
    score are Owner and Executive only. A Department Manager's portal is six
    directors, not seven, and that cost is acknowledged rather than hidden."""

    offerings: tuple[Offering, ...]


# ── The seven, from doc 05 sections 2 to 8 ────────────────────

CHIEF_OF_STAFF = Director(
    department=Department.EXECUTIVE,
    title="Nexus Chief of Staff",
    remit="Consumes every other department. Produces no data of its own.",
    scoreable=False,
    executive_only=True,
    offerings=(
        Offering(
            "2.1",
            "Morning Brief",
            "Six items and one recommended action, each citing its data",
            (Source.HISTORY, Source.LANGUAGE_MODEL),
            note=(
                "Week one shows a baseline instead — a brief is deltas, and in week one there is "
                "no prior week."
            ),
        ),
        Offering(
            "2.2",
            "Company Health Score",
            "Composite and per-department breakdown, with its denominator shown",
            (Source.HISTORY,),
            note="Scored against the six scoreable departments, never the seven directors.",
        ),
        Offering(
            "2.3",
            "Today's Priorities",
            "Ranked actions across departments",
            (Source.OPS_LAYER,),
        ),
        Offering(
            "2.4",
            "Risk Register",
            "Top risks with calculated financial exposure",
            (Source.ACCOUNTING, Source.CRM, Source.OPS_LAYER),
        ),
        Offering(
            "2.5",
            "Opportunity Radar",
            "Tenders, expansion signals, hiring activity",
            (Source.TENDER_FEED, Source.ENRICHMENT),
            phase=2,
            note=(
                "No tender provider is identified in any source document — an open procurement "
                "item."
            ),
        ),
        Offering(
            "2.6",
            "Decision Queue",
            "Decisions needing approval, with computed confidence",
            (Source.ADS,),
            phase=3,
            note="Confidence is computed in code, never by the model.",
        ),
        Offering(
            "2.7",
            "Department Briefings",
            "One status line per department, linking through",
            (),
        ),
        Offering(
            "2.8",
            "Company Brain status",
            "Facts known, their sources, and unconfirmed assumptions",
            (Source.ONBOARDING, Source.CRAWL, Source.DOCUMENTS),
        ),
        Offering(
            "2.9",
            "Board Pack export",
            "Assembled pack for a board or a bank",
            (Source.HISTORY,),
            phase=3,
        ),
    ),
)

MARKETING = Director(
    department=Department.MARKETING,
    title="AI Marketing Director",
    remit="The earliest department to become useful — on generation, before any integration.",
    scoreable=True,
    executive_only=False,
    offerings=(
        Offering(
            "3.1",
            "Marketing score and drivers",
            "Score, delta, and what moved it",
            (Source.GA4,),
            note=(
                "Brand and SEO audit scores are separate and must not be merged into a Marketing "
                "score to manufacture a number."
            ),
        ),
        Offering(
            "3.2",
            "Traffic and conversion trend",
            "Sessions, users, sources, on-site conversion",
            (Source.GA4,),
            note="Lead-to-customer conversion is a different metric and also needs a CRM.",
        ),
        Offering(
            "3.3",
            "Channel performance",
            "Traffic by channel, and cost where available",
            (Source.GA4,),
            note=(
                "Cost columns have no connector at MVP — traffic only, with cost self-reported or "
                "locked."
            ),
        ),
        Offering(
            "3.4",
            "Growth Plan (90-day)",
            "Audience, positioning, channel mix, budget split, timeline",
            (Source.ONBOARDING, Source.LANGUAGE_MODEL),
            note="The budget allocation must sum to the stated budget exactly.",
        ),
        Offering(
            "3.5",
            "Content and campaign calendar",
            "Scheduled and drafted items",
            (),
        ),
        Offering(
            "3.6",
            "Content Studio",
            "Blog, ad copy, email, captions, video scripts",
            (Source.ONBOARDING, Source.LANGUAGE_MODEL),
            note=(
                "Depends on the prohibited and preferred terms, which cannot be inferred from a "
                "website."
            ),
        ),
        Offering(
            "3.7",
            "SEO Intelligence",
            "Keyword volumes and difficulty, gaps, briefs, technical issues",
            (Source.DATAFORSEO, Source.CRAWL),
            note="Volumes are fetched, never estimated. Rankings additionally need Search Console.",
        ),
        Offering(
            "3.8",
            "Brand Intelligence",
            "Voice consistency, positioning, messaging gaps",
            (Source.CRAWL, Source.DOCUMENTS, Source.LANGUAGE_MODEL),
        ),
        Offering(
            "3.9",
            "Competitor War Room",
            "Competitor ads, new pages, ranking moves, and what they mean",
            (Source.DATAFORSEO, Source.ADS),
            phase=2,
        ),
        Offering(
            "3.10",
            "Social publishing",
            "Queue, schedule, publish",
            (Source.ADS,),
            phase=2,
        ),
        Offering(
            "3.11",
            "Ad creative generation",
            "Generated image variants from brand assets",
            (Source.ONBOARDING, Source.LANGUAGE_MODEL),
            phase=2,
        ),
        Offering(
            "3.12",
            "Landing page and CTA recommendations",
            "Prioritised on-page fixes",
            (Source.CRAWL, Source.GA4),
        ),
    ),
)

SALES = Director(
    department=Department.SALES,
    title="AI Sales Director",
    remit="Reads the customer's CRM. Owns no pipeline data.",
    scoreable=True,
    executive_only=False,
    offerings=(
        Offering("4.1", "Sales score and drivers", "Score, delta, cause", (Source.CRM,)),
        Offering(
            "4.2",
            "Pipeline overview",
            "Value by stage, count, movement",
            (Source.CRM,),
            note="A missing CRM field disables the widget that needs it, not the whole page.",
        ),
        Offering(
            "4.3",
            "Forecast",
            "Weighted and committed forecast for the period",
            (Source.CRM, Source.HISTORY),
            note="Below three months of closed history: unweighted totals only, labelled as such.",
        ),
        Offering(
            "4.4",
            "Stale and at-risk deals",
            "Deals with no activity beyond a threshold",
            (Source.CRM,),
            note=(
                "Needs reliable activity timestamps — the field most often empty in real CRMs. "
                "Absent, this is disabled rather than guessed."
            ),
        ),
        Offering(
            "4.5",
            "Lead Intelligence",
            "Discovered prospects, match score, why this lead, suggested opener",
            (Source.ONBOARDING, Source.ENRICHMENT),
            phase=2,
            note="Works with no CRM connected.",
        ),
        Offering(
            "4.6",
            "Push to CRM",
            "Write discovered leads into their CRM",
            (Source.CRM,),
            phase=2,
            note="Needs write scope — a much heavier permission than read, asked for separately.",
        ),
        Offering(
            "4.7",
            "Proposal Studio",
            "Client-ready proposals, every price cited to a source document",
            (Source.DOCUMENTS, Source.LANGUAGE_MODEL),
            note=(
                "Works with no CRM connected. A superseded price list cited in a client proposal "
                "is the highest-damage failure in the product."
            ),
        ),
        Offering(
            "4.8",
            "Outreach drafting",
            "Email and message drafts in the company's voice",
            (Source.ONBOARDING, Source.LANGUAGE_MODEL),
        ),
        Offering(
            "4.9",
            "Communication Intelligence",
            "Suggested communication style per contact",
            (Source.ENRICHMENT,),
            phase=2,
            note=(
                "Phrased as suggestion, never as fact about a person, and never used in hiring "
                "decisions."
            ),
        ),
        Offering(
            "4.10",
            "Win/loss analysis",
            "Patterns across won and lost deals",
            (Source.CRM, Source.HISTORY),
        ),
        Offering(
            "4.11",
            "Customer health and churn",
            "Health score, churn risk, revenue at risk",
            (Source.CRM, Source.ACCOUNTING, Source.HISTORY),
            phase=2,
        ),
        Offering(
            "4.12",
            "Deals-lite",
            "A minimal deal tracker for customers with no CRM",
            (Source.OPS_LAYER,),
            note=(
                "Explicitly not a CRM. Values entered here are self-reported and stay marked as "
                "such."
            ),
        ),
    ),
)

FINANCE = Director(
    department=Department.FINANCE,
    title="AI Finance Advisor",
    remit="Entirely gated on one connection.",
    scoreable=True,
    executive_only=False,
    offerings=(
        Offering("5.1", "Finance score and drivers", "Score, delta", (Source.ACCOUNTING,)),
        Offering(
            "5.2",
            "Revenue trend",
            "By month, by service, by customer",
            (Source.ACCOUNTING,),
            note="CRM closed-won is a weaker proxy and is labelled with its source.",
        ),
        Offering(
            "5.3",
            "Margin analysis",
            "Gross and net margin, by service or project",
            (Source.ACCOUNTING, Source.OPS_LAYER),
        ),
        Offering(
            "5.4",
            "Cash position and runway",
            "Balance, burn, runway",
            (Source.ACCOUNTING, Source.HISTORY),
        ),
        Offering(
            "5.5",
            "Receivables ageing",
            "Overdue invoices, collection risk, chase drafts",
            (Source.ACCOUNTING,),
        ),
        Offering(
            "5.6",
            "Expenses against budget",
            "Category spend against plan",
            (Source.ACCOUNTING, Source.ONBOARDING),
            note="No API supplies a budget — it is entered, and stays marked as self-reported.",
        ),
        Offering(
            "5.7",
            "Pricing recommendations",
            "Where prices sit below market or below margin",
            (Source.DOCUMENTS, Source.ACCOUNTING),
        ),
        Offering("5.8", "Budget scenarios", "Compare planned allocations", (Source.ACCOUNTING,)),
        Offering(
            "5.9",
            "Business Simulator",
            "Price changes, hiring and expansion, modelled",
            (Source.ACCOUNTING, Source.OPS_LAYER),
            phase=3,
            note="Deterministic model in code; the model narrates only.",
        ),
        Offering(
            "5.10",
            "Can I afford X?",
            "Questions answered against real financials",
            (Source.ACCOUNTING, Source.LANGUAGE_MODEL),
            phase=3,
        ),
    ),
)

OPERATIONS = Director(
    department=Department.OPERATIONS,
    title="AI Operations Director",
    remit="The only system of record NEXUS owns. Everything here starts with your first project.",
    scoreable=True,
    executive_only=False,
    offerings=(
        Offering("6.1", "Operations score and drivers", "Score, delta", (Source.OPS_LAYER,)),
        Offering(
            "6.2",
            "Active projects board",
            "Status, progress, on-time or at-risk",
            (Source.OPS_LAYER,),
        ),
        Offering("6.3", "Milestone timeline", "Milestones across projects", (Source.OPS_LAYER,)),
        Offering(
            "6.4", "Task queue and overdue", "Assigned work and overdue items", (Source.OPS_LAYER,)
        ),
        Offering(
            "6.5",
            "Capacity and utilisation",
            "Who is on what, and who is over-loaded",
            (Source.OPS_LAYER, Source.ROSTER),
            note=(
                "Available hours come from a settings assumption, not a measurement, and the ratio "
                "is labelled as part-assumption."
            ),
        ),
        Offering(
            "6.6",
            "Bottleneck analysis",
            "Where work consistently stalls",
            (Source.OPS_LAYER, Source.HISTORY),
        ),
        Offering(
            "6.7",
            "Project profitability",
            "Cost against contract value, per project",
            (Source.OPS_LAYER, Source.ACCOUNTING),
            note=(
                "The key cross-department interlock: the margin field renders Locked for anyone "
                "without Finance access."
            ),
        ),
        Offering(
            "6.8",
            "Delivery risk alerts",
            "Late milestones and the revenue they threaten",
            (Source.OPS_LAYER, Source.ACCOUNTING),
        ),
        Offering(
            "6.9",
            "Issue and snag register",
            "Open issues by severity and owner",
            (Source.OPS_LAYER,),
        ),
        Offering(
            "6.10",
            "Subcontractor performance",
            "On-time rate and issue rate per vendor",
            (Source.OPS_LAYER, Source.HISTORY),
        ),
        Offering(
            "6.11",
            "SOP library and builder",
            "Generated and stored procedures",
            (Source.LANGUAGE_MODEL,),
        ),
        Offering(
            "6.12",
            "Project document vault",
            "Per-project files, searchable",
            (Source.DOCUMENTS,),
        ),
    ),
)

PEOPLE = Director(
    department=Department.HR,
    title="AI HR Director",
    remit="Mostly generative — with one real data source once Operations is in use.",
    scoreable=True,
    executive_only=False,
    offerings=(
        Offering(
            "7.1", "Team directory and org view", "People, roles, reporting lines", (Source.ROSTER,)
        ),
        Offering(
            "7.2",
            "Capacity and utilisation",
            "Load per person",
            (Source.OPS_LAYER, Source.ROSTER),
            note=(
                "Assigned hours are measured; available hours are an assumption. The ratio is "
                "labelled as part-assumption."
            ),
        ),
        Offering(
            "7.3",
            "Policy library and generator",
            "HR policies in the company's voice",
            (Source.LANGUAGE_MODEL,),
            note=(
                "Labour law is country-specific — generated policies carry a review-by-local- "
                "counsel notice."
            ),
        ),
        Offering(
            "7.4",
            "Job descriptions and hiring plan",
            "Role descriptions and a hiring sequence",
            (Source.ROSTER, Source.ONBOARDING, Source.LANGUAGE_MODEL),
        ),
        Offering(
            "7.5",
            "Onboarding checklists",
            "Per-role checklists, assignable as tasks",
            (Source.ROSTER, Source.LANGUAGE_MODEL),
        ),
        Offering(
            "7.6",
            "Training plans",
            "Skill gaps and outlines",
            (Source.ROSTER, Source.LANGUAGE_MODEL),
            note="Skill gaps are self-declared, not measured, and are labelled as such.",
        ),
    ),
)

STRATEGY = Director(
    department=Department.STRATEGY,
    title="AI Strategy Director",
    remit=(
        "A synthesis director. Reads the same computed objects as the Chief of Staff, so the two "
        "can never disagree."
    ),
    scoreable=False,
    executive_only=False,
    offerings=(
        Offering(
            "8.1",
            "Market position",
            "Where the company sits against its competitors",
            (Source.CRAWL, Source.DATAFORSEO),
        ),
        Offering(
            "8.2",
            "Service portfolio analysis",
            "Which services to grow, fix or drop",
            (Source.ACCOUNTING, Source.OPS_LAYER, Source.DATAFORSEO),
        ),
        Offering(
            "8.3",
            "Expansion analysis",
            "The case for a new market or service",
            (Source.DATAFORSEO, Source.ACCOUNTING),
        ),
        Offering(
            "8.4",
            "Scenario planning",
            "Compare strategic options",
            (Source.ACCOUNTING, Source.OPS_LAYER),
            phase=3,
            note="Shares the Simulator engine with Finance — deterministic in code.",
        ),
        Offering(
            "8.5",
            "Bid / no-bid advisor",
            "Whether to chase a tender, and at what price",
            (Source.TENDER_FEED, Source.CRM, Source.OPS_LAYER, Source.ACCOUNTING),
            phase=2,
            note="High value for contracting, and it needs three departments live.",
        ),
        Offering(
            "8.6",
            "Risk register",
            "Shared with the Chief of Staff",
            (Source.ACCOUNTING, Source.CRM, Source.OPS_LAYER),
        ),
    ),
)


DIRECTORS: tuple[Director, ...] = (
    CHIEF_OF_STAFF,
    MARKETING,
    SALES,
    FINANCE,
    OPERATIONS,
    PEOPLE,
    STRATEGY,
)

BY_DEPARTMENT: dict[Department, Director] = {d.department: d for d in DIRECTORS}


# ── State ─────────────────────────────────────────────────────


def state_from_sources(
    needs: tuple[Source, ...],
    *,
    connected: frozenset[Source],
    reachable: bool,
    history_days: int | None = None,
    age_days: int | None = None,
    self_reported: bool = False,
    unavailable_reason: str = "",
    warmup_days: int = WARMUP_DAYS,
    stale_after_days: int = STALE_AFTER_DAYS,
) -> WidgetState:
    """The ordering, from the sources alone.

    `state_for` is this with an `Offering` unwrapped in front of it. The split
    exists for `unlock_for_sources`' reason: thirteen capabilities have no
    offering, and a state function that required one could not say what those
    tiles render as.
    """
    if not reachable:
        return WidgetState.PLANNED

    if unavailable_reason:
        return WidgetState.UNAVAILABLE

    missing = [source for source in needs if source not in connected]
    if len(missing) == len(needs) and needs:
        return WidgetState.LOCKED
    if missing:
        return WidgetState.PARTIAL

    if history_days is not None and history_days < warmup_days:
        return WidgetState.WARMING

    if age_days is not None and age_days > stale_after_days:
        return WidgetState.STALE

    if self_reported:
        return WidgetState.SELF_REPORTED

    return WidgetState.LIVE


def state_for(
    offering: Offering,
    *,
    connected: frozenset[Source],
    reachable: bool,
    history_days: int | None = None,
    age_days: int | None = None,
    self_reported: bool = False,
    unavailable_reason: str = "",
    warmup_days: int = WARMUP_DAYS,
    stale_after_days: int = STALE_AFTER_DAYS,
) -> WidgetState:
    """What this offering renders as, given what the workspace actually has.

    **Order is the whole design**, and each step answers a question the next one
    depends on:

    1. `PLANNED` — an unbuilt widget cannot be unlocked by connecting anything,
       and saying otherwise is a promise the product would then break.
       **`reachable` is passed in rather than read from a set here**, because
       `domain/registry.py` is the one place that knows it and it is built
       *from* these offerings — importing it back would be a real cycle. The
       argument has no default for the same reason `writes` has no default in a
       skill manifest: a caller that forgets it should not silently get the
       optimistic answer.
    2. `UNAVAILABLE` — the inputs being present says nothing about whether the
       answer was computable, and rendering `LIVE` over a failed generation
       shows a tile with no number in it.
    3. `LOCKED` / `PARTIAL` — what is missing.
    4. `WARMING` / `STALE` / `SELF_REPORTED` — everything arrived; is it usable?

    The defaults keep every existing caller working: pass nothing and the last
    four are unreachable, which is exactly the behaviour before this phase.
    """
    return state_from_sources(
        offering.needs,
        connected=connected,
        reachable=reachable,
        history_days=history_days,
        age_days=age_days,
        self_reported=self_reported,
        unavailable_reason=unavailable_reason,
        warmup_days=warmup_days,
        stale_after_days=stale_after_days,
    )


def missing_sources(offering: Offering, *, connected: frozenset[Source]) -> tuple[Source, ...]:
    """What is not yet in place. Doc 04 §6 rule 1 — the tile states its unlock."""
    return tuple(source for source in offering.needs if source not in connected)


def unlock_for_sources(needs: tuple[Source, ...], *, connected: frozenset[Source]) -> str:
    """The unlock, from the sources alone.

    Exists because **not every capability has an offering.** Thirteen are
    `doc/08`-only — the narrower cut specified them and `doc/05` never did — so
    a sentence that could only be built from an `Offering` left exactly the
    tiles a question feeds with no unlock at all, which is the one place
    `doc/04` §6 rule 1 cannot be broken.
    """
    missing = tuple(source for source in needs if source not in connected)
    if not missing:
        return ""
    names = [LABELS[source] for source in missing]
    if len(names) == 1:
        return f"Needs {names[0]}."
    return f"Needs {', '.join(names[:-1])} and {names[-1]}."


def unlock_sentence(offering: Offering, *, connected: frozenset[Source]) -> str:
    """The unlock, in words, or an empty string when there is nothing missing.

    Built here rather than in the UI so that one wording change reaches every
    surface, and so a tile can never be shipped with the outline drawn and the
    sentence forgotten.
    """
    return unlock_for_sources(offering.needs, connected=connected)


def landing_department(
    *, executive_surface: bool, departments: frozenset[Department]
) -> Department | None:
    """Which director to open after signing in.

    Resolved from the caller's **membership**, never from the `department`
    answer in onboarding. That answer is a stated fact about the person; the
    membership is what authorises, and landing someone on a page their scope
    does not reach would produce a 404 immediately after setup.

    Owner and Executive land on the Chief of Staff, which is the only page that
    reads across all seven. Everyone else lands on their own department, and a
    caller with no department at all gets `None` — there is no sensible default,
    and picking one would put someone in a department nobody assigned them to.
    """
    if executive_surface:
        return Department.EXECUTIVE
    if not departments:
        return None
    return sorted(departments)[0]
