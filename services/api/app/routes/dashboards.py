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

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Annotated, Final

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import text

from app.ai.registry import get_provider
from app.ai.runtime.fields import FIELD_CATALOGUE
from app.ai.runtime.hooks import get_hooks
from app.ai.runtime.runner import SkillRunner
from app.auth.csrf import require_csrf
from app.config import Settings, get_settings
from app.db import _unscoped_session
from app.deps import CurrentScope
from app.deps_scope import enforce_department
from app.domain.brief import compose
from app.domain.dashboards import (
    BY_DEPARTMENT,
    DIRECTORS,
    Director,
    Offering,
    Source,
    landing_department,
    state_for,
    state_from_sources,
    unlock_for_sources,
    unlock_sentence,
)
from app.domain.department_answers import BINDING_ONLY_SQL
from app.domain.departments import label_for, runs_department, selected_departments
from app.domain.director_rows import compose as compose_rows
from app.domain.narration import StoredNarration, describes, sentence_for
from app.domain.open_questions import compose as compose_questions

# Aliased: `BY_DEPARTMENT` already means the dashboard *offerings* here, and two
# dictionaries with one name is how the wrong one gets read.
from app.domain.question_bank import BY_DEPARTMENT as QUESTIONS_BY_DEPARTMENT
from app.domain.registry import (
    BY_ID,
    TILES,
    Capability,
    CapabilityKind,
    canonical_id,
    capabilities_for,
    completeness,
    coverage,
    is_reachable,
    openable_count,
    score_denominator,
)
from app.domain.scopes import Department
from app.domain.sections import (
    ASSISTANT_QUESTIONS,
    NOT_ASKED,
    WATCH_ITEMS,
    Section,
    sections_for,
)
from app.grounding.answer import NARRATOR, narrate
from app.grounding.compute import CRAWL_AUDITS, compute_from_crawl, computes
from app.grounding.context import CompanyContext, assemble
from app.grounding.pipeline import Outcome, UnavailableReason
from app.logging import get_logger
from app.retrieval.crawl import CrawlSnapshot, current_page_signals
from app.retrieval.narration import current_narrations
from app.retrieval.scoped import apply_workspace_scope, scoped_connection

log = get_logger(__name__)

router = APIRouter(prefix="/dashboards", tags=["dashboards"])


@dataclass(frozen=True, slots=True)
class Observed:
    """What this workspace demonstrably has.

    Every field is a thing something **looked at**, never a thing whose route
    exists. That distinction is the whole point: the previous version of
    `connected_sources` returned an empty set and explained that returning
    `{DOCUMENTS}` "because the upload route exists" would make every tile
    needing documents claim to be one step from working. Same rule, now with
    somewhere to put the answers.
    """

    crawl: CrawlSnapshot | None
    """The page this workspace's most recent crawl led with, or `None`.

    The snapshot rather than a boolean, because the two callers want different
    halves of the same row and one read must serve both: the state machine
    needs only "is there a crawl", and the figure needs the signals themselves.
    Answered by `retrieval/crawl.py`, not inferred from the domain being set or
    from onboarding having finished — a crawl that found nothing readable is a
    completed onboarding with no signals, which is exactly the case a tile must
    render as `locked`.
    """

    narrations: dict[str, StoredNarration] = field(default_factory=dict)
    """Every capability's most recent stored sentence, keyed by capability id.

    Defaulted, so the hermetic permission tests that construct an `Observed`
    with no database keep compiling — and so a workspace that has never
    narrated anything costs the same as one that has.

    What is stored is not necessarily what is shown: `describes` decides
    whether a sentence still applies to the figure recomputed beside it, and
    that decision is made per tile in `block_out`, not here. A read that
    quietly dropped rows it judged stale would make the rule invisible to
    anybody reading either half.
    """

    @property
    def crawled(self) -> bool:
        return self.crawl is not None


def connected_sources(observed: Observed) -> frozenset[Source]:
    """The sources this workspace actually has wired up.

    **Only `CRAWL`, and only because something asked.** The four other
    OURS-origin sources — `ONBOARDING`, `ROSTER`, `OPS_LAYER` and the TIME
    origin `HISTORY` — are deliberately absent: no reachable capability needs
    any of them, so claiming them would change the state of tiles nobody has
    verified. That is the same failure the empty set existed to avoid, arrived
    at from the other direction.

    `DOCUMENTS` and `LANGUAGE_MODEL` are absent too, and both are decisions.
    The honest test for documents is `retrieval.chunks.count(db, scope) > 0`,
    which is **per-caller** — an Owner and a Contributor in one workspace would
    get different tile states, correct under I2/I3 but a thing that deserves
    its own slice. A model *key* being set is not a model being read, and
    nothing on the dashboard path reads one until narration lands; claiming it
    now would let `brand_intelligence` reach `live` and so claim the voice
    analysis its name promises, which `score_brand` does not do.

    Every CONNECTOR-origin source stays absent until M10's integration
    registry. `DATAFORSEO` stays absent under D2, and that is what keeps
    `seo_gaps` honestly `partial` rather than accidentally `live`.

    Widening this is safer than it looks, and `test_capability_registry.py`
    asserts why: `state_from_sources` short-circuits on `not reachable` before
    it reads `connected` at all, so a new source can only affect capabilities
    somebody deliberately put in `_REACHABLE`.
    """
    return frozenset({Source.CRAWL}) if observed.crawled else frozenset()


