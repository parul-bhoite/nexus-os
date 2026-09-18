'use client'

import { motion } from 'framer-motion'
import { SectionHeading } from '@/components/ui/SectionHeading'
import { Reveal, RevealGroup, RevealItem } from '@/components/motion/Reveal'
import { IconCheck, IconMinus } from '@/components/art/Icons'
import { compare } from '@/lib/content'

export function Compare() {
  return (
    <section id="compare" className="relative scroll-mt-24 py-section">
      <div className="shell">
        <SectionHeading
          eyebrow={compare.eyebrow}
          headline={compare.headline}
          align="center"
        />

        <div className="mx-auto mt-14 max-w-5xl">
          {/* Column headers */}
          <Reveal>
            <div className="grid grid-cols-[1fr] gap-3 sm:grid-cols-[0.9fr_1fr_1fr]">
              <div className="hidden sm:block" />
              <div className="hidden rounded-t-2xl border border-b-0 border-bone-300/70 bg-bone-50 px-5 py-3.5 text-center sm:block">
                <span className="font-mono text-2xs uppercase tracking-[0.16em] text-ink-400">
                  {compare.themLabel}
                </span>
              </div>
              <div className="hidden rounded-t-2xl border border-b-0 border-ink-700 bg-ink-800 px-5 py-3.5 text-center sm:block">
                <span className="font-mono text-2xs uppercase tracking-[0.16em] text-gold-400">
                  {compare.usLabel}
                </span>
              </div>
            </div>
          </Reveal>

          <RevealGroup stagger={0.06}>
            {compare.rows.map((r, i) => {
              const last = i === compare.rows.length - 1
              return (
                <RevealItem key={r.dimension}>
                  {/* **No `whileHover={{ x: 3 }}`.** It translated the whole
                      row — label and both value cells — three pixels right on
                      hover, so the one thing a comparison table has to hold,
                      its columns, came apart under the pointer. The row is
                      still interactive-feeling; it just tints instead. */}
                  <motion.div className="group grid grid-cols-1 gap-3 sm:grid-cols-[0.9fr_1fr_1fr]">
                    {/* `items-start` and the same vertical padding as the cells
                        beside it. The label used to be `items-center` while the
                        values were `items-start`, so every row whose value
                        wrapped to two lines pushed its label half a line down —
                        a drift that reached 13px by the last row and read as
                        the table being slightly, inexplicably broken. */}
                    {/* `sm:pt-[0.8125rem]`, not `sm:py-4`.
                        Two corrections, measured rather than guessed. The cells
                        beside this one pad 16px; this one was emitting
                        `padding-top: 0` because Tailwind orders `pt-0` after
                        `py-4`, so the label sat 16px above its own row. And the
                        label is 18px on a 29.25px line box against the values'
                        14px on 22.75px, which puts its first baseline 3.25px
                        lower again — so the padding is 16 − 3.25 = 12.75px and
                        the two baselines actually meet. */}
                    <div className="flex items-start pt-5 sm:pb-4 sm:pt-[0.8125rem]">
                      <span className="font-display text-lg leading-relaxed text-ink-800">
                        {r.dimension}
                      </span>
                    </div>

                    <div
                      className={`flex items-start gap-2.5 border-x border-b border-bone-300/70 bg-bone-50/60 px-5 py-4 transition-colors duration-base ease-out group-hover:bg-bone-100 ${
                        last ? 'rounded-b-2xl' : ''
                      } border-t sm:border-t-0`}
                    >
                      <IconMinus className="mt-0.5 h-4 w-4 shrink-0 text-ink-400" />
                      <span className="text-sm leading-relaxed text-ink-500">{r.them}</span>
                    </div>

                    <div
                      className={`flex items-start gap-2.5 border-x border-b border-ink-700 bg-ink-800 px-5 py-4 transition-colors duration-base ease-out group-hover:bg-ink-700 ${
                        last ? 'rounded-b-2xl' : ''
                      } border-t sm:border-t-0`}
                    >
                      <IconCheck className="mt-0.5 h-4 w-4 shrink-0 text-gold-400" />
                      <span className="text-sm leading-relaxed text-bone-100">{r.us}</span>
                    </div>
                  </motion.div>
                </RevealItem>
              )
            })}
          </RevealGroup>
        </div>
      </div>
    </section>
  )
}
