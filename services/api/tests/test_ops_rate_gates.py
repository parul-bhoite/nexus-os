"""The two gates in front of the first ops rate — `doc/15` S10.4, ADR 0036.

`operations.on_time_dispatch` is the only ops figure that divides, and it may
divide only when both are open:

1. **Somebody vouched that the record is all of it** (ADR 0035). Otherwise the
   denominator may be a third of reality, and the percentage is a wrong number
   with a plausible denominator.
2. **Somebody said what late means here** (D32). `late_definition` is collected
   as free prose and there is no parser; a number we chose would be a threshold
   the customer never agreed to.

They refuse for different reasons and the tile has to say which, so these assert
the reason and not merely the absence.

Hermetic: the dispatch takes a snapshot, never a session.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from uuid import uuid4

from app.calculators.completeness import DISPATCHES, SUPPLIERS, Confirmation
from app.grounding.compute import RateRefusal, compute_rate_from_ops
from app.retrieval.ops import DispatchRecord, OpsSnapshot, SupplierRecord

RATE = "operations.on_time_dispatch"
TODAY = date(2026, 9, 17)
VOUCHED = {
    DISPATCHES: Confirmation(
        entity=DISPATCHES, complete_as_of=date(2026, 9, 11), confirmed_on=date(2026, 9, 14)
    )
}


def _order(promised: date, sent: date | None) -> DispatchRecord:
    return DispatchRecord(
        id=uuid4(), project_id=None, reference="SO-1", promised_on=promised, dispatched_on=sent
    )


def _snapshot(
    *,
    dispatches: list[DispatchRecord] | None = None,
    grace: int | None = None,
    confirmations: dict[str, Confirmation] | None = None,
) -> OpsSnapshot:
    return OpsSnapshot(
        projects=[],
        tasks=[],
        dispatches=dispatches if dispatches is not None else [_order(TODAY, TODAY)],
        grace_days=grace,
        confirmations=confirmations or {},
        recorded_at=datetime(2026, 9, 14, tzinfo=UTC),
    )


# ── Both gates shut, and which one is named ───────────────────


def test_an_unvouched_record_refuses_and_says_so() -> None:
    result = compute_rate_from_ops(RATE, _snapshot(grace=0), today=TODAY)

    assert result is not None
    assert result.refused is RateRefusal.UNVOUCHED
    assert result.parts.percentage is not None, "the calculator still computes it"


def test_no_rule_refuses_even_when_the_record_is_vouched_for() -> None:
    """Knowing the denominator covers everything does not tell us what the
    numerator means."""
    result = compute_rate_from_ops(RATE, _snapshot(confirmations=VOUCHED), today=TODAY)

    assert result is not None
    assert result.refused is RateRefusal.NO_RULE


def test_completeness_is_checked_before_the_rule() -> None:
    """**Order matters for the message, not the outcome.** Both missing is the
    first-run state, and telling somebody to set a grace period when we also
    cannot trust their denominator sends them to do the less useful of the two
    jobs first."""
    result = compute_rate_from_ops(RATE, _snapshot(), today=TODAY)

    assert result is not None
    assert result.refused is RateRefusal.UNVOUCHED


def test_nothing_sent_is_its_own_refusal() -> None:
    """The customer has done everything asked and there is still no rate, so it
    is named separately — there is nothing left for them to do about it."""
    result = compute_rate_from_ops(
        RATE,
        _snapshot(dispatches=[_order(TODAY, None)], grace=0, confirmations=VOUCHED),
        today=TODAY,
    )

    assert result is not None
    assert result.refused is RateRefusal.NOTHING_SENT
    assert result.parts.percentage is None


def test_both_gates_open_shows_the_rate() -> None:
    result = compute_rate_from_ops(
        RATE,
        _snapshot(
            dispatches=[_order(TODAY, TODAY), _order(TODAY, date(2026, 9, 20))],
            grace=0,
            confirmations=VOUCHED,
        ),
        today=TODAY,
    )

    assert result is not None
    assert result.refused is None
    assert result.parts.percentage == 50.0


# ── What a refusal may and may not publish ────────────────────


def test_a_refusal_publishes_no_numerator_for_the_prose_to_state() -> None:
    """**`answer._permitted` treats every key in `values` as a numeral the model
    may write.** A numerator published while the tile refuses would be a figure
    the model could write about and a reader could never see."""
    refused = compute_rate_from_ops(RATE, _snapshot(grace=0), today=TODAY)

    assert refused is not None
    assert set(refused.computed.values) == {"outstanding", "overdue", "excluded"}


def test_the_rate_publishes_both_halves_when_it_is_shown() -> None:
    shown = compute_rate_from_ops(RATE, _snapshot(grace=0, confirmations=VOUCHED), today=TODAY)

    assert shown is not None
    assert set(shown.computed.values) == {
        "outstanding",
        "overdue",
        "excluded",
        "numerator",
        "denominator",
        "percentage",
    }


def test_the_counts_are_served_under_every_refusal() -> None:
    """They are counts, true either way. Withholding them along with the rate
    would tell a founder nothing when we can honestly tell them something."""
    waiting = [_order(date(2026, 9, 1), None), _order(date(2026, 12, 1), None)]
    result = compute_rate_from_ops(RATE, _snapshot(dispatches=waiting), today=TODAY)

    assert result is not None
    assert result.refused is RateRefusal.UNVOUCHED
    assert (result.parts.outstanding, result.parts.overdue) == (2, 1)


def test_the_trace_records_which_gate_was_shut() -> None:
    """The working drawer has to be able to say why, not just that."""
    result = compute_rate_from_ops(RATE, _snapshot(confirmations=VOUCHED), today=TODAY)

    assert result is not None
    assert result.trace["refused"] == "no_rule"
    assert result.trace["grace_days"] is None


def test_a_capability_nothing_rates_is_none() -> None:
    assert compute_rate_from_ops("operations.projects_board", _snapshot(), today=TODAY) is None


# ── The second rate: supplier concentration ───────────────────


CONCENTRATION = "operations.supplier_risk"
VOUCHED_SUPPLIERS = {
    SUPPLIERS: Confirmation(
        entity=SUPPLIERS, complete_as_of=date(2026, 9, 11), confirmed_on=date(2026, 9, 14)
    )
}


def _supplier(name: str, spend: int | None) -> SupplierRecord:
    return SupplierRecord(id=uuid4(), name=name, category=None, spend_minor=spend)


def _with_suppliers(
    suppliers: list[SupplierRecord], *, confirmations: dict[str, Confirmation] | None = None
) -> OpsSnapshot:
    return OpsSnapshot(
        projects=[],
        tasks=[],
        suppliers=suppliers,
        reporting_currency="OMR",
        confirmations=confirmations or {},
        recorded_at=datetime(2026, 9, 14, tzinfo=UTC),
    )


def test_concentration_refuses_until_the_supplier_list_is_vouched_for() -> None:
    """**The gate doing real work.** Three of ten suppliers recorded would
    otherwise report one of them as 60% of the company's exposure."""
    result = compute_rate_from_ops(
        CONCENTRATION, _with_suppliers([_supplier("Al Bahja", 60_000)]), today=TODAY
    )

    assert result is not None
    assert result.refused is RateRefusal.UNVOUCHED


