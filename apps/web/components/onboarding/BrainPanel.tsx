'use client'

import { AnimatePresence, motion } from 'framer-motion'
import type { AgentState } from '@/lib/agent-onboarding-client'
import { SCOPE_LABEL } from '@/lib/agent-onboarding-client'
import { duration, easing, useMotionSafe } from '@/lib/motion'

/**
 * The live Company Brain panel (ADR 0069 phase 1): the wireframe's `.brainp`,
 * filled in as the conversation runs rather than read back at the end.
 *
 * Every row carries its provenance, because that is the product's whole claim
 * — "never invent a number, always show the source" — made visible during the
 * first minute rather than promised in copy. The four groups below mirror the
 * wireframe's four `.bgroup` sections and are populated from four different
 * parts of `AgentState`, never fabricated here:
 *
 * - **Identity / Market** — `brief.statements[]`. Provenance is the
 *   statement's own `confidence`: `'read'` renders as `read · <source>`,
 *   `'inferred'` renders as `inferred`.
 * - **You** — `persona.fields[]`. Provenance is `derived_from`, the sentence
 *   the field was built from, because a persona a person cannot trace back to
 *   something they said is one they have no grounds to correct.
 * - **Thresholds** — the answers the conversation itself records. These come
 *   from `context.facts[]` (`key`/`value`/`scope`) and are tagged `you · L<n>
 *   <department>` — `you` because a threshold is definitionally something only
 *   the person could supply, never read or inferred.
 *
 * `departments` is a plain prop rather than read off `AgentState` — department
 * selection is a chat beat this screen owns (see `ConversationalOnboarding`),
 * not a field the engine's state carries, so showing it here needs the chosen
 * values passed in explicitly.
 */

export type BrainItem = {
  id: string
  label: string
  value: string
  /** Rendered verbatim, already composed — see the three cases above. */
  provenance: string
  /** Which provenance kind, purely for the tag's colour treatment. */
  kind: 'read' | 'inferred' | 'you'
}

export type BrainGroup = {
  key: string
  title: string
  subtitle: string
  items: BrainItem[]
}

/**
 * Which declared field (`services/api/app/ai/runtime/fields.py`) belongs in
 * "Market" rather than "Identity". `target_customers`, `competitors` and
 * `goals` are about the market the company operates in and are more often
 * inferred from the conversation than read verbatim off a page; `profile`,
 * `products_services` and `brand_voice` are what the website states about
 * itself. Anything not listed here defaults to Identity, so a field added
 * later still renders — in the group that is right more often than not —
 * rather than disappearing from the panel.
 */
const MARKET_FIELDS = new Set(['brain.target_customers', 'brain.competitors', 'brain.goals'])

function titleCase(key: string): string {
  return key
    .split(/[._]/)
    .filter(Boolean)
    .map((part) => part[0].toUpperCase() + part.slice(1))
    .join(' ')
}

/**
 * Pure mapping from engine state to panel groups. Exported on its own so it is
 * testable without mounting React, and so the panel component below is a thin
 * renderer over something a test can assert on directly.
 */
export function mapAgentStateToBrainGroups(
  state: Pick<AgentState, 'brief' | 'persona' | 'context'>,
  departments: string[] = [],
): BrainGroup[] {
  const statements = state.brief.statements ?? []
  const identity = statements.filter((s) => !MARKET_FIELDS.has(s.field))
  const market = statements.filter((s) => MARKET_FIELDS.has(s.field))

  const identityItems: BrainItem[] = identity.map((s) => ({
    id: s.field,
    label: s.label ?? titleCase(s.field),
    value: s.text,
    provenance: s.confidence === 'read' ? `read${s.source ? ` · ${s.source}` : ''}` : 'inferred',
    kind: s.confidence,
  }))

  const marketItems: BrainItem[] = market.map((s) => ({
    id: s.field,
    label: s.label ?? titleCase(s.field),
    value: s.text,
    provenance: s.confidence === 'read' ? `read${s.source ? ` · ${s.source}` : ''}` : 'inferred',
    kind: s.confidence,
  }))

  const personaItems: BrainItem[] = (state.persona.fields ?? []).map((f) => ({
    id: f.key,
    label: f.label,
    value: f.value,
    provenance: f.derived_from ? `you · “${f.derived_from}”` : 'you',
    kind: 'you',
  }))

  // `context.facts` carries both general grounding and threshold answers —
  // there is no separate wire for "this one came from a chat answer". Every
  // fact the conversation records is `you` by construction: nothing writes to
  // `context.facts` except an answer the person gave, so the distinction the
  // brief asks for ("thresholds · only you know these") falls out of the data
  // rather than needing a second flag nobody sends.
  const thresholdItems: BrainItem[] = (state.context.facts ?? []).map((fact, index) => {
    const dept = departmentFor(fact.key, departments)
    const scopeLabel = SCOPE_LABEL[fact.scope] ?? `L${fact.scope}`
    return {
      id: `${fact.key}-${index}`,
      label: titleCase(fact.key),
      value: fact.value,
      provenance: dept ? `you · ${scopeLabel} ${dept}` : `you · ${scopeLabel}`,
      kind: 'you',
    }
  })

  const groups: BrainGroup[] = [
    {
      key: 'identity',
      title: 'Identity',
      subtitle: 'from your website',
      items: identityItems,
    },
    {
      key: 'market',
      title: 'Market',
      subtitle: 'from our conversation',
      items: marketItems,
    },
    {
      key: 'you',
      title: 'You',
      subtitle: 'how I should work',
      items: personaItems,
    },
    {
      key: 'thresholds',
      title: 'Thresholds',
      subtitle: 'only you know these',
      items: thresholdItems,
    },
  ]

  return groups
}

