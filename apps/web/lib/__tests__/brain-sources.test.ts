import { describe, expect, it } from 'vitest'
import { linkFactToTurns, summariseSources } from '@/lib/brain-sources'
import type { Brain } from '@/lib/settings-client'
import type { Question } from '@/lib/onboarding-client'
import type { Turn } from '@/lib/agent-onboarding-client'
import type { Fact } from '@/lib/brain-facts'

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

function turn(overrides: Partial<Turn> = {}): Turn {
  return {
    role: 'agent',
    text: 'Who actually buys from you?',
    target: null,
    scope: null,
    ...overrides,
  }
}

function fact(overrides: Partial<Fact> = {}): Fact {
  return {
    id: 'brain-target_customers',
    item: 'Who buys from you',
    value: 'Contractors and facilities teams.',
    kind: 'Market',
    scope: '—',
    sourceKind: 'read',
    sourceLabel: 'read',
    updated: 'v3',
    department: null,
    why: null,
    sources: ['https://acme.om'],
    field: 'brain.target_customers',
    ...overrides,
  }
}

describe('summariseSources', () => {
  it('counts the onboarding conversation as a source, when there are turns', () => {
    const turns = [turn(), turn({ role: 'user', text: 'Mostly contractors.' })]
    const [conversation] = summariseSources(brain(), [], turns, [])
    expect(conversation.id).toBe('conversation')
    expect(conversation.label).toBe('Onboarding conversation')
    expect(conversation.count).toBe(2)
    expect(conversation.available).toBe(true)
    expect(conversation.description).toBe('2 messages')
  })

  it('reports the conversation source as unavailable, not an error, when there are no turns', () => {
    const [conversation] = summariseSources(brain(), [], [], [])
    expect(conversation.count).toBe(0)
    expect(conversation.available).toBe(false)
    expect(conversation.description).toMatch(/no onboarding conversation/i)
  })

  it('prefers pages_read for the website source, falling back to brain.provenance', () => {
    const [, fromPagesRead] = summariseSources(brain(), [], [], ['https://acme.om/'])
    expect(fromPagesRead.label).toBe('Website')
    expect(fromPagesRead.count).toBe(1)

    const [, fromProvenance] = summariseSources(brain(), [], [], [])
    expect(fromProvenance.count).toBe(2)
  })

  it('counts only answered questions for "You"', () => {
    const [, , you] = summariseSources(
      brain(),
      [question({ value: 'OMR' }), question({ key: 'other', value: null })],
      [],
      [],
    )
    expect(you.label).toBe('You')
    expect(you.count).toBe(1)
    expect(you.available).toBe(true)
  })
})

describe('linkFactToTurns', () => {
  it('matches a brain fact to the user turn whose target is the same declared field', () => {
    const turns = [
      turn({ role: 'agent', text: 'Who actually buys from you?', target: null }),
      turn({
        role: 'user',
        text: 'Mostly contractors and facilities teams.',
        target: 'brain.target_customers',
        scope: 2,
      }),
    ]
    const linked = linkFactToTurns(fact(), turns)
    expect(linked).toHaveLength(1)
    expect(linked[0].index).toBe(1)
    expect(linked[0].turn.text).toBe('Mostly contractors and facilities teams.')
  })

  it('never links an agent turn, even one sharing the field', () => {
    const turns = [turn({ role: 'agent', target: 'brain.target_customers' })]
    expect(linkFactToTurns(fact(), turns)).toHaveLength(0)
  })

  it('matches an answered question by the trailing segment of a fact.* target', () => {
    const answer = fact({
      id: 'answer-approval_threshold',
      field: 'approval_threshold',
      sourceKind: 'you',
    })
    const turns = [
      turn({
        role: 'user',
        text: 'Five hundred.',
        target: 'fact.finance.approval_threshold',
        scope: 3,
      }),
    ]
    expect(linkFactToTurns(answer, turns)).toHaveLength(1)
  })

  it('returns nothing rather than a wrong link when the catalogue name has drifted from the question key', () => {
    const answer = fact({ id: 'answer-runway_alert_months', field: 'runway_alert_months' })
    const turns = [turn({ role: 'user', text: 'Nine months.', target: 'fact.finance.runway_alarm' })]
    expect(linkFactToTurns(answer, turns)).toHaveLength(0)
  })

  it('returns nothing for a fact with no field', () => {
    expect(linkFactToTurns(fact({ field: null }), [turn({ role: 'user', target: 'brain.profile' })])).toHaveLength(0)
  })
})
