"""What the Brain is still missing, in words a founder can act on.

`context.known_gaps` is filled by two producers with different habits, and the
Ready screen renders it. Without a normaliser the founder reads a mix of
database column names, model prose and marketing sentences joined by a middle
dot — which is what they did read, on the last screen of setup:

    Still locked: brain.profile · brain.products_services · brain.brand_voice ·
    brain.assumptions · Reporting your real traffic and conversions instead of
    leaving the tile locked. · Reading your actuals against your budget without
    you exporting anything..

**In the server, not the browser.** `BlockCard` already states the rule for
`unlock`: the sentence comes from the API so one wording change reaches every
surface, and so a screen cannot ship with the space drawn and the copy
forgotten. A map of field keys to labels held in a TSX file would be a second
place this vocabulary lives.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any, Final

BRAIN_FIELD_LABELS: Final[dict[str, str]] = {
    "brain.profile": "What the company does",
    "brain.products_services": "Products and services",
    "brain.target_customers": "Who buys from you",
    "brain.brand_voice": "Brand voice",
    "brain.goals": "Goals",
    "brain.competitors": "Competitors",
    "brain.assumptions": "Assumptions we are working from",
}
"""One label per `company_brain` column the personalisation can name.

`schema.json` types `known_gaps[].topic` as a bare string with no guidance, so
the model fills it however it likes — a column name on one run, a sentence on
the next. Guidance has been added to `SKILL.md`, but a prompt is a request and
this is the guarantee: a key that reaches here leaves as a phrase.

`tests/test_known_gap_copy.py` asserts this covers every column, so adding one
to `company_brain` fails the build rather than leaking `brain.new_column` onto
somebody's screen.
"""


def _readable(topic: str) -> str:
    """One topic, as a list item rather than as a sentence or a column name."""
    labelled = BRAIN_FIELD_LABELS.get(topic)
    if labelled is not None:
        return labelled

    # `connections.gaps_for` sets `topic = tool.unlocks`, which is written as a
    # full sentence — "Reporting your real traffic and conversions instead of
    # leaving the tile locked." The screen lists these, and an item that
    # punctuates itself is where the double stop came from.
    #
    # Only the trailing stop, and only one. A topic that legitimately ends in a
    # question mark or an ellipsis is somebody's deliberate wording, and this is
    # tidying a list, not rewriting prose.
    return topic.rstrip().removesuffix(".")


def readable_gaps(raw: Iterable[Any]) -> list[dict[str, str]]:
    """The gaps worth showing, each with the action that closes it.

    Three things happen here, and each is a defect that reached a screen:

    **Field keys become phrases.** See `BRAIN_FIELD_LABELS`.

    **Sentences lose their trailing stop**, because they are being listed.

    **A gap with no unlock is dropped.** `doc/04` §6 rule 1 makes a locked
    thing a call to action; one with no action is a complaint, and the screen
    that says setup worked is the wrong place for a list of things the product
    cannot do and cannot tell you how to fix. It is also the reason the caller
    can now render `unlocked_by` at all — it was carried through the entire
    pipeline and never shown, under a sentence telling the founder that each
    gap "names its own unlock in your workspace", which is the product asking
    somebody to go and find what it was already holding.

    Malformed entries are skipped rather than raised on. This runs on the last
    screen of onboarding, and a model's stray output must not turn "your
    workspace is ready" into a stack trace.
    """
    gaps: list[dict[str, str]] = []
    seen: set[str] = set()

    for entry in raw:
        if not isinstance(entry, Mapping):
            continue
        topic = entry.get("topic")
        unlock = entry.get("unlocked_by")
        if not isinstance(topic, str) or not isinstance(unlock, str):
            continue
        if not topic.strip() or not unlock.strip():
            continue

        readable = _readable(topic.strip())
        # De-duplicated on the *readable* form: the two producers can name the
        # same thing differently, and `brain.goals` and `Goals` are one gap.
        key = readable.casefold()
        if key in seen:
            continue
        seen.add(key)
        gaps.append({"topic": readable, "unlocked_by": unlock.strip()})

    return gaps
