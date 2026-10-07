'use client'

import { motion } from 'framer-motion'
import { SectionHeading } from '@/components/ui/SectionHeading'
import { RevealGroup, RevealItem } from '@/components/motion/Reveal'
import { moments } from '@/lib/content'

/**
 * The three moments, as a crisp monochrome timeline (ADR 0072). The old soft
 * amber pulse-ring halos are gone; each moment is a numbered marker with its
 * timestamp, joined by a hairline that draws in on scroll.
 */
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
                  {/* A hairline joining this marker to the next — per item, so it
                      never runs off the end of the row. */}
                  {i < moments.list.length - 1 ? (
                    <motion.span
                      aria-hidden="true"
                      initial={{ scaleX: 0 }}
                      whileInView={{ scaleX: 1 }}
                      viewport={{ once: true, amount: 0.3 }}
                      transition={{ duration: 0.8, delay: 0.1 * i, ease: [0.16, 1, 0.3, 1] }}
                      className="absolute left-[3.75rem] right-[-2rem] top-7 hidden h-px origin-left bg-ink-200 lg:block"
                    />
                  ) : null}

                  <div className="flex items-center gap-4">
                    <span className="relative z-10 grid h-14 w-14 shrink-0 place-items-center rounded-full border border-ink-200 bg-white shadow-e1">
                      <span className="font-mono text-2xs uppercase leading-tight tracking-[0.1em] text-ink-500">
                        {m.when.split(' ')[0]}
                        <br />
                        <span className="text-ink-900">{m.when.split(' ')[1]}</span>
                      </span>
                    </span>
                    <span className="flex items-center gap-2">
                      <span className="font-mono text-2xs text-ink-400">0{i + 1}</span>
                      <span className="h-1.5 w-1.5 rounded-full bg-gold-500" />
                    </span>
                  </div>

                  <h3 className="mt-6 font-display text-title font-semibold text-ink-900">
                    {m.title}
                  </h3>
                  <p className="mt-3 text-pretty leading-relaxed text-ink-500 lg:pr-6">{m.body}</p>
                </div>
              </RevealItem>
            ))}
          </RevealGroup>
        </div>
      </div>
    </section>
  )
}
