"""All seven render states, each reachable and each with a distinct meaning.

`doc/12` P15. `WARMING` and `SELF_REPORTED` have existed in the enum since M5
and were unreachable in both layers — a state nothing can produce is a state
nobody has thought about, and it appears in code review as a handled case when
in fact it never happens.

The rule the whole ordering serves: **each state tells the founder something
different to do.** Two states that produce the same action should be one state,
and a state whose action is wrong is worse than no tile at all.
"""

from __future__ import annotations

from app.domain.dashboards import (
    STALE_AFTER_DAYS,
    WARMUP_DAYS,
    Offering,
    Source,
    WidgetState,
    state_for,
)

BUILT = "3.4"
NEEDS_TWO = Offering(id=BUILT, name="X", shows="Y", needs=(Source.DOCUMENTS, Source.GA4))
BOTH = frozenset({Source.DOCUMENTS, Source.GA4})


UNBUILT = Offering(id="unbuilt", name="X", shows="Y", needs=())

# Every call below states `reachable` because `state_for` requires it. It used
# to be read from a module-level `DELIVERED` set, which these tests patched —
# and a test that has to reach into the module under test to reach half its
# branches is telling you the fact belongs in the signature. It does now:
# `domain/registry.py` owns it, and this file asserts the ordering rather
# than the bookkeeping.


def test_an_unbuilt_widget_is_planned_whatever_is_connected() -> None:
    """An unbuilt widget cannot be unlocked by connecting anything, and saying
    otherwise is a promise the product would then break."""
    assert state_for(NEEDS_TWO, reachable=False, connected=BOTH) is WidgetState.PLANNED


def test_nothing_connected_is_locked() -> None:
    assert state_for(NEEDS_TWO, reachable=True, connected=frozenset()) is WidgetState.LOCKED


def test_some_connected_is_partial() -> None:
    assert (
        state_for(NEEDS_TWO, reachable=True, connected=frozenset({Source.GA4}))
        is WidgetState.PARTIAL
    )


def test_everything_connected_is_live() -> None:
    assert state_for(NEEDS_TWO, reachable=True, connected=BOTH) is WidgetState.LIVE


def test_connected_but_thin_history_is_warming_never_partial() -> None:
    """The distinction that matters most, and the reason `WARMING` exists.

    `PARTIAL` means *connect another source*. `WARMING` means *wait*. Telling
    somebody to connect something they already connected is how a product loses
    their trust in its own instructions.
    """
    # The assertion is only that it is `WARMING`. Adding `is not PARTIAL`
    # alongside it reads as a second check and is provably true from the first —
    # mypy says so, and a test that cannot fail is decoration.
    assert state_for(NEEDS_TWO, reachable=True, connected=BOTH, history_days=WARMUP_DAYS - 1) is (
        WidgetState.WARMING
    )


def test_enough_history_stops_warming() -> None:
    assert (
        state_for(NEEDS_TWO, reachable=True, connected=BOTH, history_days=WARMUP_DAYS)
        is WidgetState.LIVE
    )


def test_old_data_is_stale_not_live_and_not_unavailable() -> None:
    """Both halves.

    Not `LIVE`: a figure that was true last quarter reads as current unless the
    tile says otherwise, and somebody will decide on it. Not `UNAVAILABLE`
    either: the number is real and still worth seeing, with its age attached.
    """
    assert (
        state_for(NEEDS_TWO, reachable=True, connected=BOTH, age_days=STALE_AFTER_DAYS + 1)
        is WidgetState.STALE
    )
    assert (
        state_for(NEEDS_TWO, reachable=True, connected=BOTH, age_days=STALE_AFTER_DAYS)
        is WidgetState.LIVE
    )


def test_a_number_the_founder_typed_is_labelled() -> None:
    """A number they typed and a number we measured must never look identical.
    The second can contradict them; the first cannot."""
    assert (
        state_for(NEEDS_TWO, reachable=True, connected=BOTH, self_reported=True)
        is WidgetState.SELF_REPORTED
    )


def test_a_failed_generation_outranks_everything_below_it() -> None:
    """The inputs being present says nothing about whether the answer was
    computable. Rendering `LIVE` over a failed generation shows a tile with no
    number in it."""
    assert (
        state_for(NEEDS_TWO, reachable=True, connected=BOTH, unavailable_reason="budget_exhausted")
        is WidgetState.UNAVAILABLE
    )


