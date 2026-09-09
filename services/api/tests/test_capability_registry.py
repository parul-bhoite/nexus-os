"""Both numbers are derived. **No literal 6, no literal 21 or 24, anywhere.**

`doc/12` P15. A denominator written as a number is a claim nobody re-checks: it
was true when somebody counted, and it stays on screen after a department is
added or a company selects four. A founder who counts the tiles and gets a
different answer has found a reason to distrust every other number we show.
"""

from __future__ import annotations

from app.domain.registry import (
    BY_ID,
    REGISTRY,
    TILES,
    capabilities_for,
    completeness,
    consumers_of,
    score_denominator,
    scoreable_departments,
    scoreable_units,
)
from app.domain.scopes import Department


def test_the_denominator_follows_the_company_not_a_constant() -> None:
    """The property the whole module exists for."""
    # Three departments, **four** units: Sales brings Customers with it. The
    # denominator counts what is scored, not what was selected, and those stopped
    # being the same number when #27 was resolved.
    three = frozenset({Department.FINANCE, Department.SALES, Department.MARKETING})
    assert score_denominator(three) == 4

    one = frozenset({Department.FINANCE})
    assert score_denominator(one) == 1

    assert score_denominator(frozenset()) == 0, (
        "a company that has chosen nothing is scored out of nothing"
    )


def test_synthesis_layers_are_never_scored() -> None:
    """Chief of Staff and Strategy read the other departments. Scoring them
    counts the same work twice."""
    everything = frozenset(Department)
    scoreable = scoreable_departments(everything)

    assert Department.EXECUTIVE not in scoreable
    assert Department.STRATEGY not in scoreable


def test_the_denominator_is_six_because_customers_is_a_unit_without_a_page() -> None:
    """Finding #27, resolved. ADR 0010's six, derived rather than asserted.

    Five departments have a director page and are scored. Customers is the
    sixth: scored, and shown inside the Sales director because that is where
    the people who act on it already are.

    The test that used to live here asserted **five** and said to delete it if
    somebody resolved the discrepancy. This is that deletion, and the assertion
    it leaves behind is the one worth keeping — six, arrived at by counting
    units rather than by writing `6` down.
    """
    assert score_denominator(frozenset(Department)) == 6


def test_a_company_running_sales_is_scored_on_two_units() -> None:
    """One department, two units. That is ADR 0010's arrangement made real, and
    it is why the denominator was never going to equal the number of pages."""
    units = scoreable_units(frozenset({Department.SALES}))
    assert {u.value for u in units} == {"sales", "customers"}


def test_customers_is_not_a_department_anybody_belongs_to() -> None:
    """The reason it is a `ScoreableUnit` and not a `Department`.

    A department is something a person is *in*: it appears in onboarding
    selection, goes on a membership, and scopes L3 rows through RLS. Nobody is
    "in Customers", and adding it to that enum to fix a counting problem would
    have made it selectable, assignable and permission-bearing.
    """
    assert "customers" not in {d.value for d in Department}


def test_a_company_without_sales_is_not_scored_on_customers() -> None:
    """Customers depends on Sales running. Scoring it otherwise would judge a
    company on customer retention it has no function to manage."""
    units = scoreable_units(frozenset({Department.FINANCE}))
    assert {u.value for u in units} == {"finance"}


def test_completeness_returns_a_pair_not_a_percentage() -> None:
    """A percentage hides the denominator, and the denominator is the part that
    makes the claim checkable."""
    openable, total = completeness(frozenset(Department))
    assert total == len(TILES), (
        "the meter counts tiles. A rule shapes what other capabilities say and is"
        " not something a customer acquires, so it must not sit in the denominator"
        " making the meter unreachable by one for ever."
    )
    # Non-zero for the first time, and it is step D's ten. The meter read `0 of
    # 89` for the whole build until something a founder could actually open
    # existed — which is the honest number and a poor first impression, and the
    # reason the day-one sections were worth building before the first
    # connector.
    assert openable == len([c for c in TILES if c.reachable])
    assert openable > 0


def test_completeness_counts_only_what_the_company_can_reach() -> None:
    """A company running Finance alone should not be told it has completed 0 of
    67 — most of those belong to departments it does not have."""
    _, all_departments = completeness(frozenset(Department))
    _, finance_only = completeness(frozenset({Department.FINANCE}))

    assert finance_only < all_departments
    assert finance_only == len(capabilities_for(Department.FINANCE))


