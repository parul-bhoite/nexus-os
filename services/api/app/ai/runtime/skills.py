"""Skills as files on disk, not prompts buried in Python.

A skill is a directory. Three files, and the split is the whole point:

    company-research/
      manifest.toml   what tier runs it, what it may write, how it is cached
      SKILL.md        the system prompt — prose, editable by someone who is not
                      a Python developer
      schema.json     the shape of its output, enforced at decode time

Changing how a skill behaves is editing `SKILL.md`. Changing what it costs is
editing one line of `manifest.toml`. Neither is a code change, neither needs a
deploy of anything but the files, and neither can silently widen what the skill
is allowed to write — because `writes` is validated against the field catalogue
at load, and the runner refuses to store anything outside it.

The manifest is loaded and validated at startup rather than on first use. A
malformed skill should fail the process, not the customer's onboarding: the
failure is ours and it should be found by CI, not by a person halfway through
signing up.
"""

from __future__ import annotations

import json
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.ai.runtime.fields import FIELD_CATALOGUE, FieldSpec, resolve
from app.logging import get_logger

log = get_logger(__name__)

SKILLS_ROOT = Path(__file__).resolve().parent.parent / "skills"

VALID_EFFORT = frozenset({"low", "medium", "high", "xhigh", "max"})
"""What a manifest — or a per-call override — may ask for.

Public because `SkillRunner.invoke` accepts an override and has to check it
against the same set. A second copy there is a second thing to keep in step, and
the failure it would produce is a 400 from the provider at the end of a slow
call rather than a refusal before it.
"""

_VALID_EFFORT = VALID_EFFORT


class SkillDefinitionError(Exception):
    """A skill on disk is malformed. Raised at load, never at call time."""


@dataclass(frozen=True, slots=True)
class SkillManifest:
    name: str
    version: str
    description: str
    prompt: str
    schema: Mapping[str, Any] | None

    model: str | None = None
    effort: str | None = None
    max_output_tokens: int = 2048
    cache_system: bool = True
    timeout_seconds: float = 60.0

    writes: tuple[str, ...] = ()
    """Field-catalogue keys this skill may produce values for.

    Validated against `FIELD_CATALOGUE` at load. The runner will not persist a
    value for a key absent from here even if the model returns one — a skill's
    blast radius is declared, not discovered at runtime.
    """

    requires_grounding: tuple[str, ...] = ()
    """Keys that must be present in `grounding` before this skill may run.

    Grounding holds values already fetched or computed in deterministic code
    (I1). Declaring them means a caller cannot forget one and get a model that
    quietly invents it instead.
    """

    tags: tuple[str, ...] = field(default_factory=tuple)

    @property
    def write_specs(self) -> tuple[FieldSpec, ...]:
        return tuple(resolve(key) for key in self.writes)


def _read(directory: Path, filename: str, *, required: bool = True) -> str | None:
    path = directory / filename
    if not path.exists():
        if required:
            raise SkillDefinitionError(f"{directory.name}: {filename} is missing")
        return None
    text = path.read_text(encoding="utf-8").strip()
    if required and not text:
        raise SkillDefinitionError(f"{directory.name}: {filename} is empty")
    return text


def load_manifest(directory: Path) -> SkillManifest:
    raw_toml = _read(directory, "manifest.toml")
    assert raw_toml is not None
    try:
        data: dict[str, Any] = tomllib.loads(raw_toml)
    except tomllib.TOMLDecodeError as exc:
        raise SkillDefinitionError(
            f"{directory.name}: manifest.toml is not valid TOML: {exc}"
        ) from exc

    prompt = _read(directory, "SKILL.md")
    assert prompt is not None

    raw_schema = _read(directory, "schema.json", required=False)
    schema: Mapping[str, Any] | None = None
    if raw_schema:
        try:
            schema = json.loads(raw_schema)
        except json.JSONDecodeError as exc:
            raise SkillDefinitionError(
                f"{directory.name}: schema.json is not valid JSON: {exc}"
            ) from exc

    for required_key in ("name", "version", "description"):
        if not data.get(required_key):
            raise SkillDefinitionError(f"{directory.name}: manifest.toml needs a '{required_key}'")

    if data["name"] != directory.name:
        # The name is the identity used by the kill switch, the budget and the
        # `generation` row. A manifest whose name drifts from its directory
        # makes every one of those point at something that is not there.
        raise SkillDefinitionError(
            f"{directory.name}: manifest name is {data['name']!r}; it must match the directory"
        )

    effort = data.get("effort")
    if effort is not None and effort not in _VALID_EFFORT:
        raise SkillDefinitionError(
            f"{directory.name}: effort {effort!r} is not one of {sorted(_VALID_EFFORT)}"
        )

    writes = tuple(data.get("writes", ()))
    unknown = [key for key in writes if key not in FIELD_CATALOGUE]
    if unknown:
        raise SkillDefinitionError(
            f"{directory.name}: declares writes to undeclared fields {unknown}. "
            f"Add them to app/ai/runtime/fields.py with a scope, or remove them."
        )

    return SkillManifest(
        name=str(data["name"]),
        version=str(data["version"]),
        description=str(data["description"]),
        prompt=prompt,
        schema=schema,
        model=data.get("model"),
        effort=effort,
        max_output_tokens=int(data.get("max_output_tokens", 2048)),
        cache_system=bool(data.get("cache_system", True)),
        timeout_seconds=float(data.get("timeout_seconds", 60.0)),
        writes=writes,
        requires_grounding=tuple(data.get("requires_grounding", ())),
        tags=tuple(data.get("tags", ())),
    )


class SkillRegistry:
    """Every skill on disk, loaded once and addressable by name."""

    def __init__(self, root: Path | None = None) -> None:
        self._root = root or SKILLS_ROOT
        self._skills: dict[str, SkillManifest] = {}

    def load(self) -> SkillRegistry:
        if not self._root.exists():
            raise SkillDefinitionError(f"no skills directory at {self._root}")
        found: dict[str, SkillManifest] = {}
        for directory in sorted(p for p in self._root.iterdir() if p.is_dir()):
            if directory.name.startswith((".", "_")):
                continue
            manifest = load_manifest(directory)
            found[manifest.name] = manifest
        if not found:
            raise SkillDefinitionError(f"{self._root} contains no skills")
        self._skills = found
        log.info("ai.skills.loaded", count=len(found), skills=sorted(found))
        return self

    def get(self, name: str) -> SkillManifest:
        try:
            return self._skills[name]
        except KeyError:
            raise SkillDefinitionError(
                f"no skill named {name!r}; loaded: {sorted(self._skills)}"
            ) from None

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._skills))

    def all(self) -> tuple[SkillManifest, ...]:
        return tuple(self._skills[name] for name in self.names())

    def writers_of(self, field_key: str) -> tuple[str, ...]:
        """Which skills may write this field. Used by the coverage test."""
        return tuple(m.name for m in self.all() if field_key in m.writes)


_registry: SkillRegistry | None = None


def get_registry() -> SkillRegistry:
    """Process-wide, loaded on first use.

    Not `lru_cache`d on a function with arguments, because the tests need to
    build a registry over a fixture directory without poisoning this one.
    """
    global _registry
    if _registry is None:
        _registry = SkillRegistry().load()
    return _registry
