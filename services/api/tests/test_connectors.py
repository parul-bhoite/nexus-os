"""What a connection cannot compute, said at connect — and what happens when it stops.

The two tests `doc/12` P18 names. Neither needs D3's Google credentials or D10's
CRM choice, and both cover the failures that are hardest to see later.
"""

from __future__ import annotations

from app.domain.connectors import (
    CRM_FIELD_REQUIREMENTS,
    ConnectionState,
    check_completeness,
    state_for_connection,
)
from app.domain.dashboards import WidgetState
from app.domain.registry import BY_ID

EVERYTHING = frozenset({"last_activity_at", "amount", "stage_canonical", "loss_reason"})


def test_connect_reports_what_cannot_be_calculated() -> None:
    """doc 05 §9. A CRM without `last_activity_at` disables stale-deal detection
    **at connect**, not later through an empty widget.

    The difference is between a limitation and a bug. A customer told now can
    add the field or accept the gap; a customer who finds out through an empty
    widget has learned that our widgets come up empty.
    """
    result = check_completeness(EVERYTHING - {"last_activity_at"})

    assert not result.fully_supported
    unsupported = dict(result.unsupported)
    # The tile's own name, read from the capability table. It used to be
    # "Stale deal detection" here and "Stale and at-risk deals" on the dashboard
    # — two names for one thing, which reads as two features.
    stale = BY_ID["sales.stale_deal_alert"].name
    assert stale in unsupported
    assert "last_activity_at" in unsupported[stale], (
        "the reason must name the field, because a field name is actionable and "
        "'unavailable' is not"
    )

    # And everything else still works. A partial connection is not a failed one.
    assert BY_ID["sales.pipeline_board"].name in result.supported


def test_a_complete_connection_reports_no_gaps() -> None:
    result = check_completeness(EVERYTHING)
    assert result.fully_supported
    assert len(result.supported) == len(CRM_FIELD_REQUIREMENTS)


def test_every_unsupported_capability_says_which_field_is_missing() -> None:
    """Exhaustive: no capability may be refused without naming its cause."""
    result = check_completeness(frozenset())
    assert len(result.unsupported) == len(CRM_FIELD_REQUIREMENTS)
    for name, reason in result.unsupported:
        assert "needs" in reason, name


def test_a_revoked_token_degrades_the_tile_to_stale_not_to_zero() -> None:
    """The number we last saw was real; what stopped is our ability to refresh it.

    Zero would claim their pipeline emptied overnight — a statement about their
    business made out of a statement about our access.
    """
    state = state_for_connection(
        ConnectionState.REVOKED, had_data=True, age_days=1, stale_after_days=7
    )
    # Only `is STALE`. I wrote `is not LIVE` beside it and mypy refused: it is
    # provably true from the line above, and a test that cannot fail is
    # decoration. Second time this session — the instinct to restate the point
    # in the assertion belongs in the docstring, where it already is.
    assert state is WidgetState.STALE


def test_a_revoked_token_is_never_live_however_fresh_the_cache() -> None:
    """ "Live" is a claim about now, and we no longer have access to now."""
    assert (
        state_for_connection(ConnectionState.REVOKED, had_data=True, age_days=0, stale_after_days=7)
        is WidgetState.STALE
    )


def test_a_reduced_scope_is_treated_as_seriously_as_a_revocation() -> None:
    """The dangerous case. A downgraded scope returns data that parses, looks
    valid, and is silently incomplete — right about totals and wrong about
    everything time-based, with nothing to indicate which."""
    assert (
        state_for_connection(
            ConnectionState.SCOPE_REDUCED, had_data=True, age_days=0, stale_after_days=7
        )
        is WidgetState.STALE
    )


def test_a_revocation_before_any_data_locks_rather_than_going_stale() -> None:
    """Nothing was ever read, so there is nothing to go stale. `LOCKED` names the
    missing connection rather than implying an old number exists somewhere."""
    assert (
        state_for_connection(
            ConnectionState.REVOKED, had_data=False, age_days=0, stale_after_days=7
        )
        is WidgetState.LOCKED
    )


def test_a_healthy_connection_still_goes_stale_on_age_alone() -> None:
    assert (
        state_for_connection(
            ConnectionState.CONNECTED, had_data=True, age_days=8, stale_after_days=7
        )
        is WidgetState.STALE
    )
    assert (
        state_for_connection(
            ConnectionState.CONNECTED, had_data=True, age_days=1, stale_after_days=7
        )
        is WidgetState.LIVE
    )
