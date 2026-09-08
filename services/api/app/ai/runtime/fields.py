"""The declared field catalogue: what a skill is allowed to write, and at what scope.

This file is the answer to the objection ADR 0019 raised against generated
questions. That ADR blocked them because "a generated question has no scope tag,
so its answer has nowhere honest to go" — and it was right about the failure, not
about the only possible fix.

The fix here is to invert where the tag comes from. A generated question does not
carry a scope tag *of its own*; it must **name a field from this catalogue**, and
the field carries the tag. `question-generation` returns `{question, target}` and
the runtime rejects any turn whose `target` is not a key below — before the
question is ever put to a person. So the model chooses the wording, the ordering
and the follow-up, and the sensitivity of the answer is still decided in
deterministic code that a reviewer can read in one screen.

Two consequences worth stating, because both are load-bearing:

**A question the catalogue cannot express cannot be asked.** That is the point.
Adding a field is a deliberate edit to this file with a scope on it, not a
side-effect of a model deciding a new topic is interesting.

**Persona fields never widen access.** `doc/06` §2.6: "No persona field is ever an
input to the retrieval predicate." Everything below with `kind=PERSONA` is
presentation preference, stored at L5, and `assert_persona_is_not_authorisation()`
fails the import if a role-shaped key is ever added. `persona_chat.py` expresses
the same rule as `never_asked`; this expresses it as a type the runtime enforces.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum

from app.logging import get_logger

log = get_logger(__name__)


class FieldKind(StrEnum):
    BRAIN = "brain"
    """A column on `company_brain` (migration 0019)."""

    PERSONA = "persona"
    """A column on `persona` (migration 0002). Presentation preference only."""

    FACT = "fact"
    """A row in the fact layer (migration 0022), keyed by `key`.

    Department rules — approval thresholds, stale-deal windows, lead-time
    promises — land here rather than on the brain, because they are scoped per
    department and the brain is a workspace-wide artefact.
    """


class AnswerShape(StrEnum):
    """The *form* a field's answer takes, when it has a recognisable one.

    This exists to catch a specific defect: a question whose wording cannot
    possibly elicit the field it is bound to. The architecture's central promise
    is that binding an answer to a declared field makes it "a cited fact rather
    than loose text" — but nothing checked that the *question* matched the
    field's intent, so when it did not, the wrong meaning was stored with full
    provenance and downstream agents read it as authoritative.

    Three cases from an audit of seven interviews, all still reachable after the
    catalogue was narrowed by department, because each is the *right* department
    and the wrong field inside it:

    - `runway_alarm` means "how many months of runway would change your plans".
      It was asked "what's the gap that causes the most friction right now?" —
      so a free-text complaint was stored as a runway threshold. The next
      question then said "when you hit that nine-month runway threshold",
      attributing to the person a number she had never given.
    - `brain.competitors` means "who you actually lose to". It was asked about
      channel economics.
    - `distrusted_number` means "a figure they do not currently believe". It was
      asked "what slows you down".

    A shape is a much weaker claim than "does this question mean the same as
    this intent", and deliberately so — it is checkable without a second model
    call. `PROSE` is the default and is never checked: you cannot structurally
    mismatch a prose question against a prose field.
    """

    DURATION = "duration"
    """A length of time — days, hours, months, a cadence."""

    AMOUNT = "amount"
    """A quantity or threshold, usually money."""

    NAME = "name"
    """Names a party: a person, a team, a competitor, a supplier."""

    METRIC = "metric"
    """Names a figure or a report, rather than describing one."""

    PROSE = "prose"
    """No recognisable form. Never checked."""


@dataclass(frozen=True, slots=True)
class FieldSpec:
    key: str
    kind: FieldKind
    scope: int
    """L1 public · L2 company internal · L3 department · L4 restricted · L5 personal.

    The answer is stored at this sensitivity. It is not negotiable by the model,
    and it is not derived from the question's wording.
    """

    label: str
    intent: str
    """What this field is for, in the words the model is shown. This is the only
    part of a field the prompt sees — the scope is deliberately not exposed, so a
    model cannot reason about how to get an answer stored more permissively."""

    column: str | None = None
    """The `company_brain` / `persona` column, when `kind` is not FACT."""

    department: str | None = None
    """For FACT fields, which department's catalogue this belongs to."""

    answer_shape: AnswerShape = AnswerShape.PROSE
    """The form the answer takes. See `AnswerShape` and `question_elicits`."""

    question_key: str = ""
    """The `question_bank` key this field answers, when one exists.

    **Two surfaces collect the same facts and neither knew about the other.**
    The agent interview writes catalogue keys into `fact`; the department block
    (`question_bank`, Phase 7) writes bank keys into `onboarding_answer`; and
    the dashboard's "questions still unanswered" counter reads only the second.
    So a Head of Operations could answer every operational threshold in the
    interview and still be told five questions were outstanding — three rounds
    of work on *which* questions to ask, invisible to the person who answered
    them.

    Held here rather than in a mapping table beside either surface, because a
    separate table is a third thing to keep in step with two that already drift.
    Empty means the bank has no equivalent: `payment_terms` and `quota_period`
    are bank questions with no catalogue field, and they stay outstanding until
    somebody answers the block — which is correct, nothing has answered them.
    """

    fallback_question: str = ""
    """Hand-written wording, used when the model cannot produce acceptable wording.

    **This exists because validation without a fallback is worse than no
    validation.** Narrowing the catalogue by department and checking that a
    question can elicit its field removed cross-department leakage entirely —
    and then three of six audited interviews ended early because the two gates
    share one rejection budget. One department, Operations, was asked *nothing*
    and still completed onboarding. A blank interview is a worse outcome than
    the mismatches the gates were added to prevent.

    So exhausting the retries now serves this instead of closing the interview.
    Most are lifted verbatim from `domain/question_bank.py`, which has held
    hand-written, department-correct wording since Phase 7; the rest are written
    to the same standard — one clause, one answer, no compound.

    `test_every_fallback_question_passes_its_own_gates` asserts that none of
    these can be rejected by the very checks they are the fallback for, which is
    the property that makes this safe: the floor cannot itself fall through.

    Empty means no fallback, and therefore never served this way. That is
    correct for the fields a crawl answers.
    """

    only_you_know: bool = True
    """False for anything a crawl or a connector could answer.

    The onboarding agent is told never to ask a question whose field is
    `only_you_know=False` — those are filled by `company-research` or by a
    connector, and asking would be asking someone to read their own systems out
    loud. `unaskable_fields()` is what the agent filters on.
    """


