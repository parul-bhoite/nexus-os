'use client'

import { motion } from 'framer-motion'
import { useMotionSafe } from '@/lib/motion'
import type { StepId } from '@/components/onboarding/OnboardingStepper'

/**
 * The left-hand illustration for each onboarding step (ADR 0074).
 *
 * One small, looping, monochrome-plus-amber scene per step — a building for the
 * company beat, department tiles for areas, chat bubbles for the interview, a
 * document stack, a tool hub, a knowledge graph for the Brain. They are
 * decoration (`aria-hidden` on the panel that holds them), so every loop is
 * gated by `useMotionSafe`: under `prefers-reduced-motion` each scene renders in
 * a calm resting state with nothing moving.
 *
 * `active` (the shell passes it when the agent is thinking) quickens the two
 * scenes where waiting actually happens — the interview and the Brain build —
 * so the art reads as "working" rather than idle during a model call.
 */

const CAPTION: Record<StepId, { title: string; body: string }> = {
  company: { title: 'Your company', body: 'The starting point everything else is built around.' },
  areas: { title: 'Your areas', body: 'The parts of the business NEXUS pays attention to.' },
  chat: { title: 'A short conversation', body: 'NEXUS learns what it could not read for itself.' },
  documents: { title: 'Your documents', body: 'Real figures and wording, straight from your files.' },
  tools: { title: 'Your stack', body: 'Where your numbers already live.' },
  brain: { title: 'Your Company Brain', body: 'Everything above, assembled with its source.' },
  payment: { title: 'Your plan', body: 'Priced from the areas and tools you chose.' },
}

export function StepArt({ step, active = false }: { step: StepId; active?: boolean }) {
  const caption = CAPTION[step]
  return (
    <div className="flex w-full max-w-[20rem] flex-col items-center">
      <div className="aspect-square w-full">
        <Scene step={step} active={active} />
      </div>
      <p className="mt-8 font-display text-lg text-ink-900">{caption.title}</p>
      <p className="mt-1 text-center text-sm leading-relaxed text-ink-400">{caption.body}</p>
    </div>
  )
}

function Scene({ step, active }: { step: StepId; active: boolean }) {
  switch (step) {
    case 'company':
      return <CompanyArt />
    case 'areas':
      return <AreasArt />
    case 'chat':
      return <QuestionsArt active={active} />
    case 'documents':
      return <DocumentsArt />
    case 'tools':
      return <ToolsArt />
    case 'brain':
      return <BrainArt active={active} />
    case 'payment':
      return <PaymentArt />
  }
}

const svgProps = {
  viewBox: '0 0 200 200',
  fill: 'none',
  className: 'h-full w-full',
  'aria-hidden': true,
} as const

/* ── Company — windows light up, the rooftop mark pulses ──────────────── */

const WINDOWS: [number, number][] = [
  [74, 66],
  [108, 66],
  [74, 90],
  [108, 90],
  [74, 114],
  [108, 114],
]

function CompanyArt() {
  const safe = useMotionSafe()
  return (
    <svg {...svgProps}>
      <line x1="28" y1="170" x2="172" y2="170" className="stroke-bone-300" strokeWidth="2.5" strokeLinecap="round" />
      <rect x="62" y="52" width="76" height="118" rx="6" className="fill-bone-50 stroke-ink-800" strokeWidth="3" />
      <rect x="90" y="142" width="20" height="28" rx="3" className="fill-bone-200 stroke-ink-800" strokeWidth="2.5" />
      {WINDOWS.map(([x, y], i) => (
        <motion.rect
          key={i}
          x={x}
          y={y}
          width="20"
          height="14"
          rx="2"
          className="fill-gold-500"
          initial={{ opacity: 0.18 }}
          animate={safe ? { opacity: [0.18, 1, 0.18] } : { opacity: 0.6 }}
          transition={safe ? { duration: 2.6, repeat: Infinity, delay: i * 0.35, ease: 'easeInOut' } : undefined}
        />
      ))}
      <line x1="100" y1="52" x2="100" y2="40" className="stroke-ink-800" strokeWidth="3" strokeLinecap="round" />
      <motion.circle
        cx="100"
        cy="36"
        r="5"
        className="fill-gold-500"
        animate={safe ? { opacity: [0.7, 1, 0.7], r: [5, 6.5, 5] } : { opacity: 1 }}
        transition={safe ? { duration: 2, repeat: Infinity, ease: 'easeInOut' } : undefined}
      />
    </svg>
  )
}

/* ── Areas — department tiles breathing in sequence ──────────────────── */

const TILES: [number, number][] = [
  [34, 54],
  [84, 54],
  [134, 54],
  [34, 116],
  [84, 116],
  [134, 116],
]

