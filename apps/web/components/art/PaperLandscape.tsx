'use client'

/**
 * The signature illustration: a layered paper-cut landscape, adapted from the
 * design reference into a light-theme arch vignette.
 *
 * Every mass is a separate <g> at a known depth so the parallax can move them
 * independently — that separation is what reads as "stacked paper" rather than
 * a flat picture. Depths run 0 (furthest) to 1 (nearest).
 */

type Props = {
  parallax?: { x: number; y: number }
  className?: string
}

const DEPTH = {
  sky: 0.06,
  sun: 0.12,
  farRange: 0.2,
  cloudsFar: 0.3,
  midRange: 0.42,
  cloudsNear: 0.55,
  hills: 0.62,
  village: 0.72,
  water: 0.8,
  boats: 0.94,
  foreground: 1,
} as const

function shift(parallax: { x: number; y: number }, depth: number, strength = 26) {
  return {
    transform: `translate(${(-parallax.x * depth * strength).toFixed(2)}, ${(
      -parallax.y *
      depth *
      (strength * 0.55)
    ).toFixed(2)})`,
  }
}

function Cloud({
  x,
  y,
  scale = 1,
  opacity = 1,
  fill = 'var(--c-white)',
}: {
  x: number
  y: number
  scale?: number
  opacity?: number
  fill?: string
}) {
  return (
    <g transform={`translate(${x} ${y}) scale(${scale})`} opacity={opacity}>
      <path
        d="M0 16c0-7 6-13 13-13 3 0 6 1 8 3 3-6 9-10 16-10 9 0 17 6 19 15 6 1 11 6 11 13 0 7-6 13-14 13H13C6 37 0 31 0 24z"
        fill={fill}
      />
      <path
        d="M13 30h54c1.6 0 3-.5 4.2-1.3-1 4-4.8 7-9.2 7H13c-3.4 0-6.4-1.8-8-4.5 2.2 1.8 5 2.8 8 2.8z"
        fill="#000"
        opacity="0.06"
      />
    </g>
  )
}

function Boat({
  x,
  y,
  scale = 1,
  hull = 'var(--c-grey-600)',
  sail = 'var(--c-surface-3)',
  className = '',
}: {
  x: number
  y: number
  scale?: number
  hull?: string
  sail?: string
  className?: string
}) {
  return (
    <g transform={`translate(${x} ${y}) scale(${scale})`} className={className}>
      <g className="origin-bottom">
        <path d="M20 4v30" stroke="var(--c-grey-700)" strokeWidth="2" strokeLinecap="round" />
        <path d="M21 6c9 6 13 12 14 20H21z" fill={sail} />
        <path d="M19 10c-7 5-10 10-11 16h11z" fill={sail} opacity="0.82" />
      </g>
      <path d="M2 34h40l-6 10c-1 1.6-2.7 2.5-4.6 2.5H12.6c-1.9 0-3.6-.9-4.6-2.5z" fill={hull} />
      <path d="M2 34h40l-1.6 2.6H3.6z" fill="#000" opacity="0.12" />
    </g>
  )
}

/** The concentric arcs that give the reference water its quilled-paper look. */
function Swirl({
  x,
  y,
  rings = 4,
  radius = 10,
  stroke = 'var(--c-white)',
  opacity = 0.5,
}: {
  x: number
  y: number
  rings?: number
  radius?: number
  stroke?: string
  opacity?: number
}) {
  return (
    <g transform={`translate(${x} ${y})`} opacity={opacity} fill="none" stroke={stroke}>
      {Array.from({ length: rings }).map((_, i) => (
        <path
          key={i}
          d={`M${-radius - i * 5} 0a${radius + i * 5} ${(radius + i * 5) * 0.55} 0 0 1 ${
            (radius + i * 5) * 2
          } 0`}
          strokeWidth="1.4"
          strokeLinecap="round"
        />
      ))}
    </g>
  )
}