def test_concentration_has_no_second_gate_to_pass() -> None:
    """Unlike on-time dispatch, a share of spend needs no threshold — there is
    no "late" to define. Vouched is enough."""
    result = compute_rate_from_ops(
        CONCENTRATION,
        _with_suppliers(
            [_supplier("Al Bahja", 60_000), _supplier("Gulf", 40_000)],
            confirmations=VOUCHED_SUPPLIERS,
        ),
        today=TODAY,
    )

    assert result is not None
    assert result.refused is None
    assert result.parts.percentage == 60.0
    assert result.parts.currency == "OMR", "money, so the client can format it"


def test_suppliers_with_no_spend_refuse_for_their_own_reason() -> None:
    """Distinct from `NOTHING_SENT`: the thing to do about it is enter what you
    spend, not wait."""
    result = compute_rate_from_ops(
        CONCENTRATION,
        _with_suppliers([_supplier("Al Bahja", None)], confirmations=VOUCHED_SUPPLIERS),
        today=TODAY,
    )

    assert result is not None
    assert result.refused is RateRefusal.NOTHING_PRICED


def test_an_unpriced_supplier_is_reported_rather_than_dropped() -> None:
    """Counted in the population, outside the denominator, and said so (I10)."""
    result = compute_rate_from_ops(
        CONCENTRATION,
        _with_suppliers(
            [_supplier("Al Bahja", 60_000), _supplier("Gulf", None)],
            confirmations=VOUCHED_SUPPLIERS,
        ),
        today=TODAY,
    )

    assert result is not None
    assert result.parts.excluded == 1


def test_the_two_rates_do_not_share_a_completeness_confirmation() -> None:
    """Vouching for your orders says nothing about your supplier list."""
    snapshot = OpsSnapshot(
        projects=[],
        tasks=[],
        dispatches=[_order(TODAY, TODAY)],
        suppliers=[_supplier("Al Bahja", 60_000)],
        grace_days=0,
        confirmations=VOUCHED,
        recorded_at=datetime(2026, 9, 14, tzinfo=UTC),
    )

    dispatch = compute_rate_from_ops(RATE, snapshot, today=TODAY)
    supplier = compute_rate_from_ops(CONCENTRATION, snapshot, today=TODAY)

    assert dispatch is not None and supplier is not None
    assert dispatch.refused is None
    assert supplier.refused is RateRefusal.UNVOUCHED
