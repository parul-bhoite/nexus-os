'use client'

import type { Section } from '@/lib/dashboard-client'

/**
 * The tabs on a director's page. `doc/13` §4.
 *
 * `doc/08` specifies 4–6 named sections per department — Overview, Cash &
 * runway, Receivables, Approvals — and the flat list this replaces could not
 * express any of them. The section is the unit of navigation; the block is the
 * unit of rendering.
 *
 * **Order is the design, not a sort.** Every department leads with Overview
 * because that is the screen somebody opens for, and the Executive leads with
 * the Morning brief for the same reason. The API serves them in order and this
 * renders them in the order served — sorting here would put Approvals before
 * Cash on the Finance page.
 *
 * **A tab with nothing on it never arrives.** `doc/08` draws five sections that
 * no capability fills yet, and the API omits them: clicking into a tab to find
 * nothing is worse than the tab not being there. That filter is server-side so
 * every client agrees about it.
 *
 * Labels are served rather than derived — finding F13, where the same
 * department was `hr` in the API, "Hr" in a checkbox and "People" in the nav
 * because each surface title-cased the value itself.
 */
export function SectionRail({
  sections,
  active,
  onSelect,
}: {
  sections: Section[]
  active: string
  onSelect: (key: string) => void
}) {
  return (
    <nav aria-label="Sections" className="flex flex-wrap gap-2 border-b border-ink-100 pb-4">
      {sections.map((section) => {
        const current = section.key === active
        return (
          <button
            key={section.key}
            type="button"
            onClick={() => onSelect(section.key)}
            aria-current={current ? 'page' : undefined}
            className={`rounded-full px-3.5 py-1.5 text-sm font-medium transition-colors ${
              current
                ? 'bg-ink-800 text-bone-50'
                : 'border border-ink-100 text-ink-600 hover:border-ink-300 hover:text-ink-900'
            }`}
          >
            {section.label}
            {/* The count is the honest version of a badge. It is how many
                capabilities sit on this tab, not how many of them work — and
                every one of them says which it is on its own card. */}
            <span
              className={`ml-2 font-mono text-2xs ${current ? 'text-bone-200' : 'text-ink-400'}`}
            >
              {section.blocks.length}
            </span>
          </button>
        )
      })}
    </nav>
  )
}