def test_every_state_is_reachable() -> None:
    """A state nothing can produce is a state nobody has thought about — it
    reads as a handled case in review and never happens in fact. `WARMING` and
    `SELF_REPORTED` were exactly that until this phase."""

    produced = {
        state_for(NEEDS_TWO, reachable=True, connected=BOTH),
        state_for(NEEDS_TWO, reachable=True, connected=frozenset()),
        state_for(NEEDS_TWO, reachable=True, connected=frozenset({Source.GA4})),
        state_for(NEEDS_TWO, reachable=True, connected=BOTH, history_days=0),
        state_for(NEEDS_TWO, reachable=True, connected=BOTH, age_days=STALE_AFTER_DAYS + 1),
        state_for(NEEDS_TWO, reachable=True, connected=BOTH, self_reported=True),
        state_for(NEEDS_TWO, reachable=True, connected=BOTH, unavailable_reason="x"),
        state_for(UNBUILT, reachable=False, connected=BOTH),
    }
    assert produced == set(WidgetState), f"unreachable: {set(WidgetState) - produced}"


def test_the_optional_branches_stay_unreachable_unless_asked_for() -> None:
    """With only `connected` and `reachable` given, the four later branches
    cannot fire. Callers that know about history, age, self-report or a failed
    generation opt in; callers that do not get the three original states."""
    for connected in (frozenset(), frozenset({Source.GA4}), BOTH):
        assert state_for(NEEDS_TWO, reachable=True, connected=connected) in (
            WidgetState.LOCKED,
            WidgetState.PARTIAL,
            WidgetState.LIVE,
        )


# ── The two audits, and the argument a deleted test was making ─


def test_a_crawl_alone_makes_the_audits_partial_not_live() -> None:
    """**This replaces `test_marketing_delivered.py`, which asserted the opposite.**

    `domain/marketing.py::marketing_state` returned `LIVE` for a crawled
    workspace, and its test was called
    `test_the_audits_are_not_partial_versions_of_a_ga4_number`. The argument
    was good: calling a crawl-derived audit `PARTIAL` would imply GA4 improves
    it, and GA4 has nothing to do with either score.

    The argument survives; the state name does not. GA4 is in **neither**
    capability's `required_sources`, so it can never be what the tile is
    waiting for — that is asserted separately below. What each one is genuinely
    still missing is real: `seo_gaps` promises keyword volumes and difficulty
    it has no source for, and `brand_intelligence` promises voice consistency
    that needs documents and a model. `PARTIAL` says that, and the old `LIVE`
    claimed the whole capability was delivered when a third of it was.

    `partial` is also in `hasFigure`, so the figure still renders. Nothing is
    hidden by being honest about it.
    """
    from app.domain.dashboards import state_from_sources
    from app.domain.registry import BY_ID

    for capability_id in ("marketing.seo_gaps", "marketing.brand_intelligence"):
        capability = BY_ID[capability_id]
        assert Source.CRAWL in capability.required_sources

        crawled_only = state_from_sources(
            capability.required_sources, reachable=True, connected=frozenset({Source.CRAWL})
        )
        assert crawled_only is WidgetState.PARTIAL, capability_id

        # And with nothing at all, `locked` — the missing input is the crawl
        # itself, which is ours, so this is "we have not looked yet" rather
        # than "connect something".
        assert (
            state_from_sources(
                capability.required_sources, reachable=True, connected=frozenset()
            )
            is WidgetState.LOCKED
        )


def test_an_audit_unlock_never_names_ga4() -> None:
    """The half of the deleted test that was always the real claim.

    A founder told "connect GA4 to finish your SEO audit" would connect it and
    watch nothing change. `unlock_for_sources` reads `required_sources`, so the
    guarantee is structural rather than a matter of wording — but it is worth a
    test, because the wording is what somebody reads.
    """
    from app.domain.dashboards import unlock_for_sources
    from app.domain.registry import BY_ID

    for capability_id in ("marketing.seo_gaps", "marketing.brand_intelligence"):
        capability = BY_ID[capability_id]
        sentence = unlock_for_sources(
            capability.required_sources, connected=frozenset({Source.CRAWL})
        )
        assert sentence, f"{capability_id} is partial and must say what it waits on"
        assert "analytics" not in sentence.lower(), sentence
        assert "ga4" not in sentence.lower(), sentence


def test_connecting_ga4_changes_neither_audit() -> None:
    """The same claim from the other direction, and the cheaper one to break."""
    from app.domain.dashboards import state_from_sources
    from app.domain.registry import BY_ID

    for capability_id in ("marketing.seo_gaps", "marketing.brand_intelligence"):
        capability = BY_ID[capability_id]
        without = state_from_sources(
            capability.required_sources, reachable=True, connected=frozenset({Source.CRAWL})
        )
        with_ga4 = state_from_sources(
            capability.required_sources,
            reachable=True,
            connected=frozenset({Source.CRAWL, Source.GA4}),
        )
        assert without is with_ga4, capability_id
