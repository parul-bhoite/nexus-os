"""What answering a question actually buys, asserted against the real bank.

`doc/14` step 5. The design's first draft claimed seven capabilities were
"unlockable by answering". The registry says **zero** — every fact-consuming
tile also requires a source — and that correction is the whole reason this
module exists rather than a list of questions with an encouraging heading.

The two failures worth guarding:

**Over-claiming.** Presenting every open question as though answering it moved
something lets a founder believe the product is waiting on them when it is
mostly waiting on us. The split into *changes a figure* and *waiting on us* is
what makes the honest version visible rather than merely stated.

**Under-scoping.** Questions are `L3_DEPARTMENT` by default, so composing over
every department would put another department's questions on a contributor's
dashboard.

Hermetic — the bank and the registry are tables built at import.
"""

from __future__ import annotations

from app.domain.open_questions import OpenQuestions, compose
from app.domain.question_bank import BY_DEPARTMENT
from app.domain.registry import BY_ID, TILES
from app.domain.scopes import Department
from app.grounding.compute import CRAWL_AUDITS

EVERY = frozenset(Department)
MEASURING = frozenset(CRAWL_AUDITS)


def _open(
    departments: frozenset[Department] = EVERY,
    answered: frozenset[tuple[str, str]] = frozenset(),
    measuring: frozenset[str] = MEASURING,
) -> OpenQuestions:
    return compose(
        bank=BY_DEPARTMENT, departments=departments, answered=answered, measuring=measuring
    )


# ── The correction this module exists for ─────────────────────


def test_no_question_in_the_bank_unlocks_a_tile_on_its_own() -> None:
    """**Zero, not seven.**

    Every capability that consumes a fact also requires a source, so answering
    changes what a tile *counts* and never whether it exists. Asserted against
    the registry rather than against the copy, so the claim cannot drift back
    into the optimistic version by somebody editing a sentence.
    """
    consumes_facts = [c for c in TILES if c.consumes_facts]

    assert consumes_facts, "if nothing consumes a fact this test is passing vacuously"
    assert all(c.required_sources for c in consumes_facts), sorted(
        c.id for c in consumes_facts if not c.required_sources
    )


def test_only_questions_whose_consumer_already_measures_are_listed() -> None:
    """The first tier is *what moves a number on this page today*. Anything
    else is counted, because a founder cannot act on it usefully yet."""
    result = _open()

    assert result.total == len(result.changes_a_figure) + result.waiting_on_us
    for question in result.changes_a_figure:
        assert question.consumed_by in MEASURING


def test_today_exactly_one_question_changes_a_live_figure() -> None:
    """`arabic_in_scope` changes what `marketing.seo_gaps` counts as a gap, and
    that tile is on the page. One of twenty-nine.

    Pinned deliberately: if this number climbs without a calculator landing,
    something has started counting questions whose consumer is not built, and
    that is the over-claim the region was designed to avoid.
    """
    result = _open()

    assert [q.key for q in result.changes_a_figure] == ["arabic_in_scope"]
    assert result.changes_a_figure[0].consumer_name == "SEO Intelligence"
    assert result.waiting_on_us > len(result.changes_a_figure)


# ── Nothing is invented ───────────────────────────────────────


def test_the_prompt_and_the_reason_are_the_banks_own_words() -> None:
    """The question on the dashboard has to be the question the setup flow will
    ask — two wordings for one question is two questions, and a founder who
    answers the second has not answered the first."""
    banked = {q.key: q for questions in BY_DEPARTMENT.values() for q in questions}

    for question in _open().changes_a_figure:
        assert question.prompt == banked[question.key].prompt
        assert question.why == banked[question.key].why
        assert question.why, "a question with no stated purpose is a form field (doc 06)"


def test_every_listed_question_names_a_capability_that_exists() -> None:
    """`consumed_by` is a capability id. One that the registry does not hold
    would render as a promise about something that is not in the product."""
    for question in _open().changes_a_figure:
        assert question.consumed_by in BY_ID
        assert question.consumer_name == BY_ID[question.consumed_by].name


# ── Scope and state ───────────────────────────────────────────


def test_a_reader_sees_only_their_own_departments_questions() -> None:
    """Questions are `L3_DEPARTMENT`. A composition over every department would
    put Finance's questions on a Marketing contributor's dashboard."""
    marketing = _open(departments=frozenset({Department.MARKETING}))

    assert marketing.total < _open().total
    assert all(q.department == "marketing" for q in marketing.changes_a_figure)


def test_a_sales_only_reader_has_nothing_in_the_first_tier() -> None:
    """Nothing Sales can answer moves a figure, because nothing in Sales
    computes one. The honest answer is an empty tier and a count — not an
    invented reason to fill the space."""
    sales = _open(departments=frozenset({Department.SALES}))

    assert sales.changes_a_figure == ()
    assert sales.waiting_on_us == sales.total > 0


def test_an_answered_question_leaves_the_list_entirely() -> None:
    result = _open(answered=frozenset({("marketing", "arabic_in_scope")}))

    assert result.changes_a_figure == ()
    assert result.total == _open().total - 1


def test_a_reader_with_no_department_is_asked_nothing() -> None:
    result = _open(departments=frozenset())

    assert result.total == 0
    assert result.changes_a_figure == ()


def test_the_order_is_stable_between_calls() -> None:
    """Departments are iterated in a fixed order rather than a set's. A region
    that reshuffled on reload would look rewritten while saying the same
    thing."""
    assert [q.key for q in _open().changes_a_figure] == [q.key for q in _open().changes_a_figure]
