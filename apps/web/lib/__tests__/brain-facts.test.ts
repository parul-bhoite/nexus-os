import { describe, expect, it } from 'vitest'
import {
  assumptionFacts,
  brainFacts,
  buildFacts,
  answerFacts,
  formatAnswerValue,
  matchesSearch,
} from '@/lib/brain-facts'
import type { Brain } from '@/lib/settings-client'
import type { Question } from '@/lib/onboarding-client'

function brain(overrides: Partial<Brain> = {}): Brain {
  return {
    version: 3,
    generated_by: 'agent',
    unavailable_reason: '',
    profile: 'An industrial supplies distributor.',
    products_services: 'Pipes, fittings and tools.',
    target_customers: 'Contractors and facilities teams.',
    goals: 'Grow recurring revenue.',
    assumptions: [],
    provenance: ['https://acme.om', 'https://acme.om/about'],
    ...overrides,
  }
}

function question(overrides: Partial<Question> = {}): Question {
  return {
    key: 'currency',
    prompt: 'Which currency do you report in?',
    stage: 'pass_1',
    answer_type: 'single_choice',
    scope: 'L2',
    department: null,
    required: false,
    why: 'Every figure NEXUS shows is in this currency.',
    options: [],
    free_entry: false,
    writable: true,
    value: null,
    ...overrides,
  }
}

describe('brainFacts', () => {
  it('maps the four structured fields to Identity/Market, tagged read, skipping nulls', () => {
    const facts = brainFacts(brain({ goals: null }))

    expect(facts.map((f) => f.item)).toEqual([
      'What the company does',
      'Products & services',
      'Who buys from you',
    ])
    expect(facts.every((f) => f.sourceKind === 'read')).toBe(true)
    expect(facts.find((f) => f.item === 'What the company does')!.kind).toBe('Identity')
    expect(facts.find((f) => f.item === 'Who buys from you')!.kind).toBe('Market')
  })

  it('carries the brain version as "Updated" and the provenance list as sources', () => {
    const facts = brainFacts(brain())
    expect(facts[0].updated).toBe('v3')
    expect(facts[0].sources).toEqual(['https://acme.om', 'https://acme.om/about'])
  })

  it('returns nothing for a null brain', () => {
    expect(brainFacts(null)).toEqual([])
  })
})

describe('answerFacts', () => {
  it('skips an unanswered question', () => {
    expect(answerFacts([question({ value: null })])).toHaveLength(0)
  })

  it('tags an answer "you", with its own scope and prompt as the item', () => {
    const [fact] = answerFacts([question({ value: 'OMR' })])
    expect(fact.item).toBe('Which currency do you report in?')
    expect(fact.value).toBe('OMR')
    expect(fact.sourceKind).toBe('you')
    expect(fact.scope).toBe('L2')
    expect(fact.updated).toBe('—')
    expect(fact.why).toBe('Every figure NEXUS shows is in this currency.')
  })

  it('is a Threshold with a department label when the question has one, else a Fact', () => {
    const [threshold] = answerFacts([question({ value: '1500', department: 'marketing' })])
    const [fact] = answerFacts([question({ value: 'OMR', department: null })])

    expect(threshold.kind).toBe('Threshold')
    expect(threshold.department).toBe('Marketing')
    expect(fact.kind).toBe('Fact')
    expect(fact.department).toBeNull()
  })

  it('joins a multi-choice array rather than printing "[object Object]"', () => {
    const [fact] = answerFacts([question({ value: ['Sales', 'Marketing'] })])
    expect(fact.value).toBe('Sales, Marketing')
  })
})

describe('formatAnswerValue', () => {
  it('renders an absent value as an em dash rather than the word "null"', () => {
    expect(formatAnswerValue(null)).toBe('—')
    expect(formatAnswerValue(undefined)).toBe('—')
  })
})

describe('buildFacts', () => {
  it('combines brain fields and answered questions, brain first', () => {
    const facts = buildFacts(brain(), [question({ value: 'OMR' })])
    // brain() has all four structured fields set, plus the one answer.
    expect(facts).toHaveLength(5)
    expect(facts[4].sourceKind).toBe('you')
  })

  it('produces nothing for an empty brain and no answers', () => {
    expect(buildFacts(null, [])).toEqual([])
  })
})

describe('assumptionFacts', () => {
  it('keeps assumptions out of the sortable list, carrying the same provenance', () => {
    const facts = assumptionFacts(brain({ assumptions: ['Fiscal year starts in April.'] }))
    expect(facts).toHaveLength(1)
    expect(facts[0].text).toBe('Fiscal year starts in April.')
    expect(facts[0].sources).toEqual(['https://acme.om', 'https://acme.om/about'])
  })

  it('is empty when there are no assumptions', () => {
    expect(assumptionFacts(brain({ assumptions: [] }))).toEqual([])
  })
})

describe('matchesSearch', () => {
  const [fact] = brainFacts(brain())

  it('matches on item, value and source, case-insensitively', () => {
    expect(matchesSearch(fact, 'industrial')).toBe(true)
    expect(matchesSearch(fact, 'WHAT THE COMPANY')).toBe(true)
    expect(matchesSearch(fact, 'read')).toBe(true)
  })

  it('does not match unrelated text', () => {
    expect(matchesSearch(fact, 'zzz-not-present')).toBe(false)
  })

  it('treats a blank query as matching everything', () => {
    expect(matchesSearch(fact, '   ')).toBe(true)
  })
})
