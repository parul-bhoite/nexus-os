"""The rail, the blocks, and the three gaps assigning them found.

`doc/13` §4 and §6. A director's page is 4–6 named sections; the section is the
unit of navigation, the block is the unit of rendering, and the capability is
the unit of truth. This file holds the joins between those three, and — more
usefully — the places where they do not meet.

Assigning all eighty capabilities to `doc/08`'s sections found three things that
are worth a decision rather than a fix:

1. **Two questions feed capabilities the cut cannot show anywhere.**
2. **Five sections `doc/08` draws have nothing behind them.**
3. **One block kind has no users yet**, because its section arrives in step D.

Each is asserted as an equality rather than a bound, so a *sixth* empty section
or a *third* homeless question fails here instead of shipping.
"""

from __future__ import annotations

import pytest

from app.domain.registry import BY_ID, CAPABILITIES, CapabilityKind
from app.domain.scopes import Department
from app.domain.sections import (
    BY_DEPARTMENT_AND_KEY,
    EMPTY_SECTIONS,
    NOT_ASKED,
    PLACEMENT,
    QUESTION_FED_WITHOUT_A_SECTION,
    RAILS,
    SECTIONS,
    WATCH_ITEMS,
    WATCHED_DEPARTMENTS,
    Block,
    placement_of,
    sections_for,
)

TILES = tuple(c for c in CAPABILITIES if c.kind is CapabilityKind.TILE)


# ── The rail ──────────────────────────────────────────────────


def test_every_department_with_a_director_has_a_rail() -> None:
    """A director page with no sections is the flat list this replaces."""
    for department in Department:
        assert sections_for(department), f"{department.value} has no sections"


def test_the_rail_is_ordered_and_not_sorted() -> None:
    """Order is the design. `doc/08` leads every department with Overview
    because that is the screen somebody opens for; a rail sorted alphabetically
    would put Approvals before Cash on the Finance page."""
    finance = [section.key for section in sections_for(Department.FINANCE)]

    assert finance[0] == "overview"
    assert finance != sorted(finance)


def test_section_keys_are_unique_within_a_department() -> None:
    """Two tabs with one key is how the wrong one gets rendered — and several
    departments deliberately share key *names* across departments (`overview`),
    so uniqueness is per department rather than global."""
    for department, sections in SECTIONS.items():
        keys = [section.key for section in sections]
        assert len(keys) == len(set(keys)), department.value


def test_every_section_carries_a_label_it_did_not_derive() -> None:
    """Finding F13. The same thing was `hr` in the API, "Hr" in a checkbox and
    "People" in the nav because each surface title-cased the value itself."""
    for (department, key), section in BY_DEPARTMENT_AND_KEY.items():
        assert section.label, f"{department.value}.{key}"
        assert section.label != key


# ── Placement ─────────────────────────────────────────────────


def test_every_tile_has_a_placement_and_every_rule_has_none() -> None:
    """The registry refuses to build otherwise, so this states the rule the
    import already enforces — and states it where a reader looks for it."""
    for capability in CAPABILITIES:
        if capability.kind is CapabilityKind.RULE:
            assert capability.section == ""
            assert capability.block is None
            assert capability.id not in PLACEMENT
        else:
            assert capability.block is not None, capability.id
            assert capability.id in PLACEMENT


def test_a_placed_capability_names_a_section_of_its_own_department() -> None:
    """A Marketing tile on the Finance rail would render for a caller who may
    not reach Marketing at all — reach and readiness kept apart (`doc/13` §3)
    only works if a tile cannot wander."""
    for capability in TILES:
        if not capability.section:
            continue
        assert (capability.department, capability.section) in BY_DEPARTMENT_AND_KEY, (
            f"{capability.id} sits on {capability.section!r},"
            f" which is not a {capability.department.value} section"
        )


def test_placement_of_raises_for_an_unknown_capability() -> None:
    """Defaulting would put a tile in whichever tab the loop was on."""
    with pytest.raises(KeyError):
        placement_of("finance.a_tile_nobody_declared")