function AreasArt() {
  const safe = useMotionSafe()
  return (
    <svg {...svgProps}>
      {TILES.map(([x, y], i) => {
        const gold = i === 4
        return (
          <motion.g
            key={i}
            initial={{ opacity: 0.6 }}
            animate={safe ? { scale: [0.94, 1, 0.94], opacity: [0.7, 1, 0.7] } : { scale: 1, opacity: 1 }}
            transition={safe ? { duration: 2.8, repeat: Infinity, delay: i * 0.22, ease: 'easeInOut' } : undefined}
            style={{ transformBox: 'fill-box', transformOrigin: 'center' }}
          >
            <rect
              x={x}
              y={y}
              width="48"
              height="44"
              rx="9"
              className={gold ? 'fill-gold-500 stroke-gold-500' : 'fill-white stroke-bone-300'}
              strokeWidth="2.5"
            />
            <circle cx={x + 24} cy={y + 22} r="7" className={gold ? 'fill-white' : 'fill-steel-200'} />
          </motion.g>
        )
      })}
    </svg>
  )
}

/* ── Questions — bubbles, and a typing bubble that quickens when thinking ─ */

function QuestionsArt({ active }: { active: boolean }) {
  const safe = useMotionSafe()
  return (
    <svg {...svgProps}>
      <motion.g initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={safe ? { duration: 0.5 } : { duration: 0 }}>
        <rect x="22" y="40" width="108" height="36" rx="13" className="fill-white stroke-bone-300" strokeWidth="2.5" />
        <line x1="38" y1="53" x2="108" y2="53" className="stroke-steel-200" strokeWidth="4" strokeLinecap="round" />
        <line x1="38" y1="64" x2="88" y2="64" className="stroke-steel-200" strokeWidth="4" strokeLinecap="round" />
      </motion.g>
      <motion.g initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={safe ? { duration: 0.5, delay: 0.2 } : { duration: 0 }}>
        <rect x="70" y="90" width="108" height="32" rx="13" className="fill-ink-900" />
        <line x1="86" y1="106" x2="154" y2="106" className="stroke-white/40" strokeWidth="4" strokeLinecap="round" />
      </motion.g>
      <rect x="22" y="136" width="78" height="36" rx="13" className="fill-white stroke-bone-300" strokeWidth="2.5" />
      {[0, 1, 2].map((d) => (
        <motion.circle
          key={d}
          cx={42 + d * 18}
          cy="154"
          r="5"
          className="fill-gold-500"
          animate={safe ? { y: [0, -5, 0], opacity: [0.5, 1, 0.5] } : { opacity: 0.8 }}
          transition={safe ? { duration: active ? 0.7 : 1.1, repeat: Infinity, delay: d * 0.16, ease: 'easeInOut' } : undefined}
        />
      ))}
    </svg>
  )
}

/* ── Documents — a stack whose top card drifts, read and checked ─────── */

function DocumentsArt() {
  const safe = useMotionSafe()
  return (
    <svg {...svgProps}>
      <rect x="70" y="56" width="78" height="104" rx="8" className="fill-bone-100 stroke-bone-300" strokeWidth="2.5" transform="rotate(7 109 108)" />
      <rect x="56" y="50" width="78" height="104" rx="8" className="fill-bone-50 stroke-bone-300" strokeWidth="2.5" transform="rotate(-5 95 102)" />
      <motion.g
        initial={{ y: 4 }}
        animate={safe ? { y: [4, -5, 4] } : { y: 0 }}
        transition={safe ? { duration: 3.2, repeat: Infinity, ease: 'easeInOut' } : undefined}
      >
        <rect x="52" y="48" width="78" height="104" rx="8" className="fill-white stroke-ink-800" strokeWidth="3" />
        {[0, 1, 2, 3].map((i) => (
          <line
            key={i}
            x1="64"
            y1={68 + i * 16}
            x2={i === 3 ? 102 : 118}
            y2={68 + i * 16}
            className="stroke-steel-200"
            strokeWidth="4"
            strokeLinecap="round"
          />
        ))}
        <circle cx="116" cy="138" r="12" className="fill-gold-500" />
        <path d="M110 138 l4 4 l8 -9" className="stroke-white" strokeWidth="2.5" fill="none" strokeLinecap="round" strokeLinejoin="round" />
      </motion.g>
    </svg>
  )
}

/* ── Tools — a hub with satellites, data flowing inward ──────────────── */

const SATELLITES: [number, number][] = [
  [100, 36],
  [158, 80],
  [138, 152],
  [62, 152],
  [42, 80],
]

