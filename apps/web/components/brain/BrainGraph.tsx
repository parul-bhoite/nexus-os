'use client'

import { motion } from 'framer-motion'
import { useId, useMemo } from 'react'
import type { Fact } from '@/lib/brain-facts'
import { GRAPH_EXTENT, buildGraph } from '@/lib/brain-graph'
import { duration, easing, useMotionSafe } from '@/lib/motion'

/**
 * The interactive relationship graph — ADR 0069 phase 2, stretch half.
 *
 * Same data as the table, no second endpoint, no external graphing library
 * (CSP blocks one): inline SVG for the lines, real `<button>`s laid over it
 * for the nodes. SVG was deliberately not asked to carry the interaction
 * itself — an SVG `<text>` or `<circle>` has no native focus or press
 * semantics, and recreating them with `tabIndex` and a `keydown` handler is
 * exactly the kind of bespoke a11y this product's own primitives (`Overlay`,
 * `Tabs`) exist to avoid. A `<button>` gets focus, `Enter`/`Space`, and a
 * screen-reader role for free.
 *
 * **The table is the text-equivalent**, stated in the `<figure>`'s own
 * description rather than assumed — a screen-reader user is never expected to
 * make sense of forty absolutely-positioned buttons scattered over a canvas.
 */

const PADDING = 56
const HALF = GRAPH_EXTENT + PADDING

export function BrainGraph({
  facts,
  onSelect,
  selectedFactId,
}: {
  facts: Fact[]
  onSelect: (factId: string) => void
  selectedFactId: string | null
}) {
  const safe = useMotionSafe()
  const graph = useMemo(() => buildGraph(facts), [facts])
  const titleId = useId()
  const descId = useId()

  if (facts.length === 0) return null

  return (
    <figure aria-labelledby={titleId} aria-describedby={descId} className="flex flex-col gap-3">
      <figcaption id={titleId} className="sr-only">
        Company Brain relationship graph
      </figcaption>
      <p id={descId} className="sr-only">
        A visual map of the same facts as the table above, grouped by Identity, Market and
        each department with a threshold. The table is the full text equivalent of this
        graph.
      </p>

      <div className="relative mx-auto aspect-square w-full max-w-xl">
        <svg
          viewBox={`${-HALF} ${-HALF} ${HALF * 2} ${HALF * 2}`}
          className="absolute inset-0 h-full w-full overflow-visible"
          aria-hidden="true"
        >
          {graph.edges.map((edge) => {
            const from = graph.nodes.find((n) => n.id === edge.from)
            const to = graph.nodes.find((n) => n.id === edge.to)
            if (!from || !to) return null
            return (
              <line
                key={`${edge.from}-${edge.to}`}
                x1={from.x}
                y1={from.y}
                x2={to.x}
                y2={to.y}
                stroke="currentColor"
                strokeWidth={1.5}
                className="text-ink-200"
              />
            )
          })}
        </svg>

        {graph.nodes.map((node, index) => {
          const left = 50 + (node.x / HALF) * 50
          const top = 50 + (node.y / HALF) * 50
          const selected = node.kind === 'fact' && node.factId === selectedFactId

          const dot =
            node.kind === 'company'
              ? 'h-14 w-14 bg-ink-800 text-bone-50 text-label font-semibold'
              : node.kind === 'branch'
                ? 'h-10 w-10 bg-steel-100 text-steel-700 text-2xs font-medium'
                : selected
                  ? 'h-9 w-9 bg-clay-500 text-bone-50 text-2xs'
                  : 'h-9 w-9 bg-bone-200 text-ink-600 text-2xs'

          return (
            <motion.button
              key={node.id}
              type="button"
              disabled={node.kind === 'company'}
              onClick={() => node.factId && onSelect(node.factId)}
              aria-pressed={node.kind === 'fact' ? selected : undefined}
              initial={{ opacity: 0, scale: safe ? 0.9 : 1 }}
              animate={{ opacity: 1, scale: 1 }}
              transition={{
                duration: safe ? duration.base : 0,
                delay: safe ? index * 0.02 : 0,
                ease: easing.out,
              }}
              style={{ left: `${left}%`, top: `${top}%` }}
              className={`absolute flex w-24 -translate-x-1/2 -translate-y-1/2 flex-col items-center gap-1 rounded-control py-1 text-center focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-steel-500 focus-visible:ring-offset-2 focus-visible:ring-offset-bone-50 ${
                node.kind === 'company'
                  ? 'pointer-events-none'
                  : 'min-h-11 [@media(hover:hover)and(pointer:fine)]:hover:bg-bone-100'
              }`}
            >
              <span
                aria-hidden="true"
                className={`flex shrink-0 items-center justify-center rounded-full transition-colors duration-micro ease-out ${dot}`}
              >
                {node.kind === 'company' ? '' : node.label.slice(0, 1).toUpperCase()}
              </span>
              <span className="w-full truncate text-2xs leading-tight text-ink-700">
                {node.kind === 'company' ? 'Company' : node.label}
              </span>
            </motion.button>
          )
        })}
      </div>
    </figure>
  )
}
