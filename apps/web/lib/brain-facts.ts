import type { Brain } from '@/lib/settings-client'
import { departmentLabel, type Question } from '@/lib/onboarding-client'

/**
 * The Company Brain page's one fact list, built from two existing wires.
 *
 * ADR 0069 phase 2. `fetchBrain()` is the structured, audited record —
 * `profile`, `products_services`, `target_customers`, `goals` and
 * `assumptions[]` — and `fetchQuestions()` is the catalogue of thresholds a
 * founder answered during setup. Neither endpoint was built with this page in
 * mind, so nothing here invents a field either is missing: a brain field has
 * no per-field timestamp, so `updated` is the brain's own version rather than
 * a fabricated date, and an answered question has no provenance beyond "you
 * said so", so that is exactly what it carries.
 *
 * ## Why three provenance kinds, and why assumptions get the "inferred" one
 *
 * `read` (steel), `inferred` (gold) and `you` (clay) are the palette the
 * onboarding Brain panel already uses (`components/onboarding/BrainPanel.tsx`)
 * — this page reuses it rather than inventing a fourth language for the same
 * idea.
 *
 * - The four structured brain fields came out of the audit NEXUS already ran
 *   (the crawl plus the conversation) and are shown as `read`. There is no
 *   per-field confidence on this wire — `brain.provenance` is a flat list of
 *   what the whole brain was built from — so every structured field points at
 *   that same list rather than claiming a citation the API never sent.
 * - An answered question is `you` by construction: nothing populates
 *   `questions[].value` except something the founder typed.
 * - An assumption is the one thing NEXUS **guessed rather than read or was
 *   told**, which is exactly what `inferred` means elsewhere in this product
 *   — and it is also the tier the ADR's conflict-precedence footnote ranks
 *   last. It is kept in its own block (see `CompanyBrainPage`) rather than
 *   folded into the sortable list, because a bare string has no `Item` name to
 *   search or sort by without fabricating one.
 */

export type FactKind = 'Identity' | 'Market' | 'Threshold' | 'Fact'
export type FactSourceKind = 'read' | 'inferred' | 'you'

export type Fact = {
  id: string
  item: string
  value: string
  kind: FactKind
  /** `L1`…`L5`, or `'—'` where the source carries no scope at all. Never
   *  guessed — a brain field has no scope on this wire and says so plainly. */
  scope: string
  sourceKind: FactSourceKind
  /** The short tag text, e.g. `'read'` or `'you'`. */
  sourceLabel: string
  /** Brain version (`'v3'`) for brain fields; `'—'` for an answer, which
   *  carries no timestamp on this wire. */
  updated: string
  department: string | null
  /** Why this was asked — only an answered question carries one. */
  why: string | null
  /** What to show in the detail view as "built from". */
  sources: string[]
  /**
   * The raw catalogue field key behind this fact, used by `lib/brain-
   * sources.ts` to find the onboarding turn that produced it.
   *
   * A brain field carries its full declared-field key (`brain.profile`,
   * `brain.target_customers`, …) — `services/api/app/ai/runtime/fields.py`
   * is the catalogue both sides read, so this is an exact match against
   * `turn.target` with no translation. An answered question carries its bare
   * catalogue key (`approval_threshold`) rather than the declared field's
   * full name (`fact.finance.approval_threshold`) — the two coincide for
   * several fields and not others (the catalogue's own `question_key` field
   * documents the drift), so `linkFactToTurns` matches it as a trailing
   * segment rather than claiming a mapping this wire does not carry. `null`
   * only for the places neither applies — there are none today, but nothing
   * here should assume every future fact kind has one.
   */
  field: string | null
}

const BRAIN_FIELDS: { key: 'profile' | 'products_services' | 'target_customers' | 'goals'; item: string; kind: FactKind }[] = [
  { key: 'profile', item: 'What the company does', kind: 'Identity' },
  { key: 'products_services', item: 'Products & services', kind: 'Identity' },
  { key: 'target_customers', item: 'Who buys from you', kind: 'Market' },
  { key: 'goals', item: 'Goals', kind: 'Market' },
]

/** Pretty-print whatever shape an answer's value happens to be, without
 *  pretending to know its `answer_type` more precisely than the value itself
 *  shows. */
export function formatAnswerValue(value: unknown): string {
  if (value === null || value === undefined) return '—'
  if (Array.isArray(value)) return value.map((item) => formatAnswerValue(item)).join(', ')
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}

/** The brain's four structured fields, mapped to facts. Exported separately so
 *  a caller can tell a brain-sourced fact from an answered one without
 *  re-deriving the split. */
export function brainFacts(brain: Brain | null): Fact[] {
  if (!brain) return []
  const sources = brain.provenance ?? []
  return BRAIN_FIELDS.filter((field) => brain[field.key]).map((field) => ({
    id: `brain-${field.key}`,
    item: field.item,
    value: brain[field.key] as string,
    kind: field.kind,
    scope: '—',
    sourceKind: 'read',
    sourceLabel: 'read',
    updated: `v${brain.version}`,
    department: null,
    why: null,
    sources,
    field: `brain.${field.key}`,
  }))
}

/** Answered questions — `value != null` — mapped to facts. */
export function answerFacts(questions: Question[]): Fact[] {
  return questions
    .filter((q) => q.value !== null && q.value !== undefined)
    .map((q) => ({
      id: `answer-${q.key}`,
      item: q.prompt,
      value: formatAnswerValue(q.value),
      kind: q.department ? 'Threshold' : 'Fact',
      scope: q.scope,
      sourceKind: 'you',
      sourceLabel: 'you',
      updated: '—',
      department: q.department ? departmentLabel(q.department) : null,
      why: q.why || null,
      sources: ['you'],
      field: q.key,
    }))
}

/** Every fact the table shows — brain fields first, then answers, in the
 *  order each source lists them. Assumptions are deliberately excluded; see
 *  `assumptionFacts` and the module comment above. */
export function buildFacts(brain: Brain | null, questions: Question[]): Fact[] {
  return [...brainFacts(brain), ...answerFacts(questions)]
}

export type Assumption = {
  id: string
  text: string
  sources: string[]
}

/** `brain.assumptions[]`, kept apart from the sortable facts because a bare
 *  sentence has no `Item` to search by. Still carries `brain.provenance` as
 *  its "built from" list, for the same reason the structured fields do. */
export function assumptionFacts(brain: Brain | null): Assumption[] {
  if (!brain || brain.assumptions.length === 0) return []
  const sources = brain.provenance ?? []
  return brain.assumptions.map((text, index) => ({
    id: `assumption-${index}`,
    text,
    sources,
  }))
}

/** Case-insensitive match against item, value or source label — the three
 *  columns the brief asks search to cover. */
export function matchesSearch(fact: Fact, query: string): boolean {
  if (!query.trim()) return true
  const needle = query.trim().toLowerCase()
  return (
    fact.item.toLowerCase().includes(needle) ||
    fact.value.toLowerCase().includes(needle) ||
    fact.sourceLabel.toLowerCase().includes(needle) ||
    (fact.department ?? '').toLowerCase().includes(needle)
  )
}
