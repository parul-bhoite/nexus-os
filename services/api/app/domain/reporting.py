"""The reporting settings, and what each one moves.

`doc/13` §13 and ADR 0025. Doc 05 §1 lists seven global assumptions *"required
before any dashboard renders"* — company profile, currency, fiscal year start,
timezone, reporting week definition, primary language, and role visibility.
**Four of them had no home in the product.** `workspace` carried country and
reporting currency; the fiscal year start existed only as an onboarding answer;
and the reporting week, the report timezone and the units were nowhere at all.

That is why this module is part of the dashboard rather than of an admin screen.
ADR 0025 fixed each tile's window and requires it stated in the working:

    Window    19 Jul - 17 Aug
    Settings  fiscal week starts Sunday · OMR · rounded to 0.1

A window cannot be stated from settings that do not exist, so every drawer in
`doc/13` §6 waits on this.

## Two rules

**Each setting says what it changes, and the count is derived.** The copy on the
screen is *"moves 14 tiles across Marketing, Sales and Operations"*, and a
hand-written 14 is the kind of number that is true the day somebody counts it.
`moves()` computes it from the capability registry, against the departments the
company actually runs — a company without Operations is not told that a setting
moves Operations tiles.

**Changing one restates numbers, so it is logged and stamped.** `doc/13` §10's
restate rule. `reporting_changed_at` is the stamp every later derivation is
compared against; the audit row says who changed it. Marking the affected tiles
stale and re-deriving them lands with the tiles themselves (P14) — there is
nothing to mark today, and writing the stamp now is what makes that possible
later without a second migration.

**Presentation is not computation.** Scale and decimals change how a figure is
written and never what it is, so `moves()` returns nothing for them and the copy
says so. Conflating the two would tell a founder that choosing thousands
restated their revenue.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from app.domain.dashboards import Source
from app.domain.registry import TILES, Capability
from app.domain.scopes import Department


class WeekStart(StrEnum):
    """Which day a reporting week begins on.

    Seven values rather than a boolean or an integer, because the question is
    asked in words on the screen and answered in words in the working — *"weeks
    start Sunday"* — and an integer would need a mapping in every place that
    prints it.

    **The default is Sunday**, which is the GCC working week and therefore right
    for the customers this product is for. Monday would be the ISO answer and
    the wrong one here: a weekly figure cut on Monday splits a Gulf working week
    across two rows.
    """

    SUNDAY = "sunday"
    MONDAY = "monday"
    TUESDAY = "tuesday"
    WEDNESDAY = "wednesday"
    THURSDAY = "thursday"
    FRIDAY = "friday"
    SATURDAY = "saturday"


class Scale(StrEnum):
    """How large figures are written. Presentation only.

    `184.6 K OMR` and `184600 OMR` are the same number, and the prototype writes
    the first. Which one a founder wants depends on the size of their business,
    so it is theirs to choose — and it is the one reporting setting that cannot
    change an answer, only its spelling.
    """

    UNITS = "units"
    THOUSANDS = "thousands"
    MILLIONS = "millions"


DEFAULT_WEEK_START: Final = WeekStart.SUNDAY
DEFAULT_SCALE: Final = Scale.THOUSANDS
DEFAULT_DECIMALS: Final = 1
DEFAULT_TIMEZONE: Final = "Asia/Muscat"
DEFAULT_FISCAL_YEAR_START_MONTH: Final = 1

MAX_DECIMALS: Final = 2
"""Beyond two, a rounded figure implies a precision the source does not have —
and OMR is a three-decimal currency, so this is a display choice rather than a
statement about the smallest coin."""


@dataclass(frozen=True, slots=True)
class ReportingSettings:
    """One company's reporting assumptions.

    Every field has a default that is defensible for a GCC SME, because a
    dashboard cannot render without all of them and refusing to render until
    somebody visits a settings screen would make the assumptions invisible
    rather than making them chosen. What the screen adds is the *ability* to
    change them, and the record that they were.
    """

    fiscal_year_start_month: int = DEFAULT_FISCAL_YEAR_START_MONTH
    week_start: WeekStart = DEFAULT_WEEK_START
    timezone: str = DEFAULT_TIMEZONE
    """The timezone **reports** are cut in, which is not the timezone a person
    reads them in. `persona.timezone` is the second, is per-user, and is
    presentation. A company whose founder is travelling does not want yesterday
    to move."""

    scale: Scale = DEFAULT_SCALE
    decimals: int = DEFAULT_DECIMALS

    def __post_init__(self) -> None:
        if not 1 <= self.fiscal_year_start_month <= 12:
            raise ValueError("the financial year starts in one of twelve months")
        if not 0 <= self.decimals <= MAX_DECIMALS:
            raise ValueError(f"decimals must be between 0 and {MAX_DECIMALS}")


# ── What each setting moves ───────────────────────────────────
#
# Declared as the sources a setting participates in, and the affected tiles are
# derived from that. The alternative — listing capability ids per setting — is a
# third hand-maintained list of the same relationship, which is the failure
# `domain/registry.py` exists to end.


@dataclass(frozen=True, slots=True)
class Setting:
    """One field on the panel, and the sentence that has to be true."""

    key: str
    label: str
    changes: str
    """What it changes, in the question bank's voice. Every question in
    `question_bank.py` carries a `why`; a setting that restates numbers owes the
    customer the same sentence."""

    affects: tuple[Source, ...]
    """The sources whose figures are cut differently when this changes. Empty
    means no tile is recomputed."""

    relabels: bool = False
    """Whether it changes what a figure **means** without recomputing it.

    Currency is the only one, and it is why this field exists rather than
    `restates_numbers` reading `affects` alone. Changing the currency moves no
    tile — no arithmetic is redone — and it changes every figure in the product
    from rials to dirhams. Treating that as presentation, beside the choice
    between `184.6K` and `184,600`, would be the one place this module lied:
    writing a number differently cannot mislead anybody, and labelling it in
    the wrong currency can.
    """


SETTINGS: Final[tuple[Setting, ...]] = (
    Setting(
        key="currency",
        label="You report in",
        changes=(
            "The label on every figure in the product. It changes what a number"
            " means, not what it is — and it was asked for nowhere until now,"
            " so every workspace has been assuming Omani rials."
        ),
        # No tile is recomputed, so `affects` is empty — and it is still a
        # restatement, which is what `relabels` records.
        affects=(),
        relabels=True,
    ),
    Setting(
        key="fiscal_year_start_month",
        label="Financial year starts",
        changes=(
            "Every year-to-date figure and every period comparison. Changing it"
            " re-derives this year's figures and marks the previous derivation"
            " superseded rather than editing it."
        ),
        # Year-to-date is a ledger question, and a comparison needs elapsed
        # periods to compare. Nothing else changes when the year moves.
        affects=(Source.ACCOUNTING, Source.HISTORY),
    ),
    Setting(
        key="week_start",
        label="Reporting week starts",
        changes=(
            "Where every weekly figure is cut. A week that starts on the wrong"
            " day splits a working week across two rows."
        ),
        affects=(Source.HISTORY, Source.GA4, Source.CRM, Source.OPS_LAYER),
    ),
    Setting(
        key="timezone",
        label="Reports are cut in",
        changes=(
            "Where a day ends. An order dispatched at eleven at night belongs to"
            " one day or the next depending on this, and nothing else decides it."
        ),
        affects=(Source.GA4, Source.CRM, Source.OPS_LAYER),
    ),
    Setting(
        key="scale",
        label="Large figures shown as",
        changes=(
            "How a figure is written, never what it is. `184.6K` and `184,600` are the same number."
        ),
        affects=(),
    ),
    Setting(
        key="decimals",
        label="Decimal places",
        changes="How precisely a figure is written, never how precisely it is known.",
        affects=(),
    ),
)

BY_KEY: Final[dict[str, Setting]] = {setting.key: setting for setting in SETTINGS}


def moves(setting: Setting, *, selected: frozenset[Department]) -> tuple[Capability, ...]:
    """Which of this company's tiles are computed differently if this changes.

    **Derived, and scoped to the company.** A company that does not run
    Operations must not be told that its reporting week moves Operations tiles —
    the sentence would be true of the product and false of them, which is the
    same failure as a denominator counting departments they do not have.

    Counts every tile that reads an affected source, whether or not it is built
    yet. That is deliberate and the opposite of the rule in `sources.py`: there,
    an unbuilt capability must not be advertised as an *unlock*, because the
    sentence is a call to action. Here the sentence is a warning about scope, and
    understating it would be the dangerous direction.
    """
    if not setting.affects:
        return ()
    return tuple(
        capability
        for capability in TILES
        if capability.department in selected
        and any(source in capability.required_sources for source in setting.affects)
    )


def restates_numbers(setting: Setting) -> bool:
    """Whether changing this needs the restate rule at all.

    Two ways to qualify, and they are different: `affects` means tiles are
    **recomputed**, `relabels` means they mean something else without being
    recomputed. Currency is the second and only the second.

    Scale and decimals are neither. Nothing is recomputed, nothing means
    anything new, and logging a display preference as a restatement would bury
    the changes that matter among the ones that do not.
    """
    return bool(setting.affects) or setting.relabels
