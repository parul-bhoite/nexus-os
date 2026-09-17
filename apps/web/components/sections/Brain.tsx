'use client'

import { motion } from 'framer-motion'
import { SectionHeading } from '@/components/ui/SectionHeading'
import { Reveal, RevealGroup, RevealItem } from '@/components/motion/Reveal'
import { brain } from '@/lib/content'

const R = 158 // orbit radius in SVG units
const CX = 210
const CY = 210

function polar(angleDeg: number, radius: number) {
  const rad = (angleDeg * Math.PI) / 180
  return { x: CX + radius * Math.cos(rad), y: CY + radius * Math.sin(rad) }
}

function BrainDiagram() {
  return (
    <div className="relative mx-auto aspect-square w-full max-w-[26rem]">
      <svg viewBox="0 0 420 420" className="h-full w-full" role="img" aria-label="Diagram: six connected data sources feeding one central Company Brain.">
        <defs>
          <radialGradient id="coreGlow" cx="0.5" cy="0.5" r="0.5">
            <stop offset="0%" stopColor="#EFBF6A" stopOpacity="0.4" />
            <stop offset="100%" stopColor="#EFBF6A" stopOpacity="0" />
          </radialGradient>
          <filter id="brainLift" x="-30%" y="-30%" width="160%" height="160%">
            <feDropShadow dx="0" dy="6" stdDeviation="10" floodColor="#091F46" floodOpacity="0.2" />
          </filter>
        </defs>

        {/* Orbit rings */}
        <circle cx={CX} cy={CY} r={R} fill="none" stroke="#D8D0C7" strokeWidth="1" />
        <circle
          cx={CX}
          cy={CY}
          r={R - 34}
          fill="none"
          stroke="#D8D0C7"
          strokeWidth="1"
          strokeDasharray="3 7"
          opacity="0.8"
        />

        {/* Connectors — dashes flow inward toward the core. */}
        {brain.nodes.map((n, i) => {
          const p = polar(n.angle, R)
          return (
            <line
              key={n.label}
              x1={p.x}
              y1={p.y}
              x2={CX}
              y2={CY}
              stroke="#7699AE"
              strokeWidth="1.4"
              strokeDasharray="5 9"
              opacity="0.6"
              className="motion-safe:animate-dash-flow"
              style={{ animationDelay: `${i * -3}s` }}
            />
          )
        })}

        {/* Core glow */}
        <circle cx={CX} cy={CY} r={92} fill="url(#coreGlow)" />

        {/* Core — stacked paper discs */}
        <g filter="url(#brainLift)">
          <circle cx={CX} cy={CY + 6} r={58} fill="#37729C" />
          <circle cx={CX} cy={CY} r={58} fill="#091F46" />
          <circle cx={CX} cy={CY} r={58} fill="none" stroke="#EFBF6A" strokeWidth="1.5" opacity="0.5" />
        </g>

        {/* Contour lines inside the core, echoing the water swirls */}
        <g stroke="#7699AE" fill="none" opacity="0.55" strokeLinecap="round">
          {[16, 26, 36, 46].map((r, i) => (
            <path
              key={r}
              d={`M${CX - r} ${CY + 4 - i * 3}a${r} ${r * 0.5} 0 0 1 ${r * 2} 0`}
              strokeWidth="1.3"
            />
          ))}
        </g>

        <text
          x={CX}
          y={CY + 3}
          textAnchor="middle"
          className="fill-bone-50 font-mono"
          style={{ fontSize: 10, letterSpacing: '0.16em' }}
        >
          COMPANY
        </text>
        <text
          x={CX}
          y={CY + 18}
          textAnchor="middle"
          className="fill-gold-400 font-mono"
          style={{ fontSize: 10, letterSpacing: '0.16em' }}
        >
          BRAIN
        </text>

        {/* Source nodes */}
        {brain.nodes.map((n, i) => {
          const p = polar(n.angle, R)
          return (
            <motion.g
              key={n.label}
              initial={{ opacity: 0, scale: 0.6 }}
              whileInView={{ opacity: 1, scale: 1 }}
              viewport={{ once: true, amount: 0.4 }}
              transition={{ delay: 0.2 + i * 0.09, duration: 0.55, ease: [0.16, 1, 0.3, 1] }}
            >
              <circle cx={p.x} cy={p.y} r={26} fill="#FFFFFF" stroke="#D8D0C7" strokeWidth="1.5" />
              <circle cx={p.x} cy={p.y} r={7} fill="#37729C" />
              <circle
                cx={p.x}
                cy={p.y}
                r={7}
                fill="#37729C"
                opacity="0.35"
                className="motion-safe:animate-pulse-ring"
                style={{ transformOrigin: `${p.x}px ${p.y}px`, animationDelay: `${i * -0.6}s` }}
              />
              <text
                x={p.x}
                y={p.y + 42}
                textAnchor="middle"
                className="fill-ink-500 font-sans"
                style={{ fontSize: 11 }}
              >
                {n.label}
              </text>
            </motion.g>
          )
        })}
      </svg>
    </div>
  )
}

export function Brain() {
  return (
    <section id="brain" className="relative scroll-mt-24 py-section">
      <div className="shell">
        <div className="grid items-center gap-14 lg:grid-cols-2 lg:gap-20">
          <div>
            <SectionHeading eyebrow={brain.eyebrow} headline={brain.headline} sub={brain.sub} />

            <RevealGroup className="mt-10 space-y-7" stagger={0.09}>
              {brain.points.map((p, i) => (
                <RevealItem key={p.title}>
                  <div className="flex gap-5">
                    <span className="mt-1 font-mono text-xs text-gold-700">
                      {String(i + 1).padStart(2, '0')}
                    </span>
                    <div className="border-l border-bone-300 pl-5">
                      <h3 className="text-lg font-medium text-ink-800">{p.title}</h3>
                      <p className="mt-1.5 text-pretty leading-relaxed text-ink-500">{p.body}</p>
                    </div>
                  </div>
                </RevealItem>
              ))}
            </RevealGroup>
          </div>

          <Reveal delay={0.1}>
            <BrainDiagram />
          </Reveal>
        </div>
      </div>
    </section>
  )
}
