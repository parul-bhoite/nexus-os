"""The language-model boundary.

Two guarantees are load-bearing here and neither is obvious from reading the
code, so they are asserted rather than assumed:

1. **The application runs with no API key.** Not "starts and then fails on
   first use" — reports an honest unavailable state and keeps serving. A
   product whose dashboard 500s because an optional integration is missing is
   the failure mode this whole boundary exists to prevent.

2. **Nothing invents content.** There is no demo mode that returns
   plausible-sounding analysis. The unconfigured provider refuses; the test
   provider returns only what a test scripted. A fabricated recommendation that
   reads like a real one destroys the product's central claim, and the label
   saying "demo" does not travel with the screenshot.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.ai.contracts import (
    Availability,
    CompletionRequest,
    LlmAuthError,
    LlmProvider,
    LlmRequestError,
    LlmTransientError,
    LlmUnavailableError,
    Message,
)
from app.ai.providers import ScriptedProvider, UnavailableProvider
from app.ai.registry import build_provider
from app.config import Settings
from app.main import create_app


def request_for(skill: str = "test.skill", **kwargs: object) -> CompletionRequest:
    return CompletionRequest(
        skill=skill,
        system="You are a test.",
        messages=[Message(role="user", content="hello")],
        **kwargs,  # type: ignore[arg-type]
    )


# ── Running without a key ─────────────────────────────────────


def test_no_key_selects_the_unavailable_provider() -> None:
    provider = build_provider(Settings(anthropic_api_key=SecretStr("")))
    status = provider.status()

    assert status.availability is Availability.UNCONFIGURED
    assert status.usable is False
    assert status.model is None


def test_building_a_provider_without_a_key_does_not_raise() -> None:
    """The distinction that matters. Every other secret goes through
    `require()` and fails loudly; this one must not, because an absent language
    model is a supported state rather than a misconfiguration."""
    build_provider(Settings(anthropic_api_key=SecretStr("")))


def test_the_api_starts_and_serves_with_no_language_model() -> None:
    with TestClient(create_app()) as client:
        assert client.get("/health").status_code == 200
        # Readiness answers rather than erroring.
        assert client.get("/health/ready").status_code in {200, 503}


def test_readiness_reports_the_language_model_but_never_gates_on_it() -> None:
    """An optional capability must not take the service out of a load balancer."""
    with TestClient(create_app()) as client:
        checks = client.get("/health/ready").json()["checks"]

    model = next(c for c in checks if c["name"] == "language_model")
    assert model["required_now"] is False, "an absent API key must never gate readiness"
    assert model["state"] in {"ok", "unconfigured"}
    assert model["detail"], "an unusable dependency must say why"


def test_the_unavailable_detail_is_safe_to_show_a_user() -> None:
    status = UnavailableProvider().status()

    assert "key" in status.detail.lower()
    # No stack trace, no module path, no vendor internals.
    assert "Traceback" not in status.detail
    assert "anthropic." not in status.detail


async def test_calling_an_unconfigured_provider_raises_rather_than_inventing() -> None:
    """The most important assertion in this file.

    Returning "" or a friendly paragraph here would be far worse than raising:
    a caller that forgot to check availability would silently render invented
    analysis as though it were grounded.
    """
    with pytest.raises(LlmUnavailableError):
        await UnavailableProvider().complete(request_for())


def test_an_environment_switch_is_distinct_from_a_missing_key() -> None:
    """ "Not configured yet" and "an administrator turned this off" need
    different messages, so they are different states."""
    off = UnavailableProvider(reason=Availability.DISABLED)
    assert off.status().availability is Availability.DISABLED
    assert "administrator" in off.status().detail.lower()


# ── The kill switch ───────────────────────────────────────────


def test_a_disabled_skill_is_read_from_configuration() -> None:
    settings = Settings(disabled_ai_skills="morning_brief, proposal.draft")
    assert settings.disabled_ai_skills_set == {"morning_brief", "proposal.draft"}


def test_the_skill_list_tolerates_whitespace_and_emptiness() -> None:
    assert Settings(disabled_ai_skills="").disabled_ai_skills_set == frozenset()
    assert Settings(disabled_ai_skills=" , ,a, ").disabled_ai_skills_set == {"a"}


# ── The scripted provider refuses to improvise ────────────────


async def test_the_scripted_provider_returns_exactly_what_was_scripted() -> None:
    provider = ScriptedProvider({"brief": "Pipeline is steady."})
    result = await provider.complete(request_for("brief"))

    assert result.text == "Pipeline is steady."
    assert result.provider == "scripted"


async def test_an_unscripted_skill_fails_the_test_rather_than_improvising() -> None:
    """A test provider that invented a reply would let a test pass against
    output nobody wrote, which is the quiet way a grounding rule dies."""
    with pytest.raises(AssertionError, match="no response for skill"):
        await ScriptedProvider().complete(request_for("never.scripted"))


async def test_the_scripted_provider_records_what_it_was_asked() -> None:
    """The assertion surface for every later test of prompt construction."""
    provider = ScriptedProvider({"s": "ok"})
    await provider.complete(request_for("s", grounding={"margin_pct": 34}))

    assert len(provider.calls) == 1
    assert provider.calls[0].grounding == {"margin_pct": 34}


# ── Grounding reaches the model, with the prohibition attached ─


def test_computed_values_are_put_in_the_prompt_with_an_explicit_prohibition() -> None:
    """I1's cheap half. The expensive half is M8 validating the response.

    Checked here because it is the difference between a model *reporting* a
    number and a model *producing* one.
    """
    from app.ai.anthropic_provider import _system_blocks

    system = _system_blocks(request_for(grounding={"revenue_omr": 128_400, "margin_pct": 34}))
    assert isinstance(system, str)

    assert "128400" in system.replace(",", "")
    assert "34" in system
    assert "do not calculate" in system.lower()
    assert "estimate" in system.lower()


def test_a_request_with_no_grounding_is_left_alone() -> None:
    from app.ai.anthropic_provider import _system_blocks

    assert _system_blocks(request_for()) == "You are a test."


def test_grounding_is_ordered_so_the_prompt_is_reproducible() -> None:
    """Two identical requests must produce byte-identical prompts, or the
    prompt version recorded in `generation` means nothing."""
    from app.ai.anthropic_provider import _system_blocks

    a = _system_blocks(request_for(grounding={"b": 2, "a": 1}))
    b = _system_blocks(request_for(grounding={"a": 1, "b": 2}))
    assert a == b


def test_grounding_sits_after_the_cache_breakpoint_not_inside_it() -> None:
    """The stable half is cached; the per-call half must not be.

    Caching is a prefix match. One block holding both would write a new entry on
    every request and read none — paying the premium forever for no hit.
    """
    from app.ai.anthropic_provider import _system_blocks

    blocks = _system_blocks(request_for(grounding={"pages": 47}, cache_system=True))
    assert isinstance(blocks, list) and len(blocks) == 2
    assert blocks[0]["text"] == "You are a test."
    assert blocks[0]["cache_control"] == {"type": "ephemeral"}
    assert "47" in blocks[1]["text"]
    assert "cache_control" not in blocks[1]


# ── Vendor errors are mapped, never leaked ────────────────────


class _VendorError(Exception):
    def __init__(self, status_code: int) -> None:
        super().__init__(f"vendor said {status_code} and echoed the whole prompt back")
        self.status_code = status_code


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (401, LlmAuthError),
        (403, LlmAuthError),
        (429, LlmTransientError),
        (500, LlmTransientError),
        (503, LlmTransientError),
        (400, LlmRequestError),
        (413, LlmRequestError),
    ],
)
def test_vendor_status_codes_map_to_our_error_types(status: int, expected: type[Exception]) -> None:
    """So a caller can branch on kind without importing the SDK or matching
    on a message string."""
    from app.ai.anthropic_provider import _map_error

    assert isinstance(_map_error(_VendorError(status)), expected)


def test_a_mapped_error_never_carries_the_vendor_message() -> None:
    """A vendor error can echo the request back, and the request carries
    customer content. Only the type crosses the boundary."""
    from app.ai.anthropic_provider import _map_error

    mapped = _map_error(_VendorError(500))
    assert "echoed the whole prompt back" not in str(mapped)


@pytest.mark.parametrize("status", [408, 429, 500, 502, 503, 504])
def test_transient_failures_are_retryable(status: int) -> None:
    from app.ai.anthropic_provider import _is_retryable

    assert _is_retryable(_VendorError(status)) is True


@pytest.mark.parametrize("status", [400, 401, 403, 404, 413, 422])
def test_deterministic_failures_are_not_retried(status: int) -> None:
    """A second identical request gets the same rejection and spends the
    budget twice."""
    from app.ai.anthropic_provider import _is_retryable

    assert _is_retryable(_VendorError(status)) is False


# ── The isolation claim ───────────────────────────────────────


def test_nothing_outside_the_ai_package_names_the_vendor() -> None:
    """The claim that makes the provider swappable, asserted rather than trusted.

    The boundary is the `app/ai/` package, not a single file: `registry.py`
    legitimately names `AnthropicProvider` because selecting the implementation
    is its entire job. What must never happen is a route, a calculator or a
    retrieval module reaching for the SDK directly — that is what turns "swap
    the provider" from a config change into a refactor, and D11 leaves open
    whether a second provider is ever needed.

    `config.py` is exempt: it holds the key and the model name, which are
    configuration rather than an SDK dependency.
    """
    from pathlib import Path

    app_dir = Path(__file__).resolve().parents[1] / "app"
    offenders = sorted(
        path.relative_to(app_dir).as_posix()
        for path in app_dir.rglob("*.py")
        if "anthropic" in path.read_text(encoding="utf-8").lower()
        and path.parent.name != "ai"
        and path.name != "config.py"
    )

    assert offenders == [], (
        f"the vendor is named outside app/ai/: {offenders}. "
        "Depend on app.ai.contracts.LlmProvider instead."
    )


def test_the_provider_protocol_is_satisfied_by_both_test_doubles() -> None:
    """Structural, so a new provider cannot silently miss a method."""
    assert isinstance(UnavailableProvider(), LlmProvider)
    assert isinstance(ScriptedProvider(), LlmProvider)
