"""Two invariants: a field resolves against the caller, an artifact inherits max().

P19 and P21. Both are about the same failure — a value that is correct for one
reader appearing in front of another — arriving by two different routes.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.domain.artifacts import Artifact, declassify, mark_stale
from app.domain.field_scope import redact, visible_fields
from app.domain.scopes import Department, Role, Scope
from app.domain.session import ScopedSession

PROJECT = {
    "name": "Muscat fit-out",
    "milestones": ["a", "b"],
    "progress": 0.4,
    "cost_lines": [1000, 2000],
    "margin": 0.22,
}


def _caller(role: Role, departments: set[Department]) -> ScopedSession:
    return ScopedSession(
        user_id=uuid4(),
        tenant_id=uuid4(),
        workspace_id=uuid4(),
        role=role,
        departments=frozenset(departments),
    )


def test_a_supervisor_sees_the_project_and_not_the_margin() -> None:
    """P19's sentence, as a test. The same row, two readers, two answers."""
    supervisor = _caller(Role.CONTRIBUTOR, {Department.OPERATIONS})
    seen = redact(PROJECT, supervisor)

    assert "name" in seen and "milestones" in seen
    assert "margin" not in seen
    assert "cost_lines" not in seen


def test_a_hidden_field_is_omitted_not_nulled() -> None:
    """`margin: null` beside a populated project tells the reader a margin
    exists and is being withheld — a disclosure about the company's structure,
    and an invitation to go looking elsewhere."""
    seen = redact(PROJECT, _caller(Role.CONTRIBUTOR, {Department.OPERATIONS}))
    assert "margin" not in seen.keys()


def test_finance_sees_the_cost_lines() -> None:
    finance = _caller(Role.DEPARTMENT_MANAGER, {Department.FINANCE})
    assert "cost_lines" in visible_fields(finance)


def test_visible_fields_returns_names_so_the_query_can_use_them() -> None:
    """Filtering after the fetch means the hidden value was already loaded into
    a process that serialises objects for a living, and the only thing between
    it and the response is a `del`."""
    assert isinstance(visible_fields(_caller(Role.OWNER, set(Department))), frozenset)


# ── Artifacts (I6) ────────────────────────────────────────────


def _artifact(*scopes: Scope, facts: tuple[str, ...] = ()) -> Artifact:
    return Artifact(id=uuid4(), version=1, input_scopes=scopes, input_fact_keys=facts)


def test_one_restricted_input_governs_the_whole_artifact() -> None:
    """A summary of one L4 figure and twenty L2 ones is L4. The restricted
    number is *in* it, and averaging the scopes would produce a document that
    reads as shareable and is not."""
    mixed = _artifact(*([Scope.L2_COMPANY_INTERNAL] * 20), Scope.L4_RESTRICTED)
    assert mixed.inherited_scope is Scope.L4_RESTRICTED
    assert mixed.needs_confirmation_to_share


def test_an_artifact_built_from_nothing_is_restricted_not_public() -> None:
    """The safe reading of "we cannot tell where this came from" is the most
    restrictive one. The opposite default would let a bug in input tracking
    silently publish something."""
    assert _artifact().inherited_scope is Scope.L5_PERSONAL


def test_declassifying_without_a_reason_is_refused() -> None:
    """ "Who decided this could be shared, and why" is the first question asked
    afterwards."""
    with pytest.raises(ValueError, match="needs a reason"):
        declassify(
            _artifact(Scope.L4_RESTRICTED),
            to=Scope.L2_COMPANY_INTERNAL,
            by_user_id=uuid4(),
            reason="  ",
        )


def test_declassifying_only_ever_loosens() -> None:
    """Tightening is not declassification, and an artifact quietly becoming more
    restricted breaks links for people who already hold it."""
    with pytest.raises(ValueError, match="only ever loosens"):
        declassify(
            _artifact(Scope.L2_COMPANY_INTERNAL),
            to=Scope.L4_RESTRICTED,
            by_user_id=uuid4(),
            reason="tightening",
        )


def test_a_declassified_artifact_records_who_and_why() -> None:
    who = uuid4()
    result = declassify(
        _artifact(Scope.L4_RESTRICTED),
        to=Scope.L2_COMPANY_INTERNAL,
        by_user_id=who,
        reason="Client-facing summary, figures removed.",
    )
    assert result.effective_scope is Scope.L2_COMPANY_INTERNAL
    assert result.declassified_by_user_id == who
    assert result.declassified_reason
    assert not result.needs_confirmation_to_share


