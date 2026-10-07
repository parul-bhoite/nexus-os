/**
 * The NEXUS mark and wordmark (ADR 0072).
 *
 * The glyph is an X built from two strokes; one arm carries the accent. It
 * replaces the three-layer cut-paper peak. The wordmark is now "NEXUS" — the
 * "OS" suffix is dropped to match the new mark.
 *
 * No hex lives here. The two ink strokes are `currentColor`, so the mark takes
 * its colour from the surrounding text colour (set by `tone`), and the accent
 * arm is `var(--accent)` — the amber token, defined in globals.css. This keeps
 * the single source of colour truth in the token layer rather than in SVG
 * attributes Tailwind cannot reach.
 */
export function Logo({
  className = '',
  tone = 'light',
  showWordmark = true,
}: {
  className?: string
  tone?: 'light' | 'dark'
  showWordmark?: boolean
}) {
  // `currentColor` resolves to this; on a dark surface the ink goes light.
  const inkClass = tone === 'dark' ? 'text-bone-50' : 'text-ink-950'

  return (
    <span className={`inline-flex items-center gap-2.5 ${inkClass} ${className}`}>
      <svg
        viewBox="0 0 100 100"
        className="h-7 w-7 shrink-0"
        aria-hidden="true"
        fill="none"
      >
        {/* The full "\" diagonal, ink */}
        <line
          x1="26" y1="26" x2="74" y2="74"
          stroke="currentColor" strokeWidth="13" strokeLinecap="round"
        />
        {/* The lower-left half of the "/" diagonal, ink */}
        <line
          x1="26" y1="74" x2="50" y2="50"
          stroke="currentColor" strokeWidth="13" strokeLinecap="round"
        />
        {/* The upper-right arm, the accent spark */}
        <line
          x1="50" y1="50" x2="74" y2="26"
          stroke="var(--accent)" strokeWidth="13" strokeLinecap="round"
        />
      </svg>
      {showWordmark && (
        <span className="font-display text-[1.32rem] font-extrabold tracking-tight">
          NEXUS
        </span>
      )}
    </span>
  )
}
