"""Typed deals and synced deals share a table and never share a figure.

`doc/15` S10.6, ADR 0038 (D30). `sales.deals_lite` reuses `crm_deal` with
`provider = 'nexus'` rather than adding a table, and **the whole safety of that
reuse is the partition**: without it a hand-typed deal reaches
`sales.pipeline_board` and is reported as though a CRM had said so — a typed
number and a measured one rendered identically, silently, with no symptom.

These assert the partition at the layer a reader can check it: which population
each capability's figure is built from, and what it claims about where the
number came from. The SQL half is asserted against a real database in
`test_ops_write_db.py`.
"""

from __future__ import annotations

from datetime import UTC, datetime

from app.calculators.pipeline import Deal
from app.domain.registry import BY_ID
from app.retrieval.deals import TYPED, DealSnapshot
from app.routes.dashboards import AmountFigureOut, amount_figure_out

FETCHED = datetime(2026, 9, 14, tzinfo=UTC)

SYNCED = DealSnapshot(
    deals=[
        Deal(external_id="hs-1", amount_minor=100_000, currency="OMR", stage="new", closes_on=None)
    ],
    fetched_at=FETCHED,
    provider="crm",
)
HAND_TYPED = DealSnapshot(
    deals=[
        Deal(
            external_id="uuid-1",
            amount_minor=50_000,
            currency="OMR",
            stage="quoted",
            closes_on=None,
        ),
        Deal(
            external_id="uuid-2",
            amount_minor=25_000,
            currency="OMR",
            stage="quoted",
            closes_on=None,
        ),
    ],
    fetched_at=FETCHED,
    provider=TYPED,
)


def _figure(
    capability_id: str,
    *,
    deals: DealSnapshot | None = None,
    typed: DealSnapshot | None = None,
) -> AmountFigureOut | None:
    return amount_figure_out(BY_ID[capability_id], deals, typed)


def test_the_pipeline_board_counts_only_what_a_provider_reported() -> None:
    """**The failure this exists to prevent.** Two typed deals must not appear in
    a figure a reader takes as their CRM's."""
    figure = _figure("sales.pipeline_board", deals=SYNCED, typed=HAND_TYPED)

    assert figure is not None
    assert figure.count == 1
    assert figure.self_reported is False


def test_deals_lite_counts_only_what_somebody_typed() -> None:
    figure = _figure("sales.deals_lite", deals=SYNCED, typed=HAND_TYPED)

    assert figure is not None
    assert figure.count == 2
    assert figure.self_reported is True


def test_a_workspace_with_only_typed_deals_has_no_pipeline_board_figure() -> None:
    """The ordinary case for a customer with no CRM: one tile, not two, and the
    CRM tile stays locked rather than reporting their own typing back."""
    assert _figure("sales.pipeline_board", typed=HAND_TYPED) is None


def test_a_workspace_with_only_synced_deals_has_no_deals_lite_figure() -> None:
    assert _figure("sales.deals_lite", deals=SYNCED) is None


def test_both_populations_produce_both_figures_and_neither_absorbs_the_other() -> None:
    """A founder who typed deals and later connected a CRM. Not a state we design
    for, but one they can reach, and the totals must stay apart."""
    board = _figure("sales.pipeline_board", deals=SYNCED, typed=HAND_TYPED)
    lite = _figure("sales.deals_lite", deals=SYNCED, typed=HAND_TYPED)

    assert board is not None and lite is not None
    assert board.total_minor == 100_000
    assert lite.total_minor == 75_000


def test_the_two_figures_are_the_same_kind() -> None:
    """ADR 0038: the standing differs, the shape does not. Splitting the union
    again would spend its one mechanism — a new kind fails to compile at every
    consumer — on something that is not a new kind."""
    board = _figure("sales.pipeline_board", deals=SYNCED, typed=HAND_TYPED)
    lite = _figure("sales.deals_lite", deals=SYNCED, typed=HAND_TYPED)

    assert board is not None and lite is not None
    assert board.kind == lite.kind == "amount"


def test_the_typed_figure_says_the_records_are_the_customers_own() -> None:
    """`self_reported` is what decides the sentence. A tile claiming a provider
    read somebody's own typing is the specific lie this slice could ship."""
    lite = _figure("sales.deals_lite", typed=HAND_TYPED)

    assert lite is not None
    assert lite.self_reported is True
    assert "your own records" in lite.measures.lower()
