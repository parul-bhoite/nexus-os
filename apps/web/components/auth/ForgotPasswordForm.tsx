'use client'

import Link from 'next/link'
import { useState } from 'react'
import { Field } from '@/components/auth/Field'
import { ArrowRight, Button } from '@/components/ui/Button'
import { requestPasswordReset } from '@/lib/auth-client'

type State = { status: 'idle' } | { status: 'submitting' } | { status: 'sent' }

/**
 * Asks for a reset link.
 *
 * **There is no error state, and that is the design.** The API answers
 * identically whether or not the address has an account, so this form has
 * nothing to distinguish — and a "no account with that address" message here
 * would be a complete account-enumeration oracle regardless of how carefully
 * the API avoided one. The confirmation below is deliberately written to be
 * true either way.
 *
 * A transport failure is swallowed for the same reason: "could not reach the
 * service" and "sent" must not depend on which address was typed. It cannot,
 * here — the request has already left — but keeping the two outcomes visually
 * identical removes the temptation to add a branch later.
 */
export function ForgotPasswordForm() {
  const [email, setEmail] = useState('')
  const [state, setState] = useState<State>({ status: 'idle' })

  const busy = state.status === 'submitting'

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault()
    if (busy) return

    setState({ status: 'submitting' })
    try {
      await requestPasswordReset(email.trim())
    } catch {
      // Deliberately ignored. See the note above.
    }
    setState({ status: 'sent' })
  }

  if (state.status === 'sent') {
    return (
      <div className="flex flex-col gap-6">
        <p className="text-ink-700">
          If there is a NEXUS OS account for <strong>{email.trim()}</strong>, a reset link is on
          its way. It works once and expires in an hour.
        </p>
        <p className="text-sm text-ink-500">
          Nothing has been revealed about whether that address has an account — this message is
          the same either way.
        </p>
        <Link
          href="/login"
          className="font-medium text-steel-600 underline decoration-steel-300 underline-offset-2 hover:text-steel-700"
        >
          Back to sign in
        </Link>
      </div>
    )
  }

  return (
    <form onSubmit={onSubmit} noValidate className="flex flex-col gap-5">
      <Field
        required
        label="Work email"
        type="email"
        value={email}
        onChange={setEmail}
        autoComplete="email"
        placeholder="you@yourcompany.om"
        disabled={busy}
      />
      <Button
        type="submit"
        size="lg"
        disabled={busy || email.trim() === ''}
        icon={busy ? undefined : <ArrowRight />}
        className="mt-1 w-full"
      >
        {busy ? 'Sending…' : 'Send a reset link'}
      </Button>
    </form>
  )
}
