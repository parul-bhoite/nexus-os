"""A stored sentence must stop being shown the moment the figure moves.

**The failure this exists to prevent is the worst one this product can have**,
and it is not a crash: prose written about 45 out of 65 rendered beside a fresh
39 out of 65. Both halves are individually true, the sentence is well written,
and nothing on the screen says they are about different measurements. A reader
would act on it.

So `describes()` compares five fields, not one, and every one of them earns its
place — the tests below are named for the case each catches. Written before the
function, because the two cases a naive implementation gets wrong (a changed
denominator behind an unchanged percentage, and a re-crawl with an identical
score) both look like matches.
"""

from __future__ import annotations

from datetime import UTC, datetime

from app.calculators.audit import Check
from app.domain.narration import StoredNarration, describes
from app.grounding.compute import compute_from_crawl
from app.grounding.pipeline import Computed
from app.retrieval.crawl import CrawlSnapshot
from tests.test_grounding_compute import signals, snapshot

NARRATED_AT = datetime(2026, 9, 9, 10, 0, tzinfo=UTC)


def stored(**overrides: object) -> StoredNarration:
    """A narration of the figure `snapshot()` produces.

    Built from the real computation rather than from literals, so the fixture
    cannot drift away from what the calculator actually scores — which would
    make every test here pass against a match that never happens in production.
    """
    computation = compute_from_crawl("marketing.seo_gaps", snapshot())
    assert computation is not None
    base: dict[str, object] = {
        "module": "marketing.seo_gaps",
        "prose": "Most of the technical checks pass on the page we fetched.",
        "prompt_version": "1",
        "narrated_at": NARRATED_AT,
        "numerator": str(computation.score.score),
        "denominator": str(computation.score.max_score),
        "percentage": str(computation.score.percentage),
        "page": str(computation.trace["page"]),
        "window": str(computation.trace["window"]),
    }
    base.update(overrides)
    return StoredNarration(**base)  # type: ignore[arg-type]


def current() -> object:
    computation = compute_from_crawl("marketing.seo_gaps", snapshot())
    assert computation is not None
    return computation


def test_a_narration_of_this_exact_figure_still_describes_it() -> None:
    assert describes(stored(), current()) is True  # type: ignore[arg-type]


def test_a_moved_numerator_stops_describing_it() -> None:
    """The obvious case, and the only one a one-field check catches."""
    assert describes(stored(numerator="39"), current()) is False  # type: ignore[arg-type]


def test_a_changed_denominator_stops_describing_it_even_at_the_same_percentage() -> None:
    """**45/65 and 9/13 are both 69%.**

    A percentage-only check passes here, and the prose is wrong: a changed
    denominator means the calculator changed scale, so a sentence about
    "most of the checks" was written against a different set of them.
    """
    assert round(45 * 100 / 65) == round(9 * 100 / 13)

    assert (
        describes(stored(numerator="9", denominator="13"), current())  # type: ignore[arg-type]
        is False
    )


def test_a_changed_percentage_stops_describing_it() -> None:
    """`percentage` is in `computed.values`, which makes it a numeral the prose
    is **permitted to state**. A rounding change would leave the numerator
    matching and a stated percentage wrong."""
    assert describes(stored(percentage="70"), current()) is False  # type: ignore[arg-type]


def test_the_same_score_on_a_different_page_stops_describing_it() -> None:
    """45 out of 65 on the home page and 45 out of 65 on the pricing page are
    the same number about different things — and the prose may name the page."""
    assert (
        describes(stored(page="https://muscat-marine.om/pricing"), current())  # type: ignore[arg-type]
        is False
    )


