# Changelog

All notable changes to NEXUS OS are recorded here. This project follows
[Semantic Versioning](https://semver.org/) and
[Conventional Commits](https://www.conventionalcommits.org/).

## [1.1.0] - 2026-10-03

The first tagged release. It brings the product from registration through a
grounded, permission-scoped company dashboard, with every number fetched or
computed in code and every generated claim cited or withheld.

### Added

**Onboarding & registration**
- Three-section onboarding that opens by naming who it is talking to, with
  animated waits and a panel that never pretends to be full.
- Registration that reports a taken address on the page you are already on, and
  stops asking for facts nothing reads.
- Per-request assembly: one stage per request, each committed.

**Dashboard command surface**
- A single shell for every signed-in surface; the tab rail is demoted to a
  summary within the common surface.
- The morning brief, measured tiles, the coverage region (who has to move next),
  the directors block, and the Company Brain on the common surface.
- `coverage()` and the three bands the dashboard opens with; a company dashboard
  segregated by who is looking.

**Company Brain & grounding (I1)**
- The grounding pipeline — every figure is a number or a named absence — making
  invariant I1 testable.
- The fact layer: precedence as an enum, contradiction that asks rather than
  rejects, and precedence enforced on write.
- Brain assembly through one path to facts, with every fact naming its source.
- A review gate: impact rules, bulk-accept, a separate block, and facts that are
  usable-but-labelled before review.

**Retrieval (I2/I3)**
- The retrieval core with the permission predicate inside the query, backed by
  eight red-team specs; HNSW iterative scan per ADR 0012.

**Documents**
- The upload stage with named asks, per-file failure and a real skip; the three
  server-side upload limits; CSV parsed as columns; signed downloads.
- The review queue screen so withheld chunks can be placed, wired to the
  calibrated rules classifier.

**Connectors & integrations**
- The connector spine — one adapter interface, two transports — the official MCP
  SDK, and HubSpot as the first connector, with the OAuth round trip and sealed
  provider credentials at rest.

**Operations, Sales & Marketing layers**
- The ops layer: projects, tasks, milestones, issues, stock-against-minimum and
  supplier exposure, a customer-set definition of "late", and figures marked
  self-reported — a score-free Operations surface that shows its drivers.
- Sales deals-lite reusing `crm_deal`, partitioned by provenance.
- Marketing's first real numbers and generated content where every claim is
  cited or not made.

**Instant Gap Analysis & the assistant**
- The anonymous Instant Gap Analysis scanner (G0–G10) with public-scan expiry.
- An assistant that answers from documents behind an off-by-default flag, with a
  refusal that names the missing capability and an input box argued over for
  five phases.

**Settings & security invariants**
- The Settings screen and setup shell; the three security invariants the later
  phases rest on; managers may staff their own department without losing files;
  revocation and connect-time disclosure of what a connection cannot compute.

### Fixed

- Resolved the backend and frontend findings from the end-to-end defect register.
- Scan refuses a malformed host label instead of returning 500.
- Improved website-URL validation and handling in the registration forms.
- Numerous defects surfaced by the end-to-end and browser runs, the HTTP size-unit
  regression, and the full-suite failures cleared ahead of release.

### Changed / Performance

- Read the whole ops layer in one round trip instead of nine; read both deal
  populations in a single statement.
- One shell for every signed-in surface, replacing the per-area tab rail.

### Security

- Provider credentials sealed at rest (D27).
- Middleware session gate and XML hardening (ADRs 0063, 0064).

### Docs

- Architecture (HLD/LLD), the dashboard and ops/people layer plans, the
  implementation plan, and ADRs 0039–0064 recording the decisions behind the work.

[1.1.0]: https://github.com/parul-bhoite/nexus-os/releases/tag/v1.1.0
