"""The Anthropic implementation. The only file that knows the vendor exists.

Isolated deliberately: doc 07's build contract and the D11 decision both leave
open whether a second provider is ever needed, and scattering SDK calls through
the application is what makes that question expensive to answer later.

**The SDK import is lazy and its absence is survivable.** `anthropic` is not
installed until the integration is switched on, and a missing package must not
break `import app.main`. Startup importing this module is not the same as using
it — the health endpoint asks `status()`, which never touches the SDK.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from app.ai.contracts import (
    Availability,
    Completion,
    CompletionRequest,
    LlmAuthError,
    LlmError,
    LlmRequestError,
    LlmTransientError,
    LlmUnavailableError,
    ProviderStatus,
    Usage,
)
from app.logging import get_logger

if TYPE_CHECKING:  # pragma: no cover - typing only
    pass

log = get_logger(__name__)

PROVIDER_NAME = "anthropic"

# Retried once, and only these. A 4xx is deterministic: the same request gets
# the same rejection and the retry only spends the budget twice.
_RETRYABLE_STATUS = frozenset({408, 429, 500, 502, 503, 504})


def _sdk() -> Any:
    """Import the SDK on first use, mapping its absence to an auth-style error.

    Not at module scope: `app.main` imports the registry, the registry imports
    this, and a missing optional dependency would then take down an application
    that is meant to run perfectly well without any AI configured at all.
    """
    try:
        import anthropic
    except ModuleNotFoundError as exc:  # pragma: no cover - environment-dependent
        raise LlmUnavailableError(
            "the anthropic package is not installed; add it to run with a live provider"
        ) from exc
    return anthropic


class AnthropicProvider:
    """Talks to Anthropic. Constructed by the registry, never directly."""

    name = PROVIDER_NAME

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        disabled_skills: frozenset[str] = frozenset(),
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._disabled_skills = disabled_skills
        self._client: Any | None = None

    # ── Availability ──────────────────────────────────────────

    def status(self) -> ProviderStatus:
        if not self._api_key:
            return ProviderStatus(
                availability=Availability.UNCONFIGURED,
                provider=self.name,
                model=None,
                detail="No API key configured. AI features are unavailable until one is set.",
            )
        return ProviderStatus(
            availability=Availability.AVAILABLE,
            provider=self.name,
            model=self._model,
            detail=f"Configured for {self._model}.",
        )

    def _client_or_raise(self) -> Any:
        if not self._api_key:
            raise LlmUnavailableError("no API key configured")
        if self._client is None:
            self._client = _sdk().AsyncAnthropic(api_key=self._api_key)
        return self._client

    # ── The call ──────────────────────────────────────────────

    async def complete(self, request: CompletionRequest) -> Completion:
        if request.skill in self._disabled_skills:
            raise LlmUnavailableError(f"skill '{request.skill}' is switched off")

        client = self._client_or_raise()
        model = request.model or self._model
        messages = [{"role": m.role, "content": m.content} for m in request.messages]

        started = time.monotonic()
        try:
            response = await self._send(client, request, model, messages)
        except Exception as exc:
            raise _map_error(exc) from exc
        latency_ms = int((time.monotonic() - started) * 1000)

        text = _first_text_block(response)
        usage = Usage(
            input_tokens=int(getattr(response.usage, "input_tokens", 0)),
            output_tokens=int(getattr(response.usage, "output_tokens", 0)),
        )
        stop_reason = str(getattr(response, "stop_reason", "") or "unknown")

        # Counts, latency and identifiers only. The prompt and the completion are
        # customer content and belong in the `generation` table under the scope
        # of their inputs, never in a log line.
        log.info(
            "ai.completion",
            skill=request.skill,
            provider=self.name,
            model=model,
            input_tokens=usage.input_tokens,
            cache_read_tokens=int(getattr(response.usage, "cache_read_input_tokens", 0) or 0),
            output_tokens=usage.output_tokens,
            latency_ms=latency_ms,
            stop_reason=stop_reason,
        )

        return Completion(
            text=text,
            model=str(getattr(response, "model", model)),
            provider=self.name,
            usage=usage,
            stop_reason=stop_reason,
            latency_ms=latency_ms,
            truncated=stop_reason == "max_tokens",
        )

    async def _send(
        self,
        client: Any,
        request: CompletionRequest,
        model: str,
        messages: list[dict[str, str]],
    ) -> Any:
        """One retry, transient failures only.

        Deliberately not exponential backoff across many attempts: doc 06 §8's
        pipeline is fetch, compute, one model call, validate, retry once, then
        Unavailable. A request that fails twice should surface as unavailable
        rather than be retried until the budget is gone.
        """
        kwargs = _request_kwargs(request, model, messages)
        attempts = 0
        while True:
            attempts += 1
            try:
                return await client.messages.create(**kwargs)
            except Exception as exc:
                if attempts >= 2 or not _is_retryable(exc):
                    raise
                log.info("ai.retry", skill=request.skill, provider=self.name)


# ── What each tier will accept ────────────────────────────────
#
# Not style preferences: sending a parameter a model has removed is a 400, and
# it surfaces as "this skill is broken" rather than "the manifest picked the
# wrong tier". Prefix matching — the ids are stable prefixes, and a dated
# snapshot of the same model behaves the same way.

_REJECTS_SAMPLING = (
    "claude-opus-5",
    "claude-opus-4-8",
    "claude-opus-4-7",
    "claude-sonnet-5",
    "claude-fable-5",
    "claude-mythos-5",
)
"""Sampling parameters were removed on these; sending `temperature` is a 400.

