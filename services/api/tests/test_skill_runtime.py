"""The skill runtime's invariants, and the one that replaces ADR 0019's ban.

The interesting test here is `test_a_question_targeting_an_undeclared_field_is_refused`.
ADR 0019 forbade generated questions because a generated question has no scope
tag. ADR 0025 lifts that ban on the condition that the tag comes from a declared
catalogue instead of from the model — so that condition needs a test, or the ADR
is a promise rather than a mechanism.
"""

from __future__ import annotations

import pytest

from app.ai.contracts import CompletionRequest
from app.ai.runtime import fields as fields_module
from app.ai.runtime.fields import (
    FIELD_CATALOGUE,
    FieldKind,
    FieldSpec,
    UndeclaredFieldError,
    askable_fields,
    fields_for_prompt,
    resolve,
)
from app.ai.runtime.runner import validate
from app.ai.runtime.skills import SkillRegistry


@pytest.fixture(scope="module")
def registry() -> SkillRegistry:
    return SkillRegistry().load()


# ── The skills on disk ────────────────────────────────────────


def test_every_skill_on_disk_loads(registry: SkillRegistry) -> None:
    """A malformed skill must fail the process, not a customer's onboarding."""
    assert registry.names(), "no skills loaded"
    for manifest in registry.all():
        assert manifest.prompt.strip(), f"{manifest.name}: empty prompt"
        assert manifest.description.strip(), f"{manifest.name}: no description"


def test_every_declared_write_resolves_to_a_catalogue_field(registry: SkillRegistry) -> None:
    for manifest in registry.all():
        for key in manifest.writes:
            spec = resolve(key)
            assert spec.key == key


def test_no_skill_declares_a_write_it_cannot_reach(registry: SkillRegistry) -> None:
    """A skill's blast radius is what it declares, and it must be reachable.

    Catches the copy-paste failure where a new skill inherits another's `writes`
    list and quietly gains permission to overwrite fields it never mentions.
    """
    for manifest in registry.all():
        for key in manifest.writes:
            kind = resolve(key).kind
            if kind is FieldKind.PERSONA:
                assert "persona" in manifest.name or "discovery" in manifest.name, (
                    f"{manifest.name} writes persona field {key} but is not a persona skill"
                )


# ── Persona is not authorisation ──────────────────────────────


def test_no_persona_field_carries_a_widening_scope() -> None:
    for spec in FIELD_CATALOGUE.values():
        if spec.kind is FieldKind.PERSONA:
            assert spec.scope == 5, f"{spec.key} is stored at L{spec.scope}, not L5"


def test_a_role_shaped_persona_field_fails_the_assertion() -> None:
    """Plant the violation and watch the guard fire.

    An absence ("we never added a role field") is easy to erode by addition. This
    proves the guard would actually catch the addition rather than being a
    comment that happens to be true today.
    """
    poisoned = FieldSpec(
        "persona.department_access", FieldKind.PERSONA, 5, "Departments", "which departments"
    )
    original = fields_module._SPECS
    fields_module._SPECS = (*original, poisoned)
    try:
        with pytest.raises(AssertionError, match="looks like authorisation"):
            fields_module.assert_persona_is_not_authorisation()
    finally:
        fields_module._SPECS = original
    fields_module.assert_persona_is_not_authorisation()


# ── The ADR 0025 condition ────────────────────────────────────


def test_a_question_targeting_an_undeclared_field_is_refused() -> None:
    """The mechanism that makes a generated question storable.

    The model may word the question however it likes. It may not invent the
    field, because the field is where the answer's sensitivity comes from.
    """
    with pytest.raises(UndeclaredFieldError, match="not a declared field"):
        resolve("brain.annual_revenue")


def test_a_skill_cannot_write_a_field_it_did_not_declare(registry: SkillRegistry) -> None:
    """Second gate: the field exists, but not for this skill."""
    from app.ai.runtime.runner import SkillRunner

    runner = SkillRunner(provider=object(), registry=registry)  # type: ignore[arg-type]
    # A real catalogue field, and a real skill that does not declare it.
    assert "fact.finance.approval_threshold" in FIELD_CATALOGUE
    assert "fact.finance.approval_threshold" not in registry.get("persona-builder").writes
    with pytest.raises(UndeclaredFieldError, match="does not declare"):
        runner.check_target("persona-builder", "fact.finance.approval_threshold")


