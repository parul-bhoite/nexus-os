/**
 * A small, consistent icon set drawn on a 24-grid with a 1.6 stroke. Kept
 * in-house rather than pulled from a library so the weight matches the
 * illustration line work exactly.
 */

type IconProps = { className?: string }

const wrap = (children: React.ReactNode) =>
  function Icon({ className = 'h-5 w-5' }: IconProps) {
    return (
      <svg
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden="true"
        className={className}
      >
        {children}
      </svg>
    )
  }

export const IconTeam = wrap(
  <>
    <circle cx="9" cy="8" r="3.2" />
    <path d="M2.8 20a6.2 6.2 0 0 1 12.4 0" />
    <path d="M16.5 5.6a3.2 3.2 0 0 1 0 5.9M18 20a6.3 6.3 0 0 0-2.4-4.9" />
  </>,
)

export const IconStack = wrap(
  <>
    <path d="M12 3 3 7.5 12 12l9-4.5z" />
    <path d="M3 12.5 12 17l9-4.5" />
    <path d="M3 17.2 12 21.7l9-4.5" />
  </>,
)

export const IconAgency = wrap(
  <>
    <path d="M3 21V9l6-4 6 4v12" />
    <path d="M15 21V13h6v8" />
    <path d="M7 12h2M7 16h2M18 17h.01" />
  </>,
)

export const IconChat = wrap(
  <>
    <path d="M20 12a7.5 7.5 0 0 1-11 6.6L4 20l1.4-4.4A7.5 7.5 0 1 1 20 12z" />
    <path d="M9 11h6M9 14.5h3.5" />
  </>,
)

export const IconNothing = wrap(
  <>
    <circle cx="12" cy="12" r="8.5" />
    <path d="M6 18 18 6" />
  </>,
)

export const IconCheck = wrap(<path d="m4.5 12.5 4.8 4.8L19.5 7" />)

export const IconEye = wrap(
  <>
    <path d="M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12z" />
    <circle cx="12" cy="12" r="3" />
  </>,
)

export const IconEyeOff = wrap(
  <>
    <path d="M9.9 5.1A9.6 9.6 0 0 1 12 5.5c6 0 9.5 6.5 9.5 6.5a16.2 16.2 0 0 1-2.9 3.5M6.2 6.7A15.6 15.6 0 0 0 2.5 12S6 18.5 12 18.5a9.1 9.1 0 0 0 4-.9" />
    <path d="M9.9 9.9a3 3 0 0 0 4.2 4.2" />
    <path d="M3 3l18 18" />
  </>,
)

export const IconMinus = wrap(<path d="M6 12h12" />)

export const IconPlus = wrap(<path d="M12 6v12M6 12h12" />)

export const IconSparkle = wrap(
  <>
    <path d="M12 3.5 13.9 9 19.5 11l-5.6 2L12 18.5 10.1 13 4.5 11 10.1 9z" />
    <path d="M18.5 4v3M20 5.5h-3" />
  </>,
)

export const IconShield = wrap(
  <>
    <path d="M12 3 4.8 6v6c0 4.4 3 8.1 7.2 9.2 4.2-1.1 7.2-4.8 7.2-9.2V6z" />
    <path d="m9 12 2.2 2.2L15.4 10" />
  </>,
)

export const IconGlobe = wrap(
  <>
    <circle cx="12" cy="12" r="8.5" />
    <path d="M3.5 12h17M12 3.5c2.2 2.4 3.4 5.4 3.4 8.5S14.2 18.1 12 20.5c-2.2-2.4-3.4-5.4-3.4-8.5S9.8 5.9 12 3.5z" />
  </>,
)

export const IconDoc = wrap(
  <>
    <path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z" />
    <path d="M14 3v5h5M9 13h6M9 16.5h4" />
  </>,
)

export const IconChart = wrap(
  <>
    <path d="M4 20V4M4 20h16" />
    <path d="M8 16v-4M12.5 16V8M17 16v-6" />
  </>,
)

export const IconTarget = wrap(
  <>
    <circle cx="12" cy="12" r="8.5" />
    <circle cx="12" cy="12" r="4.5" />
    <circle cx="12" cy="12" r="1" fill="currentColor" />
  </>,
)

export const problemIcons = {
  team: IconTeam,
  stack: IconStack,
  agency: IconAgency,
  chat: IconChat,
  nothing: IconNothing,
} as const