def test_the_catalogue_is_wider_than_the_cut_and_says_which_is_which() -> None:
    """`doc/08` §11: the Growth Plan, the Content Studio, the calendar, ad
    creative and the war room are *"not present. All are generation features;
    none blocked by data."*

    So an empty section is a documented gap, not a mistake — and the assertion
    worth making is that **both** groups are non-empty. A cut that placed
    everything would mean somebody invented sections; a cut that placed nothing
    would mean the rail has no content.
    """
    placed = [c for c in TILES if c.section]
    outside = [c for c in TILES if not c.section]

    assert placed, "the rail renders something"
    assert outside, "doc 08 is narrower than doc 05, and the registry keeps both"


# ── Blocks ────────────────────────────────────────────────────


def test_the_generators_are_a_block_of_their_own() -> None:
    """`doc/13` §6 specified eight blocks. Assigning eighty capabilities found a
    ninth: a generator takes an instruction and produces an artefact, and
    forcing the studios into `panel` would have made a third of the product's
    value render as an explanation of itself.
    """
    studios = {c.id for c in TILES if c.block is Block.STUDIO}

    assert "marketing.content_studio" in studios
    assert "sales.proposal_studio" in studios
    assert "people.policy_library" in studios
    assert len(studios) > 8, "enough of them that `panel` was never going to hold them"


def test_every_block_kind_has_a_capability_that_uses_it() -> None:
    """A block kind nothing produces is a kind nobody has thought about — the
    same failure as an unreachable render state.

    `FACTS` was the last one unused, and step D's Setup section is what it was
    waiting for. All nine are in use now, which is the assertion worth keeping:
    a tenth added speculatively fails here until something renders as it.
    """
    used = {c.block for c in TILES if c.block}

    assert used == set(Block), f"unused block kinds: {sorted(k.value for k in set(Block) - used)}"
    assert Block.FACTS in used, "the Setup section renders as quoted answers"


# ── The three gaps ────────────────────────────────────────────


def test_two_questions_feed_capabilities_the_cut_cannot_show() -> None:
    """Q33's rule, one step later — and the one finding here that is a decision.

    ADR 0020 cuts a question nothing consumes. This is the neighbouring case: a
    question whose consumer exists and has **nowhere on any screen to appear**.
    Question 2.3 asks for the acquisition budget and feeds the Growth Plan,
    which `doc/08` §11 cut. Question 6.3 asks for the biggest people risk and
    feeds the Executive risk register, and the executive rail is brief, health,
    departments, decisions, brain, admin.

    Answering a question and never using the answer is worse than not asking:
    the founder spent the effort and now believes the product is watching
    something it is not. **Either the section arrives or the question goes**, and
    that is Parul's call rather than a fix to make here.
    """
    homeless = {
        capability.id
        for capability in TILES
        if capability.consumes_facts and not capability.section
    }

    assert homeless == QUESTION_FED_WITHOUT_A_SECTION, (
        "a question whose answer has nowhere to appear. Either give the"
        f" capability a section or cut the question: {sorted(homeless)}"
    )


def test_five_sections_have_nothing_behind_them_yet() -> None:
    """A tab with no capability cannot render, so the rail has to know.

    Held as a set rather than discovered at request time: filling one is then a
    visible edit, and a **sixth** empty tab fails here rather than shipping a
    blank screen somebody clicks into.
    """
    filled = {(c.department.value, c.section) for c in TILES if c.section}
    empty = {
        (department.value, section.key)
        for department, sections in SECTIONS.items()
        for section in sections
        if (department.value, section.key) not in filled
    }

    assert empty == EMPTY_SECTIONS, f"the rail's empty tabs changed. Now: {sorted(empty)}"


def test_the_questions_behind_the_two_homeless_capabilities_are_named() -> None:
    """The decision needs the *questions*, not the capability ids — a founder
    answered them and a person has to decide whether that was worth their
    time."""
    questions = {
        key
        for capability_id in QUESTION_FED_WITHOUT_A_SECTION
        for key in BY_ID[capability_id].consumes_facts
    }

    assert questions == {"acquisition_budget", "people_risk"}


