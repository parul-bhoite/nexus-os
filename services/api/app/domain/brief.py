"""The morning brief: what was found, ranked by what it cost.

ADR 0029. The first region of the common surface, and the one with the most
ways to quietly become something else.

## A ranking, not a recommendation

Order is points lost, descending — arithmetic the calculator already did.
`Check.evidence` is specified as *what was observed* and never as advice, and
this is the highest-traffic place that distinction gets tested: "0 of 37 images"
is a finding, "add alt text" is guidance nobody computed. The brief may say what
a check is **worth**, because the weight is a number in the code. It may not say
what to do about it.

**The check's own label is used verbatim**, not negated. A first draft of the
design wrote *"Not served over HTTPS"* for `seo.https`, which reads well and
generalises to nothing: the same transformation turns "Page has a title" into
"Not Page has a title". The label states the check, the item states that it
failed, and no sentence is manufactured in between.

## Found, never changed

Nothing re-crawls (M32), so there is no baseline. A brief headed with a date
range, or an item reading "new this week", would claim a comparison nobody made —
the failure `SKILL.md` forbids when it says never to call a delta flat. When
re-crawling lands, items gain a movement and this docstring is the thing to
read first.

## Three states, and two of them must not be mistakable

`FINDINGS` is the ranking. `ALL_HELD` is full marks **and its own limits in the
same breath**, because a brief saying "nothing needs you" would be a claim about
a business drawn from checks on one web page. `NOT_MEASURED` exists because an
audit that never ran must not read as an audit that found nothing — the region is
never hidden and never shows a zero (I10).

## No model, ever

This renders at the top of every page load for every workspace. A model-backed
brief could be empty, refused, or billed on a page somebody opened by accident,
and ADR 0011 makes a missing API key a supported state rather than a degraded
one. The copy below is templated and reads more mechanically than written prose
would; that is the trade, and it was made deliberately.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from app.grounding.compute import Computation


class BriefState(StrEnum):
    FINDINGS = "findings"
    ALL_HELD = "all_held"
    NOT_MEASURED = "not_measured"


class ItemKind(StrEnum):
    """Two kinds today, and the order between them is not cosmetic."""

    UNMEASURED = "unmeasured"
    """A capability that should hold a figure and does not.

    **Sorts above every failure**, whatever the points. A missing measurement
    qualifies every number beneath it — a reader who does not know that half the
    page could not be scored will read the other half as the whole picture — and
    a low score qualifies nothing.
    """

    CHECK_FAILED = "check_failed"
    """One check that did not hold, carrying the weight it cost."""


@dataclass(frozen=True, slots=True)
class BriefItem:
    kind: ItemKind
    headline: str
    """The check's own label, verbatim. Never negated, never rewritten."""

    detail: str
    """`Check.evidence` — what was observed. Never advice."""

    cost: int
    """Points this check was worth. `0` for `UNMEASURED`, where nothing was
    scored at all and a number would be inventing one."""

    check_id: str
    capability_id: str
    method: str
    """The calculator that produced the weight, so a disputed item traces back
    the same way a disputed figure does."""


@dataclass(frozen=True, slots=True)
class Brief:
    state: BriefState
    items: tuple[BriefItem, ...]
    points_held: int
    points_total: int
    checks_passed: int
    checks_total: int
    measured_on: str
    """ISO date of the fetch these findings came from. Empty **only** when
    `state` is `NOT_MEASURED` — a date on an unmeasured brief would be the
    clearest possible version of the lie this region exists to avoid."""

    message: str
    """Server-authored copy for the state, never empty.

    `BlockCard` states the rule for `unlock` and it holds here: the sentence
    comes from the API so one wording change reaches every surface, and so a
    screen cannot ship with the space drawn and the copy forgotten.
    """

    @property
    def points_lost(self) -> int:
        return self.points_total - self.points_held


