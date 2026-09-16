"""The three coverage bands, and the two ways they could quietly lie.

ADR 0030. The dashboard's opening figure is *"2 of 89 capabilities produce a
figure today"*, split into what measures, what reads a founder's own answers
back, and what is not built. Every one of those numbers was estimated in the
first draft of the design and **every one was wrong** — the denominator counted
a `RULE`, and a band called "unlockable by answering" held seven capabilities
when the true figure is zero. These are the assertions that stop that happening
in code rather than in a mock.

Two failures are worth naming, because neither shows on screen:

**A band that drops a capability.** Three counts that do not sum to the
denominator still render as three plausible numbers. `Coverage.__post_init__`
raises, and the tests below prove the guard fires rather than trusting it.

**An injected set that drifts from the real one.** `coverage` takes `measured`
rather than importing it, because `domain` importing `grounding` would run the
dependency backwards. That injection is only honest while the caller passes the
real set, so the agreement is asserted here — the same both-directions rule
`grounding/compute.py` already states for calculators and reachability.

Hermetic. The registry is a table built at import; nothing here needs a database.
"""

from __future__ import annotations

import pytest

from app.domain.registry import (
    CAPABILITIES,
    TILES,
    CapabilityKind,
    CapabilityRegistryError,
    Coverage,
    completeness,
    coverage,
    openable_count,
)
from app.domain.scopes import Department
from app.grounding.compute import CRAWL_AUDITS

EVERY = frozenset(Department)
MEASURED = frozenset(CRAWL_AUDITS)


# ── The denominator, which three functions now share ──────────


def test_every_coverage_number_is_counted_over_the_same_denominator() -> None:
    """**Three counters, one denominator.**

    `completeness`, `openable_count` and `coverage` all answer a version of
    "how much of this product do I have?", and a customer seeing 2 of 89 beside
    12 of 90 has been given two facts that cannot both be true. Asserted rather
    than left to three docstrings agreeing by hand.
    """
    assert coverage(MEASURED, EVERY).total == completeness(EVERY)[1] == len(TILES)


def test_the_denominator_excludes_the_one_rule() -> None:
    """A `RULE` shapes what other capabilities say and is not something a
    customer acquires. `completeness` excludes it and says why — putting it in
    the denominator would make the meter unreachable by one for ever — and the
    first draft of the coverage design counted 90 because it read `CAPABILITIES`
    instead of `TILES`."""
    rules = [c for c in CAPABILITIES if c.kind is CapabilityKind.RULE]

    assert len(rules) == 1, "a second rule needs this test read again, not edited"
    assert coverage(MEASURED, EVERY).total == len(CAPABILITIES) - len(rules)


# ── The bands themselves ──────────────────────────────────────


def test_the_bands_account_for_every_capability() -> None:
    bands = coverage(MEASURED, EVERY)

    assert bands.measuring + bands.reading_back + bands.not_built == bands.total


def test_a_band_that_lost_a_capability_raises_rather_than_rendering() -> None:
    """Three counts that do not sum still render as three plausible numbers, and
    nothing on the screen would look wrong. The guard is in `__post_init__` so
    the object cannot exist in that state at all."""
    with pytest.raises(CapabilityRegistryError, match="do not sum"):
        Coverage(measuring=2, reading_back=10, not_built=76, total=89)


def test_the_measuring_band_counts_what_can_be_opened_not_what_was_written() -> None:
    """**`reachable`, not `implemented`** — `completeness`'s argument, applied
    to the first band.

    The two came apart once: Marketing's audits had a real calculation and no
    route serving it. Counting `implemented` during that window would have told
    a founder they held two capabilities they could not open, and a capability
    that computes but cannot be reached is dead code rather than coverage.
    """
    unreachable_calculators = {c.id for c in TILES if c.id in MEASURED and not c.reachable}
    bands = coverage(MEASURED, EVERY)

    assert bands.measuring == len({c.id for c in TILES if c.reachable} & MEASURED)
    assert not unreachable_calculators, (
        "a calculator exists for a capability no route serves — dead code that "
        "would now also inflate the dashboard's headline number"
    )


def test_reading_back_is_the_rest_of_what_is_reachable() -> None:
    """The Setup and Watchlist tabs. Real, reachable, and deliberately not
    figures: doc 05 §0 requires that a number somebody typed and a number we
    measured never look alike, so they cannot be folded into the first band to
    make it look larger."""
    bands = coverage(MEASURED, EVERY)

    assert bands.reading_back == openable_count() - bands.measuring


def test_not_built_is_ours_and_is_most_of_the_product() -> None:
    """The honest headline. If this ever reads as a small number while the other
    two are small too, a band has stopped being counted."""
    bands = coverage(MEASURED, EVERY)

    assert bands.not_built == len(TILES) - openable_count()
    assert bands.not_built > bands.measuring + bands.reading_back


# ── Scope, because the dashboard is per viewer ────────────────


def test_a_department_manager_is_counted_over_their_own_departments() -> None:
    """The surface says *where the product is, **for you***. A Marketing-only
    manager counted over all 89 would be shown a denominator of capabilities
    they cannot open, which is the same over-claim the whole region exists to
    avoid — and `completeness` already takes `selected` for this reason."""
    theirs = coverage(MEASURED, frozenset({Department.MARKETING}))

    assert theirs.total == len([c for c in TILES if c.department is Department.MARKETING])
    assert theirs.total < coverage(MEASURED, EVERY).total


def test_a_department_with_no_calculator_measures_nothing_rather_than_erroring() -> None:
    """Zero is the right answer here and is not an I10 violation: nothing is
    standing in for an absence, because the absence *is* the fact. The tile-level
    rule still holds — no capability renders a zero-scored figure."""
    assert coverage(MEASURED, frozenset({Department.SALES})).measuring == 0


def test_no_department_selected_is_an_empty_count_not_a_crash() -> None:
    bands = coverage(MEASURED, frozenset())

    assert bands == Coverage(measuring=0, reading_back=0, not_built=0, total=0)


# ── The injected set, which is the honest half of the design ──


def test_the_measured_set_the_caller_passes_is_the_one_grounding_holds() -> None:
    """**The guard on the injection.**

    `coverage` takes `measured` instead of importing it, so `domain` does not
    depend on `grounding`. That is only honest while the set passed in is the
    real one — otherwise the argument has become a second list of what computes,
    which is the failure the registry module exists to end.

    Asserted against `CRAWL_AUDITS` directly, and every id in it must be a real
    capability: a calculator wired to an id the table does not hold would be
    counted into the headline and found by nothing else.
    """
    from app.domain.registry import BY_ID

    assert MEASURED, "nothing computes, so the first band can only ever be zero"
    assert all(capability_id in BY_ID for capability_id in MEASURED), sorted(
        capability_id for capability_id in MEASURED if capability_id not in BY_ID
    )
