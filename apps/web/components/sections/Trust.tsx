'use client'

import { motion } from 'framer-motion'
import { SectionHeading } from '@/components/ui/SectionHeading'
import { Reveal, RevealGroup, RevealItem } from '@/components/motion/Reveal'
import { IconShield } from '@/components/art/Icons'
import { trust } from '@/lib/content'

export function Trust() {
  return (
    <section id="trust" className="relative scroll-mt-24 py-section">
      <div className="shell">
        {/* A contained dark panel rather than a full-bleed band — the page stays
            light, and this section still gets the gravity it needs. */}
        <Reveal>
          <div className="relative overflow-hidden rounded-panel bg-ink-950 px-7 py-16 shadow-e3 sm:px-12 lg:px-16 lg:py-20">
            {/* The brand X, ghosted in the corner — the monochrome replacement
                for the old water-swirl contour texture (ADR 0072). */}
            <svg
              viewBox="0 0 100 100"
              aria-hidden="true"
              className="pointer-events-none absolute -right-20 -top-24 h-[32rem] w-[32rem]"
              fill="none"
            >
              <line x1="26" y1="26" x2="74" y2="74" className="stroke-white/[0.04]" strokeWidth="11" strokeLinecap="round" />
              <line x1="26" y1="74" x2="50" y2="50" className="stroke-white/[0.04]" strokeWidth="11" strokeLinecap="round" />
              <line x1="50" y1="50" x2="74" y2="26" className="stroke-gold-500/20" strokeWidth="11" strokeLinecap="round" />
            </svg>

            <div className="relative">
              <div className="grid gap-12 lg:grid-cols-[1fr_1.15fr] lg:gap-16">
                <div>
                  <SectionHeading
                    eyebrow={trust.eyebrow}
                    headline={
                      <>
                        Never invent
                        <br />
                        <span className="text-gold-400">a number.</span>
                      </>
                    }
                    sub={trust.sub}
                    tone="dark"
                  />

                  {/* The pipeline, as a vertical trace. */}
                  <RevealGroup className="mt-12 space-y-0" stagger={0.08}>
                    {trust.pipeline.map((p, i) => (
                      <RevealItem key={p.step}>
                        <div className="flex gap-4">
                          <div className="flex flex-col items-center">
                            <span className="grid h-7 w-7 shrink-0 place-items-center rounded-full border border-gold-400/40 bg-ink-900 font-mono text-2xs text-gold-400">
                              {i + 1}
                            </span>
                            {i < trust.pipeline.length - 1 ? (
                              <span className="my-1 w-px flex-1 bg-gradient-to-b from-gold-400/40 to-white/10" />
                            ) : null}
                          </div>
                          <div className="pb-6">
                            <span className="block text-sm font-medium text-bone-100">
                              {p.step}
                            </span>
                            <span className="mt-0.5 block font-mono text-2xs text-slate-400">
                              {p.note}
                            </span>
                          </div>
                        </div>
                      </RevealItem>
                    ))}
                  </RevealGroup>
                </div>

                <RevealGroup className="space-y-3" stagger={0.08}>
                  {trust.rules.map((r) => (
                    <RevealItem key={r.title}>
                      <motion.div
                        whileHover={{ x: 5 }}
                        transition={{ duration: 0.35, ease: [0.16, 1, 0.3, 1] }}
                        className="rounded-2xl border border-white/10 bg-white/[0.04] p-5 backdrop-blur-sm transition-colors duration-300 hover:border-gold-400/30 hover:bg-white/[0.07]"
                      >
                        <div className="flex items-start gap-3.5">
                          <span className="mt-0.5 grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-gold-400/15 text-gold-400">
                            <IconShield className="h-4 w-4" />
                          </span>
                          <div>
                            <h3 className="text-[0.98rem] font-medium text-bone-50">{r.title}</h3>
                            <p className="mt-1.5 text-pretty text-sm leading-relaxed text-slate-300">
                              {r.body}
                            </p>
                          </div>
                        </div>
                      </motion.div>
                    </RevealItem>
                  ))}

                  <RevealItem>
                    <p className="pt-3 text-xs leading-relaxed text-slate-400">
                      This is not marketing language. It is enforced as a per-module engineering
                      contract with an automated test suite that runs on every change.
                    </p>
                  </RevealItem>
                </RevealGroup>
              </div>
            </div>
          </div>
        </Reveal>
      </div>
    </section>
  )
}