def _f(*args: object, **kwargs: object) -> FieldSpec:
    return FieldSpec(*args, **kwargs)  # type: ignore[arg-type]


_SPECS: tuple[FieldSpec, ...] = (
    # ── Company Brain ─────────────────────────────────────────
    # Columns are the real ones from migration 0019, so a value written here has
    # somewhere to go without a translation layer inventing a mapping.
    FieldSpec("brain.profile", FieldKind.BRAIN, 1, "Company profile",
              "What the business does, who it serves, where it operates.",
              column="profile", only_you_know=False),
    FieldSpec("brain.products_services", FieldKind.BRAIN, 1, "Products & services",
              "What the company sells or delivers.",
              column="products_services", only_you_know=False),
    FieldSpec("brain.target_customers", FieldKind.BRAIN, 2, "Target customers",
              "Who actually buys, described the way the company describes them.",
              column="target_customers",
              fallback_question='Who actually buys from you?'),
    FieldSpec("brain.brand_voice", FieldKind.BRAIN, 1, "Brand voice",
              "How the company writes and presents itself.",
              column="brand_voice", only_you_know=False),
    FieldSpec("brain.goals", FieldKind.BRAIN, 2, "Goals this year",
              "What would make the next twelve months a success.",
              column="goals",
              fallback_question='What would make the next twelve months a success?'),
    # L2, not L1. The intent is "who the company actually *loses* to" — never
    # public information, whatever the marketing site lists. The audit caught
    # this field holding "Meta prospecting is the worst — CAC is around 62
    # dollars" and a consultancy naming the firms it loses board relationships
    # to, both stored at "Company public".
    FieldSpec("brain.competitors", FieldKind.BRAIN, 2, "Competitors",
              "Who the company actually loses to, in their own words.",
              column="competitors",
              answer_shape=AnswerShape.NAME,
              fallback_question='Who do you most often lose to?'),
    FieldSpec("brain.assumptions", FieldKind.BRAIN, 2, "Assumptions",
              "Something proceeded on without confirmation, held for review.",
              column="assumptions",
              fallback_question='What are you assuming that you have not yet proven?'),

    # ── Persona — presentation preference, L5, never authorisation ──
    FieldSpec("persona.stated_purpose", FieldKind.PERSONA, 5, "Why you are here",
              "What the person wants this product to do for them.",
              column="stated_purpose",
              # The opening question, and the only one the model does not word.
              # `/discovery` writes it into the transcript as the agent turn the
              # first answer replies to. `AgentOnboarding.tsx` renders the same
              # string on the client, and `test_the_opening_question_is_worded
              # _once` reads the .tsx to prove the two have not drifted.
              fallback_question='What are you responsible for, day to day?'),
    FieldSpec("persona.priority_topics", FieldKind.PERSONA, 5, "Wants first",
              "What they want surfaced before anything else.",
              column="priority_topics",
              fallback_question='What should your workspace surface before anything else?'),
    FieldSpec("persona.communication_style", FieldKind.PERSONA, 5, "Detail level",
              "How much detail, and how they want to be interrupted.",
              column="communication_style",
              # One question, not two. "…and when should you be interrupted?" is a
              # second interrogative and `is_compound` rightly rejects it — the
              # field's intent covers both, but a question may only ask one.
              fallback_question='How much detail do you want in what you are shown?'),
    FieldSpec("persona.language", FieldKind.PERSONA, 5, "Language",
              "Preferred language for generated content.",
              column="language",
              fallback_question='Which language should generated content be written in?'),
    FieldSpec("persona.timezone", FieldKind.PERSONA, 5, "Timezone",
              "Used for scheduling and for what 'today' means.",
              column="timezone", only_you_know=False),
    FieldSpec("persona.default_landing_screen", FieldKind.PERSONA, 5, "Opens on",
              "Which screen they should land on.",
              column="default_landing_screen",
              fallback_question='Which screen should you land on?'),

    # ── Department rules → the fact layer ─────────────────────
    # L3 because each is meaningful only inside its department, and because a
    # Contributor reading their own rows must not see another department's.
    FieldSpec("fact.finance.approval_threshold", FieldKind.FACT, 3,
              "Spend approval threshold",
              "The amount above which spend needs sign-off.", department="finance",
              answer_shape=AnswerShape.AMOUNT,
              fallback_question='Above what amount does spend need approval?',
              question_key='approval_threshold'),
    FieldSpec("fact.finance.approver", FieldKind.FACT, 3, "Who approves spend",
              "Who signs off spend above the threshold.", department="finance",
              answer_shape=AnswerShape.NAME,
              fallback_question='Who approves spend above that?',
              question_key='approver'),
    FieldSpec("fact.finance.runway_alarm", FieldKind.FACT, 3, "Runway alarm",
              "How many months of runway would change their plans.", department="finance",
              answer_shape=AnswerShape.DURATION,
              fallback_question='How many months of runway would worry you?',
              question_key='runway_alert_months'),
    FieldSpec("fact.sales.pipeline_stages", FieldKind.FACT, 3, "Pipeline stages",
              "The stages a deal moves through, in order, in their words.", department="sales",
              fallback_question='What are your pipeline stages, in order?',
              question_key='pipeline_stages'),
    FieldSpec("fact.sales.stale_days", FieldKind.FACT, 3, "A deal is stale after",
              "How long silence means a deal needs attention.", department="sales",
              answer_shape=AnswerShape.DURATION,
              fallback_question='After how many days of silence should a deal be flagged?',
              question_key='stale_deal_days'),
    FieldSpec("fact.sales.disqualifier", FieldKind.FACT, 3, "What kills a deal",
              "What disqualifies a deal outright.", department="sales",
              fallback_question='What disqualifies a deal outright?',
              question_key='disqualifiers'),
    FieldSpec("fact.operations.lead_time", FieldKind.FACT, 3, "Promised lead time",
              "What the company promises customers, not the best case.", department="operations",
              answer_shape=AnswerShape.DURATION,
              fallback_question='What do you promise customers as a lead time?',
              question_key='promised_lead_time'),
    FieldSpec("fact.operations.late_rule", FieldKind.FACT, 3, "When an order is late",
              "The point at which an order counts as late.", department="operations",
              answer_shape=AnswerShape.DURATION,
              fallback_question='At what point is an order officially late?',
              question_key='late_definition'),
    FieldSpec("fact.operations.supplier_risk", FieldKind.FACT, 3, "Supplier concentration",
              "Which supplier they could not replace quickly.", department="operations",
              answer_shape=AnswerShape.NAME,
              fallback_question='Which supplier are you most exposed to?',
              question_key='supplier_concentration'),
    FieldSpec("fact.marketing.lead_definition", FieldKind.FACT, 3, "What counts as a lead",
              "The definition every marketing number downstream depends on.",
              department="marketing",
              fallback_question='What counts as a lead worth passing to Sales?',
              question_key='lead_definition'),
    FieldSpec("fact.marketing.channels", FieldKind.FACT, 3, "Active channels",
              "Which acquisition channels they actually run.", department="marketing",
              fallback_question='Which channels do you actively run?',
              question_key='active_channels'),
    # ── People ────────────────────────────────────────────────
    # Four askable fields where there was one. Every entry below is lifted from
    # `domain/question_bank.py`, which has held well-worded, department-correct
    # People and Strategy questions since Phase 7 — with no catalogue field to
    # bind them to, so the agent could not ask any of them. The audit found the
    # consequence: a Head of People was asked what disqualifies a sales deal,
    # and zero HR fields were reached in the whole run.
    FieldSpec("fact.hr.leave_basis", FieldKind.FACT, 3, "Leave basis",
              "Whether leave accrues monthly or is granted annually.", department="hr",
              fallback_question='Is leave accrued monthly or granted annually?',
              question_key='leave_accrual'),
    FieldSpec("fact.hr.hire_approver", FieldKind.FACT, 3, "Who approves a hire",
              "Where a request for a new role routes for sign-off.", department="hr",
              answer_shape=AnswerShape.NAME,
              fallback_question='Who signs off a new hire?',
              question_key='hire_signoff'),
    FieldSpec("fact.hr.review_cycle", FieldKind.FACT, 3, "Review cycle",
              "How often performance reviews happen, and when the next one falls.",
              department="hr",
              answer_shape=AnswerShape.DURATION,
              fallback_question='How often do performance reviews happen?',
              question_key='review_cycle'),
    FieldSpec("fact.hr.people_risk", FieldKind.FACT, 3, "People risk",
              "The person or team whose departure would hurt most. Seeds the risk "
              "register before there is any history to infer it from.",
              department="hr",
              answer_shape=AnswerShape.NAME,
              fallback_question='Whose departure would hurt the team most right now?',
              question_key='people_risk'),
    # The only L4 in the catalogue, and deliberately. `track_document_expiry`
    # is opt-in in the question bank for a stated reason: it concerns visas,
    # passports and residency documents, and nobody should be enrolled into
    # holding those by default. This field records the *decision*, never a
    # document.
    FieldSpec("fact.hr.document_expiry_tracking", FieldKind.FACT, 4,
              "Track document expiry",
              "Whether the company wants visa and residency expiry tracked at all. "
              "Records the decision, never a document.", department="hr",
              fallback_question='Should visa and document expiry be tracked?',
              question_key='track_document_expiry'),

    # ── Strategy ──────────────────────────────────────────────
    # L3, not L2. Every other department's operating facts are L3 and these are
    # the same kind of thing — a departmental rule rather than a company-wide
    # statement. At L2 a Contributor in another department could read them,
    # which is the opposite of what department scoping is for.
    FieldSpec("fact.strategy.constraint", FieldKind.FACT, 3, "Binding constraint",
              "What actually limits the business today.", department="strategy",
              fallback_question='What is the binding constraint today?',
              question_key='binding_constraint'),
    FieldSpec("fact.strategy.target_market", FieldKind.FACT, 3, "Target market",
              "Which market or region they are betting on, so a regional signal "
              "can be told from noise.", department="strategy",
              fallback_question='Which market or segment are you trying to enter?',
              question_key='target_market'),
    FieldSpec("fact.strategy.not_doing", FieldKind.FACT, 3, "Deliberately not doing",
              "Something ruled out on purpose. Prevents recommending what has "
              "already been decided against.", department="strategy",
              fallback_question='What are you deliberately not doing?',
              question_key='deliberately_not_doing'),

    # ── Chief of Staff ────────────────────────────────────────
    # No question-bank entries to lift: the bank covers six departments and has
    # never had an executive set. These three are written to the same test the
    # others pass — a thing only a person in that seat knows, answerable in one
    # line, and load-bearing for something a screen would show.
    FieldSpec("fact.executive.distrusted_number", FieldKind.FACT, 3, "Distrusted number",
              "A figure they do not currently believe. No system reports its own "
              "unreliability, so this can only come from a person.", department="executive",
              answer_shape=AnswerShape.METRIC,
              fallback_question='Which number in your reporting do you not trust?'),
    FieldSpec("fact.executive.commitment_tracking", FieldKind.FACT, 3,
              "Where commitments are tracked",
              "Where decisions made in leadership meetings are written down, if "
              "anywhere.", department="executive",
              fallback_question='Where are exec commitments written down, if anywhere?'),
    FieldSpec("fact.executive.board_cadence", FieldKind.FACT, 3, "Board cadence",
              "How often the board or leadership team formally reviews, which is "
              "what every deadline upstream of it is measured against.",
              department="executive",
              answer_shape=AnswerShape.DURATION,
              fallback_question='How often does the board formally review?'),
)

