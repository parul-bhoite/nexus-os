'use client'

import { useEffect, useId, useMemo, useRef, useState } from 'react'
import type { Turn } from '@/lib/agent-onboarding-client'
import { Empty } from '@/components/ui/States'

/**
 * The onboarding conversation, as read-only history — ADR 0069 phase 3.
 *
 * This is the other half of "the transcript is a first-class Brain source":
 * phase 1 showed the same turns live, while they were being produced. This
 * is the same shape of bubble, after the fact and searchable, reachable from
 * the Brain page's "Onboarding conversation" source and from a fact's detail
 * drawer via `anchorIndex`.
 *
 * **A log, not a live region.** `role="log"` names what this is to assistive
 * technology without an `aria-live` attribute — nothing here updates while a
 * reader has it open, so announcing changes would be announcing nothing.
 *
 * **Read-only on purpose.** No edit, no delete, no "add what you meant to
 * say" — correcting a fact found through this conversation happens where
 * every other correction does (Settings, a setup answer), not here. That is
 * P21's job, not phase 3's; see `CompanyBrainPage`'s own note to the same
 * effect.
 */

function SearchIcon() {
  return (
    <svg viewBox="0 0 16 16" fill="none" aria-hidden="true" className="h-4 w-4 shrink-0 text-ink-400">
      <circle cx="7" cy="7" r="4.75" stroke="currentColor" strokeWidth="1.4" />
      <path d="m13 13-2.6-2.6" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
    </svg>
  )
}

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

/** Wraps each case-insensitive match of `query` in `<mark>`, leaving the rest
 *  of the text untouched — plain text in, plain text out, when there is
 *  nothing to search for. */
function highlighted(text: string, query: string) {
  const needle = query.trim()
  if (!needle) return text
  const parts = text.split(new RegExp(`(${escapeRegExp(needle)})`, 'ig'))
  if (parts.length === 1) return text
  return parts.map((part, index) =>
    part.toLowerCase() === needle.toLowerCase() ? (
      <mark key={index} className="rounded-[0.2rem] bg-gold-200 px-0.5 text-ink-900">
        {part}
      </mark>
    ) : (
      <span key={index}>{part}</span>
    ),
  )
}

export function ConversationViewer({
  turns,
  anchorIndex = null,
}: {
  turns: Turn[]
  /** A turn to scroll to and highlight, set when opened from a fact's "From
   *  your onboarding conversation" block. `null` for an ordinary visit. */
  anchorIndex?: number | null
}) {
  const [query, setQuery] = useState('')
  const refs = useRef<Record<number, HTMLDivElement | null>>({})
  const inputId = useId()

  useEffect(() => {
    if (anchorIndex === null) return
    // The anchor must be visible, not filtered out by a search left over
    // from a previous visit.
    setQuery('')
    const node = refs.current[anchorIndex]
    node?.scrollIntoView({ behavior: 'smooth', block: 'center' })
    node?.focus()
  }, [anchorIndex])

  const filtered = useMemo(() => {
    const indexed = turns.map((turn, index) => ({ turn, index }))
    const needle = query.trim().toLowerCase()
    if (!needle) return indexed
    return indexed.filter(({ turn }) => turn.text.toLowerCase().includes(needle))
  }, [turns, query])

  if (turns.length === 0) {
    return (
      <Empty title="No onboarding conversation on record" action={null}>
        This workspace was not set up through the guided conversation — there is nothing here to
        search or read.
      </Empty>
    )
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="relative w-full max-w-xs">
        <span className="pointer-events-none absolute inset-y-0 left-3 flex items-center">
          <SearchIcon />
        </span>
        <input
          id={inputId}
          type="search"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Search the conversation…"
          aria-label="Search the onboarding conversation"
          className="h-11 w-full rounded-control border border-ink-200 bg-white pl-9 pr-3.5 text-body text-ink-800 placeholder:text-ink-300 transition-[border-color,box-shadow] duration-base ease-out focus:outline-none focus:ring-2 focus:ring-steel-500 focus:ring-offset-2 focus:ring-offset-white [@media(hover:hover)and(pointer:fine)]:hover:border-ink-300"
        />
      </div>

      {filtered.length === 0 ? (
        <Empty title="Nothing matches that search" action={null}>
          {turns.length} message{turns.length === 1 ? '' : 's'} in total — try a different word, or
          clear the search.
        </Empty>
      ) : (
        <div role="log" aria-label="Onboarding conversation transcript" className="flex flex-col gap-3">
          {filtered.map(({ turn, index }) => {
            const mine = turn.role === 'user'
            const anchored = index === anchorIndex
            return (
              <div
                key={index}
                ref={(node) => {
                  refs.current[index] = node
                }}
                tabIndex={-1}
                className={`flex outline-none ${mine ? 'justify-end' : 'justify-start'}`}
              >
                <div
                  className={`max-w-[34rem] rounded-panel px-4 py-3 text-body leading-relaxed ${
                    mine
                      ? 'rounded-br-md bg-ink-800 text-bone-50'
                      : 'rounded-bl-md border border-ink-100 bg-white text-ink-800'
                  } ${anchored ? 'ring-2 ring-steel-500 ring-offset-2 ring-offset-bone-50' : ''}`}
                >
                  <p>{highlighted(turn.text, query)}</p>
                  {turn.target ? (
                    <p
                      className={`mt-1.5 font-mono text-2xs uppercase tracking-[0.08em] ${
                        mine ? 'text-bone-200' : 'text-ink-400'
                      }`}
                    >
                      {turn.target}
                      {turn.scope !== null ? ` · L${turn.scope}` : ''}
                    </p>
                  ) : null}
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