def test_every_offering_has_exactly_one_capability() -> None:
    """Two hand-maintained lists of the same thing is the failure this module
    prevents. Adding an offering must update the registry, the denominator and
    the completeness meter at once.

    The registry is now **larger** than the offering list, and deliberately: the
    doc-08-only capabilities are the ones the narrower cut specified and doc 05
    never did. So the invariant is one-to-one on the offerings rather than an
    equal count, and `test_capability_ids.py` holds the other direction —
    nothing in the registry claims a doc 05 number that no offering has.
    """
    from app.domain.dashboards import DIRECTORS

    offerings = sum(len(d.offerings) for d in DIRECTORS)
    from_doc05 = [c for c in REGISTRY if not c.doc08_only]

    assert len(from_doc05) == offerings
    assert len({c.doc05_id for c in from_doc05}) == offerings, "one capability per offering"


def test_the_only_openable_capabilities_are_the_two_that_read_answers_back() -> None:
    """The first thing in this product a person can open, and what it is.

    Everything computed is still `planned`: no route serves a figure. Setup and
    the Watchlist are different in kind — they read answers the founder has
    already given, so there is nothing to connect and nothing to calculate.

    There were three mechanisms for this one fact once —
    `dashboards.DELIVERED`, `registry.Capability.delivered` and
    `marketing.DELIVERED_MARKETING` — and they disagreed. One flag now, and the
    honesty of every "planned" label rests on it.
    """
    openable = {c.id for c in REGISTRY if c.reachable}

    assert openable, "step D's sections are openable, and the meter should say so"
    assert all(c.endswith((".setup", ".watchlist")) for c in openable), sorted(openable)
    assert "marketing.setup" in openable
    assert "executive.setup" not in openable, (
        "the Chief of Staff has no question block — it consumes the other"
        " directors rather than asking anything of its own"
    )


def test_the_marketing_audits_are_implemented_and_still_not_reachable() -> None:
    """The gap the unification exposed, kept as a test so closing it is deliberate.

    `calculators/audit.py` scores brand and technical SEO, and
    `domain/marketing.py` decides their state — but `marketing_state` is called
    from its own test and from nowhere else, so no user can open either tile.
    That is why `implemented` and `reachable` are two flags: a completeness
    meter counting the first would tell a founder they have two capabilities
    they cannot open.

    When the wiring lands, this test changes on purpose.
    """
    audits = {"marketing.seo_gaps", "marketing.brand_intelligence"}

    assert audits <= {c.id for c in REGISTRY if c.implemented}
    # Asserted about the audits specifically rather than about everything
    # implemented. Step D's sections are both implemented **and** reachable, so
    # the global form of this assertion stopped being the claim worth making the
    # moment anything shipped.
    assert not any(BY_ID[capability].reachable for capability in audits)


def test_impact_is_a_declared_dependency_not_a_guess() -> None:
    """Q59's input. A fact matters because things depend on it, and the
    dependency is declared rather than inferred from how often it is mentioned.

    Both halves, because for a while only the first was true: every call
    returned `()` because the question bank's ids and the registry's ids were
    different namespaces, and a ranking that scores everything zero looks
    exactly like a working feature.
    """
    assert consumers_of("a_fact_nothing_uses") == ()
    assert consumers_of("stale_deal_days") == ("sales.stale_deal_alert",)
    assert consumers_of("people_risk") == ("executive.risk_register",), (
        "a People question feeding an Executive capability — the cross-department"
        " case, which is most of why this mapping is worth having"
    )


# ── The shell carries its denominator (P15) ───────────────────


def test_the_shell_never_reports_a_score_of_zero() -> None:
    """I10. Nothing is delivered, so nothing is computable — and `0` would be a
    statement about the customer's business rather than about our data.

    This is the failure the whole phase guards against: a dashboard showing
    0/100 to a company that has simply connected nothing looks like a verdict.
    """
    from app.routes.dashboards import ShellOut

    shell = ShellOut(
        score=None, score_denominator=3, capabilities_delivered=0, capabilities_total=24
    )
    assert shell.score is None
    assert shell.score_denominator == 3, "the denominator travels with the score"


def test_the_assistant_panel_is_reserved_rather_than_absent() -> None:
    """Q67. A blank region where a feature is coming reads as a bug; a fake one
    reads as a lie. Reserved, with an honest empty state naming what it will do."""
    from app.routes.dashboards import ShellOut

    assert ShellOut(
        score=None, score_denominator=0, capabilities_delivered=0, capabilities_total=0
    ).assistant_reserved