This file previously sent `temperature=` unconditionally, so every skill would
have failed the moment the configured model moved to a current tier.
"""

_REJECTS_EFFORT = ("claude-haiku-4-5", "claude-sonnet-4-5")
"""`output_config.effort` errors on these. Haiku is a deliberate tier for the
cheap mechanical skills, so this is a live path rather than a hypothetical."""


def _accepts_sampling(model: str) -> bool:
    return not model.startswith(_REJECTS_SAMPLING)


def _accepts_effort(model: str) -> bool:
    return not model.startswith(_REJECTS_EFFORT)


def _request_kwargs(
    request: CompletionRequest,
    model: str,
    messages: list[dict[str, str]],
) -> dict[str, Any]:
    """Assemble one Messages request, omitting whatever this tier rejects."""
    kwargs: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "max_tokens": request.max_output_tokens,
        "timeout": request.timeout_seconds,
    }
    kwargs["system"] = _system_blocks(request)

    if _accepts_sampling(model):
        kwargs["temperature"] = request.temperature

    output_config: dict[str, Any] = {}
    if request.effort and _accepts_effort(model):
        output_config["effort"] = request.effort
    if request.response_schema is not None:
        # Constrains the response at decode time. The caller still validates —
        # a provider that validated would swallow the schema failure rate, and
        # that rate is the drift signal worth watching.
        output_config["format"] = {
            "type": "json_schema",
            "schema": dict(request.response_schema),
        }
    if output_config:
        kwargs["output_config"] = output_config

    return kwargs


# ── Helpers ───────────────────────────────────────────────────


def _system_blocks(request: CompletionRequest) -> Any:
    """The system prompt, split so the cache breakpoint lands in the right place.

    Caching is a **prefix match**: any byte change before the breakpoint
    invalidates everything after it. A skill's prompt is identical on every call;
    its grounding is different on every call. Marking them as one block would
    write a fresh entry per request and read none — paying the write premium
    forever for nothing.

    So the stable prompt is its own block and carries the marker, and grounding
    follows it unmarked. When `cache_system` is off, or there is no grounding to
    separate, a plain string is sent — fewer moving parts for the common case.

    Note the minimum cacheable prefix is model-dependent (512 tokens on Opus 5,
    1024 on Sonnet 5) and a shorter prefix silently does not cache. At the
    current skill-prompt sizes (~300-430 tokens) nothing here caches yet; the
    split exists so that stays true rather than becoming a silent cost when a
    prompt grows past the threshold.
    """
    grounding = _grounding_text(request)

    if not request.cache_system:
        return request.system if grounding is None else f"{request.system}\n\n{grounding}"

    blocks: list[dict[str, Any]] = [
        {"type": "text", "text": request.system, "cache_control": {"type": "ephemeral"}}
    ]
    if grounding is not None:
        # Deliberately after the breakpoint: this is the volatile half.
        blocks.append({"type": "text", "text": grounding})
    return blocks


def _grounding_text(request: CompletionRequest) -> str | None:
    """The pre-computed facts, and the instruction forbidding more.

    The instruction is not a guarantee — prompt-level rules are weak, which doc
    06 §7.2 says plainly about L0 knowledge. It is the cheap half of the defence.
    The expensive half is M8 validating the response and rejecting figures that
    were not supplied here.
    """
    if not request.grounding:
        return None

    facts = "\n".join(f"- {key}: {value!r}" for key, value in sorted(request.grounding.items()))
    return (
        "The following values were computed from the company's own data. "
        "Use them exactly as given. Do not calculate, estimate, round or infer "
        "any other figure — if a number you need is not listed here, say which "
        "one is missing instead of producing it.\n\n"
        f"{facts}"
    )


def _first_text_block(response: Any) -> str:
    blocks = getattr(response, "content", None) or []
    parts = [
        str(getattr(block, "text", ""))
        for block in blocks
        if getattr(block, "type", None) == "text"
    ]
    return "".join(parts)


def _status_of(exc: Exception) -> int | None:
    value = getattr(exc, "status_code", None)
    return int(value) if isinstance(value, int) else None


def _is_retryable(exc: Exception) -> bool:
    status = _status_of(exc)
    if status is not None:
        return status in _RETRYABLE_STATUS
    # Timeouts and connection resets carry no status. Matching on the class name
    # rather than importing the SDK keeps this file usable when it is absent.
    return type(exc).__name__ in {
        "APIConnectionError",
        "APITimeoutError",
        "TimeoutError",
        "ConnectTimeout",
        "ReadTimeout",
    }


def _map_error(exc: Exception) -> Exception:
    """Vendor exception to ours, so callers never import the SDK to branch."""
    if isinstance(exc, LlmUnavailableError):
        return exc

    status = _status_of(exc)
    if status in {401, 403}:
        return LlmAuthError(f"authentication rejected (HTTP {status})")
    if status is not None and status in _RETRYABLE_STATUS:
        return LlmTransientError(f"provider unavailable (HTTP {status})")
    if status is not None and 400 <= status < 500:
        return LlmRequestError(f"request rejected (HTTP {status})")
    if _is_retryable(exc):
        return LlmTransientError(f"{type(exc).__name__}")

    # Type only. A vendor message can echo the request back, and the request
    # carries customer content.
    return LlmError(f"{type(exc).__name__}")
