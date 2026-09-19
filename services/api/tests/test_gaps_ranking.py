"""`app.calculators.gaps` — the pre-signup ranking, proven against the real
morning brief rather than merely described as matching it.

Hermetic. `rank`/`top` are pure and the signals are built here, so this needs
no database — the same reasoning `test_brief_composition.py` states for why
that file runs in milliseconds.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path

from app.calculators import gaps
from app.calculators.audit import build_preview_audit
from app.domain.brief import compose
from app.domain.page_signals import PageSignals
from app.grounding.compute import Computation, compute_from_crawl
from app.retrieval.crawl import CrawlSnapshot

MEASURED_AT = datetime(2026, 9, 19, 10, 0, tzinfo=UTC)

# A page that fails a spread of checks at more than one weight, so the
# ranking has something to rank — modelled on test_brief_composition.py's
# POOR, not reused from it, so this file does not silently break if that
# fixture ever changes shape for a reason of its own.
POOR = PageSignals(
    url="http://gap-example.om/",
    title="A title that is far too long to be useful for a search result page listing",
    title_length=76,
    meta_description="x" * 168,
    meta_description_length=168,
    h1_texts=("one", "two"),
    h2_texts=("a", "b"),
    word_count=1178,
    is_https=False,
    has_canonical=True,
    canonical_url="https://gap-example.om/",
    has_structured_data=False,
    declared_language=None,
    robots_blocks_indexing=False,
    has_open_graph=False,
    has_viewport_meta=True,
    has_robots_meta=False,
    image_count=37,
    images_with_alt=0,
    internal_link_count=51,
    external_link_count=29,
    script_count=10,
    stylesheet_count=4,
    inline_style_count=2,
    html_bytes=63762,
    emails=("hello@gap-example.om",),
    has_phone=True,
    social_profiles=("facebook",),
)

# The two capabilities `brief.py`'s pipeline actually wires to `score_brand`
# and `score_technical_seo` (`app/grounding/compute.py:CRAWL_AUDITS`).
# `score_performance` is not wired to a capability id there today — a
# pre-existing gap in the brief pipeline, not one this change introduces —
# so the parity test below covers the two categories both systems can rank,
# not all three `build_preview_audit` produces.
BRIEF_CAPABILITY_IDS = ("marketing.brand_intelligence", "marketing.seo_gaps")


def _computations(signals: PageSignals) -> tuple[Computation, ...]:
    snapshot = CrawlSnapshot(
        signals=signals, url=signals.url, captured_at=MEASURED_AT, pages_captured=1
    )
    return tuple(
        computation
        for capability_id in BRIEF_CAPABILITY_IDS
        if (computation := compute_from_crawl(capability_id, snapshot)) is not None
    )


def test_gaps_rank_orders_by_points_lost_descending_then_check_id() -> None:
    audit = build_preview_audit(POOR)
    ranked = gaps.rank(audit.categories)

    weights = [check.weight for check in ranked]
    assert weights == sorted(weights, reverse=True)
    assert all(not check.passed for check in ranked)


def test_gaps_top_never_exceeds_n_and_never_pads() -> None:
    audit = build_preview_audit(POOR)
    assert len(gaps.top(audit.categories, 3)) <= 3

    # A page with nothing wrong yields zero gaps, not three invented ones.
    perfect = build_preview_audit(
        PageSignals(
            url="https://clean.om/",
            title="A usable page title",
            title_length=19,
            meta_description="y" * 120,
            meta_description_length=120,
            h1_texts=("the one heading",),
            h2_texts=("Our services", "Contact"),
            is_https=True,
            has_canonical=True,
            canonical_url="https://clean.om/",
            has_structured_data=True,
            declared_language="en",
            robots_blocks_indexing=False,
            has_open_graph=True,
            has_viewport_meta=True,
            has_robots_meta=True,
            image_count=4,
            images_with_alt=4,
            internal_link_count=6,
            external_link_count=1,
            word_count=400,
            emails=("hello@clean.om",),
            has_phone=True,
            social_profiles=("facebook", "instagram"),
        )
    )
    assert gaps.top(perfect.categories, 3) == ()


def test_gaps_rank_matches_brief_compose() -> None:
    """The parity this whole module exists for: the gap shown pre-signup and
    the top item in the post-signup morning brief are the same check, in the
    same words, for the same page.
    """
    audit = build_preview_audit(POOR)
    matched_categories = tuple(
        c for c in audit.categories if c.category in {"brand", "technical_seo"}
    )
    ranked = gaps.rank(matched_categories)

    brief = compose(
        _computations(POOR),
        expected=frozenset(BRIEF_CAPABILITY_IDS),
        unobserved=0,
    )
    brief_check_ids = [item.check_id for item in brief.items]

    assert [check.id for check in ranked] == brief_check_ids
    assert ranked, "the fixture must actually fail some checks or this proves nothing"


def test_the_check_count_is_derived_not_typed() -> None:
    """`doc/18` §1: the count is 23, derived here rather than typed anywhere
    — a fourth calculator or a widened one changes this number without
    anyone having to remember to update a literal."""
    audit = build_preview_audit(POOR)
    assert sum(len(c.checks) for c in audit.categories) == 23


def test_no_literal_check_count_is_hardcoded_in_the_scan_surface() -> None:
    """`doc/18` §1: "Anything downstream that says 27 is wrong; the figure is
    derived in G3's test rather than typed anywhere." Checked against both
    the backend package and (once G9 exists) the web UI, so a hardcoded `23`
    or the old, wrong `27` cannot slip into either without failing this.
    """
    api_root = Path(__file__).resolve().parents[1]
    scan_dirs = [api_root / "app" / "scan"]
    web_scan_dir = api_root.parents[1] / "apps" / "web" / "app" / "scan"
    if web_scan_dir.exists():
        scan_dirs.append(web_scan_dir)

    offenders: list[str] = []
    pattern = re.compile(r"(?<![0-9])(23|27)(?![0-9])")
    for scan_dir in scan_dirs:
        for path in sorted(scan_dir.rglob("*")):
            if not path.is_file() or path.suffix not in {".py", ".ts", ".tsx"}:
                continue
            for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
                if pattern.search(line):
                    offenders.append(f"{path}:{lineno}: {line.strip()}")

    assert offenders == [], "a literal check count appears in the scan surface:\n  " + "\n  ".join(
        offenders
    )
