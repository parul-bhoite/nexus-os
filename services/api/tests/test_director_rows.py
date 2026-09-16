"""What each department's one line says, and why four states rather than two.

`doc/14` step 6, and it answers the question that document left open: what a row
says for a department holding nothing.

`doc/13` §7's rule, applied a level up — **each state has to tell the reader
something different to do.** Two states that produce the same sentence should be
one state, and a state whose sentence is wrong is worse than no row. That is
what these assert: not that copy exists, but that the copy sent is the copy that
is true for the department it describes.

The failure that matters and would never look like a bug: telling somebody to
answer questions for a department where the questions are all answered and the
capabilities are waiting on an accounting system. They go looking for a form
that is not there, and conclude the product is broken rather than early.
"""

from __future__ import annotations

from app.domain.departments import label_for
from app.domain.director_rows import DirectorRow, RowState, compose
from app.domain.registry import TILES
from app.domain.scopes import Department
from app.grounding.compute import CRAWL_AUDITS

EVERY = list(Department)
MEASURING = frozenset(CRAWL_AUDITS)


def _rows(
    departments: list[Department] = EVERY,
    measuring: frozenset[str] = MEASURING,
    unanswered: dict[Department, int] | None = None,
) -> dict[Department, DirectorRow]:
    rows = compose(
        departments=departments,
        measuring=measuring,
        unanswered=unanswered if unanswered is not None else {},
        label=label_for,
    )
    return {row.department: row for row in rows}


def _ordered(unanswered: dict[Department, int] | None = None) -> list[DirectorRow]:
    return list(
        compose(
            departments=EVERY,
            measuring=MEASURING,
            unanswered=unanswered if unanswered is not None else {},
            label=label_for,
        )
    )


# ── Each state says its own thing ─────────────────────────────


def test_a_department_that_measures_says_so_and_nothing_else() -> None:
    row = _rows()[Department.MARKETING]

    assert row.state is RowState.MEASURING
    assert "2 of this department's capabilities produce a figure" in row.line


def test_a_department_with_open_questions_is_offered_the_questions() -> None:
    row = _rows(unanswered={Department.SALES: 4})[Department.SALES]

    assert row.state is RowState.ANSWERABLE
    assert "4 questions open here, and nothing measured yet." == row.line


def test_a_department_with_nothing_open_names_what_it_is_waiting_on() -> None:
    """**The failure this exists to prevent.** Saying "answer some questions"
    here sends a founder looking for a form that is not there, and they conclude
    the product is broken rather than early."""
    row = _rows()[Department.FINANCE]

    assert row.state is RowState.WAITING
    assert "your accounting system" in row.line
    assert "question" not in row.line


def test_the_largest_blocker_is_named_as_something_we_build() -> None:
    """Operations' commonest requirement is `ops_layer` — projects and tasks
    *inside* NEXUS. The row says so rather than implying a connection would
    help, which is ADR 0030's finding reaching the customer."""
    row = _rows()[Department.OPERATIONS]

    assert "projects and tasks in NEXUS" in row.line


def test_measuring_beats_open_questions_when_both_are_true() -> None:
    """A department can measure *and* have questions open — Marketing does. The
    figure is the more useful sentence, and offering both would make the row two
    sentences long for no gain."""
    row = _rows(unanswered={Department.MARKETING: 5})[Department.MARKETING]

    assert row.state is RowState.MEASURING


# ── Copy that cannot be empty or wrong ────────────────────────


def test_every_row_carries_a_sentence() -> None:
    """Server-authored and never empty, the same rule `unlock` follows: a row
    cannot ship with the space drawn and the sentence forgotten."""
    for row in _rows().values():
        assert row.line.strip()
        assert row.line.endswith(".")


def test_no_row_promises_that_connecting_something_would_switch_it_on() -> None:
    """ADR 0030's rule at row level. Connecting a source unlocks nothing while
    the capabilities behind it have no calculator, so a line may say what is
    needed and never what would follow."""
    for row in _rows().values():
        assert "unlock" not in row.line.lower()
        assert "will work" not in row.line.lower()


def test_singulars_and_plurals_agree_with_their_counts() -> None:
    one = _rows(unanswered={Department.SALES: 1})[Department.SALES]

    assert "1 question open" in one.line


def test_the_row_that_measures_comes_first(  # noqa: D401
) -> None:
    """A summary leads with the only row worth opening. Ordered by state, then
    by display name — sorting on the enum value looks alphabetical and is not,
    because `hr` renders as "People" and landed between Finance and Marketing."""
    rows = _ordered(unanswered=dict.fromkeys(Department, 4))

    assert rows[0].department is Department.MARKETING
    answerable = [label_for(r.department) for r in rows if r.state is RowState.ANSWERABLE]
    assert answerable == sorted(answerable)


def test_the_answerable_line_does_not_repeat_the_regions_argument() -> None:
    """**Found by looking at a real workspace.** The first draft appended
    "answering changes what these capabilities will count, not whether they
    exist yet" to every row, and five of seven rows carried the identical
    twenty-word clause — noise that buried the one row saying something
    different. The claim is made once, in the region directly above."""
    lines = [r.line for r in _ordered(unanswered=dict.fromkeys(Department, 5))]
    answerable = [line for line in lines if "questions open here" in line]

    assert len(answerable) > 1
    assert all(len(line) < 60 for line in answerable), answerable


# ── Determinism and scope ─────────────────────────────────────


def test_the_blocker_is_the_same_between_calls() -> None:
    """`Counter.most_common` does not order ties, so a tie would give the same
    workspace a different sentence on each request for no reason a reader could
    see."""
    assert [r.line for r in _rows().values()] == [r.line for r in _rows().values()]


def test_only_the_departments_passed_in_get_a_row() -> None:
    """The filtering is the caller's — by what the company runs and what the
    reader may reach — so a row for a department the panel does not list would
    be a disclosure by a different route."""
    rows = _rows(departments=[Department.MARKETING])

    assert list(rows) == [Department.MARKETING]


def test_the_empty_state_is_unreachable_today_and_kept_anyway() -> None:
    """`doc/14` left this open. Every department in the registry holds tiles, so
    nothing reaches `EMPTY` — and it stays because the alternative to a sentence
    admitting there is nothing is a row with no sentence at all, which is the
    one thing worse.

    Asserted as the reason rather than the outcome: if a department ever holds
    no tiles, this fails and somebody reads the paragraph above.
    """
    assert all(any(c.department is department for c in TILES) for department in Department), (
        "a department now holds no tiles — the EMPTY state is live, and its copy needs reading"
    )
    assert all(row.state is not RowState.EMPTY for row in _rows().values())
