"""P14's acceptance test: every number traces to a row naming its inputs.

`doc/12` P14: *"Every number rendered anywhere traces to a `generation` row
naming its inputs and its calculation."* The pipeline, the guard and eleven
evals existed before this file; what did not exist was **a single row in the
table**. `generation` had two indexes, three check constraints and nothing
written to it, and the budget those indexes were built for was never counted.

Against Neon, because the claims are about a table: row-level security on the
insert, a `date_trunc` in the caller's own timezone, and a constraint that
refuses an unavailable row with no reason. None of that can be proved against a
monkeypatched write, and the phase rule says so — *"driven through the
application rather than around it."*
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import _unscoped_session, get_engine, get_sessionmaker
from app.domain.reporting import ReportingSettings
from app.domain.scopes import Department, Role
from app.domain.session import ScopedSession
from app.grounding import ledger
from app.grounding.answer import unavailable_for
from app.grounding.context import CompanyContext, assemble
from app.grounding.pipeline import Answer, Budgets, Outcome, UnavailableReason
from app.retrieval.scoped import apply_workspace_scope
from tests.dburl import async_database_url

pytestmark = pytest.mark.requires_db

ASYNC_DB_URL = async_database_url()

CAPABILITY = "finance.runway_alert"
"""A real capability id, because `narrate` resolves it through the registry and
a made-up one would prove only that `KeyError` works."""


@dataclass(frozen=True, slots=True)
class Seed:
    tenant_id: UUID
    user_id: UUID
    workspace_id: UUID


@pytest.fixture
async def app_db(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[None]:
    """Point the application's own cached engine at the test database.

    The same fixture `evals/test_permissions.py` uses, and for the same reason:
    `conftest.py` pins `NEXUS_DATABASE_URL` to empty for hermeticity, so the
    engine has to be pointed deliberately rather than by ambient configuration.
    Using the app's engine rather than one built here is what makes this test
    exercise the application's write path instead of a parallel one.
    """
    assert ASYNC_DB_URL is not None, (
        "`requires_db` guarantees a database; a missing URL is a broken harness"
    )
    monkeypatch.setenv("NEXUS_DATABASE_URL", ASYNC_DB_URL)
    monkeypatch.setenv("NEXUS_STORAGE_SIGNING_SECRET", "test-secret")
    for cache in (get_settings, get_engine, get_sessionmaker):
        cache.cache_clear()
    yield
    await get_engine().dispose()
    for cache in (get_settings, get_engine, get_sessionmaker):
        cache.cache_clear()


async def _seed(db: AsyncSession) -> Seed:
    """A tenant, a user, a workspace and an owner membership, in this transaction.

    Not committed. Every test here runs inside one transaction and lets it roll
    back, which is cheaper than a teardown against `us-east-2` and cannot leave
    a half-deleted workspace behind when an assertion fails partway through.
    """
    seed = Seed(uuid4(), uuid4(), uuid4())

    await apply_workspace_scope(db, str(seed.workspace_id))
    await db.execute(
        sa.text("INSERT INTO tenant (id, name) VALUES (:t, 'Grounding Ledger Test')"),
        {"t": str(seed.tenant_id)},
    )
    await db.execute(
        sa.text("INSERT INTO app_user (id, email) VALUES (:u, :e)"),
        {"u": str(seed.user_id), "e": f"ledger-{seed.user_id}@example.invalid"},
    )
    await db.execute(
        sa.text(
            "INSERT INTO workspace (id, workspace_id, tenant_id, name, reporting_currency)"
            " VALUES (:id, :id, :t, 'Grounding Ledger Test', 'OMR')"
        ),
        {"id": str(seed.workspace_id), "t": str(seed.tenant_id)},
    )
    await db.execute(
        sa.text(
            "INSERT INTO membership (workspace_id, user_id, role, departments)"
            " VALUES (:ws, :u, 'owner', ARRAY['finance'])"
        ),
        {"ws": str(seed.workspace_id), "u": str(seed.user_id)},
    )
    return seed


def _scope(seed: Seed) -> ScopedSession:
    return ScopedSession(
        user_id=seed.user_id,
        tenant_id=seed.tenant_id,
        workspace_id=seed.workspace_id,
        role=Role.OWNER,
        departments=frozenset({Department.FINANCE}),
    )


# ── The row ───────────────────────────────────────────────────


async def test_an_answer_writes_a_row_naming_its_inputs_and_its_calculation(app_db: None) -> None:
    """P14's acceptance, in one test.

    The row has to carry both halves. `input_snapshot` answers *what did you
    use?*; `calculation_trace` answers *what did you do with it?* A row with one
    and not the other cannot answer "why are you telling me this?" — which is
    the question this whole phase exists to make answerable.
    """
    async with _unscoped_session() as db:
        seed = await _seed(db)
        answer = Answer(
            outcome=Outcome.ANSWERED,
            prose="Cash runway is unchanged since last month.",
            values={"runway_months": 7.4},
        )
        generation_id = await ledger.record(
            db,
            workspace_id=seed.workspace_id,
            module=CAPABILITY,
            prompt_version="1",
            answer=answer,
            input_snapshot={"facts": [{"key": "runway_alert_months", "value": "6"}]},
            calculation_trace={"method": "cash / monthly burn", "window": "30 days"},
            scope_key="L3:finance",
            input_tokens=120,
            output_tokens=40,
            requested_by_user_id=seed.user_id,
        )
        await db.flush()

        row = (
            await db.execute(
                sa.text(
                    "SELECT module, prompt_version, input_snapshot, calculation_trace,"
                    "       scope_key, outcome, unavailable_reason,"
                    "       input_tokens, output_tokens, cost_micros"
                    "  FROM generation WHERE id = :id"
                ),
                {"id": str(generation_id)},
            )
        ).one()

        assert row.module == CAPABILITY
        assert row.outcome == "answered"
        assert row.unavailable_reason == ""
        assert row.input_snapshot["facts"][0]["key"] == "runway_alert_months"
        assert row.calculation_trace["method"] == "cash / monthly burn"
        assert row.scope_key == "L3:finance"
        assert row.input_tokens + row.output_tokens == 160
        assert row.cost_micros == 0, (
            "there is no price table in the repository, and a made-up cost in a"
            " column called cost_micros is the exact kind of number this phase refuses"
        )


async def test_a_refusal_is_recorded_with_its_reason(app_db: None) -> None:
    """The row somebody suspicious will actually read.

    Without it, *"the tile said it could not compute this"* is unfalsifiable: a
    missing input, a schema failure and an exhausted budget look identical on
    the screen and want three different responses.
    """
    async with _unscoped_session() as db:
        seed = await _seed(db)
        generation_id = await ledger.record(
            db,
            workspace_id=seed.workspace_id,
            module=CAPABILITY,
            prompt_version="1",
            answer=Answer(
                outcome=Outcome.UNAVAILABLE,
                reason=UnavailableReason.MISSING_INPUT,
                missing=("runway_alert_months",),
            ),
            input_snapshot={"missing_facts": ["runway_alert_months"]},
            calculation_trace={},
            scope_key="L3:finance",
            requested_by_user_id=seed.user_id,
        )
        await db.flush()

        row = (
            await db.execute(
                sa.text("SELECT outcome, unavailable_reason FROM generation WHERE id = :id"),
                {"id": str(generation_id)},
            )
        ).one()

        assert row.outcome == "unavailable"
        assert row.unavailable_reason == "missing_input"


async def test_an_unavailable_row_without_a_reason_is_refused(app_db: None) -> None:
    """`ck_generation_reason_matches_outcome`, caught a layer earlier.

    The constraint is the guarantee; this check is so the caller is told which
    of its branches forgot, rather than reading a constraint name out of Neon at
    three in the morning.
    """
    async with _unscoped_session() as db:
        seed = await _seed(db)
        with pytest.raises(ValueError, match="must say which kind"):
            await ledger.record(
                db,
                workspace_id=seed.workspace_id,
                module=CAPABILITY,
                prompt_version="1",
                answer=Answer(outcome=Outcome.UNAVAILABLE),
                input_snapshot={},
                calculation_trace={},
                scope_key="L3:finance",
            )


# ── The budget, counted from the rows ─────────────────────────


async def test_the_budget_is_counted_from_the_rows_not_a_counter(app_db: None) -> None:
    """Both budgets, from one query.

    A counter would be a second source of truth about spending, and the one
    thing worse than an overspend is an overspend nobody can reconstruct.
    """
    async with _unscoped_session() as db:
        seed = await _seed(db)
        settings = get_settings()
        before = await ledger.budgets_for(
            db,
            workspace_id=seed.workspace_id,
            user_id=seed.user_id,
            settings=settings,
            timezone="Asia/Muscat",
        )
        assert before.tenant_spent == 0
        assert before.user_spent == 0
        assert not before.exhausted

        await ledger.record(
            db,
            workspace_id=seed.workspace_id,
            module=CAPABILITY,
            prompt_version="1",
            answer=Answer(outcome=Outcome.ANSWERED, prose="Unchanged."),
            input_snapshot={},
            calculation_trace={},
            scope_key="L3:finance",
            input_tokens=1_000,
            output_tokens=500,
            requested_by_user_id=seed.user_id,
        )
        await db.flush()

        after = await ledger.budgets_for(
            db,
            workspace_id=seed.workspace_id,
            user_id=seed.user_id,
            settings=settings,
            timezone="Asia/Muscat",
        )
        assert after.tenant_spent == 1_500
        assert after.user_spent == 1_500


async def test_a_generation_with_no_human_asker_spends_nobodys_allowance(app_db: None) -> None:
    """A scheduled brief counts against the tenant and against no person.

    Nobody should lose their own daily allowance to a job they did not run, and
    a background refresh that quietly ate the owner's budget would present as
    the product breaking at the same time every morning.
    """
    async with _unscoped_session() as db:
        seed = await _seed(db)
        settings = get_settings()
        await ledger.record(
            db,
            workspace_id=seed.workspace_id,
            module=CAPABILITY,
            prompt_version="1",
            answer=Answer(outcome=Outcome.ANSWERED, prose="Unchanged."),
            input_snapshot={},
            calculation_trace={},
            scope_key="L3:finance",
            input_tokens=800,
            output_tokens=200,
            requested_by_user_id=None,
        )
        await db.flush()

        budgets = await ledger.budgets_for(
            db,
            workspace_id=seed.workspace_id,
            user_id=seed.user_id,
            settings=settings,
            timezone="Asia/Muscat",
        )
        assert budgets.tenant_spent == 1_000
        assert budgets.user_spent == 0


async def test_an_exhausted_budget_is_read_from_the_rows_already_written(app_db: None) -> None:
    """Exhaustion is a fact about the table, not a flag somebody set.

    The pipeline refuses **before** the model call for this reason, so a
    workspace that has spent its allowance costs nothing more to refuse. The
    limits come from `config.py`, where they have sat unread since M0.
    """
    async with _unscoped_session() as db:
        seed = await _seed(db)
        await ledger.record(
            db,
            workspace_id=seed.workspace_id,
            module=CAPABILITY,
            prompt_version="1",
            answer=Answer(outcome=Outcome.ANSWERED, prose="Unchanged."),
            input_snapshot={},
            calculation_trace={},
            scope_key="L3:finance",
            input_tokens=10,
            output_tokens=10,
            requested_by_user_id=seed.user_id,
        )
        await db.flush()

        settings = get_settings()
        generous = await ledger.budgets_for(
            db,
            workspace_id=seed.workspace_id,
            user_id=seed.user_id,
            settings=settings,
            timezone="Asia/Muscat",
        )
        assert not generous.exhausted, "twenty tokens against the configured daily budget"

        # The same rows, read against a budget of one token. Constructed rather
        # than mutated: `Settings` is frozen, and a test that reached in to
        # change a limit would be asserting against a shape production cannot
        # take.
        tight = Budgets(
            tenant_spent=generous.tenant_spent,
            tenant_limit=1,
            user_spent=generous.user_spent,
            user_limit=1,
        )
        assert tight.exhausted

        recorded = await ledger.record(
            db,
            workspace_id=seed.workspace_id,
            module=CAPABILITY,
            prompt_version="1",
            answer=Answer(
                outcome=Outcome.UNAVAILABLE,
                reason=UnavailableReason.BUDGET_EXHAUSTED,
            ),
            input_snapshot={},
            calculation_trace={},
            scope_key="L3:finance",
            requested_by_user_id=seed.user_id,
        )
        await db.flush()

        row = (
            await db.execute(
                sa.text("SELECT unavailable_reason FROM generation WHERE id = :id"),
                {"id": str(recorded)},
            )
        ).one()
        assert row.unavailable_reason == "budget_exhausted", (
            "and it degrades to this rather than to a cheaper unevaluated model,"
            " which would be a different product nobody agreed to"
        )


# ── The context assembler ─────────────────────────────────────


async def test_the_context_reads_the_reporting_settings_it_will_be_cited_by(app_db: None) -> None:
    """The join between step A and step B.

    ADR 0025 requires every window stated in the working, and the working reads
    the reporting settings off the context. A context that did not carry them
    would leave each drawer to fetch its own — the second path
    `context.assemble` exists to prevent.
    """
    async with _unscoped_session() as db:
        seed = await _seed(db)
        context = await assemble(db, _scope(seed))

        assert context.company_name == "Grounding Ledger Test"
        assert context.currency == "OMR"
        assert context.reporting.week_start.value == "sunday"
        assert context.brain is None, "no onboarding has run for this workspace"

        # The seed is an Owner, so the context spans every department they
        # reach — and the snapshot tag has to say so. It read `L3:finance`
        # while the assembler filtered on the membership; tagging a snapshot
        # that holds seven departments' answers as a Finance artefact would
        # understate what is in it, and the retention and export queries read
        # this column.
        assert context.scope_key.startswith("L3:")
        assert "finance" in context.scope_key
        assert "operations" in context.scope_key, (
            "an Owner's context carries every department, so its tag must too"
        )


async def test_a_capabilitys_declared_facts_are_reachable_from_the_context() -> None:
    """What lets a tile say *"you told us a lead is X"*.

    Pure, because it is about the join rather than about the database: the
    capability declares the question keys it consumes, and the context resolves
    them to answers with their sources.
    """
    from app.grounding.context import Fact

    context = CompanyContext(
        workspace_id=uuid4(),
        company_name="X",
        currency="OMR",
        reporting=ReportingSettings(),
        department_facts={
            "finance": (
                Fact(
                    key="runway_alert_months",
                    value="6",
                    source_ref="onboarding_answer:finance:runway_alert_months",
                    source_kind="user_confirmed",
                ),
            )
        },
    )

    found = context.facts_for(("runway_alert_months", "payment_terms"))

    assert [fact.key for fact in found] == ["runway_alert_months"]
    assert found[0].source_ref.startswith("onboarding_answer:")
    assert context.missing_facts(("runway_alert_months", "payment_terms")) == ("payment_terms",)


# ── Which failure renders as which named state ────────────────


def test_our_own_bug_is_raised_rather_than_rendered_as_a_tile_state() -> None:
    """A caller that invoked a skill without its declared grounding has made a
    mistake, and the runner's docstring says loud is the whole point. Rendering
    it as *"unavailable"* would hide a programming error behind a sentence about
    the customer's data."""
    from app.ai.runtime.runner import SkillFailedError

    with pytest.raises(SkillFailedError):
        unavailable_for(SkillFailedError("missing required grounding"))


