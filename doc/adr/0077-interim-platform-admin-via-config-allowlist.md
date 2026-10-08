# ADR 0077 — Global prices are edited by an interim platform admin (config allowlist)

- Status: Accepted
- Date: 2026-10-07
- Related: [0076](0076-onboarding-ends-in-a-payment-step-with-db-pricing-and-entitlement.md)
  (the `price` table these endpoints edit).

## Context

ADR 0076 puts prices in a global `price` table and requires an **admin portal** to
edit them. "Admin" is a problem the existing model does not answer: every role in
`scopes.py` (`Role`/`ROLE_GRANTS`) is **workspace-scoped**, and prices are **global**
platform data. Letting any workspace owner edit global prices is a cross-tenant
authority leak — one tenant's owner changing the price everyone sees. There is no
platform-operator role today.

## Decision

Introduce an **interim platform-admin check** keyed on a server-side config allowlist:
a setting `platform_admin_emails` (from `NEXUS_PLATFORM_ADMIN_EMAILS`,
comma-separated, default empty). The admin pricing endpoints
(`GET /admin/prices`, `PUT /admin/prices/{kind}/{key}`) allow a request only when the
authenticated user's email is in that allowlist; otherwise `403`. An empty allowlist
means **no** platform admins — every admin write is refused — which is the safe
default (it follows the optional-secret pattern: absent config fails closed on the
admin path, like `anthropic_api_key` elsewhere).

No new database column and no change to the workspace `Role` lattice: this is
deliberately the smallest thing that keeps global-price editing off the tenant roles.

## Reasoning

- **It must not be a workspace role.** A workspace owner editing global prices is the
  exact cross-tenant authority this avoids; gating on an allowlist of operator emails
  keeps the decision outside the tenant model entirely.
- **A config allowlist over a DB `is_platform_admin` flag** for the interim: the flag
  would still need a way to be set (seeding, an even-more-privileged editor) — a
  bootstrapping regress. An env allowlist is settable by whoever controls deployment,
  which is who a platform operator actually is today, and adds no migration.
- **Fails closed.** Empty allowlist → no admins → `403`. A pricing editor that
  defaulted open would be worse than none.

## Consequences

- The admin pricing UI/endpoints are usable only by configured operator emails; for
  everyone else the route 403s (the UI shows "not authorised").
- This is explicitly **interim**. A real platform-admin identity (its own table/flag,
  audit trail, maybe MFA) is a follow-up; until then the allowlist is the authority.
- The check reads the authenticated user's email from the session the same way the
  rest of the API does — it never takes an identity as input (invariants I2/I3).

## Revisit trigger

Revisit when: platform administration grows beyond editing prices (needs a real role
with an audit trail and finer permissions); more than a handful of operators need
access (an env list stops scaling); or prices become per-workspace/per-region, which
would move some "pricing" authority back onto workspace roles and change who may edit
what.
