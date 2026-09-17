"""I1 at the new boundary: the dispatch that turns a crawl into a figure.

`app/grounding/compute.py` is the first code in this product to put a computed
number on a path that ends at a screen. Doc 07 §5.3 says write the invariant
test before the feature it guards, and the invariant here is the one the whole
product sells on: **every number is fetched or computed in code.** So these
tests assert that `Computed.values` contains the calculator's arithmetic and
nothing else, and that the trace is a real account of that arithmetic rather
than a plausible one.

Pure. No database, no model, no session — which is itself the assertion in
`test_the_dispatch_needs_no_session`: a dispatch that needed a connection would
have to be called once per tile, and the route reads once per request.
"""

from __future__ import annotations

import inspect
from datetime import UTC, datetime

import pytest

from app.calculators import audit
from app.domain.page_signals import PageSignals
from app.domain.registry import CAPABILITIES, TILES
from app.grounding.compute import (
    CRAWL_AUDITS,
    OPS_CENSUSES,
    PIPELINE_TALLIES,
    compute_from_crawl,
    computes,
)
from app.retrieval.crawl import CrawlSnapshot

CAPTURED_AT = datetime(2026, 9, 3, 9, 30, tzinfo=UTC)


def signals() -> PageSignals:
    """A page good enough to pass some checks and fail others.

    A page that passed everything would hide a scoring bug that always returns
    `max_score`, and one that failed everything would hide the inverse.
    """
    return PageSignals(
        url="https://muscat-marine.om/",
        is_https=True,
        title="Marine engine repair in Muscat",
        title_length=31,
        meta_description="Dry-dock maintenance and engine overhaul for Omani fleets.",
        meta_description_length=57,
        h1_texts=("Marine engine repair",),
        has_viewport_meta=True,
        has_canonical=True,
        declared_language="en",
        image_count=10,
        images_with_alt=4,
        internal_link_count=18,
        word_count=640,
        h2_texts=("Dry dock", "Overhaul"),
    )


def snapshot() -> CrawlSnapshot:
    return CrawlSnapshot(
        signals=signals(),
        url="https://muscat-marine.om/",
        captured_at=CAPTURED_AT,
        pages_captured=6,
    )


@pytest.fixture(params=sorted(CRAWL_AUDITS))
def capability_id(request: pytest.FixtureRequest) -> str:
    """Every audited capability, so adding a third does not add an untested one."""
    return str(request.param)


# ── I1: the only permitted numbers ────────────────────────────


def test_every_number_in_computed_came_from_the_calculator(capability_id: str) -> None:
    """The set is exact, not a superset.

    `>=` would let a convenience value in — a ratio, a rounded copy, a
    "previous" figure with nothing behind it — and `answer._permitted` treats
    everything in `values` as a number the model is allowed to write. So an
    extra key here is a licence to state a figure no calculator produced.

    **It grew from three to five when narration landed, and the reason has to
    survive the growth.** `BlockCard` renders "6 of 9 checks passed" three
    lines above where the narrated sentence goes. With only score, max_score
    and percentage permitted, a narrator writing "6 of 9" was refused as
    `INVENTED_NUMBER` — whose meaning is *"the model stated a figure no
    calculation produced"*. That is a false accusation, rendered to the
    customer, about the most sensitive claim this product makes, and it was the
    easiest outcome in the enum to trigger.

    Both additions are calculator outputs: `Computation.checks_passed` counts
    the passing checks, `checks_total` is the length of the calculator's own
    list. Nothing derived, nothing rounded, no "previous". The honest cost is
    that `9` and `65` become numerals the prose may state in an unrelated
    sense — which is why this widened by exactly two named outputs rather than
    by everything that would be convenient.
    """
    result = compute_from_crawl(capability_id, snapshot())
    assert result is not None

    assert set(result.computed.values) == {
        "score",
        "max_score",
        "percentage",
        "checks_passed",
        "checks_total",
    }
    assert result.computed.values["score"] == float(result.score.score)
    assert result.computed.values["max_score"] == float(result.score.max_score)
    assert result.computed.values["percentage"] == float(result.score.percentage)
    assert result.computed.values["checks_passed"] == float(result.checks_passed)
    assert result.computed.values["checks_total"] == float(len(result.score.checks))


