'use client'

import { useEffect, useMemo, useState } from 'react'

import { type Tool, type ToolCatalogue, readTools } from '@/lib/agent-onboarding-client'

/**
 * The tools step: which systems this company runs on. The last thing before
 * the Persona and the Company Brain are assembled.
 *
 * **It says "declare", not "connect", because that is what it does.** No OAuth
 * flow exists yet, and `connectable` comes back false for every tool — so the
 * screen asks which systems they use and says plainly that connecting comes
 * later. The alternative was a row of Connect buttons that open nothing, which
 * is the one thing this product cannot afford to ship: the whole claim is that
 * it never states what it cannot support.
 *
 * That does not make the step decorative. What is recorded here is grounding
 * the Brain is built *with* — "deals are in Pipedrive, invoices in Xero" is a
 * fact only this person has — and every declared-but-unconnected tool becomes a
 * named gap with a named unlock, which is a different thing from an empty tile.
 *
 * **Nothing is filtered out.** The catalogue arrives ordered by the departments
 * this company runs, and every tool is still on it: a company with no formal
 * finance function may well run Stripe, and hiding it would be the product
 * deciding it knows their stack better than they do.
 *
 * **The CRMs are grouped, not made exclusive.** Four of them are alternatives
 * to each other, so they are presented under one heading rather than as four
 * unrelated choices — but more than one can be ticked, because a company
 * mid-migration really does run two, and a radio group would force them to lie.
 */
export function ToolsStep({
  onContinue,
  disabled,
}: {
  /** The ids to declare, and whether the person chose to skip the step. */
  onContinue: (providers: string[], skipped: boolean) => void
  disabled: boolean
}) {
  const [catalogue, setCatalogue] = useState<ToolCatalogue | null>(null)
  const [picked, setPicked] = useState<Set<string> | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let live = true
    void (async () => {
      try {
        const loaded = await readTools()
        if (!live) return
        setCatalogue(loaded)
        // Seeded from the server so that returning to this step — a refresh, a
        // second tab, a resumed journey — shows what was declared last time
        // rather than an empty form that would silently clear it on continue.
        setPicked(new Set(loaded.declared))
      } catch (cause) {
        if (!live) return
        setError(cause instanceof Error ? cause.message : 'Could not load the tool list.')
      }
    })()
    return () => {
      live = false
    }
  }, [])

  /**
   * The catalogue in the order it arrived, split into department blocks with
   * the four CRMs collapsed into one.
   *
   * Grouped here rather than server-side because it is a layout decision: the
   * wire carries `department` and `kind` per tool, which is the data, and how
   * many headings that becomes is a question about this screen.
   */
  const groups = useMemo(() => {
    const out: { key: string; label: string; note: string | null; tools: Tool[] }[] = []
    for (const tool of catalogue?.tools ?? []) {
      const key = tool.kind === 'crm' ? 'crm' : tool.department
      const existing = out.find((group) => group.key === key)
      if (existing) {
        existing.tools.push(tool)
        continue
      }
      out.push({
        key,
        label: tool.kind === 'crm' ? 'Your CRM' : tool.department_label,
        note: tool.kind === 'crm' ? 'Whichever you use — more than one is fine.' : null,
        tools: [tool],
      })
    }
    return out
  }, [catalogue])

  const chosen = picked ?? new Set<string>()

  const toggle = (id: string) =>
    setPicked((prev) => {
      const next = new Set(prev ?? [])
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })

  return (
    <div className="rounded-2xl border border-bone-300 bg-white/90 p-4 backdrop-blur-sm">
      <h2 className="font-display text-lg text-ink">Last thing — which systems do you run on?</h2>
      <p className="mt-2 text-sm text-ink-600">
        Knowing where your numbers live changes how your workspace answers, even before it can read
        them. Tick what you use.
      </p>

      {groups.map((group) => (
        <fieldset key={group.key} className="mt-4">
          <legend className="font-mono text-[11px] uppercase tracking-[0.18em] text-ink-400">
            {group.label}
          </legend>
          {group.note && <p className="mt-1 text-xs text-ink-400">{group.note}</p>}
          <ul className="mt-1.5 divide-y divide-bone-200">
            {group.tools.map((tool) => (
              <li key={tool.id}>
                <label className="flex cursor-pointer items-start gap-3 py-2.5">
                  <input
                    type="checkbox"
                    checked={chosen.has(tool.id)}
                    disabled={disabled}
                    onChange={() => toggle(tool.id)}
                    className="mt-0.5 h-4 w-4 shrink-0 accent-ink"
                  />
                  <span className="min-w-0">
                    <span className="block text-sm font-medium text-ink">{tool.name}</span>
                    {/* A capability, never a finding. */}
                    <span className="mt-0.5 block text-xs text-ink-400">{tool.unlocks}</span>
                  </span>
                </label>
              </li>
            ))}
          </ul>
        </fieldset>
      ))}

      {/* The honest sentence, and the reason this screen has checkboxes rather
          than Connect buttons. Rendered from `connectable` so it disappears on
          its own the day a real flow lands, rather than staying on screen
          after it stops being true. */}
      {catalogue !== null && catalogue.tools.every((tool) => !tool.connectable) && (
        <p className="mt-4 border-l-2 border-gold pl-2 text-[11px] leading-snug text-ink-400">
          Ticking a box records that you use it — it does not connect it. Signing in to these comes
          after setup, and until then your workspace will say which figures it cannot see yet
          instead of guessing at them.
        </p>
      )}

      {error && (
        <p role="alert" className="mt-3 text-xs text-clay-600">
          {error}
        </p>
      )}

      <div className="mt-4 flex flex-wrap items-center gap-3">
        <button
          type="button"
          // Held until the catalogue lands. Continuing before it does would
          // post an empty declaration and — because the write replaces rather
          // than appends — clear anything already on record.
          disabled={disabled || picked === null}
          onClick={() => onContinue(Array.from(chosen), chosen.size === 0)}
          className="rounded-full bg-ink px-5 py-2 text-sm font-medium text-bone-50 disabled:opacity-50"
        >
          {chosen.size > 0
            ? `Continue with ${chosen.size} ${chosen.size === 1 ? 'system' : 'systems'}`
            : 'I use none of these'}
        </button>
        {chosen.size > 0 && (
          <button
            type="button"
            disabled={disabled}
            onClick={() => onContinue([], true)}
            className="text-sm text-ink-400 underline decoration-bone-300 underline-offset-4 hover:text-ink-600 disabled:opacity-50"
          >
            Skip this
          </button>
        )}
      </div>
    </div>
  )
}
