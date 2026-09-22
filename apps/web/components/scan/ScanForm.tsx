'use client'

import { useState } from 'react'
import { Button, ArrowRight } from '@/components/ui/Button'
import { ScanError, ScanResult, deleteScan, startScan } from '@/lib/scan-client'

type State =
  | { status: 'idle' }
  | { status: 'submitting' }
  | { status: 'result'; result: ScanResult }
  | { status: 'refused'; message: string }
  | { status: 'limited'; message: string; retryAfterSeconds: number | null }
  | { status: 'deleted' }

/** "in about 20 minutes" — the same shape `app/routes/onboarding.py`'s
 * `_humanise_wait` gives a Python caller, so the two surfaces do not invent
 * two different ways to say the same wait. */
function humaniseWait(seconds: number | null): string {
  if (seconds === null) return 'shortly'
  if (seconds < 90) return 'in under a minute'
  const minutes = Math.round(seconds / 60)
  if (minutes < 60) return `in about ${minutes} minute${minutes === 1 ? '' : 's'}`
  const hours = Math.round(seconds / 3600)
  return hours <= 1 ? 'in about an hour' : `in about ${hours} hours`
}

export function ScanForm() {
  const [url, setUrl] = useState('')
  const [state, setState] = useState<State>({ status: 'idle' })

  const busy = state.status === 'submitting'

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault()
    if (busy || !url.trim()) return

    setState({ status: 'submitting' })
    try {
      const result = await startScan(url.trim())
      setState({ status: 'result', result })
    } catch (error) {
      if (error instanceof ScanError && error.status === 429) {
        setState({
          status: 'limited',
          message: `Too many scans right now — try again ${humaniseWait(error.retryAfterSeconds)}.`,
          retryAfterSeconds: error.retryAfterSeconds,
        })
        return
      }
      const message =
        error instanceof ScanError
          ? error.message
          : 'Could not reach the scan service. Is the API running?'
      setState({ status: 'refused', message })
    }
  }

  async function onDelete(id: string) {
    // F-10: this used to be an unguarded floating promise — no try/catch, so
    // a failed delete threw an unhandled rejection while the screen still
    // flipped to "deleted" underneath it (the caller never awaited this).
    try {
      await deleteScan(id)
      setState({ status: 'deleted' })
    } catch (error) {
      setState({
        status: 'refused',
        message: error instanceof ScanError ? error.message : 'Could not delete that result.',
      })
    }
  }

  if (state.status === 'result') {
    return <ScanResultView result={state.result} onDelete={onDelete} onScanAnother={() => setState({ status: 'idle' })} />
  }

  if (state.status === 'refused') {
    return (
      <div className="rounded-2xl border border-ink-200 bg-white p-6 shadow-paper">
        <p role="alert" className="text-sm text-clay-600">
          {state.message}
        </p>
        <Button className="mt-4" variant="secondary" onClick={() => setState({ status: 'idle' })}>
          Try a different address
        </Button>
      </div>
    )
  }

  if (state.status === 'limited') {
    return (
      <div className="rounded-2xl border border-ink-200 bg-white p-6 shadow-paper">
        <p role="alert" className="text-sm text-clay-600">
          {state.message}
        </p>
        {/* F-11: `refused` and `deleted` both offer a way out; `limited` used
            to be the one dead end on this form — nothing to click but reload
            the page. */}
        <Button className="mt-4" variant="secondary" onClick={() => setState({ status: 'idle' })}>
          Try a different address
        </Button>
      </div>
    )
  }

  if (state.status === 'deleted') {
    return (
      <div className="rounded-2xl border border-ink-200 bg-white p-6 shadow-paper">
        <p className="text-sm text-ink-600">This result has been deleted.</p>
        <Button className="mt-4" variant="secondary" onClick={() => setState({ status: 'idle' })}>
          Scan another site
        </Button>
      </div>
    )
  }

  return (
    <form onSubmit={onSubmit} noValidate className="flex flex-col gap-4">
      <div className="flex flex-col gap-3 sm:flex-row">
        <label htmlFor="scan-url" className="sr-only">
          Your website address
        </label>
        <input
          id="scan-url"
          type="text"
          inputMode="url"
          autoComplete="url"
          placeholder="yourcompany.om"
          value={url}
          onChange={(event) => setUrl(event.target.value)}
          disabled={busy}
          className="h-12 flex-1 rounded-xl border border-ink-200 bg-white px-4 text-[0.95rem] text-ink-900 shadow-paper outline-none transition-colors placeholder:text-ink-300 focus:border-steel-500 focus:ring-2 focus:ring-steel-200 disabled:bg-bone-100"
        />
        <Button type="submit" loading={busy} loadingLabel="Scanning…" icon={<ArrowRight />} disabled={!url.trim()}>
          Scan my site
        </Button>
      </div>
      <p className="text-xs text-ink-500">
        No login needed. Results are cached for 7 days, and you can delete yours at any time.
      </p>
    </form>
  )
}