async def observed_sources(scope: CurrentScope) -> Observed:
    """Look at what this workspace has, once per request.

    A dependency, for the third time in this file and the same reason the other
    two give: `tests/test_dashboard_scope.py` asserts the permission lattice
    with no database, and reading this inside the handler turns those unit
    tests into integration tests. I tried it inline first and eleven of them
    failed on a missing `NEXUS_DATABASE_URL`, which is the lesson arriving for
    the third time.

    A dependency does resolve *before* the handler's four guards, so a caller
    who is about to get a 404 still costs one read. That is not the exposure it
    looks like: `scoped_connection` scopes the query to the caller's own
    workspace, so the read can only ever see what they were already entitled
    to — and `running_departments` and `answered_questions` have both worked
    this way since step C.
    """
    async with scoped_connection(scope) as db:
        # Two reads, one connection, once per request. Both feed every tile on
        # the page, so a per-tile read would be the same round trip to
        # `us-east-2` repeated for one answer.
        return Observed(
            crawl=await current_page_signals(db, scope),
            narrations=await current_narrations(db, scope),
        )


ObservedSources = Annotated[Observed, Depends(observed_sources)]


class OfferingOut(BaseModel):
    id: str
    """Doc 05's numbering, which is what the tile shows as its traceability
    label — `3.4` points at the paragraph that specified it."""

    key: str
    """The canonical capability id — `marketing.growth_planner`. The join to the
    question bank, the tool ledger and (later) the skill that narrates it. Both
    are here because they answer different questions: one traces the tile to a
    document, the other traces it to the rest of the system."""

    name: str
    shows: str
    state: str
    unlock: str
    """What this needs, in words. Empty only when nothing is missing."""
    needs: list[str]
    phase: int
    note: str


class NarrateIn(BaseModel):
    """What the client asks to have explained."""

    key: str
    """The canonical capability id — `marketing.seo_gaps`.

    Exactly the string the client was served as `BlockOut.key`, so nothing is
    derived and there is no second spelling of the same thing. Not a department
    plus a block name: the block key *is* the capability id, and two ways to
    name one thing is two ways to disagree about it.
    """


class NarrationOut(BaseModel):
    """A sentence, and enough to trace it."""

    prose: str
    narrated_at: str
    prompt_version: str
    """Which `SKILL.md` wrote it. Shown in the working drawer beside the
    calculator's `method`, so a disputed sentence traces to the instructions
    that produced it as readily as a disputed figure traces to its arithmetic."""


class NarrationResultOut(BaseModel):
    """What just happened, which is not the same question as what is true.

    The GET says what a tile holds; this says what one attempt did. That split
    is why no refusal reason is stored on `BlockOut` — a reason kept there
    would resurrect yesterday's "budget exhausted" on every page load, hours
    after the allowance reset.
    """

    key: str
    outcome: str
    reason: str
    """Empty unless `outcome` is `unavailable`."""

    message: str
    """Never empty, and always server-authored.

    `BlockCard` already states the rule for `unlock`: the sentence comes from
    the API so one wording change reaches every surface, and so a screen cannot
    ship with the space drawn and the copy forgotten. A reason-to-sentence map
    in the browser would be that failure with an extra step.
    """

    narration: NarrationOut | None = None
    generation_id: str
    """Empty when no row was written — which happens only when nothing ran."""

    measured_at: str
    """The figure this describes. The client compares it with the one it is
    showing: if the page was re-crawled between load and click, the sentence is
    about a number the reader cannot see."""


class CheckOut(BaseModel):
    """One observation and the points it contributed. Never a recommendation.

    `Check.evidence` is specified as what was *observed* rather than as advice,
    and this carries it through unrestated. A tile that turned "0 internal
    links" into "add internal links" would be giving guidance nobody computed.
    """

    id: str
    label: str
    passed: bool
    weight: int
    evidence: str


class FigureOut(BaseModel):
    """A computed figure, its denominator, and its working.

    **The denominator travels with the number** — `ShellOut`'s rule for
    `ShellOut`'s reason. A score on its own is a claim the reader cannot check;
    `45 out of 65` lets them count. `percentage` is served rather than divided
    in the browser so two clients cannot round differently from the drawer.

    **Not a view's shape.** No colour, no ordering, no formatting, no chip
    text. Every field is either the calculator's output or the provenance that
    makes it checkable — `label` and `measures` included, because what a number
    measures is a property of the calculation and not of the tile drawing it.
    """

    label: str
    """What was measured, from the calculator — **not** the capability's name.
    `3.7` is presented as "SEO Intelligence" and this measures its technical
    half."""

    measures: str
    """One sentence naming exactly what was counted, and what was not.

    The field that stops a correct number being read as an answer to a wider
    question than it is. `brand_intelligence` promises voice consistency;
    `score_brand` measures whether a first-time visitor can tell what you do.
    Both true, and only one of them is what the figure says.
    """

    score: int
    max_score: int
    percentage: int

    checks: list[CheckOut]
    checks_passed: int

    source_url: str
    """The page. A score whose page cannot be opened is a number nobody can
    check, which for a reader is the same as one we invented."""

    measured_at: str
    """When the page was fetched. Rendered beside the figure rather than in the
    drawer, because it stands in for the `stale` state this route deliberately
    does not reach — nothing re-crawls on a schedule, so passing `age_days`
    would make every audit read "out of date" a week after signup, for good."""

    method: str


