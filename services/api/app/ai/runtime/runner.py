"""Running a skill: build the request, validate the answer, refuse the rest.

The pipeline is doc 06 §8's, unchanged: fetch and compute deterministically,
make **one** model call, validate the response against the skill's schema, retry
exactly once, then give up honestly. Not exponential backoff across many
attempts — a call that fails twice should surface as unavailable rather than be
retried until the budget is gone.

Three things this enforces that a prompt cannot:

**Declared grounding.** A skill that lists `requires_grounding` will not run
without those values. Without the check, a caller who forgot one gets a model
that invents it instead, and I1 is broken quietly rather than loudly.

**Declared writes.** Every `target` the model returns is checked against the
skill's manifest *and* the field catalogue. A skill cannot write a field it did
not declare, whatever the model returns.

**Schema, twice.** `output_config.format` constrains the response at decode time
and the runner validates it again on receipt. That is not belt-and-braces for its
own sake: the second check is what produces the failure rate worth watching, and
a provider that validated for us would swallow it.
"""

from __future__ import annotations

import json
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from app.ai.contracts import (
    Completion,
    CompletionRequest,
    LlmProvider,
    Message,
)
from app.ai.runtime.fields import FieldSpec, UndeclaredFieldError, resolve
from app.ai.runtime.hooks import HookBus, HookEvent, HookPoint
from app.ai.runtime.skills import VALID_EFFORT, SkillManifest, SkillRegistry, get_registry
from app.logging import get_logger

log = get_logger(__name__)


class SkillFailedError(Exception):
    """The skill ran and did not produce a usable answer.

    Distinct from `LlmError`: the provider worked, the output was unusable. The
    caller renders an honest unavailable state — it never falls back to a
    plausible default, because a fabricated brain is the thing this product
    exists not to be.
    """


class SkillOutputInvalidError(SkillFailedError):
    """Two attempts, neither matched the schema."""


@dataclass(frozen=True, slots=True)
class SkillResult:
    skill: str
    version: str
    data: Mapping[str, Any]
    completion: Completion
    attempts: int

    @property
    def usage_summary(self) -> dict[str, int]:
        return {
            "input_tokens": self.completion.usage.input_tokens,
            "output_tokens": self.completion.usage.output_tokens,
        }


# ── A small schema validator ──────────────────────────────────
#
# Deliberately not a new dependency. The repository has no lockfile (finding
# #16), so every added package is one more thing CI resolves differently from
# every developer, and this needs to cover exactly the subset our own schemas
# use: object, array, string, integer, number, boolean, required, enum and
# minLength. When a skill needs more than this, add the dependency then — with
# a pin.


def validate(value: Any, schema: Mapping[str, Any], path: str = "$") -> list[str]:
    """Return a list of human-readable problems. Empty means valid."""
    problems: list[str] = []
    expected = schema.get("type")

    if expected == "object":
        if not isinstance(value, dict):
            return [f"{path}: expected an object, got {type(value).__name__}"]
        for key in schema.get("required", []):
            if key not in value:
                problems.append(f"{path}.{key}: required, and missing")
        properties: Mapping[str, Any] = schema.get("properties", {})
        if schema.get("additionalProperties") is False:
            for key in value:
                if key not in properties:
                    problems.append(f"{path}.{key}: not allowed by the schema")
        for key, sub in properties.items():
            if key in value:
                problems.extend(validate(value[key], sub, f"{path}.{key}"))
        return problems

    if expected == "array":
        if not isinstance(value, list):
            return [f"{path}: expected an array, got {type(value).__name__}"]
        items = schema.get("items")
        if isinstance(items, dict):
            for index, item in enumerate(value):
                problems.extend(validate(item, items, f"{path}[{index}]"))
        return problems

    checks: dict[str, type | tuple[type, ...]] = {
        "string": str,
        "integer": int,
        "number": (int, float),
        "boolean": bool,
    }
    if expected in checks:
        # bool is an int in Python; an integer field must not accept True.
        if expected in {"integer", "number"} and isinstance(value, bool):
            problems.append(f"{path}: expected {expected}, got boolean")
        elif not isinstance(value, checks[expected]):
            problems.append(f"{path}: expected {expected}, got {type(value).__name__}")

    # `minLength` earns its place because "present but empty" is a real failure
    # mode rather than a hypothetical one: a question-generation response naming
    # a valid target with `question: ""` passed every other check here and put a
    # blank agent turn on the screen.
    minimum = schema.get("minLength")
    if minimum is not None and isinstance(value, str) and len(value) < minimum:
        problems.append(f"{path}: expected at least {minimum} character(s), got {len(value)}")

    allowed = schema.get("enum")
    if allowed is not None and value not in allowed:
        problems.append(f"{path}: {value!r} is not one of {allowed}")

    return problems


# ── The runner ────────────────────────────────────────────────


