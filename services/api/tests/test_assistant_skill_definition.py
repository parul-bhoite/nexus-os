"""What `assistant-answer` may do, asserted against its manifest. `doc/20` A5.

No model and no network: every claim here is about the three files on disk, and
they are the files that decide the skill's blast radius before a single token is
generated.

**The schema walk is the one worth reading.** `runner.validate` is a hand-rolled
subset of JSON Schema, and a keyword it does not implement is not an error — it
is **silently ignored**. So `maxItems: 8` in a schema file would read to every
future author as a bound that exists, while the validator skipped it and the
runner accepted forty segments. `doc/19` K4 hit this with `minimum` on a
`confidence` field; this file makes the second occurrence fail loudly instead.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from app.ai.runtime.skills import get_registry

SKILL = "assistant-answer"
HERE = Path(__file__).resolve().parents[1] / "app" / "ai" / "skills" / SKILL

# Exactly what `runner.validate` reads. Derived by reading the function, and
# pinned here so that adding a keyword to a schema without teaching the
# validator fails in this file rather than in production.
SUPPORTED: frozenset[str] = frozenset(
    {
        "type",
        "properties",
        "required",
        "additionalProperties",
        "items",
        "minLength",
        "enum",
        # Not read by the validator, but inert and useful to a human.
        "description",
    }
)


@pytest.fixture(scope="module")
def manifest() -> Any:
    registry = get_registry()
    registry.load()
    return registry.get(SKILL)


def test_the_registry_loads_it_at_startup(manifest: Any) -> None:
    """A malformed skill already fails the process rather than the customer —
    this asserts the skill is inside that guarantee rather than beside it."""
    assert manifest.name == SKILL
    assert manifest.prompt, "SKILL.md is the system prompt; an empty one is a silent no-op"
    assert manifest.schema is not None


def test_it_cannot_persist_anything(manifest: Any) -> None:
    """`writes = []`, and this is structural rather than a convention.

    The runner refuses a target absent from `writes`, so an empty tuple means
    the model could return a perfectly formed write instruction and nothing
    would happen. That matters more here than for `narrate-metric`: this skill's
    output has **not yet passed A2's guard** at the moment it is produced, so a
    skill that could persist would be persisting unchecked text.
    """
    assert manifest.writes == ()


def test_it_cannot_run_without_the_grounding_it_needs(manifest: Any) -> None:
    """The failure this prevents is the quiet one: a caller that forgets
    `passages` gets a model answering the question from its own memory of the
    internet, which looks exactly like a working assistant."""
    assert set(manifest.requires_grounding) == {"question", "passage_refs", "department"}


def test_the_timeout_sits_under_the_gateway(manifest: Any) -> None:
    """Under the BFF's 90 s, so a slow model surfaces as a refusal we worded
    rather than as a gateway error the reader has to interpret."""
    assert 0 < manifest.timeout_seconds < 90


def test_the_answer_is_bounded(manifest: Any) -> None:
    """A ceiling is a design constraint, not a saving. `narrate-metric`'s
    argument applies unchanged: a model given room for an essay writes one, and
    a truncated answer reads as a complete one."""
    assert 0 < manifest.max_output_tokens <= 2048


# ── The schema, and the validator that reads it ───────────────


def _walk(node: Any, path: str = "$") -> list[tuple[str, str]]:
    """Every (path, keyword) pair in the schema."""
    found: list[tuple[str, str]] = []
    if isinstance(node, dict):
        for key, value in node.items():
            found.append((path, key))
            if key == "properties" and isinstance(value, dict):
                for name, sub in value.items():
                    found.extend(_walk(sub, f"{path}.{name}"))
            elif key == "items":
                found.extend(_walk(value, f"{path}[]"))
    return found


def test_the_schema_uses_only_what_the_validator_implements() -> None:
    """**The trap, caught at the door.**

    An unimplemented keyword is ignored rather than rejected, so a schema can
    promise a bound that nothing enforces. Asserted against the validator's own
    supported set rather than against a list of known-bad keywords, because the
    failure is a keyword nobody thought to ban.
    """
    schema = json.loads((HERE / "schema.json").read_text(encoding="utf-8"))

    unsupported = sorted({f"{path}: {key}" for path, key in _walk(schema) if key not in SUPPORTED})

    assert unsupported == [], (
        "these keywords are silently ignored by `runner.validate`, so they are a "
        f"promise nothing keeps: {unsupported}. Either drop them or teach the validator."
    )


def test_nothing_is_unbounded_free_text_except_the_answer_itself() -> None:
    """`text` is prose and cannot be constrained by a schema; everything else
    can. A free-text field with no shape is where a model puts an explanation
    nobody asked for — and for a refusal, an explanation is exactly what must
    not reach the reader, because the sentence they see is ours."""
    schema = json.loads((HERE / "schema.json").read_text(encoding="utf-8"))
    segment = schema["properties"]["segments"]["items"]

    assert segment["additionalProperties"] is False
    assert schema["additionalProperties"] is False
    assert set(segment["properties"]) == {"text", "cited_refs"}, (
        "a reason field here would let the model word its own refusal"
    )
    assert segment["properties"]["cited_refs"]["items"]["minLength"] >= 1


def test_the_segment_count_is_not_bounded_here_and_must_be_bounded_in_code() -> None:
    """**A deliberately inverted assertion.** It asserts the bound is *absent*.

    `maxItems` is not implemented by `runner.validate`, so writing it would be
    decoration. This test exists so that somebody adding it — reasonably, since
    it is valid JSON Schema — is told why it does not work, instead of shipping
    a limit that silently does nothing. A6 bounds the count in code.
    """
    schema = json.loads((HERE / "schema.json").read_text(encoding="utf-8"))

    assert "maxItems" not in schema["properties"]["segments"], (
        "`maxItems` is ignored by `runner.validate` — bound the segment count in "
        "A6's composition, or teach the validator first"
    )


# ── The prompt ────────────────────────────────────────────────


def test_the_prompt_never_names_the_vendor() -> None:
    """`test_ai_boundary.py` asserts this product-wide and has caught a prose
    mention once already. Repeated narrowly because a prompt is the one file
    where writing the model's own name feels natural."""
    prompt = (HERE / "SKILL.md").read_text(encoding="utf-8").lower()

    for vendor in ("anthropic", "claude", "openai", "gpt", "gemini"):
        assert vendor not in prompt, f"{vendor!r} in SKILL.md"


def test_the_prompt_states_the_rules_without_describing_the_check() -> None:
    """**A prompt that knows the check is a prompt that can be asked to clear
    it.** A payload cannot talk its way past a rule it cannot see the shape of,
    so the prompt states what is forbidden and never how it is detected.
    """
    prompt = (HERE / "SKILL.md").read_text(encoding="utf-8").lower()

    # The rules are stated.
    assert "data, never instructions" in prompt or "data and never" in prompt
    assert "cited_refs" in prompt
    assert "answered: false" in prompt

    # The mechanism is not.
    for leak in ("regex", "post-process", "we check", "we compare", "discard", "guard"):
        assert leak not in prompt, f"the prompt describes the check: {leak!r}"