/** Best-effort department label for a fact key — cosmetic only, never authorisation. */
function departmentFor(key: string, departments: string[]): string | null {
  const lower = key.toLowerCase()
  const match = departments.find((dept) => lower.includes(dept.toLowerCase()))
  return match ? match[0].toUpperCase() + match.slice(1) : null
}

const TAG_CLASS: Record<BrainItem['kind'], string> = {
  read: 'bg-steel-100 text-steel-700',
  inferred: 'bg-gold-100 text-gold-700',
  you: 'bg-clay-100 text-clay-700',
}

export function BrainPanel({
  state,
  departments,
}: {
  state: Pick<AgentState, 'brief' | 'persona' | 'context'> | null
  departments: string[]
}) {
  const safe = useMotionSafe()
  const groups = state ? mapAgentStateToBrainGroups(state, departments) : []
  const totalItems = groups.reduce((sum, g) => sum + g.items.length, 0)

  return (
    <aside
      aria-label="Company Brain, live"
      className="relative hidden h-full flex-col overflow-y-auto border-l border-bone-200 bg-bone-50 px-5 py-6 lg:flex lg:w-[22rem]"
    >
      <p className="font-mono text-2xs uppercase tracking-[0.14em] text-ink-400">
        Company Brain
      </p>
      <h2 className="mt-1 font-display text-lg text-ink">Building as we talk</h2>

      {totalItems === 0 && (
        <p className="mt-6 text-sm leading-relaxed text-ink-400">
          Nothing yet — this fills in, with its source, as soon as we start reading your
          website and talking it through.
        </p>
      )}

      <div className="mt-5 flex flex-col gap-5">
        {groups
          .filter((group) => group.items.length > 0)
          .map((group) => (
            <section key={group.key} aria-label={`${group.title} · ${group.subtitle}`}>
              <p className="text-xs font-semibold text-ink-700">
                {group.title}
                <span className="ml-1.5 font-normal text-ink-400">· {group.subtitle}</span>
              </p>
              <ul className="mt-2 flex flex-col gap-2.5">
                <AnimatePresence initial={false}>
                  {group.items.map((item) => (
                    <motion.li
                      key={item.id}
                      layout
                      initial={{ opacity: 0, ...(safe ? {} : { y: 6, scale: 0.98 }) }}
                      animate={{ opacity: 1, y: 0, scale: 1 }}
                      transition={{ duration: safe ? 0.01 : duration.base, ease: easing.out }}
                      className="rounded-xl border border-bone-200 bg-white/90 p-3"
                    >
                      <p className="text-[11px] font-medium text-ink-500">{item.label}</p>
                      <p className="mt-0.5 text-sm leading-snug text-ink-800">{item.value}</p>
                      <span
                        className={`mt-1.5 inline-block rounded px-1.5 py-0.5 font-mono text-[10px] ${TAG_CLASS[item.kind]}`}
                      >
                        {item.provenance}
                      </span>
                    </motion.li>
                  ))}
                </AnimatePresence>
              </ul>
            </section>
          ))}
      </div>
    </aside>
  )
}