export function PaperLandscape({ parallax = { x: 0, y: 0 }, className = '' }: Props) {
  return (
    <svg
      viewBox="0 0 720 760"
      className={className}
      role="img"
      aria-label="Illustration: a layered paper landscape of mountains, sea and small boats, representing a business finding its direction."
    >
      <defs>
        <clipPath id="arch">
          {/* Arch vignette — full radius on top, soft radius at the base. */}
          <path d="M40 360C40 183 183 40 360 40s320 143 320 320v297c0 34-27 61-61 61H101c-34 0-61-27-61-61z" />
        </clipPath>

        <linearGradient id="sky" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="var(--c-surface-2)" />
          <stop offset="55%" stopColor="var(--c-surface-3)" />
          <stop offset="100%" stopColor="var(--c-surface-3)" />
        </linearGradient>

        <linearGradient id="seaFar" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="var(--c-grey-300)" />
          <stop offset="100%" stopColor="var(--c-grey-400)" />
        </linearGradient>

        <linearGradient id="seaNear" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="var(--c-grey-600)" />
          <stop offset="100%" stopColor="var(--c-ink-800)" />
        </linearGradient>

        <radialGradient id="sunGlow" cx="0.5" cy="0.5" r="0.5">
          <stop offset="0%" stopColor="var(--accent)" stopOpacity="0.55" />
          <stop offset="100%" stopColor="var(--accent)" stopOpacity="0" />
        </radialGradient>

        <filter id="paperLift" x="-20%" y="-20%" width="140%" height="140%">
          <feDropShadow dx="0" dy="4" stdDeviation="6" floodColor="var(--c-ink)" floodOpacity="0.18" />
        </filter>

        <filter id="paperLiftSoft" x="-20%" y="-20%" width="140%" height="140%">
          <feDropShadow dx="0" dy="3" stdDeviation="4" floodColor="var(--c-ink)" floodOpacity="0.12" />
        </filter>
      </defs>

      <g clipPath="url(#arch)">
        {/* ── Sky ─────────────────────────────────────────────── */}
        <g {...shift(parallax, DEPTH.sky)}>
          <rect x="0" y="0" width="720" height="760" fill="url(#sky)" />
        </g>

        {/* ── Sun and its slow ring ───────────────────────────── */}
        <g {...shift(parallax, DEPTH.sun)}>
          <circle cx="360" cy="196" r="150" fill="url(#sunGlow)" />
          <g className="origin-center motion-safe:animate-spin-slow" style={{ transformOrigin: '360px 196px' }}>
            <circle
              cx="360"
              cy="196"
              r="88"
              fill="none"
              stroke="var(--accent-strong)"
              strokeWidth="1.5"
              strokeDasharray="4 10"
              opacity="0.75"
            />
          </g>
          <circle cx="360" cy="196" r="62" fill="var(--accent)" filter="url(#paperLiftSoft)" />
          <path d="M330 152a62 62 0 0 1 52 100 62 62 0 1 0-52-100z" fill="var(--c-white)" opacity="0.22" />
        </g>

        {/* ── Far range ───────────────────────────────────────── */}
        <g {...shift(parallax, DEPTH.farRange)} opacity="0.75">
          <path d="M-20 380 120 246l86 74 74-58 92 86 96-70 132 102v106H-20z" fill="var(--c-grey-200)" />
        </g>

        {/* ── Far clouds ──────────────────────────────────────── */}
        <g {...shift(parallax, DEPTH.cloudsFar)} className="motion-safe:animate-drift">
          <Cloud x={64} y={196} scale={1.05} opacity={0.9} fill="var(--c-surface-2)" />
          <Cloud x={508} y={150} scale={0.85} opacity={0.85} fill="var(--c-surface-2)" />
        </g>

        {/* ── Mid range with snow caps ────────────────────────── */}
        <g {...shift(parallax, DEPTH.midRange)} filter="url(#paperLiftSoft)">
          <path d="M356 452 500 214l166 238z" fill="var(--c-grey-500)" />
          <path d="M500 214l50 72-24 10-20-16-22 20-18-14z" fill="var(--c-surface-2)" />
          <path d="M500 214 666 452h-58L500 260z" fill="#000" opacity="0.08" />

          <path d="M-20 452 130 268l144 184z" fill="var(--c-grey-300)" />
          <path d="M130 268l34 42-18 8-14-10-14 12-12-10z" fill="var(--c-surface)" />
        </g>

        {/* ── Near clouds ─────────────────────────────────────── */}
        <g
          {...shift(parallax, DEPTH.cloudsNear)}
          className="motion-safe:animate-float"
          filter="url(#paperLiftSoft)"
        >
          <Cloud x={196} y={148} scale={1.25} fill="var(--c-white)" />
          <Cloud x={430} y={222} scale={0.72} opacity={0.95} fill="var(--c-white)" />
        </g>

        {/* ── Rolling hills ───────────────────────────────────── */}
        <g {...shift(parallax, DEPTH.hills)} filter="url(#paperLift)">
          <path d="M-20 452c120-46 208-4 300 20s180 28 440-22v112H-20z" fill="var(--c-grey-400)" />
          <path d="M-20 496c140-40 232 6 322 26s186 16 418-30v100H-20z" fill="var(--c-grey-600)" />
        </g>

        {/* ── Village and trees ───────────────────────────────── */}
        <g {...shift(parallax, DEPTH.village)}>
          {/* Right-hand cluster of roofs */}
          <g filter="url(#paperLiftSoft)">
            <path d="M566 486l30-22 30 22v34h-60z" fill="var(--c-grey-600)" />
            <rect x="576" y="502" width="40" height="20" fill="var(--c-grey-400)" />
            <path d="M622 500l24-18 24 18v22h-48z" fill="var(--c-grey-700)" />
            <rect x="630" y="512" width="32" height="12" fill="var(--c-grey-600)" />
          </g>
          {/* Left-hand pagoda, echoing the reference silhouette */}
          <g filter="url(#paperLiftSoft)">
            <path d="M96 494l22-26 22 26z" fill="var(--c-grey-600)" />
            <path d="M104 512l14-18 14 18z" fill="var(--c-grey-400)" />
            <rect x="112" y="510" width="12" height="22" fill="var(--c-grey-700)" />
          </g>
          {/* Trees */}
          {[
            { x: 168, y: 512, s: 1 },
            { x: 196, y: 522, s: 0.8 },
            { x: 528, y: 516, s: 0.9 },
            { x: 496, y: 524, s: 0.72 },
          ].map((t, i) => (
            <g key={i} transform={`translate(${t.x} ${t.y}) scale(${t.s})`}>
              <rect x="-2" y="8" width="4" height="14" fill="var(--c-grey-700)" />
              <circle cx="0" cy="2" r="12" fill="var(--c-grey-700)" />
              <circle cx="-5" cy="-4" r="8" fill="var(--c-grey-600)" />
            </g>
          ))}
        </g>

        {/* ── Sea ─────────────────────────────────────────────── */}
        <g {...shift(parallax, DEPTH.water)}>
          <path d="M-20 556c150-34 250 8 340 22s220 10 400-30v232H-20z" fill="url(#seaFar)" filter="url(#paperLift)" />
          <path d="M-20 628c160-30 268 12 356 24s210 4 384-32v160H-20z" fill="url(#seaNear)" filter="url(#paperLift)" />

          <g>
            <Swirl x={92} y={624} rings={4} radius={12} opacity={0.42} />
            <Swirl x={252} y={664} rings={3} radius={9} opacity={0.32} />
            <Swirl x={556} y={614} rings={4} radius={11} opacity={0.36} />
            <Swirl x={648} y={676} rings={3} radius={8} opacity={0.28} />
            <Swirl x={392} y={700} rings={5} radius={13} opacity={0.3} />
          </g>
        </g>

        {/* ── Boats ───────────────────────────────────────────── */}
        <g {...shift(parallax, DEPTH.boats)}>
          <g className="motion-safe:animate-sway" style={{ transformOrigin: '300px 690px' }}>
            <Boat x={268} y={640} scale={1.15} />
          </g>
          <g
            className="motion-safe:animate-sway"
            style={{ transformOrigin: '452px 706px', animationDelay: '-2.4s' }}
          >
            <Boat x={430} y={668} scale={0.82} hull="var(--c-grey-400)" sail="var(--c-surface)" />
          </g>
        </g>

        {/* ── Birds ───────────────────────────────────────────── */}
        <g
          {...shift(parallax, DEPTH.foreground)}
          className="motion-safe:animate-float"
          fill="none"
          stroke="var(--c-surface)"
          strokeWidth="2.5"
          strokeLinecap="round"
          opacity="0.9"
        >
          <path d="M104 322c10-9 18-9 26 0m0 0c8-9 16-9 26 0" />
          <path d="M596 366c7-6 13-6 19 0m0 0c6-6 12-6 18 0" opacity="0.7" />
        </g>
      </g>

      {/* Arch edge — the cut line of the topmost sheet of paper. */}
      <path
        d="M40 360C40 183 183 40 360 40s320 143 320 320v297c0 34-27 61-61 61H101c-34 0-61-27-61-61z"
        fill="none"
        stroke="var(--c-line)"
        strokeWidth="2"
      />
    </svg>
  )
}
