'use client'

import { motion } from 'framer-motion'
import { useCallback, useEffect, useRef, useState } from 'react'
import { SectionHeading } from '@/components/ui/SectionHeading'
import { Reveal } from '@/components/motion/Reveal'
import { LoopMock } from '@/components/art/LoopMock'
import { loop } from '@/lib/content'

const AUTOPLAY_MS = 6200

export function Loop() {
  const [active, setActive] = useState(0)
  const [paused, setPaused] = useState(false)
  const sectionRef = useRef<HTMLElement>(null)
  const [inView, setInView] = useState(false)

  // Only autoplay while the section is actually on screen.
  useEffect(() => {
    const el = sectionRef.current
    if (!el) return
    const io = new IntersectionObserver(([e]) => setInView(e.isIntersecting), { threshold: 0.25 })
    io.observe(el)
    return () => io.disconnect()
  }, [])

  useEffect(() => {
    if (paused || !inView) return
    const id = window.setInterval(
      () => setActive((i) => (i + 1) % loop.steps.length),
      AUTOPLAY_MS,
    )
    return () => window.clearInterval(id)
  }, [paused, inView])

  const select = useCallback((i: number) => {
    setActive(i)
    setPaused(true)
  }, [])

  const step = loop.steps[active]
  const progress = ((active + 1) / loop.steps.length) * 100

  return (
    <section
      id="loop"
      ref={sectionRef}
      className="relative scroll-mt-24 overflow-hidden bg-bone-50 py-section"
    >
      {/* The cut-paper topographic contour background is gone (ADR 0072); the
          section rests on a clean neutral ground. */}
      <div className="shell relative">
        <SectionHeading eyebrow={loop.eyebrow} headline={loop.headline} sub={loop.sub} />

        {/* ── Stepper track ───────────────────────────────────── */}
        <Reveal delay={0.1}>
          <div
            className="relative mt-14"
            onMouseEnter={() => setPaused(true)}
            onFocusCapture={() => setPaused(true)}
          >
            <div className="absolute left-0 right-0 top-[1.4rem] h-px bg-bone-300" aria-hidden="true" />
            <motion.div
              className="absolute left-0 top-[1.4rem] h-px bg-ink-700"
              animate={{ width: `${progress}%` }}
              transition={{ duration: 0.7, ease: [0.16, 1, 0.3, 1] }}
              aria-hidden="true"
            />

            <div
              className="relative grid grid-cols-2 gap-y-8 sm:grid-cols-3 lg:grid-cols-5"
              role="tablist"
              aria-label="The NEXUS loop"
            >
              {loop.steps.map((s, i) => {
                const isActive = i === active
                const isPast = i < active
                return (
                  <button
                    key={s.id}
                    role="tab"
                    id={`loop-tab-${s.id}`}
                    aria-selected={isActive}
                    aria-controls={`loop-panel-${s.id}`}
                    onClick={() => select(i)}
                    className="group flex flex-col items-start text-left"
                  >
                    <span
                      className={`relative z-10 grid h-11 w-11 place-items-center rounded-full border-2 font-mono text-xs transition-all duration-500 ease-out-expo ${
                        isActive
                          ? 'border-ink-800 bg-ink-800 text-bone-50 shadow-paper'
                          : isPast
                            ? 'border-ink-700 bg-white text-ink-700'
                            : 'border-bone-300 bg-white text-ink-400 group-hover:border-steel-400 group-hover:text-steel-500'
                      }`}
                    >
                      {s.n}
                      {isActive ? (
                        <span className="absolute inset-0 rounded-full bg-ink-800/25 motion-safe:animate-pulse-ring" />
                      ) : null}
                    </span>
                    <span
                      className={`mt-4 font-display text-xl transition-colors duration-300 ${
                        isActive ? 'text-ink-800' : 'text-ink-400 group-hover:text-ink-600'
                      }`}
                    >
                      {s.title}
                    </span>
                    <span className="mt-1 pr-4 text-xs leading-relaxed text-ink-400">
                      {s.lead}
                    </span>
                  </button>
                )
              })}
            </div>
          </div>
        </Reveal>

        {/* ── Active panel ────────────────────────────────────── */}
        <Reveal delay={0.16}>
          <div
            className="mt-12 overflow-hidden rounded-panel border border-bone-300/70 bg-white shadow-paper-lg"
            onMouseEnter={() => setPaused(true)}
          >
            {/* Keyed remount rather than AnimatePresence: the panel swaps on
                every click, with no exit animation to wait on. */}
            <motion.div
              key={step.id}
              id={`loop-panel-${step.id}`}
              role="tabpanel"
              aria-labelledby={`loop-tab-${step.id}`}
              initial={{ opacity: 0, y: 18 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.45, ease: [0.16, 1, 0.3, 1] }}
              className="grid gap-0 lg:grid-cols-[0.9fr_1.1fr]"
            >
                <div className="flex flex-col justify-center p-8 sm:p-12">
                  <span className="eyebrow">
                    Stage {step.n} — {step.title}
                  </span>
                  <h3 className="mt-4 text-title text-balance">{step.lead}</h3>
                  <p className="mt-4 text-pretty leading-relaxed text-ink-500">{step.body}</p>
                  <div className="mt-7 flex flex-wrap gap-2">
                    {step.chips.map((c, i) => (
                      <motion.span
                        key={c}
                        initial={{ opacity: 0, y: 8 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ delay: 0.14 + i * 0.05, duration: 0.4 }}
                        className="rounded-full border border-bone-300 bg-bone-50 px-3 py-1.5 text-xs text-ink-600"
                      >
                        {c}
                      </motion.span>
                    ))}
                  </div>
                </div>

                <div className="relative border-t border-bone-200 bg-bone-50 p-8 sm:p-10 lg:border-l lg:border-t-0">
                  <LoopMock step={step.id} />
                </div>
            </motion.div>
          </div>
        </Reveal>

        {paused ? (
          <Reveal>
            <button
              onClick={() => setPaused(false)}
              className="mx-auto mt-6 block font-mono text-2xs uppercase tracking-[0.18em] text-ink-400 transition-colors hover:text-ink-700"
            >
              ▸ Resume auto-play
            </button>
          </Reveal>
        ) : null}
      </div>
    </section>
  )
}
