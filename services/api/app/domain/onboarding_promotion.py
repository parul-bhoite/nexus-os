"""Promoting a finished onboarding into the tables other agents read.

**Everything the interview collected used to stop here.** The agent path wrote
`onboarding_turn` and `onboarding_session` and nothing else: `INSERT INTO fact`
existed nowhere in the repository, `company_brain` was fed only by
`company_brain.build`, which reads `onboarding_answer` — a table whose sole
writer is the retired setup wizard — and `persona` only by the spine's own chat
route, which has no caller on this path either.

So two audits' worth of work on *which* questions get asked was landing in a
draft column that stage three of the assembly then overwrote with the
personalisation preamble. `_touch`'s docstring said promotion "only happens in
the two commands that do it explicitly". Those two commands did not exist. This
module is them.

Three rules it exists to keep:

**Nothing is promoted without provenance.** `ck_company_brain_grounded_has_provenance`
refuses a brain that cannot point at something, and every fact row carries a
`source_ref` precise enough to open. A value whose source was dropped along the
way is not written — it is logged and skipped, because a fact nobody can check
is the thing this product exists not to produce.

**A person's answer outranks everything.** Interview answers land at
`SourceKind.USER_CONFIRMED`, which `facts.PRECEDENCE` puts above a connected
system, a crawl, an inference and a document. That is not this module's opinion;
it reads the rank rather than writing a number.

**It runs inside the caller's transaction.** The last stage of `/finish` already
commits the session as completed; promoting in the same transaction means a
workspace is never left marked finished with nothing behind it, and never left
with a promoted Brain and an unfinished session.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import company_brain
from app.domain.facts import SourceKind, rank
from app.logging import get_logger

log = get_logger(__name__)

# `Brain`'s prose columns, and the array ones. Split because the table types
# differ — `competitors` and `assumptions` are `text[]` — and a string written
# into an array column is a driver error at the far end of a slow request.
_PROSE_COLUMNS = ("profile", "products_services", "target_customers", "brand_voice", "goals")
_ARRAY_COLUMNS = ("competitors", "assumptions")

# `persona`'s own columns, from migration 0002. Every persona field in the
# catalogue declares one of these in `FieldSpec.column`, which is what makes
# this a lookup rather than a mapping table to keep in step.
_PERSONA_TEXT = ("stated_purpose", "communication_style", "language", "timezone",
                 "default_landing_screen")
_PERSONA_ARRAY = ("priority_topics",)


@dataclass(frozen=True, slots=True)
class Promoted:
    """What reached the authoritative tables. Counts, for the completion hook."""

    brain_version: int
    brain_values: int
    facts: int
    persona_fields: int


def _split(value: object) -> list[str]:
    """A list column's value, without inventing a list that is not there.

    `competitors`, `assumptions` and `priority_topics` are `text[]`, and the
    skills that fill them return one string. Splitting that string on commas
    looks obviously right and is wrong as often as not — a live run stored
    `priority_topics` as::

        ['Inland haulage', 'port handling', 'and keeping shipments on schedule.']

    from the sentence "inland haulage, port handling and keeping shipments on
    schedule". The third element is not a topic; it is the tail of a sentence.
    Deriving structure that the source does not have is the same failure this
    product exists to avoid, one layer down.

    So: a semicolon is an explicit list and always splits. A comma splits only
    when what surrounds it looks like a list rather than prose — no conjunction,
    no dash, and short. Anything else is stored whole, which leaves a
    single-element array holding exactly what the person or the model said. A
    badly *shaped* value is recoverable; a fabricated one is not.
    """
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]

    text = str(value or "").strip()
    if not text:
        return []

    parts = [part.strip() for part in text.split(";") if part.strip()]
    if len(parts) > 1:
        return parts

    prose = any(marker in text.lower() for marker in (" and ", " or ", " — ", " that ", " which "))
    if "," in text and not prose and len(text.split()) <= 12:
        return [part.strip() for part in text.split(",") if part.strip()]
    return [text]


def _brain_from(payload: Mapping[str, Any]) -> tuple[company_brain.Brain, int]:
    """The `Brain` to store, and how many values went into it.

    Reads the *assembled* payload from `build-company-brain` — the one on
    `session.context` before stage three replaces it — rather than re-deriving
    anything. Each value already carries the catalogue column it belongs to and
    the provenance the builder refused to accept it without.
    """
    brain = company_brain.Brain()
    provenance: list[str] = []
    used = 0

    for value in payload.get("values", []):
        if not isinstance(value, dict):
            continue
        column = str(value.get("column") or "")
        source = str(value.get("provenance") or "").strip()
        if not column or not source:
            # The builder already drops unsourced values; this is the second
            # gate, because the constraint below is not negotiable and a
            # `CheckViolation` at the end of a two-minute assembly is a poor
            # way to learn that something upstream changed.
            log.warning("promotion.value.unsourced", key=value.get("key"))
            continue

        if column in _PROSE_COLUMNS:
            setattr(brain, column, str(value.get("value") or "").strip() or None)
        elif column in _ARRAY_COLUMNS:
            setattr(brain, column, _split(value.get("value")))
        else:
            log.warning("promotion.value.unknown_column", key=value.get("key"), column=column)
            continue

        provenance.append(f"{value.get('key')}: {source}")
        used += 1

    brain.provenance = provenance
    brain.generated_by = str(payload.get("generated_by") or company_brain.GeneratedBy.MODEL.value)
    brain.assumptions = [
        *brain.assumptions,
        *[
            str(item.get("text") or item).strip()
            for item in payload.get("assumptions", [])
            if str(item.get("text") if isinstance(item, dict) else item).strip()
        ],
    ]

    if not provenance:
        # `ck_company_brain_grounded_has_provenance` permits an empty
        # `provenance` only for an unavailable brain, and that is the honest
        # description of this state: the assembly produced nothing citable.
        brain.generated_by = company_brain.GeneratedBy.UNAVAILABLE.value
        brain.unavailable_reason = (
            "The assembly produced no value that could name where it came from."
        )
    return brain, used


async def _record_facts(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    user_id: UUID,
    session_id: UUID,
    brain_version_id: UUID,
    answers: Mapping[str, str],
) -> int:
    """One `fact` row per interview answer that targets a `fact.*` key.

    `source_ref` names the session rather than the sentence. It is precise
    enough to open — the transcript is stored — and it is the same reference the
    review gate will need when a document later contradicts one of these.

    `confirmed_by_user_id` and `confirmed_at` are written together or not at
    all; `ck_fact_confirmation_is_whole` refuses half a record of a human
    decision, on the grounds that it looks like an audit trail and cannot answer
    the question one is kept for. These *are* confirmed: the person typed them.
    """
    from app.ai.runtime.fields import FIELD_CATALOGUE

    written = 0
    for key, value in answers.items():
        if not key.startswith("fact."):
            continue
        spec = FIELD_CATALOGUE.get(key)
        text = str(value or "").strip()
        if spec is None or not text:
            continue
        await db.execute(
            sa.text(
                "INSERT INTO fact (workspace_id, brain_version_id, key, value, source_ref,"
                "                  source_kind, confidence, precedence,"
                "                  confirmed_by_user_id, confirmed_at)"
                " VALUES (:w, :bv, :key, :value, :ref, :kind, :confidence, :precedence,"
                "         :user, now())"
            ),
            {
                "w": str(workspace_id),
                "bv": str(brain_version_id),
                "key": key,
                "value": text,
                "ref": f"onboarding_session:{session_id}",
                "kind": SourceKind.USER_CONFIRMED.value,
                # A person stating a rule about their own business is as certain
                # as this system gets. Anything less would be inventing doubt.
                "confidence": 1.0,
                "precedence": rank(SourceKind.USER_CONFIRMED),
                "user": str(user_id),
            },
        )
        written += 1
    return written


async def _upsert_persona(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    user_id: UUID,
    fields: Sequence[Mapping[str, Any]],
) -> int:
    """Write the persona the assembly built, without blanking what it did not.

    An upsert on `(workspace_id, user_id)`, because a persona is per person and
    onboarding can be re-run.

    **One static statement naming every column**, rather than composing the
    column list from the values that happen to be present. Composed SQL here
    would be safe — the names come from a closed allowlist — but "safe because
    of a filter three lines up" is a property a reader has to reconstruct, and
    `ruff` flags it either way. Absent values arrive as NULL and are coalesced.

    `COALESCE(:param, persona.column)` in the update, **not**
    `COALESCE(EXCLUDED.column, …)`. `language`, `timezone` and `priority_topics`
    are `NOT NULL` with defaults, so the insert has to supply those defaults —
    which means `EXCLUDED` never holds NULL for them, and a re-run that learned
    no language would quietly reset an existing one to `en`. Reading the
    parameter instead keeps "not learned this time" distinct from "learned to be
    the default".

    Presentation preference only. `assert_persona_is_not_authorisation`
    guarantees no persona field can widen a scope, and nothing here reads
    `membership`.
    """
    values: dict[str, Any] = dict.fromkeys((*_PERSONA_TEXT, *_PERSONA_ARRAY))
    for field in fields:
        column = str(field.get("column") or "")
        text = str(field.get("value") or "").strip()
        if not text or column not in values:
            continue
        values[column] = _split(text) or None if column in _PERSONA_ARRAY else text

    written = sum(1 for value in values.values() if value is not None)
    if not written:
        return 0

    await db.execute(
        sa.text(
            "INSERT INTO persona (workspace_id, user_id, stated_purpose, priority_topics,"
            "                     communication_style, language, timezone,"
            "                     default_landing_screen)"
            " VALUES (:w, :u, :stated_purpose,"
            "         COALESCE(CAST(:priority_topics AS text[]), '{}'),"
            "         :communication_style, COALESCE(:language, 'en'),"
            "         COALESCE(:timezone, 'Asia/Muscat'), :default_landing_screen)"
            " ON CONFLICT (workspace_id, user_id) DO UPDATE SET"
            "   stated_purpose = COALESCE(:stated_purpose, persona.stated_purpose),"
            "   priority_topics = COALESCE(CAST(:priority_topics AS text[]),"
            "                              persona.priority_topics),"
            "   communication_style = COALESCE(:communication_style,"
            "                                  persona.communication_style),"
            "   language = COALESCE(:language, persona.language),"
            "   timezone = COALESCE(:timezone, persona.timezone),"
            "   default_landing_screen = COALESCE(:default_landing_screen,"
            "                                     persona.default_landing_screen),"
            "   updated_at = now()"
        ),
        {"w": str(workspace_id), "u": str(user_id), **values},
    )
    return written


async def promote(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    user_id: UUID,
    session_id: UUID,
    brain: Mapping[str, Any],
    persona_draft: Mapping[str, Any],
    answers: Mapping[str, str],
) -> Promoted:
    """Write a finished onboarding into `company_brain`, `brain_version`,
    `fact` and `persona`.

    Called from the last stage of `/finish`, **before** `store.complete`
    replaces `session.context` with the preamble — which is the only moment the
    assembled Brain still exists. Same transaction as that completion, so the
    two cannot disagree about whether this workspace is set up.

    `brain_version` is inserted at the same version number `company_brain` just
    took, so the fact layer and the prose Brain point at the same generation of
    the same company. `fact.brain_version_id` is `NOT NULL`, which is what
    forces that to be true rather than conventional.
    """
    built, values = _brain_from(brain)
    version = await company_brain.store(db, workspace_id=workspace_id, brain=built)

    brain_version_id = (
        await db.execute(
            sa.text(
                "INSERT INTO brain_version (workspace_id, version, created_by_user_id)"
                " VALUES (:w, :v, :u) RETURNING id"
            ),
            {"w": str(workspace_id), "v": version, "u": str(user_id)},
        )
    ).scalar_one()

    facts = await _record_facts(
        db,
        workspace_id=workspace_id,
        user_id=user_id,
        session_id=session_id,
        brain_version_id=brain_version_id,
        answers=answers,
    )
    persona_fields = await _upsert_persona(
        db,
        workspace_id=workspace_id,
        user_id=user_id,
        fields=list(persona_draft.get("fields", [])),
    )

    log.info(
        "onboarding.promoted",
        workspace_id=str(workspace_id),
        brain_version=version,
        brain_values=values,
        facts=facts,
        persona_fields=persona_fields,
    )
    return Promoted(
        brain_version=version,
        brain_values=values,
        facts=facts,
        persona_fields=persona_fields,
    )
