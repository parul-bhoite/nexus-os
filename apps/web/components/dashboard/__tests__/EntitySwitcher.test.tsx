import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { EntitySwitcher } from '@/components/dashboard/EntitySwitcher'

/**
 * ADR 0026's most dangerous control.
 *
 * The two assertions that matter are that it is **absent** for a single-entity
 * account, and that switching does a **full navigation** rather than a state
 * update — because entity A's figures under entity B's name is the one failure
 * that would look entirely normal on screen.
 */

const TWO = {
  workspaces: [
    { workspace_id: 'ws-1', name: 'Entity One', role: 'owner', active: true },
    { workspace_id: 'ws-2', name: 'Entity Two', role: 'department_manager', active: false },
  ],
}

const ONE = { workspaces: [TWO.workspaces[0]] }

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

let assigned: string[] = []
let replaced: string[] = []

/** The URL the component reads `?switched=1` from. */
function at(search: string): void {
  Object.defineProperty(window, 'location', {
    configurable: true,
    value: {
      ...window.location,
      pathname: '/dashboard/executive',
      search,
      hash: '',
      assign: (url: string) => assigned.push(url),
    },
  })
}

beforeEach(() => {
  assigned = []
  replaced = []
  vi.stubGlobal('fetch', vi.fn(async () => json(TWO)))
  // `window.location.assign` is not implemented in jsdom and would warn; the
  // whole point of the component is that it calls it, so it is recorded.
  at('')
  vi.spyOn(window.history, 'replaceState').mockImplementation(
    (_s: unknown, _t: unknown, url?: string | URL | null) => {
      replaced.push(String(url))
    },
  )
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('EntitySwitcher', () => {
  it('renders nothing for an account holding one company', async () => {
    // Which is almost everybody. A switcher with one option implies a second
    // company exists somewhere this person cannot see.
    vi.stubGlobal('fetch', vi.fn(async () => json(ONE)))
    const { container } = render(<EntitySwitcher />)

    await waitFor(() => expect(container.firstChild).toBeNull())
  })

  it('points at Settings when the list cannot be read, rather than vanishing', async () => {
    // The first version set `[]` here and rendered nothing, so a timeout on
    // this one fetch made the switcher disappear for somebody holding two
    // companies with nothing saying why. Found in a browser under load, when
    // the proxy answered 503.
    //
    // Still not a red box — it is a navigation control, so the fallback is a
    // route to the panel that lists the same thing.
    vi.stubGlobal('fetch', vi.fn(async () => json({ detail: 'nope' }, 503)))
    render(<EntitySwitcher />)

    await waitFor(() =>
      expect(screen.getByRole('link', { name: /Settings lists them/ })).toBeTruthy(),
    )
  })

  it('marks the active company and offers the other', async () => {
    render(<EntitySwitcher />)

    await waitFor(() => expect(screen.getByRole('button', { name: 'Entity One' })).toBeTruthy())
    expect(screen.getByRole('button', { name: 'Entity One' })).toHaveProperty('disabled', true)
    expect(screen.getByRole('button', { name: 'Entity Two' })).toHaveProperty('disabled', false)
  })

  it('leaves the page entirely rather than updating state', async () => {
    // The assertion this component exists for. A `router.refresh()` would leave
    // React state, module state and any in-flight request from the previous
    // entity alive in the same document.
    render(<EntitySwitcher />)

    await waitFor(() => expect(screen.getByRole('button', { name: 'Entity Two' })).toBeTruthy())
    fireEvent.click(screen.getByRole('button', { name: 'Entity Two' }))

    // `?switched=1` is part of the contract, not decoration: it is the only
    // channel that survives a hard navigation, and it is what lets the next
    // document announce a switch whose URL is otherwise unchanged.
    await waitFor(() => expect(assigned).toEqual(['/dashboard?switched=1']))
  })

  it('announces which company you landed in, because the URL does not change', async () => {
    // `/dashboard` redirects an Owner to `/dashboard/executive`, so switching
    // from a dashboard navigates to the address already on screen. Without
    // this the only changed pixels were which pill was dark, and a screen
    // reader got nothing at all.
    at('?switched=1')
    render(<EntitySwitcher />)

    const said = await waitFor(() => screen.getByRole('status'))
    // Names the entity the *session* says is active, not the one that was
    // clicked — the risk this control carries is one company's figures under
    // another's name, so "switched successfully" would not be an answer.
    expect(said.textContent).toContain('Entity One')
  })

  it('strips the flag so a refresh does not re-announce a stale switch', async () => {
    at('?switched=1')
    render(<EntitySwitcher />)

    await waitFor(() => expect(screen.getByRole('status')).toBeTruthy())
    expect(replaced).toEqual(['/dashboard/executive'])
  })

  it('stays quiet on an ordinary visit', async () => {
    render(<EntitySwitcher />)

    await waitFor(() => expect(screen.getByRole('button', { name: 'Entity Two' })).toBeTruthy())
    expect(screen.queryByRole('status')).toBeNull()
    expect(replaced).toEqual([])
  })

  it('says you are still where you were when the switch fails', async () => {
    // The dangerous ambiguity: a failed switch that said nothing would leave
    // somebody unsure which company they are looking at.
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string, init?: RequestInit) =>
        init?.method === 'POST' ? json({ detail: 'no' }, 403) : json(TWO),
      ),
    )
    render(<EntitySwitcher />)

    await waitFor(() => expect(screen.getByRole('button', { name: 'Entity Two' })).toBeTruthy())
    fireEvent.click(screen.getByRole('button', { name: 'Entity Two' }))

    await waitFor(() => expect(screen.getByRole('alert').textContent).toContain('Entity One'))
    expect(assigned).toEqual([])
  })
})