def test_no_key_and_a_malformed_answer_are_different_states() -> None:
    """One is a deployment fact and the other is ours to fix. Collapsing them
    makes *"the product is misconfigured"* indistinguishable from *"the model
    wrote something malformed"* on the screen where somebody is deciding whether
    to trust us."""
    from app.ai.contracts import LlmAuthError, LlmTransientError
    from app.ai.runtime.runner import SkillOutputInvalidError

    assert unavailable_for(LlmAuthError("no key")) is UnavailableReason.MODEL_UNAVAILABLE
    assert unavailable_for(LlmTransientError("overloaded")) is UnavailableReason.PROVIDER_FAILED
    assert unavailable_for(SkillOutputInvalidError("twice")) is UnavailableReason.SCHEMA_INVALID


# ── Step D: the answers, read back ────────────────────────────


async def test_setup_reads_the_founders_answers_back_with_their_dates(
    app_db: None,
) -> None:
    """`doc/13` §4's Setup section, against the real table.

    The date is not decoration. An answer from four months ago and one from
    yesterday warrant different confidence, and a founder cannot tell which they
    are looking at without it — which matters most for the answers that are
    judgements rather than facts.
    """
    async with _unscoped_session() as db:
        seed = await _seed(db)

        for key, value in (
            ("runway_alert_months", "under 6"),
            ("payment_terms", "30 days"),
        ):
            await db.execute(
                sa.text(
                    "INSERT INTO onboarding_answer"
                    " (workspace_id, answered_by_user_id, question_key, value,"
                    "  scope, department, answer_state)"
                    " VALUES (:w, :u, :k, CAST(:v AS jsonb), 'L3',"
                    "         'finance', 'bound')"
                ),
                {
                    "w": str(seed.workspace_id),
                    "u": str(seed.user_id),
                    "k": key,
                    "v": f'"{value}"',
                },
            )
        await db.flush()

        context = await assemble(db, _scope(seed))
        finance = {fact.key: fact for fact in context.department_facts["finance"]}

        assert finance["runway_alert_months"].value == "under 6", (
            "unwrapped from jsonb — a citation reading '\"30 days\"' with the"
            " quotes in it is a citation somebody stops trusting"
        )
        assert finance["payment_terms"].answered_at, "the date the founder said it"
        assert finance["runway_alert_months"].source_kind == "user_confirmed"
        assert finance["runway_alert_months"].source_ref.startswith("onboarding_answer:")


