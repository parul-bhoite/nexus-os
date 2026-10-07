import { describe, expect, it } from 'vitest'
import { buildGraph } from '@/lib/brain-graph'
import type { Fact } from '@/lib/brain-facts'

function fact(overrides: Partial<Fact> = {}): Fact {
  return {
    id: 'f1',
    item: 'What the company does',
    value: 'A distributor.',
    kind: 'Identity',
    scope: '—',
    sourceKind: 'read',
    sourceLabel: 'read',
    updated: 'v1',
    department: null,
    why: null,
    sources: ['https://acme.om'],
    field: 'brain.profile',
    ...overrides,
  }
}

describe('buildGraph', () => {
  it('always has exactly one company node at the centre', () => {
    const { nodes } = buildGraph([fact()])
    const company = nodes.find((n) => n.kind === 'company')!
    expect(company).toBeDefined()
    expect(company.x).toBe(0)
    expect(company.y).toBe(0)
  })

  it('groups Identity and Market facts into their own branches', () => {
    const { nodes, edges } = buildGraph([
      fact({ id: 'a', kind: 'Identity' }),
      fact({ id: 'b', kind: 'Market' }),
    ])

    const branches = nodes.filter((n) => n.kind === 'branch')
    expect(branches.map((b) => b.label).sort()).toEqual(['Identity', 'Market'])
    expect(edges.some((e) => e.from === 'company' && e.to === 'branch-identity')).toBe(true)
    expect(edges.some((e) => e.from === 'company' && e.to === 'branch-market')).toBe(true)
  })

  it('gives each department with a Threshold fact its own branch', () => {
    const { nodes } = buildGraph([
      fact({ id: 'a', kind: 'Threshold', department: 'Marketing' }),
      fact({ id: 'b', kind: 'Threshold', department: 'Sales' }),
    ])
    const branches = nodes.filter((n) => n.kind === 'branch')
    expect(branches.map((b) => b.label).sort()).toEqual(['Marketing', 'Sales'])
  })

  it('routes a departmentless Fact into a General branch', () => {
    const { nodes } = buildGraph([fact({ id: 'a', kind: 'Fact', department: null })])
    expect(nodes.some((n) => n.kind === 'branch' && n.label === 'General')).toBe(true)
  })

  it('creates one leaf node per fact, each pointing back at it', () => {
    const facts = [fact({ id: 'a' }), fact({ id: 'b' })]
    const { nodes } = buildGraph(facts)
    const leaves = nodes.filter((n) => n.kind === 'fact')
    expect(leaves).toHaveLength(2)
    expect(leaves.map((l) => l.factId).sort()).toEqual(['a', 'b'])
  })

  it('produces only the company node when there are no facts', () => {
    const { nodes, edges } = buildGraph([])
    expect(nodes).toHaveLength(1)
    expect(edges).toHaveLength(0)
  })
})