FIELD_CATALOGUE: Mapping[str, FieldSpec] = {spec.key: spec for spec in _SPECS}


# ── The guards ────────────────────────────────────────────────


class UndeclaredFieldError(ValueError):
    """A skill named a target that is not in the catalogue.

    Raised before the question reaches a person, and before any answer is
    stored. The whole point of the catalogue is that this is the only way a
    generated question can fail, and that it fails loudly.
    """


def resolve(key: str) -> FieldSpec:
    spec = FIELD_CATALOGUE.get(key)
    if spec is None:
        raise UndeclaredFieldError(
            f"'{key}' is not a declared field. A generated question must target a "
            f"key in app/ai/runtime/fields.py, which is where its scope comes from."
        )
    return spec


def askable_fields(department: str | None = None) -> tuple[FieldSpec, ...]:
    """What the agent may put to a person, narrowed to their department.

    Excludes anything a source can answer. This is the machine-readable form of
    the product's central restraint — do not ask what you can read — so it is
    enforced by the filter rather than by asking the model nicely.

    **`department` is the second restraint, and it used to be missing.** This
    function took no argument, so every one of the askable fields was offered
    to every user and the department they gave at signup reached the model as
    prose advice only — "a Head of Sales should not be walked through the
    finance fields first". An audit of seven end-to-end runs measured how well
    that held: **26% of questions were bound to a field belonging to a
    different department.** A Head of People was asked what disqualifies a
    sales deal; a Chief of Staff spent three of five questions on CRM
    mechanics; a hiring answer was written into `fact.sales.disqualifier`,
    where any sales dashboard would read it as deal policy.

    A model asked "what should we ask next" will always find a defensible next
    field, so the set it is shown is the only real control over which one. Now
    it is shown:

    - every `brain.*` and `persona.*` field, because those are company-wide and
      belong to whoever is answering; and
    - the `fact.*` fields of **their** department, and no other.

    `department` of None means nobody said — a user with no `stated_department`
    — and the honest response is to offer every department's facts rather than
    none, exactly as `runs_department` treats an empty selection as "nothing has
    been ruled out". Narrowing to zero would leave the interview with only
    narrative fields, which is the other half of what the audit found wrong.

    An unrecognised department is treated the same way, deliberately: the value
    is what a person typed about themselves, so a typo must not silently empty
    the catalogue.
    """
    known = {spec.department for spec in _SPECS if spec.department}
    scoped = department if department in known else None
    if department and scoped is None:
        # Loud, because the consequence is invisible and total: every field is
        # offered to everyone, which is exactly the pre-narrowing behaviour. An
        # audit hit this by sending the label "Operations" for the key
        # `operations` and watched a Head of Operations be led with Finance
        # questions. `POST /companies` now rejects a bad value outright; this
        # catches the row that was written before it did, or by anything else.
        log.warning(
            "fields.department.unrecognised",
            department=department,
            known=sorted(known),
        )

    def offered(spec: FieldSpec) -> bool:
        if not spec.only_you_know:
            return False
        if spec.department is None:
            return True  # brain.* and persona.* belong to whoever is answering.
        return scoped is None or spec.department == scoped

    return tuple(spec for spec in _SPECS if offered(spec))


