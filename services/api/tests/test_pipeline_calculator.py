"""The pipeline calculator — `doc/14` step 9.

Pure arithmetic over deals, and every test here is about a way of being wrong
that would still render a plausible number:

- **A total that silently dropped unpriced deals.** "OMR 148,000 across 23
  deals" reads as complete, and is not, if three of them have no value on them.
- **A zero standing in for "could not add these up".** I10 at the money level.
- **Two currencies added together.** Needs a rate; a rate needs a source and a
  date, and a total built on one nobody can see is the number this product
  exists not to produce.
- **A stage match that quietly shrinks the pipeline.** A customer renaming a
  stage must not make deals disappear from a figure.

Hermetic and instant — `calculators/` is pure by construction.
"""

from __future__ import annotations

from datetime import date

from app.calculators.pipeline import Deal, Pipeline, compute_pipeline

TODAY = date(2026, 9, 17)


def deal(
    external_id: str = "1",
    *,
    amount_minor: int | None = 1_000_00,
    currency: str | None = "OMR",
    stage: str | None = "proposal",
    closes_on: date | None = None,
) -> Deal:
    return Deal(
        external_id=external_id,
        amount_minor=amount_minor,
        currency=currency,
        stage=stage,
        closes_on=closes_on,
    )


def _pipeline(deals: list[Deal]) -> Pipeline:
    return compute_pipeline(deals, today=TODAY)


# ── The total, and what it leaves out ─────────────────────────


def test_it_totals_the_open_deals() -> None:
    result = _pipeline([deal("1", amount_minor=31_500_00), deal("2", amount_minor=11_300_00)])

    assert result.open_deals == 2
    assert result.total_minor == 42_800_00
    assert result.currency == "OMR"
    assert result.unpriced == 0


def test_an_unpriced_deal_is_counted_and_never_added_as_zero() -> None:
    """**A deal nobody has priced is not a deal worth nothing.** It is in the
    count, out of the total, and reported — because a total that did not say how
    many deals it left out is a total presented as complete."""
    result = _pipeline(
        [deal("1", amount_minor=31_500_00), deal("2", amount_minor=None, currency=None)]
    )

    assert result.open_deals == 2
    assert result.priced == 1
    assert result.unpriced == 1
    assert result.total_minor == 31_500_00


def test_a_pipeline_of_only_unpriced_deals_totals_nothing_rather_than_zero() -> None:
    """I10 at the money level. Zero would say these deals are worth nothing;
    `None` says nobody has priced them, and the count still stands."""
    result = _pipeline([deal("1", amount_minor=None, currency=None)])

    assert result.open_deals == 1
    assert result.total_minor is None
    assert result.currency is None
    assert result.unpriced == 1


def test_an_empty_pipeline_is_not_the_same_as_an_unpriced_one() -> None:
    """No deals at all is a real, reportable state — and a different sentence
    from "we could not add these up"."""
    result = _pipeline([])

    assert result.open_deals == 0
    assert result.unpriced == 0
    assert result.total_minor is None


# ── Currency ──────────────────────────────────────────────────


def test_two_currencies_cannot_be_totalled() -> None:
    """Adding them needs a rate; a rate needs a source and a date. A total built
    on one nobody can see is exactly the figure this product refuses."""
    result = _pipeline(
        [deal("1", amount_minor=10_000_00, currency="OMR"), deal("2", currency="USD")]
    )

    assert result.open_deals == 2
    assert result.total_minor is None
    assert result.currency is None


def test_the_count_survives_a_currency_mix() -> None:
    """The total is unanswerable; how many deals are open is not. Losing both
    would throw away a true figure to avoid a false one."""
    result = _pipeline(
        [deal("1", currency="OMR"), deal("2", currency="USD"), deal("3", currency="OMR")]
    )

    assert result.open_deals == 3


def test_the_currency_is_the_providers_and_is_reported_with_the_total() -> None:
    """A number with no currency beside it is a number a reader will assume is
    theirs. HubSpot's deals are in whatever the portal uses, which is not
    necessarily the workspace's reporting currency."""
    result = _pipeline([deal("1", amount_minor=5_000_00, currency="AED")])

    assert (result.total_minor, result.currency) == (5_000_00, "AED")


# ── Which deals are in the pipeline at all ────────────────────


def test_closed_deals_are_not_in_the_pipeline() -> None:
    result = _pipeline(
        [deal("1", stage="proposal"), deal("2", stage="closedwon"), deal("3", stage="closedlost")]
    )

    assert result.open_deals == 1


def test_a_renamed_stage_does_not_silently_leave_the_pipeline() -> None:
    """**The failure that shrinks a figure without anybody noticing.** Matching
    a `closed` prefix would drop "Closed - pending paperwork", which a customer
    considers very much still open."""
    result = _pipeline([deal("1", stage="Closed - pending paperwork")])

    assert result.open_deals == 1


def test_stage_matching_ignores_case() -> None:
    result = _pipeline([deal("1", stage="ClosedWon")])

    assert result.open_deals == 0


def test_a_deal_with_no_stage_is_treated_as_open() -> None:
    """The alternative is dropping it, and a deal missing from a pipeline is
    worse than one counted in a stage nobody set."""
    result = _pipeline([deal("1", stage=None)])

    assert result.open_deals == 1


# ── The ninety-day window ─────────────────────────────────────


def test_it_counts_what_closes_inside_ninety_days() -> None:
    result = _pipeline(
        [
            deal("1", closes_on=date(2026, 10, 1)),
            deal("2", closes_on=date(2026, 12, 31)),
            deal("3", closes_on=None),
        ]
    )

    assert result.closing_within_90_days == 1


def test_a_date_already_past_is_not_closing_soon() -> None:
    """An overdue close date is a data-quality problem, not a forecast. Counting
    it forward would put deals in a window they left."""
    result = _pipeline([deal("1", closes_on=date(2026, 9, 1))])

    assert result.closing_within_90_days == 0


def test_the_window_is_measured_from_a_date_passed_in() -> None:
    """`today` is an argument so the boundary is testable without freezing the
    clock — the same reason `manual_runs_this_month` takes a `now`, and the same
    lesson M33 taught about tests that encode the current moment."""
    closing = [deal("1", closes_on=date(2026, 12, 1))]

    assert compute_pipeline(closing, today=date(2026, 9, 17)).closing_within_90_days == 1
    assert compute_pipeline(closing, today=date(2026, 1, 1)).closing_within_90_days == 0


def test_it_is_not_a_forecast() -> None:
    """No probability, no weighting by stage. `sales.forecast` requires
    `history`, which this capability does not have — and a weighted figure
    presented beside an unweighted one would be read as the same kind of
    number."""
    result = _pipeline([deal("1", amount_minor=10_000_00, stage="appointmentscheduled")])

    assert result.total_minor == 10_000_00
    assert not hasattr(result, "weighted")
    assert not hasattr(result, "probability")
