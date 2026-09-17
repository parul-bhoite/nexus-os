"""`workspace_connection.credentials` — the OAuth half migration 0026 left open.

ADR 0032, answering **D27 with option A**. Migration 0026 created the table with
`provider`, `state` and `declared_by`, and its own comment on `connected_at`
said the rest was *"null until the OAuth half lands"*. This is that half's
storage: a workspace could declare *"we use HubSpot"* and nothing could read
HubSpot, because there was nowhere to put a token.

**Two columns, not one.** The ciphertext and the id of the key that made it. A
row whose key id is *queryable* is a row that a rotation can find; one that has
to be decrypted before you know which key it used cannot be found without the
very key that may already be gone. `credentials.key_id_for` derives that id from
the key material itself, so a new key has a new id by construction and nobody
has to remember to increment anything.

**Only a refresh token is ever stored here** — ADR 0032's option C. An access
token expires within the hour, so keeping one buys nothing and widens what a
read of this table is worth.

`ck_workspace_connection_credentials` is the same shape as
`ck_generation_prose_matches_outcome` and exists for the same reason: two
columns that are meaningful only together must not be able to disagree. A
ciphertext with no key id cannot be opened, and a key id with no ciphertext
describes nothing.

Additive. No `DROP`, both columns nullable, so every existing row — all of them
`declared` and none of them connected — remains valid.

Revision ID: 0030
Revises: 0029
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0030"
down_revision = "0029"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Nullable, because a `declared` connection legitimately has no credential:
    # the customer has told us which CRM they run and has not yet authorised us
    # to read it. Those are different states and the column keeps them apart.
    op.add_column("workspace_connection", sa.Column("credentials", sa.Text, nullable=True))
    op.add_column("workspace_connection", sa.Column("credential_key_id", sa.Text, nullable=True))

    op.create_check_constraint(
        "ck_workspace_connection_credentials",
        "workspace_connection",
        "(credentials IS NULL) = (credential_key_id IS NULL)",
    )

    # Rotation's only query: *which rows still hold the old key?* Partial,
    # because rows with no credential are the overwhelming majority today and
    # will never be an answer to it.
    op.create_index(
        "ix_workspace_connection_credential_key",
        "workspace_connection",
        ["credential_key_id"],
        postgresql_where=sa.text("credential_key_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_workspace_connection_credential_key", table_name="workspace_connection")
    op.drop_constraint("ck_workspace_connection_credentials", "workspace_connection", type_="check")
    op.drop_column("workspace_connection", "credential_key_id")
    op.drop_column("workspace_connection", "credentials")
