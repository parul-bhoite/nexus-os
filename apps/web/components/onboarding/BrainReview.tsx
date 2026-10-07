'use client'

import type { AgentState } from '@/lib/agent-onboarding-client'
import type { BrainItem } from '@/components/onboarding/BrainPanel'
import { mapAgentStateToBrainGroups } from '@/components/onboarding/BrainPanel'
import { PresenceMark } from '@/components/onboarding/OnboardingAura'

/**
 * Step 6 of the stepped onboarding (ADR 0073): the Company Brain, read-only.
 *
 * ADR 0069 showed the Brain live beside the chat and let the founder correct
 * facts inline at a `brief`/`persona` gate. The product owner chose instead to
 * show it **read-only at the end**, with corrections moving to Settings — so
 * this renders the assembled Brain grouped by provenance (reusing the pure
 * `mapAgentStateToBrainGroups`) and a single action onward to the dashboard.
 *
 * While the Brain is still being assembled (`building`), it shows a staged
 * loader rather than an empty frame — the facts appear only once they are real.
 */

const TAG_CLASS: Record<BrainItem['kind'], string> = {
  read: 'bg-steel-100 text-steel-700',
  inferred: 'bg-gold-100 text-gold-700',
  you: 'bg-clay-100 text-clay-700',
}

export function BrainReview({
  state,
  departments,
  building,
  onOpen,
}: {
  state: AgentState
  departments: string[]
  building: boolean
  onOpen: () => void
}) {
  if (building) return <Building />

  const groups = mapAgentStateToBrainGroups(state, departments).filter((group) => group.items.length > 0)

  return (
    <div className="flex flex-col gap-6">
      <div>
        <div className="flex items-center gap-3">
          <PresenceMark state="ready" size={30} />
          <h1 className="font-display text-page text-ink-900">Your Company Brain is ready</h1>
        </div>
        <p className="mt-2 max-w-read text-body text-ink-600">
          This is everything NEXUS is working from, and where each part came from. Every director
          reads it. You can correct anything in Settings — nothing here is a score.
        </p>
      </div>

      {groups.length === 0 ? (
        <div role="status" className="rounded-data border border-dashed border-bone-400 px-6 py-5">
          <p className="text-sm text-ink-600">
            Nothing was captured this run. Your workspace will start from your role and learn the
            rest as you use it.
          </p>
        </div>
      ) : (
        <div className="flex flex-col gap-6">
          {groups.map((group) => (
            <section key={group.key} aria-label={`${group.title} · ${group.subtitle}`}>
              <p className="text-sm font-semibold text-ink-800">
                {group.title}
                <span className="ml-1.5 font-normal text-ink-400">· {group.subtitle}</span>
              </p>
              <ul className="mt-2 flex flex-col gap-2.5">
                {group.items.map((item) => (
                  <li key={item.id} className="rounded-xl border border-bone-200 bg-white/90 p-3">
                    <p className="text-[11px] font-medium text-ink-500">{item.label}</p>
                    <p className="mt-0.5 text-sm leading-snug text-ink-800">{item.value}</p>
                    <span
                      className={`mt-1.5 inline-block rounded px-1.5 py-0.5 font-mono text-[10px] ${TAG_CLASS[item.kind]}`}
                    >
                      {item.provenance}
                    </span>
                  </li>
                ))}
              </ul>
            </section>
          ))}
        </div>
      )}

      <div className="mt-2">
        <button
          type="button"
          onClick={onOpen}
          className="min-h-[2.75rem] rounded-full bg-ink px-7 text-sm font-medium text-bone-50 shadow-paper transition-transform hover:scale-[1.02]"
        >
          Open my workspace
        </button>
      </div>
    </div>
  )
}

function Building() {
  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center gap-3">
        <PresenceMark state="thinking" size={30} />
        <h1 className="font-display text-page text-ink-900">Building your Company Brain</h1>
      </div>
      <p role="status" aria-live="polite" className="max-w-read text-body text-ink-500">
        Turning everything you told us into facts, each with its source. This takes a few seconds.
      </p>
      <ul aria-hidden className="flex flex-col gap-3">
        {['Reading your answers', 'Writing the facts', 'Personalising your workspace'].map((label) => (
          <li key={label} className="flex items-center gap-3">
            <span className="h-2 w-2 animate-breathe rounded-full bg-steel-400" />
            <span className="text-sm text-ink-400">{label}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}