async def test_a_proposed_answer_is_never_quoted_back_as_what_you_told_us(
    app_db: None,
) -> None:
    """Q31/D22, and the reason Setup cannot read the answer table directly.

    A Contributor's answer is kept and waits for a manager at the review gate.
    Quoting one back under *"what you told us"* would present one person's
    suggestion as the department's settled position — and the person reading it
    would be the manager who never agreed to it.
    """
    async with _unscoped_session() as db:
        seed = await _seed(db)

        await db.execute(
            sa.text(
                "INSERT INTO onboarding_answer"
                " (workspace_id, answered_by_user_id, question_key, value,"
                "  scope, department, answer_state)"
                " VALUES (:w, :u, 'approver', CAST('\"the owner\"' AS jsonb),"
                "         'L3', 'finance', 'proposed')"
            ),
            {"w": str(seed.workspace_id), "u": str(seed.user_id)},
        )
        await db.flush()

        context = await assemble(db, _scope(seed))

        assert "approver" not in {fact.key for fact in context.department_facts.get("finance", ())}


async def test_an_owner_is_grounded_in_every_department_they_reach(
    app_db: None,
) -> None:
    """The bug a browser found and the unit tests could not.

    An Owner reaches every department **by role** — `ROLE_GRANTS` calls it
    `all_departments` — and usually has none listed on their membership at all.
    The assembler read `scope.departments`, so a founder who had just registered
    opened Finance and the Setup tab told them nobody had answered anything.
    Three answers were in the table.

    It was invisible to the tests because every one of them constructed a scope
    with the department on it. The seeded membership here has Finance, so the
    assertion that matters is about the **other** departments: an Owner is
    grounded in Operations too, without Operations ever being on their
    membership.
    """
    async with _unscoped_session() as db:
        seed = await _seed(db)

        await db.execute(
            sa.text(
                "INSERT INTO onboarding_answer"
                " (workspace_id, answered_by_user_id, question_key, value,"
                "  scope, department, answer_state)"
                " VALUES (:w, :u, 'supplier_concentration',"
                "         CAST('\"one valve supplier\"' AS jsonb),"
                "         'L3', 'operations', 'bound')"
            ),
            {"w": str(seed.workspace_id), "u": str(seed.user_id)},
        )
        await db.flush()

        owner = ScopedSession(
            user_id=seed.user_id,
            tenant_id=seed.tenant_id,
            workspace_id=seed.workspace_id,
            role=Role.OWNER,
            # Empty, as a real owner's membership is after registration.
            departments=frozenset(),
        )
        assert owner.has_all_departments, "the premise: reach comes from the role"

        context = await assemble(db, owner)
        operations = context.department_facts.get("operations", ())

        assert [fact.key for fact in operations] == ["supplier_concentration"]


