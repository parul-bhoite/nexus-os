import type { Brain } from '@/lib/settings-client'
import type { Question } from '@/lib/onboarding-client'
import type { Turn } from '@/lib/agent-onboarding-client'
import type { Fact } from '@/lib/brain-facts'

/**
 * The Company Brain's source layer — ADR 0069 phase 3.
 *
 * Phase 2 built the facts table: *what* NEXUS knows. This is the second
 * layer the brief asks for — *how it came to know it* — named as three
 * first-class sources rather than left implicit in each fact's provenance
 * tag: **Onboarding conversation**, **Website**, **You**. The three map
 * directly onto `buildFacts`' own inputs, so this file takes the same three
 * wires `CompanyBrainPage` already fetches rather than a fourth endpoint.
 */

export type SourceId = 'conversation' | 'website' | 'you'

export type Source = {
  id: SourceId
  label: string
  count: number
  description: string
  /** Whether this source produced anything for this workspace. A workspace
   *  onboarded through the catalogue (or never onboarded) has `count: 0` and
   *  `available: false` for `conversation` — not an error, just absent. */
  available: boolean
}

function dedupeUrls(urls: string[]): string[] {
  return Array.from(new Set(urls.filter((url) => /^https?:\/\//i.test(url))))
}

/**
 * The three sources, with a count and a one-line description each.
 *
 * `pagesRead` is `AgentState.pages_read` — the crawl's own record of what it
 * fetched, preferred over `brain.provenance` because it is pages rather than
 * a flat citation list. When a workspace predates the agent (or the agent
 * state could not be read), it is empty and `brain.provenance` is used
 * instead, filtered to things that are actually URLs — the full research
 * session is deliberately not surfaced here (see `ConversationViewer`'s
 * neighbour copy in `CompanyBrainPage`), only the pages it visited.
 */
export function summariseSources(
  brain: Brain | null,
  questions: Question[],
  turns: Turn[],
  pagesRead: string[] = [],
): Source[] {
  const pages = pagesRead.length > 0 ? dedupeUrls(pagesRead) : dedupeUrls(brain?.provenance ?? [])
  const answered = questions.filter((q) => q.value !== null && q.value !== undefined).length

  return [
    {
      id: 'conversation',
      label: 'Onboarding conversation',
      count: turns.length,
      description:
        turns.length > 0
          ? `${turns.length} message${turns.length === 1 ? '' : 's'}`
          : 'No onboarding conversation is on record for this workspace.',
      available: turns.length > 0,
    },
    {
      id: 'website',
      label: 'Website',
      count: pages.length,
      description:
        pages.length > 0
          ? `Read your website — ${pages.length} page${pages.length === 1 ? '' : 's'}`
          : 'No pages have been read yet.',
      available: pages.length > 0,
    },
    {
      id: 'you',
      label: 'You',
      count: answered,
      description:
        answered > 0
          ? `What you told us — ${answered} answer${answered === 1 ? '' : 's'}`
          : 'Nothing answered directly yet.',
      available: answered > 0,
    },
  ]
}

/**
 * The onboarding turn(s) that produced a fact — chat-to-knowledge.
 *
 * `fact.field` and `turn.target` are two different shapes of the same
 * catalogue key (see the comment on `Fact.field`): a brain field's is the
 * full declared-field key (`brain.target_customers`) and matches a turn's
 * `target` exactly; an answered question's is the bare catalogue key
 * (`approval_threshold`) and is matched as the trailing segment of a
 * `fact.<department>.<name>` target, which coincides with the declared name
 * for some fields and not others. Where it does not coincide, this correctly
 * returns nothing rather than fabricating a link — a wrong citation is worse
 * than an absent one.
 *
 * Only `role: 'user'` turns qualify: an agent's own question is never the
 * source of a fact, the person's answer is.
 */
export function linkFactToTurns(
  fact: Fact,
  turns: Turn[],
): { turn: Turn; index: number }[] {
  if (!fact.field) return []
  return turns
    .map((turn, index) => ({ turn, index }))
    .filter(
      ({ turn }) =>
        turn.role === 'user' &&
        turn.target !== null &&
        (turn.target === fact.field || turn.target.endsWith(`.${fact.field}`)),
    )
}
