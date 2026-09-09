'use client'

import { motion } from 'framer-motion'
import { SectionHeading } from '@/components/ui/SectionHeading'
import { Reveal, RevealGroup, RevealItem } from '@/components/motion/Reveal'
import { Button, ArrowRight } from '@/components/ui/Button'
import { IconCheck, IconMinus } from '@/components/art/Icons'
import { pricing } from '@/lib/content'

export function Pricing() {
  return (
    <section id="pricing" className="relative scroll-mt-24 bg-bone-50 py-section">
      <div className="shell">
        <SectionHeading
          eyebrow={pricing.eyebrow}
          headline={pricing.headline}
          sub={pricing.sub}
          align="center"
        />

        <RevealGroup className="mt-16 grid gap-5 lg:grid-cols-3" stagger={0.09}>
          {pricing.tiers.map((t) => (
            <RevealItem key={t.name} className={t.featured ? 'lg:-mt-4 lg:mb-4' : ''}>
              <motion.div
                whileHover={{ y: -6 }}
                transition={{ duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
                className={`relative flex h-full flex-col rounded-panel border p-8 ${
                  t.featured
                    ? 'border-ink-700 bg-ink-800 shadow-paper-xl'
                    : 'border-bone-300/70 bg-white shadow-paper'
                }`}
              >
                {t.featured ? (
                  <span className="absolute -top-3 left-8 rounded-full bg-gold-400 px-3 py-1 font-mono text-2xs uppercase tracking-[0.16em] text-ink-900">
                    Most complete
                  </span>
                ) : null}

                <h3
                  className={`font-display text-2xl ${t.featured ? 'text-bone-50' : 'text-ink-800'}`}
                >
                  {t.name}
                </h3>
                <p className={`mt-1.5 text-sm ${t.featured ? 'text-slate-300' : 'text-ink-400'}`}>
                  {t.for}
                </p>

                <div className="mt-7 flex items-baseline gap-1.5">
                  <span
                    className={`font-display text-4xl ${
                      t.featured ? 'text-bone-50' : 'text-ink-800'
                    }`}
                  >
                    {t.price}
                  </span>
                  {t.cadence ? (
                    <span className={`text-sm ${t.featured ? 'text-slate-400' : 'text-ink-400'}`}>
                      {t.cadence}
                    </span>
                  ) : null}
                </div>

                <div
                  className={`my-7 h-px w-full ${t.featured ? 'bg-white/10' : 'bg-bone-200'}`}
                />

                <ul className="space-y-2.5">
                  {t.includes.map((f) => (
                    <li key={f} className="flex items-start gap-2.5">
                      <IconCheck
                        className={`mt-0.5 h-4 w-4 shrink-0 ${
                          t.featured ? 'text-gold-400' : 'text-steel-500'
                        }`}
                      />
                      <span
                        className={`text-sm leading-relaxed ${
                          t.featured ? 'text-bone-100' : 'text-ink-600'
                        }`}
                      >
                        {f}
                      </span>
                    </li>
                  ))}
                  {/* Excluded lines are signalled by the strike and the minus
                      glyph, not by low opacity — dimming them below AA would
                      make real content unreadable. */}
                  {t.excludes.map((f) => (
                    <li key={f} className="flex items-start gap-2.5">
                      <IconMinus
                        className={`mt-0.5 h-4 w-4 shrink-0 ${
                          t.featured ? 'text-slate-400' : 'text-ink-400'
                        }`}
                      />
                      <span
                        className={`text-sm leading-relaxed line-through ${
                          t.featured ? 'text-slate-400' : 'text-ink-400'
                        }`}
                      >
                        {f}
                      </span>
                    </li>
                  ))}
                </ul>

                <div className="mt-auto pt-8">
                  <Button
                    href={t.href}
                    size="lg"
                    variant={t.featured ? 'onDark' : 'secondary'}
                    icon={<ArrowRight />}
                    className="w-full"
                  >
                    {t.cta}
                  </Button>
                </div>
              </motion.div>
            </RevealItem>
          ))}
        </RevealGroup>

        <Reveal delay={0.1}>
          <p className="mx-auto mt-10 max-w-2xl text-center text-xs leading-relaxed text-ink-400">
            {pricing.disclaimer}
          </p>
        </Reveal>
      </div>
    </section>
  )
}
