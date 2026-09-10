"""What a crawled page contains, how it is stored, and which crawl it came from.

Three things that belong together and deliberately **not** beside the HTML
parser. `research/extract.py` turns HTML into a `PageSignals`;
`retrieval/crawl.py` turns a stored row back into one. Only the first is the
crawl engine, and `tests/test_no_unauthenticated_crawl.py` forbids any module
under `app/research/` from being reachable from an unauthenticated route — so a
shape shared by the write path and the read path cannot live there. Putting it
in `research/` put `app.research.extract` on an import graph reachable from
`routes/companies.py`, which is exactly the exposure that test exists to catch.


In `domain/` rather than `research/`, and that placement is load-bearing.
`tests/test_no_unauthenticated_crawl.py` forbids **any** module under
`app/research/` from being reachable from an unauthenticated route — `crawler`
performs the fetch and `extract` reads what came back, and neither has business
on a path a stranger can reach. `domain/onboarding_sessions.py` writes these
rows and is reachable from `routes/companies.py`, so an enum living beside the
extractor would have failed that test. This is the vocabulary of a table, which
is a domain fact; it happens to describe two crawls.

Both crawl paths write it and neither owns the other: onboarding crawls
synchronously inside a request (`routes/onboarding_agent.py`), and the research
worker crawls on a schedule as the `nexus_jobs` role
(`research/worker_loop.py`).

The values are the value-list of `ck_page_signals_captured_by` in migration
0028, registered in `tests/test_constraint_enum_parity.py` in the same commit —
a CHECK with no Python counterpart fails
`test_every_value_list_constraint_is_registered` rather than the test it was
added for.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, fields
from enum import StrEnum
from typing import Any, Final


class CaptureSource(StrEnum):
    """Provenance, and it is not optional.

    Migration 0028's `ck_page_signals_provenance` requires that a row naming
    `ONBOARDING` carries a `session_id` and no `run_id`, and vice versa. A row
    that cannot name the crawl it came from is a signal nobody can trace back
    to a fetch, which makes the figure it feeds unverifiable — and being
    checkable is the one property this product cannot give up.
    """

    ONBOARDING = "onboarding"
    """The synchronous crawl during stage 1, budgeted to a handful of pages."""

    RESEARCH_RUN = "research_run"
    """The background worker's full crawl, queued at registration or on an
    explicit request."""


@dataclass(frozen=True, slots=True)
class PageSignals:
    """What the page demonstrably contains. No interpretation."""

    url: str
    is_https: bool

    title: str | None
    title_length: int
    meta_description: str | None
    meta_description_length: int

    h1_texts: tuple[str, ...] = field(default=())
    h2_texts: tuple[str, ...] = field(default=())

    has_viewport_meta: bool = False
    has_canonical: bool = False
    canonical_url: str | None = None
    has_robots_meta: bool = False
    robots_blocks_indexing: bool = False
    has_structured_data: bool = False
    has_open_graph: bool = False
    declared_language: str | None = None

    image_count: int = 0
    images_with_alt: int = 0

    internal_link_count: int = 0
    external_link_count: int = 0

    emails: tuple[str, ...] = field(default=())
    has_phone: bool = False
    social_profiles: tuple[str, ...] = field(default=())

    word_count: int = 0
    html_bytes: int = 0
    script_count: int = 0
    stylesheet_count: int = 0
    inline_style_count: int = 0

    text_sample: str = ""
    """Leading body text. Untrusted content — see the M12 boundary."""


# ── Storage codec ─────────────────────────────────────────────
#
# `PageSignals` is built from HTML at crawl time and read back at dashboard
# time, days later, by which point the HTML is long gone. So it has to survive
# a JSONB round trip — and the failure mode if it does not is silent: a dropped
# field comes back as its dataclass default, so `has_canonical` reads False for
# a page that has a canonical tag, and the calculator scores it wrongly with no
# exception anywhere. `tests/test_signals_codec.py` iterates
# `dataclasses.fields` rather than a remembered list, so a new field fails the
# build instead of being quietly discarded.


SIGNALS_NOT_STORED: Final = frozenset({"text_sample", "emails"})
"""The two fields that deliberately never reach the database.

`text_sample` — already persisted as `pages[].text` by `save_crawl`, and it is
untrusted page content. A second copy is a second thing the M12 boundary has to
know about, for no gain.

`emails` — addresses scraped from a public page. `calculators/audit.py` asks
only `bool(signals.emails)` and `len(signals.emails)`, never an address, so
`EMAIL_COUNT_KEY` carries the count and `signals_from_json` rebuilds a
placeholder tuple of that length. Both predicates stay exactly correct and no
personal data lands in a table that has no retention rule.

`social_profiles` is **not** in this set: `audit.py` renders it into evidence
text, so it has to survive. Those are public company profile URLs.
"""

EMAIL_COUNT_KEY: Final = "email_count"

EMAIL_PLACEHOLDER: Final = "(not stored)"
"""What `emails` is rebuilt from. Self-describing on purpose — if this ever
does reach a screen it should read as an absence rather than as an address, and
it contains no `@`, which is what `test_no_scraped_address_is_ever_stored`
checks the payload for."""

_TUPLE_FIELDS: Final = frozenset(
    f.name for f in fields(PageSignals) if str(f.type).startswith("tuple")
)
"""Derived, not written down. JSON has only lists, and a list in a frozen slots
dataclass declaring `tuple[str, ...]` is a type lie that `len()` never catches
and `mypy` never sees, because the object is built at runtime from a row."""


def signals_to_json(signals: PageSignals) -> dict[str, Any]:
    """The JSONB payload for one page. Every field except the two exclusions."""
    payload: dict[str, Any] = {}
    for f in fields(PageSignals):
        if f.name in SIGNALS_NOT_STORED:
            continue
        value = getattr(signals, f.name)
        payload[f.name] = list(value) if f.name in _TUPLE_FIELDS else value
    payload[EMAIL_COUNT_KEY] = len(signals.emails)
    return payload


def signals_from_json(payload: Mapping[str, Any]) -> PageSignals:
    """Rebuild the signals a crawl observed.

    Missing keys fall through to the dataclass defaults rather than raising,
    because a row written by an older revision is still worth scoring — the
    checks it cannot answer fail, which is the same thing the page not having
    the tag would have said. A key present but null is the same case.
    """
    kwargs: dict[str, Any] = {}
    for f in fields(PageSignals):
        if f.name in SIGNALS_NOT_STORED or f.name not in payload:
            continue
        value = payload[f.name]
        if f.name in _TUPLE_FIELDS:
            kwargs[f.name] = tuple(value or ())
        else:
            kwargs[f.name] = value

    count = int(payload.get(EMAIL_COUNT_KEY) or 0)
    kwargs["emails"] = tuple(EMAIL_PLACEHOLDER for _ in range(count))
    return PageSignals(**kwargs)
