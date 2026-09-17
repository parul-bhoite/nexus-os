# 0042 — 21st is registered, not yet adopted

**Status:** Proposed
**Date:** 17 September 2026
**Depends on:** ADR 0031 (MCP is a transport, not a tool surface)
**Context:** Three install commands run in one session, on
`feature/dashboard-command-surface`

## Context

Three commands were run, in this order:

```
npx skills add https://github.com/greensock/gsap-skills
npx skills add https://github.com/Leonxlnx/taste-skill
npx @21st-dev/cli@latest init --client claude --write
```

They left four untracked paths and nothing else. `.agents/skills/` holds
twenty-one third-party skills — eight GSAP, thirteen from `taste-skill` —
symlinked into `.claude/skills/`; `skills-lock.json` records the two sources;
and a new `.mcp.json` registers `21st` as an HTTP MCP server at
`https://21st.dev/api/mcp`, authenticating with `${API_KEY_21ST}`.

**None of it is live.** `API_KEY_21ST` is unset in the environment and absent
from `.env`, so the server has never completed a request. `apps/web` still
declares `framer-motion ^11.11.17` as its only animation library, has no `gsap`
dependency, and contains no `gsap` import. No component in `apps/web` came from
21st. Nothing is committed.

Two properties of what was installed matter more than the count. Seven of the
design skills — `design-taste-frontend`, `design-taste-frontend-v1`,
`high-end-visual-design`, `industrial-brutalist-ui`, `minimalist-ui`,
`redesign-existing-projects`, `stitch-design-taste` — carry their own hex
palettes and `font-family` stacks in their instructions, which is the thing the
design-token guard exists to refuse. And the two installs are not independent:
`gpt-taste` prescribes GSAP ScrollTrigger by name, so following it leads to the
`gsap` dependency that `doc/adr` has not agreed to.

## Decision

**Registration is not adoption, and this ADR records the distinction rather than
resolving it.** The three commands are a trial. They may be reverted with four
`rm`s and no code change, and until one of the revisit triggers below fires,
that remains true.

Two things hold while this is Proposed:

**The design-token guard is the boundary, and it is not relaxed for a skill.** A
skill that prescribes `#0A0A0A` and `font-family: 'Inter'` gets the same denial
as a hand-written literal. No skill's instructions override `tokens.css`,
`--primary` (`#E331D0`) stays the single accent, and a skill asking for the
retired purple is a defect wherever it comes from.

**Nothing 21st returns is pasted into `apps/web` under this ADR.** Adopting a
component-generation service is the decision this document declines to make on
Parul's behalf, not one it makes quietly by permitting the first paste.

## Reasoning

**This is not ADR 0031's category, and the difference is the whole argument.**
0031 governs MCP servers that reach *a customer's* systems — HubSpot, Stripe,
Xero — where letting the model call the tool directly destroys I1, because the
model becomes the thing fetching the number. 21st reaches nothing of a
customer's and returns nothing that becomes a number on a dashboard. It is a
developer-time source of markup, so I1 is not implicated and 0031's remedy does
not apply.

**One half of 0031's reasoning does transfer, in a different shape.** 0031 warns
that an MCP response arrives shaped like a tool result, which is what models are
trained to act on. 21st's responses are *code*. Code fetched from an external
service and pasted into `apps/web` is a supply-chain surface, and the failure
mode is quieter than a bad number: it looks like a component that works. That is
an argument for the token guard remaining the enforcement point, since it reads
every line before it lands, and against any workflow that treats generated
output as finished.

**Writing this as Accepted would assert reasoning nobody has given.** Why 21st
over the alternatives, whether a 21st component is a reference to be rewritten
against the tokens or a source to paste and de-hex, and what would make the
choice wrong are all unanswered. An ADR in this repository argues a decision;
inventing the argument is the failure mode `CLAUDE.md` names — *never invent a
resolution*. Proposed is the honest status for a thing that has been installed
and not yet chosen.

## What is open

Three questions, all of which must be answered before this can become Accepted:

1. **What is 21st for here** — component discovery, the AI sketch generation, or
   the theme CSS. Each implies a different boundary.
2. **How a 21st component meets the ADF tokens.** Reference to be rewritten, or
   source to paste and de-hex. Different workflows, different review burdens.
3. **What would make this wrong**, which is the revisit trigger a real decision
   carries and a trial does not.

GSAP is deliberately not settled here. If it is adopted, it needs its own ADR
arguing a second animation library against `framer-motion`, and the boundary
between them — that is a larger question than this one and should not ride along
on it.

## Revisit trigger

Whichever comes first:

- **`API_KEY_21ST` is set** and the server completes a request.
- **The first component in `apps/web` sourced from 21st.**
- **The first `gsap` import**, or `gsap` appearing in `apps/web/package.json`.
- **Any of the four untracked paths is committed**, which turns a local trial
  into a team-wide default.

At that point this ADR is either superseded by an Accepted one answering the
three open questions, or the installs are reverted and this is marked Rejected.
