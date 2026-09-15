"""The two non-vendor providers: unconfigured, and deterministic for tests.

Neither invents content. That is the whole point of both of them.

A "demo mode" that returns plausible-sounding analysis would be the single most
damaging thing this codebase could contain. The product's entire position is
that a number on the screen was fetched or computed and can be traced back to
its source; a fabricated paragraph that reads like a real recommendation
destroys that whether or not it is labelled, because the label is on the screen
and the screenshot is in the customer's email.

So `UnavailableProvider` refuses, and `ScriptedProvider` returns only what a
test explicitly told it to.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping

from app.ai.contracts import (
    Availability,
    Completion,
    CompletionRequest,
    LlmUnavailableError,
    ProviderStatus,
    Usage,
)

# ── No credentials ────────────────────────────────────────────


class UnavailableProvider:
    """What the application runs on until an API key is supplied.

    It reports `UNCONFIGURED` and raises if called. That combination is
    deliberate: callers are expected to check `status()` and render an honest
    "needs an API key" state, and one that calls anyway has a bug worth
    surfacing loudly rather than a silent empty string to paper over.
    """

    name = "unavailable"

    def __init__(
        self, *, reason: Availability = Availability.UNCONFIGURED, detail: str = ""
    ) -> None:
        self._reason = reason
        self._detail = detail or _default_detail(reason)

    def status(self) -> ProviderStatus:
        return ProviderStatus(
            availability=self._reason,
            provider=self.name,
            model=None,
            detail=self._detail,
        )

    async def complete(self, request: CompletionRequest) -> Completion:
        raise LlmUnavailableError(
            f"no language model is configured; '{request.skill}' cannot run ({self._reason.value})"
        )


def _default_detail(reason: Availability) -> str:
    return {
        Availability.UNCONFIGURED: (
            "No language model is configured. Everything else works; features that "
            "need one are marked unavailable until an API key is set."
        ),
        Availability.DISABLED: (
            "Language model features have been switched off by an administrator."
        ),
        Availability.BUDGET_EXHAUSTED: (
            "This workspace has used its language model allowance for the period."
        ),
        Availability.AVAILABLE: "Available.",
    }[reason]


# ── Deterministic, for tests ──────────────────────────────────


class ScriptedProvider:
    """Returns exactly what the test supplied, and records what it was asked.

    Not a "fake AI" — it has no behaviour of its own. A test states the response
    it wants for a skill; anything unscripted raises rather than improvising, so
    a test can never accidentally pass against invented output.

    `calls` is the assertion surface: tests check *what was sent*, which is where
    the interesting bugs are. Whether the grounding block reached the system
    prompt, whether a skill honoured its kill switch, whether customer content
    leaked into a field it should not — all of that is visible here.
    """

    name = "scripted"

    def __init__(
        self,
        responses: Mapping[str, str | Callable[[CompletionRequest], str]] | None = None,
        *,
        model: str = "scripted-model",
    ) -> None:
        self._responses = dict(responses or {})
        self._model = model
        self.calls: list[CompletionRequest] = []

    def script(self, skill: str, response: str | Callable[[CompletionRequest], str]) -> None:
        self._responses[skill] = response

    def status(self) -> ProviderStatus:
        return ProviderStatus(
            availability=Availability.AVAILABLE,
            provider=self.name,
            model=self._model,
            detail="Deterministic test provider.",
        )

    async def complete(self, request: CompletionRequest) -> Completion:
        self.calls.append(request)

        # **Refuse what the real provider refuses.**
        #
        # This is not behaviour of its own — it is fidelity, and its absence
        # cost a defect that could only ever have been found in production.
        # `grounding/answer.py::narrate` sent `messages=[]` for as long as it
        # existed. Anthropic rejects that with `messages: at least one message
        # is required` and HTTP 400, so narration was structurally incapable of
        # producing a sentence — and every test passed, because this double
        # accepted a request the API does not.
        #
        # A test double that accepts what production rejects is the pattern
        # CLAUDE.md names three times: an environment that differs from the one
        # you deploy to can be green in the place nobody deploys to.
        if not request.messages:
            raise AssertionError(
                f"skill {request.skill!r} was called with an empty message list. "
                "The real provider answers that with HTTP 400 "
                "('messages: at least one message is required'), so this would "
                "ship as PROVIDER_FAILED. Send a user turn naming the task."
            )

        if request.skill not in self._responses:
            raise AssertionError(
                f"ScriptedProvider has no response for skill {request.skill!r}. "
                "Script it explicitly — improvising here would let a test pass "
                "against output nobody wrote."
            )

        scripted = self._responses[request.skill]
        text = scripted(request) if callable(scripted) else scripted

        return Completion(
            text=text,
            model=self._model,
            provider=self.name,
            # Proportional to length so budget arithmetic can be exercised
            # without pretending to be a real tokeniser.
            usage=Usage(
                input_tokens=sum(len(m.content) for m in request.messages) // 4,
                output_tokens=len(text) // 4,
            ),
            stop_reason="end_turn",
            latency_ms=0,
        )
