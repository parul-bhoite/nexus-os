# ADR 0032 — How a provider's token is held

**Status** Accepted
**Date** 17 September 2026
**Decided by** Parul, answering D27 — *"go with A for D27"*. Written before implementation
because guessing at a secret-storage design is the wrong thing to do quietly, and because
a provider token is read-access to a customer's entire pipeline.

**Implemented** in migration 0030 (`workspace_connection.credentials` and
`credential_key_id`), `app/connectors/credentials.py`, and
`Settings.connector_secret_key` — which joins `_DEPLOYED_REQUIRES`.

## Context

ADR 0031 built the connector spine: one adapter interface, an HTTP transport and an MCP
transport. It reaches a provider by holding a token and putting it in a header — and
**there is nowhere to put that token.**

`workspace_connection` (migration 0026) holds `provider`, `state`, `declared_by` and
`connected_at`, and its own comment says the rest is *"null until the OAuth half lands"*.
So a workspace can declare *"we use HubSpot"* and nothing can read HubSpot.

Two things are missing and only one of them is a decision:

1. **A column.** Additive, previewable, and nobody's judgement call.
2. **How the value in it is protected.** That is this ADR.

The service holds no encryption dependency today — `cryptography` is not installed — and
`Settings` has exactly one secret of this shape, `storage_signing_secret`, which signs
rather than encrypts. So this is a new capability rather than an extension of an existing
one, which is why it is worth deciding rather than assuming.

## The options

**A — Encrypted column, key from the environment.** A `credentials` column holding an
AEAD ciphertext; the key arrives as `NEXUS_CONNECTOR_SECRET_KEY`. Adds `cryptography`.
Rotation means re-encrypting every row, so the column carries a key id from the start.

**B — A managed secret store** (AWS Secrets Manager, GCP Secret Manager, Vault). The row
holds a reference; the secret never touches our database. Rotation and audit come with
it. Adds a cloud dependency and a second failure mode on a path that must work for a
background sweep.

**C — Never hold a long-lived token.** Short-lived access tokens only, re-obtained per
sweep from a refresh token — which is itself a long-lived secret that has to live
somewhere, so this reduces exposure rather than removing the question. It is a *modifier*
on A or B, not an alternative to them.

## Decision

**A, with C layered on: an encrypted column keyed from the environment, storing the
refresh token, with access tokens held only in memory for the life of a sweep.**

### Reasoning

**Why not B, today.** The product has one deployment target and no secret-store
dependency. Introducing one puts a network call between a worker and every provider
fetch, and its outage mode is *"no connector runs"* — which would render as every
connected tile going quiet at once, the failure hardest to distinguish from the product
being broken. B is the right answer at a scale this has not reached; the column in A can
hold a reference later without another migration.

**Why the key is an environment variable and not derived.** A key derived from something
already in the database is not a key. `storage_signing_secret` already sets the shape:
one variable, required in deployed environments, absent locally without breaking
development.

**Why a key id in the column from day one.** Rotation without one means decrypting every
row with every historical key and guessing. Cheap now, impossible to retrofit quietly.

**Why the refresh token rather than the access token.** An access token expires in an
hour, so storing it buys nothing and widens what a database read is worth. This is C's
only real contribution and it costs one extra call per sweep.

**Why this blocks rather than proceeds.** A provider token is the customer's own CRM,
read-access to their whole pipeline. Choosing how it is held is not an implementation
detail to be settled inside a step, and the sequence is short: answer D27, add the
dependency, write an additive migration, then step 9 is unblocked.

## Consequences

- **Adds `cryptography` to the base dependency set**, not an optional extra. Unlike the
  language model (ADR 0011), a connector that cannot decrypt its token is not a supported
  state — it is a connection that silently stops working.
- **`NEXUS_CONNECTOR_SECRET_KEY` joins the deployed-required list** beside
  `database_url` and `storage_signing_secret`. A deployment that starts without it and
  fails on the first sweep is worse than one that refuses to start.
- **Losing the key means every workspace reconnects.** Recoverable, and the recovery is
  visible and explainable, which is more than can be said for a key that is present and
  wrong.
- **Nothing in `app/connectors/` changes.** The spine takes a token; where it came from is
  above it. That is the boundary earning its keep on the first real question asked of it.

## Revisit trigger

- **A second deployment environment appears**, or compliance asks where keys live. That is
  when B stops being premature.
- **A provider requires per-user rather than per-workspace tokens.** The column is on
  `workspace_connection`, and that assumption is currently free.
- **Any connector needs write scope.** `SourceEntry.read_only` is `True` everywhere and A5
  makes write a separate, heavier ask — a token that can write is a different risk and
  deserves this argument again rather than inheriting it.
