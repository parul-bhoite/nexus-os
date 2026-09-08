"""Which systems a company runs on, and what each one would unlock.

The tools step of onboarding. It sits after the interview and after the
documents, and it is the **last** thing that happens before the Persona and the
Company Brain are assembled — so what is recorded here is grounding the Brain is
built *with*, rather than a setting applied to a Brain that is already written.
That ordering is the point of the step existing at all: a Brain assembled before
anyone said "our pipeline is in HubSpot" has to guess where pipeline answers come
from, and it guesses in prose that reads as fact.

**Declaring is not connecting, and the column says which.** No OAuth exists yet
— `app/domain/connectors.py` records that the OAuth half waits on D3 (Google
credentials) and D10 (the CRM choice), and neither has landed. So what this step
collects today is the person naming their own stack, stored as
`ConnectionState.DECLARED`. Two things make that worth collecting rather than
worth deferring:

- It is grounding. "Deals live in Pipedrive, invoices in Xero" changes what the
  Brain should say about how this company runs, and it is a fact only the person
  has.
- It turns silence into a named gap. Every declared-but-unconnected tool becomes
  a `known_gap` carrying its own unlock, which is what `context.known_gaps` is
  for — a workspace that says "I cannot see your traffic until Analytics is
  connected" is in a different category from one whose traffic tile is empty.

When the OAuth half lands it moves the same row to `CONNECTED` and fills
`connected_at`. No migration, no second table, and no ambiguity about which
tools were ever actually reachable — that was the whole reason for putting the
lifecycle in one column instead of inferring "connected" from the row existing.

**Every `unlocks` is a capability, never a finding.** The same rule
`document_asks` is written under. "Answering pipeline questions from your own
deals" is a promise kept the moment the connection works; "you are losing 12% at
proposal stage" is a conclusion invented before anything has been read.

**The catalogue is closed, and the database agrees.**
`ck_workspace_connection_provider` holds the same ids as `PROVIDERS`, and
`test_constraint_enum_parity` compares the two on every run. A client cannot
declare `provider: "our internal thing"` and leave a row that nothing
downstream knows how to read.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Final
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.connectors import ConnectionState
from app.domain.scopes import Department

MAX_DECLARED = 20
"""A ceiling on one declaration request.