def brain_fields() -> tuple[FieldSpec, ...]:
    """The Company Brain keys, and the only ones a brief statement may name.

    A brief statement is not just prose on a screen — its `field` comes back as
    the key of a correction, and a correction is stored, so it has to resolve in
    the catalogue like any other write. Grounded into `company-summary` for that
    reason: left to invent keys it produced `profile` for `brain.profile`, plus
    two (`profile_disclaimer`, `products_services_detail`) that exist nowhere at
    all, and every one of them made its row impossible to correct.
    """
    return tuple(s for s in _SPECS if s.kind is FieldKind.BRAIN)


@dataclass(frozen=True, slots=True)
class BrainGroup:
    """One slice of the Brain, and how hard to think about it."""

    name: str
    keys: tuple[str, ...]
    effort: str
    """Overrides the skill manifest for this group only.

    Not a knob for taste — it is the difference between the assembly finishing
    and not. Measured on the same session and the same skill:

        identity  3 fields, 20 pages in   ->   46.8s, clean finish
        market    4 fields,  8 pages in   ->   >240s, killed by the proxy

    The group with *fewer* pages and one more field took five times longer, so
    input size is not what separates them. `identity` asks for profile, products
    and brand voice — all of it plainly on the page. `market` asks for
    competitors and assumptions, which a company's own site barely evidences,
    and at `high` the model spends its reasoning budget deciding what it may not
    say. The prompt tells it to refuse rather than invent, correctly, and then
    high effort makes refusing expensive.

    `medium` here buys a shorter deliberation on exactly the fields where the
    deliberation was not producing a better answer — the honest ceiling on those
    fields is the evidence, not the thinking. `identity` stays at the manifest's
    `high`, because there the thinking has something to work with.
    """


