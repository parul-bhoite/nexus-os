# doc 14 — The dashboard build plan

**Narrows:** `doc/13` (shape) into a sequence.
**Depends on:** ADR 0029 (the brief), ADR 0030 (coverage), ADR 0031 (MCP as a
transport), ADR 0032 (provider tokens at rest — D27 answered *A with C*, shipped in
migration 0030).
**Does not supersede `doc/12`** — that still owns the phase numbering for the product as a
whole. This is the dashboard's own ordering, and every step below is written to
`CLAUDE.md`'s rule: one at a time, and a step is done when its acceptance test has run
green against a real Postgres, driven through the application rather than around it.

---

## 0. The shape being built

One **common command surface** at `/dashboard`, with a **left navigation panel** and a thin
header. The surface is the same for everyone; what it *contains* is composed from what the
reader's `ScopedSession` can reach.

### Reconciling "hide the tabs" with a left panel

These are two different things and both hold:

- **Gone:** the seven-department **tab rail** that currently gates a director page, and the
  department tabs as the primary way into the product. A founder does not think in
  departments; they think *what needs me today*.
- **Added:** a **left panel** as global navigation — how you get to a place, not what
  decides whether the place will speak to you.

The mock's 32-item sidebar is the anti-pattern: it groups by feature name, so it grows once
per capability. Ours groups by **what a thing is**, so it stays roughly fixed as the product
fills in.

```
  Today                    the command surface — the default route
  ───────────────
  Directors                Chief of Staff · Marketing · Sales · Finance
                           Operations · People · Strategy
  ───────────────
  Your data                Workspace setup
  ───────────────
  Settings                 Workspace · Account
```

**Corrected while building S1.** This sketch had four entries under *Your data* and four
under *Settings*. Only `/onboarding`, `/settings` and `/account` exist — a nav entry
pointing at a route nobody built is a 404 with a friendly name — so the group holds what
is real and grows when the pages do. Eleven destinations today.

The **Directors** group is composed per viewer — a Marketing
contributor sees one entry, not seven greyed out. Greying out advertises what somebody
cannot have; omitting is the same rule `DirectorPage` already follows for empty tabs.

**The header carries only what is about *who and where you are*:** the entity switcher
(`EntitySwitcher` exists), the account menu, and — later — search. It is not a second
navigation. If it ends up with more than three controls, the third belongs in the panel.

---

## 1. The regions of the common surface

| # | Region | Provenance | Status |
|---|---|---|---|
| 1 | Morning brief | measured | **Live** — ADR 0029. Three states, four item kinds |
| 2 | Where the product is | counted | **Live** — ADR 0030. Three bands over 89 |
| 3 | Measured today | measured | **Live** — `BlockCard`, identical to the director page |
| 4 | Open on your side | needs you | **Live** — questions only; sources are region 2's |
| 5 | The seven directors | mixed | **Live** — the tab rail, demoted to a summary |
| 6 | Company Brain | you told us | **Live** — the fields plus the assumptions block |

All six ship, in that order. Coverage sits above the questions deliberately: its *not built
yet* band is what makes *"28 more are waiting on us"* legible a moment later, and the
reverse order reads as a list of chores with the reason arriving too late.

---

## 2. Sources: the honest map

There are **16 sources**. Only **9 are connectable**. This is the fact that shapes the whole
connector effort, and it is easy to get wrong by reading the tile copy alone.

| Source | Origin | Tiles blocked | How it arrives |
|---|---|---:|---|
| `ops_layer` | **ours** | 23 | Projects and tasks **inside NEXUS** — a feature we build |
| `accounting` | connector | 20 | Xero · QuickBooks · Stripe |
| `language_model` | **key** | 13 | Our API key. Absent is *supported* (ADR 0011) |
| `crm` | connector | 12 | HubSpot · Salesforce · Pipedrive · Zoho |
| `roster` | **ours** | 10 | The team list we hold |
| `history` | **time** | 9 | Accrues. Nothing to connect — renders `WARMING` |
| `onboarding` | **ours** | 9 | The answers already given |
| `crawl` | **ours** | 6 | Our own fetch of the customer's site |
| `documents` | **ours** | 5 | Uploads we index |
| `dataforseo` | connector | 5 | **Blocked — D2, no provider** |
| `ga4` | connector | 4 | Google Analytics |
| `enrichment` | connector | 3 | Contact enrichment |
| `ads` | connector | 3 | Meta · Google Ads |
| `tender_feed` | connector | 2 | Tender feeds |
| `search_console` | connector | 0 | No tile requires it yet |
| `pagespeed` | connector | 0 | **Blocked — D3** |

**53 capability-requirements are first-party, 49 are connectors, 13 a key, 9 time.**

Two consequences that must not be lost:

1. **The single largest blocker is not a connector.** `ops_layer` blocks 23 tiles and is
   something NEXUS *contains*, not something anybody connects. No MCP server can supply it.
2. **A connector unlocks nothing on its own.** `implemented` is 12. Connecting every source
   in existence would move the figure-producing count from 2 to 2, because the other 77
   capabilities have no calculator. **Every connector step below is therefore paired with at
   least one calculator**, or it ships something a customer can connect and not see.

---

## 3. MCP: how it is used, and how it is not

**Settled in ADR 0031**, which carries the full argument, the consequences and the
revisit triggers. This section is the shape; that is the reasoning, and the two must not
drift — if they disagree, the ADR wins.

### The rule

> **The API process is the MCP client. The model never sees an MCP server.**

MCP is used as a **transport for deterministic fetches made from code** — not as a tool
surface handed to a language model. A model that called a CRM's MCP server and reported
what it found would be *fetching*, and invariant **I1** says every number is fetched or
computed in code. The same call made by an adapter, landed in the database, and read back
through `retrieval/` under a `ScopedSession` satisfies I1, I2 and I3 unchanged.

This is what makes MCP compatible with this product rather than a shortcut around it.

### The adapter shape

One interface, two transports, so the choice per provider is an implementation detail and
never leaks into the capability model:

```
app/connectors/
  contracts.py     SourceAdapter and Transport protocols, ToolCall, Fetched
  mcp.py           McpTransport — tools called by name, from code
  rest.py          RestTransport — the fallback
  <provider>.py    picks a transport; nothing above can tell which
```

Flatter than the sketch, matching the package's existing shape (`rate_limit.py`,
`domain_check.py` are already flat). Both transports and the contracts shipped in S8.

`connectors/rate_limit.py` and `connectors/domain_check.py` already exist and stay.

### The untrusted boundary

Whatever comes back from a provider — MCP or REST — is **customer data from a third party**
and is treated exactly as crawled HTML already is: data, never instruction. A deal note
reading *"ignore previous instructions"* must be as inert as a competitor's web page. This
matters more for MCP than for REST, because an MCP response is shaped like a tool result and
tool results are the thing models are trained to act on.

### Per-provider status

Verified September 2026. **The plan does not assume any of this stays true** — each connector
step re-checks at implementation time, and the adapter shape means a wrong guess costs one
file.

| Provider | Official MCP server | First choice |
|---|---|---|
| HubSpot | Yes — vendor-hosted, remote | **MCP** |
| Salesforce | Yes — vendor-hosted | **MCP** |
| Stripe | Yes — documented at `docs.stripe.com/mcp` | **MCP** |
| Xero | Yes — vendor-hosted | **MCP** |
| Pipedrive | Yes — native, launched June 2026 | **MCP** |
| Zoho CRM | Analytics only; CRM not confirmed | REST, re-check |
| QuickBooks | Not confirmed | REST |
| Google Analytics | Not confirmed | REST |
| Search Console · Ads · Enrichment · Tender feeds | Not surveyed | REST until surveyed |

**Third-party aggregator MCPs are out of scope.** Several exist that would cover most of this
table in one integration. They would also put every customer's CRM and accounting data
through a party with no contract with us, which is a trust-boundary decision and not an
implementation convenience. If it is ever wanted, it is an ADR of its own.

---

## 4. The steps

Each has one acceptance test. Nothing starts until the previous has run green.

**S1–S8 are done** and on `feature/dashboard-command-surface`, one commit each.
**S9–S11 are blocked**, and on decisions rather than on effort — see §6.

### S1 — The shell: left panel and header ✅

> **Done.** Two corrections while building: the planned four-entry *Your data* group is one, because three of those pages do not exist; and the shell took over the single `/api/dashboards` fetch that `DirectorPage` had been making a second time.

Build the panel, the header and the composed navigation. Remove the department tab rail.
**Acceptance:** every existing route renders inside the new shell; a Department Manager
holding one department sees one Directors entry and no others; keyboard traversal and focus
states work; `tsc`, `vitest`, `next lint` green.

### S2 — `coverage()` in the registry ✅

> **Done.** Every figure in the design's first draft was estimated and every one was wrong — the denominator counted the one `RULE`, and a band called *unlockable by answering* held seven where the truth is zero.

ADR 0030's recorded debt. Derive the three bands rather than typing them.
**Acceptance:** a test asserts `coverage()`, `completeness()` and `openable_count()` share
the 89 denominator, and that the bands sum to it. No count appears as a literal in any
component.

### S3 — `domain/brief.py` and the brief region ✅

> **Done.** The design negated check labels (*"Not served over HTTPS"*), which generalises to nonsense — *"Not Page has a title"*. Labels are used verbatim.

