"""The reporting assumptions every window is cut against.

`doc/13` §13, ADR 0025. Doc 05 §1 lists seven global assumptions *"required
before any dashboard renders"*, and **four had nowhere to live**: the fiscal year
start existed only as an onboarding answer, and the reporting week, the report
timezone and the units did not exist at all. ADR 0025 then fixed each tile's
window and required it stated in its working — which cannot be done from
settings that are not stored.

Five columns on `workspace`, and a stamp.

**Defaults, not nulls.** Every column has a server default that is defensible
for a GCC SME: the calendar year, a **Sunday** week, Asia/Muscat, thousands to
one decimal. A dashboard cannot render without all five, so making them nullable
would push the decision into every reader — and the first reader to substitute
Monday because ISO says so would cut a Gulf working week across two rows.

**`reporting_changed_at` is the restate stamp** (`doc/13` §10). Changing a
setting that restates numbers marks the affected tiles stale and re-derives
them; there are no tiles yet, so what lands here is the stamp a later derivation
compares itself against, plus the audit row saying who moved it. Adding the
column now is what makes P14 able to do that without a second migration.

Nullable, deliberately: NULL means *never changed since registration*, which is
a different fact from *changed at the moment the row was created*. A derivation
comparing itself against a stamp needs to be able to tell those apart.

**`ck_workspace_reporting_scale` and `ck_workspace_reporting_week_start`** are
value-list CHECKs and are registered in `test_constraint_enum_parity` in the
same commit — a value-list constraint with no mapping fails that test rather
than the one it was added for, which `CONTINUE-HERE` records as having cost
three CI round trips.

The month and the decimal places are range CHECKs rather than value lists: there
is no enum behind twelve months, and writing one out to satisfy a pattern would
be a list to keep in step for nothing.

Revision ID: 0027
Revises: 0026
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0027"
down_revision = "0026"
branch_labels = None
depends_on = None

WEEK_STARTS = (
    "sunday",
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
)
"""Mirrors `app.domain.reporting.WeekStart`, compared on every run by
`test_constraint_enum_parity`. Written out rather than imported: a migration
that imports application code stops running the day that code is refactored,
and the point of a migration is that it still runs against the schema it was
written for."""

SCALES = ("units", "thousands", "millions")
"""Mirrors `app.domain.reporting.Scale`."""

MAX_DECIMALS = 2


def upgrade() -> None:
    op.add_column(
        "workspace",
        sa.Column(
            "fiscal_year_start_month",
            sa.SmallInteger,
            nullable=False,
            server_default="1",
        ),
    )
    op.add_column(
        "workspace",
        sa.Column(
            "reporting_week_start",
            sa.Text,
            nullable=False,
            server_default="sunday",
        ),
    )
    op.add_column(
        "workspace",
        sa.Column(
            "report_timezone",
            sa.Text,
            nullable=False,
            server_default="Asia/Muscat",
        ),
    )
    op.add_column(
        "workspace",
        sa.Column("report_scale", sa.Text, nullable=False, server_default="thousands"),
    )
    op.add_column(
        "workspace",
        sa.Column("report_decimals", sa.SmallInteger, nullable=False, server_default="1"),
    )
    op.add_column(
        "workspace",
        sa.Column("reporting_changed_at", sa.DateTime(timezone=True)),
    )

    op.create_check_constraint(
        "ck_workspace_reporting_week_start",
        "workspace",
        "reporting_week_start IN ('" + "', '".join(WEEK_STARTS) + "')",
    )
    op.create_check_constraint(
        "ck_workspace_reporting_scale",
        "workspace",
        "report_scale IN ('" + "', '".join(SCALES) + "')",
    )
    op.create_check_constraint(
        "ck_workspace_fiscal_year_start_month",
        "workspace",
        "fiscal_year_start_month BETWEEN 1 AND 12",
    )
    op.create_check_constraint(
        "ck_workspace_report_decimals",
        "workspace",
        f"report_decimals BETWEEN 0 AND {MAX_DECIMALS}",
    )


def downgrade() -> None:
    for constraint in (
        "ck_workspace_report_decimals",
        "ck_workspace_fiscal_year_start_month",
        "ck_workspace_reporting_scale",
        "ck_workspace_reporting_week_start",
    ):
        op.drop_constraint(constraint, "workspace")

    for column in (
        "reporting_changed_at",
        "report_decimals",
        "report_scale",
        "report_timezone",
        "reporting_week_start",
        "fiscal_year_start_month",
    ):
        op.drop_column("workspace", column)
