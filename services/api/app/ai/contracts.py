"""The LLM boundary: what the rest of the application is allowed to know.

Nothing outside `app/ai/` imports a vendor SDK. Everything above this file
depends on `LlmProvider`, and swapping Anthropic for another provider — or for
the deterministic test double — is a registry change, not a refactor.

Three decisions shape this interface, and each of them is a product constraint
rather than a style preference.

**Unavailable is a value, not an exception.** A workspace with no API key
configured is in a normal operating state, not a broken one. `availability()`
answers before any call is made, so a dashboard can render "this needs an API
key" instead of catching an error from a call it should never have attempted.
Doc 07 §7's honesty rule applies to our own operations surface too.

**The model never supplies a number (I1).** `CompletionRequest.grounding` holds
values that were already fetched or computed in deterministic code, and the
prompt is expected to reference them. This interface cannot enforce that on its
own — a determined caller could still ask a model to do arithmetic — so M8's
pipeline validates the response against a schema and rejects unexpected figures.
What this file does is make the grounded shape the obvious one to write.

**No prompt and no completion text is ever logged.** `app/logging.py` already
raises on keys like `prompt` and `input_snapshot`; the telemetry here carries
token counts, latency, model id, skill and stop reason, and nothing else. The
content belongs in the `generation` table (task 8.5) under the scope of its
inputs, not in a log line.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Literal, Protocol, runtime_checkable

# ── Availability ──────────────────────────────────────────────


class Availability(StrEnum):
    """Why a provider can or cannot be used, right now.

    Distinguished rather than collapsed into a boolean because each state has a
    different answer for the user. "Add an API key" and "an administrator turned
    this off" are not the same message, and neither is "the vendor is down".
    """

    AVAILABLE = "available"
    """Configured and expected to work."""

    UNCONFIGURED = "unconfigured"
    """No credentials. The normal state before the key is supplied."""

    DISABLED = "disabled"
    """Switched off deliberately — a per-skill kill switch (doc 07 M8 task 8.7)."""

    BUDGET_EXHAUSTED = "budget_exhausted"
    """The tenant or user has spent its token allowance (task 8.6).

    Degrading here is mandatory and the degradation is *always downward*: to an
    honest unavailable state, never to a cheaper unevaluated model and never to a
    stale cached answer. Both of those would silently change what the customer is
    being told while appearing to still work.
    """


@dataclass(frozen=True, slots=True)
class ProviderStatus:
    availability: Availability
    provider: str
    model: str | None
    detail: str
    """Safe to show a user. Never contains a key, a DSN or customer content."""

    @property
    def usable(self) -> bool:
        return self.availability is Availability.AVAILABLE


# ── Request ───────────────────────────────────────────────────

Role = Literal["user", "assistant"]


@dataclass(frozen=True, slots=True)
class Message:
    role: Role
    content: str


@dataclass(frozen=True, slots=True)
class CompletionRequest:
    """One model call.

    `skill` is required and is not decoration: it keys the kill switch, the
    token budget, the prompt version recorded in `generation`, and the eval that
    has to pass before the skill may use a cheaper model (doc 06 §8.4).
    """

    skill: str
    system: str
    messages: Sequence[Message]

    grounding: Mapping[str, object] = field(default_factory=dict)
    """Values already fetched or computed in deterministic code.

    The prompt should reference these rather than asking the model to derive
    them. A figure that appears here can be traced; a figure the model produced
    cannot, and I1 exists to make sure the second kind never reaches a screen.
    """

    max_output_tokens: int = 1024
    temperature: float = 0.0
    """Zero by default. These calls are business analysis, not creative writing,
    and a reproducible answer is worth more than a varied one.

    **Not sent to models that reject sampling parameters.** Claude Opus 4.7 and
    later return a 400 for `temperature`, `top_p` or `top_k` at all; Sonnet 5
    rejects a non-default value. The provider decides — see `_accepts_sampling`
    in `anthropic_provider.py`. The field stays because older models and the
    scripted double still honour it, and because deleting it would silently
    change behaviour for anything pinned to a legacy tier.
    """

    model: str | None = None
    """Which tier runs this call. `None` means the configured default.

    Set from the skill manifest, never by a caller at the call site: a skill's
    tier is part of its definition and has to move with it, or the eval that
    approved a skill on one tier says nothing about the tier it actually runs on.
    """

    effort: str | None = None
    """`low` | `medium` | `high` | `xhigh` | `max`. Depth of reasoning and spend.

    Also from the manifest. Cheap mechanical skills run low; synthesis runs high.
    """

    cache_system: bool = False
    """Ask the provider to cache the system prompt.

    Worth setting for any skill whose system prompt is stable across calls — a
    skill prompt is by definition the same bytes every time, which is exactly
    the shape prompt caching rewards. The provider applies the marker; whether
    it actually caches depends on the prompt clearing the model's minimum.
    """

    response_schema: Mapping[str, object] | None = None
    """When set, the provider asks for JSON matching this shape. Validation is
    the caller's job — a provider that validated would swallow the schema
    failure rate that doc 07 M13 task 13.4 wants to watch as a drift signal."""

    timeout_seconds: float = 60.0


# ── Response ──────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class Usage:
    input_tokens: int
    output_tokens: int

    @property
    def total(self) -> int:
        return self.input_tokens + self.output_tokens


@dataclass(frozen=True, slots=True)
class Completion:
    text: str
    model: str
    provider: str
    usage: Usage
    stop_reason: str
    latency_ms: int

    truncated: bool = False
    """The model hit `max_output_tokens`. A truncated answer must never be
    presented as a complete one — a half-written recommendation reads as a whole
    one, which is worse than no recommendation."""


# ── Errors ────────────────────────────────────────────────────


class LlmError(Exception):
    """Base for provider failures. Messages are safe to log, not to display.

    Callers render their own user-facing text: the point of mapping vendor
    errors onto these types is that a caller can branch on *kind* without
    importing a vendor module or matching on a message string.
    """


class LlmUnavailableError(LlmError):
    """Called a provider that `availability()` had already said was unusable.

    A bug rather than a runtime condition — check availability first.
    """


class LlmTransientError(LlmError):
    """Overload, timeout, or a 5xx. Retrying may work."""


class LlmRequestError(LlmError):
    """The request itself was rejected: too long, malformed, refused.

    Never retried — a second identical request gets the same answer and only
    spends the budget twice.
    """


class LlmAuthError(LlmError):
    """Credentials missing, invalid or revoked."""


# ── The interface ─────────────────────────────────────────────


@runtime_checkable
class LlmProvider(Protocol):
    """What the application depends on. Implementations live beside this file."""

    name: str

    def status(self) -> ProviderStatus:
        """Answer without making a network call. Safe to call per request."""
        ...

    async def complete(self, request: CompletionRequest) -> Completion:
        """Raises `LlmError` or a subclass. Never returns a partial success."""
        ...