BRAIN_GROUPS: tuple[BrainGroup, ...] = (
    BrainGroup(
        name="identity",
        keys=("brain.profile", "brain.products_services", "brain.brand_voice"),
        effort="high",
    ),
    BrainGroup(
        name="market",
        keys=("brain.target_customers", "brain.goals", "brain.competitors", "brain.assumptions"),
        effort="medium",
    ),
)
"""The Brain, in the order it is assembled — one model call per group.

It used to be one call for all seven fields, and that call did not fit. Measured
twice against a real site: **242 seconds, aborted both times** by the 240s proxy
timeout in `apps/web/app/api/onboarding/agent/finish/route.ts`. Onboarding could
not reach `ready` at all. Raising the timeout only moves the number a person
stares at a spinner, and every proxy in front of this has a limit of its own.

The split is by where the answers come from, not by counting fields into equal
piles. `identity` is what the crawl can support on its own; `market` is what the
interview and the founder's corrections decide. Each group is a smaller prompt
*and* a smaller output, so both halves of the budget shrink together.

Two groups is a floor, not a target: adding a third is adding a tuple here, and
nothing else changes — the route reads the next unfinished group off the session
row, so the phase machine, the resume path and the client loop all follow.
"""


def brain_group(name: str) -> BrainGroup | None:
    """One group by name, or None if it is not a group."""
    return next((group for group in BRAIN_GROUPS if group.name == name), None)


