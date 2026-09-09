'use client'

import Link from 'next/link'
import { useRouter, useSearchParams } from 'next/navigation'
import { useState } from 'react'
import { Field } from '@/components/auth/Field'
import { ArrowRight, Button } from '@/components/ui/Button'
import { AuthError, MIN_PASSWORD_LENGTH, confirmPasswordReset } from '@/lib/auth-client'

type State = { status: 'idle' } | { status: 'submitting' } | { status: 'error'; message: string }

/**
 * Spends a reset token and sets a new password.
 *
 * The token stays in the query string and is never put in component state that
 * outlives the submit — there is nothing to gain by copying it around, and one
 * fewer place it can end up in a log or a serialised error.
 *
 * **Succeeding here signs the account out everywhere, including here.** That is
 * the API's behaviour and it is the point: the ordinary reason to reset a
 * password is that somebody else has it, and leaving their session alive makes
 * the reset a formality. So this redirects to sign-in rather than to the
 * account page, which would 401 the moment it loaded.
 */
export function ResetPasswordForm() {
  const router = useRouter()
  const token = useSearchParams().get('token')
  const [password, setPassword] = useState('')
  const [confirmation, setConfirmation] = useState('')
  const [state, setState] = useState<State>({ status: 'idle' })

  const busy = state.status === 'submitting'
  const tooShort = password.length > 0 && password.length < MIN_PASSWORD_LENGTH
  const mismatched = confirmation.length > 0 && confirmation !== password

  if (!token) {
    return (
      <div className="flex flex-col gap-6">
        <div
          role="alert"
          className="rounded-xl border border-clay-300 bg-clay-100 px-4 py-3 text-sm text-clay-600"
        >
          This page needs the link from your reset email.
        </div>
        <Link
          href="/forgot-password"
          className="font-medium text-steel-600 underline decoration-steel-300 underline-offset-2 hover:text-steel-700"
        >
          Ask for a new link
        </Link>
      </div>
    )
  }

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault()
    if (busy || !token) return

    setState({ status: 'submitting' })
    try {
      await confirmPasswordReset(token, password)
      router.replace('/login?reset=1')
    } catch (error) {
      setState({
        status: 'error',
        message:
          error instanceof AuthError
            ? error.message
            : 'Could not reach the account service. Try again in a moment.',
      })
      setPassword('')
      setConfirmation('')
    }
  }

  return (
    <form onSubmit={onSubmit} noValidate className="flex flex-col gap-5">
      {state.status === 'error' ? (
        <div
          role="alert"
          className="rounded-xl border border-clay-300 bg-clay-100 px-4 py-3 text-sm text-clay-600"
        >
          {state.message}
        </div>
      ) : null}

      <Field
        required
        label="New password"
        type="password"
        value={password}
        onChange={setPassword}
        autoComplete="new-password"
        disabled={busy}
        revealable
        hint={`At least ${MIN_PASSWORD_LENGTH} characters.`}
        error={tooShort ? `Use at least ${MIN_PASSWORD_LENGTH} characters.` : undefined}
      />

      <Field
        label="Confirm new password"
        type="password"
        value={confirmation}
        onChange={setConfirmation}
        autoComplete="new-password"
        disabled={busy}
        revealable
        error={mismatched ? 'These do not match.' : undefined}
      />

      <p className="text-sm text-ink-500">
        Setting a new password signs you out on every device — including this one.
      </p>

      <Button
        type="submit"
        size="lg"
        disabled={busy || password.length < MIN_PASSWORD_LENGTH || confirmation !== password}
        icon={busy ? undefined : <ArrowRight />}
        className="mt-1 w-full"
      >
        {busy ? 'Saving…' : 'Set new password'}
      </Button>
    </form>
  )
}