def test_the_figure_is_complete_so_the_pipeline_will_not_refuse_it(capability_id: str) -> None:
    """`pipeline.run` checks `computed.complete` before any model call and
    returns `MISSING_INPUT` when it is False. A crawl-backed audit always has
    every input it needs — the page either had the tag or it did not — so a
    `missing` entry here would mean the dispatch invented an absence."""
    result = compute_from_crawl(capability_id, snapshot())
    assert result is not None
    assert result.computed.missing == ()
    assert result.computed.complete is True


def test_the_score_never_exceeds_its_denominator(capability_id: str) -> None:
    result = compute_from_crawl(capability_id, snapshot())
    assert result is not None
    assert 0 <= result.score.score <= result.score.max_score
    assert result.score.max_score > 0, "a zero denominator makes the percentage meaningless"


# ── The trace is a real account, not a plausible one ──────────


def test_the_trace_names_a_method_that_actually_exists(capability_id: str) -> None:
    """`trace["method"]` is what the drawer shows as the provenance of the
    number. A string naming a function that does not exist is worse than no
    string, because it reads as verifiable and is not."""
    result = compute_from_crawl(capability_id, snapshot())
    assert result is not None

    method = result.trace["method"]
    assert method.startswith("calculators.audit."), method
    resolved = getattr(audit, method.rsplit(".", 1)[1], None)
    assert callable(resolved), f"{method} does not resolve to a callable in calculators.audit"
    assert resolved is CRAWL_AUDITS[capability_id].calculator


def test_the_trace_carries_every_check_that_produced_the_score(capability_id: str) -> None:
    """Not a sample. The drawer's claim is that it shows the working, and nine
    checks summarised as three is a different claim."""
    result = compute_from_crawl(capability_id, snapshot())
    assert result is not None

    assert len(result.trace["checks"]) == len(result.score.checks)
    for recorded, check in zip(result.trace["checks"], result.score.checks, strict=True):
        assert recorded["id"] == check.id
        assert recorded["evidence"] == check.evidence
        assert recorded["passed"] is check.passed
        assert recorded["weight"] == check.weight


def test_the_trace_arithmetic_agrees_with_the_score(capability_id: str) -> None:
    """The numerator and denominator in the trace are the ones in the figure.

    Two places holding the same number is two places it can drift, and the
    drawer is precisely where a reader would catch us at it.
    """
    result = compute_from_crawl(capability_id, snapshot())
    assert result is not None

    assert result.trace["numerator"] == result.score.score
    assert result.trace["denominator"] == result.score.max_score
    assert result.trace["percentage"] == result.score.percentage
    assert sum(c.weight for c in result.score.checks if c.passed) == result.score.score


def test_the_trace_names_the_page_and_when_it_was_fetched(capability_id: str) -> None:
    """A score whose page cannot be opened is a number nobody can check, which
    for a reader is the same as one we made up."""
    result = compute_from_crawl(capability_id, snapshot())
    assert result is not None

    assert result.trace["page"] == "https://muscat-marine.om/"
    assert result.source_url == "https://muscat-marine.om/"
    assert result.measured_at == CAPTURED_AT
    assert "2026-09-03" in result.trace["window"]


def test_the_trace_carries_the_keys_narrate_reads() -> None:
    """Slice 2 wires `narrate`, which reads `method`, `window` and the working.

    Asserting the shape now means slice 2 is wiring rather than reshaping — and
    a trace that lost `window` would degrade a narrated sentence silently.
    """
    result = compute_from_crawl(next(iter(CRAWL_AUDITS)), snapshot())
    assert result is not None
    for key in (
        "method",
        "window",
        "delta",
        "checks",
        "numerator",
        "denominator",
        "page",
        "measures",
    ):
        assert key in result.trace, f"narrate and ledger.record expect trace[{key!r}]"


