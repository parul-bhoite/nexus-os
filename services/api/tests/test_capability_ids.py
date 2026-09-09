"""One id space, and the guards that keep it joined.

`doc/13` §5. The question bank has declared, since P7, the capability that
consumes each of its twenty-nine questions — and until this file existed nothing
checked that the declared consumer *was* a capability. Q33's guard proved a
question named **a string**. These prove the string names something.

The failure that makes this worth a file of its own: it looked like a working
feature. `consumers_of()` returned `()` for every fact, the review gate ranked
every fact equally, and no test failed — because a mapping between two
namespaces that share no members is empty rather than wrong.
"""

from __future__ import annotations

import pytest

from app.domain.dashboards import DIRECTORS
from app.domain.question_bank import BY_DEPARTMENT as QUESTIONS_BY_DEPARTMENT
from app.domain.registry import (
    BY_ID,
    CAPABILITIES,
    CapabilityKind,
    CapabilityRegistryError,
    _validate,
    canonical_id,
)
from app.domain.scopes import Department

SYNTHESISES_OTHER_CAPABILITIES = {
    "executive.department_briefings",
    "marketing.content_calendar",
}
"""The two offerings whose sources are empty because they read other
capabilities rather than any system. Module-level so adding a third is a visible
edit rather than a line inside a test nobody re-reads."""


def _displays_rather_than_computes(capability_id: str) -> bool:
    """Step D's two sections, which need no source because they compute nothing.

    Setup reads the founder's answers back and the Watchlist quotes one with
    what will test it. Neither calculates, so neither has an input to wait for —
    and declaring one made Setup render `locked` on *"needs your setup
    answers"*, an instruction to supply the thing it exists to show back.

    An empty Setup tab is a fact about the answers, never about our access.
    """
    return capability_id.endswith((".setup", ".watchlist"))

PREFIXES = {
    Department.EXECUTIVE: "executive",
    Department.MARKETING: "marketing",
    Department.SALES: "sales",
    Department.FINANCE: "finance",
    Department.OPERATIONS: "operations",
    Department.HR: "people",
    Department.STRATEGY: "strategy",
}


# ── The join itself ───────────────────────────────────────────


def test_every_consumed_by_names_a_capability_in_the_registry() -> None:
    """Q33's missing half.

    A question exists because something reads its answer. Proving the question
    names a string proves nothing about whether that something exists, and a
    founder asked twenty-nine questions deserves better than a namespace that
    resolves to nothing.
    """
    for questions in QUESTIONS_BY_DEPARTMENT.values():
        for question in questions:
            assert question.consumed_by in BY_ID, (
                f"{question.key} is consumed by {question.consumed_by!r}, which is not a capability"
            )


def test_every_answered_question_is_reachable_from_its_capability() -> None:
    """The reverse direction, which is what a tile actually needs.

    A tile saying *"you told us a lead is X"* has to get from the capability to
    the answer. That is `consumes_facts`, and it is inverted from the bank
    rather than typed, so this asserts the inversion lost nothing.
    """
    declared = {
        question.key for questions in QUESTIONS_BY_DEPARTMENT.values() for question in questions
    }
    reached = {key for capability in CAPABILITIES for key in capability.consumes_facts}

    assert reached == declared, f"unreachable answers: {sorted(declared - reached)}"


def test_question_keys_are_globally_unique() -> None:
    """Why `consumes_facts` can hold a bare key rather than a department pair.

    Answers are stored per `(department, question_key)`. If two departments ever
    asked a question under one key, a capability declaring the bare key would
    read whichever row came back first — so either the keys stay unique or this
    field grows a department. Today they are unique, and this is the tripwire.
    """
    keys = [
        question.key for questions in QUESTIONS_BY_DEPARTMENT.values() for question in questions
    ]
    assert len(keys) == len(set(keys))


# ── The shape of an id ────────────────────────────────────────


def test_every_capability_is_namespaced_by_its_department() -> None:
    """ADR 0020: *"two departments will eventually both have a forecast, and a
    bare name makes the collision invisible."*

    Two already do. `executive.risk_register` and `strategy.risk_register` are
    both called "Risk register" in doc 05; `operations.capacity_utilisation` and
    `people.capacity_utilisation` are one offering surfaced on two pages.
    """
    for capability in CAPABILITIES:
        assert capability.id.startswith(f"{PREFIXES[capability.department]}.")