def test_the_prompt_never_sees_a_scope_tag() -> None:
    """A model that could see the tag could reason about how to get a looser one.

    Written as an allowlist plus a named denylist rather than an exact-set
    equality. The equality version failed when `answer_shape` was added — a
    deliberate addition, and one that carries no sensitivity information — which
    made a correct change look like a violation of the rule this guards. The
    rule is *what must never appear*, so that is what is asserted, and the
    allowlist still catches a field leaking in by accident.
    """
    shown = fields_for_prompt(askable_fields())
    assert shown
    allowed = {"key", "label", "intent", "answer_shape"}
    for entry in shown:
        assert set(entry) <= allowed, f"unexpected key in the prompt: {set(entry) - allowed}"
        # The three that would let a model reason about storage rather than
        # about the question.
        assert not {"scope", "column", "kind"} & set(entry)


def test_askable_excludes_what_a_source_can_answer() -> None:
    askable = {spec.key for spec in askable_fields()}
    assert "brain.target_customers" in askable, "only the owner knows this"
    assert "brain.profile" not in askable, "the crawl answers this; asking wastes a turn"


# ── The request the provider actually sends ───────────────────


@pytest.mark.parametrize(
    "model,expect_temperature",
    [
        ("claude-opus-5", False),
        ("claude-sonnet-5", False),
        ("claude-opus-4-7", False),
        ("claude-haiku-4-5", True),
    ],
)
def test_sampling_parameters_are_omitted_where_they_are_rejected(
    model: str, expect_temperature: bool
) -> None:
    """Sending `temperature` to Opus 5 is a 400.

    The provider used to send it unconditionally, so every skill would have
    failed the moment the configured tier moved forward.
    """
    from app.ai.anthropic_provider import _request_kwargs

    request = CompletionRequest(skill="s", system="sys", messages=[])
    kwargs = _request_kwargs(request, model, [])
    assert ("temperature" in kwargs) is expect_temperature


def test_effort_is_omitted_on_tiers_that_reject_it() -> None:
    from app.ai.anthropic_provider import _request_kwargs

    request = CompletionRequest(skill="s", system="sys", messages=[], effort="high")
    assert "effort" in _request_kwargs(request, "claude-opus-5", [])["output_config"]
    assert "output_config" not in _request_kwargs(request, "claude-haiku-4-5", [])


def test_a_cached_system_prompt_is_sent_as_a_marked_block() -> None:
    from app.ai.anthropic_provider import _request_kwargs

    request = CompletionRequest(skill="s", system="sys", messages=[], cache_system=True)
    system = _request_kwargs(request, "claude-opus-5", [])["system"]
    assert system[0]["cache_control"] == {"type": "ephemeral"}


def test_a_response_schema_becomes_a_json_schema_output_format() -> None:
    from app.ai.anthropic_provider import _request_kwargs

    schema = {"type": "object", "properties": {}, "required": []}
    request = CompletionRequest(skill="s", system="sys", messages=[], response_schema=schema)
    fmt = _request_kwargs(request, "claude-opus-5", [])["output_config"]["format"]
    assert fmt["type"] == "json_schema"
    assert fmt["schema"] == schema


# ── The validator ─────────────────────────────────────────────


def test_validator_catches_a_missing_required_key() -> None:
    schema = {"type": "object", "properties": {"a": {"type": "string"}}, "required": ["a"]}
    assert validate({}, schema) == ["$.a: required, and missing"]
    assert validate({"a": "x"}, schema) == []


def test_validator_does_not_accept_a_boolean_as_an_integer() -> None:
    """`isinstance(True, int)` is True in Python, which is the bug this catches."""
    assert validate(True, {"type": "integer"}) == ["$: expected integer, got boolean"]


def test_validator_checks_enums_and_nested_arrays() -> None:
    schema = {
        "type": "object",
        "properties": {
            "items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {"kind": {"type": "string", "enum": ["read", "inferred"]}},
                    "required": ["kind"],
                },
            }
        },
        "required": ["items"],
    }
    assert validate({"items": [{"kind": "read"}]}, schema) == []
    problems = validate({"items": [{"kind": "guessed"}]}, schema)
    assert problems == ["$.items[0].kind: 'guessed' is not one of ['read', 'inferred']"]


def test_every_skill_schema_is_itself_walkable(registry: SkillRegistry) -> None:
    """A schema the validator cannot walk would pass everything silently."""
    for manifest in registry.all():
        if manifest.schema is None:
            continue
        assert manifest.schema.get("type") == "object", f"{manifest.name}: root must be an object"
        assert manifest.schema.get("required"), f"{manifest.name}: schema requires nothing"


# ── No dead skills ────────────────────────────────────────────


def test_every_skill_is_reachable_from_a_command(registry: SkillRegistry) -> None:
    """A skill no command reaches is maintained for nothing."""
    from app.ai.runtime.commands import get_commands

    reachable = get_commands().skills_used()
    orphans = sorted(set(registry.names()) - reachable)
    assert not orphans, f"skills on disk that no command invokes: {orphans}"