def brain_group_fields(name: str) -> tuple[FieldSpec, ...]:
    """The specs in one group, in catalogue order.

    Grounded into `company-brain-builder` for the same reason `askable_fields`
    is grounded into question-generation: a model asked to fill in a catalogue it
    cannot see guesses at key names, and the gate then correctly refuses every
    one of them.
    """
    group = brain_group(name)
    keys = group.keys if group else ()
    return tuple(spec for spec in _SPECS if spec.key in keys)


def persona_fields() -> tuple[FieldSpec, ...]:
    """The persona keys, and the only ones `persona-builder` may name.

    Grounded into that skill for the same reason `askable_fields` is grounded
    into question-generation: a model asked to fill in a catalogue it cannot see
    guesses at the key names. It guessed `priority_topics` for
    `persona.priority_topics`, the catalogue gate correctly refused it, and the
    persona came out empty — the filter worked and the feature did not.
    """
    return tuple(s for s in _SPECS if s.kind is FieldKind.PERSONA)


_SHAPE_CUES: Mapping[AnswerShape, tuple[str, ...]] = {
    AnswerShape.DURATION: (
        "how long", "how many day", "how many week", "how many month",
        "how many hour", "how often", "after how", "at what point",
        "how quickly", "how soon", "within what", " days", " day ", " hours",
        " weeks", " months", " fortnight", "how frequently",
        # Nouns that *are* a duration. Without these, "what do you promise
        # customers as a lead time?" — the hand-written bank wording for
        # `fact.operations.lead_time` — fails the gate on its own field, which
        # is a hole in the cues rather than a fault in the question.
        "lead time", "turnaround", "cycle time", "how much notice",
    ),
    AnswerShape.AMOUNT: (
        "how much", "what amount", "above what", "over what", "what threshold",
        "what level", "what size", "what value", "above which",
        "more than what", "what budget",
    ),
    AnswerShape.NAME: (
        "who ", "who's", "whose", "whom", "who?", "which person", "which team",
        "which compan", "which firm", "which competitor", "which supplier",
        "which vendor", "name the",
    ),
    # Phrase cues only, never a bare unit word. "tracking down the actual
    # numbers" is prose that mentions numbers without asking for one, and it is
    # the exact sentence that was bound to `distrusted_number`.
    AnswerShape.METRIC: (
        "which number", "what number", "which figure", "what figure",
        "which metric", "what metric", "which report", "what report",
        "which of your numbers", "what data",
    ),
}
"""Wording that can plausibly elicit each shape.

Deliberately generous. A rejection costs one extra model call — the retry loop
already exists for undeclared targets — while a false rejection of a well-worded
question costs nothing but that call. Being strict here would trade a real
defect for an invented one.
"""


