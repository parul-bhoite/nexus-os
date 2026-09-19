import Link from 'next/link'
import type { ReactNode } from 'react'

/**
 * The shell both legal pages use, and the reason they look unusual.
 *
 * **These pages describe behaviour, not obligations.** Every factual claim on
 * them was read out of the code — retention windows from the migrations and the
 * expiry job, the session lifetime from `config.py`, what leaves the system from
 * the provider modules. None of it was drafted from a template.
 *
 * That is deliberate and it is the only honest version available right now.
 * Generating plausible policy prose would produce a document a customer could
 * rely on and nobody had checked, about a company whose legal identity, place of
 * establishment and PDPL position are not settled — the exact shape of invention
 * this product refuses everywhere else. `Pending` is how the missing half says
 * so, in place, rather than by omission.
 *
 * **Consequence, stated once here so neither page has to hedge every sentence:**
 * these are not yet a privacy policy or a contract, they are a disclosure of
 * what the software does, and they say so at the top.
 */

export function Pending({ what, needs }: { what: string; needs: string }) {
  return (
    <li className="flex flex-col gap-0.5 border-l-2 border-clay-300 py-1 pl-3">
      <span className="text-sm font-medium text-ink-800">{what}</span>
      <span className="text-sm leading-relaxed text-ink-500">{needs}</span>
    </li>
  )
}

export function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="mt-10">
      <h2 className="font-display text-xl font-semibold text-ink-900">{title}</h2>
      <div className="mt-3 flex flex-col gap-3 text-[0.95rem] leading-relaxed text-ink-600">
        {children}
      </div>
    </section>
  )
}

/** A claim with the file that makes it true. The point is that a reader — or a
 *  lawyer — can check any line here against the source rather than trust it. */
export function Fact({ children, source }: { children: ReactNode; source: string }) {
  return (
    <li className="flex flex-col gap-0.5 py-1.5">
      <span>{children}</span>
      <code className="font-mono text-2xs text-ink-400">{source}</code>
    </li>
  )
}

export function LegalPage({
  kicker,
  title,
  lede,
  missing,
  children,
}: {
  kicker: string
  title: string
  lede: string
  /** What a lawyer still has to supply. Rendered prominently rather than
   *  omitted: a reader must not mistake this for a finished document. */
  missing: ReactNode
  children: ReactNode
}) {
  return (
    <main id="main" tabIndex={-1} className="mx-auto max-w-2xl px-6 py-16">
      <p className="font-mono text-2xs uppercase tracking-[0.14em] text-clay-600">{kicker}</p>
      <h1 className="mt-3 font-display text-3xl font-bold text-ink-900 sm:text-4xl">{title}</h1>
      <p className="mt-3 text-[0.95rem] leading-relaxed text-ink-600">{lede}</p>

      <div className="mt-8 rounded-2xl border border-gold-300 bg-gold-100 p-5">
        <h2 className="font-display text-base font-semibold text-ink-900">
          This is not a finished legal document
        </h2>
        <p className="mt-2 text-sm leading-relaxed text-ink-700">
          What follows is an accurate description of what the software does, checked against the
          code. It has not been reviewed by a lawyer, and the parts below are genuinely undecided —
          they are listed rather than filled in with something plausible.
        </p>
        <ul className="mt-3 flex flex-col gap-2">{missing}</ul>
        <p className="mt-3 text-sm leading-relaxed text-ink-700">
          Until those are settled, treat this page as a factual disclosure and not as terms you can
          rely on.
        </p>
      </div>

      {children}

      <footer className="mt-12 border-t border-bone-300 pt-5 text-sm text-ink-400">
        <Link href="/" className="underline decoration-bone-400 underline-offset-2">
          Back to NEXUS OS
        </Link>
        <span className="mx-2">·</span>
        <Link href="/privacy" className="underline decoration-bone-400 underline-offset-2">
          Privacy
        </Link>
        <span className="mx-2">·</span>
        <Link href="/terms" className="underline decoration-bone-400 underline-offset-2">
          Terms
        </Link>
      </footer>
    </main>
  )
}
