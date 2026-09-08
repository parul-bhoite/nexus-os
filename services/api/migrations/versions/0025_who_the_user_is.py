"""Who the user is: a name to address them by, and the job they say they do.

Three columns, all nullable, no data moved. Additive.

**`app_user.phone`** — so a person can be reached outside the product. Not
verified and not an identifier: `ix_app_user_email_lower` remains the unique
one, because a phone number is shared, reassigned and re-formatted, and a second
unique identity column is a second way for two humans to collide.

**`membership.designation`** and **`membership.stated_department`** — the job
title and department the user types about themselves.

The important thing about both is what they are *not*, and the column names are
chosen so the distinction survives somebody reading this table at speed:

- `membership.role` is authorisation. Migration 0002 records the rule — *"role
  is set by the inviter, never self-declared at acceptance"* — and it is the
  input to the retrieval predicate.
- `membership.departments` (plural, `text[]`) is department **reach**, and is
  what a `department_manager` is scoped by.
- `membership.stated_department` (singular, `text`) is what the user *said*.
  It steers what the agent asks and what the dashboard shows first. It reaches
  nothing.

Those two department columns sit next to each other, one letter apart in intent
and nothing alike in consequence, so the singular one is named for the fact that
it is a claim rather than a grant. A future reader who wires `stated_department`
into a permission check should find the name itself argues with them.

Neither may become a persona field. `assert_persona_is_not_authorisation` fails
at import on any persona key whose tail contains `department`, which is the
guard that makes this more than a naming convention.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0025"
down_revision = "0024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("app_user", sa.Column("phone", sa.Text(), nullable=True))
    op.add_column("membership", sa.Column("designation", sa.Text(), nullable=True))
    op.add_column("membership", sa.Column("stated_department", sa.Text(), nullable=True))

    # Cheap, and it stops the two obvious ways this gets abused: a blank string
    # standing in for "not answered", and a free-text field used as a paragraph.
    op.create_check_constraint(
        "ck_app_user_phone_shape",
        "app_user",
        "phone IS NULL OR (btrim(phone) <> '' AND length(phone) <= 32)",
    )
    op.create_check_constraint(
        "ck_membership_designation_shape",
        "membership",
        "designation IS NULL OR (btrim(designation) <> '' AND length(designation) <= 120)",
    )
    op.create_check_constraint(
        "ck_membership_stated_department_shape",
        "membership",
        "stated_department IS NULL OR"
        " (btrim(stated_department) <> '' AND length(stated_department) <= 120)",
    )


def downgrade() -> None:
    op.drop_constraint("ck_membership_stated_department_shape", "membership")
    op.drop_constraint("ck_membership_designation_shape", "membership")
    op.drop_constraint("ck_app_user_phone_shape", "app_user")
    op.drop_column("membership", "stated_department")
    op.drop_column("membership", "designation")
    op.drop_column("app_user", "phone")
