"""The only reader of chunk content. One function, and it takes a `ScopedSession`.

`ARCHITECTURE-LLD.md` §3.1, and I2/I3: **the permission predicate is part of the
query**, not a filter applied to its results. The difference is everything —
filtering afterwards means the database returned rows the caller may not see,
and every count, every `LIMIT`, every "no results" message computed before the
filter has already leaked their existence.

**No identity argument.** These functions cannot be asked to read "as" somebody:
the only way to say who is asking is to pass the `ScopedSession` the request was
authenticated into. A `user_id` parameter is exactly the shape that lets a bug
two layers up become a cross-tenant read, so it does not exist.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.scopes import Department, Scope
from app.domain.session import ScopedSession

# `review_state` is checked here as well as in the predicate below because a
# chunk still waiting for review is not yet a workspace fact — the review gate
# exists to stop unconfirmed content being retrieved as though it were.
READABLE_STATES: Final = ("auto_approved", "approved")

# `chunk.scope` is stored as the lattice's short name; `Scope` is an `IntEnum`
# whose members are spelled out. Mapped explicitly rather than by index
# arithmetic so that a value the lattice does not have raises here, at the row
# it came from, instead of resolving to a neighbouring scope.
_SCOPE_NAMES: Final = {
    "L1": "L1_COMPANY_PUBLIC",
    "L2": "L2_COMPANY_INTERNAL",
    "L3": "L3_DEPARTMENT",
    "L4": "L4_RESTRICTED",
    "L5": "L5_PERSONAL",
}

# The predicate, spelled once. `ARCHITECTURE-LLD.md` §3.1.
#
# `is_dept_aggregate` is part of it rather than checked afterwards, which is why
# it is a column: a restricted Contributor may read their department's rows but
# not the roll-ups computed across them, and "read then hide" would already have
# put the aggregate in memory next to the response.
# `noqa: S608` sits on the queries below because `PREDICATE` is interpolated
# into them. It is a module constant, never caller input, and every value it
# compares against is a bound parameter — the interpolation exists so the
# predicate is written **once** and cannot drift between the read and the count,
# which is the exact defect that turns a count into an existence oracle.
PREDICATE: Final = """
      scope IN ('L1','L2')
   OR (scope = 'L3' AND department && :depts
                    AND NOT (:restricted AND is_dept_aggregate))
   OR (scope = 'L4' AND id = ANY(:named_l4))
   OR (scope = 'L5' AND owner_user_id = :uid)
"""


@dataclass(frozen=True, slots=True)
class Passage:
    """A chunk the caller may read, with enough to cite it.

    Citations inherit permissions by construction: a passage exists only because
    it came back through the predicate, so there is no path by which a citation
    the caller cannot open reaches them.
    """

    id: UUID
    content: str
    document_id: UUID
    source_page: int | None
    source_label: str | None

    scope: Scope
    """**Read from the row, never asserted about the caller** (ADR 0057).

    A generation is tagged with the scope of what it cited, not of who asked —
    migration 0023's rule, and `context.py`'s argument for it: *"a snapshot of
    Finance facts is a Finance artefact whoever asked for it."* Without this on
    the passage, that tag would have to come from the caller's departments,
    which inverts it.

    This cannot widen what comes back. It is a column on a row `PREDICATE`
    already returned, so a passage carrying a scope the caller may not read
    would mean the predicate was wrong — which is why
    `evals/test_permissions.py` asserts these fields rather than a unit test.
    """

    department: tuple[Department, ...]
    """Empty for scopes that are not department-keyed. `chunk.department` is
    `text[]` and a chunk can sit in more than one."""


def _params(scope: ScopedSession, extra: dict[str, object]) -> dict[str, object]:
    return {
        "depts": [d.value for d in scope.departments],
        "restricted": scope.contributor_restricted,
        "named_l4": [str(i) for i in scope.named_l4_item_ids],
        "uid": str(scope.user_id),
        **extra,
    }


async def search(
    db: AsyncSession,
    scope: ScopedSession,
    *,
    embedding: list[float],
    limit: int = 10,
) -> list[Passage]:
    """Nearest chunks this caller may read. The vector path.

    **`SET LOCAL hnsw.iterative_scan` is not optional** (ADR 0012). Measured, not
    assumed: a plain HNSW index with the permission predicate as an ordinary
    `WHERE` returns **5% recall** at the selectivity of a Contributor reading
    their own rows. Raising `ef_search` looks like the fix and is not — it
    rescues a department-sized filter and leaves narrow ones broken.

    `SET LOCAL` rather than `SET`: it dies with the transaction, so it cannot
    leak onto a pooled connection and change how the next request's query plans.
    """
    await db.execute(text("SET LOCAL hnsw.iterative_scan = relaxed_order"))

    rows = (
        await db.execute(
            text(
                "SELECT id, content, document_id, source_page, source_label,"  # noqa: S608
                "       scope, department"
                "  FROM chunk"
                " WHERE workspace_id = :ws"
                "   AND review_state = ANY(:states)"
                # `PREDICATE` is a module constant, not caller input — every
                # value in it is a bound parameter. Interpolated so the
                # predicate is written once and cannot drift between the read
                # and the count, which is the defect this file exists to
                # prevent.
                f"  AND ({PREDICATE})"
                " ORDER BY embedding <=> CAST(:q AS vector)"
                " LIMIT :k"
            ),
            _params(
                scope,
                {
                    "ws": str(scope.workspace_id),
                    "states": list(READABLE_STATES),
                    "q": str(embedding),
                    "k": limit,
                },
            ),
        )
    ).all()

    return [
        Passage(
            id=row.id,
            content=row.content,
            document_id=row.document_id,
            source_page=row.source_page,
            source_label=row.source_label,
            scope=Scope[_SCOPE_NAMES[row.scope]],
            department=tuple(Department(d) for d in row.department),
        )
        for row in rows
    ]


async def count(db: AsyncSession, scope: ScopedSession) -> int:
    """How many chunks this caller may read. The relational path.

    A count is a disclosure. "There are 47 documents you cannot see" tells you
    the company has 47 documents, so this counts **through the same predicate**
    rather than counting everything and subtracting — which is the shape that
    turns a count into an oracle.
    """
    return int(
        (
            await db.execute(
                text(
                    "SELECT count(*) FROM chunk"  # noqa: S608
                    " WHERE workspace_id = :ws"
                    "   AND review_state = ANY(:states)"
                    f"  AND ({PREDICATE})"
                ),
                _params(scope, {"ws": str(scope.workspace_id), "states": list(READABLE_STATES)}),
            )
        ).scalar_one()
    )
