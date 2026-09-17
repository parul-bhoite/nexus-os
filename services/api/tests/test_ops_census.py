"""Counting a workspace's own records — `doc/15` S10.1, ADR 0034.

`compute_from_ops` is the third dispatch in `grounding/compute.py` and the first
over rows NEXUS itself stores. These assert the arithmetic reaches the figure
unchanged, and — more importantly — that nothing in the shape can express a
rate. The ops layer fails on adoption, so a percentage over its rows is a wrong
number with a plausible denominator, which is the failure this product exists to
prevent.

Hermetic: the dispatch takes a snapshot, never a session.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from uuid import uuid4

import pytest

from app.calculators.completeness import PROJECTS, TASKS, Confirmation
from app.grounding.compute import OPS_CENSUSES, compute_from_ops, computes
from app.retrieval.ops import OpsSnapshot, Project, Task

TODAY = date(2026, 9, 17)
RECORDED_AT = datetime(2026, 9, 14, 8, 30, tzinfo=UTC)


def _project(status: str = "active", due_on: date | None = None) -> Project:
    return Project(id=uuid4(), name="Muscat fit-out", status=status, client=None, due_on=due_on)


def _task(status: str = "todo", due_on: date | None = None) -> Task:
    return Task(
        id=uuid4(),
        project_id=None,
        title="Order the glazing",
        status=status,
        assignee_id=None,
        due_on=due_on,
    )


def _snapshot(
    *,
    projects: list[Project] | None = None,
    tasks: list[Task] | None = None,
    recorded_at: datetime | None = RECORDED_AT,
    confirmations: dict[str, Confirmation] | None = None,
) -> OpsSnapshot:
    return OpsSnapshot(
        projects=projects if projects is not None else [],
        tasks=tasks if tasks is not None else [],
        recorded_at=recorded_at,
        confirmations=confirmations or {},
    )


def _confirmed(entity: str) -> Confirmation:
    return Confirmation(
        entity=entity, complete_as_of=date(2026, 9, 11), confirmed_on=date(2026, 9, 14)
    )


# ── The dispatch ──────────────────────────────────────────────


def test_it_counts_the_projects_for_the_projects_board() -> None:
    result = compute_from_ops(
        "operations.projects_board",
        _snapshot(
            projects=[_project(due_on=date(2026, 9, 1)), _project("done"), _project()],
            tasks=[_task() for _ in range(9)],
        ),
        today=TODAY,
    )

    assert result is not None
    assert (result.counts.recorded, result.counts.open_items) == (3, 2)
    assert (result.counts.overdue, result.counts.undated) == (1, 1)


def test_the_two_capabilities_count_different_lists() -> None:
    """The bug this guards is one `select` pasted into both entries — the tiles
    would agree with each other and disagree with the database, and both numbers
    would look entirely plausible."""
    snapshot = _snapshot(projects=[_project()], tasks=[_task(), _task()])

    projects = compute_from_ops("operations.projects_board", snapshot, today=TODAY)
    tasks = compute_from_ops("operations.task_queue", snapshot, today=TODAY)

    assert projects is not None and tasks is not None
    assert projects.counts.recorded == 1
    assert tasks.counts.recorded == 2
    assert (projects.noun, tasks.noun) == ("projects", "tasks")


def test_a_capability_nothing_censuses_is_none_not_a_zero() -> None:
    """`compute_from_crawl`'s rule, for the same reason: a zero would say this
    company has no projects, where the truth is that nobody wrote the
    calculation."""
    assert compute_from_ops("operations.stock_levels", _snapshot(), today=TODAY) is None


def test_an_empty_list_is_a_real_zero_and_not_none() -> None:
    """A workspace that recorded projects and no tasks has zero tasks written
    down. **Never having used the layer at all** is `current_ops` returning
    `None`, which never reaches this function."""
    result = compute_from_ops(
        "operations.task_queue", _snapshot(projects=[_project()]), today=TODAY
    )

    assert result is not None
    assert result.counts.recorded == 0


# ── What the figure is allowed to say ─────────────────────────


@pytest.fixture(params=sorted(OPS_CENSUSES))
def capability_id(request: pytest.FixtureRequest) -> str:
    return str(request.param)


def test_the_label_says_recorded(capability_id: str) -> None:
    """**The sentence-level half of ADR 0034.** "Projects" is a claim about the
    company; "Projects recorded" is a claim about the record, and only the
    second is one we can stand behind while D29 is open."""
    result = compute_from_ops(capability_id, _snapshot(), today=TODAY)

    assert result is not None
    assert "recorded" in result.label.lower()


def test_measures_names_what_was_not_counted(capability_id: str) -> None:
    """The same guard the other two kinds carry. A correct number under a
    headline that promises more is the one dishonest thing any of these shapes
    can ship."""
    result = compute_from_ops(capability_id, _snapshot(), today=TODAY)

    assert result is not None
    assert "Not " in result.measures
    assert len(result.measures) > 80


def test_no_value_the_prose_may_state_is_a_rate(capability_id: str) -> None:
    """**The rule this kind exists under.** `answer._permitted` treats every key
    in `values` as a figure the model may write, so a ratio landing here is a
    percentage the product would then defend as grounded."""
    result = compute_from_ops(
        capability_id,
        _snapshot(projects=[_project(), _project("done")], tasks=[_task(), _task("done")]),
        today=TODAY,
    )

    assert result is not None
    assert set(result.computed.values) == {"recorded", "open", "overdue", "undated", "done"}
    assert all(float(v).is_integer() for v in result.computed.values.values())
    assert all(v <= result.computed.values["recorded"] for v in result.computed.values.values())


def test_the_counts_reach_the_figure_unchanged(capability_id: str) -> None:
    """I1: the number on the tile is the number the calculator produced. A
    dispatch that re-derived anything would be a second place for "overdue" to
    mean something else."""
    result = compute_from_ops(
        capability_id,
        _snapshot(projects=[_project(due_on=date(2026, 1, 1))], tasks=[_task(due_on=TODAY)]),
        today=TODAY,
    )

    assert result is not None
    assert result.computed.values["recorded"] == float(result.counts.recorded)
    assert result.computed.values["overdue"] == float(result.counts.overdue)
    assert result.trace["overdue"] == result.counts.overdue


def test_the_trace_names_a_method_a_reader_can_go_and_check(capability_id: str) -> None:
    result = compute_from_ops(capability_id, _snapshot(), today=TODAY)

    assert result is not None
    assert result.trace["method"] == "calculators.ops.count_items"
    assert result.trace["delta"] == "no_baseline"


# ── Provenance ────────────────────────────────────────────────


def test_it_reports_when_somebody_typed_not_when_we_measured(capability_id: str) -> None:
    """Nothing was fetched, so `recorded_at` is the only honest timestamp — and
    it is the snapshot's, never `now()`, which would make a figure from March
    look like it was taken this morning."""
    result = compute_from_ops(capability_id, _snapshot(), today=TODAY)

    assert result is not None
    assert result.recorded_at == RECORDED_AT


def test_a_snapshot_with_no_stamp_falls_back_to_today(capability_id: str) -> None:
    """`recorded_at` is `None` only when both lists are empty, which
    `current_ops` turns into `None` before this is ever called — so this is the
    unreachable branch made deliberate rather than left to raise."""
    result = compute_from_ops(capability_id, _snapshot(recorded_at=None), today=TODAY)

    assert result is not None
    assert result.recorded_at.date() == TODAY


# ── It is wired ───────────────────────────────────────────────


def test_computes_says_yes_for_both(capability_id: str) -> None:
    assert computes(capability_id) is True


# ── Completeness — `doc/15` S10.2, ADR 0035 ───────────────────


def test_a_figure_carries_no_confirmation_by_default(capability_id: str) -> None:
    """**The common case, and the one that matters.** Nobody has said whether
    this is all of them, which is what refuses every rate over these rows and
    what the tile has to say in words."""
    result = compute_from_ops(capability_id, _snapshot(), today=TODAY)

    assert result is not None
    assert result.confirmation is None
    assert result.trace["complete_as_of"] == "not confirmed"


def test_a_figure_carries_the_confirmation_for_its_own_entity(capability_id: str) -> None:
    entity = PROJECTS if capability_id == "operations.projects_board" else TASKS
    result = compute_from_ops(
        capability_id, _snapshot(confirmations={entity: _confirmed(entity)}), today=TODAY
    )

    assert result is not None
    assert result.confirmation is not None
    assert result.confirmation.entity == entity
    assert result.trace["complete_as_of"] == "2026-09-11"


def test_confirming_one_entity_does_not_vouch_for_the_other() -> None:
    """**The reason completeness is per entity.** Somebody can have recorded
    every project and a third of the tasks; one switch covering both would let
    the honest half vouch for the careless one."""
    snapshot = _snapshot(confirmations={PROJECTS: _confirmed(PROJECTS)})

    projects = compute_from_ops("operations.projects_board", snapshot, today=TODAY)
    tasks = compute_from_ops("operations.task_queue", snapshot, today=TODAY)

    assert projects is not None and tasks is not None
    assert projects.confirmation is not None
    assert tasks.confirmation is None


def test_a_confirmation_does_not_add_a_rate_to_the_values(capability_id: str) -> None:
    """Confirming completeness unlocks S10.4's rate; it does not retroactively
    turn a count into one. The keys the model may state are unchanged."""
    entity = PROJECTS if capability_id == "operations.projects_board" else TASKS
    confirmed = compute_from_ops(
        capability_id, _snapshot(confirmations={entity: _confirmed(entity)}), today=TODAY
    )
    bare = compute_from_ops(capability_id, _snapshot(), today=TODAY)

    assert confirmed is not None and bare is not None
    assert set(confirmed.computed.values) == set(bare.computed.values)
