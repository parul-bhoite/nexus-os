"""The gate every ops rate passes — `doc/15` S10.2, ADR 0035 (D29).

The ops layer fails on adoption, so a rate over its rows needs a fact the
database cannot hold about itself: somebody saying *"this is all of them"*. The
first ops rate is S10.4 and does not exist yet; these assert the rule anyway,
because a rule written after the code it governs is a rule written once somebody
has already shipped around it.

Hermetic: `calculators/` is pure by construction.
"""

from __future__ import annotations

from datetime import date

import pytest

from app.calculators.completeness import (
    ENTITIES,
    PROJECTS,
    TASKS,
    Confirmation,
    may_compute_a_rate,
    unvouched,
)

CONFIRMED = Confirmation(
    entity=PROJECTS, complete_as_of=date(2026, 9, 11), confirmed_on=date(2026, 9, 14)
)


# ── The gate ──────────────────────────────────────────────────


def test_no_confirmation_means_no_rate() -> None:
    """**The whole point.** Without somebody vouching for the denominator, a
    percentage over these rows is a wrong number with a plausible denominator —
    which is the failure this product exists to prevent, arriving from our own
    feature."""
    assert may_compute_a_rate(None) is False


def test_a_confirmation_permits_a_rate() -> None:
    assert may_compute_a_rate(CONFIRMED) is True


def test_the_gate_asks_about_the_confirmation_and_not_the_counts() -> None:
    """A rate is refused because nobody vouched for the denominator, never
    because the denominator is small. Two projects somebody confirmed are all of
    them is a real, computable rate over two things."""
    assert may_compute_a_rate(CONFIRMED) is True
    assert may_compute_a_rate(None) is False


def test_unvouched_is_the_inverse_and_drives_copy() -> None:
    """Named separately because `if not may_compute_a_rate(...)` on a tile that
    is showing a count reads as a statement about rates."""
    assert unvouched(None) is True
    assert unvouched(CONFIRMED) is False


# ── What it deliberately does not do ──────────────────────────


@pytest.mark.parametrize("years_ago", [1, 5, 20])
def test_an_old_confirmation_still_permits_a_rate(years_ago: int) -> None:
    """**No expiry, and that is a decision.** A founder who confirmed long ago
    and stopped recording has a record we were told was complete and probably is
    not — but an accurate list that simply stopped changing is indistinguishable
    from an abandoned one, and N days would be a threshold nobody set. ADR 0035
    rejects it as D29's staleness option; the mitigation is reporting the date.
    """
    stale = Confirmation(
        entity=PROJECTS,
        complete_as_of=date(2026 - years_ago, 9, 11),
        confirmed_on=date(2026 - years_ago, 9, 11),
    )

    assert may_compute_a_rate(stale) is True


def test_the_gate_takes_no_clock() -> None:
    """The corollary, asserted structurally: a function that cannot see today
    cannot grow an expiry without somebody changing its signature, which is a
    change a reviewer would see."""
    import inspect

    assert set(inspect.signature(may_compute_a_rate).parameters) == {"confirmation"}


# ── The confirmation itself ───────────────────────────────────


def test_the_two_dates_are_separate() -> None:
    """A founder catching up on Monday can honestly say the record was complete
    as of Friday. Reporting Monday would overstate how current the claim is."""
    assert CONFIRMED.complete_as_of < CONFIRMED.confirmed_on


def test_completeness_is_asked_per_entity() -> None:
    """Somebody can have recorded every project and a third of the tasks. One
    switch covering both would let the honest half vouch for the careless one."""
    # Two distinct entities, asserted through the set rather than by comparing
    # the two constants — they are `Final` literals, so mypy calls that
    # comparison non-overlapping and is right: it can never be false.
    assert ENTITIES == {PROJECTS, TASKS}
    assert len(ENTITIES) == 2


def test_a_confirmation_is_frozen() -> None:
    """It is a record of something somebody said. Editing one in place would
    rewrite what they said rather than adding what they say now — and the table
    is append-only for the same reason."""
    with pytest.raises(AttributeError):
        CONFIRMED.complete_as_of = date(2026, 1, 1)  # type: ignore[misc]
