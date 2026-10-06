import type { Fact } from '@/lib/brain-facts'

/**
 * The Company Brain relationship graph — the stretch half of ADR 0069 phase 2.
 *
 * Built from the exact same `Fact[]` the table renders; there is no second
 * endpoint and nothing here infers a relationship the facts list does not
 * already state. Layout is a plain radial tree computed in code: the Company
 * at the centre, one branch per group (`Identity`, `Market`, one per
 * department that has a Threshold fact, plus `General` for a departmentless
 * `Fact`), and that group's facts as leaves around it.
 *
 * A caller that wants the pixel-free version has one: the table this graph is
 * built from is the accessible fallback, which is why `BrainGraph` wraps this
 * in a `<figure>` with that stated in its description rather than trying to
 * make forty radial SVG buttons into a screen-reader tree.
 */

export type GraphNodeKind = 'company' | 'branch' | 'fact'

export type GraphNode = {
  id: string
  label: string
  kind: GraphNodeKind
  x: number
  y: number
  /** Present on a `'fact'` node — which row in the table it opens. */
  factId?: string
}

export type GraphEdge = { from: string; to: string }

export type Graph = { nodes: GraphNode[]; edges: GraphEdge[] }

const BRANCH_RADIUS = 150
const LEAF_RADIUS = 110
/** How far a leaf can land from the centre, so the renderer can size its
 *  viewBox without recomputing the trig itself. */
export const GRAPH_EXTENT = BRANCH_RADIUS + LEAF_RADIUS
// The sector each branch's leaves fan across, so a branch with many facts
// does not overlap its neighbour's.
const LEAF_SPREAD = (Math.PI * 2) / 7

function point(cx: number, cy: number, radius: number, angle: number): { x: number; y: number } {
  return { x: cx + radius * Math.cos(angle), y: cy + radius * Math.sin(angle) }
}

/** Which branch a fact belongs under. */
function branchKeyFor(fact: Fact): { key: string; label: string } {
  if (fact.kind === 'Identity') return { key: 'identity', label: 'Identity' }
  if (fact.kind === 'Market') return { key: 'market', label: 'Market' }
  if (fact.kind === 'Threshold' && fact.department) {
    return { key: `dept-${fact.department}`, label: fact.department }
  }
  return { key: 'general', label: 'General' }
}

/**
 * The radial tree. `cx`/`cy` default to the origin — the caller's `<svg>`
 * translates the whole thing to its own centre, which keeps this function
 * free of any notion of viewport size.
 */
export function buildGraph(facts: Fact[], cx = 0, cy = 0): Graph {
  const nodes: GraphNode[] = [{ id: 'company', label: 'Company', kind: 'company', x: cx, y: cy }]
  const edges: GraphEdge[] = []

  const branches = new Map<string, { label: string; facts: Fact[] }>()
  for (const fact of facts) {
    const { key, label } = branchKeyFor(fact)
    const existing = branches.get(key)
    if (existing) existing.facts.push(fact)
    else branches.set(key, { label, facts: [fact] })
  }

  const order = Array.from(branches.entries()).filter(([, group]) => group.facts.length > 0)
  const branchCount = order.length

  order.forEach(([key, group], index) => {
    const angle = branchCount === 1 ? -Math.PI / 2 : (index / branchCount) * Math.PI * 2 - Math.PI / 2
    const branchPoint = point(cx, cy, BRANCH_RADIUS, angle)
    const branchId = `branch-${key}`
    nodes.push({ id: branchId, label: group.label, kind: 'branch', ...branchPoint })
    edges.push({ from: 'company', to: branchId })

    const leafCount = group.facts.length
    group.facts.forEach((fact, leafIndex) => {
      const spread = leafCount === 1 ? 0 : LEAF_SPREAD
      const leafAngle =
        angle + (leafCount === 1 ? 0 : (leafIndex / (leafCount - 1) - 0.5) * spread)
      const leafPoint = point(branchPoint.x, branchPoint.y, LEAF_RADIUS, leafAngle)
      const leafId = `fact-${fact.id}`
      nodes.push({ id: leafId, label: fact.item, kind: 'fact', factId: fact.id, ...leafPoint })
      edges.push({ from: branchId, to: leafId })
    })
  })

  return { nodes, edges }
}
