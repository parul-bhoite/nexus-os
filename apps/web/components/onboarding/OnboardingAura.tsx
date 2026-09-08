'use client'

/**
 * The motion on the onboarding screen, in two pieces.
 *
 * It started as one large blurred disc fixed behind the transcript, with a
 * rotating dashed ring around it. Two things were wrong with that and both are
 * visible in a screenshot: at 42rem it was a 672px circle centred on the
 * viewport, so on the boot screen — which has nothing else on it — the entire
 * page was one soft blob; and a dashed ring slowly rotating behind body text
 * reads as a loading spinner that forgot to stop, which is decoration drawing
 * attention to itself rather than to the conversation.
 *
 * So: a **wash** with no discernible edge, and a **mark** small enough to be
 * looked at deliberately. The wash is atmosphere and says nothing. The mark
 * carries the state, at a size where its detail is legible instead of blurred
 * into a gradient.
 *
 * Both are `aria-hidden`. Every state either shows is also written in words
 * elsewhere on the screen — `globals.css` collapses animations to one iteration
 * under `prefers-reduced-motion`, and neither of these may be the only signal.
 */

export type AuraState =
  /** The read, and every model call after it. */
  | 'thinking'
  /** The microphone is open. A distinct colour, because it is a distinct risk. */
  | 'listening'
  /** Waiting on the person. */
  | 'idle'
  /** The Brain is live. */
  | 'ready'

const TONE: Record<AuraState, { core: string; ring: string; wash: string }> = {
  // steel — what the product uses everywhere for "read from a source".
  thinking: { core: '#37729C', ring: '#5F94B8', wash: 'rgba(95,148,184,0.20)' },
  // clay. A microphone that looks like everything else is one somebody forgets
  // is open.
  listening: { core: '#A55D35', ring: '#C5825A', wash: 'rgba(197,130,90,0.20)' },
  idle: { core: '#7699AE', ring: '#B4C7D5', wash: 'rgba(118,153,174,0.13)' },
  // gold, used once, for the only moment in the journey that is an arrival.
  ready: { core: '#DFA542', ring: '#EFBF6A', wash: 'rgba(239,191,106,0.20)' },
}

/**
 * Atmosphere. A gradient bleeding down from above the fold.
 *
 * Deliberately shapeless — it reaches `transparent` before any edge could be
 * made out, which is the whole difference from the disc it replaces. Nothing
 * here animates except the colour, which crossfades over a second when the
 * state changes; a background that moves competes with the text on top of it.
 */
export function OnboardingAura({ state }: { state: AuraState }) {
  return (
    <div
      aria-hidden
      className="pointer-events-none fixed inset-0 -z-10 transition-[background] duration-1000"
      style={{
        background: `radial-gradient(58rem 30rem at 50% -10rem, ${TONE[state].wash}, transparent 72%)`,
      }}
    />
  )
}

/**
 * The state, as one small mark.
 *
 * Concentric rather than blurred: at this size the two rings and the core are
 * distinguishable, so "waiting on a model" and "waiting on you" differ in a way
 * you can actually see rather than in an opacity nobody notices. The outer ring
 * only spins while something is in flight — motion means work here, so a mark
 * that always moved would mean nothing.
 */
export function PresenceMark({
  state,
  size = 22,
}: {
  state: AuraState
  size?: number
}) {
  const tone = TONE[state]
  const active = state === 'thinking' || state === 'listening'

  return (
    <svg
      aria-hidden
      viewBox="0 0 32 32"
      style={{ width: size, height: size }}
      className="shrink-0 overflow-visible"
    >
      {/* Dashed, and only turning while there is work. Six dashes rather than a
          fine dotted line: at 22px a fine one aliases into a grey smudge. */}
      <circle
        cx="16"
        cy="16"
        r="14"
        fill="none"
        stroke={tone.ring}
        strokeOpacity={active ? 0.85 : 0.4}
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeDasharray="5 6.3"
        className="animate-spin-slow"
        style={{
          transformOrigin: 'center',
          animationDuration: active ? '3.2s' : '0s',
          animationDirection: state === 'listening' ? 'reverse' : 'normal',
        }}
      />
      {/* The halo pulse is the "something is happening" signal, and it is paused
          rather than hidden when nothing is: a mark that vanished between turns
          would read as the agent having gone away. */}
      <circle
        cx="16"
        cy="16"
        r="9"
        fill="none"
        stroke={tone.ring}
        strokeOpacity="0.5"
        strokeWidth="1.5"
        className="animate-pulse-ring"
        style={{
          transformOrigin: 'center',
          animationPlayState: active ? 'running' : 'paused',
        }}
      />
      <circle cx="16" cy="16" r="5.5" fill={tone.core} fillOpacity={active ? 1 : 0.75} />
    </svg>
  )
}