def test_a_recrawl_with_an_identical_score_stops_describing_it() -> None:
    """**The case a naive implementation gets wrong.**

    Nothing about the figure changed, so every numeric field still matches —
    but the page was fetched again on a later date, and `window` is the only
    place that date lives. The prose may cite it ("as of 3 September"), and a
    sentence citing a date we have since replaced is a false statement about
    when we looked.
    """
    assert (
        describes(
            stored(window="the page as fetched on 2026-09-01"),
            current(),  # type: ignore[arg-type]
        )
        is False
    )


def test_an_unrecognised_trace_fails_closed() -> None:
    """`->>` returns `None` for a missing key, and `None` never equals a `str`.

    Which is the direction that matters: a trace shape we cannot read means we
    cannot prove the sentence still applies, and the honest answer to that is
    to stop showing it rather than to assume.
    """
    for field in ("numerator", "denominator", "percentage", "page", "window"):
        assert describes(stored(**{field: None}), current()) is False, field  # type: ignore[arg-type]


def test_a_different_capabilitys_narration_never_describes_this_figure() -> None:
    """Both audits score the same page, so `page` and `window` match and only
    the module differs. Without this the read-back could pair Brand
    Intelligence's sentence with SEO Intelligence's score."""
    other = compute_from_crawl("marketing.brand_intelligence", snapshot())
    assert other is not None
    assert describes(stored(), other) is False


def test_a_prompt_version_change_still_describes_the_figure() -> None:
    """**Deliberately True.**

    Editing `SKILL.md` changes the voice, not the truth. Gating on it would
    blank every sentence in the product the moment somebody fixed a typo in the
    prompt, with no cause a reader could see. The version is carried through and
    shown in the working drawer instead, so a disputed sentence still traces to
    the instructions that produced it.
    """
    assert describes(stored(prompt_version="2"), current()) is True  # type: ignore[arg-type]


def test_a_reworded_sentence_still_describes_the_figure() -> None:
    """The prose itself is not part of the comparison. What is being asked is
    "does this sentence describe this figure", not "is this the sentence we
    would write today"."""
    assert describes(stored(prose="Something else entirely."), current()) is True  # type: ignore[arg-type]


def test_the_comparison_reads_strings_and_never_casts() -> None:
    """`json.dumps` wrote `45`, `->>` reads back `"45"`, and `str(45)` is `"45"`.

    Casting to `int` would raise on a malformed trace and turn a staleness
    check into a 500 on the dashboard — so a garbage value must be a mismatch,
    not an exception.
    """
    assert describes(stored(numerator="not a number"), current()) is False  # type: ignore[arg-type]


def test_a_score_of_zero_is_a_figure_and_not_an_absence() -> None:
    """I10 cuts both ways here. A page that failed every check scores 0 out of
    65, which is a real measurement, and a narration of it must stay attached —
    a falsy-check implementation would treat `"0"` as missing and blank it."""
    bare = CrawlSnapshot(
        signals=signals(),
        url="https://muscat-marine.om/",
        captured_at=snapshot().captured_at,
        pages_captured=1,
    )
    zeroed = compute_from_crawl("marketing.seo_gaps", bare)
    assert zeroed is not None

    matching = stored(
        numerator=str(zeroed.score.score),
        denominator=str(zeroed.score.max_score),
        percentage=str(zeroed.score.percentage),
    )
    assert describes(matching, zeroed) is True


def test_it_needs_no_session_and_no_computed() -> None:
    """Pure, and asserted pure: the read-back runs it once per tile inside a
    request that has already spent its round trips."""
    import inspect

    parameters = inspect.signature(describes).parameters
    assert list(parameters) == ["stored", "computation"]
    assert not inspect.iscoroutinefunction(describes)
    # It reads the computation, never a `Computed` — the permitted-values set is
    # `pipeline`'s business, not staleness's.
    assert Computed not in {p.annotation for p in parameters.values()}


def test_the_check_dataclass_is_the_calculators_and_not_restated() -> None:
    """A guard on the import, so a future refactor cannot quietly give
    `describes` its own idea of what a check is."""
    assert Check.__module__ == "app.calculators.audit"
