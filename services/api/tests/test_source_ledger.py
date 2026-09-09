"""What a source turns on is derived, and what it cannot answer is stated.

`doc/13` §16. The claim the connect screen makes — *"connect Google Analytics
and six Marketing capabilities turn on"* — is a promise, and a hand-written
count is a promise nobody re-checks. Every number here is computed by inverting
`Capability.required_sources`.

Writing this file is what found the two dead connectors below.
"""

from __future__ import annotations

from dataclasses import fields

import pytest

from app.domain.connections import PROVIDERS
from app.domain.dashboards import LABELS, Source
from app.domain.registry import TILES
from app.domain.sources import (
    BY_SOURCE,
    CONNECTABLE,
    DAY_ONE,
    LEDGER,
    PROVIDER_SOURCES,
    Origin,
    SourceEntry,
    SourceLedgerError,
    _validate,
    contributes_to,
    source_for_provider,
    unlocks_now,
    will_unlock,
)

# Two connectors that no capability requires. Both are real gaps rather than
# mistakes in the ledger, and both are named here so that adding a **third**
# fails this test rather than passing quietly:
#
# - **`search_console`** — doc 05 §10 makes it part of Marketing's score and
#   doc 08 §2C's "Content & pages" section is impressions, positions and average
#   position, which is Search Console and nothing else. No doc 05 offering
#   carries it, so no capability lists it. **ADR 0023 makes it one of the first
#   two connectors to build**, which means the capability has to arrive with it
#   or the customer connects a tool that turns nothing on.
# - **`pagespeed`** — `calculators/audit.py` computes a performance score and
#   `doc/12` P18 promotes PageSpeed from the retired preview path, but there is
#   no `marketing.site_performance` capability for it to feed. The score exists
#   and has nowhere to be shown.
#
# The rule that kept them out of the table for now: a doc-08-only capability is
# admitted when a **question** declares it, and neither of these has one. They
# arrive with the section work (`doc/13` step D).
CONNECTORS_WITH_NOTHING_TO_UNLOCK = {Source.SEARCH_CONSOLE, Source.PAGESPEED}


# ── Totality ──────────────────────────────────────────────────


def test_every_source_has_a_ledger_row() -> None:
    """The guard the module exists for.

    A source in the enum with no row is a tile whose unlock sentence nobody has
    written — and the tile will still render, saying "needs" and then a phrase
    somebody invented at the call site.
    """
    assert set(BY_SOURCE) == set(Source)


def test_every_source_has_both_a_title_and_a_mid_sentence_label() -> None:
    """*"Needs Google Analytics 4."* reads worse in a sentence than "Needs Google
    Analytics."*, and the reverse is true as a heading. Two fields, both
    required, rather than one that is wrong in one of the two places."""
    for tool in LEDGER:
        assert tool.name
        assert LABELS[tool.source]


def test_the_ledger_refuses_a_source_that_claims_no_limits() -> None:
    """A source that answers everything in its area is one nobody has thought
    about, so the empty case is an import failure rather than a blank column."""
    for tool in LEDGER:
        assert tool.cannot_answer


def test_a_missing_row_is_an_import_error_not_a_blank_screen() -> None:
    """The validator, proved by breaking it — the same method the retrieval
    evals use. A guard that passes against a broken table certifies nothing."""
    without_crm = tuple(t for t in LEDGER if t.source is not Source.CRM)

    with pytest.raises(SourceLedgerError, match="crm"):
        _validate(without_crm)


# ── Origin: what kind of act unlocks it ───────────────────────


def test_only_connectors_appear_on_the_tools_screen() -> None:
    """Q44. Offering a Connect button for the website crawl, for the customer's
    own answers, or for *elapsed time* is nonsense — and the last one is why
    `WARMING` is a separate state from `LOCKED`: one asks for an act, the other
    asks them to wait."""
    assert all(t.origin is Origin.CONNECTOR for t in CONNECTABLE)
    assert {t.source for t in CONNECTABLE} == {
        t.source for t in LEDGER if t.origin is Origin.CONNECTOR
    }

    ours = {t.source for t in LEDGER if t.origin is Origin.OURS}
    assert DAY_ONE < ours, "everything onboarding produces is ours, and the ops layer too"


def test_history_is_time_and_the_language_model_is_a_key() -> None:
    """The two sources most likely to be mislabelled as connectors, because both
    look like integrations from the outside and neither has anything to click."""
    assert BY_SOURCE[Source.HISTORY].origin is Origin.TIME
    assert BY_SOURCE[Source.LANGUAGE_MODEL].origin is Origin.KEY


# ── What it turns on, derived ─────────────────────────────────


def test_no_connector_advertises_an_unlockable_capability_yet() -> None:
    """`doc/13` §16 rule 1, and today's honest answer is still zero.

    An unbuilt capability cannot be unlocked by connecting something, and
    `doc/04` §6 rule 1 makes a locked tile a call to action — so a false one is
    worse than no tile. The catalogue lives in `will_unlock`, which the tool's
    page may show as *coming*, never as *waiting for you*.

    **The premise narrowed when step D shipped.** This asserted that *nothing*
    was reachable, and Setup and the Watchlist now are — they read answers that
    already exist. They need no source at all, so they can never be something a
    connector unlocks, which is why the claim worth asserting is about the
    capabilities a connector actually feeds.
    """
    connector_fed = [c for c in TILES if c.required_sources]

    assert not any(c.reachable for c in connector_fed), (
        "nothing that needs a source is reachable yet — the tiles that are"
        " reachable need none, which is a different thing"
    )

    for tool in CONNECTABLE:
        assert unlocks_now(tool.source, connected=DAY_ONE) == ()


