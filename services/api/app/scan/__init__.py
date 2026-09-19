"""The anonymous Instant Gap Analysis scanner — ADR 0046.

The only package a route without a session may use to perform a server-side
fetch. Bounded by two tests: `tests/test_no_unauthenticated_crawl.py` (the
general rule — no anonymous route may reach anything metered or credentialed)
and `tests/test_scan_boundary.py` (the narrow one — `app.scan.*` may import
only a fixed allowlist, and only `app.routes.scan` may reach
`app.research.crawler` from an anonymous route).

As of G1 (`doc/18-GAP-ANALYSIS-BUILD-PLAN.md`), this package holds only the
caps in `budget.py`. No fetch, no route, no schema yet.
"""

from __future__ import annotations