Not a product limit — nine providers exist, so nobody can legitimately reach it.
It is here because the request body is a list and an unbounded list is a way to
make one endpoint do arbitrary work. The catalogue check refuses the ids anyway;
this refuses the *size* before nine lookups turn into nine thousand.
"""


class UnknownProviderError(ValueError):
    """A provider id the catalogue does not declare.

    Raised rather than skipped. A request naming five tools of which one is
    unknown is a client and a server that disagree about the catalogue, and
    silently storing four would make the disagreement invisible — the person
    would tick five boxes, see four come back, and have no way to learn which
    one did not take.
    """


@dataclass(frozen=True, slots=True)
class Tool:
    """One system a company might run on, and what connecting it turns on."""

    id: str
    """The stored value. In `ck_workspace_connection_provider`, so it is not
    free to change without a migration."""

    name: str
    """What it is called by the people who use it, not by its vendor's
    marketing. "Google Analytics", not "Google Analytics 4 Property"."""

    department: Department
    """Which director's questions this tool would answer.

    Used to order the step by the departments the company actually runs — the
    same rule `document_asks` follows. A company with no finance function should
    not be asked for its accounting system first.
    """

    unlocks: str
    """What NEXUS can do once this is connected. A capability, never a finding."""

    kind: str = "tool"
    """`crm` for the four that are alternatives to each other, `tool` otherwise.

    The step uses it to say "pick the one you use" over the CRMs instead of
    presenting four systems nobody runs together as four independent choices.
    It is display grouping and nothing else — the database stores each on its
    own row, because a company mid-migration really does run two.
    """


PROVIDERS: Final[tuple[Tool, ...]] = (
    Tool(
        id="ga4",
        name="Google Analytics",
        department=Department.MARKETING,
        unlocks="Reporting your real traffic and conversions instead of leaving the tile locked.",
    ),
    Tool(
        id="search_console",
        name="Google Search Console",
        department=Department.MARKETING,
        unlocks="Telling you which searches you already rank for, from your own data.",
    ),
    Tool(
        id="hubspot",
        name="HubSpot",
        department=Department.SALES,
        unlocks="Answering pipeline questions from your own deals rather than from your memory.",
        kind="crm",
    ),
    Tool(
        id="salesforce",
        name="Salesforce",
        department=Department.SALES,
        unlocks="Answering pipeline questions from your own deals rather than from your memory.",
        kind="crm",
    ),
    Tool(
        id="pipedrive",
        name="Pipedrive",
        department=Department.SALES,
        unlocks="Answering pipeline questions from your own deals rather than from your memory.",
        kind="crm",
    ),
    Tool(
        id="zoho_crm",
        name="Zoho CRM",
        department=Department.SALES,
        unlocks="Answering pipeline questions from your own deals rather than from your memory.",
        kind="crm",
    ),
    Tool(
        id="xero",
        name="Xero",
        department=Department.FINANCE,
        unlocks="Reading your actuals against your budget without you exporting anything.",
    ),
    Tool(
        id="quickbooks",
        name="QuickBooks",
        department=Department.FINANCE,
        unlocks="Reading your actuals against your budget without you exporting anything.",
    ),
    Tool(
        id="stripe",
        name="Stripe",
        department=Department.FINANCE,
        unlocks="Seeing revenue as it lands, rather than as it was last reconciled.",
    ),
)

PROVIDER_IDS: Final[frozenset[str]] = frozenset(tool.id for tool in PROVIDERS)

_BY_ID: Final[dict[str, Tool]] = {tool.id: tool for tool in PROVIDERS}

OAUTH_READY: Final[frozenset[str]] = frozenset()
"""Providers whose connect flow actually exists. **Empty, deliberately.**