def test_a_changed_fact_marks_stale_rather_than_regenerating() -> None:
    """Somebody may have sent this to a client, and the version they hold has to
    go on existing. Regenerating in place changes a document after it was
    quoted, which is worse than an out-of-date one that admits it."""
    original = _artifact(Scope.L2_COMPANY_INTERNAL, facts=("revenue",))
    marked = mark_stale(original, changed_fact="revenue")

    assert marked.stale
    assert marked.version == original.version, "the version is not bumped; it is flagged"


def test_an_unrelated_fact_does_not_mark_it_stale() -> None:
    original = _artifact(Scope.L2_COMPANY_INTERNAL, facts=("revenue",))
    assert not mark_stale(original, changed_fact="headcount").stale


# ── The catalogue is narrowed by department ───────────────────
#
# From an audit of seven end-to-end onboardings, one per department: 26% of the
# 35 questions asked were bound to a field belonging to a *different*
# department. A Head of People was asked what disqualifies a sales deal; a
# hiring answer was written into `fact.sales.disqualifier`, where a sales
# dashboard would read it as deal policy.
#
# The cause was that `askable_fields()` took no argument and the department
# reached the model as prose advice only. These tests exist because prose
# advice that is ignored 26% of the time has to become a filter.


def test_a_department_is_never_offered_another_departments_facts() -> None:
    from app.ai.runtime.fields import askable_fields

    for department in ("hr", "sales", "finance", "operations", "marketing",
                       "strategy", "executive"):
        offered = askable_fields(department)
        foreign = [
            spec.key
            for spec in offered
            if spec.department is not None and spec.department != department
        ]
        assert not foreign, f"{department} was offered {foreign}"


def test_every_department_is_offered_its_own_facts_and_the_shared_set() -> None:
    """Narrowing must not narrow to nothing.

    Every department needs its own `fact.*` fields *and* the company-wide
    `brain.*`/`persona.*` set, which belong to whoever is answering. A filter
    that dropped the shared set would leave the interview with only
    department trivia; one that dropped the department set would leave it with
    only narrative — and "too much narrative, not enough threshold" is the
    other half of what the audit found.
    """
    from app.ai.runtime.fields import askable_fields

    shared = {s.key for s in askable_fields(None) if s.department is None}
    assert shared, "there are no shared askable fields; this test proves nothing"

    for department in ("hr", "sales", "finance", "operations", "marketing",
                       "strategy", "executive"):
        offered = {s.key for s in askable_fields(department)}
        own = {
            s.key
            for s in askable_fields(None)
            if s.department == department
        }
        assert own, f"{department} has no askable facts at all"
        assert own <= offered, f"{department} lost its own fields"
        assert shared <= offered, f"{department} lost the shared fields"


def test_an_unknown_or_absent_department_is_offered_everything() -> None:
    """Not nothing — the same rule `runs_department` applies to an empty set.

    `stated_department` is what a person typed about themselves. Rows written
    before it became a dropdown hold free text like "Design", and a typo must
    not silently empty the catalogue and leave the interview unable to ask
    anything operational.
    """
    from app.ai.runtime.fields import askable_fields

    everything = {s.key for s in askable_fields(None)}
    assert {s.key for s in askable_fields("Design")} == everything
    assert {s.key for s in askable_fields("")} == everything


def test_no_department_is_left_with_only_one_askable_fact() -> None:
    """The skew the audit measured, asserted so it cannot come back.

    Askable `fact.*` per department was Finance 3, Sales 3, Operations 3,
    Marketing 2, **People 1, Strategy 1, Chief of Staff 1** — and with the
    catalogue narrowed by department, a department with one field has an
    interview that is almost entirely narrative. `question_bank.py` had held
    good People and Strategy questions since Phase 7 with no field to bind
    them to.
    """
    from collections import Counter

    from app.ai.runtime.fields import askable_fields

    counts = Counter(s.department for s in askable_fields(None) if s.department)
    thin = {d: n for d, n in counts.items() if n < 2}
    assert not thin, f"these departments cannot sustain an interview: {thin}"


