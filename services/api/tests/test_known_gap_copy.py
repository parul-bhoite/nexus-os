"""`known_gaps` reaches a screen, so its `topic` has to be readable by a person.

## What went wrong

`context.known_gaps` is `{topic, unlocked_by}`, and **two producers fill it with
different kinds of string**:

- `context-personalization` (a model) — `schema.json` types `topic` as a bare
  `{"type": "string"}` with no guidance anywhere, so it emitted
  `brain.products_services` on one run and *"Products & services (detailed list
  of what is sold or delivered beyond the general profile)"* on the next.
- `connections.gaps_for` — `topic = tool.unlocks`, a full benefit sentence
  ending in a full stop: *"Reporting your real traffic and conversions instead
  of leaving the tile locked."*

The Ready screen joined them with `·` and appended a full stop, so a founder
finishing onboarding read:

    Still locked: brain.profile · brain.products_services · brain.brand_voice ·
    brain.assumptions · Reporting your real traffic and conversions instead of
    leaving the tile locked. · Reading your actuals against your budget without
    you exporting anything..

Raw column names, a marketing sentence, and a double stop — on the last screen
of setup, which is the first impression the product makes.

**Normalising in the server, not the browser**, for the reason `BlockCard`
already gives about `unlock`: one wording change should reach every surface,
and a map of field keys to labels held in a TSX file is a second place the
vocabulary lives.
"""

from __future__ import annotations

from app.domain.known_gaps import BRAIN_FIELD_LABELS, readable_gaps


def test_a_raw_field_key_is_given_the_label_a_person_would_use() -> None:
    """The defect as seen on screen. `brain.products_services` is a column
    name; it tells a founder nothing about what is missing."""
    gaps = readable_gaps(
        [{"topic": "brain.products_services", "unlocked_by": "Tell your workspace"}]
    )

    assert gaps[0]["topic"] == "Products and services"
    assert "brain." not in gaps[0]["topic"]


def test_every_brain_field_the_model_can_name_has_a_label() -> None:
    """Totality over the columns `company_brain` actually has.

    A key with no label falls through to the screen as a column name, which is
    exactly the defect. Asserted against the table rather than against a list
    kept here, so a new brain column fails this instead of leaking.
    """
    columns = (
        "profile",
        "products_services",
        "target_customers",
        "brand_voice",
        "goals",
        "competitors",
        "assumptions",
    )

    for column in columns:
        assert f"brain.{column}" in BRAIN_FIELD_LABELS, column
        label = BRAIN_FIELD_LABELS[f"brain.{column}"]
        assert label
        assert label[0].isupper(), f"{column}: {label!r} should read as a heading"
        assert "_" not in label


def test_a_sentence_from_the_tool_ledger_loses_its_full_stop() -> None:
    """`connections.gaps_for` writes `topic = tool.unlocks`, which is a whole
    sentence. The screen lists these as items, and an item that punctuates
    itself produces the double stop the founder saw."""
    gaps = readable_gaps(
        [
            {
                "topic": "Reporting your real traffic and conversions instead of "
                "leaving the tile locked.",
                "unlocked_by": "Connecting Google Analytics",
            }
        ]
    )

    assert not gaps[0]["topic"].endswith("."), gaps[0]["topic"]
    assert gaps[0]["topic"].startswith("Reporting your real traffic")


def test_a_description_the_model_wrote_is_left_alone() -> None:
    """The third kind of string, and the one that was already fine. Normalising
    must not rewrite prose a model wrote well — only the two shapes that are
    demonstrably wrong."""
    written = "Brand voice (how the company writes and presents itself)"
    gaps = readable_gaps([{"topic": written, "unlocked_by": "Upload two documents"}])

    assert gaps[0]["topic"] == written


def test_the_unlock_survives_because_the_screen_now_shows_it() -> None:
    """`unlocked_by` was carried through the whole pipeline and **never
    rendered** — the screen said "Each names its own unlock in your workspace",
    which is the product telling somebody to go and look for what it already
    had in its hand."""
    gaps = readable_gaps(
        [{"topic": "brain.brand_voice", "unlocked_by": "Uploading two pieces of your writing"}]
    )

    assert gaps[0]["unlocked_by"] == "Uploading two pieces of your writing"


def test_a_gap_with_no_unlock_is_dropped_rather_than_shown_as_a_dead_end() -> None:
    """`doc/04` §6 rule 1: a locked thing is a call to action. One with no
    action is a complaint, and the Ready screen is not the place for a list of
    things the product cannot do and cannot tell you how to fix."""
    gaps = readable_gaps(
        [
            {"topic": "brain.profile", "unlocked_by": ""},
            {"topic": "brain.goals", "unlocked_by": "Tell your workspace"},
        ]
    )

    assert [g["topic"] for g in gaps] == ["Goals"]


def test_malformed_entries_are_skipped_rather_than_crashing_the_last_screen() -> None:
    """The model's output reaches this. A missing key or a non-string must not
    take down the screen that says setup succeeded."""
    gaps = readable_gaps(
        [
            {"topic": "brain.goals", "unlocked_by": "Tell your workspace"},
            {"unlocked_by": "no topic at all"},
            "not a mapping at all",
            {"topic": 42, "unlocked_by": "a number"},
        ]
    )

    assert [g["topic"] for g in gaps] == ["Goals"]


def test_the_same_gap_named_twice_is_listed_once() -> None:
    """Both producers can name the same thing — the model from the brain side
    and the ledger from the tool side — and a list that repeats itself reads as
    a rendering fault."""
    gaps = readable_gaps(
        [
            {"topic": "brain.goals", "unlocked_by": "Tell your workspace"},
            {"topic": "Goals", "unlocked_by": "Something else"},
        ]
    )

    assert len(gaps) == 1
    assert gaps[0]["unlocked_by"] == "Tell your workspace", "the first wins"


def test_nothing_missing_produces_an_empty_list_not_a_sentence() -> None:
    """The screen decides what to say about "nothing is missing"; this decides
    what is missing. A function that returned copy here would be a second place
    the wording lives."""
    assert readable_gaps([]) == []
