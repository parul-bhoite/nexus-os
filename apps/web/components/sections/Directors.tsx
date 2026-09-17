'use client'

import { SectionHeading } from '@/components/ui/SectionHeading'
import { Reveal, RevealGroup, RevealItem } from '@/components/motion/Reveal'
import { directors } from '@/lib/content'

const accents: Record<string, { bg: string; fg: string; mark: string }> = {
  gold: { bg: 'bg-gold-200', fg: 'text-gold-700', mark: '#EFBF6A' },
  steel: { bg: 'bg-steel-100', fg: 'text-steel-600', mark: '#37729C' },
  clay: { bg: 'bg-clay-100', fg: 'text-clay-600', mark: '#A55D35' },
  ink: { bg: 'bg-ink-100', fg: 'text-ink-700', mark: '#091F46' },
  slate: { bg: 'bg-slate-100', fg: 'text-slate-600', mark: '#7699AE' },
}

/**
 * A paper-cut "portrait" — deliberately abstract. Illustrating an AI director
 * as a human face would overclaim; layered shapes read as a role, not a person.
 */
function DirectorMark({ seed, colour }: { seed: number; colour: string }) {
  const rot = (seed * 37) % 40 - 20
  return (
    <svg viewBox="0 0 64 64" className="h-14 w-14" aria-hidden="true">
      <circle cx="32" cy="32" r="30" fill="#FFFFFF" />
      <g transform={`rotate(${rot} 32 32)`}>
        <path d="M32 8a24 24 0 0 1 24 24H32z" fill={colour} opacity="0.9" />
        <path d="M32 32h24a24 24 0 0 1-24 24z" fill={colour} opacity="0.45" />
        <path d="M8 32a24 24 0 0 1 24-24v24z" fill={colour} opacity="0.22" />
      </g>
      <circle cx="32" cy="32" r="7" fill="#FFFFFF" />
      <circle cx="32" cy="32" r="30" fill="none" stroke="#D8D0C7" strokeWidth="1.5" />
    </svg>
  )
}

function DirectorCard({
  name,
  owns,
  accent,
  index,
  lead = false,
}: {
  name: string
  owns: string
  accent: string
  index: number
  /** The Chief of Staff, which reads the other six. Drawn across the row. */
  lead?: boolean
}) {
  const a = accents[accent] ?? accents.steel
  return (
    <article
      className={`group flex h-full flex-col rounded-card border border-bone-300/70 bg-white p-6 shadow-e1 transition-[box-shadow,transform] duration-base ease-out hover:-translate-y-0.5 hover:shadow-e2 ${
        lead ? 'sm:col-span-2 lg:col-span-3 lg:flex-row lg:items-center lg:gap-7' : ''
      }`}
    >
      <div className={`w-fit shrink-0 rounded-2xl p-2 ${a.bg}`}>
        <DirectorMark seed={index} colour={a.mark} />
      </div>
      <div className={lead ? 'lg:flex-1' : ''}>
        <h3 className={`font-display text-ink-800 ${lead ? 'mt-5 text-2xl lg:mt-0' : 'mt-5 text-xl'}`}>
          {name}
        </h3>
        <p className="mt-2 text-pretty text-sm leading-relaxed text-ink-500">{owns}</p>
      </div>
      {/* Said once, on the card whose whole job is reading the others — not
          seven times down a row, where it stopped being a claim and became a
          rule under every heading. */}
      {lead ? (
        <span
          className={`mt-4 shrink-0 text-2xs uppercase tracking-[0.16em] lg:mt-0 ${a.fg}`}
        >
          reads the company brain
        </span>
      ) : null}
    </article>
  )
}

export function Directors() {
  return (
    <section id="team" className="relative scroll-mt-24 overflow-hidden py-section">
      <div className="shell">
        <SectionHeading
          eyebrow={directors.eyebrow}
          headline={directors.headline}
          sub={directors.sub}
          align="center"
        />
      </div>

      {/* **A grid, not a belt.**
          This was two identical tracks scrolling as one 46-second loop. Three
          things were wrong with it, and only the third is a matter of taste:

          1. **WCAG 2.2.2.** Content that moves automatically for more than five
             seconds needs a mechanism to pause it. `pause-on-hover` is not one
             — it is unreachable from a keyboard and meaningless on a touch
             screen, which is most of the traffic a landing page gets.
          2. **You could not read it.** Cards were clipped mid-word at both
             edges at all times, and seeing all seven meant waiting out the
             loop. Seven items is a grid; a carousel is for a list whose length
             you do not control.
          3. It was motion for its own sake on a page that already had
             twenty-seven infinite animations running at once.

          Seven into three columns is 3 + 3 + 1, which leaves two holes — so the
          Chief of Staff, which is the one that reads the other six, spans the
          first row. That tiles exactly and it is also the truthful hierarchy. */}
      <div className="shell">
        <RevealGroup className="mt-14 grid gap-4 sm:grid-cols-2 lg:grid-cols-3" stagger={0.05}>
          {directors.list.map((d, i) => (
            <RevealItem key={d.name} className={i === 0 ? 'sm:col-span-2 lg:col-span-3' : ''}>
              <DirectorCard name={d.name} owns={d.owns} accent={d.accent} index={i} lead={i === 0} />
            </RevealItem>
          ))}
        </RevealGroup>
      </div>

      <div className="shell">
        <Reveal delay={0.16}>
          <p className="mx-auto mt-12 max-w-xl text-center text-sm text-ink-400">
            Seven directors, one shared understanding of your business. The Sales Director already
            knows what the Finance Advisor knows.
          </p>
        </Reveal>
      </div>
    </section>
  )
}