# ── A question must be able to elicit its own field ───────────
#
# The five mismatches an audit of seven interviews found, verbatim. Two of them
# are already impossible — the catalogue is narrowed by department now, and they
# named another department's field. The other three name the *right*
# department's field and the wrong one inside it, which no amount of scoping
# catches. `AnswerShape` explains why the check is a shape rather than a
# meaning.


def test_the_three_audited_mismatches_are_rejected() -> None:
    """Each of these stored the wrong meaning with full provenance."""
    from app.ai.runtime.fields import FIELD_CATALOGUE, question_elicits

    # `brain.competitors` means "who you actually lose to". Asked about channel
    # economics, and stored — at the time — as "Company public".
    assert not question_elicits(
        "You mentioned cutting blended CAC below $40 — which channels or customer types "
        "are you currently losing money on, or where do you see the biggest opportunity "
        "to improve efficiency?",
        FIELD_CATALOGUE["brain.competitors"],
    )

    # `runway_alarm` means "how many months of runway would change their plans".
    # The compounding case: the *next* question said "when you hit that
    # nine-month runway threshold", quoting a number never given.
    assert not question_elicits(
        "You mentioned cash visibility is your biggest headache — when you're forecasting "
        "cash, what's the gap that causes the most friction right now?",
        FIELD_CATALOGUE["fact.finance.runway_alarm"],
    )

    # `distrusted_number` means "a figure they do not currently believe".
    # Note it *mentions* numbers — "tracking down the actual numbers" — which is
    # why the metric cues are phrases and never a bare unit word.
    assert not question_elicits(
        "When the CEO needs an answer to a board question, what's the single biggest thing "
        "that slows you down — is it finding who owns the information, tracking down the "
        "actual numbers, or something else?",
        FIELD_CATALOGUE["fact.executive.distrusted_number"],
    )


def test_well_worded_questions_are_not_rejected() -> None:
    """The cost of being strict, kept honest.

    Every one of these is a real question from the audit or from a live run that
    landed correctly. A shape check that rejected them would trade a real defect
    for an invented one — so they are asserted alongside the failures rather
    than left to trust.
    """
    from app.ai.runtime.fields import FIELD_CATALOGUE, question_elicits

    good = [
        ("fact.sales.stale_days",
         "When a deal goes quiet, how many days pass before you flag it for attention?"),
        ("fact.finance.approver",
         "When you're forecasting cash and you hit that threshold, who needs to sign off "
         "on the plan change?"),
        ("fact.operations.late_rule",
         "What's the threshold before it counts as late to your customers — is it a "
         "specific number of hours, or does it depend on what was promised?"),
        # Both of these were asked and accepted in a live People interview.
        ("fact.hr.hire_approver",
         "You mentioned cutting time-to-hire as a priority — who signs off on a new hire "
         "at your company?"),
        ("fact.hr.people_risk", "Whose departure would hurt the team most right now?"),
        ("brain.competitors",
         "When you're competing for those board-level relationships, who do you actually "
         "lose to?"),
        ("fact.finance.approval_threshold",
         "Above what amount does spend need your sign-off?"),
        ("fact.hr.review_cycle", "How often do performance reviews happen?"),
        ("fact.executive.distrusted_number",
         "Which number in your current reporting do you not trust?"),
    ]
    for key, question in good:
        assert question_elicits(question, FIELD_CATALOGUE[key]), f"{key} rejected: {question}"


def test_a_prose_field_is_never_shape_checked() -> None:
    """There is no structural mismatch to find between prose and prose.

    Checking them would reject good questions to no purpose — the failure this
    catches is a question asking for the wrong *kind* of thing, and a prose
    field has no kind to be wrong about.
    """
    from app.ai.runtime.fields import FIELD_CATALOGUE, AnswerShape, question_elicits

    spec = FIELD_CATALOGUE["brain.goals"]
    assert spec.answer_shape is AnswerShape.PROSE
    assert question_elicits("Anything at all, really.", spec)
    assert question_elicits("", spec)


