"""Commands: the application-facing verbs.

A command is the unit a route, a job or another agent calls. It owns one
transaction's worth of work — invoke a skill, validate what came back against
the field catalogue, persist it, emit the hook — and it is the only layer that
knows about all three of those at once.

The layering exists so the pieces stay swappable in the direction that matters:

    route / agent  ->  command  ->  skill (a file)  ->  LlmProvider

A route never touches a prompt. A skill never touches the database. Changing how
`research-company` reasons is editing `SKILL.md`; changing what it stores is
editing the command. Changing the vendor is the registry, and touches neither.

Commands are registered by name so the agent can drive them from data rather
than from a match statement that has to be edited every time a step is added.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Any, Protocol

from app.ai.runtime.hooks import HookBus
from app.ai.runtime.runner import SkillRunner
from app.logging import get_logger

log = get_logger(__name__)


@dataclass(slots=True)
class CommandContext:
    """Everything a command is allowed to reach.

    A `ScopedSession` rather than a raw one, and no `user_id`: I2/I3 say
    `retrieval/` is the only path to data and never accepts a user id. A command
    that wanted to widen its own reach would have to change this dataclass,
    which is a reviewable act.
    """

    workspace_id: str
    session: Any
    runner: SkillRunner
    hooks: HookBus
    grounding: Mapping[str, Any]
    """Grounding every skill in this request gets, on top of its own.

    Carries `user_context` — who is answering and what they say they do. Shared
    rather than threaded through each command because three skills want it and
    the fourth should not have to know that.

    Presentation only. Nothing here reaches a permission check, and
    `fields.assert_persona_is_not_authorisation` is the guard that keeps it so.
    """

    actor_user_id: str | None = None
    """Who is doing this, for the audit trail only.

    Not a retrieval input and never passed to `retrieval/` — I3 forbids that,
    and the reason it is safe here is that audit answers "who did this" rather
    than "what may they see". `audit.record` takes it for the same reason.
    """


class Command(Protocol):
    name: str
    description: str

    async def __call__(self, ctx: CommandContext, **kwargs: Any) -> Mapping[str, Any]: ...


CommandFn = Callable[..., Awaitable[Mapping[str, Any]]]


@dataclass(frozen=True, slots=True)
class _Entry:
    name: str
    description: str
    fn: CommandFn
    uses_skills: tuple[str, ...]


class CommandRegistry:
    def __init__(self) -> None:
        self._commands: dict[str, _Entry] = {}

    def register(
        self,
        name: str,
        *,
        description: str,
        uses_skills: tuple[str, ...] = (),
    ) -> Callable[[CommandFn], CommandFn]:
        def decorate(fn: CommandFn) -> CommandFn:
            if name in self._commands:
                raise ValueError(f"command {name!r} is already registered")
            self._commands[name] = _Entry(
                name=name, description=description, fn=fn, uses_skills=uses_skills
            )
            return fn

        return decorate

    def get(self, name: str) -> _Entry:
        try:
            return self._commands[name]
        except KeyError:
            raise KeyError(f"no command {name!r}; registered: {sorted(self._commands)}") from None

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._commands))

    def skills_used(self) -> frozenset[str]:
        """Every skill reachable through a command.

        A skill on disk that no command reaches is dead weight that still has to
        be maintained; the test asserts this set covers the registry.
        """
        return frozenset(s for entry in self._commands.values() for s in entry.uses_skills)

    async def run(self, name: str, ctx: CommandContext, **kwargs: Any) -> Mapping[str, Any]:
        entry = self.get(name)
        log.info("command.run", command=name, workspace_id=ctx.workspace_id)
        return await entry.fn(ctx, **kwargs)


_registry: CommandRegistry | None = None


def get_commands() -> CommandRegistry:
    global _registry
    if _registry is None:
        _registry = CommandRegistry()
        # Imported for the side effect of registering. Deferred to here rather
        # than at module scope so `app.ai.runtime` stays importable without
        # dragging in the domain layer, which imports back into it.
        from app.domain import onboarding_commands  # noqa: F401
    return _registry