# ── Step D: the two sections that are ours ────────────────────


def test_setup_reaches_every_department_that_asked_questions() -> None:
    """And no others. The Chief of Staff has no question block — it consumes the
    other directors rather than asking anything of its own — so a Setup tab
    there would be empty, which is the one thing this rail refuses to render."""
    from app.domain.question_bank import BY_DEPARTMENT as QUESTIONS

    with_setup = {
        department
        for department, sections in RAILS.items()
        if any(section.key == "setup" for section in sections)
    }

    assert with_setup == {d for d in Department if QUESTIONS.get(d)}
    assert Department.EXECUTIVE not in with_setup


def test_the_watchlist_reaches_only_departments_that_named_a_risk() -> None:
    """Sales and Finance have none, and that is a property of their questions
    rather than an oversight: every one of theirs is a threshold or a definition
    — payment terms, the stale-deal window, the quota period. Useful, and not a
    statement about what is currently wrong."""
    with_watch = {
        department
        for department, sections in RAILS.items()
        if any(section.key == "watchlist" for section in sections)
    }

    assert with_watch == WATCHED_DEPARTMENTS
    assert Department.SALES not in with_watch
    assert Department.FINANCE not in with_watch


def test_every_watch_item_names_a_real_question() -> None:
    """A watch card built from a question nobody was asked would be the product
    inventing a worry and attributing it to the founder."""
    from app.domain.question_bank import BY_DEPARTMENT as QUESTIONS

    asked = {
        question.key: department
        for department, questions in QUESTIONS.items()
        for question in questions
    }

    for item in WATCH_ITEMS:
        assert item.question_key in asked, item.question_key
        assert asked[item.question_key] is item.department, (
            f"{item.question_key} is asked of {asked[item.question_key].value},"
            f" not {item.department.value}"
        )


def test_the_executive_watch_card_the_design_describes_does_not_exist() -> None:
    """`doc/13` §9 lists five watch items. Four exist.

    The fifth comes from `doc/08` 8.3 — *"what decision have you been putting
    off?"* — feeding the Executive decision queue. **That question is not in the
    bank**: ADR 0020 cut it to six departments with a block, and the Chief of
    Staff asks nothing of its own.

    So the card cannot be built without either adding an executive block or
    dropping it from the design. Asserted rather than fixed, because inventing
    the question is the one option that must not be taken quietly.
    """
    from app.domain.question_bank import BY_DEPARTMENT as QUESTIONS

    assert not QUESTIONS.get(Department.EXECUTIVE)
    assert len(WATCH_ITEMS) == 4
    assert not any(item.department is Department.EXECUTIVE for item in WATCH_ITEMS)


def test_every_department_says_what_it_will_not_ask_for() -> None:
    """`doc/08` §2B to §8B, and §11 calls it one of the two things that cut adds:
    *"showing the customer what NEXUS refuses to ask them is a product surface,
    not just an internal rule."*

    Every department, including the Executive — which asks nothing and therefore
    has the longest list of things it will fetch instead.
    """
    for department in Department:
        entries = NOT_ASKED.get(department, ())
        assert entries, department.value
        for entry in entries:
            assert entry.what
            assert entry.source, f"{department.value}: {entry.what} names no source"


def test_no_question_is_both_asked_and_declared_unaskable() -> None:
    """The contradiction that would make the two surfaces disagree.

    A department cannot say *"we will not ask you for your payment terms"* on
    one tab and ask for them on another. Compared on the words rather than on a
    key, because the two lists are prose written months apart — which is exactly
    when this drifts.
    """
    from app.domain.question_bank import BY_DEPARTMENT as QUESTIONS

    for department, questions in QUESTIONS.items():
        asked = {question.prompt.lower().rstrip("?") for question in questions}
        for entry in NOT_ASKED.get(department, ()):
            assert entry.what.lower() not in asked, (
                f"{department.value} both asks for and refuses to ask for {entry.what!r}"
            )