# ── What it refuses to do ─────────────────────────────────────


def test_a_capability_with_no_calculator_computes_nothing() -> None:
    """`None`, not a zero-scored `Computation`.

    I10: a zero would say this company scored nothing, where the truth is that
    nobody has written the calculation. The two must not be the same object.
    """
    assert computes("marketing.growth_planner") is False
    assert compute_from_crawl("marketing.growth_planner", snapshot()) is None


def test_an_unknown_capability_id_computes_nothing() -> None:
    assert computes("not.a.capability") is False
    assert compute_from_crawl("not.a.capability", snapshot()) is None


def test_the_dispatch_needs_no_session() -> None:
    """Pure, and asserted so it stays pure.

    The moment this takes a session it has to be awaited per tile, and the
    route's single read per request becomes N reads — the shape
    `director_setup` deliberately avoids.
    """
    parameters = inspect.signature(compute_from_crawl).parameters
    assert "db" not in parameters
    assert "scope" not in parameters
    assert not inspect.iscoroutinefunction(compute_from_crawl)


# ── The dispatch and the registry cannot drift ────────────────


def test_every_dispatched_capability_is_reachable_and_implemented() -> None:
    """A calculator wired to a capability the route will not serve is dead code
    that looks live; the reverse is a tile that promises a figure and renders a
    disabled button.

    **All three dispatches, iterated rather than named.** This asserted
    `CRAWL_AUDITS` alone for two slices, while `PIPELINE_TALLIES` and then
    `OPS_CENSUSES` carried docstrings claiming they were guarded "in both
    directions, exactly as `CRAWL_AUDITS` is" — which was false in the only
    direction that catches a dispatch nobody wired up. A new dict added to
    `compute.py` and not to this tuple is the way that comes back, so the
    companion test below asserts the tuple is complete.
    """
    by_id = {c.id: c for c in CAPABILITIES}
    for dispatch in (CRAWL_AUDITS, PIPELINE_TALLIES, OPS_CENSUSES):
        for capability_id in dispatch:
            capability = by_id.get(capability_id)
            assert capability is not None, f"{capability_id} is not in the registry"
            assert capability.implemented, f"{capability_id} is dispatched but not implemented"
            assert capability.reachable, f"{capability_id} is dispatched but not reachable"


def test_the_guard_above_covers_every_dispatch() -> None:
    """`computes()` is the product's own answer to "is there a calculator", so
    every id it accepts must be an id the guard above checked. A fourth dispatch
    added to `computes()` and forgotten in that tuple would make the guard pass
    by not looking."""
    guarded = set(CRAWL_AUDITS) | set(PIPELINE_TALLIES) | set(OPS_CENSUSES)
    for capability in CAPABILITIES:
        if computes(capability.id):
            assert capability.id in guarded, (
                f"{capability.id} computes but no dispatch in the guard above holds it — "
                f"add the new dict to both."
            )


def test_every_reachable_tile_either_computes_or_has_its_own_endpoint() -> None:
    """The converse, and the one that catches the real mistake.

    `state_from_sources` reaches `live`/`partial` by the *absence* of
    contradicting evidence, not by the presence of a number — so a tile added
    to `_REACHABLE` with no calculator renders a figure state with no figure,
    which is a disabled drawer and a blank space where a number belongs.

    `setup` and `watchlist` are the standing exception: `DirectorPage` routes
    those two tab keys to `SetupSection` and they never reach `BlockCard`.
    """
    for capability in TILES:
        if not capability.reachable:
            continue
        if capability.id.endswith((".setup", ".watchlist")):
            continue
        # `computes()` rather than `CRAWL_AUDITS`, because there are two
        # dispatches now (ADR 0033) and the question this asks is whether
        # *anything* computes the tile. Asserted against the crawl dict alone,
        # it failed the day a capability computed an amount — correctly by its
        # own wording and wrongly by its intent.
        assert computes(capability.id), (
            f"{capability.id} is reachable but nothing computes it — it will render a "
            f"figure state with no figure. Add a calculator, or take it out of _REACHABLE."
        )


