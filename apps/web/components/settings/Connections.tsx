'use client'

import { useEffect, useState } from 'react'
import {
  fetchConnections,
  revokeConnection,
  startAuthorization,
  type Connections as ConnectionsPayload,
  type Offerable,
} from '@/lib/connections-client'

/**
 * The tools this workspace is read from — `doc/14` S9, `doc/13`'s tool ledger.
 *
 * **Three states, and the middle one is the one screens usually get wrong.**
 * Connected, connectable, and *not configurable by this deployment* — the last
 * being a supported state under ADR 0011, not an error. A deployment with no
 * HubSpot client id shows the row and says so, rather than showing a Connect
 * button that fails at the vendor or hiding the row and looking broken.
 */

function messageOf(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback
}

function Row({
  tool,
  busy,
  onConnect,
  onDisconnect,
}: {
  tool: Offerable
  busy: boolean
  onConnect: () => void
  onDisconnect: () => void
}) {
  return (
    <li className="flex flex-wrap items-baseline gap-x-4 gap-y-2 px-4 py-4">
      <span className="min-w-0 grow">
        <span className="text-sm font-medium text-ink-900">{tool.name}</span>
        <span className="mt-0.5 block text-sm text-ink-500">
          {tool.connected
            ? 'Connected. The tiles that need it are reading from it.'
            : tool.configured
              ? 'Not connected. Connecting grants NEXUS a read of this system.'
              : /* ADR 0011: no credentials is a supported state, said plainly
                   rather than shown as a button that cannot work. */
                'Not available on this deployment — no credentials are configured for it.'}
        </span>
      </span>

      {tool.connected ? (
        <button
          type="button"
          disabled={busy}
          onClick={onDisconnect}
          className="rounded-lg border border-ink-200 px-3 py-1.5 text-sm font-medium text-ink-700 hover:border-ink-300 hover:text-ink-900 disabled:opacity-60"
        >
          {busy ? 'Working…' : 'Disconnect'}
        </button>
      ) : tool.configured ? (
        <button
          type="button"
          disabled={busy}
          onClick={onConnect}
          className="rounded-lg bg-ink-800 px-4 py-2 text-sm font-medium text-bone-50 disabled:opacity-60"
        >
          {busy ? 'Opening…' : `Connect ${tool.name}`}
        </button>
      ) : null}
    </li>
  )
}

export function Connections() {
  const [data, setData] = useState<ConnectionsPayload | null>(null)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [busy, setBusy] = useState('')

  async function reload() {
    try {
      setData(await fetchConnections())
      setError('')
    } catch (caught) {
      setError(messageOf(caught, 'Could not read your connections.'))
    }
  }

  useEffect(() => {
    void reload()
  }, [])

  async function connect(provider: string) {
    setBusy(provider)
    setNotice('')
    try {
      const { url } = await startAuthorization(provider)
      // The person follows it, not this fetch. A redirect returned from the API
      // would have been followed by `fetch` and never reach the browser bar.
      window.location.href = url
    } catch (caught) {
      setError(messageOf(caught, 'Could not start that connection.'))
      setBusy('')
    }
  }

  async function disconnect(provider: string) {
    setBusy(provider)
    setError('')
    try {
      const result = await revokeConnection(provider)
      setNotice(result.message)
      await reload()
    } catch (caught) {
      setError(messageOf(caught, 'Could not disconnect that.'))
    } finally {
      setBusy('')
    }
  }

  const tools = data?.offerable ?? []

  return (
    <section aria-labelledby="connections-heading" className="mt-10">
      <h2 id="connections-heading" className="font-display text-lg text-ink-900">
        Connected tools
      </h2>
      <p className="mt-1 max-w-prose text-sm text-ink-600">
        What NEXUS reads from. Connecting one grants a read of the whole company&rsquo;s data
        in that system, which is why it is an Owner or Executive decision.
      </p>

      {error ? (
        <p role="alert" className="mt-3 text-sm text-clay-600">
          {error}
        </p>
      ) : null}
      {notice ? (
        <p role="status" className="mt-3 text-sm text-steel-600">
          {notice}
        </p>
      ) : null}

      {tools.length > 0 ? (
        <ul className="mt-4 max-w-2xl divide-y divide-ink-100 rounded-xl border border-ink-100">
          {tools.map((tool) => (
            <Row
              key={tool.provider}
              tool={tool}
              busy={busy === tool.provider}
              onConnect={() => void connect(tool.provider)}
              onDisconnect={() => void disconnect(tool.provider)}
            />
          ))}
        </ul>
      ) : null}
    </section>
  )
}