def question_elicits(question: str, spec: FieldSpec) -> bool:
    """Can this question's wording plausibly produce this field's answer?

    Not "does the question mean the same as the intent" — that needs a second
    model call to judge, and a model judging a model on the hot path of every
    turn is a poor trade for a check this can make for free. It asks the weaker,
    checkable question: **the field wants a length of time / an amount / a name
    / a figure, so does the question ask for one?**

    `PROSE` fields always pass. There is no structural mismatch to find between
    a prose question and a prose field, and pretending otherwise would reject
    good questions to no purpose.

    See `AnswerShape` for the three audited failures this catches, each of which
    survives the department narrowing because each names the right department's
    field and the wrong one inside it.
    """
    if spec.answer_shape is AnswerShape.PROSE:
        return True
    lowered = question.lower()
    return any(cue in lowered for cue in _SHAPE_CUES[spec.answer_shape])


_SECOND_INTERROGATIVE = (
    "is it", "which", "what", "how", "do you", "does it", "are you", "where",
    "who", "when",
)

MAX_QUESTION_WORDS = 22
"""Longer than this is a second question wearing the first one's punctuation.

Not a style preference. The longest well-formed question in two audits is 18
words; every compound one is 20 or more. The margin is deliberately thin
because a rejection is now cheap — `MAX_REJECTIONS` is 8 and there is a
hand-written fallback under it, so a firm cap costs a Haiku call rather than an
interview.
"""


