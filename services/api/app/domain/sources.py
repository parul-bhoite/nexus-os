"""The source ledger: every source, what it turns on, and what it still cannot answer.

`doc/13` §16. `doc/prototype/NEXUS OS Dashboard Tools.xlsx` answers *"what could
we buy?"* — twenty-eight modules with a free and a paid option each. The product
needs the inverse, and this is it: **for each source, what connecting it turns
on, what it still does not answer, and what kind of act unlocks it.**

## Three rules, and the second is the one that earns its keep

**Nothing is typed twice.** `unlocks_now` and `will_unlock` are computed by
inverting `Capability.required_sources`. A tool cannot advertise a capability
that does not list it, and adding a capability updates the connect screen with
no second edit. There is deliberately no `unlocks` field on a
ledger row — a list of ids here is a list that goes stale.

**Every row says what it cannot answer.** Half a ledger is a sales sheet. GA4
will never tell us what an enquiry was worth; a CRM will never tell us the cash
position. Saying so is what stops "connect everything" from ending in
disappointment, and it is the same honesty that makes `doc/08` §2B — *the
questions we refuse to ask you* — a product surface rather than an internal
rule.

**A source is not always a tool.** Six of them are ours, one is an API key, and
one is elapsed time. Rendering "connect your website crawl" or offering a
Connect button for *history* would be nonsense, and the reason `WARMING` exists
as a separate state from `LOCKED` is exactly this distinction: one asks the
customer for an act and the other asks them to wait. `Origin` is that
distinction as data.

## The count on the connect screen

*"Connect Google Analytics — turns on six Marketing capabilities"* is the
conversion mechanism `doc/09` §3 identified, and it is a claim that has to be
true. Two things make it so:

- **It is computed against what is already connected.** A capability needing a
  CRM *and* an accounting system is not unlocked by connecting the first, and
  counting it under both would promise the same tile twice.
- **It counts `reachable` capabilities only.** Today that is zero for every
  connector, and the screen must say zero rather than count the catalogue. What
  the catalogue holds is `will_unlock`, which the tool's own page may show as
  long as it is labelled as coming rather than as waiting for the customer.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from app.domain.dashboards import LABELS, Source
from app.domain.registry import TILES, Capability


class SourceLedgerError(Exception):
    """A source with no ledger row, or a row for a source that does not exist."""


class Origin(StrEnum):
    """What kind of act turns this source on.

    The four are not a taxonomy for its own sake — each one is a different
    sentence on a locked tile, and getting them wrong is how a product tells
    somebody to connect a thing that cannot be connected.
    """

    OURS = "ours"
    """First-party. It arrives because the product did something — crawled the
    site, asked a question, indexed an upload, or recorded a project. Never a
    Connect button."""

    CONNECTOR = "connector"
    """A third-party system with an OAuth or key exchange behind it. The only
    origin the tools screen lists, and the only one the domain gate applies to
    (D19)."""

    KEY = "key"
    """An API key we hold rather than the customer. `LANGUAGE_MODEL` is the only
    one, and an absent key is a supported state, not a degraded one (ADR
    0011)."""

    TIME = "time"
    """Nothing to connect. `HISTORY` accrues, which is why a tile short of it
    renders `WARMING` with a date rather than `LOCKED` with an instruction."""


@dataclass(frozen=True, slots=True)
class SourceEntry:
    """One source, and everything true about it that is not derived.

    **Not a `Tool`.** `domain/connections.py` already has that name, and for a
    different thing: a `Tool` there is a *provider* the customer declares —
    HubSpot, Zoho, Pipedrive — and four of those map to the single `CRM` source
    a capability actually requires. Providers are what somebody connects; sources
    are what capabilities need. `PROVIDER_SOURCES` below is the join, and calling
    both of them `Tool` is how a reader ends up thinking there are nine sources.
    """

    source: Source
    origin: Origin
    name: str
    """What the customer calls it. `LABELS` in `dashboards.py` holds the phrase
    used mid-sentence — *"needs your CRM"* — and this is the proper noun used as
    a heading. Both exist because "Needs Google Analytics 4." reads worse than
    "Needs Google Analytics." in a sentence and worse as a title the other way
    round."""

    cannot_answer: tuple[str, ...]
    """The honest half. Every row has at least one, enforced below, because a
    source that answers everything in its area is a source somebody has not
    thought about."""

    free_option: str = ""
    paid_option: str = ""
    """From the tools sheet, and both empty for anything we do not ask the
    customer to buy. Kept because the answer to *"do I have to pay for this?"*
    belongs on the connect screen rather than in a sales conversation."""

    required_fields: tuple[str, ...] = ()
    """Fields that must be mapped for **anything** to work. Per-capability
    requirements live in `connectors.py`, checked at connect (doc 05 §9); this
    is the floor below which the connection is not usable at all."""

    read_only: bool = True
    """A5. Write scope is a separate, heavier, later ask, and a ledger that
    quietly allowed a write scope would be the wrong place to discover it."""


# ── The ledger ────────────────────────────────────────────────
#
# One row per `Source`, and `_validate` refuses to import if that stops being
# true in either direction. That totality is the point of the module: a new
# source added to the enum without a row is a tile whose unlock sentence nobody
# has written, and it fails here rather than on a customer's screen.

LEDGER: Final[tuple[SourceEntry, ...]] = (
    # ── Ours ──
    SourceEntry(
        source=Source.CRAWL,
        origin=Origin.OURS,
        name="Your website",
        cannot_answer=(
            "who visited, or what they did",
            "anything about money, stock or people",
        ),
    ),
    SourceEntry(
        source=Source.ONBOARDING,
        origin=Origin.OURS,
        name="Your setup answers",
        cannot_answer=(
            "whether what you told us is still true",
            "anything you were not asked",
        ),
    ),
    SourceEntry(
        source=Source.DOCUMENTS,
        origin=Origin.OURS,
        name="Your uploaded documents",
        cannot_answer=("anything that is not in a file you uploaded",),
    ),
    SourceEntry(
        source=Source.ROSTER,
        origin=Origin.OURS,
        name="Your team list",
        cannot_answer=(
            "headcount — the roster is who uses NEXUS, not who works here",
            "salaries, which stay L4 whoever is asking",
        ),
    ),
    SourceEntry(
        source=Source.OPS_LAYER,
        origin=Origin.OURS,
        name="Projects and tasks in NEXUS",
        cannot_answer=("anything nobody recorded — this one fails on adoption, not on an API",),
    ),
    # ── An API key we hold ──
    SourceEntry(
        source=Source.LANGUAGE_MODEL,
        origin=Origin.KEY,
        name="A language model",
        cannot_answer=(
            "any number at all — it phrases, and never computes (I1)",
            "anything, when no key is configured, which is a supported state",
        ),
    ),
    # ── Elapsed time ──
    SourceEntry(
        source=Source.HISTORY,
        origin=Origin.TIME,
        name="Enough elapsed periods to compare",
        cannot_answer=("what changed, in week one — that is a baseline, not a brief",),
    ),
    # ── Connectors ──
    SourceEntry(
        source=Source.GA4,
        origin=Origin.CONNECTOR,
        name="Google Analytics",
        cannot_answer=(
            "what an enquiry was worth — that is Sales' to hold",
            "leads that arrived by phone, WhatsApp or in person",
        ),
        free_option="Google Analytics 4 (free)",
        paid_option="Mixpanel or Amplitude",
        required_fields=("a configured conversion event",),
    ),
    SourceEntry(
        source=Source.SEARCH_CONSOLE,
        origin=Origin.CONNECTOR,
        name="Search Console",
        cannot_answer=(
            "sessions or conversion — it sees the search result, not the visit",
            "anything about paid traffic",
        ),
        free_option="Google Search Console (free)",
    ),
    SourceEntry(
        source=Source.PAGESPEED,
        origin=Origin.CONNECTOR,
        name="PageSpeed",
        cannot_answer=("whether anybody arrived, or what slow pages cost you",),
        free_option="PageSpeed Insights (free)",
    ),
    SourceEntry(
        source=Source.DATAFORSEO,
        origin=Origin.CONNECTOR,
        name="Keyword data",
        cannot_answer=("how your own site actually performs",),
        paid_option="DataForSEO, Ahrefs or Semrush",
    ),
    SourceEntry(
        source=Source.CRM,
        origin=Origin.CONNECTOR,
        name="Your CRM",
        cannot_answer=(
            "cash, margin or anything in the ledger",
            "where the enquiry came from before it reached the pipeline",
        ),
        free_option="HubSpot CRM (free tier)",
        paid_option="Zoho CRM or Salesforce",
        required_fields=("stage_canonical", "amount"),
    ),
    SourceEntry(
        source=Source.ACCOUNTING,
        origin=Origin.CONNECTOR,
        name="Your accounting system",
        cannot_answer=(
            "anything about the pipeline or about delivery",
            "margin per project without the operations layer beside it",
        ),
        free_option="Wave (free bookkeeping)",
        paid_option="Xero, QuickBooks or Zoho Books",
        required_fields=("a mapped chart of accounts",),
    ),
    SourceEntry(
        source=Source.ADS,
        origin=Origin.CONNECTOR,
        name="An ad platform",
        cannot_answer=("anything organic",),
        free_option="Google Ads and Meta Ads Manager (native)",
        paid_option="Madgicx or Revealbot",
    ),
    SourceEntry(
        source=Source.ENRICHMENT,
        origin=Origin.CONNECTOR,
        name="A contact enrichment provider",
        cannot_answer=("whether any of them will buy",),
        free_option="Hunter.io (free tier)",
        paid_option="Apollo.io or Clay",
    ),
    SourceEntry(
        source=Source.TENDER_FEED,
        origin=Origin.CONNECTOR,
        name="A tender feed",
        cannot_answer=("anything yet — no provider is identified in any source document",),
    ),
)


# What a workspace has before it connects anything. Onboarding produces all
# four, so they are the baseline every "does connecting this help?" question is
# asked against — the alternative is telling a founder that GA4 unlocks a tile
# which in fact also needed the crawl they already have.
DAY_ONE: Final[frozenset[Source]] = frozenset(
    {Source.CRAWL, Source.ONBOARDING, Source.DOCUMENTS, Source.ROSTER}
)

BY_SOURCE: Final[dict[Source, SourceEntry]] = {tool.source: tool for tool in LEDGER}

CONNECTABLE: Final[tuple[SourceEntry, ...]] = tuple(
    tool for tool in LEDGER if tool.origin is Origin.CONNECTOR
)
"""The only rows the tools screen lists (Q44), and the only ones the domain
verification gate applies to (D19)."""


def _validate(ledger: tuple[SourceEntry, ...]) -> None:
    """Both directions of the totality, and the two rules a row cannot break.

    Takes the ledger rather than reading the module global so a test can hand it
    a broken one — a guard that can only be run against the correct table
    certifies nothing.
    """
    by_source = {tool.source: tool for tool in ledger}

    if len(by_source) != len(ledger):
        raise SourceLedgerError("two ledger rows for one source")

    for source in Source:
        if source not in by_source:
            raise SourceLedgerError(
                f"{source.value} has no ledger row. Every source needs one: a tile"
                " that needs it has to be able to say what turns it on, and what"
                " kind of act that is."
            )
        if source not in LABELS:
            raise SourceLedgerError(
                f"{source.value} has no mid-sentence label in `dashboards.LABELS`"
            )

    for tool in ledger:
        if not tool.cannot_answer:
            raise SourceLedgerError(
                f"{tool.source.value} claims no limits. A source that answers"
                " everything in its area is one nobody has thought about."
            )
        if not tool.read_only:
            raise SourceLedgerError(
                f"{tool.source.value} asks for write scope. A5 makes that a separate,"
                " heavier ask — and not one the ledger may grant quietly."
            )


_validate(LEDGER)


# ── Derived: what a source turns on ───────────────────────────


def contributes_to(source: Source) -> tuple[Capability, ...]:
    """Every capability that lists this source, whether or not it needs others too.

    The tool's own page shows this. The connect screen must not, because most of
    these need something else as well.
    """
    return tuple(c for c in TILES if source in c.required_sources)


def _satisfied_by(capability: Capability, available: frozenset[Source]) -> bool:
    return all(source in available for source in capability.required_sources)


def unlocks_now(source: Source, *, connected: frozenset[Source]) -> tuple[Capability, ...]:
    """What a person could open the moment this source arrives.

    Three filters, and each one is a promise the screen would otherwise break:

    - **Not already satisfied** — a capability that already works is not an
      argument for connecting anything.
    - **Satisfied afterwards** — a capability still missing a CRM is not
      unlocked by an accounting system, and counting it under both promises the
      same tile twice.
    - **`reachable`** — an unbuilt capability cannot be unlocked by connecting
      something, and `doc/04` §6 rule 1 makes a locked tile a call to action, so
      a false one is worse than no tile.
    """
    after = connected | {source}
    return tuple(
        c
        for c in TILES
        if c.reachable and not _satisfied_by(c, connected) and _satisfied_by(c, after)
    )


def will_unlock(source: Source, *, connected: frozenset[Source]) -> tuple[Capability, ...]:
    """The same question for capabilities that are not built yet.

    Kept separate from `unlocks_now` rather than folded in with a flag, because
    the two produce different sentences and only one of them is an instruction.
    *"Turns on four capabilities"* and *"four more are planned"* can both be
    true; collapsing them makes the second read as the first.
    """
    after = connected | {source}
    return tuple(
        c
        for c in TILES
        if not c.reachable and not _satisfied_by(c, connected) and _satisfied_by(c, after)
    )


# ── The join to what a customer actually connects ─────────────
#
# `domain/connections.py` holds nine **providers**, closed and constrained by
# `ck_workspace_connection_provider`. This maps each to the **source** a
# capability requires. Four CRMs and two accounting systems collapse, which is
# the whole reason the two tables are separate: a capability needs *a CRM*, and
# the customer has a particular one.
#
# The totality test on this mapping is what found two promises the product
# cannot keep — see `test_source_ledger.py`.

PROVIDER_SOURCES: Final[dict[str, Source]] = {
    "ga4": Source.GA4,
    "search_console": Source.SEARCH_CONSOLE,
    "hubspot": Source.CRM,
    "salesforce": Source.CRM,
    "pipedrive": Source.CRM,
    "zoho_crm": Source.CRM,
    "xero": Source.ACCOUNTING,
    "quickbooks": Source.ACCOUNTING,
    # Stripe is payments, not bookkeeping, and there is no payments source. It
    # is mapped to accounting because that is the nearest thing the capability
    # model has and because *"revenue as it lands"* is a revenue claim — but the
    # mapping is an approximation and the ledger says so rather than hiding it.
    # Either a `PAYMENTS` source arrives with the capability that needs it, or
    # the provider stops being offered.
    "stripe": Source.ACCOUNTING,
}


def source_for_provider(provider_id: str) -> Source:
    """Which source a declared provider satisfies.

    Raises rather than returning `None`: a provider the ledger cannot place is a
    row in `workspace_connection` that no tile will ever read, and returning
    nothing would let that pass as an ordinary absence.
    """
    try:
        return PROVIDER_SOURCES[provider_id]
    except KeyError as absent:
        raise SourceLedgerError(
            f"provider {provider_id!r} satisfies no source, so declaring it"
            " unlocks nothing. Map it or stop offering it."
        ) from absent
