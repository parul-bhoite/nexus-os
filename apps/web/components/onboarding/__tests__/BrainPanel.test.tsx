import { describe, expect, it } from 'vitest'
import { mapAgentStateToBrainGroups } from '@/components/onboarding/BrainPanel'

/**
 * `mapAgentStateToBrainGroups` is the product's "never invent a number, always
 * show the source" promise expressed as a pure function — every item it
 * produces must carry provenance traceable to exactly one of three places on
 * `AgentState`: `brief.statements` (read/inferred), `persona.fields` (you,
 * from what was said), `context.facts` (you, with scope). These tests assert
 * that mapping directly, without mounting the panel.
 */

describe('mapAgentStateToBrainGroups', () => {
  it('tags a read statement with its source, in Identity', () => {
    const groups = mapAgentStateToBrainGroups({
      brief: {
        statements: [
          {
            field: 'brain.profile',
            label: 'Company profile',
            text: 'A consulting company.',
            confidence: 'read',
            source: 'https://acme.om/about',
          },
        ],
      },
      persona: {},
      context: {},
    })

    const identity = groups.find((g) => g.key === 'identity')!
    expect(identity.items).toHaveLength(1)
    expect(identity.items[0].provenance).toBe('read · https://acme.om/about')
    expect(identity.items[0].kind).toBe('read')
  })

  it('tags an inferred statement without a source, and routes market fields to Market', () => {
    const groups = mapAgentStateToBrainGroups({
      brief: {
        statements: [
          {
            field: 'brain.target_customers',
            label: 'Target customers',
            text: 'Mid-market retailers.',
            confidence: 'inferred',
          },
        ],
      },
      persona: {},
      context: {},
    })

    const identity = groups.find((g) => g.key === 'identity')!
    const market = groups.find((g) => g.key === 'market')!
    expect(identity.items).toHaveLength(0)
    expect(market.items).toHaveLength(1)
    expect(market.items[0].provenance).toBe('inferred')
    expect(market.items[0].kind).toBe('inferred')
  })

  it('tags a persona field "you" with the sentence it was derived from', () => {
    const groups = mapAgentStateToBrainGroups({
      brief: {},
      persona: {
        fields: [
          {
            key: 'persona.tone',
            label: 'Tone',
            value: 'Direct and data-led',
            derived_from: 'I like short, numbers-first updates.',
          },
        ],
      },
      context: {},
    })

    const you = groups.find((g) => g.key === 'you')!
    expect(you.items[0].provenance).toBe('you · “I like short, numbers-first updates.”')
    expect(you.items[0].kind).toBe('you')
  })

  it('tags a threshold fact "you · L<scope>", with a department when one matches', () => {
    const groups = mapAgentStateToBrainGroups(
      {
        brief: {},
        persona: {},
        context: {
          facts: [{ key: 'sales.discount_ceiling', value: '15%', scope: 3 }],
        },
      },
      ['sales', 'finance'],
    )

    const thresholds = groups.find((g) => g.key === 'thresholds')!
    expect(thresholds.items[0].provenance).toBe('you · L3 Department Sales')
    expect(thresholds.items[0].kind).toBe('you')
  })

  it('omits the department when no declared department matches the fact key', () => {
    const groups = mapAgentStateToBrainGroups(
      {
        brief: {},
        persona: {},
        context: { facts: [{ key: 'general.timezone', value: 'GMT+4', scope: 1 }] },
      },
      ['sales'],
    )

    const thresholds = groups.find((g) => g.key === 'thresholds')!
    expect(thresholds.items[0].provenance).toBe('you · L1 Company public')
  })

  it('produces no items for an empty state', () => {
    const groups = mapAgentStateToBrainGroups({ brief: {}, persona: {}, context: {} })
    expect(groups.every((g) => g.items.length === 0)).toBe(true)
  })
})
