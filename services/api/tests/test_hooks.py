"""The hook bus: what runs, what is isolated, and what is allowed to fail a turn.

The split between the two handler classes is the part worth testing. "Isolated"
is not a property you can grant a handler that touches the database — once a
statement fails, Postgres aborts the transaction and every later statement
raises regardless of what this bus swallows. So the bus has to let those
propagate, and the tests below pin both halves.
"""

from __future__ import annotations

import pytest

from app.ai.runtime.hooks import HookBus, HookEvent, HookPoint, get_hooks


def _event(point: HookPoint = HookPoint.CONTEXT_UPDATED, **payload: object) -> HookEvent:
    return HookEvent(point=point, workspace_id="ws-1", payload=payload)


async def test_a_handler_runs_and_receives_the_event() -> None:
    bus = HookBus()
    seen: list[HookEvent] = []

    @bus.on(HookPoint.CONTEXT_UPDATED, name="collect")
    def collect(event: HookEvent) -> None:
        seen.append(event)

    await bus.emit(_event(kind="brain"))
    assert [e.payload["kind"] for e in seen] == ["brain"]


async def test_async_and_sync_handlers_both_work() -> None:
    bus = HookBus()
    order: list[str] = []

    @bus.on(HookPoint.CONTEXT_UPDATED, name="sync", priority=1)
    def sync_handler(_: HookEvent) -> None:
        order.append("sync")

    @bus.on(HookPoint.CONTEXT_UPDATED, name="async", priority=2)
    async def async_handler(_: HookEvent) -> None:
        order.append("async")

    await bus.emit(_event())
    assert order == ["sync", "async"]


async def test_an_isolated_handler_failing_does_not_stop_the_others() -> None:
    """A broken log line must never cost somebody their signup."""
    bus = HookBus()
    reached: list[str] = []

    @bus.on(HookPoint.CONTEXT_UPDATED, name="broken", priority=1)
    def broken(_: HookEvent) -> None:
        raise RuntimeError("telemetry backend is down")

    @bus.on(HookPoint.CONTEXT_UPDATED, name="after", priority=2)
    def after(_: HookEvent) -> None:
        reached.append("after")

    await bus.emit(_event())
    assert reached == ["after"]


async def test_a_critical_handler_failing_fails_the_turn() -> None:
    """The audit row and the answer are one fact; half of it is worse than neither.

    Swallowing here would also be a lie: a handler that already issued a failed
    statement has aborted the transaction, so every later write raises anyway —
    just further away from the cause.
    """
    bus = HookBus()

    @bus.on(HookPoint.ANSWER_SUBMITTED, name="audit", critical=True)
    def audit(_: HookEvent) -> None:
        raise RuntimeError("audit_log insert refused")

    with pytest.raises(RuntimeError, match="audit_log insert refused"):
        await bus.emit(_event(HookPoint.ANSWER_SUBMITTED))


async def test_critical_handlers_run_before_isolated_ones() -> None:
    """Ordering is not cosmetic.

    If a telemetry handler ran first and threw, its exception would be swallowed
    — but any statement it had issued would already have poisoned the
    transaction, and the audit write would then fail for a reason that has
    nothing to do with audit.
    """
    bus = HookBus()
    order: list[str] = []

    @bus.on(HookPoint.ANSWER_SUBMITTED, name="telemetry", priority=1)
    def telemetry(_: HookEvent) -> None:
        order.append("telemetry")

    @bus.on(HookPoint.ANSWER_SUBMITTED, name="audit", priority=99, critical=True)
    def audit(_: HookEvent) -> None:
        order.append("audit")

    await bus.emit(_event(HookPoint.ANSWER_SUBMITTED))
    assert order == ["audit", "telemetry"], "critical must run first despite priority"


async def test_two_handlers_cannot_share_a_name() -> None:
    """A duplicate name is a silent override, and names are how tests assert."""
    bus = HookBus()

    @bus.on(HookPoint.CONTEXT_UPDATED, name="same")
    def first(_: HookEvent) -> None: ...

    with pytest.raises(ValueError, match="already registered"):

        @bus.on(HookPoint.CONTEXT_UPDATED, name="same")
        def second(_: HookEvent) -> None: ...


async def test_emitting_a_point_with_no_handlers_is_not_an_error() -> None:
    await HookBus().emit(_event())


# ── The real registrations ────────────────────────────────────


def test_every_hook_point_has_at_least_one_handler() -> None:
    """A point nobody listens to is an event that fires into nothing.

    `skill.invoked` sat in the enum unemitted and unhandled for exactly this
    reason — the member existed, so it looked wired.
    """
    bus = get_hooks()
    orphans = [p.value for p in HookPoint if not bus.handlers_for(p)]
    assert not orphans, f"hook points with no handler: {orphans}"


def test_the_answer_audit_handler_is_registered_critical() -> None:
    """If this ever became isolated, answers would be recorded with no audit row
    and nothing would say so."""
    bus = get_hooks()
    assert "audit-answer" in bus.handlers_for(HookPoint.ANSWER_SUBMITTED)


async def test_the_audit_handler_skips_a_turn_with_no_target() -> None:
    """A free-text aside is not a fact; there is nothing to audit.

    Passing no session as well proves the guard order — it must not reach for
    the database before deciding there is nothing to write.
    """
    from app.domain.onboarding_hooks import audit_answer

    await audit_answer(HookEvent(point=HookPoint.ANSWER_SUBMITTED, workspace_id="ws-1"))


async def test_the_audit_handler_does_nothing_without_a_session() -> None:
    from app.domain.onboarding_hooks import audit_answer

    await audit_answer(
        HookEvent(
            point=HookPoint.ANSWER_SUBMITTED,
            workspace_id="ws-1",
            payload={"target": "brain.goals", "scope": 2},
        )
    )
