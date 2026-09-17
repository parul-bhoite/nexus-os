'use client'

import { motion } from 'framer-motion'
import { SectionHeading } from '@/components/ui/SectionHeading'
import { RevealGroup, RevealItem } from '@/components/motion/Reveal'
import { moments } from '@/lib/content'

export function Moments() {
  return (
    <section id="moments" className="relative scroll-mt-24 py-section">
      <div className="shell">
        <SectionHeading
          eyebrow={moments.eyebrow}
          headline={moments.headline}
          sub={moments.sub}
          align="center"
        />

        <div className="relative mt-16">
          <RevealGroup className="grid gap-10 lg:grid-cols-3 lg:gap-8" stagger={0.12}>
            {moments.list.map((m, i) => (
              <RevealItem key={m.when}>
                <div className="relative">
                  {/* The thread, drawn per item rather than once across the
                      row. One absolutely positioned line spanning the whole
                      grid ran past the third circle and off to the right edge,
                      which reads as a fourth moment that failed to render. A
                      segment that belongs to an item and stops at its
                      neighbour cannot do that, whatever the column count. */}
                  {i < moments.list.length - 1 ? (
                    <motion.span
                      aria-hidden="true"
                      initial={{ scaleX: 0 }}
                      whileInView={{ scaleX: 1 }}
                      viewport={{ once: true, amount: 0.3 }}
                      transition={{ duration: 0.8, delay: 0.1 * i, ease: [0.16, 1, 0.3, 1] }}
                      className="absolute left-[4.5rem] right-[-2rem] top-9 hidden h-px origin-left bg-gradient-to-r from-gold-400/70 to-bone-300 lg:block"
                    />
                  ) : null}

                  <div className="flex items-center gap-4">
                    <span className="relative z-10 grid h-[4.5rem] w-[4.5rem] shrink-0 place-items-center rounded-full border border-bone-300 bg-white shadow-paper">
                      <span className="font-mono text-2xs uppercase leading-tight tracking-[0.12em] text-ink-500">
                        {m.when.split(' ')[0]}
                        <br />
                        <span className="text-gold-700">{m.when.split(' ')[1]}</span>
                      </span>
                      <span
                        className="absolute inset-0 rounded-full bg-gold-400/30 motion-safe:animate-pulse-ring"
                        style={{ animationDelay: `${i * -1.1}s` }}
                      />
                    </span>
                    <h3 className="font-display text-2xl text-ink-800">{m.title}</h3>
                  </div>
                  <p className="mt-5 text-pretty leading-relaxed text-ink-500 lg:pr-6">{m.body}</p>
                </div>
              </RevealItem>
            ))}
          </RevealGroup>
        </div>
      </div>
    </section>
  )
}
