'use client'

import { useEffect, useState } from 'react'
import { AuthError } from '@/lib/auth-client'
import {
  fetchPrices,
  updatePrice,
  minorToMajor,
  parseMajorToMinor,
  type AdminPrice,
} from '@/lib/billing-client'

/**
 * The platform-admin pricing editor (ADR 0076/0077).
 *
 * Reads the whole rate card from `/api/admin/prices` and lets an operator change
 * each department and tool price. The API gates both the read and the write on
 * the `NEXUS_PLATFORM_ADMIN_EMAILS` allowlist, so a non-admin sees the 403 branch
 * below rather than the table — the authority is server-side, this screen only
 * renders what it is allowed to read.
 *
 * Amounts are edited in major units (OMR 25.000, not 25000 baisa) and converted
 * on save, inverting `formatMinor`.
 */

const DEPARTMENT_LABEL: Record<string, string> = {
  marketing: 'Marketing',
  sales: 'Sales',
  finance: 'Finance',
  operations: 'Operations',
  hr: 'People',
  strategy: 'Strategy',
}

const TOOL_LABEL: Record<string, string> = {
  ga4: 'Google Analytics',
  search_console: 'Google Search Console',
  hubspot: 'HubSpot',
  salesforce: 'Salesforce',
  pipedrive: 'Pipedrive',
  zoho_crm: 'Zoho CRM',
  xero: 'Xero',
  quickbooks: 'QuickBooks',
  stripe: 'Stripe',
}

function labelFor(kind: string, key: string): string {
  return (kind === 'department' ? DEPARTMENT_LABEL : TOOL_LABEL)[key] ?? key
}

type Load =
  | { status: 'loading' }
  | { status: 'forbidden' }
  | { status: 'error'; message: string }
  | { status: 'ready'; prices: AdminPrice[] }

export function AdminPricing() {
  const [load, setLoad] = useState<Load>({ status: 'loading' })
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    let live = true
    setLoad({ status: 'loading' })
    fetchPrices()
      .then((prices) => {
        if (live) setLoad({ status: 'ready', prices })
      })
      .catch((error: unknown) => {
        if (!live) return
        if (error instanceof AuthError && error.status === 403) {
          setLoad({ status: 'forbidden' })
          return
        }
        setLoad({
          status: 'error',
          message: error instanceof Error ? error.message : 'Could not load the rate card.',
        })
      })
    return () => {
      live = false
    }
  }, [attempt])

  function onSaved(updated: AdminPrice) {
    setLoad((prev) =>
      prev.status === 'ready'
        ? {
            status: 'ready',
            prices: prev.prices.map((p) =>
              p.kind === updated.kind && p.key === updated.key ? updated : p,
            ),
          }
        : prev,
    )
  }

  if (load.status === 'loading') {
    return (
      <div aria-hidden className="flex flex-col gap-3">
        {Array.from({ length: 6 }).map((_, i) => (
          <div key={i} className="h-12 w-full animate-breathe rounded-data bg-bone-200" />
        ))}
      </div>
    )
  }

  if (load.status === 'forbidden') {
    return (
      <div role="alert" className="rounded-data border border-bone-300 bg-white px-6 py-5">
        <h2 className="font-medium text-ink-800">Not a platform admin</h2>
        <p className="mt-2 max-w-read text-sm text-ink-600">
          Editing the rate card is limited to platform administrators. Access is set by the
          <code className="mx-1 rounded bg-bone-100 px-1 font-mono text-xs">
            NEXUS_PLATFORM_ADMIN_EMAILS
          </code>
          allowlist on the server; your account is not on it.
        </p>
      </div>
    )
  }

  if (load.status === 'error') {
    return (
      <div role="alert" className="rounded-data border border-clay-300 bg-clay-100 px-6 py-5">
        <h2 className="font-medium text-ink-800">The rate card did not load</h2>
        <p className="mt-2 text-sm text-clay-600">{load.message}</p>
        <button
          type="button"
          onClick={() => setAttempt((n) => n + 1)}
          className="mt-4 min-h-[2.75rem] rounded-full bg-ink px-5 text-sm font-medium text-bone-50"
        >
          Try again
        </button>
      </div>
    )
  }

  const departments = load.prices.filter((p) => p.kind === 'department')
  const tools = load.prices.filter((p) => p.kind === 'tool')

  return (
    <div className="flex flex-col gap-8">
      <PriceGroup title="Departments" subtitle="Billed per selected area" rows={departments} onSaved={onSaved} />
      <PriceGroup title="Tools" subtitle="Charged when added from an unselected area" rows={tools} onSaved={onSaved} />
    </div>
  )
}