def test_the_reachable_capabilities_need_no_source_at_all() -> None:
    """The other half, and the reason the test above could narrow safely.

    A reachable capability that *did* need a source would mean a connector was
    advertising something openable, and the count on the connect screen would
    have to include it. Step D's two need nothing: they read what the workspace
    already holds, so an empty Setup tab is a fact about the answers rather than
    about our access.
    """
    reachable = [c for c in TILES if c.reachable]

    assert reachable, "step D shipped ten of them"
    assert all(not c.required_sources for c in reachable), sorted(
        c.id for c in reachable if c.required_sources
    )


def test_a_tool_never_claims_a_capability_that_needs_another_tool_too() -> None:
    """The claim that would promise the same tile twice.

    `sales.customer_health` needs a CRM **and** an accounting system **and**
    history. Connecting the CRM does not turn it on, and counting it under both
    connectors is how a founder connects two systems and finds the tile still
    locked.
    """
    for tool in CONNECTABLE:
        for capability in will_unlock(tool.source, connected=DAY_ONE):
            assert all(
                source in DAY_ONE or source == tool.source for source in capability.required_sources
            ), f"{tool.source.value} claims {capability.id}, which needs more than it"


def test_contributes_to_is_wider_than_will_unlock() -> None:
    """The two numbers, and why both exist.

    A CRM contributes to twelve capabilities and turns on six by itself. The
    first belongs on the tool's page — *this is what your CRM feeds* — and the
    second is the only one that may be phrased as a consequence of clicking
    Connect.
    """
    crm_alone = will_unlock(Source.CRM, connected=DAY_ONE)
    crm_total = contributes_to(Source.CRM)

    assert set(crm_alone) < set(crm_total)


def test_the_unlock_count_is_never_written_down() -> None:
    """`doc/13` §16 rule 1 as a structural check rather than a promise.

    A ledger row has no `unlocks` field, so there is nowhere to type a list of
    capability ids that could go stale. If one is ever added, this fails and the
    reviewer has to argue for it.
    """
    declared = {f.name for f in fields(SourceEntry)}

    assert "unlocks" not in declared
    assert not any(name.endswith("_capabilities") for name in declared)


# ── The gap this file found ───────────────────────────────────


def test_every_connector_turns_something_on_except_the_two_that_do_not() -> None:
    """Connecting a tool that feeds no capability is a dead end with a button on it.

    Two connectors are in exactly that position today, and the exception set
    above says why for each. The assertion is written as an equality rather than
    a skip so that a third one cannot join them silently — which is the failure
    mode that let these two sit in the enum unnoticed.
    """
    dead = {t.source for t in CONNECTABLE if not contributes_to(t.source)}

    assert dead == CONNECTORS_WITH_NOTHING_TO_UNLOCK, (
        "a connector with nothing behind it. Either a capability must declare"
        f" this source or the source should not be offered: {sorted(s.value for s in dead)}"
    )


# ── Providers, and the two promises the product cannot keep ───


def test_every_declarable_provider_maps_to_a_source() -> None:
    """Both directions.

    `domain/connections.py` offers nine providers in onboarding's tools step,
    and every one of them shows the customer a sentence saying what connecting
    it unlocks. A provider with no source behind it is a row in
    `workspace_connection` that no tile will ever read — the declaration is
    stored, the promise is displayed, and nothing consumes either.
    """
    assert set(PROVIDER_SOURCES) == {tool.id for tool in PROVIDERS}

    for tool in PROVIDERS:
        assert source_for_provider(tool.id) in BY_SOURCE


def test_four_crms_and_two_ledgers_collapse_to_two_sources() -> None:
    """Why providers and sources are separate tables rather than one.

    A capability needs *a CRM*; the customer has a particular one. Merging the
    two would mean `sales.pipeline_board` listing four alternatives it treats
    identically, and a fifth CRM becoming a change to every capability that
    reads a pipeline.
    """
    crms = {tool.id for tool in PROVIDERS if tool.kind == "crm"}

    assert len(crms) > 1
    assert {source_for_provider(provider) for provider in crms} == {Source.CRM}


def test_an_unmapped_provider_raises_rather_than_returning_nothing() -> None:
    """Returning `None` would let a provider nothing consumes pass as an
    ordinary absence, which is the failure mode the whole ledger exists to
    close."""
    with pytest.raises(SourceLedgerError, match="unlocks nothing"):
        source_for_provider("our_internal_thing")


def test_no_offered_provider_promises_more_than_the_product_can_deliver() -> None:
    """The finding, written as an assertion so that closing it is deliberate.

    Onboarding shows the customer nine tools, each with a sentence saying what
    connecting it unlocks. One of those sentences is backed by no capability at
    all: **Google Search Console** — *"Telling you which searches you already
    rank for, from your own data."* `Source.SEARCH_CONSOLE` is required by
    nothing, so declaring it turns on no tile, now or when OAuth lands. ADR 0023
    makes it one of the first two connectors to build, which is what makes this
    urgent rather than merely untidy.

    A promise made during onboarding is worse than a locked tile: a locked tile
    states what is missing, and this states what is coming.

    **Stripe is a different and softer problem** and deliberately not asserted
    here. It maps to `ACCOUNTING`, which backs twenty capabilities, so the
    sentence is honourable — but payments and bookkeeping are not the same
    source, and no capability distinguishes them. That is recorded in
    `PROVIDER_SOURCES` next to the mapping rather than as a failure.
    """
    unbacked = {tool.id for tool in PROVIDERS if not contributes_to(source_for_provider(tool.id))}

    assert unbacked == {"search_console"}, (
        f"a provider whose unlock sentence no capability can honour. Currently: {sorted(unbacked)}"
    )