class BlockOut(BaseModel):
    """One capability, as the rail renders it.

    Deliberately not `OfferingOut` with a field added. An offering is a row in
    `doc/05`; a block is a thing on a screen, and it carries the two facts an
    offering has no opinion about — which tab it is on and which of the nine
    components draws it.
    """

    key: str
    doc05_id: str
    name: str
    shows: str
    block: str
    state: str
    unlock: str
    needs: list[str]

    narration: NarrationOut | None = None
    """The stored sentence, when one still describes the figure above it.

    **A sibling of `figure`, not a field on it.** `FigureOut`'s own docstring
    says every field there is either the calculator's output or the provenance
    that makes it checkable; prose is neither — it is a model's output *about*
    that output, and nesting it would make the figure object partly generated,
    which is the conflation I1 exists to prevent. They also have different
    lifetimes: the figure is recomputed from the crawl on every page load, the
    sentence is stored and can be absent while the figure is present.

    **Absent rather than stale.** If the stored sentence describes an older
    measurement it is dropped, not labelled — to a reader, "superseded" and
    "never narrated" both render as the button, and surfacing the difference
    only invites showing it anyway.

    No refusal reason travels here either. This says what is true; the POST
    says what just happened. A reason kept on the tile would resurrect
    yesterday's "budget exhausted" on every page load.
    """

    figure: FigureOut | None = None
    """The computed number, when there is one.

    `None` for every capability nothing computes, which is still most of them.
    Optional rather than absent from the model so the TypeScript mirror can
    narrow on it — and **never a zero-valued object**, because a zero score
    says the website failed every check where the truth is that nobody has
    looked (I10). That case is `None` alongside a `locked` state.
    """


class FactOut(BaseModel):
    """One answer, read back with everything needed to check it."""

    key: str
    question: str
    answer: str
    answered_at: str
    reads_it: str
    """The capability that consumes this answer, in words. An answer whose
    consumer cannot be named is a form field (Q33), and this is where a founder
    can see that it is not."""


class WatchOut(BaseModel):
    """One stated risk, and what would confirm or refute it."""

    key: str
    label: str
    stated: str
    answered_at: str
    measured_by: str
    needs: str


class SectionOut(BaseModel):
    """One tab, with what is on it."""

    key: str
    label: str
    blocks: list[BlockOut]

    available: int
    """How many of this tab's blocks are not `planned`.

    The page opens on the first tab where this is non-zero. On a day-one
    dashboard that is Setup, because it is the only tab with content — and the
    alternative, always opening on Overview, would greet a new customer with
    five tiles that all say "not built yet"."""


class NotAskedOut(BaseModel):
    what: str
    source: str


class AssistantOut(BaseModel):
    """The reserved panel's honest empty state (Q67).

    It names the director and the questions it will answer rather than saying
    "coming soon": a reserved region that says what it will do is a preview of
    value, a blank one reads as a bug, and a fake one reads as a lie.
    """

    director: str
    questions: list[str]
    available: bool = False
    """False everywhere today. The panel is reserved, not built (P20)."""


class DirectorOut(BaseModel):
    department: str
    title: str
    remit: str
    scoreable: bool
    path: str
    offerings: list[OfferingOut]
    """The flat catalogue, kept while the web adopts `sections`. Two shapes of
    the same list, and the older one goes when nothing reads it."""

    sections: list[SectionOut]
    """The rail. Only tabs with something on them — `doc/08` draws five that no
    capability fills yet, and a tab somebody clicks into to find nothing is
    worse than a tab that is not there."""

    catalogue: list[BlockOut]
    not_asked: list[NotAskedOut]
    """`doc/08` §2B to §8B. The figures NEXUS refuses to ask for, and where each
    comes from instead — a product surface rather than an internal rule, and the
    highest-intent place in the application for a Connect button."""

    """Capabilities in this director's remit that `doc/08`'s cut has no section
    for (§11's deliberate gaps). Shown apart from the rail and labelled as
    planned, because they are neither locked nor coming."""

    assistant: AssistantOut


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
    """How many offerings across the whole product a person can actually open.

    Zero today. Counts `reachable` rather than `implemented`: two Marketing
    capabilities have a real calculation behind them and no route serving it,
    and counting those here would imply the page has something on it that it
    does not."""


def _path(department: Department) -> str:
    return f"/dashboard/{department.value}"


