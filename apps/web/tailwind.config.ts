import type { Config } from 'tailwindcss'

/**
 * Palette is taken verbatim from the design reference (layered paper-cut
 * landscape). The six source values are the `DEFAULT` of each scale; the
 * surrounding steps are tints/shades derived from them for UI needs
 * (borders, hovers, muted text) so nothing off-brand creeps in.
 */
const config: Config = {
  content: ['./app/**/*.{ts,tsx}', './components/**/*.{ts,tsx}', './lib/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        ink: {
          DEFAULT: '#091F46',
          50: '#F2F5FA',
          100: '#E2E8F2',
          200: '#C2CEE2',
          300: '#93A8C7',
          400: '#5C769E',
          500: '#2F4C7B',
          600: '#193460',
          700: '#0F2851',
          800: '#091F46',
          900: '#061634',
          950: '#030C1E',
        },
        steel: {
          DEFAULT: '#37729C',
          100: '#E4EDF4',
          200: '#C3D8E7',
          300: '#93B8D1',
          400: '#5F94B8',
          500: '#37729C',
          600: '#2C5C80',
          700: '#224862',
        },
        slate: {
          DEFAULT: '#7699AE',
          100: '#EDF2F6',
          200: '#D6E1E9',
          300: '#B4C7D5',
          400: '#7699AE',
          500: '#5C8098',
          600: '#48657A',
        },
        bone: {
          DEFAULT: '#E9E4DE',
          50: '#FBFAF8',
          100: '#F5F2EF',
          200: '#E9E4DE',
          300: '#D8D0C7',
          400: '#BFB4A7',
        },
        gold: {
          DEFAULT: '#EFBF6A',
          100: '#FDF6E8',
          200: '#FAE9C7',
          300: '#F5D89B',
          400: '#EFBF6A',
          500: '#DFA542',
          600: '#B9822B',
        },
        clay: {
          DEFAULT: '#A55D35',
          100: '#F8EDE6',
          200: '#EED7C7',
          300: '#DCB098',
          400: '#C5825A',
          500: '#A55D35',
          600: '#84492A',
        },
      },
      fontFamily: {
        display: ['var(--font-display)', 'Georgia', 'serif'],
        sans: ['var(--font-sans)', 'system-ui', 'sans-serif'],
        mono: ['var(--font-mono)', 'ui-monospace', 'monospace'],
      },
      fontSize: {
        '2xs': ['0.6875rem', { lineHeight: '1rem' }],
        display: ['clamp(2.75rem, 7vw, 5.25rem)', { lineHeight: '0.98', letterSpacing: '-0.03em' }],
        headline: ['clamp(2rem, 4.2vw, 3.35rem)', { lineHeight: '1.06', letterSpacing: '-0.025em' }],
        title: ['clamp(1.4rem, 2.2vw, 1.9rem)', { lineHeight: '1.18', letterSpacing: '-0.015em' }],
      },
      borderRadius: {
        card: '1.75rem',
        panel: '2.5rem',
      },
      boxShadow: {
        // Soft, directional shadows — the "cut paper lifted off the page" look.
        paper: '0 1px 2px rgba(9,31,70,0.05), 0 8px 24px -12px rgba(9,31,70,0.18)',
        'paper-lg': '0 2px 4px rgba(9,31,70,0.05), 0 24px 56px -24px rgba(9,31,70,0.28)',
        'paper-xl': '0 4px 8px rgba(9,31,70,0.06), 0 48px 96px -40px rgba(9,31,70,0.34)',
        lift: '0 1px 2px rgba(9,31,70,0.06), 0 32px 64px -28px rgba(9,31,70,0.32)',
        inset: 'inset 0 1px 0 rgba(255,255,255,0.75)',
      },
      spacing: {
        section: 'clamp(5rem, 11vw, 9.5rem)',
      },
      maxWidth: {
        shell: '78rem',
        prose: '46rem',
      },
      transitionTimingFunction: {
        paper: 'cubic-bezier(0.22, 1, 0.36, 1)',
        'out-expo': 'cubic-bezier(0.16, 1, 0.3, 1)',
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
        'spin-slow': {
          to: { transform: 'rotate(360deg)' },
        },
        marquee: {
          from: { transform: 'translateX(0)' },
          to: { transform: 'translateX(-50%)' },
        },
        'dash-flow': {
          to: { strokeDashoffset: '-1000' },
        },
        'pulse-ring': {
          '0%': { transform: 'scale(0.82)', opacity: '0.7' },
          '70%': { transform: 'scale(1.35)', opacity: '0' },
          '100%': { transform: 'scale(1.35)', opacity: '0' },
        },
        shimmer: {
          '100%': { transform: 'translateX(100%)' },
        },
        // The agent is composing. Three dots, staggered by animation-delay at
        // the call site, so the bubble reads as someone typing rather than as a
        // progress bar with no denominator.
        'typing-dot': {
          '0%, 65%, 100%': { transform: 'translateY(0)', opacity: '0.3' },
          '30%': { transform: 'translateY(-3px)', opacity: '1' },
        },
        // A section arriving. Shorter and flatter than `rise`, because a whole
        // screen sliding as far as a single card does reads as a page reload.
        'section-in': {
          from: { opacity: '0', transform: 'translate3d(0,10px,0)' },
          to: { opacity: '1', transform: 'translate3d(0,0,0)' },
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
        'section-in': 'section-in 0.5s cubic-bezier(0.16,1,0.3,1) both',
      },
    },
  },
  plugins: [],
}

export default config
