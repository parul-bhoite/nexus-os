"""`PageSignals` must survive a round trip through JSONB, field by field.

Written before the codec, because the failure mode it guards is invisible. A
field dropped in serialisation does not raise — it comes back as its dataclass
default, which for `has_canonical` is `False` and for `image_count` is `0`. The
calculator then scores a page that has a canonical tag as though it did not,
and the number is wrong in a way no exception and no eyeball catches. So the
test iterates `dataclasses.fields` rather than listing what it remembers:
**a thirtieth field added to `PageSignals` fails this build** instead of being
silently discarded.

Two fields are deliberately not stored, and both exclusions are named in
`SIGNALS_NOT_STORED` rather than left implicit:

`text_sample` — already persisted as `pages[].text` by `save_crawl`, and it is
untrusted page content. A second copy is a second thing the M12 boundary has to
know about.

`emails` — addresses scraped from a public page. `score_brand` uses only
`bool(signals.emails)` and `len(signals.emails)` (`calculators/audit.py:109`
and `:111`), never an address itself, so the codec stores a count and rebuilds
a placeholder tuple of that length. Both predicates stay exactly correct and no
personal data lands in a table that has no retention rule. `social_profiles`
*is* stored, because `audit.py:119` renders it into evidence text — those are
public company profile URLs, not personal data.
"""

from __future__ import annotations

import dataclasses
import json

from app.domain.page_signals import (
    SIGNALS_NOT_STORED,
    PageSignals,
    signals_from_json,
    signals_to_json,
)


def populated() -> PageSignals:
    """Every field set to something that is **not** its default.

    That is the whole point: a field that serialises to its default is
    indistinguishable from a field that was dropped, so a fixture full of
    zeroes and empty tuples would pass while proving nothing.
    """
    return PageSignals(
        url="https://muscat-marine.om/services",
        is_https=True,
        title="Marine engine repair in Muscat",
        title_length=31,
        meta_description="Dry-dock maintenance and engine overhaul for Omani fleets.",
        meta_description_length=57,
        h1_texts=("Marine engine repair",),
        h2_texts=("Dry dock", "Overhaul", "Emergency call-out"),
        has_viewport_meta=True,
        has_canonical=True,
        canonical_url="https://muscat-marine.om/services",
        has_robots_meta=True,
        robots_blocks_indexing=True,
        has_structured_data=True,
        has_open_graph=True,
        declared_language="en",
        image_count=12,
        images_with_alt=9,
        internal_link_count=24,
        external_link_count=3,
        emails=("hello@muscat-marine.om", "ops@muscat-marine.om"),
        has_phone=True,
        social_profiles=("linkedin", "instagram"),
        word_count=812,
        html_bytes=48_112,
        script_count=7,
        stylesheet_count=3,
        inline_style_count=2,
        text_sample="We service and repair commercial marine engines.",
    )


def test_every_field_survives_the_round_trip_or_is_a_named_exclusion() -> None:
    original = populated()
    restored = signals_from_json(signals_to_json(original))

    for field in dataclasses.fields(PageSignals):
        if field.name in SIGNALS_NOT_STORED:
            continue
        assert getattr(restored, field.name) == getattr(original, field.name), (
            f"{field.name} did not survive the round trip. Either serialise it, "
            f"or add it to SIGNALS_NOT_STORED with a reason — a field that comes "
            f"back as its default is a wrong number, not a missing one."
        )


def test_the_exclusions_are_the_two_we_decided_on() -> None:
    """A guard on the exclusion list itself.

    Without this, `SIGNALS_NOT_STORED` is a place to quietly hide a field that
    turned out to be awkward to serialise, and the test above would keep
    passing while the tile lost inputs.
    """
    assert SIGNALS_NOT_STORED == frozenset({"text_sample", "emails"})


def test_tuples_come_back_as_tuples() -> None:
    """JSON has only lists.

    `PageSignals` declares `tuple[str, ...]` on a frozen slots dataclass, and a
    list in that slot is a type lie that `len()` never catches and `mypy` never
    sees, because the object was built at runtime from a database row.
    """
    restored = signals_from_json(signals_to_json(populated()))
    assert isinstance(restored.h1_texts, tuple)
    assert isinstance(restored.h2_texts, tuple)
    assert isinstance(restored.social_profiles, tuple)
    assert isinstance(restored.emails, tuple)


def test_no_scraped_address_is_ever_stored() -> None:
    """The privacy claim, asserted against the serialised payload itself.

    Not against the dataclass — against the thing that goes into the column.
    `@` is a crude test and that is deliberate: it catches an address that
    arrives through a field nobody thought about, including one added later.
    """
    payload = signals_to_json(populated())
    flattened = json.dumps(payload)
    assert "@" not in flattened, f"a scraped address reached the payload: {flattened[:200]}"
    assert "emails" not in payload


def test_the_email_predicates_the_calculator_uses_still_work() -> None:
    """`bool()` and `len()` are the only two things `score_brand` asks.

    So the placeholder tuple has to answer both exactly as the real one did,
    or the "contact details present" check silently flips for every site.
    """
    original = populated()
    restored = signals_from_json(signals_to_json(original))

    assert bool(restored.emails) is bool(original.emails)
    assert len(restored.emails) == len(original.emails)


def test_a_page_with_no_contact_details_round_trips_as_having_none() -> None:
    """The other half of the count, which the populated fixture cannot show.

    If the codec defaulted a missing count to something truthy, every site
    without an email would start passing the contact check.
    """
    bare = dataclasses.replace(populated(), emails=())
    restored = signals_from_json(signals_to_json(bare))

    assert restored.emails == ()
    assert bool(restored.emails) is False


def test_the_payload_is_json_serialisable() -> None:
    """It is going into a JSONB column through asyncpg, which will not accept a
    tuple, a dataclass or a `None` key. Assert it here rather than discovering
    it in a migration-time insert."""
    json.dumps(signals_to_json(populated()))
