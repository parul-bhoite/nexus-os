import type { Config } from 'tailwindcss'

/**
 * The design tokens. This file and `app/globals.css` are the only two places a
 * raw value may appear — everything else composes these names.
 *
 * ## The palette is unchanged; the rules for using it are new
 *
 * The six source values still come from the cut-paper landscape reference, and
 * the scales around them are still tints and shades of those six. What the
 * 2026-09 pass changed is *discipline*, because the audit found the same three
 * failures everywhere:
 *
 * - **Gold had become decoration.** It is the only accent, and an accent that
 *   appears on every card cannot mark the one card that needs attention. It is
 *   now reserved for attention and for the one hero flourish.
 * - **Clay had become permanent.** Six tiles on the dashboard carried a clay
 *   sentence about unconfirmed data *at all times*. A warning that is always on
 *   is not a warning, so clay is now strictly exceptional state.
 * - **Three greys were doing one job.** `ink-400`, `slate-400` and `bone-400`
 *   all appeared as "muted text" at 11–14px and two of the three failed
 *   contrast. There is now one muted step per surface, and each passes.
 *
 * ## Contrast
 *
 * Every foreground step below is checked against the surface it is used on:
 * `ink-500` and darker pass 4.5:1 on white and on `bone-50`; `steel-600` and
 * `clay-600` pass on both. The values that failed the audit are recorded in the
 * comments beside their replacements so the mistake is not made twice.
 */

/** ── Motion ────────────────────────────────────────────────────────────────
 *  Mirrors `lib/motion.ts`. Duplicated deliberately: Tailwind needs literals
 *  at build time and framer-motion needs numbers at run time, and a single
 *  source would have to be one or the other. `motion.ts` is the canonical
 *  documentation of *why* each value is what it is.
 */
const duration = {
  instant: '80ms',
  micro: '140ms',
  base: '200ms',
  emphasis: '320ms',
  slow: '480ms',
}

const easing = {
  // Entrances. Fast start, long settle — the curve that reads as "arriving".
  out: 'cubic-bezier(0.16, 1, 0.3, 1)',
  // Exits. Slow start, fast finish — reads as "leaving" rather than "removed".
  in: 'cubic-bezier(0.4, 0, 1, 1)',
  // Moves between two on-screen positions.
  inOut: 'cubic-bezier(0.4, 0, 0.2, 1)',
}

