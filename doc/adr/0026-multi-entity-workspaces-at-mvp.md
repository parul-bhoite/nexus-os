# ADR 0026 — Multi-entity workspaces at MVP, reversing Q9 and D17

**Status** Accepted
**Date** 9 September 2026
**Decided by** Parul, answering `doc/13` §25 decision 6.

## Context

`doc/11` Q9 and Q17 decided **one person, one company, one workspace**, reversing
doc 07 M1's many-to-many agency case. The resolution was *"keep the schema, constrain the
product"*: `membership` stayed many-to-many because it was already built and proved under
RLS, and the product enforced a single live membership per user, with a test asserting it.
The workspace switcher was cancelled, `POST /auth/workspace` was deleted, and
`_teardown_on_switch` was deleted with it — which also retired **I5's
cache-invalidation-on-switch requirement**.

`doc/prototype/NEXUS OS Dashboard Tools.xlsx` then listed multi-entity switching as a
feature: one login managing several business units, each with its own Company Brain, CRM
and dashboard, **rolling up to a group view**. `doc/11` §3.2 had explicitly deferred that
to post-MVP.

## Decision

**Build it at MVP.** One login may hold membership in several workspaces, switch between
them, and — where they hold membership in more than one — see a **group view** across the
ones they hold.

`membership` needs no migration; it is already many-to-many. What changes is the product
constraint, and one genuinely new read path.

## Consequences, in order of how much they cost

**1. The group view is a cross-tenant read, and everything in this product is built so
that cannot happen.** This is the substantial consequence, not the switcher.
`retrieval/` takes a `ScopedSession` scoped to exactly one `nexus.workspace_id`, and
`nexus_app` is `NOBYPASSRLS`, so a query with no workspace set returns **zero rows rather
than an error**. A group roll-up therefore must **not** be built by loosening the
predicate. It is a separate, explicitly-named path that:

- resolves the caller's memberships first, from `membership_own_rows`;
- opens **one scoped session per workspace** and computes each entity's figures inside
  its own scope;
- aggregates **outside** the database, in `calculators/`, which is pure;
- and renders per-entity provenance, so a group number can always be broken back down
  into the entities it came from.

A test must assert that the group path holds no query without a workspace GUC set, and
that it returns nothing for a workspace the caller has no membership in.

**2. I5 comes back.** Cache invalidation on switch was retired with
`_teardown_on_switch`. Every cache keyed by anything narrower than the workspace — the
Brain, computed tiles, generation snapshots, assistant context — must be invalidated on
switch, or entity A's numbers appear under entity B's name. That is the worst failure
this product can have, and it is the one the deletion made possible again.

**3. One-live-membership and its test are lifted**, deliberately, and the test is
replaced rather than deleted — with one asserting that a caller's reachable workspaces
are exactly their memberships and no more.

**4. `POST /auth/workspace` returns**, and with it the switcher UI, an entity selector in
the shell, and an entity column in the audit log. Old work item H6 in `BUILD-STATUS.md`
is un-cancelled; the ~2 days it saved are spent.

**5. Per-entity everything, and it mostly already works.** The Brain, the domain claim,
the tool connections, the invitations, the departments and the question answers are all
already keyed by workspace, so each entity gets its own without new schema. The scoping
consolidation that just finished — three GUCs, each with its own primitive — is what
makes this affordable.

**6. Group-level composite needs a denominator of its own.** "72 across 4 of 6 scored
departments" is a per-entity claim. A group number needs to state how many entities it
covers and which are unscored, by the same rule: the denominator travels with the score.

**7. Departments are per entity, not per person.** Somebody may be Finance at one entity
and Operations at another. `scope.departments` is therefore resolved per active
workspace, never cached across a switch — which is consequence 2 restated where it will
actually bite.

**8. Invitations still name one workspace.** A person invited to a second entity joins
that entity; they do not gain the group view unless they hold membership in more than
one. The group view is a property of memberships, never of a role.

## What this reverses, explicitly

`doc/11` Q9, Q17 and §3.2's deferral. Those decisions are superseded by this one, not
reinterpreted. `doc/11` should carry a pointer to this ADR so the reversal is visible
from where the original decision is recorded.
