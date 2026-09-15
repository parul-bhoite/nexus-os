"""`set_config('nexus.workspace_id', …)` is how a request becomes a tenant.

Every row-level security policy in this database reads that GUC. Setting it is
therefore the single most security-critical line in the codebase, and `doc/12`
P10 asks for it to live in one place — `app/retrieval/`, behind
`scoped_connection` — so there is one function to audit rather than ten.

**Ten modules spelled it out; three still do, and this test names them.**

That is not a passing grade dressed up as a list. It is a ratchet: the rule is
enforced from today, so an eleventh site fails immediately, and the ten are
visible in source control rather than being something a future audit discovers.
The allowlist may only ever shrink — `test_the_allowlist_only_shrinks` asserts
the count, so removing a site is a one-line change and adding one is not
possible without editing a file that explains why you should not.

Seven were consolidated in one pass and now call `apply_workspace_scope` in
`app/retrieval/scoped.py`. The rest have different transaction shapes and were
left deliberately: `auth/service.py` sets it before a workspace exists,
`domain/audit.py` writes inside somebody else's transaction, and
`routes/companies.py` spans a registration that creates the workspace it then
scopes to. Routing those through one primitive is a real refactor with real
failure modes, and doing it badly would be worse than doing it late — a
`scoped_connection` that silently opens a second transaction would break
atomicity in exactly the places that most need it.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Final

APP = Path(__file__).resolve().parents[1] / "app"

# The only place that *should* set it.
SANCTIONED: Final = {"retrieval/scoped.py"}

# Everywhere that currently does and should not. **This list may only shrink.**
# Each entry is a module to route through `scoped_connection`, and the comment
# is why it has not been yet.
ALLOWED_FOR_NOW: Final[set[str]] = set()
"""**Empty, and it should stay that way.**

Ten modules once spelled these statements out. They now call
`apply_workspace_scope`, `apply_user_scope` or `apply_invitation_token_scope` in
`app/retrieval/scoped.py`, so there is one place to audit for each of the three
GUCs instead of ten near-identical strings that could drift apart with nothing
noticing."""

PATTERN: Final = re.compile(r"""set_config\(\s*['"]nexus\.""")


def _sites() -> set[str]:
    found = set()
    for path in APP.rglob("*.py"):
        # `encoding="utf-8"` is not optional. Without it `read_text` uses the
        # *locale* codepage, which on Windows is cp1252 — and this repository's
        # prose is full of em-dashes and curly quotes, so the read raises
        # `UnicodeDecodeError` and the containment ratchet fails to run at all.
        # It passes on a UTF-8 runner, which is the whole problem: the guard was
        # green in CI and unrunnable on a developer's machine.
        if PATTERN.search(path.read_text(encoding="utf-8")):
            # `as_posix()`, not `str()`. On Windows `str()` yields
            # `retrieval\scoped.py`, which matches neither `SANCTIONED` nor
            # `ALLOWED_FOR_NOW` — so the one sanctioned site was reported as an
            # unlisted offender *and* as missing from the sanctioned set, in the
            # same run. Both readings were wrong, and both looked alarming: the
            # ratchet appeared to have caught a tenancy violation in the very
            # module that exists to prevent them. `test_ai_boundary` already
            # normalises this way.
            found.add(path.relative_to(APP).as_posix())
    return found


def test_no_new_module_sets_the_scoping_guc() -> None:
    """The ratchet.

    An eleventh site fails here, at the point somebody adds it, rather than in
    an audit months later — which is how it reached ten.
    """
    unexpected = _sites() - SANCTIONED - ALLOWED_FOR_NOW
    assert not unexpected, (
        "These modules set `nexus.workspace_id` and are not on the list:\n  "
        + "\n  ".join(sorted(unexpected))
        + "\n\nSetting that GUC is how a request becomes a tenant — every RLS policy "
        "reads it. Route the work through `scoped_connection` in `app/retrieval/` "
        "instead. If you genuinely cannot, add it to ALLOWED_FOR_NOW with a comment "
        "saying why, and know that the list is meant to shrink."
    )


def test_the_allowlist_only_shrinks() -> None:
    """The allowlist reached zero. A stale entry is worse than none — it reads
    as a decision when it is a leftover — so this fails on both a module that
    still sets a GUC and an entry that no longer needs to be listed."""
    remaining = _sites() & ALLOWED_FOR_NOW
    assert not remaining, (
        f"{len(remaining)} modules still set a scoping GUC directly. The allowlist is "
        "empty and is meant to stay empty."
    )
    assert not (ALLOWED_FOR_NOW - _sites()), (
        "These are on the allowlist but no longer set the GUC — delete them from it:\n  "
        + "\n  ".join(sorted(ALLOWED_FOR_NOW - _sites()))
    )


def test_the_sanctioned_home_actually_sets_it() -> None:
    """If `scoped_connection` stopped setting the GUC, every policy would see an
    empty string and every scoped query would return nothing — which looks like
    "no data" rather than like a broken security primitive."""
    assert SANCTIONED <= _sites(), "app/retrieval/scoped.py must set the scoping GUC"
