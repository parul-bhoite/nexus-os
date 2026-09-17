/**
 * Wordmark. The glyph is three stacked paper layers forming a peak — the same
 * cut-paper language as the hero illustration, and a nod to "one brain, many
 * layers of context".
 *
 * The hex values live here rather than in a token file because they are the
 * mark's own ink and are passed as SVG `fill` attributes, which Tailwind cannot
 * reach. `muted` was `#5C8098` and measured 4.20:1 against white at 21px —
 * under AA, on the product's own name. It is `steel-600` now, which clears it.
 */
export function Logo({
  className = '',
  tone = 'light',
}: {
  className?: string
  tone?: 'light' | 'dark'
}) {
  const ink = tone === 'dark' ? '#FBFAF8' : '#091F46'
  const muted = tone === 'dark' ? '#7699AE' : '#2C5C80'

  return (
    <span className={`inline-flex items-center gap-2.5 ${className}`}>
      <svg viewBox="0 0 32 32" className="h-7 w-7 shrink-0" aria-hidden="true">
        <path d="M16 4 30 15l-5 3.9L16 11.8 7 18.9 2 15z" fill={ink} />
        <path d="M16 15.6l9-7 5 3.9-14 11L2 12.5l5-3.9z" fill="#37729C" opacity="0.9" />
        <path d="M16 22.4l9-7 5 3.9-14 11L2 19.3l5-3.9z" fill="#EFBF6A" />
      </svg>
      <span
        className="font-display text-[1.32rem] font-semibold tracking-tight"
        style={{ color: ink }}
      >
        NEXUS
        <span style={{ color: muted }} className="ml-1 font-normal">
          OS
        </span>
      </span>
    </span>
  )
}