def test_every_numeric_field_declares_a_shape() -> None:
    """The fields whose answers a screen can act on must be checkable.

    The audit's other half: narrative fields produced 15 of 35 questions and a
    workspace cannot act on a paragraph. The ones that change what a first
    screen does are the specific ones — stale after N days, approval above N —
    and those are exactly the ones where a mismatch is both most likely and most
    damaging, because the wrong answer still looks like a number.
    """
    from app.ai.runtime.fields import FIELD_CATALOGUE, AnswerShape

    must_be_specific = (
        "fact.sales.stale_days",
        "fact.finance.approval_threshold",
        "fact.finance.approver",
        "fact.finance.runway_alarm",
        "fact.operations.lead_time",
        "fact.operations.late_rule",
        "fact.hr.hire_approver",
        "fact.hr.review_cycle",
        "fact.executive.distrusted_number",
    )
    for key in must_be_specific:
        assert FIELD_CATALOGUE[key].answer_shape is not AnswerShape.PROSE, key


# ── The floor under the validators ────────────────────────────
#
# Round 2 of the audit: narrowing by department and checking that a question can
# elicit its field removed 100% of the leakage and 100% of the mismatches — and
# then **three of six interviews ended early**, one having asked nothing at all,
# because three validators shared a budget of three rejections. A validator
# without a fallback trades the defect it prevents for a blank interview.


def test_every_fallback_question_passes_its_own_gates() -> None:
    """The floor cannot itself fall through.

    This is the property that makes serving a fallback safe. Each one is the
    answer to "the model could not write an acceptable question for this field",
    so a fallback that the same checks would reject would loop or close the
    interview anyway — and the whole point is that it terminates.

    It also caught two real defects when written: the bank's `lead_time` wording
    ("what do you promise customers as a lead time?") failed the DURATION gate
    because the cues had no noun that *is* a duration, and the
    `persona.communication_style` fallback was genuinely two questions.
    """
    from app.ai.runtime.fields import askable_fields, is_compound, question_elicits

    with_fallback = [s for s in askable_fields(None) if s.fallback_question]
    assert len(with_fallback) >= 25, "too few fallbacks for this to prove anything"

    for spec in with_fallback:
        assert question_elicits(spec.fallback_question, spec), (
            f"{spec.key}'s fallback cannot elicit its own field: {spec.fallback_question!r}"
        )
        assert not is_compound(spec.fallback_question), (
            f"{spec.key}'s fallback is compound: {spec.fallback_question!r}"
        )


def test_every_department_has_a_fallback_for_its_own_facts() -> None:
    """A Head of Operations must not be able to finish having been asked nothing.

    That happened. `next_fallback` puts the answerer's own department first, so
    this asserts there is something there to put first.
    """
    from app.ai.runtime.fields import askable_fields, next_fallback

    for department in ("hr", "sales", "finance", "operations", "marketing",
                       "strategy", "executive"):
        own = [
            s
            for s in askable_fields(department)
            if s.department == department and s.fallback_question
        ]
        assert own, f"{department} has no fallback question for any of its own fields"

        served = next_fallback(department, {})
        assert served is not None
        assert served.department == department, (
            f"{department} was offered {served.key} before its own fields"
        )


def test_the_fallback_walks_the_department_then_the_shared_set() -> None:
    """It runs out honestly rather than repeating or stopping early."""
    from app.ai.runtime.fields import askable_fields, next_fallback

    answered: dict[str, object] = {}
    served: list[str] = []
    # Bounded well above the catalogue so a repeat shows up as a failure here
    # rather than as an infinite loop in the interview.
    for _ in range(60):
        spec = next_fallback("operations", answered)
        if spec is None:
            break
        assert spec.key not in served, f"{spec.key} served twice"
        served.append(spec.key)
        answered[spec.key] = "answered"

    assert served, "nothing was ever served"
    offered = {s.key for s in askable_fields("operations") if s.fallback_question}
    assert set(served) == offered, "the walk did not cover every offered fallback"
    # Own department before the company-wide set.
    own_count = sum(1 for k in served if k.startswith("fact.operations."))
    assert served[:own_count] == [k for k in served if k.startswith("fact.operations.")]