def test_the_label_is_not_the_capability_name(capability_id: str) -> None:
    """The guard against a correct number under a misdescribing headline.

    `score_brand` measures site legibility while `brand_intelligence` promises
    voice consistency; `score_technical_seo` measures nine checks while
    `seo_gaps` promises keyword volumes too. `measures` is what stops the
    figure being read as an answer to the wider question, so it has to say
    something, and it has to say what was *not* counted.
    """
    result = compute_from_crawl(capability_id, snapshot())
    assert result is not None

    assert result.label, "a figure with no label cannot say what it measured"
    assert len(result.measures) > 40, "measures has to name what was counted, not gesture at it"
    assert "Not " in result.measures, (
        "measures must name what this figure does NOT cover, or the tile's wider "
        "promise reads as delivered"
    )


# ── What the narrator is told about comparison ────────────────


def test_a_single_crawl_declares_no_baseline_rather_than_an_empty_delta(
    capability_id: str,
) -> None:
    """`SKILL.md` distinguishes three absences and this is one of them.

    `narrate` sends `delta: trace.get("delta", "")`, and the runner's
    `requires_grounding` check passes on a present-but-empty key — so the model
    received `delta: ''` and had to guess what that meant. The prompt already
    handles the real case verbatim: *"`no_baseline` — there is nothing to
    compare against. Say so. Never call it flat, which claims a comparison you
    did not make."*

    Set in the calculator rather than defaulted in `narrate`, because it is the
    calculator that knows it scored one snapshot. A default there would make a
    future calculator that genuinely computed a zero delta and forgot to record
    it silently assert that we did not compare when we did — the exact inverse
    of the rule above.
    """
    result = compute_from_crawl(capability_id, snapshot())
    assert result is not None

    assert result.trace["delta"] == "no_baseline"
    # No numeral in it, which is why it is safe to send. When re-crawling makes
    # a real delta possible, a delta the prose may state has to go into
    # `computed.values` too, or the invented-number guard rejects every
    # sentence that mentions it.
    assert not any(character.isdigit() for character in str(result.trace["delta"]))


def test_the_narrator_is_never_given_a_fact_value() -> None:
    """**Why a workspace-wide narration read-back is safe.**

    The plan for this slice assumed both audits had empty `consumes_facts`, and
    that a workspace-wide read of stored prose was safe because of it. That
    assumption was wrong: `marketing.seo_gaps` consumes `arabic_in_scope`,
    which is `Scope.L3_DEPARTMENT` — a Marketing fact. The one-line guard
    written to check the assumption is what caught it.

    The read is safe anyway, for a narrower and better-founded reason.
    `narrate` sends the model exactly six grounding keys — label, value, unit,
    window, sources, delta — and **not one of them is a fact.** The consumed
    fact goes into `input_snapshot`, which is stored on the row and never sent
    to the provider, so the model cannot write a value it was never shown. The
    read-back then selects `prose` and five `calculation_trace` keys and
    **never `input_snapshot`** (asserted where that query lives).

    So the invariant is not "an audited capability consumes no facts" — it is
    "the narrator is given no facts, and the display read does not carry the
    ones we stored". Both halves are checkable, which the original assumption
    was not.

    The day the narrator *is* given facts — to say why a number moved, which is
    what `because` is for — this test fails, and the read-back has to be scoped
    before it can pass again. That is the intended tripwire.
    """
    from app.ai.runtime.skills import get_registry
    from app.grounding.answer import NARRATOR

    required = set(get_registry().get(NARRATOR).requires_grounding)

    assert required == {"label", "value", "unit", "window", "sources", "delta"}
    for key in required:
        assert "fact" not in key, key

    # And the skill cannot persist anything it was given, so a fact reaching it
    # by some future route still could not be written back as an answer.
    assert get_registry().get(NARRATOR).writes == ()
