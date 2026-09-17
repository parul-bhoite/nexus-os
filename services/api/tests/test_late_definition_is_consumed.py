"""`late_definition` is read by the figure that declares it — `doc/14` S9, ADR 0036.

**The defect this closes was a lie the dashboard told.** `open_questions.compose`
puts a question in the "answers that would change a figure on this page" tier
when its consumer is currently measuring. `operations.on_time_dispatch` measures,
and declared `late_definition` consumed — while the question was typed
`SINGLE_CHOICE` with **no options**, collected free prose, and was read by
nothing. A founder was told that answering it would move a number, and it would
not have.

The question now offers days as a closed set, so the answer *is* the threshold
the rate needs. These assert both halves: that the options are numbers, and that
the capability declaring the fact is the one that can use it.

Hermetic: the question bank and the registry are tables built at import.
"""

from __future__ import annotations

from app.domain.question_bank import BY_DEPARTMENT
from app.domain.registry import BY_ID, consumers_of
from app.domain.scopes import Department

LATE = next(q for q in BY_DEPARTMENT[Department.OPERATIONS] if q.key == "late_definition")


def test_the_answer_is_a_number_of_days() -> None:
    """**The whole fix.** A parser over prose would be us choosing a threshold on
    the customer's behalf, which is what ADR 0036 refused; a closed set of days
    makes the answer the number itself."""
    assert LATE.options, "a SINGLE_CHOICE question with no options collects prose"
    assert all(choice.value.isdigit() for choice in LATE.options), [c.value for c in LATE.options]


def test_every_option_is_a_grace_a_business_would_actually_state() -> None:
    """Five options rather than a free number. A grace measured in weeks is a
    different promise rather than a longer one, and a text box invites "it
    depends" — the state this question exists to leave."""
    days = sorted(int(choice.value) for choice in LATE.options)

    assert days[0] == 0, "same-day-late is a real promise and the strictest one"
    assert days[-1] <= 7
    assert len(days) == len(set(days)), "two options meaning the same thing"


def test_each_option_says_what_it_means_in_words() -> None:
    """The value is a number and the label is a sentence. A menu reading
    "0 / 1 / 2" asks a founder to guess the unit."""
    for choice in LATE.options:
        assert choice.label
        assert not choice.label.isdigit()


def test_the_capability_that_declares_it_is_the_one_that_reads_it() -> None:
    """`consumers_of` inverts the bank into the registry, and the dashboard uses
    it to promise that an answer changes a figure. The promise is only true if
    the consumer is the capability whose rule this is."""
    assert consumers_of("late_definition") == ("operations.on_time_dispatch",)
    assert BY_ID["operations.on_time_dispatch"].reachable


def test_the_other_operations_facts_are_not_claimed_to_be_numbers() -> None:
    """A guard against fixing this by giving every prose question a menu.
    `common_delay_cause` is genuinely the founder's own words, and a closed set
    there would put our vocabulary in their mouth — `domain/onboarding.py` says
    so where it defines `Choice`."""
    cause = next(q for q in BY_DEPARTMENT[Department.OPERATIONS] if q.key == "common_delay_cause")

    assert not any(c.value.isdigit() for c in cause.options)