# ── Present but empty ─────────────────────────────────────────
#
# Both of these come from one live run. `question-generation` returned a valid
# `target` with `question: ""`, every existing gate passed it, and the founder
# was shown a blank card with a Send button under it. "Required" was true and
# useless; the missing idea was that a string can be there and say nothing.


def test_the_validator_enforces_min_length() -> None:
    schema = {"type": "object", "properties": {"question": {"type": "string", "minLength": 1}}}
    assert validate({"question": "why?"}, schema) == []
    problems = validate({"question": ""}, schema)
    assert problems and "at least 1 character" in problems[0]


def test_question_generation_requires_a_non_empty_question(registry: SkillRegistry) -> None:
    """The schema on disk must refuse the empty string, not merely allow a key."""
    schema = registry.get("question-generation").schema
    # Asserted, not assumed: `schema` is optional on the manifest, and a skill
    # that lost its schema would otherwise fail below with a confusing
    # `NoneType is not subscriptable` rather than saying what is missing.
    assert schema is not None, "question-generation has no schema on disk"
    assert schema["properties"]["question"].get("minLength") == 1
    assert schema["properties"]["target"].get("minLength") == 1
    assert validate({"done": False, "question": "", "target": "x"}, schema)


def test_persona_builder_is_given_the_keys_it_must_use(registry: SkillRegistry) -> None:
    """Every key the skill may write has to be one the runtime puts in front of it.

    The filter in `build_persona` refuses anything outside the catalogue, so a
    skill left to guess key names produces an empty persona and a log full of
    correct refusals — which is what happened before `persona_fields` was
    grounded.
    """
    from app.ai.runtime.fields import persona_fields

    manifest = registry.get("persona-builder")
    assert "persona_fields" in manifest.requires_grounding
    offered = {entry["key"] for entry in fields_for_prompt(persona_fields())}
    assert set(manifest.writes) <= offered


def test_company_summary_is_given_the_keys_a_statement_may_name(
    registry: SkillRegistry,
) -> None:
    """A brief statement's `field` is a correction key, so it must resolve.

    This is the same defect as the persona one and was found the same way: the
    skill invented `profile` for `brain.profile`, plus two keys in no catalogue
    at all. Every statement rendered an edit box that could not be saved — on the
    one screen whose entire instruction is "correct anything that is wrong".
    """
    from app.ai.runtime.fields import brain_fields

    manifest = registry.get("company-summary")
    assert "brain_fields" in manifest.requires_grounding
    offered = {entry["key"] for entry in fields_for_prompt(brain_fields())}
    assert offered, "no brain fields offered"
    # Every key the skill is shown resolves, and none of them is a bare name.
    for key in offered:
        assert resolve(key).kind is FieldKind.BRAIN
        assert key.startswith("brain."), key


def test_a_brief_statement_key_is_not_a_bare_field_name() -> None:
    """The specific keys the model reached for, kept as a regression."""
    for invented in ("profile", "brand_voice", "products_services"):
        with pytest.raises(UndeclaredFieldError):
            resolve(invented)
        assert f"brain.{invented}" in FIELD_CATALOGUE or invented == "profile_disclaimer"


def test_a_thinking_skill_has_room_to_think(registry: SkillRegistry) -> None:
    """A skill that reasons needs a budget bigger than its answer.

    **Three skills have failed this way**, each discovered by a customer-shaped
    run rather than by a test:

    - `persona-builder` at `high` effort with 2048 tokens — spent the whole
      allowance thinking, emitted no valid JSON, and 502'd every journey at the
      persona stage.
    - `context-personalization` at `medium` with 2048 — the same, at the *last*
      stage, with the entire interview already collected.
    - `user-discovery` at `medium` with 2048 — same shape, not yet observed
      failing, which is the only reason it was not a third incident.

    On this model the reasoning budget and the answer share one allowance, so
    the failure is not "the answer was too long" — it is that nothing was left
    to write the answer with. It arrives as `stop_reason=max_tokens`, the runner
    retries an identical request, and it fails the same way twice.

    4096 is a floor rather than a recommendation: `company-research` runs at
    `high` on exactly that and is fine. `low` is exempt because
    `company-summary` works at 2048 and has never truncated.
    """
    thinking = {"medium", "high", "xhigh", "max"}
    thin = {
        name: (manifest.effort, manifest.max_output_tokens)
        for name in registry.names()
        for manifest in [registry.get(name)]
        if manifest.effort in thinking and manifest.max_output_tokens < 4096
    }
    assert not thin, (
        f"these skills reason but cannot afford to: {thin}. The reasoning budget "
        f"and the answer share one allowance — see this test's docstring."
    )
