# NEXUS OS — Documentation Set

Version 0.9 (Draft for review) · 16 August 2026 · Parul Bhoite
*Reorganised 25 August 2026 — see the folder map at the end.*

> **These are the specification.** They describe the intended product. For the
> plan, the architecture and what is actually built, start at the repo root:
> `VISION-AND-PLAN.md` · `ARCHITECTURE-HLD.md` · `ARCHITECTURE-LLD.md` ·
> `BUILD-STATUS.md`.

| File | What it is | Read it if you are |
|---|---|---|
| `01-NEXUS-OS-PRD.md` / `.docx` | **Lean PRD** — analysis of the idea and its motive, users, principles, MVP scope cut, module requirements with acceptance criteria, NFRs, AI grounding contract, metrics, risks, open decisions | Building the product |
| `02-NEXUS-OS-Solution-Offering.md` / `.docx` | **Solution offering** — problem, value narrative, seven pillars, AI executive team, competitive position, packaging and tiers, cost to run, delivery model | Selling or positioning it |
| `03-NEXUS-OS-Architecture-and-Roadmap.md` / `.docx` | **Architecture & roadmap** — component design, grounding pipeline, data model, integration inventory, phased roadmap, effort estimate, engineering standards | Scoping or estimating the build |
| `04-NEXUS-OS-Flow-and-Cold-Start-Analysis.md` / `.docx` | **Flow & cold-start analysis** — a deliberately adversarial read of the onboarding flow: what we ask the user, what the crawler should infer instead, the data-source truth table for every capability, and what the dashboard can honestly show when the customer connects nothing | Designing onboarding or the empty states |
| `05-Department-Dashboard-Offerings-and-Data-Assumptions.md` / `.docx` | **Department dashboard spec** — every offering for each of the seven AI directors, the information assumptions behind each widget, degraded states, the CRM normalisation model, the new Operations data layer, and which departments are scoreable | Designing or building the dashboard |
| `06-User-Journey-and-System-Design.md` / `.docx` | **User journey & system design** — the 17-step journey specified stage by stage: account types, role-derived departments, the persona object, domain verification, the Company Brain permission model, the review gate, the always-on assistant, the untrusted-content and prompt-injection boundary, the Claude Agent SDK mapping, the admin panel, and the gaps in the journey | Building the application |
| `08-Department-Onboarding-Questions-and-Dashboard-Offering.md` / `.docx` | **Department question bank & as-built offering** — for each of the seven departments: the onboarding questions with their option lists, what NEXUS deliberately does *not* ask because a connector answers it, what the dashboard offers section by section, what stays locked, and what the scoped assistant can answer. Extracted from the prototype, so it records what exists rather than what was intended | Building onboarding, or answering "what does a Sales manager actually get?" |
| `09-NEW-APPLICATION-FLOW.md` | **The new application flow** (25 Aug 2026) — the nine-stage linear journey from landing page to Company Brain to dashboard, what it changes, the four problems it must resolve, and what it does to the codebase. Supersedes doc 06 §0 and doc 04 §5 | Building anything user-facing |
| `10-FLOW-QUESTIONS.md` | **The interrogation** — 71 questions across the eleven stages, each with a recommendation. Historical; the answers are in doc 11 | Understanding why a decision went the way it did |
| `11-FLOW-DECISIONS.md` | **The answer record** — every flow decision, the consequences of each reversal, the preserved capability list, and the four items still open. **Authoritative** | Building anything user-facing |
| `12-IMPLEMENTATION-PLAN.md` | **The executable plan** — twenty-two phases, each with a build list, a do-not-build list, tests-first, and an acceptance test. Supersedes `VISION-AND-PLAN.md` §6 | Executing a phase |
| `13-DASHBOARD-DESIGN.md` | **The dashboard, the settings portal and the agents** (v2, 9 Sep 2026) — information architecture for all seven directors (sections, blocks, seven render states, what every domain can honestly show on day one with no connector, the Watchlist, the finding primitive); the fourteen-panel settings portal and why it holds the dashboard's denominators; the tool ledger — every tool, what it unlocks, what it cannot answer; and every director as a skill on the existing skill runtime. Four decisions taken (ADR 0023–0026), nine still owed, nine defects found | Designing or building the dashboard, settings, connectors or the directors |
| `NEXUS-OS-Solution-Overview.pptx` | **Executive deck** (20 slides) — opportunity, solution, capability, trust model, architecture, business model, roadmap, risks, next steps *(now in `doc/exports/`)* | Presenting to stakeholders |

## Folder map

| Folder | Contents |
|---|---|
| `doc/` | The eight specification documents, in Markdown. **Canonical** |
| `doc/adr/` | Architecture decision records, `0001`–`0026` |
| `doc/exports/` | `.docx` and `.pptx` renderings of the specs, for sharing. **Generated — do not edit; the `.md` is the source** |
| `doc/source/` | The four supplied documents these specs derive from |
| `doc/prototype/` | The interactive prototype and its notes, plus the v2 dashboard mock and tools sheet. Doc 08 was extracted from these |
| `doc/archive/` | Retired working documents — the pre-build `ARCHITECTURE.md`, `TASKS.md` and the six `MILESTONE-N.md` notes. See `doc/archive/README.md` for what replaced each |

Doc 07 has no `.docx`; it was written as a build prompt, not a deliverable.

## Source material

Everything here derives from four supplied documents plus the interactive
prototype. The four now live in `doc/source/`:

- `Ai Business.pdf` — project understanding, resourcing, tech stack, INR 49K setup cost
- `AI-Business-OS-Business-Model.pdf` — market, revenue model, 12 Phase-1 modules, architecture
- `NEXUS-OS-AI-Prompt-Library.docx` — 23 production prompt modules with grounding rules and JSON schemas
- `NEXUS-OS-Monthly-Running-Costs.xlsx` — per-service cost breakdown, ~$260/month total
- `https://nexusdraftnew.netlify.app/` — landing page, 11-step onboarding, full dashboard, captured in `doc/prototype/`

## The findings that shaped these documents

1. **The prototype is a materially bigger product than the written scope.** The business-model document commits 12 modules to Phase 1; the prototype adds Business Simulator, Opportunity Radar, Competitor War Room, Customer Intelligence, Decision Intelligence and NEXUS Labs on top. These documents reconcile the two by cutting an explicit MVP and dating — not deleting — the rest.

2. **The moat is the Company Brain, not the feature list.** Any single feature is copyable. A customer's accumulated business context is not, and it compounds every week they use the product.

3. **The cold-start problem is unsolved in the current flow.** None of the prototype's headline dashboard numbers are available on day one. Document 04 works this through in full.

4. **NEXUS connects to the customer's CRM rather than replacing it** (decision, Aug 2026). That makes the new **Operations / Delivery layer the only first-party data NEXUS owns** — so its adoption, not CRM adoption, now determines whether the executive layer ever works. Document 05 specifies the consequences.

5. **Trust is an engineering problem, not a marketing one.** The supplied prompt library is unusually disciplined about never inventing numbers. That discipline is elevated here into a per-module contract enforced in code and CI, because it is the single thing that decides whether people keep believing the product.

## Figures and their status

All numbers reproduced from the source material are labelled as such. Two in particular are flagged as unvalidated **in the source itself** and should be treated as planning inputs, not commitments:

- **$49/month** — reference price point, explicitly to be validated with real customers
- **~$260/month** — running cost at validation-stage volume, scaling with usage

Effort estimates (~18 / ~17 / ~23 person-months by phase) are derived from the stated scope and team composition; they are planning estimates, not quotes.
