'use client'

import { useCallback, useEffect, useId, useState } from 'react'
import { BrainGraph } from '@/components/brain/BrainGraph'
import { ConversationViewer } from '@/components/brain/ConversationViewer'
import { Badge } from '@/components/ui/Data'
import { Sheet } from '@/components/ui/Overlay'
import { Empty, Failed } from '@/components/ui/States'
import { Loading, TableSkeleton } from '@/components/ui/Skeleton'
import { Tabs, TabPanel } from '@/components/ui/Tabs'
import {
  assumptionFacts,
  buildFacts,
  matchesSearch,
  type Fact,
  type FactSourceKind,
} from '@/lib/brain-facts'
import { linkFactToTurns, summariseSources, type Source } from '@/lib/brain-sources'
import { fetchQuestions } from '@/lib/onboarding-client'
import { fetchBrain, type Brain } from '@/lib/settings-client'
import { readState, type Turn } from '@/lib/agent-onboarding-client'

/**
 * The Company Brain page — ADR 0069 phases 2 and 3.
 *
 * Every fact NEXUS holds, with its provenance, built from three endpoints
 * that already existed for other screens: `fetchBrain()` (the structured,
 * audited record), `fetchQuestions()` (what the founder answered) and
 * `readState()` (the onboarding transcript, phase 1's own agent state).
 * `lib/brain-facts.ts` owns the facts mapping and `lib/brain-sources.ts` the
 * source summary and the chat-to-knowledge link; both are tested on their
 * own. This component is the view over all three: a search box, the
 * `SourcesSection` (phase 3's "two layers" made explicit), a
 * Table/Graph/Conversation toggle and a detail drawer.
 *
 * ## The three data states
 *
 * `loading` renders `TableSkeleton` — the shape of the real table, not a blank
 * page. `unavailable` (the brain never audited, or the audit came back empty)
 * is a real `Empty` with somewhere to go, never a table with no rows and no
 * explanation. `failed` (the fetch itself broke) offers a retry. These are
 * three different facts and the state machine below keeps them that way
 * rather than collapsing "no rows" into one shape.
 *
 * **The conversation source is independently optional.** `readState()` is
 * never allowed to fail this page — a workspace onboarded through the
 * retired catalogue, one never onboarded at all, or a transient read failure
 * all resolve to an empty `turns[]` rather than `status: 'failed'`. The
 * Sources section and the Conversation tab then simply say there is nothing
 * here, same as `ConversationViewer`'s own empty state.
 *
 * ## Deferred, stated in the UI rather than silently absent
 *
 * The full web-research session (`research` JSONB) is not on this wire and
 * is not shown — only the pages read, as the Website source. Correcting a
 * fact or adding new information after onboarding (P21) is likewise not
 * here: the conversation is read-only history, and `FactDetail`'s closing
 * note says so rather than rendering a control that does nothing.
 */

const TAG_CLASS: Record<FactSourceKind, string> = {
  read: 'bg-steel-100 text-steel-700',
  inferred: 'bg-gold-100 text-gold-700',
  you: 'bg-clay-100 text-clay-700',
}

type LoadState =
  | { status: 'loading' }
  | { status: 'failed'; message: string }
  | {
      status: 'ready'
      brain: Brain | null
      facts: Fact[]
      assumptions: ReturnType<typeof assumptionFacts>
      /** The onboarding transcript, in `seq` order — empty for a workspace
       *  onboarded through the catalogue, never onboarded, or whose agent
       *  state could not be read. Never an error on its own; see `load`. */
      turns: Turn[]
      sources: Source[]
    }

function SearchIcon() {
  return (
    <svg viewBox="0 0 16 16" fill="none" aria-hidden="true" className="h-4 w-4 shrink-0 text-ink-400">
      <circle cx="7" cy="7" r="4.75" stroke="currentColor" strokeWidth="1.4" />
      <path d="m13 13-2.6-2.6" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
    </svg>
  )
}