async def test_a_manager_is_grounded_only_in_their_own_department(
    app_db: None,
) -> None:
    """The other half, and the one that must not regress in fixing the first.

    Widening the assembler to the caller's *reachable* departments is correct
    for an Owner and would be a leak for anybody else. A Department Manager
    holds one department, and the facts they are grounded in are that one's.
    """
    async with _unscoped_session() as db:
        seed = await _seed(db)

        for department, key in (
            ("finance", "payment_terms"),
            ("operations", "supplier_concentration"),
        ):
            await db.execute(
                sa.text(
                    "INSERT INTO onboarding_answer"
                    " (workspace_id, answered_by_user_id, question_key, value,"
                    "  scope, department, answer_state)"
                    " VALUES (:w, :u, :k, CAST('\"something\"' AS jsonb),"
                    "         'L3', :d, 'bound')"
                ),
                {"w": str(seed.workspace_id), "u": str(seed.user_id), "k": key, "d": department},
            )
        await db.flush()

        manager = ScopedSession(
            user_id=seed.user_id,
            tenant_id=seed.tenant_id,
            workspace_id=seed.workspace_id,
            role=Role.DEPARTMENT_MANAGER,
            departments=frozenset({Department.FINANCE}),
        )
        assert not manager.has_all_departments

        context = await assemble(db, manager)

        assert set(context.department_facts) == {"finance"}
        assert "operations" not in context.department_facts, (
            "a Finance manager's context must not carry Operations' answers,"
            " however much better the prose would read for it"
        )
        assert context.scope_key == "L3:finance"