def test_people_is_prefixed_people_and_not_hr() -> None:
    """The department enum says `hr`; the question bank, doc 08 and the nav all
    say People. The bank is what the ids have to match, so `people` wins — and
    a mismatch here is the one that breaks the join silently."""
    people = [c for c in CAPABILITIES if c.department is Department.HR]

    assert people, "the People director has capabilities"
    assert all(c.id.startswith("people.") for c in people)


def test_no_capability_claims_a_doc05_number_that_no_offering_has() -> None:
    """The other direction from `test_every_offering_has_exactly_one_capability`.

    Together they close the loop: an offering with no canonical name fails at
    import, and a canonical name pointing at a paragraph that no longer exists
    fails here.
    """
    real = {offering.id for director in DIRECTORS for offering in director.offerings}
    claimed = {c.doc05_id for c in CAPABILITIES if c.doc05_id}

    assert claimed <= real, f"orphaned doc 05 ids: {sorted(claimed - real)}"


def test_canonical_id_resolves_every_offering() -> None:
    """What a route calls to get from a tile to its capability."""
    for director in DIRECTORS:
        for offering in director.offerings:
            assert canonical_id(offering.id) in BY_ID


# ── What a capability must declare ────────────────────────────


def test_every_capability_declares_a_source_or_a_fact() -> None:
    """A capability needing neither a source nor an answer needs nothing, which
    means it computes nothing.

    Two offerings were already in that position — doc 05 2.7 Department
    Briefings and 3.5 the content calendar — and both have empty sources because
    they read other capabilities rather than any system. Neither consumes a
    fact, so they are named here rather than let through a hole in the rule: the
    day either is built it will declare what it synthesises, and the exception
    list is where that gets noticed.
    """
    for capability in CAPABILITIES:
        if capability.id in SYNTHESISES_OTHER_CAPABILITIES:
            continue
        if _displays_rather_than_computes(capability.id):
            continue
        assert capability.required_sources or capability.consumes_facts, (
            f"{capability.id} needs nothing, so it can compute nothing"
        )


def test_a_rule_is_never_scored_and_never_counted() -> None:
    """`executive.recommendation_filter` reads two Strategy answers and
    suppresses recommendations across every director. It renders nothing, so it
    cannot be scored, and it is not a capability a customer acquires, so it
    cannot sit in the completeness denominator."""
    rules = [c for c in CAPABILITIES if c.kind is CapabilityKind.RULE]

    assert rules, "the filter is a rule, and rules must stay expressible"
    assert not any(c.scoreable for c in rules)


def test_reachable_implies_implemented() -> None:
    """A route cannot serve a calculation that does not exist. The two flags
    exist because they came apart in the other direction — implemented and not
    reachable — and that gap is real today."""
    for capability in CAPABILITIES:
        if capability.reachable:
            assert capability.implemented


# ── The guard, proved by breaking it ──────────────────────────


def test_the_validator_rejects_a_dangling_consumer() -> None:
    """A spec that passes against a broken table certifies nothing.

    So: remove the capability a question declares, and the validator must
    refuse. This is the same method the retrieval evals use — plant the defect
    the guard names and watch it go red.
    """
    without_forecast = tuple(c for c in CAPABILITIES if c.id != "sales.forecast")

    with pytest.raises(CapabilityRegistryError, match="disqualifiers"):
        _validate(without_forecast)


def test_the_validator_rejects_a_wrongly_namespaced_id() -> None:
    """The collision ADR 0020 was written about, caught at import."""
    from dataclasses import replace

    misfiled = tuple(
        replace(c, id="forecast") if c.id == "sales.forecast" else c for c in CAPABILITIES
    )

    with pytest.raises(CapabilityRegistryError, match="prefixed"):
        _validate(misfiled)


def test_the_validator_rejects_a_duplicate_id() -> None:
    """Two entries under one name is how the wrong one gets read — the reason
    `BY_DEPARTMENT` is aliased on import in `routes/dashboards.py`."""
    from dataclasses import replace

    collided = tuple(
        replace(c, id="sales.forecast") if c.id == "sales.pipeline_board" else c
        for c in CAPABILITIES
    )

    with pytest.raises(CapabilityRegistryError, match="duplicate"):
        _validate(collided)
