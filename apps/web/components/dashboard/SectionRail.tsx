'use client'

import { Tabs } from '@/components/ui/Tabs'
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
 *
 * ## It is a tab list now, not a row of buttons
 *
 * The audit's finding: a row of buttons is not a tab list. Every tab was its
 * own tab stop, so reaching the sixth took six presses; nothing announced that
 * a selection controlled a panel, or which of six it was; and the arrow keys —
 * which is how a tab list is actually driven — did nothing. It also could not
 * survive 390px, where six pills with counts wrap onto three lines above the
 * content they belong to.
 *
 * `Tabs` holds the WAI pattern (one tab stop, arrows within, `aria-selected`,
 * `aria-controls`) and the horizontal overflow. This file keeps what is
 * specific to a director: the order, the labels and what the count means.
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
    <div className="border-b border-ink-100 pb-3">
      <Tabs
        label="Sections"
        active={active}
        onChange={onSelect}
        tabs={sections.map((section) => ({
          key: section.key,
          label: section.label,
          // The count is the honest version of a badge. It is how many
          // capabilities sit on this tab, not how many of them work — and every
          // one of them says which it is on its own card.
          count: section.blocks.length,
        }))}
      />
    </div>
  )
}