def test_the_compound_check_rejects_every_audited_compound_question() -> None:
    """Round 2, verbatim. All five are one sentence with one question mark.

    The mark-counting version passed every one of these, which is why the rate
    went from ~43% to ~73%: the model stopped writing two sentences and started
    writing one long one.
    """
    from app.ai.runtime.fields import is_compound

    compound = [
        "What's your definition of a lead for the subscription funnel—is it someone who "
        "clicks through from your paid social, or does it need to go further, like adding "
        "to cart or starting checkout?",
        "Which of those channels is actually driving the subscription signups today, and "
        "which one would you want to fix first?",
        "What actually limits the business today — is it the number of partners we can "
        "deploy, the markets we can reach, or something else?",
        "You mentioned spending too long chasing managers for review sign-offs — how "
        "often do those reviews happen, and when is the next cycle?",
        "When a container is stuck at the port or a truck doesn't show, what's the "
        "threshold before it counts as late to your customers — is it a specific number "
        "of hours, or does it depend on what was promised for that shipment?",
    ]
    for question in compound:
        assert is_compound(question), f"not caught: {question}"


def test_the_compound_check_keeps_good_questions() -> None:
    """The cost of a firm check, kept honest.

    Every one of these was asked and landed correctly in an audit or a live run.
    A short either/or stays legal — the prompt encourages offering alternatives
    inside one question.
    """
    from app.ai.runtime.fields import is_compound

    good = [
        "Where are exec commitments currently written down, if anywhere?",
        "When a deal goes quiet, how many days pass before you flag it for attention?",
        "You mentioned cutting time-to-hire as a priority — who signs off on a new hire "
        "at your company?",
        "You mentioned close takes eleven days — above what amount does a spend decision "
        "need sign-off before then?",
        "Is leave accrued monthly or granted annually?",
        "Whose departure would hurt the team most right now?",
    ]
    for question in good:
        assert not is_compound(question), f"wrongly rejected: {question}"


def test_promotion_does_not_invent_a_list_from_a_sentence() -> None:
    """The live defect, verbatim.

    `competitors`, `assumptions` and `priority_topics` are `text[]` and the
    skills that fill them return one string. A real promoted row read::

        ['Inland haulage', 'port handling', 'and keeping shipments on schedule.']

    from "inland haulage, port handling and keeping shipments on schedule" —
    the third element is the tail of a sentence, not a topic. Splitting on
    punctuation derives structure the source does not have, which is the
    failure this product exists to avoid one layer down.
    """
    from app.domain.onboarding_promotion import _split

    # Prose stays whole, even with commas in it.
    assert _split("Inland haulage, port handling and keeping shipments on schedule.") == [
        "Inland haulage, port handling and keeping shipments on schedule."
    ]
    assert _split("Schedule reliability above ninety per cent.") == [
        "Schedule reliability above ninety per cent."
    ]
    # A short comma list is a list.
    assert _split("Aramex, DHL, Fastway") == ["Aramex", "DHL", "Fastway"]
    # A semicolon is explicit and always splits.
    assert _split("MSC; CMA CGM; Hapag-Lloyd") == ["MSC", "CMA CGM", "Hapag-Lloyd"]
    # An actual list is passed through.
    assert _split(["already", "a list"]) == ["already", "a list"]
    assert _split("") == []
    assert _split(None) == []


def test_the_opening_question_is_worded_once() -> None:
    """The opener's wording lives in the catalogue, and the screen must agree.

    `/discovery` writes the opening question into the transcript from
    `FIELD_CATALOGUE['persona.stated_purpose'].fallback_question`, while
    `AgentOnboarding.tsx` renders it to the person before they answer. Two
    copies of one string in two languages is exactly the pair that drifts, and
    the drift is invisible: the screen asks one thing and the record says
    another, with no error anywhere.

    A cross-language assertion is unusual, so it is worth saying why this one
    is worth it. The transcript is the product's evidence that a stored fact
    came from a person's own words. A question mis-recorded in that transcript
    is the same class of defect as an invented number — it just looks like a
    typo.
    """
    from pathlib import Path

    from app.ai.runtime.fields import FIELD_CATALOGUE

    opener = FIELD_CATALOGUE["persona.stated_purpose"].fallback_question
    assert opener, "the opener must have wording in the catalogue"

    screen = (
        Path(__file__).resolve().parents[3]
        / "apps"
        / "web"
        / "components"
        / "onboarding"
        / "AgentOnboarding.tsx"
    )
    assert screen.is_file(), f"expected the onboarding screen at {screen}"
    assert opener in screen.read_text(encoding="utf-8"), (
        f"the screen no longer asks {opener!r}. Change the catalogue and the "
        f".tsx together, or the transcript records a question nobody was asked."
    )
