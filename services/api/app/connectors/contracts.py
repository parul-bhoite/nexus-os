"""The connector spine: one adapter interface, two transports, no model.

`doc/14` step 8, ADR 0031.

## The rule this file exists to hold

> **The API process is the client. No model ever sees a provider.**

MCP is used here as a *transport for deterministic fetches made from code* — not
as a tool surface handed to a language model. A model that called a CRM's MCP
server and reported what it found would be **fetching**, and invariant I1 says
every number is fetched or computed in code. Nothing in this package returns a
value to a model; the rows it produces are stored, and every figure is then
computed by `calculators/` and read back through `retrieval/` under a
`ScopedSession`.

`test_connector_boundary.py` asserts it rather than trusting it.

## Why the transport is invisible above the adapter

Vendor MCP availability moves: Pipedrive shipped a server in June 2026 that did
not exist in March, and Google Analytics still has none. If the capability model,
the source ledger or a screen could tell MCP from REST, every vendor launch would
be a change across layers. Here it is one constructor argument, so a wrong guess
costs one file.

## Everything a provider returns is untrusted

A response carries the customer's own text — deal notes, invoice descriptions,
page titles — and `ARCHITECTURE-HLD`'s untrusted boundary already covers crawled
pages and uploaded documents. Provider responses join that set **explicitly**
rather than by analogy, because an MCP result is shaped like a tool result and
tool results are the thing models are trained to act on. A note reading "ignore
previous instructions" must be as inert as a competitor's web page.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol

from app.domain.dashboards import Source


class ConnectorError(Exception):
    """A provider could not be read. Carries no credential, ever.

    `str(error)` reaches logs and, in summarised form, a screen. An exception
    that interpolated a token into its message would put it in both, and no
    amount of care at the call site takes it back out.
    """


class ProviderUnavailableError(ConnectorError):
    """The provider answered with a refusal, or did not answer.

    Distinct from a mapping failure so a caller can tell *"try again later"*
    from *"this will never work"* — the first is a state, the second is a bug,
    and a tile that renders them identically teaches a founder to ignore both.
    """


class ProviderMisconfiguredError(ConnectorError):
    """The connection exists and cannot be used — a revoked token, a missing
    scope, a field the plan does not expose. Never retried on a schedule,
    because retrying will not fix it and the customer has to act."""


@dataclass(frozen=True, slots=True)
class ToolCall:
    """One named operation against a provider, with its arguments.

    Named rather than free-form on purpose. A transport that accepted a URL or a
    query string would let a caller reach anything the credential can reach, and
    the whole argument for MCP being safe here is that **we** choose the calls.
    """

    name: str
    arguments: Mapping[str, Any] = field(default_factory=dict)


class Transport(Protocol):
    """How a named call reaches a provider. MCP or HTTP; the adapter cannot tell.

    Returns the provider's own payload, unvalidated and untrusted. Shaping it
    into rows is the adapter's job, and validating those rows is the database's.
    """

    async def call(self, call: ToolCall) -> Mapping[str, Any]: ...


@dataclass(frozen=True, slots=True)
class Fetched:
    """What one adapter run produced.

    **`rows` are not figures.** They are the provider's records, normalised
    enough to store and no further: a connector that computed a conversion rate
    on the way past would be a number produced outside `calculators/`, which is
    exactly what I1 forbids and exactly what a rushed adapter does.
    """

    source: Source
    rows: Sequence[Mapping[str, Any]]
    fetched_at: datetime
    """When the provider answered. The figure computed from these rows will be
    presented with a date, and that date has to be this one rather than the
    moment somebody opened a page."""

    truncated: bool = False
    """True when the provider had more and we stopped. Carried rather than
    hidden: a figure computed over a page of results, presented as if it covered
    everything, is a wrong number with a plausible denominator."""


class SourceAdapter(Protocol):
    """Reads one provider, and satisfies exactly one `Source`.

    `source` is declared rather than inferred so an adapter wired to the wrong
    one fails at import rather than by populating a tile with somebody else's
    data. `PROVIDER_SOURCES` in `domain/sources.py` is the join it must agree
    with.
    """

    @property
    def source(self) -> Source: ...

    @property
    def provider(self) -> str: ...

    async def fetch(self, *, since: datetime | None = None) -> Fetched: ...
