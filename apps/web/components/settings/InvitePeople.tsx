'use client'

import { useEffect, useState } from 'react'
import { Button } from '@/components/ui/Button'
import { Dialog } from '@/components/ui/Overlay'
import { AuthError } from '@/lib/auth-client'
import { formatDate } from '@/lib/format'
import {
  createInvitation,
  fetchInvitations,
  revokeInvitation,
  type Invitation,
  type IssuedInvitation,
} from '@/lib/onboarding-client'

/**
 * Bringing somebody into the company.
 *
 * Finding F3: this screen did not exist. The API side was complete — issue,
 * list, revoke, an email, and a gate refusing all of it until the domain is
 * proved — and no page in the product sent an invitation, so the entire
 * multi-user half was unreachable from a browser.
 *
 * **The role and the departments are chosen here and nowhere else** (doc 06
 * §2.2). The acceptance screen offers neither, deliberately: a self-declared
 * role is privilege escalation via dropdown. That makes this form the only
 * place either fact is decided, which is why it states what each role gets
 * rather than listing six words in a select.
 */

type Role = {
  value: string
  label: string
  blurb: string
  /** How many departments this role takes. `'none'` means the role derives its
   *  own — an owner or executive is in Chief of Staff by definition. */
  departments: 'none' | 'one-to-three'
}

const ROLES: Role[] = [
  {
    value: 'executive',
    label: 'Executive',
    blurb: 'Sees the whole company, including the Chief of Staff page.',
    departments: 'none',
  },
  {
    value: 'department_manager',
    label: 'Department manager',
    blurb: 'Runs one to three departments, and their answers bind.',
    departments: 'one-to-three',
  },
  {
    value: 'contributor',
    label: 'Contributor',
    blurb:
      'Works inside their departments. Their answers are proposed and wait for a manager, ' +
      'and they never see department-wide aggregates.',
    departments: 'one-to-three',
  },
  {
    value: 'viewer',
    label: 'Viewer',
    blurb: 'Company-wide material only, and nothing that belongs to a single department.',
    departments: 'none',
  },
  {
    value: 'external',
    label: 'External',
    blurb: 'An accountant or agency. The narrowest access there is.',
    departments: 'none',
  },
]

const MAX_DEPARTMENTS = 3

type Sent = { issued: IssuedInvitation } | null

