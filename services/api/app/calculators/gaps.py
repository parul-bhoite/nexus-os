"""The pre-signup gap ranking — extracted from `domain/brief.py:compose`. G3.

Pure, no IO, no model (I1). Ranks the checks that failed across a
`PreviewAudit`'s categories by points lost, descending, tie-broken by check
id — the exact key `brief.py:compose`'s `failures.sort` already uses for the
morning brief. That parity is proven, not merely intended:
`tests/test_gaps_ranking.py::test_gaps_rank_matches_brief_compose` asserts the
two produce the same check ids in the same order for the same page, so the
gap a stranger sees on the landing page is the item at the top of their
morning brief after signup, in the same words.

Whether `brief.py` is ever refactored to *call* this rather than be checked
against it is left open (`doc/18` G3). The parity test is what makes
deferring that safe — if it is ever deleted, this is two rankings that can
silently drift apart.
"""

from __future__ import annotations

from app.calculators.audit import CategoryScore, Check


def rank(categories: tuple[CategoryScore, ...]) -> tuple[Check, ...]:
    """Every failed check across `categories`, points lost descending, tie-
    broken by check id. A passed check never appears — a gap is something
    that did not hold, not a status report on everything that did.
    """
    failed = [check for category in categories for check in category.checks if not check.passed]
    failed.sort(key=lambda check: (-check.weight, check.id))
    return tuple(failed)


def top(categories: tuple[CategoryScore, ...], n: int) -> tuple[Check, ...]:
    """Up to `n` gaps, ranked. Fewer failures means fewer gaps — never padded
    to `n`, and never a gap invented to avoid showing zero (I10)."""
    return rank(categories)[:n]
