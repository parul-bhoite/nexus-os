'use client'

import { motion, useReducedMotion } from 'framer-motion'
import { useRef, useState } from 'react'
import { SectionHeading } from '@/components/ui/SectionHeading'
import { RevealGroup, RevealItem } from '@/components/motion/Reveal'
import { pillars } from '@/lib/content'

/**
 * Three surfaces, not five.
 *
 * The section used to draw one card in navy, one in gold-100, one in clay-100,
 * one in white and one in slate-100 — five fills, carrying no meaning, in a
 * palette whose whole discipline is that colour marks something. A reader
 * cannot help looking for the pattern, and there is none: Growth is gold and
 * Sales is clay for no reason either of them could name.
 *
 * So: `feature` for the two that span two columns, `plain` and `tint` for the
 * rest, alternating. The rhythm that made the bento work is kept; the five-way
 * colour code that made it noisy is not. `gold`, `clay`, `slate` and `steel`
 * still resolve, because `lib/content.ts` names them — they simply resolve to
 * the two neutrals now, which is the whole change.
 */
const tones: Record<
  string,
  { card: string; title: string; body: string; chip: string; rule: string }
> = {
  ink: {
    card: 'bg-ink-800 border-ink-700',
    title: 'text-bone-50',
    body: 'text-slate-300',
    chip: 'border-white/15 bg-white/5 text-bone-200',
    rule: 'bg-white/10',
  },
  plain: {
    card: 'bg-white border-bone-300/70',
    title: 'text-ink-800',
    body: 'text-ink-500',
    chip: 'border-bone-300 bg-bone-50 text-ink-600',
    rule: 'bg-bone-300',
  },
  tint: {
    card: 'bg-bone-100 border-bone-300/70',
    title: 'text-ink-800',
    body: 'text-ink-600',
    chip: 'border-bone-300 bg-white/70 text-ink-600',
    rule: 'bg-bone-300',
  },
}

/** The four retired names, mapped onto the two neutrals that replaced them. */
const TONE_ALIAS: Record<string, string> = {
  gold: 'tint',
  clay: 'plain',
  steel: 'plain',
  slate: 'tint',
}

/** A cursor-following highlight — cheap, and it makes a static grid feel alive. */
function Spotlight({ active, tone }: { active: { x: number; y: number } | null; tone: string }) {
  if (!active) return null
  const colour = tone === 'ink' ? 'rgba(239,191,106,0.16)' : 'rgba(9,31,70,0.06)'
  return (
    <div
      aria-hidden="true"
      className="pointer-events-none absolute inset-0 opacity-0 transition-opacity duration-300 group-hover:opacity-100"
      style={{
        background: `radial-gradient(18rem 18rem at ${active.x}px ${active.y}px, ${colour}, transparent 70%)`,
        opacity: 1,
      }}
    />
  )
}

function PillarCard({
  title,
  promise,
  items,
  tone,
  span,
}: {
  title: string
  promise: string
  items: readonly string[]
  tone: string
  span: string
}) {
  const t = tones[tone] ?? tones[TONE_ALIAS[tone] ?? 'plain'] ?? tones.plain
  const wide = span === 'lg'
  const ref = useRef<HTMLDivElement>(null)
  const [pos, setPos] = useState<{ x: number; y: number } | null>(null)
  const reduced = useReducedMotion()

  return (
    <RevealItem className={wide ? 'sm:col-span-2' : ''}>
      <motion.div
        ref={ref}
        onMouseMove={(e) => {
          if (reduced) return
          const r = ref.current?.getBoundingClientRect()
          if (r) setPos({ x: e.clientX - r.left, y: e.clientY - r.top })
        }}
        onMouseLeave={() => setPos(null)}
        whileHover={reduced ? undefined : { y: -6 }}
        transition={{ duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
        className={`group relative flex h-full flex-col overflow-hidden rounded-card border p-7 shadow-paper transition-shadow duration-400 hover:shadow-paper-lg ${t.card}`}
      >
        <Spotlight active={pos} tone={tone} />

        {/* A two-column interior for the wide cards, and only for them.
            A card twice as wide as its neighbours held the same single column
            of text, so its five chips fitted in two rows instead of five — and
            with `mt-auto` pinning them to the bottom of a row sized by a taller
            sibling, the result was ~200px of empty navy between the rule and
            the chips. The space was real; what was wrong was putting it in the
            middle of the card, where it reads as a failed render, rather than
            using the width the card actually has. */}
        <div
          className={`relative z-10 flex h-full flex-col gap-5 ${
            // Centred, not top-aligned. `auto-rows-fr` makes the row as tall
            // as its tallest card, and the wide card's two-column interior is
            // the shortest content in the row — so top-aligning it left ~180px
            // of empty navy below the chips. Centred, the same space becomes
            // symmetrical padding, which reads as a roomy feature card rather
            // than as one that failed to fill.
            wide ? 'lg:flex-row lg:items-center lg:gap-10' : ''
          }`}
        >
          <div className={wide ? 'lg:w-[34%] lg:shrink-0' : ''}>
            <h3 className={`font-display text-2xl leading-tight ${t.title}`}>{title}</h3>
            <p className={`mt-2.5 text-pretty text-[0.95rem] leading-relaxed ${t.body}`}>
              {promise}
            </p>
          </div>

          <div className={`h-px w-full ${t.rule} ${wide ? 'lg:hidden' : ''}`} />

          {/* No `mt-auto`. Spare height now falls as padding at the foot of the
              card, which reads as room; in the middle it read as a gap. */}
          <ul className="flex flex-wrap content-start gap-2">
            {items.map((item) => (
              <li
                key={item}
                className={`rounded-full border px-3 py-1.5 text-xs transition-transform duration-base ease-out group-hover:-translate-y-0.5 ${t.chip}`}
              >
                {item}
              </li>
            ))}
          </ul>
        </div>
      </motion.div>
    </RevealItem>
  )
}

export function Pillars() {
  return (
    <section id="pillars" className="relative scroll-mt-24 bg-bone-50 py-section">
      <div className="shell">
        <SectionHeading
          eyebrow={pillars.eyebrow}
          headline={pillars.headline}
          sub={pillars.sub}
          align="center"
        />

        {/* **Three columns, not four.** Seven pillars, two of which span two
            columns, is nine cells. Nine into four is 4 + 3 + 2, so the grid
            rendered two visible holes — one beside the third row of cards and
            one two-thirds of a row wide beneath it. Nine into three is 3 + 3 +
            3, and the served order happens to place both wide cards at the
            start of a row, so it tiles exactly:

                [ Executive Command    ][ Growth  ]
                [ Sales ][ Competitive ][ Customers ]
                [ People ][ Money & Risk           ]

            At `sm` there are two columns and seven cards, so one hole is
            arithmetically unavoidable — it falls in the last row against the
            section's own background, where an empty cell is invisible. */}
        <RevealGroup
          className="mt-14 grid auto-rows-fr gap-4 sm:grid-cols-2 lg:grid-cols-3"
          stagger={0.05}
        >
          {pillars.list.map((p) => (
            <PillarCard
              key={p.title}
              title={p.title}
              promise={p.promise}
              items={p.items}
              tone={p.tone}
              span={p.span}
            />
          ))}
        </RevealGroup>
      </div>
    </section>
  )
}