class SkillRunner:
    """Invokes skills. Constructed once per process, injected into commands."""

    def __init__(
        self,
        provider: LlmProvider,
        registry: SkillRegistry | None = None,
        *,
        hooks: HookBus | None = None,
        workspace_id: str | None = None,
    ) -> None:
        self._provider = provider
        self._registry = registry or get_registry()
        self._hooks = hooks
        self._workspace_id = workspace_id
        """Both or neither. `SKILL_INVOKED` is emitted only when the runner was
        given somewhere to send it and a workspace to attribute it to — a hook
        with no workspace is an observation nobody can act on."""

    @property
    def registry(self) -> SkillRegistry:
        return self._registry

    async def invoke(
        self,
        skill_name: str,
        *,
        messages: Sequence[Message],
        grounding: Mapping[str, Any] | None = None,
        effort: str | None = None,
    ) -> SkillResult:
        """Run a skill once, validate, retry once.

        `effort` overrides the manifest for this call only. It exists for one
        real case: `company-brain-builder` is invoked once per field group, and
        the groups are not equally hard — see `BrainGroup.effort`, where the
        measurement is. Everything else passes None and gets what the manifest
        declares, which stays the default and the documented value.

        Validated against the same set the manifest loader uses, because an
        effort the provider does not recognise is a 400 at the far end of a slow
        call rather than an error here.
        """
        manifest = self._registry.get(skill_name)
        grounding = dict(grounding or {})

        if effort is not None and effort not in VALID_EFFORT:
            raise SkillFailedError(
                f"{skill_name}: effort {effort!r} is not one of {sorted(VALID_EFFORT)}"
            )

        missing = [key for key in manifest.requires_grounding if key not in grounding]
        if missing:
            # A skill that runs without its grounding gets a model inventing the
            # values instead. Loud is the whole point.
            raise SkillFailedError(
                f"{skill_name}: missing required grounding {missing}. These are "
                f"computed in code and passed in; the model must not derive them."
            )

        request = CompletionRequest(
            skill=manifest.name,
            system=manifest.prompt,
            messages=list(messages),
            grounding=grounding,
            max_output_tokens=manifest.max_output_tokens,
            response_schema=manifest.schema,
            model=manifest.model,
            effort=effort or manifest.effort,
            cache_system=manifest.cache_system,
            timeout_seconds=manifest.timeout_seconds,
        )

        started = time.monotonic()
        last_problems: list[str] = []
        for attempt in (1, 2):
            completion = await self._provider.complete(request)

            if completion.truncated:
                # A truncated answer read as a complete one is worse than none —
                # half a brief looks like a whole brief.
                last_problems = ["the response hit max_output_tokens and is incomplete"]
                if attempt == 1:
                    continue
                break

            parsed, problems = _parse(completion.text, manifest)
            if not problems and parsed is not None:
                log.info(
                    "ai.skill.ok",
                    skill=manifest.name,
                    version=manifest.version,
                    attempts=attempt,
                    total_ms=int((time.monotonic() - started) * 1000),
                )
                result = SkillResult(
                    skill=manifest.name,
                    version=manifest.version,
                    data=parsed,
                    completion=completion,
                    attempts=attempt,
                )
                await self._announce(result)
                return result

            last_problems = problems
            if attempt == 1:
                log.info("ai.skill.revalidate", skill=manifest.name, problems=problems[:3])

        log.info("ai.skill.invalid", skill=manifest.name, problems=last_problems[:5])
        raise SkillOutputInvalidError(
            f"{skill_name} did not return a valid response in two attempts: "
            + "; ".join(last_problems[:5])
        )

    async def _announce(self, result: SkillResult) -> None:
        """One observability event per successful skill call.

        Emitted here rather than from each of the six commands: the runner is
        the single place every skill call passes through, so this cannot drift
        out of step with a command that forgot to fire it. Counts and
        identifiers only — never the prompt, never the completion.
        """
        if self._hooks is None or self._workspace_id is None:
            return
        await self._hooks.emit(
            HookEvent(
                point=HookPoint.SKILL_INVOKED,
                workspace_id=self._workspace_id,
                payload={
                    "skill": result.skill,
                    "version": result.version,
                    "attempts": result.attempts,
                    "model": result.completion.model,
                    **result.usage_summary,
                },
            )
        )

    def permitted_targets(self, skill_name: str) -> tuple[FieldSpec, ...]:
        """The fields this skill is allowed to fill."""
        return self._registry.get(skill_name).write_specs

    def check_target(self, skill_name: str, target: str) -> FieldSpec:
        """Resolve a model-supplied target, or refuse it.

        Two gates, in order: the key must exist in the catalogue at all, and this
        particular skill must have declared it. The first stops an invented
        field; the second stops a skill widening its own reach.
        """
        spec = resolve(target)
        manifest = self._registry.get(skill_name)
        if target not in manifest.writes:
            raise UndeclaredFieldError(
                f"{skill_name} returned target {target!r}, which it does not declare "
                f"in manifest.toml. Declared: {list(manifest.writes)}"
            )
        return spec


def _parse(text: str, manifest: SkillManifest) -> tuple[Mapping[str, Any] | None, list[str]]:
    if manifest.schema is None:
        return {"text": text}, []

    stripped = text.strip()
    if stripped.startswith("```"):
        # Structured outputs should make this unreachable, but a fenced block is
        # the one malformation cheap enough to recover from rather than re-bill.
        stripped = stripped.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError as exc:
        return None, [f"response is not JSON: {exc}"]

    problems = validate(parsed, manifest.schema)
    return (parsed if not problems else None), problems


__all__ = [
    "SkillFailedError",
    "SkillOutputInvalidError",
    "SkillResult",
    "SkillRunner",
    "validate",
]