A constant rather than a `False` on every `Tool`, because the day one of these
becomes real it should become real in one place — and because a screen has to be
able to say "connect" for the ready ones and "we will ask you to connect this"
for the rest without a second list to keep in step. Today it says the second
thing about all nine, which is the truth.
"""


def by_id(provider: str) -> Tool:
    tool = _BY_ID.get(provider)
    if tool is None:
        raise UnknownProviderError(
            f"{provider!r} is not a tool this product knows how to connect; "
            f"declared providers are {', '.join(sorted(PROVIDER_IDS))}"
        )
    return tool


def for_departments(departments: frozenset[Department]) -> tuple[Tool, ...]:
    """The catalogue, with this company's own departments first.

    Nothing is removed. That is the difference between this and
    `document_asks.asks_for`, and it is deliberate: a document ask is work we
    are giving somebody, so asking a company with no finance function for its
    budget is an imposition. A tool list is a set of boxes to leave unticked,
    and a company that runs no formal finance function may still run Stripe.
    Hiding it would be the product deciding it knows their stack better than
    they do.

    So the ordering carries the department selection and the membership does
    not. Marketing's two land at the top for a marketing-led company; Finance's
    three are still further down the same list.
    """
    # Stable on the catalogue's own order, not on the department name. Sorting
    # by `tool.department` put Finance's three ahead of the CRMs for a
    # marketing-led company purely because "finance" < "sales" — a tail order
    # decided by the alphabet rather than by anything about the product. The
    # index keeps `PROVIDERS` as written: marketing, then sales, then finance.
    order = {tool.id: index for index, tool in enumerate(PROVIDERS)}
    return tuple(
        sorted(
            PROVIDERS,
            key=lambda tool: (tool.department not in departments, order[tool.id]),
        )
    )


async def declared(db: AsyncSession, *, workspace_id: UUID) -> tuple[str, ...]:
    """Which providers this workspace has on record, in catalogue order.

    Catalogue order rather than insertion order so that re-opening the step
    twice draws the same screen — the row order out of Postgres is not promised
    and, once a declaration is amended, is not even stable.
    """
    rows = (
        (
            await db.execute(
                sa.text(
                    "SELECT provider FROM workspace_connection WHERE workspace_id = :w"
                ),
                {"w": str(workspace_id)},
            )
        )
        .scalars()
        .all()
    )
    on_record = {str(row) for row in rows}
    return tuple(tool.id for tool in PROVIDERS if tool.id in on_record)


async def declare(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    user_id: UUID,
    providers: Sequence[str],
) -> tuple[str, ...]:
    """Record this workspace's stack. Returns what is on record afterwards.

    **Replaces rather than appends**, for the declared ones only. The step is a
    set of checkboxes and a person may come back to it having unticked one, so
    "what they last submitted" has to be what the row set says — an append-only
    write would leave a tool they explicitly removed on record forever, and the
    Brain would go on being told about a system they told us they do not use.

    **A `connected` row is never deleted by an untick.** Unticking is a
    statement about the stack; revoking access is a different act with a
    different consequence, and losing a live connection's tokens because
    somebody cleared a checkbox on a screen they had reopened out of curiosity
    is not a trade this makes. Those rows survive and keep their state — which
    is also why the delete below is narrowed to `declared`.

    Every id is checked against the catalogue *before* anything is written, so a
    request naming one unknown tool changes nothing at all. A partial write here
    is worse than a refusal: the person sees four of five boxes come back ticked
    and cannot tell whether the fifth failed or was never sent.
    """
    if len(providers) > MAX_DECLARED:
        raise UnknownProviderError(
            f"{len(providers)} providers named; at most {MAX_DECLARED} can be declared at once"
        )

    wanted = {by_id(provider).id for provider in providers}

    # One statement whatever the selection is, with the empty case carried by
    # the parameter rather than by concatenating a different query — an
    # unticked-everything submission is the normal way to clear the step and
    # does not deserve its own SQL. `<> ALL('{}')` is true for every row, so
    # this deletes the lot; the cast is required because asyncpg cannot infer
    # the element type of an empty array.
    #
    # Narrowed to `state = 'declared'` on purpose: see the note above about a
    # `connected` row surviving an untick.
    await db.execute(
        sa.text(
            "DELETE FROM workspace_connection"
            " WHERE workspace_id = :w AND state = :declared"
            " AND provider <> ALL(CAST(:keep AS text[]))"
        ),
        {
            "w": str(workspace_id),
            "declared": ConnectionState.DECLARED.value,
            "keep": sorted(wanted),
        },
    )

    now = datetime.now(UTC)
    for provider in sorted(wanted):
        # `ON CONFLICT DO NOTHING`, not `DO UPDATE`. The conflicting row is
        # either this same declaration — in which case there is nothing to
        # write and `declared_at` should keep saying when they first told us —
        # or a `connected` one, which this must not demote to `declared`.
        await db.execute(
            sa.text(
                "INSERT INTO workspace_connection"
                " (workspace_id, provider, state, declared_by, declared_at)"
                " VALUES (:w, :p, :state, :u, :at)"
                " ON CONFLICT (workspace_id, provider) DO NOTHING"
            ),
            {
                "w": str(workspace_id),
                "p": provider,
                "state": ConnectionState.DECLARED.value,
                "u": str(user_id),
                "at": now,
            },
        )

    return await declared(db, workspace_id=workspace_id)


def gaps_for(providers: Iterable[str]) -> list[dict[str, str]]:
    """What each named tool cannot do yet, as `known_gaps` entries.

    The shape `context.known_gaps` already uses — `topic` and `unlocked_by` —
    so these merge into the list `context-personalization` produces rather than
    needing a second list beside it with the same job.

    **Only the declared ones.** A gap for a tool nobody uses is noise: telling a
    company with no CRM that pipeline analysis is locked behind a CRM is a
    limitation of a product they did not ask for. A gap for a tool they told us
    they run is actionable, and the action is named.
    """
    gaps: list[dict[str, str]] = []
    for provider in providers:
        if provider in OAUTH_READY:
            continue
        tool = _BY_ID.get(provider)
        if tool is None:
            continue
        gaps.append(
            {
                "topic": tool.unlocks,
                "unlocked_by": f"Connecting {tool.name}",
            }
        )
    return gaps