function PriceGroup({
  title,
  subtitle,
  rows,
  onSaved,
}: {
  title: string
  subtitle: string
  rows: AdminPrice[]
  onSaved: (p: AdminPrice) => void
}) {
  if (rows.length === 0) return null
  return (
    <section>
      <h2 className="font-display text-lg text-ink-900">{title}</h2>
      <p className="mt-0.5 text-sm text-ink-500">{subtitle}</p>
      <ul className="mt-3 divide-y divide-bone-200 rounded-data border border-bone-300 bg-white">
        {rows.map((price) => (
          <PriceRow key={`${price.kind}:${price.key}`} price={price} onSaved={onSaved} />
        ))}
      </ul>
    </section>
  )
}

function PriceRow({ price, onSaved }: { price: AdminPrice; onSaved: (p: AdminPrice) => void }) {
  const [amount, setAmount] = useState(String(minorToMajor(price.amount_minor, price.currency)))
  const [active, setActive] = useState(price.active)
  const [status, setStatus] = useState<'idle' | 'saving' | 'saved' | 'error'>('idle')
  const [error, setError] = useState<string | null>(null)

  async function save() {
    const minor = parseMajorToMinor(amount, price.currency)
    if (minor === null) {
      setStatus('error')
      setError('Enter a non-negative amount.')
      return
    }
    setStatus('saving')
    setError(null)
    try {
      const updated = await updatePrice(price.kind, price.key, { amount_minor: minor, active })
      onSaved(updated)
      setAmount(String(minorToMajor(updated.amount_minor, updated.currency)))
      setStatus('saved')
    } catch (caught) {
      setStatus('error')
      setError(caught instanceof Error ? caught.message : 'Save failed.')
    }
  }

  return (
    <li className="flex flex-wrap items-center gap-3 px-4 py-3">
      <span className="min-w-[10rem] flex-1 text-sm text-ink-800">
        {labelFor(price.kind, price.key)}
        <span className="ml-2 font-mono text-2xs text-ink-400">{price.key}</span>
      </span>
      <span className="font-mono text-2xs uppercase text-ink-400">{price.currency}</span>
      <label className="flex items-center gap-1.5 text-sm text-ink-700">
        <span className="sr-only">Monthly price for {labelFor(price.kind, price.key)}</span>
        <input
          type="text"
          inputMode="decimal"
          value={amount}
          onChange={(event) => {
            setAmount(event.target.value)
            setStatus('idle')
          }}
          className="w-28 rounded-control border border-bone-300 px-3 py-1.5 text-right text-sm text-ink tabular-nums"
        />
        <span className="text-ink-400">/ mo</span>
      </label>
      <label className="flex items-center gap-1.5 text-sm text-ink-600">
        <input
          type="checkbox"
          checked={active}
          onChange={(event) => {
            setActive(event.target.checked)
            setStatus('idle')
          }}
        />
        Active
      </label>
      <button
        type="button"
        onClick={() => void save()}
        disabled={status === 'saving'}
        className="min-h-[2.25rem] rounded-full bg-ink px-4 text-sm font-medium text-bone-50 disabled:opacity-50"
      >
        {status === 'saving' ? 'Saving…' : status === 'saved' ? 'Saved' : 'Save'}
      </button>
      {error && <span className="w-full text-xs text-clay-600">{error}</span>}
    </li>
  )
}