const config: Config = {
  content: ['./app/**/*.{ts,tsx}', './components/**/*.{ts,tsx}', './lib/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        /* ── Monochrome system (ADR 0072) ──────────────────────────────────
         * The palette was navy/bone/gold "cut paper". It is now a cool-biased
         * neutral ladder with a single amber accent. The token *names* are
         * unchanged on purpose — redefining the values in place reskins every
         * component that composes these names, so the diff stays in this file
         * and the logo rather than spreading across the app. A later cleanup
         * may rename `gold`→`accent` and `clay`→`warning`; not in this change.
         *
         * Contrast is checked against the surface each step is used on: ink-500
         * and darker pass 4.5:1 on white and on bone-50; gold-700 and clay-600
         * pass for small text on white. The greys carry a faint cool cast so
         * they read as chosen rather than as a default mid-grey. */

        // The neutral ink ladder — text, borders and the true blacks. ink-950
        // is the primary action/ink; ink-800/700 are text; ink-200/100 borders.
        ink: {
          DEFAULT: '#0B0C0E',
          50: '#F4F5F7',
          100: '#E7E9EC',
          200: '#D4D8DD',
          300: '#B0B5BD',
          // Muted — large text and decoration only (3.0:1 on white).
          400: '#8A909A',
          // The muted-text floor that still passes on white (5.9:1) and on
          // bone-50 (5.6:1): secondary copy, meta, eyebrows, group labels.
          500: '#5E646E',
          600: '#434852',
          700: '#2E323A',
          800: '#1C1F25',
          900: '#121419',
          950: '#0B0C0E',
        },

        // Was the blue "chrome" tone (links, focus, UI). Now neutral grey, so
        // anything still reaching for steel renders monochrome. The focus ring
        // and links move to the amber accent in globals.css.
        steel: {
          DEFAULT: '#5E646E',
          100: '#E7E9EC',
          200: '#D4D8DD',
          300: '#B0B5BD',
          400: '#8A909A',
          500: '#5E646E',
          600: '#434852',
          700: '#2E323A',
        },

        // A second muted grey, kept distinct only so the two historical "muted"
        // call sites do not collapse onto one value mid-reskin.
        slate: {
          DEFAULT: '#7A808A',
          100: '#EDEEF1',
          200: '#D4D8DD',
          300: '#B0B5BD',
          400: '#8A909A',
          500: '#5E646E',
          600: '#434852',
        },

        // Surfaces. Was a warm bone wash; now cool light greys and white. These
        // are the backgrounds — cards are white, sunken fills are bone-50/100,
        // hairlines are bone-300.
        bone: {
          DEFAULT: '#E7E9EC',
          50: '#F7F8FA',
          100: '#F1F3F5',
          200: '#E7E9EC',
          300: '#D4D8DD',
          400: '#AEB4BD',
        },

        // The one accent — warm amber, the complement of the cool neutrals.
        // The single spark: active state, focus ring, key-metric highlight, the
        // logo arm. It never fills a button (black does), so 500 need not carry
        // white text; gold-700 is the step for amber *text* on white (5.0:1).
        gold: {
          DEFAULT: '#E2881F',
          50: '#FDF3E6',
          100: '#FBE8CE',
          200: '#F6D09B',
          300: '#EFB264',
          400: '#E89A3C',
          500: '#E2881F',
          600: '#C4710F',
          700: '#9A560A',
        },

        // Restrained semantic warning — genuine error state only, never
        // decoration. A muted brick red that holds its own on white (clay-600
        // passes AA for small text).
        clay: {
          DEFAULT: '#B14A38',
          100: '#F7E7E4',
          200: '#ECC9C3',
          300: '#DCA59B',
          400: '#C8705F',
          500: '#B14A38',
          600: '#8F3A2C',
        },
      },

      fontFamily: {
        // Display is now a grotesque (Bricolage), not a serif — the fallback is
        // a sans stack, not Georgia. See ADR 0072 and app/layout.tsx.
        display: ['var(--font-display)', 'system-ui', 'sans-serif'],
        sans: ['var(--font-sans)', 'system-ui', 'sans-serif'],
        mono: ['var(--font-mono)', 'ui-monospace', 'monospace'],
      },

      /**
       * One scale, seven steps, each with its line height and tracking bound to
       * it. The audit found the app using eleven sizes across two conventions
       * (`text-sm` beside `text-[0.95rem]`), and two different label styles —
       * 11px tracked-out mono on `/settings`, sentence-case sans on `/work`.
       * Naming the steps by role is what stops that: a label is `text-label`
       * everywhere, and there is nowhere to put a second opinion.
       */
      fontSize: {
        '2xs': ['0.6875rem', { lineHeight: '1rem' }],

        // Marketing only. The hero earns one size nothing else may use. Tracked
        // tight — Bricolage Grotesque is built to close up at display sizes
        // (ADR 0072), and the tight set is what makes the monochrome hero read
        // as designed rather than plain.
        display: ['clamp(2.5rem, 6.2vw, 4.75rem)', { lineHeight: '1.0', letterSpacing: '-0.04em' }],
        headline: ['clamp(1.875rem, 3.6vw, 3rem)', { lineHeight: '1.06', letterSpacing: '-0.032em' }],

        // Product. `page` is an h1, `section` an h2, `card` an h3 — and the gap
        // between page and section is now large enough to read as a hierarchy.
        // It was 34px against 30px, which is not a hierarchy, it is a wobble.
        page: ['clamp(1.75rem, 2.6vw, 2.25rem)', { lineHeight: '1.1', letterSpacing: '-0.028em' }],
        section: ['1.3125rem', { lineHeight: '1.25', letterSpacing: '-0.012em' }],
        card: ['1.0625rem', { lineHeight: '1.35', letterSpacing: '-0.006em' }],
        // Alias of `section`. Sixteen files already say `text-title`, and
        // pointing it here is what collapses the old 30px-vs-34px wobble
        // between a page title and a section title into a real step.
        title: ['1.3125rem', { lineHeight: '1.25', letterSpacing: '-0.012em' }],

        // A figure. Tabular by construction — see `.tnum` in globals.css — so a
        // column of numbers does not shift width digit by digit.
        figure: ['clamp(1.75rem, 2.6vw, 2.25rem)', { lineHeight: '1.05', letterSpacing: '-0.025em' }],
        'figure-sm': ['1.375rem', { lineHeight: '1.1', letterSpacing: '-0.018em' }],

        body: ['0.9375rem', { lineHeight: '1.6' }],
        meta: ['0.8125rem', { lineHeight: '1.5' }],
        label: ['0.8125rem', { lineHeight: '1.2', letterSpacing: '0' }],
      },

      /**
       * Radii, by what the thing is rather than by how round it looks.
       *
       * `card` was 1.75rem (28px) and `panel` 2.5rem (40px). At 28px a dense
       * data tile reads as a marketing card — the audit's "over-designed
       * dashboard" note — and the corner eats the first character of a table
       * cell. Data surfaces are now 14px, marketing surfaces 20px, and the
       * difference is the point: the same component library can be calm in the
       * product and generous on the landing page.
       */
      borderRadius: {
        // Softer than the cut-paper set (ADR 0072) — the monochrome surfaces
        // lean on hairline borders and generous rounding rather than colour.
        control: '0.75rem',
        data: '1rem',
        card: '1.125rem',
        panel: '1.5rem',
      },

      /**
       * Three elevations, not five.
       *
       * `e1` is a resting surface, `e2` is one the pointer is on or that has
       * been raised, `e3` is something floating over the page. The old set had
       * `paper`, `paper-lg`, `paper-xl`, `lift` and `inset`, which is five
       * answers to a question with three cases — so call sites picked by feel
       * and two cards at the same depth got different shadows.
       *
       * `paper*` and `lift` are kept as aliases of the new three so nothing
       * has to be renamed in one pass, but new code uses `e1`/`e2`/`e3`.
       */
      // Shadows are cast in near-black (11,12,14) rather than navy, and are soft
      // and diffuse — depth by blur, not by line (ADR 0072).
      boxShadow: {
        e1: '0 1px 2px rgba(11,12,14,0.04), 0 8px 24px -14px rgba(11,12,14,0.12)',
        e2: '0 2px 6px -2px rgba(11,12,14,0.06), 0 16px 32px -16px rgba(11,12,14,0.16)',
        e3: '0 2px 8px rgba(11,12,14,0.06), 0 32px 64px -24px rgba(11,12,14,0.24)',
        paper: '0 1px 2px rgba(11,12,14,0.04), 0 8px 24px -14px rgba(11,12,14,0.12)',
        'paper-lg': '0 2px 6px -2px rgba(11,12,14,0.06), 0 16px 32px -16px rgba(11,12,14,0.16)',
        'paper-xl': '0 2px 8px rgba(11,12,14,0.06), 0 32px 64px -24px rgba(11,12,14,0.24)',
        lift: '0 2px 6px -2px rgba(11,12,14,0.06), 0 16px 32px -16px rgba(11,12,14,0.16)',
        inset: 'inset 0 1px 0 rgba(255,255,255,0.75)',
        // The focus ring, as a shadow, for controls that cannot spare an outline.
        // White gap, then the amber accent.
        focus: '0 0 0 2px #FFFFFF, 0 0 0 4px #E2881F',
      },

      spacing: {
        section: 'clamp(4.5rem, 9vw, 8rem)',
        // The app's vertical rhythm: the gap between two sections of a page.
        stack: 'clamp(2rem, 4vw, 3rem)',
      },

      maxWidth: {
        shell: '78rem',
        // The product shell is wider than the marketing one. At 1440 the old
        // 78rem left 96px of dead margin either side of an app that was already
        // fighting for width in a three-column dashboard.
        app: '96rem',
        prose: '46rem',
        // A measure for explanatory text inside a card. 60ch, not the card.
        read: '34rem',
      },

      transitionDuration: duration,
      transitionTimingFunction: {
        ...easing,
        // Kept: `ease-out-expo` and `ease-paper` are used in ~40 call sites and
        // are the same curve as `out`.
        paper: easing.out,
        'out-expo': easing.out,
      },

      zIndex: {
        base: '0',
        raised: '10',
        sticky: '20',
        header: '30',
        drawer: '40',
        overlay: '50',
        toast: '60',
      },

      keyframes: {
        float: {
          '0%, 100%': { transform: 'translate3d(0,0,0)' },
          '50%': { transform: 'translate3d(0,-10px,0)' },
        },
        drift: {
          '0%, 100%': { transform: 'translate3d(0,0,0) rotate(0deg)' },
          '50%': { transform: 'translate3d(14px,-6px,0) rotate(1.2deg)' },
        },
        sway: {
          '0%, 100%': { transform: 'rotate(-1.5deg)' },
          '50%': { transform: 'rotate(1.5deg)' },
        },
        'spin-slow': { to: { transform: 'rotate(360deg)' } },
        marquee: { from: { transform: 'translateX(0)' }, to: { transform: 'translateX(-50%)' } },
        'dash-flow': { to: { strokeDashoffset: '-1000' } },
        'pulse-ring': {
          '0%': { transform: 'scale(0.82)', opacity: '0.7' },
          '70%': { transform: 'scale(1.35)', opacity: '0' },
          '100%': { transform: 'scale(1.35)', opacity: '0' },
        },
        'typing-dot': {
          '0%, 65%, 100%': { transform: 'translateY(0)', opacity: '0.3' },
          '30%': { transform: 'translateY(-3px)', opacity: '1' },
        },
        'section-in': {
          from: { opacity: '0', transform: 'translate3d(0,10px,0)' },
          to: { opacity: '1', transform: 'translate3d(0,0,0)' },
        },
        /**
         * The skeleton sweep. Opacity, not a moving highlight.
         *
         * A travelling gradient repaints a large area every frame and, on a
         * page with thirty placeholders, is the most expensive thing on screen
         * while the page is by definition already waiting on something. This
         * animates `opacity` only, which the compositor handles, and it is
         * slow and shallow enough to read as breathing rather than as a
         * loading bar with no denominator.
         */
        breathe: {
          '0%, 100%': { opacity: '1' },
          '50%': { opacity: '0.45' },
        },
        /** A live indicator. One dot, and only where something really updates. */
        'pulse-dot': {
          '0%, 100%': { opacity: '1', transform: 'scale(1)' },
          '50%': { opacity: '0.4', transform: 'scale(0.82)' },
        },
      },

      animation: {
        float: 'float 7s ease-in-out infinite',
        drift: 'drift 14s ease-in-out infinite',
        sway: 'sway 6s ease-in-out infinite',
        'spin-slow': 'spin-slow 40s linear infinite',
        marquee: 'marquee 46s linear infinite',
        'dash-flow': 'dash-flow 22s linear infinite',
        'pulse-ring': 'pulse-ring 3.4s cubic-bezier(0.4,0,0.6,1) infinite',
        'typing-dot': 'typing-dot 1.3s ease-in-out infinite',
        'section-in': `section-in ${duration.slow} ${easing.out} both`,
        breathe: `breathe 1.6s ${easing.inOut} infinite`,
        'pulse-dot': 'pulse-dot 2.4s cubic-bezier(0.4,0,0.6,1) infinite',
      },
    },
  },
  plugins: [],
}

export default config
