"""Every value-list `CHECK` in the database, against the Python that feeds it.

This is the test for the *class* of defect Phase 1 exists to clear, rather than
for its two instances. `ReviewState` and `ck_chunk_review_state` were two
independent lists of strings that had drifted apart, and nothing could tell:
the enum type-checked, the constraint was valid SQL, and the only place they met
was an `INSERT` at runtime that no test had ever executed. `ck_document_status`
was worse — it had no Python counterpart at all, so `'superseded'` was written
as a bare literal in one place and permitted in none.

Two halves, and the second is what makes this durable:

- every registered constraint's allowed values must equal its enum's, and
- **every value-list constraint must be registered.** A new one added without a
  mapping fails the build, so the next constraint of this shape cannot arrive
  unwatched. Where no enum exists yet, the reason is written down in `UNMAPPED`
  and names the phase that owns it — and a stale entry there fails too, so a
  constraint that goes away takes its excuse with it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import pytest
import sqlalchemy as sa
from sqlalchemy import Engine, create_engine

from app.connectors.domain_check import Method, Strength
from app.documents.classify import ReviewState
from app.documents.status import DocumentStatus
from app.domain.access import Sensitivity
from app.domain.company_brain import GeneratedBy
from app.domain.connections import PROVIDER_IDS
from app.domain.connectors import ConnectionState
from app.domain.department_answers import AnswerState
from app.domain.facts import SourceKind as FactSourceKind
from app.domain.onboarding_sessions import Phase, SessionStatus, TurnRole
from app.domain.page_signals import CaptureSource
from app.domain.registration import JoinRequestState, ResearchRunState
from app.domain.reporting import Scale, WeekStart
from app.domain.research import SourceKind, SourceState
from app.domain.scopes import Role, Scope, scope_code
from app.grounding.pipeline import Outcome
from tests.dburl import database_url

DB_URL = database_url()

# The real marker, declared in pyproject.toml. See the note in conftest.py.
requires_db = pytest.mark.requires_db

pytestmark = requires_db


@dataclass(frozen=True, slots=True)
class Mapping:
    """A `CHECK` constraint and the Python that decides what may be written."""

    constraint: str
    source: str
    values: frozenset[str]


MAPPINGS: tuple[Mapping, ...] = (
    Mapping(
        "ck_generation_outcome",
        "app.grounding.pipeline.Outcome",
        frozenset(outcome.value for outcome in Outcome),
    ),
    Mapping(
        "ck_fact_source_kind",
        "app.domain.facts.SourceKind",
        frozenset(kind.value for kind in FactSourceKind),
    ),
    Mapping(
        "ck_research_source_kind",
        "app.domain.research.SourceKind",
        frozenset(kind.value for kind in SourceKind),
    ),
    Mapping(
        "ck_research_source_state",
        "app.domain.research.SourceState",
        frozenset(state.value for state in SourceState),
    ),
    Mapping(
        "ck_company_brain_generated_by",
        "app.domain.company_brain.GeneratedBy",
        frozenset(how.value for how in GeneratedBy),
    ),
    Mapping(
        "ck_onboarding_answer_state",
        "app.domain.department_answers.AnswerState",
        frozenset(state.value for state in AnswerState),
    ),
    Mapping(
        "ck_research_run_state",
        "app.domain.registration.ResearchRunState",
        frozenset(state.value for state in ResearchRunState),
    ),
    Mapping(
        "ck_join_request_state",
        "app.domain.registration.JoinRequestState",
        frozenset(state.value for state in JoinRequestState),
    ),
    Mapping(
        "ck_chunk_review_state",
        "app.documents.classify.ReviewState",
        frozenset(state.value for state in ReviewState),
    ),
    Mapping(
        "ck_document_status",
        "app.documents.status.DocumentStatus",
        frozenset(status.value for status in DocumentStatus),
    ),
    Mapping(
        "ck_chunk_sensitivity",
        "app.domain.access.Sensitivity",
        frozenset(level.value for level in Sensitivity),
    ),
    # Scope stores a code, not the member name — `scope_code` is the translation
    # and it is on the write path, so it is what this compares.
    Mapping(
        "ck_chunk_scope",
        "app.domain.scopes.Scope via scope_code",
        frozenset(scope_code(scope) for scope in Scope),
    ),
    Mapping(
        "ck_onboarding_answer_scope",
        "app.domain.scopes.Scope via scope_code",
        frozenset(scope_code(scope) for scope in Scope),
    ),
    Mapping(
        "ck_membership_role",
        "app.domain.scopes.Role",
        frozenset(role.value for role in Role),
    ),
    Mapping(
        "ck_invitation_role",
        "app.domain.scopes.Role",
        frozenset(role.value for role in Role),
    ),
    Mapping(
        "ck_domain_claim_method",
        "app.connectors.domain_check.Method",
        frozenset(method.value for method in Method),
    ),
    Mapping(
        "ck_domain_claim_strength",
        "app.connectors.domain_check.Strength",
        frozenset(strength.value for strength in Strength),
    ),
    Mapping(
        "ck_onboarding_session_phase",
        "app.domain.onboarding_sessions.Phase",
        frozenset(phase.value for phase in Phase),
    ),
    Mapping(
        "ck_onboarding_session_status",
        "app.domain.onboarding_sessions.SessionStatus",
        frozenset(status.value for status in SessionStatus),
    ),
    Mapping(
        "ck_onboarding_turn_role",
        "app.domain.onboarding_sessions.TurnRole",
        frozenset(role.value for role in TurnRole),
    ),
    # The tools step. Both of these were written in the same commit as the
    # constraint, which is the habit `CONTINUE-HERE` records as having cost a CI
    # round trip three times — a value-list CHECK with no Mapping fails
    # `test_every_value_list_constraint_is_registered` rather than the test it
    # was added for.
    Mapping(
        "ck_workspace_connection_state",
        "app.domain.connectors.ConnectionState",
        frozenset(state.value for state in ConnectionState),
    ),
    # The one mapping here whose Python side is not an enum. The catalogue is a
    # tuple of `Tool` dataclasses because each entry carries a name, a
    # department and the sentence saying what it unlocks — none of which fits in
    # an enum member — so the compared set is the ids it exposes. The constraint
    # is doing the same job either way: refusing a provider nothing downstream
    # can read.
    # The reporting settings (`doc/13` §13, ADR 0025). Registered in the same
    # commit as migration 0027, because a value-list CHECK with no mapping fails
    # `test_every_value_list_constraint_is_registered` rather than the test it
    # was added for — three CI round trips, per `CONTINUE-HERE`.
    Mapping(
        "ck_workspace_reporting_week_start",
        "app.domain.reporting.WeekStart",
        frozenset(day.value for day in WeekStart),
    ),
    Mapping(
        "ck_workspace_reporting_scale",
        "app.domain.reporting.Scale",
        frozenset(scale.value for scale in Scale),
    ),
    Mapping(
        "ck_workspace_connection_provider",
        "app.domain.connections.PROVIDERS via PROVIDER_IDS",
        PROVIDER_IDS,
    ),
    # Crawled page signals (`doc/13` slice 1). Registered in the same commit as
    # migration 0028, for the reason two comments above already give.
    Mapping(
        "ck_page_signals_captured_by",
        "app.domain.page_signals.CaptureSource",
        frozenset(source.value for source in CaptureSource),
    ),
)

UNMAPPED: dict[str, str] = {
    # Six states written as bare literals across seven statements in
    # app/auth/domains.py. The same defect shape as ck_document_status, and the
    # fix is the same — an enum on the write path. Phase 3 owns domain
    # verification and should do it there rather than have Phase 1 rewrite SQL
    # it is not otherwise touching.
    "ck_domain_claim_state": "no enum yet; app/auth/domains.py writes literals. Phase 3.",
}

_VALUE_LIST = re.compile(r"'([^']+)'::text")


@dataclass(frozen=True, slots=True)
class Discovered:
    table: str
    constraint: str
    values: frozenset[str]


def _discover(engine: Engine) -> dict[str, Discovered]:
    """Every `CHECK` in `public` that constrains a column to a list of strings.

    `= ANY (ARRAY[...])` and `<@ ARRAY[...]` are the two shapes the migrations
    use. Constraints that merely *mention* a literal — `ck_chunk_l5_has_owner`
    naming `'L5'`, `ck_document_consent_before_indexing` naming `'indexed'` —
    are deliberately not value lists and are excluded, because there is no set
    of permitted values for an enum to be compared against.
    """
    with engine.connect() as conn:
        rows = conn.execute(
            sa.text(
                "SELECT conrelid::regclass::text AS table_name, conname,"
                "       pg_get_constraintdef(oid) AS definition"
                "  FROM pg_constraint"
                " WHERE contype = 'c' AND connamespace = 'public'::regnamespace"
            )
        ).mappings()

        found: dict[str, Discovered] = {}
        for row in rows:
            definition = row["definition"]
            if "= ANY" not in definition and "<@" not in definition:
                continue
            found[row["conname"]] = Discovered(
                table=row["table_name"],
                constraint=row["conname"],
                values=frozenset(_VALUE_LIST.findall(definition)),
            )
        return found


@pytest.fixture(scope="module")
def engine() -> object:
    # `requires_db` guarantees a database, so a missing URL here is a broken
    # harness rather than an absent one. Assert loudly instead of skipping.
    assert DB_URL is not None
    eng = create_engine(DB_URL, poolclass=sa.pool.NullPool)
    yield eng
    eng.dispose()


@pytest.fixture(scope="module")
def discovered(engine: Engine) -> dict[str, Discovered]:
    return _discover(engine)


# ── The two lists must agree ──────────────────────────────────


@pytest.mark.parametrize("mapping", MAPPINGS, ids=lambda m: m.constraint)
def test_the_constraint_permits_exactly_what_the_enum_can_produce(
    mapping: Mapping, discovered: dict[str, Discovered]
) -> None:
    """Set equality, not containment, and in both directions.

    A constraint wider than the enum is a column that accepts values no code
    path can produce — dead vocabulary that a later reader will treat as
    supported. Narrower is the live bug: an enum member that cannot be written,
    which is exactly what `needs_review` was.
    """
    assert mapping.constraint in discovered, (
        f"{mapping.constraint} is registered here but does not exist in the "
        "database. Either the migration was never applied, or the constraint "
        "was renamed and this mapping is now pointing at nothing."
    )

    permitted = discovered[mapping.constraint].values
    assert permitted == mapping.values, (
        f"{mapping.constraint} permits {sorted(permitted)} but "
        f"{mapping.source} can produce {sorted(mapping.values)}. "
        f"Only in the database: {sorted(permitted - mapping.values)}. "
        f"Only in Python: {sorted(mapping.values - permitted)}."
    )


# ── Nothing of this shape may go unwatched ────────────────────


def test_every_value_list_constraint_is_registered(discovered: dict[str, Discovered]) -> None:
    """A new value-list `CHECK` with no mapping fails the build.

    Without this the test only guards the constraints somebody remembered to
    add, which is the same reliance on memory that produced the drift.
    """
    registered = {mapping.constraint for mapping in MAPPINGS} | set(UNMAPPED)
    unregistered = {
        name: sorted(found.values) for name, found in discovered.items() if name not in registered
    }

    assert not unregistered, (
        "These value-list CHECK constraints have no Python counterpart declared "
        f"in this test: {unregistered}. Add a Mapping if an enum feeds it, or an "
        "UNMAPPED entry saying why not and which phase owns it."
    )


def test_no_unmapped_entry_outlives_its_constraint(discovered: dict[str, Discovered]) -> None:
    """A dropped constraint takes its excuse with it.

    This has already earned itself once. `ck_preview_session_status` was
    exempted here with "table is dropped in Phase 2", and when migration 0011
    dropped it this test failed until the entry was removed — which is the
    point. An exemption list nobody prunes becomes a list of things nobody
    checks.
    """
    stale = sorted(name for name in UNMAPPED if name not in discovered)
    assert not stale, (
        f"UNMAPPED still excuses {stale}, which no longer exists in the "
        "database. Delete the entries."
    )