def _offering_out(offering: Offering, connected: frozenset[Source]) -> OfferingOut:
    return OfferingOut(
        id=offering.id,
        key=canonical_id(offering.id),
        name=offering.name,
        shows=offering.shows,
        state=state_for(offering, connected=connected, reachable=is_reachable(offering.id)).value,
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


class BriefItemOut(BaseModel):
    """One finding. Never a recommendation — ADR 0029."""

    kind: str
    headline: str
    """The check's own label, verbatim. The API does not negate it and neither
    should a client: "Page has a title" has no sensible negation, and the one
    that reads well for `seo.https` generalises to nothing."""

    detail: str
    """`Check.evidence` — what was observed."""

    cost: int
    check_id: str
    capability_id: str
    method: str


class BriefOut(BaseModel):
    """The morning brief, computed in code and costing nothing to render."""

    state: str
    """`findings`, `all_held` or `not_measured`. The third is **not** the second
    with zeroes in it: an audit that never ran must not read as one that found
    nothing (I10)."""

    items: list[BriefItemOut]
    message: str
    """Server-authored, never empty, for the reason `unlock` already gives — one
    wording change has to reach every surface."""

    points_held: int
    points_total: int
    checks_passed: int
    checks_total: int
    measured_on: str
    """Empty only when nothing was measured."""


class CoverageOut(BaseModel):
    """Where the product is for this company, split by who has to move next.

    ADR 0030. Three counts rather than a percentage: a percentage of "done"
    invites being read as a verdict on the business — the thing the composite
    score is refused for — and the three bands have genuinely different
    remedies, two of which are ours.
    """

    measuring: int
    reading_back: int
    """Reachable and not a measurement: the Setup and Watchlist tabs, which show
    a founder their own answers. Kept separate because doc 05 §0 requires that
    a number somebody typed and a number we measured never look alike."""

    not_built: int
    """Ours, not the customer's. No connection anybody makes switches one on,
    and saying so is what makes the other two numbers mean anything."""

    total: int
    """Tiles only — a `RULE` is not something a customer acquires. Shared with
    `completeness` and `openable_count`, and `test_coverage_bands.py` asserts
    all three agree rather than leaving three docstrings to."""


class OpenQuestionOut(BaseModel):
    """One question still open, and what answering it would change."""

    key: str
    department: str
    prompt: str
    """The bank's own wording — the question on the dashboard has to be the
    question the setup flow will ask."""

    why: str
    consumed_by: str
    consumer_name: str


class OpenQuestionsOut(BaseModel):
    """`doc/14` step 5. Questions only — what you *connect* is coverage's half.

    **Answering informs; it does not unlock.** Every fact-consuming tile also
    requires a source, so no question in the bank switches one on by itself.
    The split below is what makes that honest rather than merely stated:
    `changes_a_figure` moves a number already on the page, and the rest are
    waiting on us.
    """

    changes_a_figure: list[OpenQuestionOut]
    waiting_on_us: int
    """Counted rather than listed. A founder cannot act on these usefully
    today, and forty rows would bury the handful that can."""

    total: int


class DirectorRowOut(BaseModel):
    """One department, as the common surface summarises it.

    **The tab rail, demoted.** It used to gate a director page; here it is a
    row a founder reads past on the way to something else, and `path` is how
    they open it when they want to.
    """

    department: str
    label: str
    path: str
    measuring: int
    """Capabilities in this department producing a figure today."""

    unanswered: int
    state: str
    """`measuring`, `answerable`, `waiting` or `empty` — four, because each has
    a different sentence and a state whose sentence is wrong is worse than no
    row. `empty` is the one `doc/14` left open: a department where nothing
    computes, nothing is asked, and nothing is coming."""

    line: str
    """Server-authored, never empty — the same rule `unlock` follows."""


class SurfaceOut(BaseModel):
    """Everything the common surface needs, in one response.

    Separate from `GET /dashboards` on purpose. The shell fetches that on every
    signed-in page to draw its navigation, and folding the brief into it would
    compute an audit for somebody sitting in Settings. This is the Today page's
    own payload and is fetched only there.
    """

    brief: BriefOut
    coverage: CoverageOut
    questions: OpenQuestionsOut
    directors: list[DirectorRowOut]
    measured: list[BlockOut]
    """The tiles that carry a figure, served exactly as the director page serves
    them — same `figure_out`, same `narration_out`, same stored sentence. The
    surface changes where a founder reads a number, never what it says."""


def figure_out(capability: Capability, snapshot: CrawlSnapshot | None) -> FigureOut | None:
    """The computed figure for one capability, or `None` when nothing scores it.

    **Module level, and shared by every route that serves a tile.** This was
    a closure inside the director handler, and `doc/14` step 7 puts the same
    tiles on the common surface — two copies would be two ways to render one
    number, which is the disagreement the grounding layer exists to prevent.
    `test_surface_tiles.py` asserts both routes serve an identical figure for
    an identical capability.
    """
    if snapshot is None:
        return None
    computation = compute_from_crawl(capability.id, snapshot)
    if computation is None:
        return None
    return FigureOut(
        label=computation.label,
        measures=computation.measures,
        score=computation.score.score,
        max_score=computation.score.max_score,
        percentage=computation.score.percentage,
        checks=[
            CheckOut(
                id=check.id,
                label=check.label,
                passed=check.passed,
                weight=check.weight,
                evidence=check.evidence,
            )
            for check in computation.score.checks
        ],
        checks_passed=computation.checks_passed,
        source_url=computation.source_url,
        measured_at=computation.measured_at.date().isoformat(),
        method=str(computation.trace["method"]),
    )


def narration_out(
    capability: Capability,
    snapshot: CrawlSnapshot | None,
    narrations: dict[str, StoredNarration],
) -> NarrationOut | None:
    """The stored sentence, if it still describes what the tile now shows.

    `describes` compares five fields of the stored trace against the live
    computation — numerator, denominator, percentage, page and window — and
    all five must match. The one that catches what nothing else does is
    `window`: a re-crawl the next day with an identical score leaves every
    number matching and the date wrong, and the prose may cite the date.

    A mismatch logs rather than renders, so the rate is observable without
    anybody having to notice a missing sentence.
    """
    stored = narrations.get(capability.id)
    if stored is None or snapshot is None:
        return None

    computation = compute_from_crawl(capability.id, snapshot)
    if computation is None:
        return None

    if not describes(stored, computation):
        log.info(
            "dashboard.narration_superseded",
            capability=capability.id,
            narrated_at=stored.narrated_at.isoformat(),
        )
        return None

    return NarrationOut(
        prose=stored.prose,
        narrated_at=stored.narrated_at.date().isoformat(),
        prompt_version=stored.prompt_version,
    )


def _measured_block(
    capability: Capability, snapshot: CrawlSnapshot | None, observed: Observed
) -> BlockOut:
    """One tile for the common surface, built the way the director page builds it.

    Shares `figure_out` and `narration_out` rather than reimplementing them, so
    the two surfaces cannot disagree about a number or about whether a stored
    sentence still describes it.
    """
    connected = connected_sources(observed)
    return BlockOut(
        key=capability.id,
        doc05_id=capability.doc05_id,
        name=capability.name,
        shows=capability.shows,
        block=capability.block.value if capability.block else "",
        state=state_from_sources(
            capability.required_sources, connected=connected, reachable=capability.reachable
        ).value,
        unlock=unlock_for_sources(capability.required_sources, connected=connected),
        needs=[source.value for source in capability.required_sources],
        figure=figure_out(capability, snapshot),
        narration=narration_out(capability, snapshot, observed.narrations),
    )


@router.get("/surface", response_model=SurfaceOut)
async def command_surface(
    scope: CurrentScope,
    chosen: RunningDepartments,
    answered: AnsweredQuestions,
    observed: ObservedSources,
) -> SurfaceOut:
    """The common surface — one page, composed from what this reader can see.

    **Declared before `/{department}`**, or FastAPI matches `surface` as a
    department name and every request 404s on an unknown enum. The other static
    sibling, `/company`, sits above the same wildcard for the same reason.

    ## Scoped by the same two filters as the nav

    Which departments the *company runs* and which the *caller may reach* —
    identical to `list_dashboards`, deliberately. A brief that surfaced a
    finding from a department the left panel does not list would be a
    disclosure by a different route, and ADR 0029 makes this composition
    scoped from day one precisely so the first department-scoped finding does
    not become one silently.

    ## No model, no ledger row, no cost

    `compose` is pure and the figures come from `calculators/`. There is
    nothing here to refuse, nothing to bill, and nothing that behaves
    differently with an API key absent (ADR 0011).
    """
    departments = frozenset(
        d.department
        for d in DIRECTORS
        if _reachable(scope, d) and runs_department(chosen, d.department)
    )
    mine = frozenset(
        c.id for c in TILES if c.department in departments and c.reachable and computes(c.id)
    )

    snapshot = observed.crawl
    computations = (
        ()
        if snapshot is None
        else tuple(
            computation
            for capability_id in sorted(mine)
            if (computation := compute_from_crawl(capability_id, snapshot)) is not None
        )
    )

    bands = coverage(frozenset(CRAWL_AUDITS), departments)
    brief = compose(computations, expected=mine, unobserved=bands.not_built)
    # `mine` rather than every capability with a calculator: a question is only
    # in the first tier if its consumer produces a figure **this reader can
    # see**, which is the same scoping the brief and the nav apply.
    open_questions = compose_questions(
        bank=QUESTIONS_BY_DEPARTMENT,
        departments=departments,
        answered=answered,
        measuring=mine,
    )

    outstanding = {
        department: sum(
            1
            for question in QUESTIONS_BY_DEPARTMENT.get(department, ())
            if (department.value, question.key) not in answered
        )
        for department in departments
    }

    return SurfaceOut(
        measured=[
            block
            for block in (
                _measured_block(BY_ID[capability_id], snapshot, observed)
                for capability_id in sorted(mine)
            )
            # A capability that should compute and did not is already reported
            # by the brief as `unmeasured`. An empty tile here would say the
            # same absence a second time, in a shape that looks like a figure.
            if block.figure is not None
        ],
        directors=[
            DirectorRowOut(
                department=row.department.value,
                label=label_for(row.department),
                path=_path(row.department),
                measuring=row.measuring,
                unanswered=row.unanswered,
                state=row.state.value,
                line=row.line,
            )
            for row in compose_rows(
                departments=departments,
                measuring=mine,
                unanswered=outstanding,
                # The display name, so the ordering matches what a reader sees.
                # `hr` renders as "People", and sorting on the enum value put it
                # between Finance and Marketing.
                label=label_for,
            )
        ],
        questions=OpenQuestionsOut(
            changes_a_figure=[
                OpenQuestionOut(
                    key=question.key,
                    department=question.department,
                    prompt=question.prompt,
                    why=question.why,
                    consumed_by=question.consumed_by,
                    consumer_name=question.consumer_name,
                )
                for question in open_questions.changes_a_figure
            ],
            waiting_on_us=open_questions.waiting_on_us,
            total=open_questions.total,
        ),
        coverage=CoverageOut(
            measuring=bands.measuring,
            reading_back=bands.reading_back,
            not_built=bands.not_built,
            total=bands.total,
        ),
        brief=BriefOut(
            state=brief.state.value,
            items=[
                BriefItemOut(
                    kind=item.kind.value,
                    headline=item.headline,
                    detail=item.detail,
                    cost=item.cost,
                    check_id=item.check_id,
                    capability_id=item.capability_id,
                    method=item.method,
                )
                for item in brief.items
            ],
            message=brief.message,
            points_held=brief.points_held,
            points_total=brief.points_total,
            checks_passed=brief.checks_passed,
            checks_total=brief.checks_total,
            measured_on=brief.measured_on,
        ),
    )


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
        delivered_count=openable_count(),
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
    scope: CurrentScope,
    chosen: RunningDepartments,
    answered: AnsweredQuestions,
    observed: ObservedSources,
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
    connected = connected_sources(observed)

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
                1
                for o in d.offerings
                if state_for(o, connected=connected, reachable=is_reachable(o.id)).value
                == "planned"
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


def _facts_for(department: Department, context: CompanyContext) -> list[FactOut]:
    """The department's answers, joined to the questions that produced them.

    Only answers that are **bound** reach here — a Contributor's proposal waits
    for a manager at the review gate (Q31/D22), and quoting one back as "what
    you told us" would present one person's suggestion as the department's
    position.

    An answer with no question in the bank is skipped rather than shown with a
    blank prompt. That happens when a question is cut: the row survives and the
    thing that gives it meaning does not.
    """
    prompts = {question.key: question for question in QUESTIONS_BY_DEPARTMENT.get(department, ())}
    return [
        FactOut(
            key=fact.key,
            question=prompts[fact.key].prompt,
            answer=fact.value,
            answered_at=fact.answered_at,
            reads_it=prompts[fact.key].consumed_by,
        )
        for fact in context.department_facts.get(department.value, ())
        if fact.key in prompts
    ]


def _watch_for(department: Department, context: CompanyContext) -> list[WatchOut]:
    """The stated risks this department named, with what will test them.

    Empty until the question is answered — a watch card for a risk nobody
    described would be the product inventing a worry. Sales and Finance have
    none at all, and that is a property of their questions rather than an
    oversight: every one of theirs is a threshold or a definition.
    """
    answers = {fact.key: fact for fact in context.department_facts.get(department.value, ())}
    return [
        WatchOut(
            key=item.question_key,
            label=item.label,
            stated=answers[item.question_key].value,
            answered_at=answers[item.question_key].answered_at,
            measured_by=item.measured_by,
            needs=item.needs,
        )
        for item in WATCH_ITEMS
        if item.department is department and item.question_key in answers
    ]


async def reachable_director(
    department: Department, scope: CurrentScope, chosen: RunningDepartments
) -> Director:
    """The four refusals that gate every director surface, in one place.

    **Written twice before this existed** — in `director_dashboard` and
    `director_setup` — and already drifting: the two copies differed by a
    comment, which is how the next pair differs by a check. Slice 2 would have
    made it three copies. A permission check duplicated per route is one that
    diverges per route, and one handler refusing where another admits is the
    shape of a leak rather than a cosmetic bug.

    Extracted **before** the narration endpoint was written, so that route
    could not be what introduced a divergence; the proof that nothing moved is
    that `test_dashboard_scope.py` and `test_api_scope_enforcement.py` are
    unchanged.

    The order is the one both copies used, and each step answers a different
    question:

    1. **Is this a director at all?** 404 — an unknown department is not a
       thing you may not see, it is a thing that does not exist.
    2. **Is it the executive surface, and may this caller see it?** 403 *with a
       sentence*, because the Chief of Staff page is not a department somebody
       could be added to, so naming the requirement is safe and useful.
    3. **Does the caller hold this department?** `enforce_department`, which
       404s rather than 403s — a department you do not hold must not be
       distinguishable from one that does not exist.
    4. **Does the company run it?** Finding #21: an owner holds all seven while
       running only the ones chosen at stage 4, and without this the list and
       the detail disagreed — `GET /dashboards` omitted People while
       `GET /dashboards/hr` served it. An empty `chosen` means the company has
       not chosen yet, which reads as "show everything" in both places.
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

    if not runs_department(chosen, director.department):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")

    return director


ReachableDirector = Annotated[Director, Depends(reachable_director)]


@router.get("/{department}", response_model=DirectorOut)
async def director_dashboard(
    director: ReachableDirector,
    scope: CurrentScope,
    observed: ObservedSources,
) -> DirectorOut:
    """One director's page.

    `enforce_department` is what refuses a department the caller does not hold,
    and it 404s. The executive check is separate because it is a different rule
    with a different answer: the Chief of Staff page is not a department someone
    might be added to, so naming the requirement is safe and useful.
    """
    # **One read per request, not one per tile.** Both audited capabilities
    # score the same page, so a per-tile read would be the same round trip to
    # `us-east-2` twice for one answer — the shape `director_setup` already
    # uses: read once, then shape purely.
    snapshot = observed.crawl
    connected = connected_sources(observed)
    tiles = [
        capability
        for capability in capabilities_for(director.department)
        if capability.kind is CapabilityKind.TILE
    ]

    def block_out(capability: Capability) -> BlockOut:
        state = state_from_sources(
            capability.required_sources,
            connected=connected,
            reachable=capability.reachable,
        )
        return BlockOut(
            key=capability.id,
            doc05_id=capability.doc05_id,
            name=capability.name,
            shows=capability.shows,
            # Non-null for every tile, and the registry refuses to build
            # otherwise — so this is a type narrowing rather than a default.
            block=capability.block.value if capability.block else "",
            state=state.value,
            unlock=unlock_for_sources(capability.required_sources, connected=connected),
            needs=[source.value for source in capability.required_sources],
            figure=figure_out(capability, snapshot),
            narration=narration_out(capability, snapshot, observed.narrations),
        )

    def section_out(section: Section) -> SectionOut:
        blocks = [block_out(c) for c in tiles if c.section == section.key]
        return SectionOut(
            key=section.key,
            label=section.label,
            blocks=blocks,
            available=sum(1 for block in blocks if block.state != "planned"),
        )

    return DirectorOut(
        department=director.department.value,
        title=director.title,
        remit=director.remit,
        scoreable=director.scoreable,
        path=_path(director.department),
        offerings=[_offering_out(offering, connected) for offering in director.offerings],
        not_asked=[
            NotAskedOut(what=entry.what, source=entry.source)
            for entry in NOT_ASKED.get(director.department, ())
        ],
        sections=[
            section_out(section)
            for section in sections_for(director.department)
            # A tab with nothing on it is not rendered. `EMPTY_SECTIONS` names
            # the five and `test_sections.py` holds the list, so this filter is
            # the consequence of a known gap rather than a silent skip.
            if any(c.section == section.key for c in tiles)
        ],
        catalogue=[block_out(c) for c in tiles if not c.section],
        assistant=AssistantOut(
            director=director.title,
            questions=list(ASSISTANT_QUESTIONS.get(director.department, ())),
        ),
    )


class SetupOut(BaseModel):
    """What the Setup and Watchlist tabs render.

    **Its own endpoint, not part of the director payload.** The rail is served
    without touching the database beyond what it already reads; this costs a
    context assembly, and most visits to a director page never open Setup.
    Finding #23 is that `GET /dashboards` already spends 25 to 30 round trips, and
    the fix for that is not to add four more to every page load.
    """

    department: str
    facts: list[FactOut]
    watch: list[WatchOut]


_NARRATED_MESSAGE: Final = "Written from the figure above and nothing else."
"""What a success says. Short, because the sentence itself is the answer and
this is the label on it."""


def _narratable(key: str, director: Director) -> Capability:
    """The capability this caller may have narrated, or a 404.

    **Six checks, all before `narrate` sees the id**, because
    `answer.narrate` does `BY_ID[capability_id]` and raises a bare `KeyError`
    on a miss — deliberately, per its own docstring, which makes an unvalidated
    id a 500 on a typo.

    404 rather than 422 throughout. The client only ever gets keys from a
    payload it just fetched, so any other value is a typo or a probe, and this
    file's standing rule is that "this exists and you may not have it" is itself
    a disclosure.
    """
    capability: Capability | None = BY_ID.get(key)
    if capability is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")

    # **The check with no precedent anywhere else in this codebase**, because
    # no other route takes a capability id from the caller. `reachable_director`
    # proved they may open *this* department; without this, a Marketing-only
    # manager posts `finance.runway_alert` to `/dashboards/marketing/narrate`
    # and has Finance narrated under a Marketing permission.
    if capability.department is not director.department:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")

    if capability.kind is not CapabilityKind.TILE:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")

    # Nothing computes it, so there is no number to explain. Asking a model to
    # account for a figure that does not exist is how a plausible one gets
    # written.
    if not computes(capability.id) or not capability.reachable:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")

    # **There is deliberately no check on `consumes_facts` here**, and the
    # first draft of this function had one — which would have refused
    # `marketing.seo_gaps`, the tile the whole slice exists for, because it
    # consumes `arabic_in_scope` (a `Scope.L3_DEPARTMENT` fact).
    #
    # Consuming a department fact is not what would make a workspace-wide
    # read-back unsafe. Two narrower things guarantee that, and both are
    # asserted rather than assumed:
    #
    #   `narrate` sends the model six grounding keys — label, value, unit,
    #   window, sources, delta — and **not one of them is a fact**, so the
    #   prose cannot contain a value the model was never shown
    #   (`test_grounding_compute.py::test_the_narrator_is_never_given_a_fact_value`).
    #
    #   The consumed fact lands in `input_snapshot`, and
    #   `retrieval/narration.py` **never selects that column**
    #   (`test_narration_isolation.py::test_the_reader_never_selects_the_input_snapshot`).
    #
    # Refusing on `consumes_facts` would have been a guard aimed at the wrong
    # thing, disabling a working feature while leaving the actual exposure —
    # a future reader that does select the snapshot — untouched.
    return capability


@router.get("/{department}/setup", response_model=SetupOut)
async def director_setup(director: ReachableDirector, scope: CurrentScope) -> SetupOut:
    """The department's own answers, and the risks it named.

    **The same refusals as the director page, because they are literally the
    same code** — `reachable_director`. They used to be a second copy here, on
    the argument that "a caller who cannot open Finance must not be able to
    read Finance's answers through a second door", which is right and is
    exactly why the check should not have been duplicated to say it.

    Read through `grounding.context.assemble`, which is the single path (P14).
    A query of this route's own would be the second context the assembler exists
    to prevent: the one that forgets the superseded-fact filter and quotes last
    month's answer beside this month's.
    """
    async with scoped_connection(scope) as db:
        context = await assemble(db, scope)

    return SetupOut(
        department=director.department.value,
        facts=_facts_for(director.department, context),
        watch=_watch_for(director.department, context),
    )


@router.post(
    "/{department}/narrate",
    response_model=NarrationResultOut,
    dependencies=[Depends(require_csrf)],
)
async def narrate_block(
    body: NarrateIn,
    director: ReachableDirector,
    scope: CurrentScope,
    observed: ObservedSources,
    settings: Annotated[Settings, Depends(get_settings)],
) -> NarrationResultOut:
    """Put a sentence around a figure this tile already shows.

    **A button, not a page load.** `director_dashboard` makes no model call and
    must not start: a key-less deployment is a *supported* state (ADR 0011), so
    a model on the render path would turn a computable 45/65 into `unavailable`
    for a whole page, and a founder reloading would spend their daily allowance
    on prose they did not ask for. Here the spend is attributable to somebody
    who pressed something.

    **No `_require_model()` gate**, unlike `routes/onboarding_agent.py`. That
    pattern exists because guided onboarding *requires* a model. A tile does
    not: with no key, `narrate` catches `LlmUnavailableError`, writes its row
    and returns `MODEL_UNAVAILABLE`, and the tile says so beside a figure that
    never needed one. A 503 here would turn a documented configuration into an
    outage on the one screen where somebody is deciding whether to trust us.

    **No new quota.** `Budgets.exhausted` already binds, is counted from the
    rows in the workspace's own reporting timezone, and returns a named reason.
    A per-tile counter would be a second source of truth about spending, which
    `ledger.py` refuses on principle.
    """
    capability = _narratable(body.key, director)

    # No crawl is an answer, and a 200 carrying it. A 4xx would push the client
    # into an error path and tempt it to render something of its own, when the
    # tile already has the specific sentence: "Needs a read of your website."
    #
    # And no `generation` row: the rule that every refusal is recorded governs
    # answers we *attempted*. Nothing ran here, and a row for a calculation
    # that never happened is noise in the table the ledger exists to keep
    # readable.
    snapshot = observed.crawl
    if snapshot is None:
        return NarrationResultOut(
            key=capability.id,
            outcome=Outcome.UNAVAILABLE.value,
            reason=UnavailableReason.MISSING_INPUT.value,
            message=unlock_for_sources(capability.required_sources, connected=frozenset())
            or sentence_for(UnavailableReason.MISSING_INPUT),
            generation_id="",
            measured_at="",
        )

    computation = compute_from_crawl(capability.id, snapshot)
    if computation is None:  # pragma: no cover - `_narratable` already refused it
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")

    runner = SkillRunner(get_provider(), hooks=get_hooks(), workspace_id=str(scope.workspace_id))

    async with scoped_connection(scope) as db:
        context = await assemble(db, scope)
        result = await narrate(
            db,
            scope,
            capability_id=capability.id,
            context=context,
            computed=computation.computed,
            trace=computation.trace,
            runner=runner,
            settings=settings,
        )
        # The ledger row is written inside this transaction and committed with
        # it, so the answer and its provenance are one fact — `ledger.record`
        # declines to commit for exactly that reason.
        await db.commit()

    answer = result.answer
    narrated = (
        NarrationOut(
            prose=answer.prose,
            narrated_at=datetime.now(UTC).date().isoformat(),
            prompt_version=runner.registry.get(NARRATOR).version,
        )
        if result.answered
        else None
    )

    return NarrationResultOut(
        key=capability.id,
        outcome=answer.outcome.value,
        reason=answer.reason.value if answer.reason else "",
        message=(
            _NARRATED_MESSAGE
            if result.answered
            else sentence_for(answer.reason)
            if answer.reason
            else sentence_for(UnavailableReason.SCHEMA_INVALID)
        ),
        narration=narrated,
        generation_id=str(result.generation_id),
        measured_at=computation.measured_at.date().isoformat(),
    )
