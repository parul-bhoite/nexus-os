"""Preview audit scoring. Pure functions, no IO, no model.

**I1 — never invent a number.** Every score here is arithmetic over observed
signals, and every one returns the checks that produced it. **I9 — every number
is auditable**: the trace *is* the answer to "why are you telling me this?", so
it is returned alongside the score rather than reconstructed later.

Three categories only. Doc 06 §1.1 limits the pre-verification Preview to brand,
performance and technical SEO on the entered domain — no competitor discovery,
no keyword data, because those have intelligence value about third parties and
sit behind domain verification.

**Marketing, Sales, Finance, Operations and People are deliberately absent, not
zero.** Doc 05 §3.1 is explicit that Marketing is not scoreable without GA4, and
that Brand and SEO must not be merged into a Marketing score to manufacture a
number. A category with no evidence is `Locked`, never `0` (I10).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.domain.page_signals import PageSignals


@dataclass(frozen=True, slots=True)
class Check:
    """One observation and the points it contributed."""

    id: str
    label: str
    passed: bool
    weight: int
    evidence: str
    """What was actually observed. Never a recommendation."""


@dataclass(frozen=True, slots=True)
class CategoryScore:
    category: str
    score: int
    max_score: int
    checks: tuple[Check, ...] = field(default=())

    @property
    def percentage(self) -> int:
        if self.max_score == 0:
            return 0
        return round(self.score * 100 / self.max_score)


def _score(category: str, checks: list[Check]) -> CategoryScore:
    return CategoryScore(
        category=category,
        score=sum(c.weight for c in checks if c.passed),
        max_score=sum(c.weight for c in checks),
        checks=tuple(checks),
    )


def score_brand(signals: PageSignals) -> CategoryScore:
    """Is the company legible to a first-time visitor?"""
    checks = [
        Check(
            "brand.title",
            "Page has a title",
            bool(signals.title),
            10,
            f"title: {signals.title!r}" if signals.title else "no <title> element",
        ),
        Check(
            "brand.title_length",
            "Title is a usable length",
            10 <= signals.title_length <= 70,
            5,
            f"{signals.title_length} characters",
        ),
        Check(
            "brand.description",
            "Page has a meta description",
            bool(signals.meta_description),
            10,
            f"{signals.meta_description_length} characters",
        ),
        Check(
            "brand.h1",
            "Page states what the company does in a heading",
            len(signals.h1_texts) >= 1,
            10,
            f"{len(signals.h1_texts)} h1 element(s)",
        ),
        Check(
            "brand.single_h1",
            "Exactly one primary heading",
            len(signals.h1_texts) == 1,
            5,
            f"{len(signals.h1_texts)} h1 element(s)",
        ),
        Check(
            "brand.substance",
            "Page has enough copy to explain the business",
            signals.word_count >= 150,
            10,
            f"{signals.word_count} words",
        ),
        Check(
            "brand.contact",
            "A way to make contact is on the page",
            bool(signals.emails) or signals.has_phone,
            10,
            f"{len(signals.emails)} email(s), "
            f"phone {'found' if signals.has_phone else 'not found'}",
        ),
        Check(
            "brand.social",
            "Social profiles are linked",
            len(signals.social_profiles) > 0,
            5,
            f"{', '.join(signals.social_profiles) or 'none found'}",
        ),
        Check(
            "brand.open_graph",
            "Shares render with a preview card",
            signals.has_open_graph,
            5,
            "og:title present" if signals.has_open_graph else "no Open Graph tags",
        ),
    ]
    return _score("brand", checks)


def score_technical_seo(signals: PageSignals) -> CategoryScore:
    """Can a search engine index and understand the page?"""
    alt_coverage = signals.images_with_alt / signals.image_count if signals.image_count else 1.0
    checks = [
        Check(
            "seo.https",
            "Served over HTTPS",
            signals.is_https,
            10,
            "https" if signals.is_https else "http only",
        ),
        Check(
            "seo.indexable",
            "Page is not blocked from indexing",
            not signals.robots_blocks_indexing,
            15,
            "noindex present" if signals.robots_blocks_indexing else "indexable",
        ),
        Check(
            "seo.canonical",
            "Canonical URL is declared",
            signals.has_canonical,
            5,
            signals.canonical_url or "no canonical link",
        ),
        Check(
            "seo.description",
            "Meta description is a usable length",
            50 <= signals.meta_description_length <= 160,
            10,
            f"{signals.meta_description_length} characters",
        ),
        Check(
            "seo.structured_data",
            "Structured data is present",
            signals.has_structured_data,
            5,
            "JSON-LD found" if signals.has_structured_data else "no JSON-LD",
        ),
        Check(
            "seo.language",
            "Page language is declared",
            bool(signals.declared_language),
            5,
            signals.declared_language or "no lang attribute",
        ),
        Check(
            "seo.image_alt",
            "Images carry alternative text",
            alt_coverage >= 0.8,
            5,
            f"{signals.images_with_alt}/{signals.image_count} images"
            if signals.image_count
            else "no images",
        ),
        Check(
            "seo.internal_links",
            "Page links onward into the site",
            signals.internal_link_count >= 3,
            5,
            f"{signals.internal_link_count} internal links",
        ),
        Check(
            "seo.headings",
            "Content is structured with subheadings",
            len(signals.h2_texts) >= 2,
            5,
            f"{len(signals.h2_texts)} h2 elements",
        ),
    ]
    return _score("technical_seo", checks)


def score_performance(signals: PageSignals) -> CategoryScore:
    """Structural weight only — **not** a Core Web Vitals measurement.

    Lighthouse-grade metrics need the PageSpeed Insights API, which is not
    wired (`D3`). What is measured here is what the fetched HTML demonstrably
    contains: page weight and resource counts. It is labelled accordingly, and
    it deliberately does not claim to be a performance *grade* — presenting
    resource counts as a Core Web Vitals score would be inventing a number by
    relabelling a different one.
    """
    checks = [
        Check(
            "perf.mobile_viewport",
            "Declares a mobile viewport",
            signals.has_viewport_meta,
            15,
            "viewport meta present" if signals.has_viewport_meta else "no viewport meta",
        ),
        Check(
            "perf.html_weight",
            "HTML document is not oversized",
            signals.html_bytes <= 500_000,
            10,
            f"{signals.html_bytes / 1024:.0f} KB of HTML",
        ),
        Check(
            "perf.script_count",
            "Script count is moderate",
            signals.script_count <= 25,
            10,
            f"{signals.script_count} script tags",
        ),
        Check(
            "perf.stylesheets",
            "Stylesheet count is moderate",
            signals.stylesheet_count <= 8,
            5,
            f"{signals.stylesheet_count} stylesheets",
        ),
        Check(
            "perf.inline_styles",
            "Few inline style blocks",
            signals.inline_style_count <= 5,
            5,
            f"{signals.inline_style_count} inline style blocks",
        ),
    ]
    return _score("performance", checks)


@dataclass(frozen=True, slots=True)
class PreviewAudit:
    categories: tuple[CategoryScore, ...]
    locked_categories: tuple[str, ...]
    """Named, with what they need — never rendered as zero (I10)."""

    @property
    def overall(self) -> int:
        total = sum(c.score for c in self.categories)
        possible = sum(c.max_score for c in self.categories)
        return round(total * 100 / possible) if possible else 0

    @property
    def scored_count(self) -> int:
        return len(self.categories)


# What each locked category needs, so the UI can name the unlock rather than
# show an empty tile (doc 04 §6, doc 05 §0).
LOCKED_IN_PREVIEW: dict[str, str] = {
    "marketing": "Connect Google Analytics",
    "sales": "Connect your CRM",
    "finance": "Connect your accounting system",
    "operations": "Create your first project",
    "people": "Invite your team",
    "customer_experience": "Verify your domain to include review data",
    "competitors": "Verify your domain to discover competitors",
}


def build_preview_audit(signals: PageSignals) -> PreviewAudit:
    return PreviewAudit(
        categories=(
            score_brand(signals),
            score_technical_seo(signals),
            score_performance(signals),
        ),
        locked_categories=tuple(LOCKED_IN_PREVIEW),
    )
