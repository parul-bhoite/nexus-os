import type { Metadata } from 'next'
import { ScanForm } from '@/components/scan/ScanForm'

export const metadata: Metadata = {
  title: 'Instant Gap Analysis',
  description: 'Three real gaps on your own website, in about 90 seconds. No login needed.',
}

export default function ScanPage() {
  return (
    <main id="main" tabIndex={-1} className="mx-auto flex min-h-screen max-w-2xl flex-col justify-center px-6 py-16">
      <div className="mb-8">
        <p className="font-mono text-2xs uppercase tracking-[0.14em] text-clay-600">
          Instant Gap Analysis
        </p>
        <h1 className="mt-3 font-display text-3xl font-bold text-ink-900 sm:text-4xl">
          What is your website not doing for you?
        </h1>
        <p className="mt-3 text-[0.95rem] text-ink-600">
          One field. No login. Three real gaps from your own site, computed from what we could
          actually read on it.
        </p>
      </div>
      <ScanForm />
    </main>
  )
}