ADR 0029. `BriefItem`, the ranking, the three states, the four item kinds. Scope-composed.
**Acceptance:** against Neon, an Owner and a Marketing-only contributor both receive a
brief; the ranking matches the calculator's weights; the *not measured* state appears for a
workspace with no crawl and is distinguishable from *all held*; no model is called.

### S4 — The Coverage region ✅

> **Done.**

Renders S2's output.
**Acceptance:** the rendered numbers change when a capability's `implemented` flag changes,
proving nothing is hard-coded.

### S5 — Open on your side ✅

> **Done.** Of twenty-nine open questions, exactly one changes a figure today.

Questions only, with the honest framing: answering informs, it does not unlock.
**Acceptance:** every listed question names a capability that consumes it; a question with
no consumer cannot render.

### S6 — The directors row ✅

> **Done.** The open question is answered: four states, and `empty` is unreachable today with a test asserting the reason rather than the outcome.

**Acceptance:** composed per viewer; a department the reader cannot reach is absent, not
greyed; the status line for a department holding nothing is settled and tested.

### S7 — Measured today, and Company Brain ✅

> **Done.** `figure_out` and `narration_out` are module level and shared, so two renderings of one figure is structurally impossible.

Largely a move of existing components onto the surface.
**Acceptance:** the figure and narration are byte-identical to what the director page serves
today — this step changes location, not content.

### S8 — The connector spine ✅ — ADR 0031

> **Done.** The no-model rule is asserted as an import graph. Two MCP protocol details would have become I10 violations — see the commit.

`SourceAdapter`, both transports, credential storage, the untrusted-boundary rule.
**Acceptance:** two adapters over a fake provider — one MCP transport, one REST — land
identical rows through `retrieval/`; a test asserts no adapter output can reach a model
without passing through a calculator; credentials are never logged.

### S9 — The first real connector, paired with a calculator ⛔ blocked
**CRM via HubSpot's official MCP server**, plus one calculator so something appears.
Chosen over accounting because **D7 is open** — whether Finance brings accounting in at all
is undecided, and building its connector first would be building on a decision nobody has
made.
**Acceptance:** a real HubSpot sandbox connects, rows land scoped, one tile moves from
`locked` to a figure with its denominator, and disconnecting returns it to `locked` rather
than to a zero.

### S10 — `ops_layer` ⛔ needs its own plan
The largest blocker, and a product to build rather than a connector to write: projects and
tasks inside NEXUS, feeding 23 capabilities. **This needs its own plan** — it is named here
so the sequence is honest about where the weight actually is.

### S11 — The remaining connectors ⛔ blocked behind S9
Accounting (after D7), GA4, ads, enrichment, tender feeds. Each paired with at least one
calculator, each re-checking its MCP status at implementation time.

---

## 5. What S9 is waiting on

Nothing here is work. Each is a decision or a credential, and the sequence after them is
short.

| # | Blocker | Who |
|---|---|---|
| ~~1~~ | ~~**D27 — how a provider token is held at rest**~~ — **answered: A with C.** Migration 0030 adds `credentials` and `credential_key_id`, applied to Neon; `app/connectors/credentials.py` seals the refresh token only | ✅ done |
| ~~2~~ | ~~**`cryptography`**~~ — a base dependency, not an optional extra: a connector that cannot decrypt its token is not a supported state | ✅ done |
| ~~3~~ | ~~**`NEXUS_CONNECTOR_SECRET_KEY`**~~ — a real `Settings` field, in `_DEPLOYED_REQUIRES` and in `doc/DEPLOYMENT-ENV.md`. Generate with `Fernet.generate_key()` | ✅ **set this in `.env` before S9** |
| 4 | **The official `mcp` SDK.** Not a dependency. `McpTransport.Session` is the one seam it plugs into; hand-rolling JSON-RPC session setup, version negotiation, SSE framing and OAuth against five vendors is the kind of thing that works in a test and fails on the third provider | Parul — a dependency choice |
| 5 | **A HubSpot developer app**: client id, client secret, redirect URI, and a sandbox portal to read | Parul |
| 6 | **D7** — whether Finance brings accounting in at all. Not a blocker for S9, which is why S9 is CRM; it blocks the accounting half of S11 | Parul |

Every one of these is in `.env.example` with the reason, and in `FUTURE` in
`tests/test_config_gates.py` with the step that wires it — so adding one without saying
why fails the build.

## 6. Not in this plan

- **Auto-narration.** ADR 0028 and 0029 both put prose behind a decision; nothing here
  changes that.
- **A composite company score.** Refused by ADR 0029 and 0030 on the same grounds.
- **Write scope on any connector.** `SourceEntry.read_only` is `True` for every row and A5
  makes write a separate, heavier ask.
- **Aggregator MCPs.** A trust-boundary decision needing its own ADR.
- **`dataforseo` (D2) and `pagespeed` (D3).** Both blocked on decisions, not on work.
- **Search.** The header reserves room; nothing fills it yet.