export function InvitePeople({
  verified,
  mayAdminister,
  departments,
}: {
  verified: boolean
  mayAdminister: boolean
  /** The departments this company actually runs, with their labels. */
  departments: { value: string; label: string }[]
}) {
  const [email, setEmail] = useState('')
  const [role, setRole] = useState('contributor')
  const [chosen, setChosen] = useState<string[]>([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [sent, setSent] = useState<Sent>(null)
  const [existing, setExisting] = useState<Invitation[] | null>(null)
  // F-19: which invitation is awaiting a confirmed withdrawal, and a per-row
  // busy flag so a second click while the first request is still in flight
  // cannot fire twice.
  const [confirmWithdraw, setConfirmWithdraw] = useState<Invitation | null>(null)
  const [withdrawing, setWithdrawing] = useState<string | null>(null)

  const selectedRole = ROLES.find((r) => r.value === role) ?? ROLES[2]
  const needsDepartments = selectedRole.departments === 'one-to-three'

  useEffect(() => {
    if (!mayAdminister) return
    let live = true
    fetchInvitations()
      .then((found) => live && setExisting(found))
      // A list that will not load must not take the form down with it — the
      // useful half of this screen is the one that sends.
      .catch(() => live && setExisting([]))
    return () => {
      live = false
    }
  }, [mayAdminister])

  if (!mayAdminister) {
    return (
      <section className="rounded-2xl border border-ink-100 bg-white px-5 py-5 shadow-paper">
        <h2 className="font-display text-lg font-medium text-ink-900">People</h2>
        <p className="mt-2 text-[0.95rem] leading-relaxed text-ink-700">
          Owners, executives and department managers bring people into a company. Your
          account is not one of those, so there is nothing for you to do here.
        </p>
      </section>
    )
  }

  if (!verified) {
    // The same refusal the API gives, said before the attempt rather than
    // after it — and it no longer points at a screen that does not exist,
    // because this is that screen.
    return (
      <section className="rounded-2xl border border-ink-100 bg-white px-5 py-5 shadow-paper">
        <h2 className="font-display text-lg font-medium text-ink-900">Invite your colleagues</h2>
        <p className="mt-2 max-w-prose text-[0.95rem] leading-relaxed text-ink-700">
          Not yet — <strong>verify the domain first</strong>. It proves the company is yours,
          which is what stops somebody else registering it and inviting your colleagues. The
          card above has the record to add.
        </p>
      </section>
    )
  }

  async function send(event: React.FormEvent) {
    event.preventDefault()
    if (busy) return

    // F-24: the form sets `noValidate`, so this is what actually stops an
    // incomplete submit — the `disabled` attribute below covers a mouse
    // click, but an implicit submit (Enter in the email field) still fires
    // this handler.
    if (email.trim() === '') {
      setError('Enter the address you are inviting.')
      return
    }
    if (departmentCountWrong) {
      setError(`Choose one to ${MAX_DEPARTMENTS} departments for this role.`)
      return
    }

    setBusy(true)
    setError(null)
    setSent(null)
    try {
      const issued = await createInvitation({
        email: email.trim().toLowerCase(),
        role,
        departments: needsDepartments ? chosen : [],
      })
      setSent({ issued })
      setEmail('')
      setChosen([])
      setExisting(await fetchInvitations().catch(() => existing ?? []))
    } catch (caught) {
      setError(
        caught instanceof AuthError
          ? caught.message
          : 'Could not reach the setup service. Is the API running?',
      )
    } finally {
      setBusy(false)
    }
  }

  const departmentCountWrong =
    needsDepartments && (chosen.length === 0 || chosen.length > MAX_DEPARTMENTS)

  return (
    <section className="rounded-2xl border border-ink-100 bg-white px-5 py-5 shadow-paper">
      <h2 className="font-display text-lg font-medium text-ink-900">Invite your colleagues</h2>
      <p className="mt-2 max-w-prose text-[0.95rem] leading-relaxed text-ink-600">
        The role and departments you choose here are what the invitation carries. The person
        accepting is never asked — they get what you set, which is why a forwarded link cannot
        seat somebody in a role that was chosen for someone else.
      </p>

      {error ? (
        <div
          role="alert"
          className="mt-4 rounded-xl border border-clay-300 bg-clay-100 px-4 py-3 text-sm text-clay-600"
        >
          {error}
        </div>
      ) : null}

      {sent ? (
        <div className="mt-4 rounded-xl border border-steel-300 bg-steel-100 px-4 py-3 text-sm text-ink-700">
          <p>
            Invitation sent to <span className="font-medium">{sent.issued.email}</span>. It
            {/* F-20: unguarded `new Date(...).toLocaleDateString()` printed
                the literal string "Invalid Date" for anything malformed, and
                used the runtime's implicit locale otherwise. `formatDate`
                closes both. */}
            {formatDate(sent.issued.expires_at)
              ? ` expires ${formatDate(sent.issued.expires_at)}.`
              : ' has an expiry date.'}
          </p>
          {/* Handed back as well as emailed. An owner who would rather paste it
              into a chat should be able to; the link alone grants nothing,
              since accepting requires being signed in as the address it names. */}
          <p className="mt-2 break-all font-mono text-[0.75rem] text-ink-600">
            {sent.issued.accept_path}
          </p>
        </div>
      ) : null}

      <form onSubmit={send} noValidate className="mt-6 flex flex-col gap-5">
        <label className="flex flex-col gap-1.5">
          <span className="font-medium text-ink-900">Their work email</span>
          <input
            type="email"
            value={email}
            disabled={busy}
            onChange={(e) => setEmail(e.target.value)}
            autoComplete="off"
            placeholder="colleague@yourcompany.om"
            className="rounded-xl border border-ink-200 bg-white px-3 py-2 text-ink-900 disabled:bg-bone-100"
          />
        </label>

        <fieldset disabled={busy}>
          <legend className="font-medium text-ink-900">What they get</legend>
          <div className="mt-2 flex flex-col gap-2">
            {ROLES.map((option) => (
              <label
                key={option.value}
                className="flex items-start gap-2 rounded-xl bg-bone-50 px-3 py-2 text-[0.95rem] text-ink-800"
              >
                <input
                  type="radio"
                  name="invite-role"
                  value={option.value}
                  checked={role === option.value}
                  onChange={() => {
                    setRole(option.value)
                    setChosen([])
                  }}
                  className="mt-1.5"
                />
                <span>
                  <span className="font-medium">{option.label}</span>
                  <span className="mt-0.5 block text-sm text-ink-600">{option.blurb}</span>
                </span>
              </label>
            ))}
          </div>
        </fieldset>

        {/* Shown only for the roles that take one. A department on a Viewer is
            a label with no effect, and a label with no effect is what somebody
            later mistakes for a boundary — so the API refuses it and this form
            does not offer it. */}
        {needsDepartments ? (
          <fieldset disabled={busy}>
            <legend className="font-medium text-ink-900">
              Which departments — one to {MAX_DEPARTMENTS}
            </legend>
            {departments.length === 0 ? (
              <p className="mt-2 text-[0.95rem] text-ink-600">
                Your company has not chosen its departments yet, so there is none to assign.
                Finish workspace setup first.
              </p>
            ) : (
              <div className="mt-2 flex flex-wrap gap-2">
                {departments.map((d) => {
                  const on = chosen.includes(d.value)
                  return (
                    <label
                      key={d.value}
                      // X-05: the `sr-only` checkbox had no focus ring at all
                      // — a keyboard user tabbing through these pills had no
                      // way to see which one they were on — and selection was
                      // carried by colour alone, which a low-vision or
                      // colour-blind reader cannot rely on. `focus-within`
                      // puts the ring on the label the checkbox is hidden
                      // inside, and the check glyph is a second, non-colour
                      // signal for "on".
                      className={`flex cursor-pointer items-center gap-1.5 rounded-full border px-3.5 py-1.5 text-sm focus-within:ring-2 focus-within:ring-steel-500 focus-within:ring-offset-2 ${
                        on
                          ? 'border-ink-800 bg-ink-800 text-bone-50'
                          : 'border-ink-200 bg-white text-ink-700'
                      }`}
                    >
                      <input
                        type="checkbox"
                        className="sr-only"
                        checked={on}
                        onChange={(e) =>
                          setChosen(
                            e.target.checked
                              ? [...chosen, d.value]
                              : chosen.filter((x) => x !== d.value),
                          )
                        }
                      />
                      {on ? (
                        <svg viewBox="0 0 16 16" fill="none" aria-hidden="true" className="h-3.5 w-3.5">
                          <path
                            d="m3.5 8.5 2.75 2.75L12.5 5"
                            stroke="currentColor"
                            strokeWidth="1.6"
                            strokeLinecap="round"
                            strokeLinejoin="round"
                          />
                        </svg>
                      ) : null}
                      {d.label}
                    </label>
                  )
                })}
              </div>
            )}
            {chosen.length > MAX_DEPARTMENTS ? (
              <p className="mt-2 text-sm text-clay-600">
                At most {MAX_DEPARTMENTS}. Somebody who needs more than that is probably an
                executive.
              </p>
            ) : null}
          </fieldset>
        ) : null}

        <Button
          type="submit"
          size="lg"
          className="w-fit"
          disabled={busy || email.trim() === '' || departmentCountWrong}
        >
          {busy ? 'Sending…' : 'Send invitation'}
        </Button>
      </form>

      {/* ── Who is already invited ── */}
      {existing && existing.length > 0 ? (
        <div className="mt-8 border-t border-ink-100 pt-6">
          <h3 className="font-mono text-2xs uppercase tracking-[0.12em] text-ink-400">
            Already invited
          </h3>
          <ul className="mt-3 flex flex-col gap-2">
            {existing.map((entry) => (
              <li
                key={entry.invitation_id}
                className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-ink-100 px-4 py-2.5"
              >
                <span className="text-[0.95rem] text-ink-800">
                  {entry.email}{' '}
                  <span className="text-ink-500">— {entry.role.replace('_', ' ')}</span>
                </span>
                <span className="flex items-center gap-3">
                  <span className="rounded-full bg-bone-200 px-2.5 py-1 font-mono text-2xs uppercase tracking-[0.08em] text-ink-600">
                    {entry.state}
                  </span>
                  {entry.state === 'pending' ? (
                    <button
                      type="button"
                      disabled={withdrawing === entry.invitation_id}
                      className="text-sm font-medium text-clay-600 underline decoration-clay-300 underline-offset-2 disabled:opacity-60"
                      onClick={() => setConfirmWithdraw(entry)}
                    >
                      {withdrawing === entry.invitation_id ? 'Withdrawing…' : 'Withdraw'}
                    </button>
                  ) : null}
                </span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {/* F-19: confirm before withdrawing — an unconfirmed one-click revoke,
          same as disconnect on the tools panel. */}
      <Dialog
        open={confirmWithdraw !== null}
        onClose={() => setConfirmWithdraw(null)}
        title="Withdraw this invitation?"
        footer={
          <>
            <Button variant="secondary" onClick={() => setConfirmWithdraw(null)}>
              Cancel
            </Button>
            <Button
              variant="danger"
              loading={withdrawing === confirmWithdraw?.invitation_id}
              loadingLabel="Withdrawing…"
              onClick={async () => {
                const entry = confirmWithdraw
                if (!entry) return
                setConfirmWithdraw(null)
                setWithdrawing(entry.invitation_id)
                try {
                  await revokeInvitation(entry.invitation_id)
                  setExisting(await fetchInvitations())
                } catch (caught) {
                  setError(
                    caught instanceof AuthError
                      ? caught.message
                      : 'Could not withdraw that invitation.',
                  )
                } finally {
                  setWithdrawing(null)
                }
              }}
            >
              Withdraw
            </Button>
          </>
        }
      >
        {confirmWithdraw ? (
          <>
            The link sent to <strong>{confirmWithdraw.email}</strong> stops working. They can
            be invited again later.
          </>
        ) : null}
      </Dialog>
    </section>
  )
}
