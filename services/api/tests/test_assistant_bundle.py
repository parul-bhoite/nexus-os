"""The global assistant's grounding bundle: which figures reach it, and for whom.

ADR 0086. Fast and hermetic — `_assemble` is pure over snapshots the caller
hands it, so this needs no database and no model. It proves the extension that
widened the bundle beyond insights/brain/crawl to the **CRM pipeline** and the
**operations** figures, and that it is **scoped**: a caller sees in the assistant
only the figures their own dashboard would show them.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from uuid import uuid4

from app.calculators.pipeline import Deal
from app.domain.scopes import Department, Role
from app.domain.session import ScopedSession
from app.grounding import qa
from app.retrieval.deals import DealSnapshot
from app.retrieval.ops import OpsSnapshot

TODAY = date(2026, 10, 8)
FETCHED = datetime(2026, 10, 8, 9, 0, tzinfo=UTC)


def _scope(role: Role, *departments: Department) -> ScopedSession:
    return ScopedSession(
        user_id=uuid4(),
        tenant_id=uuid4(),
        workspace_id=uuid4(),
        role=role,
        departments=frozenset(departments),
    )


def _typed_deals() -> DealSnapshot:
    return DealSnapshot(
        deals=[
            Deal(
                external_id="d1",
                amount_minor=500_000,
                currency="OMR",
                stage="proposal",
                closes_on=None,
            ),
            Deal(
                external_id="d2",
                amount_minor=300_000,
                currency="OMR",
                stage="negotiation",
                closes_on=None,
            ),
        ],
        fetched_at=FETCHED,
        provider="nexus",
    )


def test_a_typed_pipeline_figure_reaches_the_bundle() -> None:
    computed, lines, labels = qa._assemble(
        _scope(Role.OWNER, *Department),
        (),  # insights
        None,  # brain
        None,  # crawl
        None,  # synced
        _typed_deals(),  # typed
        None,  # ops
        today=TODAY,
    )
    assert "sales.deals_lite" in labels
    assert any(key.startswith("sales.deals_lite.") for key in computed.values), computed.values
    # A readable line is produced for the model to quote from.
    assert lines and any(any(ch.isdigit() for ch in line) for line in lines)


def test_an_operations_figure_reaches_the_bundle() -> None:
    """An adopted-but-empty ops layer still produces zero-count figures — a real
    zero the dashboard shows, and the assistant may state."""
    computed, _lines, labels = qa._assemble(
        _scope(Role.OWNER, *Department),
        (),
        None,
        None,
        None,
        None,
        OpsSnapshot(projects=[], tasks=[]),
        today=TODAY,
    )
    assert any(label.startswith("operations.") for label in labels), labels
    assert any(key.startswith("operations.") for key in computed.values)


def test_a_caller_who_cannot_reach_sales_gets_no_pipeline_figure() -> None:
    """The scope filter: the assistant never grounds on a figure the reader's own
    dashboard would not show them. A marketing-only contributor sees no Sales
    pipeline figure, even with deals present."""
    computed, _lines, labels = qa._assemble(
        _scope(Role.CONTRIBUTOR, Department.MARKETING),
        (),
        None,
        None,
        None,
        _typed_deals(),
        None,
        today=TODAY,
    )
    assert "sales.deals_lite" not in labels
    assert not any(key.startswith("sales.") for key in computed.values)