function ScanResultView({
  result,
  onDelete,
  onScanAnother,
}: {
  result: ScanResult
  onDelete: (id: string) => void
  onScanAnother: () => void
}) {
  return (
    <div className="flex flex-col gap-6">
      <div className="rounded-2xl border border-ink-200 bg-white p-6 shadow-paper">
        {result.js_rendered ? (
          <JsRenderedState domain={result.domain} pagesRead={result.pages_read} />
        ) : result.checks.length === 0 ? (
          <AllHeldState domain={result.domain} pagesRead={result.pages_read} />
        ) : (
          <FindingsState result={result} />
        )}
      </div>

      <div className="flex items-center justify-between text-xs text-ink-500">
        <span>Results are cached for 7 days.</span>
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={onScanAnother}
            className="font-medium text-steel-600 underline decoration-steel-300 underline-offset-2 hover:text-steel-700"
          >
            Scan another site
          </button>
          <button
            type="button"
            onClick={() => onDelete(result.id)}
            className="font-medium text-clay-600 underline decoration-clay-300 underline-offset-2 hover:text-clay-700"
          >
            Delete this result
          </button>
        </div>
      </div>
    </div>
  )
}

function FindingsState({ result }: { result: ScanResult }) {
  const pageWord = result.pages_read === 1 ? 'page' : 'pages'
  return (
    <div data-testid="scan-findings" className="flex flex-col gap-4">
      <p className="text-sm text-ink-600">
        Read {result.pages_read} {pageWord} on {result.domain}. {result.checks.length} thing
        {result.checks.length === 1 ? '' : 's'} worth a look:
      </p>
      <ol className="flex flex-col gap-4">
        {result.checks.map((check, index) => (
          <li key={check.id} className="flex gap-3">
            <span className="mt-0.5 font-display text-lg font-bold text-clay-600">{index + 1}</span>
            <div>
              <p className="font-medium text-ink-900">{check.label}</p>
              <p className="mt-1 text-sm text-ink-600">{check.evidence}</p>
            </div>
          </li>
        ))}
      </ol>
    </div>
  )
}

function AllHeldState({ domain, pagesRead }: { domain: string; pagesRead: number }) {
  const pageWord = pagesRead === 1 ? 'page' : 'pages'
  return (
    <p className="text-sm text-ink-600">
      Every check held on the {pageWord} we read for {domain}. That is not a full audit — one page
      cannot see your keywords, traffic or competitors — so it is a clean read, not a clean bill of
      health.
    </p>
  )
}

function JsRenderedState({ domain, pagesRead }: { domain: string; pagesRead: number }) {
  const pageWord = pagesRead === 1 ? 'page' : 'pages'
  return (
    <p className="text-sm text-ink-600">
      {domain}&rsquo;s {pageWord} build{pagesRead === 1 ? 's' : ''} their text in the browser, so
      there was nothing in the page source for us to read. Nothing is wrong with the site — we
      simply could not score it this way.
    </p>
  )
}