_HELD: Final = (
    "Every check held on the page as fetched on {date}. "
    "That is not a clean bill of health, and this is the part worth reading: "
    "the audit reads one page. It does not look at keywords, traffic, "
    "conversions or pipeline, and {unobserved} capabilities are not built yet, "
    "so most of the business is unobserved rather than healthy."
)

_ABSENT: Final = (
    "No page has been fetched for this workspace, so there is nothing to "
    "report — which is not the same as nothing being wrong. The audit runs "
    "once a website is added and crawled."
)

_FOUND: Final = (
    "{failed} of {total} checks did not hold on the page as fetched on "
    "{date}, costing {lost} of {points} points."
)


def _items_for(computation: Computation) -> list[BriefItem]:
    return [
        BriefItem(
            kind=ItemKind.CHECK_FAILED,
            headline=check.label,
            detail=check.evidence,
            cost=check.weight,
            check_id=check.id,
            capability_id=computation.capability_id,
            method=str(computation.trace["method"]),
        )
        for check in computation.score.checks
        if not check.passed
    ]


def compose(
    computations: tuple[Computation, ...],
    *,
    expected: frozenset[str],
    unobserved: int,
) -> Brief:
    """Assemble the brief from what was computed for this reader.

    `computations` is what actually produced a figure; `expected` is every
    capability this reader can reach that *should* have. The difference is the
    `UNMEASURED` band, and computing it here rather than in the route is what
    stops a capability silently disappearing from the brief when its calculator
    starts returning `None`.

    **Scoped by the caller, not here.** Both arguments arrive already filtered
    to what the reader may see (ADR 0029), so this function has no permission
    logic of its own to drift out of step with the route's.

    `unobserved` is coverage's `not_built` — the only number the copy borrows
    from outside, and only so the `ALL_HELD` state can state its own limits in
    the same sentence as the good news.
    """
    measured = {computation.capability_id for computation in computations}

    # Missing measurements first, at any cost, because they qualify everything
    # below them. Sorted by id so the order is stable between requests rather
    # than following whatever the set happened to iterate as.
    items: list[BriefItem] = [
        BriefItem(
            kind=ItemKind.UNMEASURED,
            headline="This could not be measured",
            detail="Nothing scored it on the most recent fetch.",
            cost=0,
            check_id="",
            capability_id=capability_id,
            method="",
        )
        for capability_id in sorted(expected - measured)
    ]

    failures = [item for c in computations for item in _items_for(c)]
    # Points lost descending, then by check id so a tie is resolved the same way
    # every time. An unstable order would make the brief look rewritten on every
    # reload while saying exactly the same thing.
    failures.sort(key=lambda item: (-item.cost, item.check_id))
    items.extend(failures)

    points_total = sum(c.score.max_score for c in computations)
    points_held = sum(c.score.score for c in computations)
    checks_total = sum(len(c.score.checks) for c in computations)
    checks_passed = sum(c.checks_passed for c in computations)

    if not computations:
        # Not "everything passed with a denominator of zero". Nothing was
        # looked at, and the totals stay zero *with a state that says so* —
        # which is the distinction I10 exists to keep.
        return Brief(
            state=BriefState.NOT_MEASURED,
            items=(),
            points_held=0,
            points_total=0,
            checks_passed=0,
            checks_total=0,
            measured_on="",
            message=_ABSENT,
        )

    measured_on = min(c.measured_at for c in computations).date().isoformat()

    if not failures:
        return Brief(
            state=BriefState.ALL_HELD,
            items=tuple(items),
            points_held=points_held,
            points_total=points_total,
            checks_passed=checks_passed,
            checks_total=checks_total,
            measured_on=measured_on,
            message=_HELD.format(date=measured_on, unobserved=unobserved),
        )

    return Brief(
        state=BriefState.FINDINGS,
        items=tuple(items),
        points_held=points_held,
        points_total=points_total,
        checks_passed=checks_passed,
        checks_total=checks_total,
        measured_on=measured_on,
        message=_FOUND.format(
            failed=checks_total - checks_passed,
            total=checks_total,
            date=measured_on,
            lost=points_total - points_held,
            points=points_total,
        ),
    )