export function CompanyBrainPage() {
  const [state, setState] = useState<LoadState>({ status: 'loading' })
  const [query, setQuery] = useState('')
  const [view, setView] = useState<'table' | 'graph' | 'conversation'>('table')
  const [openFactId, setOpenFactId] = useState<string | null>(null)
  const [anchorTurnIndex, setAnchorTurnIndex] = useState<number | null>(null)
  const tabsId = useId()

  const load = useCallback(() => {
    setState({ status: 'loading' })
    Promise.all([
      fetchBrain(),
      fetchQuestions(),
      // The agent state is never allowed to fail this page: a workspace
      // onboarded through the old catalogue, never onboarded at all, or hit
      // by a transient read failure all resolve to "no conversation source"
      // rather than a page-level error — see `AgentState.turns` on
      // `readState`'s own type for why an inactive state is not an error
      // either.
      readState().catch(() => null),
    ])
      .then(([brain, questions, agentState]) => {
        const turns = agentState?.turns ?? []
        const facts = buildFacts(brain, questions.questions)
        setState({
          status: 'ready',
          brain,
          facts,
          assumptions: assumptionFacts(brain),
          turns,
          sources: summariseSources(brain, questions.questions, turns, agentState?.pages_read ?? []),
        })
        // Land on the view that actually has content. Every agent-onboarded
        // workspace has a conversation before it has assembled facts (the agent
        // writes turns, and the brain only assembles at `finish`), so defaulting
        // to the table there would open on an empty tab while the real content
        // sits one tab over.
        setView(facts.length > 0 ? 'table' : turns.length > 0 ? 'conversation' : 'table')
      })
      .catch((cause: unknown) => {
        setState({
          status: 'failed',
          message: cause instanceof Error ? cause.message : 'Could not load the Company Brain.',
        })
      })
  }, [])

  useEffect(() => {
    load()
  }, [load])

  if (state.status === 'loading') {
    return (
      <Loading label="Loading the Company Brain…">
        <TableSkeleton rows={6} columns={6} />
      </Loading>
    )
  }

  if (state.status === 'failed') {
    return <Failed retry={load}>{state.message}</Failed>
  }

  const { brain, facts, assumptions, turns, sources } = state

  const brainIsEmpty =
    !brain || Boolean(brain.unavailable_reason) || (facts.length === 0 && assumptions.length === 0)

  // The pure empty state is for a workspace with *nothing* to show — no facts,
  // no assumptions, and no conversation. A workspace mid-onboarding has an empty
  // brain but a real conversation, and that conversation is a first-class source
  // (ADR 0069 phase 3): it must not be hidden behind "no audit has run yet". So
  // this returns only when there is also no transcript; otherwise the page
  // renders below with the conversation as its content and the fact views in
  // their own empty states. Distinct from `loading` and `failed` above.
  if (brainIsEmpty && turns.length === 0) {
    return (
      <Empty
        title="No audit has run yet"
        action={{ label: 'Go to setup', href: '/onboarding' }}
      >
        {brain?.unavailable_reason
          ? brain.unavailable_reason
          : 'The Company Brain fills in as NEXUS reads your website and you answer setup questions. Once that has happened, every fact it holds will be listed here with where it came from.'}
      </Empty>
    )
  }

  const filtered = facts.filter((fact) => matchesSearch(fact, query))
  const openFact = facts.find((fact) => fact.id === openFactId) ?? null

  const openConversationAt = (turnIndex: number) => {
    setOpenFactId(null)
    setAnchorTurnIndex(turnIndex)
    setView('conversation')
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-meta text-ink-500">
          {brain && !brain.unavailable_reason && facts.length > 0
            ? `Version ${brain.version} · built by ${brain.generated_by}`
            : 'Not assembled yet — your conversation is on record below and the Brain fills in once setup finishes.'}
        </p>
        <div className="relative w-full max-w-xs sm:w-72">
          <span className="pointer-events-none absolute inset-y-0 left-3 flex items-center">
            <SearchIcon />
          </span>
          <input
            type="search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search facts…"
            aria-label="Search facts by item, value or source"
            className="h-11 w-full rounded-control border border-ink-200 bg-white pl-9 pr-3.5 text-body text-ink-800 placeholder:text-ink-300 transition-[border-color,box-shadow] duration-base ease-out focus:outline-none focus:ring-2 focus:ring-steel-500 focus:ring-offset-2 focus:ring-offset-white [@media(hover:hover)and(pointer:fine)]:hover:border-ink-300"
          />
        </div>
      </div>

      <SourcesSection
        sources={sources}
        onViewConversation={() => {
          setAnchorTurnIndex(null)
          setView('conversation')
        }}
      />

      {assumptions.length > 0 ? (
        <section
          aria-labelledby="assumptions-heading"
          className="rounded-data border-l-[3px] border-gold-500 bg-gold-100 px-5 py-4"
        >
          <p id="assumptions-heading" className="text-meta font-medium text-gold-700">
            Assumptions NEXUS is working from
          </p>
          <p className="mt-1 max-w-prose text-meta leading-relaxed text-ink-600">
            Guessed rather than read or confirmed — the part of the Brain you are expected to
            audit. A later crawl that disagrees raises a re-confirmation; it never silently
            overwrites one of these.
          </p>
          <ul className="mt-3 flex flex-col gap-2">
            {assumptions.map((assumption) => (
              <li key={assumption.id} className="flex items-start gap-2.5 text-body text-ink-800">
                <Badge tone="attention" className="mt-0.5 shrink-0">
                  assumption · unconfirmed
                </Badge>
                <span className="leading-relaxed">{assumption.text}</span>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      <Tabs
        id={tabsId}
        label="View the facts as"
        tabs={[
          { key: 'table', label: 'Table' },
          { key: 'graph', label: 'Graph' },
          { key: 'conversation', label: 'Conversation', count: turns.length > 0 ? turns.length : undefined },
        ]}
        active={view}
        onChange={(key) => setView(key as 'table' | 'graph' | 'conversation')}
        className="w-fit"
      />

      <TabPanel
        id={tabsId}
        tab="table"
        ariaLabel="Facts table"
        className={view === 'table' ? undefined : 'hidden'}
      >
        <FactsTable facts={filtered} total={facts.length} onOpen={setOpenFactId} />
      </TabPanel>
      <TabPanel
        id={tabsId}
        tab="graph"
        ariaLabel="Facts graph"
        className={view === 'graph' ? undefined : 'hidden'}
      >
        <div className="surface px-5 py-6">
          {facts.length > 0 ? (
            <BrainGraph facts={facts} onSelect={setOpenFactId} selectedFactId={openFactId} />
          ) : (
            <Empty title="No facts to graph yet" action={null}>
              The relationship graph draws itself from the Brain&rsquo;s facts, which assemble once
              setup finishes. Your onboarding conversation is on the Conversation tab.
            </Empty>
          )}
        </div>
      </TabPanel>
      <TabPanel
        id={tabsId}
        tab="conversation"
        ariaLabel="Onboarding conversation"
        className={view === 'conversation' ? undefined : 'hidden'}
      >
        <ConversationViewer turns={turns} anchorIndex={anchorTurnIndex} />
      </TabPanel>

      <p className="max-w-prose text-meta leading-relaxed text-ink-500">
        Conflict precedence: your confirmation &gt; connected system &gt; crawl &gt; inference.
        A later crawl that contradicts a confirmed fact raises a re-confirmation, never an
        overwrite.
      </p>

      <Sheet
        open={openFact !== null}
        onClose={() => setOpenFactId(null)}
        title={openFact?.item ?? ''}
        description={openFact ? `${openFact.kind} · ${openFact.scope}` : undefined}
      >
        {openFact ? (
          <FactDetail fact={openFact} turns={turns} onOpenConversation={openConversationAt} />
        ) : null}
      </Sheet>
    </div>
  )
}

/**
 * The source layer — ADR 0069 phase 3's "two layers" made explicit. Same
 * facts as the table above; this names *where* they came from, as three
 * first-class sources rather than left implicit in each row's provenance
 * tag.
 */
function SourcesSection({
  sources,
  onViewConversation,
}: {
  sources: Source[]
  onViewConversation: () => void
}) {
  return (
    <section aria-labelledby="sources-heading" className="flex flex-col gap-3">
      <div>
        <h2 id="sources-heading" className="text-card font-medium text-ink-800">
          Where this Brain came from
        </h2>
        <p className="mt-1 max-w-prose text-meta leading-relaxed text-ink-500">
          What NEXUS knows, and the record of how it learned it — every fact above traces back
          to one of these.
        </p>
      </div>
      <ul className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        {sources.map((source) => (
          <li key={source.id} className="surface flex flex-col gap-2 px-4 py-4">
            <p className="text-body font-medium text-ink-800">{source.label}</p>
            <p className="text-meta leading-relaxed text-ink-600">{source.description}</p>
            {source.id === 'conversation' && source.available ? (
              <button
                type="button"
                onClick={onViewConversation}
                className="mt-1 min-h-11 w-fit rounded-control px-2.5 text-meta font-medium text-steel-600 transition-colors duration-micro ease-out focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-steel-500 focus-visible:ring-offset-2 [@media(hover:hover)and(pointer:fine)]:hover:text-steel-700"
              >
                View conversation
              </button>
            ) : null}
          </li>
        ))}
      </ul>
      <p className="max-w-prose text-meta leading-relaxed text-ink-400">
        The research session behind the website read is not shown in detail here — only the
        pages it visited are, as the Website source above.
      </p>
    </section>
  )
}

function FactsTable({
  facts,
  total,
  onOpen,
}: {
  facts: Fact[]
  total: number
  onOpen: (id: string) => void
}) {
  if (facts.length === 0) {
    if (total === 0) {
      return (
        <Empty title="No facts yet" action={null}>
          The Brain assembles its facts once setup finishes. Your onboarding conversation is
          already on record — see the Conversation tab.
        </Empty>
      )
    }
    return (
      <Empty title="Nothing matches that search" action={null}>
        {total} fact{total === 1 ? '' : 's'} in total — try a different word, or clear the
        search.
      </Empty>
    )
  }

  return (
    <div className="surface overflow-hidden">
      <table className="w-full border-collapse text-left">
        <caption className="sr-only">Every fact NEXUS holds, with its provenance</caption>
        <thead className="hidden md:table-header-group">
          <tr className="border-b border-ink-100 bg-bone-50">
            {['Item', 'Value', 'Kind', 'Scope', 'Source', 'Updated', ''].map((header) => (
              <th
                key={header || 'actions'}
                scope="col"
                className="px-4 py-2.5 text-2xs font-medium uppercase tracking-[0.08em] text-ink-500"
              >
                {header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="flex flex-col md:table-row-group">
          {facts.map((fact) => (
            <tr
              key={fact.id}
              className="flex flex-col gap-1 border-b border-ink-100 px-4 py-3 last:border-0 md:table-row md:px-0 md:py-0"
            >
              <td data-label="Item" className="text-body font-medium text-ink-900 md:px-4 md:py-3">
                {fact.item}
              </td>
              <td data-label="Value" className="max-w-sm text-body text-ink-700 md:px-4 md:py-3">
                {fact.value}
              </td>
              <td data-label="Kind" className="md:px-4 md:py-3">
                <Badge tone="outline">{fact.kind}</Badge>
              </td>
              <td data-label="Scope" className="font-mono text-meta text-ink-600 md:px-4 md:py-3">
                {fact.scope}
              </td>
              <td data-label="Source" className="md:px-4 md:py-3">
                <span
                  className={`inline-flex rounded px-1.5 py-0.5 font-mono text-2xs ${TAG_CLASS[fact.sourceKind]}`}
                >
                  {fact.sourceLabel}
                </span>
              </td>
              <td data-label="Updated" className="font-mono text-meta text-ink-500 md:px-4 md:py-3">
                {fact.updated}
              </td>
              <td className="md:px-4 md:py-3">
                <button
                  type="button"
                  onClick={() => onOpen(fact.id)}
                  className="min-h-11 rounded-control px-2.5 text-meta font-medium text-steel-600 transition-colors duration-micro ease-out focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-steel-500 focus-visible:ring-offset-2 [@media(hover:hover)and(pointer:fine)]:hover:text-steel-700"
                >
                  View source
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function FactDetail({
  fact,
  turns,
  onOpenConversation,
}: {
  fact: Fact
  turns: Turn[]
  onOpenConversation: (turnIndex: number) => void
}) {
  const linked = linkFactToTurns(fact, turns)

  return (
    <div className="flex flex-col gap-5">
      <div>
        <p className="text-2xs font-medium uppercase tracking-[0.08em] text-ink-400">Value</p>
        <p className="mt-1 text-body leading-relaxed text-ink-800">{fact.value}</p>
      </div>

      {linked.length > 0 ? (
        <div className="rounded-data border-l-[3px] border-steel-500 bg-steel-100 px-3.5 py-3">
          <p className="text-2xs font-medium uppercase tracking-[0.08em] text-steel-700">
            From your onboarding conversation
          </p>
          <ul className="mt-2 flex flex-col gap-2">
            {linked.map(({ turn, index }) => (
              <li key={index} className="text-meta leading-relaxed text-ink-700">
                &ldquo;{turn.text}&rdquo;
              </li>
            ))}
          </ul>
          <button
            type="button"
            onClick={() => onOpenConversation(linked[0].index)}
            className="mt-2 min-h-11 rounded-control px-2.5 text-meta font-medium text-steel-700 transition-colors duration-micro ease-out focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-steel-500 focus-visible:ring-offset-2 [@media(hover:hover)and(pointer:fine)]:hover:text-steel-900"
          >
            Open in conversation
          </button>
        </div>
      ) : null}

      <dl className="grid grid-cols-2 gap-x-4 gap-y-3 text-body">
        <div>
          <dt className="text-2xs font-medium uppercase tracking-[0.08em] text-ink-400">Kind</dt>
          <dd className="mt-0.5 text-ink-700">{fact.kind}</dd>
        </div>
        <div>
          <dt className="text-2xs font-medium uppercase tracking-[0.08em] text-ink-400">Scope</dt>
          <dd className="mt-0.5 font-mono text-ink-700">{fact.scope}</dd>
        </div>
        {fact.department ? (
          <div>
            <dt className="text-2xs font-medium uppercase tracking-[0.08em] text-ink-400">
              Department
            </dt>
            <dd className="mt-0.5 text-ink-700">{fact.department}</dd>
          </div>
        ) : null}
        <div>
          <dt className="text-2xs font-medium uppercase tracking-[0.08em] text-ink-400">
            Updated
          </dt>
          <dd className="mt-0.5 font-mono text-ink-700">{fact.updated}</dd>
        </div>
      </dl>

      {fact.why ? (
        <div>
          <p className="text-2xs font-medium uppercase tracking-[0.08em] text-ink-400">
            Why NEXUS asked
          </p>
          <p className="mt-1 text-body leading-relaxed text-ink-700">{fact.why}</p>
        </div>
      ) : null}

      <div>
        <p className="text-2xs font-medium uppercase tracking-[0.08em] text-ink-400">
          Built from
        </p>
        {fact.sources.length > 0 && fact.sources[0] !== 'you' ? (
          <ul className="mt-1.5 flex flex-col gap-1">
            {fact.sources.map((source) => (
              <li key={source} className="truncate text-meta text-ink-600">
                {source}
              </li>
            ))}
          </ul>
        ) : (
          <p className="mt-1 text-meta leading-relaxed text-ink-600">
            Something you told NEXUS directly, during setup — there is no crawled page or
            connected system behind this one.
          </p>
        )}
      </div>

      <p className="rounded-data bg-bone-100 px-3.5 py-3 text-meta leading-relaxed text-ink-500">
        Correcting or deleting a fact from here is not available yet. For now, change it where
        it was set — a brain field in <span className="font-medium">Settings</span>, or an
        answer on the relevant setup question.
      </p>
    </div>
  )
}