function ToolsArt() {
  const safe = useMotionSafe()
  return (
    <svg {...svgProps}>
      {SATELLITES.map(([x, y], i) => (
        <motion.line
          key={`l${i}`}
          x1={x}
          y1={y}
          x2="100"
          y2="100"
          className="stroke-gold-500"
          strokeWidth="2.5"
          strokeLinecap="round"
          strokeDasharray="4 8"
          animate={safe ? { strokeDashoffset: [0, -24] } : undefined}
          transition={safe ? { duration: 1.3, repeat: Infinity, ease: 'linear', delay: i * 0.1 } : undefined}
        />
      ))}
      {SATELLITES.map(([x, y], i) => (
        <g key={`s${i}`}>
          <circle cx={x} cy={y} r="14" className="fill-white stroke-ink-800" strokeWidth="2.5" />
          <circle cx={x} cy={y} r="4" className="fill-steel-300" />
        </g>
      ))}
      <motion.circle
        cx="100"
        cy="100"
        r="20"
        className="fill-ink-900"
        animate={safe ? { r: [20, 22, 20] } : undefined}
        transition={safe ? { duration: 2, repeat: Infinity, ease: 'easeInOut' } : undefined}
      />
      <circle cx="100" cy="100" r="7" className="fill-gold-500" />
    </svg>
  )
}

/* ── Company Brain — a knowledge graph, edges pulsing, nodes breathing ── */

const NODES: [number, number][] = [
  [100, 58],
  [58, 90],
  [142, 92],
  [72, 142],
  [132, 144],
  [100, 108],
]
const EDGES: [number, number][] = [
  [0, 1],
  [0, 2],
  [1, 5],
  [2, 5],
  [1, 3],
  [2, 4],
  [3, 5],
  [4, 5],
  [0, 5],
]

function BrainArt({ active }: { active: boolean }) {
  const safe = useMotionSafe()
  return (
    <svg {...svgProps}>
      {EDGES.map(([a, b], i) => {
        const [x1, y1] = NODES[a]
        const [x2, y2] = NODES[b]
        return (
          <motion.line
            key={i}
            x1={x1}
            y1={y1}
            x2={x2}
            y2={y2}
            className="stroke-gold-500"
            strokeWidth="2"
            strokeLinecap="round"
            strokeDasharray="3 7"
            animate={safe ? { strokeDashoffset: [0, -20] } : undefined}
            transition={safe ? { duration: active ? 1 : 1.9, repeat: Infinity, ease: 'linear', delay: i * 0.08 } : undefined}
          />
        )
      })}
      {NODES.map(([x, y], i) => {
        const center = i === 5
        return (
          <motion.circle
            key={i}
            cx={x}
            cy={y}
            r={center ? 16 : 9}
            className={center ? 'fill-ink-900' : 'fill-white stroke-ink-800'}
            strokeWidth="2.5"
            animate={safe ? { opacity: [0.65, 1, 0.65] } : { opacity: 1 }}
            transition={safe ? { duration: 2.4, repeat: Infinity, delay: i * 0.2, ease: 'easeInOut' } : undefined}
          />
        )
      })}
      <circle cx="100" cy="108" r="5" className="fill-gold-500" />
    </svg>
  )
}

/* ── Payment — a card with a chip, and a "paid" badge that settles in ──── */

function PaymentArt() {
  const safe = useMotionSafe()
  return (
    <svg {...svgProps}>
      <rect x="36" y="64" width="128" height="84" rx="12" className="fill-white stroke-ink-800" strokeWidth="3" />
      {/* magnetic stripe */}
      <rect x="36" y="78" width="128" height="14" className="fill-ink-900" />
      {/* chip */}
      <rect x="52" y="104" width="22" height="16" rx="3" className="fill-gold-500" />
      {/* number lines */}
      <line x1="52" y1="132" x2="96" y2="132" className="stroke-steel-200" strokeWidth="4" strokeLinecap="round" />
      <line x1="104" y1="132" x2="134" y2="132" className="stroke-steel-200" strokeWidth="4" strokeLinecap="round" />
      {/* "paid" badge, settling in */}
      <motion.g
        initial={{ opacity: 0.8 }}
        animate={safe ? { scale: [0.9, 1, 0.9], opacity: [0.8, 1, 0.8] } : { scale: 1, opacity: 1 }}
        transition={safe ? { duration: 2.4, repeat: Infinity, ease: 'easeInOut' } : undefined}
        style={{ transformBox: 'fill-box', transformOrigin: 'center' }}
      >
        <circle cx="150" cy="60" r="18" className="fill-gold-500" />
        <path
          d="M142 60 l5 5 l11 -12"
          className="stroke-white"
          strokeWidth="3"
          fill="none"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </motion.g>
    </svg>
  )
}
