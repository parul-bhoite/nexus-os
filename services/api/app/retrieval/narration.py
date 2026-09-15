"""The stored sentence for each capability — the first display read of `generation`.

`ledger.py`'s header records that migration 0023 "built an index for each
direction while nothing wrote a single row". This is the read those indexes
were for, finally built, and 0029 added the one it actually needs.

## Three decisions in the query

**No `scope_key` filter, and it cannot have one.** `context.assemble` derives
`scope_key` from the *caller's* reach, so an Owner's is every department they
hold and a Marketing manager's is `L3:marketing` — for the same tile, narrated
once. Filtering on it would mean neither ever sees the other's sentence.

That is honest only because of two things asserted elsewhere: `narrate` sends
the model **no facts at all** (six grounding keys, none of them a fact — see
`test_grounding_compute.py`), so the prose cannot contain a department-scoped
value; and this query **never selects `input_snapshot`**, which is where a
capability's `consumes_facts` do land. `marketing.seo_gaps` consumes
`arabic_in_scope`, which is L3, so that second half is load-bearing rather than
theoretical, and `test_narration_isolation.py` asserts the column stays out of
the `SELECT`.

**`outcome = 'answered'` is in the `WHERE`.** A refusal is not a narration to
display. Without this line a founder who exhausted their allowance yesterday
opens the dashboard today and reads that their allowance is spent, hours after
it reset. The refusal belongs to the attempt somebody just made — the POST's
response — and the page says what is true now.

**`->>`, never `=`.** `calculation_trace` is `sa.JSON`, not JSONB (migration
0023 line 43), and `json = json` is not an operator in Postgres. A comparison
written that way passes every test that does not touch a database and fails
only against a real one.
"""

from __future__ import annotations

from typing import Final

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.narration import StoredNarration
from app.domain.session import ScopedSession

_CURRENT: Final = sa.text(
    """
    SELECT DISTINCT ON (module)
           module,
           prose,
           prompt_version,
           created_at,
           calculation_trace ->> 'numerator'   AS numerator,
           calculation_trace ->> 'denominator' AS denominator,
           calculation_trace ->> 'percentage'  AS percentage,
           calculation_trace ->> 'page'        AS page,
           calculation_trace ->> 'window'      AS window
      FROM generation
     WHERE workspace_id = :ws
       AND outcome = 'answered'
     ORDER BY module, created_at DESC
    """
)
"""Newest answered row per capability.

`DISTINCT ON (module) … ORDER BY module, created_at DESC` is what migration
0029's `(workspace_id, module, created_at DESC)` index serves. Re-narrating
leaves both rows — the ledger is a record, not a cache — so the read has to
pick, and picking the older one would show a sentence somebody has already
replaced.

`workspace_id = :ws` doubles the RLS policy for the reason `crawl.py` gives: it
is what makes the index usable, and it is the same value the policy compares,
so the two cannot disagree.
"""


async def current_narrations(
    db: AsyncSession, scope: ScopedSession
) -> dict[str, StoredNarration]:
    """Every capability's most recent sentence, keyed by capability id.

    Returns what was *written*, not what should be *shown*. Whether a stored
    sentence still describes the figure beside it is
    `domain.narration.describes`, and the separation is deliberate: this is a
    read, that is a rule, and a query that quietly dropped rows it judged stale
    would make the rule invisible to anybody reading either half.
    """
    rows = (await db.execute(_CURRENT, {"ws": str(scope.workspace_id)})).mappings().all()

    return {
        str(row["module"]): StoredNarration(
            module=str(row["module"]),
            prose=str(row["prose"]),
            prompt_version=str(row["prompt_version"]),
            narrated_at=row["created_at"],
            numerator=row["numerator"],
            denominator=row["denominator"],
            percentage=row["percentage"],
            page=row["page"],
            window=row["window"],
        )
        for row in rows
    }
