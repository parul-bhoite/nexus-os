"""Reading and writing the agentic onboarding journey.

Thin on purpose. The routes decide what to do next and the agent decides what to
say; this module only knows how to put a turn in a table and get it back.

One rule it does enforce, because it is the only place that can: **a user turn
carrying a target must carry that target's scope**, and the scope is looked up
here from the field catalogue rather than accepted from the caller. The database
has the same rule as `ck_onboarding_turn_scoped_answer`; this is the layer that
makes sure the value is right rather than merely present.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.engine import RowMapping
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.runtime.fields import resolve
from app.domain.page_signals import CaptureSource
from app.logging import get_logger

log = get_logger(__name__)

# Arbitrary but fixed. `pg_advisory_*` locks share one global space, so the first
# key is a namespace: anything else in this application that locks on a workspace
# id must pick a different one or the two features will exclude each other.
_START_LOCK_NAMESPACE = 0x4E58_5301


class Phase(StrEnum):
    """The journey's steps, and the source of truth for `ck_onboarding_session_phase`.

    An enum rather than literals because the set is written in three places —
    this module, the agent's transitions, and the client's union type — and the
    migration's CHECK is the fourth. `test_constraint_enum_parity` compares this
    against the constraint on every run, which is the only reason the four
    cannot quietly disagree.

    **`DOCUMENTS` and `TOOLS` are between the interview and the assembly, not
    after it.** Everything the person supplies has to be in hand before
    `build_persona` and `build_company_brain` run, because those two commands
    are the moment the drafts become the artefact the rest of the product reads.
    A journey that assembled first and collected the files afterwards would
    produce a Brain that had never seen the price list it is quoting from, and
    the only repair would be assembling it a second time — paying for every
    model call again to reach a state that could have been reached once.

    So `finish` refuses to run from either of them: the ordering is a
    precondition checked in the database's phase column rather than a sequence
    the client is trusted to follow. Both steps are skippable (`doc/09` §6.2
    already makes the upload stage skippable), and skipping is an explicit move
    that advances the phase — not a silence the server has to interpret.
    """

    ANALYSING = "analysing"
    BRIEF = "brief"
    DISCOVERY = "discovery"
    DOCUMENTS = "documents"
    TOOLS = "tools"
    PERSONA = "persona"
    ASSEMBLING = "assembling"
    READY = "ready"


class SessionStatus(StrEnum):
    ACTIVE = "active"
    COMPLETED = "completed"
    ABANDONED = "abandoned"


class TurnRole(StrEnum):
    AGENT = "agent"
    USER = "user"


@dataclass(slots=True)
class StoredTurn:
    seq: int
    role: str
    text: str
    target_field: str | None
    scope: int | None


@dataclass(slots=True)
class StoredSession:
    id: UUID
    workspace_id: UUID
    status: str
    phase: str
    domain: str | None
    research: Mapping[str, Any]
    brief: Mapping[str, Any]
    persona_draft: Mapping[str, Any]
    context: Mapping[str, Any]
    turns: list[StoredTurn]

    @property
    def answers(self) -> dict[str, str]:
        """Every answered field, latest wins.

        Derived from the turns rather than kept as a second column: two places
        holding the same truth is two places to disagree, and the turn list is
        the one that has to be right for the transcript to make sense.
        """
        out: dict[str, str] = {}
        for turn in self.turns:
            if turn.role == "user" and turn.target_field:
                out[turn.target_field] = turn.text
        return out


def _loads(value: Any) -> Mapping[str, Any]:
    if value is None:
        return {}
    if isinstance(value, str):
        return dict(json.loads(value))
    return dict(value)


async def active(db: AsyncSession, *, workspace_id: UUID) -> StoredSession | None:
    row = (
        await db.execute(
            sa.text(
                "SELECT id, workspace_id, status, phase, domain, research, brief,"
                " persona_draft, context FROM onboarding_session"
                " WHERE workspace_id = :ws AND status = :active"
            ),
            {"ws": workspace_id, "active": SessionStatus.ACTIVE.value},
        )
    ).mappings().first()
    if row is None:
        return None

    return await _hydrate(db, row)


async def _hydrate(db: AsyncSession, row: RowMapping) -> StoredSession:
    turns = (
        await db.execute(
            sa.text(
                "SELECT seq, role, text, target_field, scope FROM onboarding_turn"
                " WHERE session_id = :sid ORDER BY seq"
            ),
            {"sid": row["id"]},
        )
    ).mappings().all()

    return StoredSession(
        id=row["id"],
        workspace_id=row["workspace_id"],
        status=row["status"],
        phase=row["phase"],
        domain=row["domain"],
        research=_loads(row["research"]),
        brief=_loads(row["brief"]),
        persona_draft=_loads(row["persona_draft"]),
        context=_loads(row["context"]),
        turns=[
            StoredTurn(
                seq=t["seq"], role=t["role"], text=t["text"],
                target_field=t["target_field"], scope=t["scope"],
            )
            for t in turns
        ],
    )


async def latest(db: AsyncSession, *, workspace_id: UUID) -> StoredSession | None:
    """The most recent session for a workspace, whatever its status.

    `active()` cannot tell "never started" from "already finished" — both give
    None. The difference matters at the front door: the first should begin a
    journey and the second must not, or a founder who clicks a stale link from
    their dashboard silently starts a second onboarding over the top of the
    Brain they already have.
    """
    row = (
        await db.execute(
            sa.text(
                "SELECT id, workspace_id, status, phase, domain, research, brief,"
                " persona_draft, context FROM onboarding_session"
                " WHERE workspace_id = :ws ORDER BY created_at DESC LIMIT 1"
            ),
            {"ws": workspace_id},
        )
    ).mappings().first()
    return None if row is None else await _hydrate(db, row)


async def by_id(db: AsyncSession, *, session_id: UUID) -> StoredSession | None:
    """One session by id, whatever its status.

    `active()` filters to the live journey, which is right for every request
    that continues one. It is wrong immediately after `complete()`, when the
    caller still needs to render the session it just closed — reusing `active()`
    there returns None and the request 404s on its own success.
    """
    row = (
        await db.execute(
            sa.text(
                "SELECT id, workspace_id, status, phase, domain, research, brief,"
                " persona_draft, context FROM onboarding_session WHERE id = :sid"
            ),
            {"sid": session_id},
        )
    ).mappings().first()
    return None if row is None else await _hydrate(db, row)


class StartInFlightError(RuntimeError):
    """Another request is already opening a journey for this workspace."""


async def start(db: AsyncSession, *, workspace_id: UUID, user_id: UUID, domain: str) -> UUID:
    """Open a journey, or return the one already open.

    `ux_onboarding_session_active` allows exactly one live session per workspace,
    so a double-clicked Start does not produce two agents racing to promote their
    own drafts into the same Brain.

    The index alone is not enough, because the check below and the insert are not
    one atomic act across two transactions. Both callers read "no active session",
    both insert, and the loser then **waits on the index** — not for a moment, but
    for as long as the winner's transaction runs, which for this particular caller
    is a crawl plus two model calls. The wait outlives the statement timeout and
    surfaces as a 500 on a request that did nothing wrong.

    So the mutual exclusion is taken up front, with a lock that refuses rather
    than queues. `pg_try_advisory_xact_lock` returns false instead of blocking,
    and is released when the transaction ends however it ends. The caller that
    loses is told to retry, by which time the winner has committed and the
    `active()` check above it returns the session it was going to create.
    """
    existing = await active(db, workspace_id=workspace_id)
    if existing is not None:
        return existing.id

    # Keyed on the workspace, so two different workspaces never contend. The
    # namespace constant keeps this lock from colliding with any other advisory
    # lock the application takes on the same workspace id.
    got = (
        await db.execute(
            # The `int4` cast is required, not decorative: the two-key overload
            # is `(int4, int4)` and a Python int binds as `int8`, which matches
            # no overload at all.
            sa.text("SELECT pg_try_advisory_xact_lock(CAST(:ns AS int4), hashtext(:key))"),
            {"ns": _START_LOCK_NAMESPACE, "key": str(workspace_id)},
        )
    ).scalar_one()
    if not got:
        raise StartInFlightError(str(workspace_id))

    # Re-read under the lock. The winner may have committed between the check at
    # the top and the lock being granted, in which case there is now a session to
    # return and nothing to insert.
    existing = await active(db, workspace_id=workspace_id)
    if existing is not None:
        return existing.id

    row = (
        await db.execute(
            sa.text(
                "INSERT INTO onboarding_session (workspace_id, user_id, domain)"
                " VALUES (:ws, :uid, :domain) RETURNING id"
            ),
            {"ws": workspace_id, "uid": user_id, "domain": domain},
        )
    ).mappings().one()
    return UUID(str(row["id"]))


def _storable(value: str) -> str:
    """Text Postgres will accept in a `jsonb` string.

    **`jsonb` cannot hold `\u0000`.** Not "should not" — the driver raises
    `UntranslatableCharacterError` and the whole request dies. A crawl of
    `berkshirehathaway.com` returned a body the fetcher could not decode, six
    NUL bytes among the replacement characters, and onboarding answered 500 on
    the first request of that customer's life.

    Stripped here, at the boundary that actually fails, rather than trusted to
    every caller: the onboarding route now refuses undecodable pages outright
    (`research.runner.is_prose`), but a single stray NUL in an otherwise
    readable page must cost a character and not a signup.
    """
    return value.replace("\x00", "")


async def save_page_signals(
    db: AsyncSession,
    *,
    session_id: UUID,
    workspace_id: UUID,
    pages: Sequence[Mapping[str, str]],
    signals: Mapping[str, dict[str, Any]],
) -> None:
    """Store what each kept page demonstrably contained, superseding any prior crawl.

    Takes **already-serialised** payloads rather than `PageSignals`, and that
    is not a convenience. `tests/test_no_unauthenticated_crawl.py` forbids any
    module under `app/research/` from being reachable from an unauthenticated
    route, and this module is reachable from `routes/companies.py` — so
    importing the codec here failed that test the moment it was written. The
    conversion belongs to the caller, which is the authenticated route that
    already imports the crawler to run it.

    Separate from `save_crawl` and not folded into it, because the two write
    different shapes for different readers. `save_crawl` merges into the
    `research` JSONB with `||`, and it flattens every page value with
    `_storable(str(v))` — a nested signals dict would be stored as its Python
    `repr` and come back unparseable. These go to their own table, typed, with
    RLS of their own.

    **`position` is the index into `pages`, not into the crawl.** The caller has
    already dropped undecodable pages with `is_prose`, so position 0 is the
    first page that survived that filter. `site.plan` orders by priority, which
    makes it the page the crawl led with — the rule `retrieval/crawl.py` reads
    by. Indexing the unfiltered crawl instead would let position 0 name a page
    that was dropped, and the tile would read `locked` while rows existed.

    Supersede-then-insert in the caller's transaction, matching `company_brain`:
    a re-crawl must not leave two generations of a page competing to be
    position 0, and the old rows are the history that explains why a figure
    moved.
    """
    await db.execute(
        sa.text(
            "UPDATE page_signals SET superseded_at = now()"
            " WHERE workspace_id = :ws AND superseded_at IS NULL"
        ),
        {"ws": workspace_id},
    )
    for position, page in enumerate(pages):
        url = str(page.get("url", ""))
        captured = signals.get(url)
        if captured is None:
            # A page kept by the caller that the crawl captured nothing for.
            # Skipped rather than stored empty: an all-default `PageSignals`
            # scores zero on every check, which would say the page failed them
            # rather than that we never read it (I10).
            continue
        await db.execute(
            sa.text(
                "INSERT INTO page_signals"
                " (workspace_id, captured_by, session_id, url, position, signals)"
                " VALUES (:ws, :by, :sid, :url, :pos, CAST(:sig AS jsonb))"
            ),
            {
                "ws": workspace_id,
                "by": CaptureSource.ONBOARDING.value,
                "sid": session_id,
                "url": url,
                "pos": position,
                "sig": json.dumps(captured),
            },
        )


async def save_crawl(
    db: AsyncSession,
    *,
    session_id: UUID,
    pages: Sequence[Mapping[str, str]],
    unreadable_reason: str | None = None,
) -> None:
    """Record what the fetcher retrieved, before anything has read it.

    **Called for a failed crawl too, with no pages and a reason.** It used to be
    called only on success, which left "we have not crawled yet" and "we
    crawled and the site gave us nothing" indistinguishable on the row — so a
    site behind bot protection produced a 422, an account and a company that
    already existed, and no state saying why or what to do next. Recording the
    attempt is what makes that recoverable: `unreadable` is the flag the manual
    description path is offered on, and it also stops a repeated `/start` from
    re-crawling a site that has already refused once.

    Written under `research.crawl` rather than into `research` itself: the
    research skill's own output lands in the same column a few seconds later,
    and the two are different kinds of thing. This is what was fetched; that is
    what was understood from it.

    Kept server-side so the pages the brief is grounded in cannot be edited in
    transit — a client that supplied the grounding could have the brief describe
    a company it invented.
    """
    await db.execute(
        sa.text(
            # `CAST(:patch AS jsonb)`, not `:patch::jsonb`. SQLAlchemy's `text()`
            # will not bind a parameter followed immediately by `::` — the name
            # is left in the string and Postgres reports a syntax error at the
            # colon. The `'{}'::jsonb` on the same line is fine: no bind there.
            "UPDATE onboarding_session"
            " SET research = COALESCE(research, '{}'::jsonb) || CAST(:patch AS jsonb),"
            "     updated_at = now()"
            " WHERE id = :sid"
        ),
        {
            "sid": session_id,
            "patch": json.dumps(
                {
                    "crawl": {
                        "pages": [
                            {k: _storable(str(v)) for k, v in dict(p).items()} for p in pages
                        ],
                        # Present and true only when the fetch produced nothing.
                        # Absent on success rather than false, so an older row
                        # written before this existed reads as "not unreadable"
                        # without a migration.
                        **(
                            {"unreadable": True, "reason": unreadable_reason or "no pages returned"}
                            if not pages
                            else {}
                        ),
                    }
                }
            ),
        },
    )


async def save_research(
    db: AsyncSession, *, session_id: UUID, research: Mapping[str, Any]
) -> None:
    """Merge a research payload into the session's `research` column.

    Merged rather than replaced, for the same reason `save_crawl` merges: the
    crawl record lives in the same column under `crawl`, and overwriting it
    would erase the evidence of what was fetched — or, on the unreadable path,
    the evidence that nothing was and why.
    """
    await db.execute(
        sa.text(
            "UPDATE onboarding_session"
            " SET research = COALESCE(research, '{}'::jsonb) || CAST(:patch AS jsonb),"
            "     updated_at = now()"
            " WHERE id = :sid"
        ),
        {"sid": session_id, "patch": json.dumps(dict(research))},
    )


async def set_phase(db: AsyncSession, *, session_id: UUID, phase: str) -> None:
    """Move the session to `phase`.

    The value is checked against `Phase` before it reaches SQL — the column has
    `ck_onboarding_session_phase` behind it, and a bad value should fail here
    with the name of the offender rather than as a constraint violation with a
    stack trace.
    """
    if phase not in set(Phase):
        raise ValueError(f"{phase!r} is not an onboarding phase; see Phase")
    await db.execute(
        sa.text("UPDATE onboarding_session SET phase = :p, updated_at = now() WHERE id = :sid"),
        {"sid": session_id, "p": phase},
    )


async def append_turn(
    db: AsyncSession,
    *,
    session_id: UUID,
    workspace_id: UUID,
    role: str,
    text: str,
    target_field: str | None = None,
    skill: str | None = None,
    skill_version: str | None = None,
) -> StoredTurn:
    """Write one turn and return it. The scope is looked up, never passed in.

    A caller that could supply the scope could choose the sensitivity its own
    answer is stored at, which is the one thing the field catalogue exists to
    take out of anyone's hands.

    **One statement, not two.** The sequence number used to be a `SELECT
    MAX(seq) + 1` of its own, immediately before the insert. Against a database
    340ms away that is a third of a second spent asking a question the insert
    could answer for itself, on the hot path of every turn in the interview —
    and it was also a read-then-write race that only the unique constraint on
    `(session_id, seq)` was catching.

    Returning the row rather than the number is what lets a caller add it to the
    session it is already holding, instead of re-reading the whole session and
    every turn in it to see the one it just wrote.
    """
    scope = resolve(target_field).scope if target_field else None

    seq = (
        await db.execute(
            sa.text(
                "INSERT INTO onboarding_turn (session_id, workspace_id, seq, role, text,"
                " target_field, scope, skill, skill_version)"
                " SELECT :sid, :ws, COALESCE(MAX(seq), 0) + 1, :role, :text, :target,"
                "        :scope, :skill, :version"
                "   FROM onboarding_turn WHERE session_id = :sid"
                " RETURNING seq"
            ),
            {
                "sid": session_id, "ws": workspace_id,
                "role": role, "text": text, "target": target_field,
                "scope": scope, "skill": skill, "version": skill_version,
            },
        )
    ).scalar_one()

    return StoredTurn(
        seq=int(seq), role=role, text=text, target_field=target_field, scope=scope
    )


async def complete(db: AsyncSession, *, session_id: UUID, context: Mapping[str, Any]) -> None:
    await db.execute(
        sa.text(
            "UPDATE onboarding_session SET status = :done, phase = :ready,"
            " context = CAST(:ctx AS jsonb), completed_at = now(), updated_at = now()"
            " WHERE id = :sid"
        ),
        {
            "sid": session_id,
            "ctx": json.dumps(dict(context)),
            "done": SessionStatus.COMPLETED.value,
            "ready": Phase.READY.value,
        },
    )


def transcript(turns: Sequence[StoredTurn]) -> list[dict[str, str]]:
    return [{"role": t.role, "text": t.text} for t in turns]
