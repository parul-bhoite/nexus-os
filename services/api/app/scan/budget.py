"""Caps for the anonymous scan — separate from D20's research budget.

`app.research.site.MAX_PAGES`/`SOFT_CAP_SECONDS`/`HARD_CAP_SECONDS` bound a
workspace's paid-for, authenticated, multi-page research run. These bound a
stranger's single, free page, and are deliberately not the same constants:
conflating them would let a change meant for one silently retune the other.
`doc/18-GAP-ANALYSIS-BUILD-PLAN.md` §3 is where these numbers were decided.
"""

from __future__ import annotations

from typing import Final

MAX_PAGES: Final = 1
"""The domain's home page after redirects. Not a crawl — `doc/18` §0: a
second page would buy `build_preview_audit` nothing (it scores one page) and
would cost the scanned site a request nobody asked for."""

MAX_REDIRECTS: Final = 3

MAX_BYTES: Final = 1_000_000
"""1 MB. A larger page is truncated at this many bytes, not read past it."""

TIMEOUT_SECONDS: Final = 10
"""Total budget for the fetch, not a per-hop timeout."""
