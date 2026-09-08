"""The onboarding commands.

Each is one transaction's worth of work: invoke a skill, check what came back
against the declared field catalogue, persist it, emit the hook. They are the
only layer that knows about all three.

Everything model-shaped lives in the skill file; everything database-shaped lives
here. That is the seam the whole architecture turns on — changing how
`research-company` reasons is editing `app/ai/skills/company-research/SKILL.md`
and nothing else, and changing where its output is stored is editing this file
and nothing else.

Registered by name so the agent drives them from data. Adding a step to the
journey is adding a command and naming it in the agent's plan, not editing a
match statement.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any
from uuid import UUID

import sqlalchemy as sa

from app.ai.contracts import Message
from app.ai.runtime.commands import CommandContext, get_commands
from app.ai.runtime.fields import (
    BRAIN_GROUPS,
    FieldKind,
    UndeclaredFieldError,
    askable_fields,
    brain_fields,
    brain_group,
    brain_group_fields,
    fields_for_prompt,
    is_compound,
    persona_fields,
    question_elicits,
    resolve,
)
from app.ai.runtime.hooks import HookEvent, HookPoint
from app.logging import get_logger

log = get_logger(__name__)
commands = get_commands()


_DRAFT_COLUMNS = frozenset(
    {"research", "brief", "persona_draft", "context", "phase", "status", "domain"}
)
"""Every column `_touch` may write, checked before the name reaches SQL."""


def _shared(ctx: CommandContext, own: dict[str, Any]) -> dict[str, Any]:
    """A skill's own grounding, plus whatever this request carries for everyone.

    Own keys win. A command that computed something deliberately must not have
    it overwritten by a request-wide default that happens to share a name.
    """
    return {**dict(ctx.grounding), **own}


def _user(text: str) -> list[Message]:
    return [Message(role="user", content=text)]


async def _touch(ctx: CommandContext, session_id: UUID, **columns: Any) -> None:
    """Update the draft columns on the live session row.

    Drafts, deliberately: nothing written here is authoritative. An onboarding
    abandoned halfway leaves a session row and no half-written Brain, because
    promotion into `company_brain` / `persona` / `fact` only happens in the two
    commands that do it explicitly.
    """
    if not columns:
        return
    unknown = set(columns) - _DRAFT_COLUMNS
    if unknown:
        # The names are ours, not a caller's — but "ours today" is not a
        # guarantee, and this string does reach the database as SQL.
        raise ValueError(f"not draft columns on onboarding_session: {sorted(unknown)}")
    assignments = ", ".join(f"{name} = :{name}" for name in columns)
    params: dict[str, Any] = {
        name: (json.dumps(value) if isinstance(value, (dict, list)) else value)
        for name, value in columns.items()
    }
    params["sid"] = session_id
    # Safe by construction: every name in `assignments` was checked against
    # _DRAFT_COLUMNS above, and every value is bound rather than interpolated.
    sql = f"UPDATE onboarding_session SET {assignments}, updated_at = now() WHERE id = :sid"  # noqa: S608
    await ctx.session.execute(sa.text(sql), params)


# ── research-company ──────────────────────────────────────────


@commands.register(
    "research-company",
    description="Read the company's public pages and record what is actually there.",
    uses_skills=("company-research", "company-summary"),
)
async def research_company(
    ctx: CommandContext,
    *,
    session_id: UUID,
    domain: str,
    pages: list[Mapping[str, str]],
    company_name: str,
) -> Mapping[str, Any]:
    """Crawl output in, a correctable brief out.

    `pages` arrives already fetched. The skill has no browsing and is given only
    the page content — so anything it reports is traceable to something the
    fetcher actually retrieved, rather than to the model's memory of the company.
    """
    research = await ctx.runner.invoke(
        "company-research",
        messages=_user(
            f"Read {company_name} at {domain}. Report only what these pages support."
        ),
        grounding={"domain": domain, "pages": pages},
    )

    brief = await ctx.runner.invoke(
        "company-summary",
        messages=_user("Turn these observations into statements the owner can correct."),
        grounding=_shared(ctx, {
            "research": dict(research.data),
            "company_name": company_name,
            # The keys a statement may name. Grounded for the same reason as
            # persona-builder's: the `field` comes back as a correction key and
            # has to resolve in the catalogue.
            "brain_fields": fields_for_prompt(brain_fields()),
        }),
    )

    # The gate, because grounding is guidance and this needs to be a guarantee.
    #
    # Each statement is rendered with an edit box, and the key it carries is what
    # the correction is filed under. A key outside the catalogue makes that box a
    # trap: the founder types a correction into the one screen that asks them to,
    # and submitting it fails the whole request with an undeclared-field error.
    # Better not to offer the row than to offer an edit that cannot be saved.
    brief_data = dict(brief.data)
    kept: list[Mapping[str, Any]] = []
    for statement in brief_data.get("statements", []):
        key = str(statement.get("field", ""))
        try:
            resolve(key)
        except UndeclaredFieldError as exc:
            log.warning("brief.statement.rejected", field=key, reason=str(exc))
            continue
        kept.append(statement)
    brief_data["statements"] = kept

    await _touch(
        ctx, session_id, research=dict(research.data), brief=brief_data, phase="brief"
    )

    await ctx.hooks.emit(
        HookEvent(
            point=HookPoint.CONTEXT_UPDATED,
            workspace_id=ctx.workspace_id,
            session=ctx.session,
            payload={
                "kind": "research",
                "statements": len(brief_data.get("statements", [])),
                "gaps": len(brief_data.get("needs_you", [])),
            },
        )
    )
    return {"research": research.data, "brief": brief_data}


# ── generate-questions ────────────────────────────────────────


@commands.register(
    "generate-questions",
    description="Choose and word the next question, bound to a declared field.",
    uses_skills=("question-generation",),
)
async def generate_questions(
    ctx: CommandContext,
    *,
    session_id: UUID,
    already_known: Mapping[str, Any],
    conversation: list[Mapping[str, str]],
) -> Mapping[str, Any]:
    """The generated question, and the check that makes it safe to store.

    ADR 0019 blocked generated questions because one has no scope tag. The
    resolution is that the model does not supply the tag: it names a `target`
    from the catalogue it was given, `check_target` refuses anything else, and
    the scope is read off the catalogue entry. So the wording is generated and
    the sensitivity is not.

    Refusal here is a normal outcome, not an error path — a model that names an
    undeclared field is asked again with the failure in front of it.
    """
    # Narrowed to the answerer's department before the model sees it. The
    # department arrives in `user_context`, which `_shared` puts on every
    # skill's grounding — the same row the greeting is built from. Reading it
    # here rather than threading a new argument through `OnboardingAgent` keeps
    # `AgentState` free of a field it has no other use for.
    #
    # This is the fix for the audit's central finding: the model was shown all
    # 23 askable fields regardless of department and bound 26% of questions to
    # another department's. `askable_fields` documents what the narrowing does
    # with an unknown or absent department, and why it is not "nothing".
    department = str(
        (dict(ctx.grounding).get("user_context") or {}).get("department") or ""
    ).strip()
    available = tuple(
        spec
        for spec in askable_fields(department or None)
        if spec.key not in already_known
    )
    if not available:
        return {"done": True, "reason": "every askable field already has an answer"}

    result = await ctx.runner.invoke(
        "question-generation",
        messages=_user("What should we ask next?"),
        grounding=_shared(ctx, {
            "available_fields": fields_for_prompt(available),
            "already_known": dict(already_known),
            "conversation_so_far": conversation,
        }),
    )

    if result.data.get("done"):
        return {"done": True, "reason": result.data.get("reason", "")}

    # `done` false means "here is a question", so there has to be one. The
    # schema's `minLength` catches the empty string and the runner retries on
    # it; this catches the key being absent altogether, which no `required` list
    # can express while `done: true` legitimately omits it. Without both, a
    # blank agent turn reaches the transcript and the founder is shown an empty
    # card with a Send button under it.
    question = str(result.data.get("question", "")).strip()
    if not question:
        reason = "a question was promised (done was false) and none was given"
        log.warning("onboarding.question.empty", reason=reason)
        return {"done": False, "rejected": True, "reason": reason}

    if is_compound(question):
        # The prompt says "One question per turn". A prose rule violated ~43% of
        # the time became a filter — and the first filter counted question
        # marks, so the model stopped writing two sentences and started packing
        # both questions into one. Compound questions went **up**, to ~73%.
        #
        # `is_compound` checks structure instead, and carries the measurements.
        # The cost of a false rejection is now one Haiku call against a raised
        # `MAX_REJECTIONS` with a hand-written fallback beneath it, which is
        # what makes a firm check affordable.
        reason = (
            "that asks more than one thing — ask a single question in under "
            "twenty words, and leave the rest for a later turn"
        )
        log.info("onboarding.question.compound", question=question)
        return {"done": False, "rejected": True, "reason": reason}

    target = str(result.data.get("target", ""))
    offered = {spec.key for spec in available}
    if target not in offered:
        # The gate is the set the runtime put on the table *this turn* — not the
        # skill's `writes`. `question-generation` names a field; it never writes
        # one, so `check_target` (which asserts a write permission) is the wrong
        # question to ask of it and rejects every target including valid ones.
        # `writes` still gates the skills that do persist: persona-builder and
        # company-brain-builder.
        reason = (
            f"{target!r} was not among the fields offered this turn. A question may "
            f"only target a field the runtime put on the table."
        )
        log.warning("onboarding.question.rejected", target=target, reason=reason)
        return {"done": False, "rejected": True, "reason": reason}

    try:
        spec = resolve(target)
    except UndeclaredFieldError as exc:
        log.warning("onboarding.question.undeclared", target=target, reason=str(exc))
        return {"done": False, "rejected": True, "reason": str(exc)}

    if not question_elicits(question, spec):
        # The target is declared and in this turn's set, and the question still
        # cannot produce what the field means. `question_elicits` carries the
        # three audited cases; the shortest is `runway_alarm`, which means "how
        # many months of runway would change your plans" and was asked "what's
        # the gap that causes the most friction right now?" — storing a
        # free-text complaint as a runway threshold, which the *next* question
        # then quoted back as a number the person had never given.
        #
        # Rejected into the same retry as an undeclared target, because it is
        # the same kind of failure: a question that would store the wrong
        # meaning with full provenance, which is worse than no question.
        reason = (
            f"that question cannot elicit {spec.key!r}, which wants "
            f"{spec.answer_shape.value} — ask directly for that"
        )
        log.info(
            "onboarding.question.shape_mismatch",
            target=spec.key,
            shape=spec.answer_shape.value,
            question=question,
        )
        return {"done": False, "rejected": True, "reason": reason}

    return {
        "done": False,
        "question": question,
        "target": spec.key,
        "scope": spec.scope,
        "choices": result.data.get("choices", []),
        "rationale": result.data.get("rationale", ""),
        "skill": result.skill,
        "skill_version": result.version,
    }


# ── build-persona ─────────────────────────────────────────────


@commands.register(
    "build-persona",
    description="Assemble the persona from answers, citing the sentence behind each field.",
    uses_skills=("persona-builder",),
)
async def build_persona(
    ctx: CommandContext,
    *,
    session_id: UUID,
    answers: Mapping[str, str],
    company_profile: str,
) -> Mapping[str, Any]:
    """Persona is presentation preference. Enforced here, not just prompted.

    The skill is told not to write role or reach. This filter is what makes that
    true regardless of what it returns: every field is resolved against the
    catalogue, and anything that is not `kind=PERSONA` is dropped with a warning
    rather than stored. `fields.assert_persona_is_not_authorisation` already
    guarantees no persona field carries a widening scope, so a value that passes
    both cannot change what anyone is allowed to see.
    """
    result = await ctx.runner.invoke(
        "persona-builder",
        messages=_user("Assemble the persona from these answers."),
        grounding=_shared(ctx, {
            "answers": dict(answers),
            "company_profile": company_profile,
            # The exact keys, for the same reason question-generation gets its
            # own list: the filter below refuses anything not in the catalogue,
            # so a skill left to guess the key names produces an empty persona
            # and a log full of correct refusals.
            "persona_fields": fields_for_prompt(persona_fields()),
        }),
    )

    accepted: list[dict[str, Any]] = []
    for entry in result.data.get("fields", []):
        key = str(entry.get("key", ""))
        try:
            spec = ctx.runner.check_target("persona-builder", key)
        except UndeclaredFieldError as exc:
            log.warning("persona.field.rejected", key=key, reason=str(exc))
            continue
        if spec.kind is not FieldKind.PERSONA:
            log.warning("persona.field.wrong_kind", key=key, kind=str(spec.kind))
            continue
        accepted.append(
            {
                "key": spec.key,
                "column": spec.column,
                "label": spec.label,
                "value": entry.get("value", ""),
                "derived_from": entry.get("derived_from", ""),
                "scope": spec.scope,
            }
        )

    await _touch(
        ctx,
        session_id,
        persona_draft={"fields": accepted, "summary": result.data.get("summary", "")},
        phase="persona",
    )
    await ctx.hooks.emit(
        HookEvent(
            point=HookPoint.CONTEXT_UPDATED,
            workspace_id=ctx.workspace_id,
            session=ctx.session,
            payload={"kind": "persona", "fields": [f["key"] for f in accepted]},
        )
    )
    return {"fields": accepted, "summary": result.data.get("summary", "")}


# ── build-company-brain ───────────────────────────────────────


@commands.register(
    "build-company-brain",
    description="Assemble the Company Brain from research, documents and confirmed answers.",
    uses_skills=("company-brain-builder",),
)
async def build_company_brain(
    ctx: CommandContext,
    *,
    session_id: UUID,
    research: Mapping[str, Any],
    answers: Mapping[str, str],
    company_name: str,
    domain: str,
    group: str,
    so_far: Mapping[str, Any] | None = None,
    deep_research: Mapping[str, Any] | None = None,
) -> Mapping[str, Any]:
    """One **group** of the Brain. Every stored value keeps its provenance.

    `group` names a slice of `BRAIN_GROUPS`, and this writes only that slice —
    see the note there for why the single seven-field call had to be broken up
    (it took 242 seconds and was killed by the proxy, twice, so onboarding could
    never finish).

    `so_far` is what earlier groups already committed. It is merged, not
    replaced: each call returns the whole Brain as it now stands, so the row is
    always a complete artefact and a run that dies between groups leaves a
    smaller Brain rather than a torn one. Later groups win on a key collision,
    which only arises if a model names a field outside its group — the catalogue
    gate below drops those first, so in practice the merge is disjoint.

    The phase advances **only on the last group**. That is what makes the route's
    "pick the next unfinished group" loop terminate, and what lets a retry resume
    at the group that failed instead of paying for the ones that succeeded.

    `deep_research` is the background run's pages, if it has finished. It is
    optional on purpose: the interview and the crawl race each other, and a
    founder who answers quickly must not be made to wait for a twenty-page
    fetch. Absent, the Brain is built from the three pages onboarding read and
    says what it does not yet know; present, it is built from all of them.
    Either way nothing is estimated to fill the gap.

    Migration 0019 makes `provenance` NOT NULL, and this drops any value that
    arrives without one rather than inventing a placeholder to satisfy the
    column. A brain that cannot say where a claim came from is the thing the
    product exists not to be — satisfying the constraint with 'unknown' would
    keep the schema happy and defeat its purpose.
    """
    spec_group = brain_group(group)
    if spec_group is None:
        raise ValueError(f"{group!r} is not a Brain group; see BRAIN_GROUPS")
    specs = brain_group_fields(group)
    result = await ctx.runner.invoke(
        "company-brain-builder",
        messages=_user(
            f"Assemble the {group} part of the Company Brain for {company_name}."
        ),
        grounding=_shared(ctx, {
            "research": dict(research),
            "answers": dict(answers),
            "company_name": company_name,
            "domain": domain,
            "brain_fields": fields_for_prompt(specs),
            "deep_research": dict(deep_research) if deep_research else {},
        }),
        # Per group, not per skill. `BrainGroup.effort` carries the measurement
        # that made this necessary.
        effort=spec_group.effort,
    )

    # The gate for this call is the group, not the whole catalogue. Without it a
    # model handed the market fields cheerfully rewrites `brain.profile` too, and
    # the merge below would let a later group silently overwrite an earlier one's
    # sourced value with a fresh guess.
    offered = {spec.key for spec in specs}

    accepted: list[dict[str, Any]] = []
    for entry in result.data.get("values", []):
        key = str(entry.get("key", ""))
        provenance = str(entry.get("provenance", "")).strip()
        if not provenance:
            log.warning("brain.value.unsourced", key=key)
            continue
        try:
            spec = ctx.runner.check_target("company-brain-builder", key)
        except UndeclaredFieldError as exc:
            log.warning("brain.value.rejected", key=key, reason=str(exc))
            continue
        if spec.key not in offered:
            log.warning("brain.value.out_of_group", key=key, group=group)
            continue
        accepted.append(
            {
                "key": spec.key,
                "column": spec.column,
                "value": entry.get("value", ""),
                "source_kind": entry.get("source_kind", "inference"),
                "provenance": provenance,
                "superseded": entry.get("superseded"),
                "scope": spec.scope,
            }
        )

    prior = dict(so_far or {})
    done = [*prior.get("groups_done", []), group]
    remaining = [g.name for g in BRAIN_GROUPS if g.name not in done]

    by_key = {value["key"]: value for value in prior.get("values", [])}
    by_key.update({value["key"]: value for value in accepted})

    payload = {
        "values": list(by_key.values()),
        "assumptions": [*prior.get("assumptions", []), *result.data.get("assumptions", [])],
        "unavailable": [*prior.get("unavailable", []), *result.data.get("unavailable", [])],
        "generated_by": result.data.get("generated_by", "model"),
        # The resume marker, and the route's only input for choosing what runs
        # next. On the session row rather than in a new column: it is true for
        # exactly the life of one journey, and a migration to hold four bytes
        # that `context` is already carrying is a migration to maintain forever.
        "groups_done": done,
    }
    await _touch(
        ctx,
        session_id,
        brief=None,
        context=payload,
        phase="assembling" if not remaining else "persona",
    )
    await ctx.hooks.emit(
        HookEvent(
            point=HookPoint.CONTEXT_UPDATED,
            workspace_id=ctx.workspace_id,
            session=ctx.session,
            payload={"kind": "brain", "group": group, "values": len(accepted),
                     "remaining_groups": len(remaining),
                     "unavailable": len(payload["unavailable"])},
        )
    )
    return payload


# ── personalize-context ───────────────────────────────────────


@commands.register(
    "personalize-context",
    description="Join Brain and Persona into the preamble later agents receive.",
    uses_skills=("context-personalization",),
)
async def personalize_context(
    ctx: CommandContext,
    *,
    session_id: UUID,
    brain: Mapping[str, Any],
    persona: Mapping[str, Any],
    role_reach: Mapping[str, Any],
) -> Mapping[str, Any]:
    """The artefact the whole journey exists to produce.

    `role_reach` is passed in so the skill can be told what it must *not* assert.
    The preamble may say what a person prefers to see; it may never say what they
    are permitted to see, because the retrieval layer does not read this file and
    a preamble that claimed reach would be an authorisation statement nothing
    enforces.
    """
    result = await ctx.runner.invoke(
        "context-personalization",
        messages=_user("Write the grounded preamble for this workspace and person."),
        grounding={"brain": dict(brain), "persona": dict(persona), "role_reach": dict(role_reach)},
    )
    await _touch(ctx, session_id, context=dict(result.data), phase="ready")
    return result.data


# ── interpret-user ────────────────────────────────────────────


@commands.register(
    "interpret-user",
    description="Interpret a free-text answer about someone's work into scoped interests.",
    uses_skills=("user-discovery",),
)
async def interpret_user(
    ctx: CommandContext,
    *,
    session_id: UUID,
    answer: str,
    company_profile: str,
) -> Mapping[str, Any]:
    """The opening turn of the interview, where the person answers in prose.

    This is the one place a person writes freely rather than answering a targeted
    question, so it is also the one place where an interpretation step is needed
    before anything can be stored. The skill returns interests with the literal
    span that produced each; anything it could not ground in a quote is dropped
    here rather than stored as an unattributed claim about a person.

    `declined_to_infer_role` is surfaced rather than swallowed: when someone
    asserts seniority and the skill correctly records only the interest, that is
    worth seeing in the logs — it is the persona/authorisation boundary holding
    under the exact pressure that tests it.
    """
    result = await ctx.runner.invoke(
        "user-discovery",
        messages=_user(answer),
        grounding={"company_profile": company_profile},
    )

    grounded: list[dict[str, str]] = []
    for topic in result.data.get("priority_topics", []):
        evidence = str(topic.get("evidence", "")).strip()
        if not evidence or evidence.lower() not in answer.lower():
            # `evidence` must be a literal span from what they wrote. A
            # paraphrase shown back as "you said this" is a fabrication, and the
            # panel does show these back.
            log.warning("discovery.evidence.not_literal", topic=topic.get("topic"))
            continue
        grounded.append({"topic": str(topic.get("topic", "")), "evidence": evidence})

    if result.data.get("declined_to_infer_role"):
        log.info("discovery.role_not_inferred", workspace_id=ctx.workspace_id)

    await ctx.hooks.emit(
        HookEvent(
            point=HookPoint.ANSWER_SUBMITTED,
            workspace_id=ctx.workspace_id,
            session=ctx.session,
            payload={
                "target": "persona.stated_purpose",
                "scope": 5,
                "origin": "discovery-opening",
                "actor_user_id": ctx.actor_user_id,
            },
        )
    )
    return {
        "stated_purpose": result.data.get("stated_purpose", {}),
        "priority_topics": grounded,
        "needs_followup": result.data.get("needs_followup", ""),
        "declined_to_infer_role": bool(result.data.get("declined_to_infer_role")),
    }