def is_compound(question: str) -> bool:
    """Whether this asks more than one thing.

    **The counting-question-marks version made this worse, measurably.** It
    rejected two sentences, so the model stopped writing two sentences and
    started packing both questions into one — compound questions went from ~43%
    to ~73% between audits. Every example was a single sentence with a single
    mark:

    - "...is it someone who clicks through from your paid social, or does it
      need to go further, like adding to cart or starting checkout?"
    - "...which of those channels is driving signups today, and which one would
      you want to fix first?"
    - "What actually limits the business today — is it the number of partners we
      can deploy, the markets we can reach, or something else?"

    It matters because people answer the last clause and drop the first, so the
    stored fact is systematically the less useful half of what was asked.

    Four structural tests instead of one punctuation test: more than one mark, an
    option-list tell ("or something else"), a substantial trailing alternative,
    and a second interrogative after "and". Verified against every compound
    question in both audits and every hand-written fallback.
    """
    text = question.strip()
    lowered = text.lower()

    if text.count("?") > 1:
        return True
    # The tell of a question offering a menu rather than asking one thing.
    if "or something else" in lowered or "or is it" in lowered:
        return True
    if len(text.split()) > MAX_QUESTION_WORDS:
        return True
    # ", or ..." with something substantial after it. A short tail is a genuine
    # either/or, which the prompt encourages; a long one is a second question.
    alternative = re.split(r",\s+or\s+", text, maxsplit=1)
    if len(alternative) == 2 and len(alternative[1].split()) > 4:
        return True
    # ", and " followed by a fresh interrogative — "…today, and which one…".
    joined = re.split(r",\s+and\s+", text, maxsplit=1)
    if len(joined) == 2:
        rest = joined[1].lstrip().lower()
        if any(rest.startswith(word) for word in _SECOND_INTERROGATIVE):
            return True
    return False


def next_fallback(
    department: str | None, already_known: Mapping[str, object]
) -> FieldSpec | None:
    """The best unanswered field with hand-written wording, or None.

    Served when the model has failed to produce an acceptable question often
    enough that the alternative is ending the interview — which is what used to
    happen, silently, in half of an audited sample.

    **The answerer's own department comes first.** That is the floor the audit
    asked for: a Head of Operations completing onboarding without being asked
    anything operational should be impossible by construction rather than
    unlucky. Only once their department is exhausted does this fall back to the
    company-wide fields, which anyone can answer.

    Catalogue order within each group, so the ordering is the same one a reader
    of `fields.py` sees rather than a second, invisible priority list.
    """
    offered = askable_fields(department)
    answered = set(already_known)

    def usable(spec: FieldSpec) -> bool:
        return bool(spec.fallback_question) and spec.key not in answered

    own = [s for s in offered if usable(s) and s.department is not None]
    shared = [s for s in offered if usable(s) and s.department is None]
    return next(iter(own + shared), None)


def fields_for_prompt(specs: tuple[FieldSpec, ...]) -> list[dict[str, str]]:
    """What the model is shown. Deliberately no scope, no column, no kind.

    A model that could see the scope could reason about which phrasing gets an
    answer stored more permissively. It has no legitimate use for the tag, so it
    does not get it.

    `answer_shape` **is** shown, unlike the scope, because it is a fact about
    what a good question looks like rather than about where the answer lands.
    Telling the model up front is what makes the check in `question_elicits`
    mostly unnecessary: the point is to aim, not to reject.
    """
    return [
        {
            "key": s.key,
            "label": s.label,
            "intent": s.intent,
            "answer_shape": s.answer_shape.value,
        }
        for s in specs
    ]


_ROLE_SHAPED = ("role", "seniority", "department", "permission", "scope", "access", "admin")


def assert_persona_is_not_authorisation() -> None:
    """Fail at import if a persona field ever starts to look like authorisation.

    `doc/06` §2.6 — conflating presentation preference with authorisation is how
    access-control bugs get written; `persona_chat.never_asked` says the same
    thing as an absence. An absence is easy to erode by addition, so this says it
    as an assertion that a future edit has to argue with.
    """
    for spec in _SPECS:
        if spec.kind is not FieldKind.PERSONA:
            continue
        if spec.scope != 5:
            raise AssertionError(
                f"persona field {spec.key!r} is stored at L{spec.scope}; persona is "
                f"personal preference and belongs at L5"
            )
        tail = spec.key.split(".", 1)[1]
        if any(word in tail for word in _ROLE_SHAPED):
            raise AssertionError(
                f"persona field {spec.key!r} looks like authorisation. Role, seniority "
                f"and department reach are set by membership, never by onboarding."
            )


assert_persona_is_not_authorisation()
