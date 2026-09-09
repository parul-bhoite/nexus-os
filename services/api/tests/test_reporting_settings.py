"""The assumptions every window is cut against, and what moving one costs.

`doc/13` §13, ADR 0025. Doc 05 §1 requires seven global assumptions before any
dashboard renders and **four of them had no home in the product** — so every
working drawer that has to print *"Window 19 Jul - 17 Aug"* was blocked on this.

The tests split in two. The pure ones assert that each setting's *"moves N
tiles"* sentence is derived from the registry and scoped to the company, because
a hand-counted N is the kind of claim nobody re-checks. The database ones assert
the restate rule: the stamp moves only when a number is actually restated, and
the audit row goes with it.
"""

from __future__ import annotations

import pytest

from app.domain.reporting import (
    BY_KEY,
    DEFAULT_DECIMALS,
    DEFAULT_FISCAL_YEAR_START_MONTH,
    DEFAULT_SCALE,
    DEFAULT_TIMEZONE,
    DEFAULT_WEEK_START,
    MAX_DECIMALS,
    SETTINGS,
    ReportingSettings,
    Scale,
    WeekStart,
    moves,
    restates_numbers,
)
from app.domain.scopes import Department

EVERYTHING = frozenset(Department)
THREE = frozenset({Department.MARKETING, Department.SALES, Department.FINANCE})


# ── The defaults ──────────────────────────────────────────────


def test_the_week_starts_on_sunday() -> None:
    """The GCC working week, and the one default where the ISO answer is wrong.

    A weekly figure cut on Monday splits a Gulf working week across two rows, so
    every weekly number this product shows would be wrong in a way that looks
    like a business problem rather than a configuration one.
    """
    assert DEFAULT_WEEK_START is WeekStart.SUNDAY


def test_every_setting_has_a_default_so_a_dashboard_can_render() -> None:
    """Nullable would push the decision into every reader, and the first reader
    to substitute its own default makes the assumption invisible again — which
    is the state this module was written to end."""
    settings = ReportingSettings()

    assert settings.fiscal_year_start_month == DEFAULT_FISCAL_YEAR_START_MONTH
    assert settings.week_start is DEFAULT_WEEK_START
    assert settings.timezone == DEFAULT_TIMEZONE
    assert settings.scale is DEFAULT_SCALE
    assert settings.decimals == DEFAULT_DECIMALS


def test_an_impossible_month_or_precision_is_refused_in_the_domain() -> None:
    """Bounded in three places on purpose — the request model, the dataclass and
    a database CHECK. The dataclass is the one a caller that is not a route has
    to get past."""
    with pytest.raises(ValueError, match="twelve months"):
        ReportingSettings(fiscal_year_start_month=13)

    with pytest.raises(ValueError, match="decimals"):
        ReportingSettings(decimals=MAX_DECIMALS + 1)


# ── What each setting says it changes ─────────────────────────


def test_every_setting_says_what_it_changes() -> None:
    """Every question in `question_bank.py` carries a `why`. A setting that
    restates numbers owes the customer the same sentence, and an unlabelled
    control on a screen that moves forty tiles is the opposite of that."""
    for setting in SETTINGS:
        assert setting.label
        assert setting.changes
        assert setting.changes[0].isupper(), setting.key


def test_the_number_of_tiles_moved_is_derived_and_never_written_down() -> None:
    """*"Moves 14 tiles"* is a claim, and a literal 14 is true only on the day
    somebody counts it. This is the same rule as the score denominator."""
    weekly = BY_KEY["week_start"]
    moved = moves(weekly, selected=EVERYTHING)

    assert moved, "the reporting week cuts weekly figures across four sources"
    assert all(any(source in c.required_sources for source in weekly.affects) for c in moved)


def test_a_company_is_only_told_about_departments_it_runs() -> None:
    """The same failure as a denominator counting departments they do not have.

    "Moves 40 tiles across seven departments" is true of the product and false
    of a company running three, and a sentence that is true of the product is
    not the sentence the customer is owed.
    """
    everything = moves(BY_KEY["week_start"], selected=EVERYTHING)
    three = moves(BY_KEY["week_start"], selected=THREE)

    assert len(three) < len(everything)
    assert {c.department for c in three} <= THREE


def test_presentation_moves_nothing_and_restates_nothing() -> None:
    """`184.6K` and `184,600` are the same number.

    Telling a founder that choosing thousands re-derived their revenue would be
    false, and logging it beside the three settings that really do restate
    figures would bury them.
    """
    for key in ("scale", "decimals"):
        setting = BY_KEY[key]
        assert moves(setting, selected=EVERYTHING) == ()
        assert not restates_numbers(setting)
        assert not setting.relabels, (
            "writing 184.6 as 184,600 cannot mislead anybody. That is the line"
            " between these two and the currency."
        )


def test_the_settings_that_restate_numbers_say_so() -> None:
    """Three recompute and one relabels, and both count.

    The fiscal year, the reporting week and the report timezone each change
    where a period is cut, so each changes figures somebody may already have
    acted on. **Currency changes none of them and still restates**: no
    arithmetic is redone and every figure in the product goes from rials to
    dirhams, which is why `Setting` carries `relabels` rather than
    `restates_numbers` reading `affects` alone.
    """
    restating = {s.key for s in SETTINGS if restates_numbers(s)}

    assert restating == {"currency", "fiscal_year_start_month", "week_start", "timezone"}
    assert moves(BY_KEY["currency"], selected=EVERYTHING) == (), (
        "it relabels every tile and recomputes none, so the sentence on the"
        " screen must not promise a re-derivation"
    )


def test_the_report_timezone_is_not_the_persona_timezone() -> None:
    """Two different facts that would collapse into one field if nobody said so.

    `persona.timezone` is per-user presentation — where the reader is. This is
    where a *day* ends for the whole company. A founder reading yesterday's
    dispatch from an airport does not want yesterday to move.
    """
    from app.ai.runtime.fields import FIELD_CATALOGUE

    assert "persona.timezone" in FIELD_CATALOGUE
    assert BY_KEY["timezone"].key == "timezone"
    assert "cut" in BY_KEY["timezone"].label.lower() or "cut" in BY_KEY["timezone"].changes


def test_scale_and_week_start_are_closed_lists() -> None:
    """Both are value-list CHECKs in migration 0027 and both are registered in
    `test_constraint_enum_parity`, which compares them to these enums on every
    run."""
    assert {s.value for s in Scale} == {"units", "thousands", "millions"}
    assert len({d.value for d in WeekStart}) == 7
