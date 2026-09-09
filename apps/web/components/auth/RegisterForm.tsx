'use client'

import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { useState } from 'react'
import { Field } from '@/components/auth/Field'
import { ArrowRight, Button } from '@/components/ui/Button'
import { AuthError, MIN_PASSWORD_LENGTH, login, register } from '@/lib/auth-client'

type State =
  | { status: 'idle' }
  | { status: 'submitting' }
  // `taken` marks the one error this form can diagnose rather than relay.
  // See the note on `onSubmit` for why a 401 here means precisely one thing,
  // and what stating it costs.
  | { status: 'error'; message: string; taken?: boolean }

export function RegisterForm() {
  const router = useRouter()
  const [fullName, setFullName] = useState('')
  const [phone, setPhone] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [state, setState] = useState<State>({ status: 'idle' })

  const busy = state.status === 'submitting'
  const tooShort = password !== '' && password.length < MIN_PASSWORD_LENGTH

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault()
    if (busy || tooShort) return

    setState({ status: 'submitting' })
    try {
      await register(email.trim(), password, { displayName: fullName, phone })
    } catch (error) {
      const message =
        error instanceof AuthError
          ? error.message
          : 'Could not reach the account service. Is the API running?'
      setState({ status: 'error', message })
      return
    }

    // Sign in with the password they just chose, rather than asking for it a
    // second time on the same page. This leaks nothing the old two-step did
    // not: whether sign-in succeeds already distinguished a new account from
    // an existing one, and `register` above still answers identically either
    // way — which is where the enumeration resistance actually lives.
    try {
      await login(email.trim(), password)
      // Replace rather than push: the sign-up page must not sit in history
      // behind an authenticated page, where Back would show a stale form.
      //
      // Straight to the company. A brand-new account has no workspace, and
      // nothing else in the product works until it does.
      router.replace('/register-company')
    } catch {
      // **Why a 401 here can only mean "this address already has an account".**
      //
      // `/auth/register` above returned 201 whatever happened — it answers
      // identically for a new address and a taken one, which is where the
      // endpoint's enumeration resistance lives and is untouched by this. So by
      // the time we are here the account exists either way, and `authenticate`
      // rejects for exactly two reasons: the password does not match, or the
      // account is disabled. A brand-new account signs in with the password
      // just chosen, every time.
      //
      // Rate limiting does not muddy this. Being over the limit buys a delay on
      // *both* paths and never converts a valid credential into a 401
      // (`app/routes/auth.py`), which is what would otherwise make this
      // sentence a lie for somebody registering a genuinely new address from a
      // busy office IP.
      //
      // **What it costs.** The flow already distinguished the two cases in the
      // open — a new address was redirected to `/register-company` and a taken
      // one was not — so naming it does not create an oracle, it makes an
      // existing one legible. That is a real trade and it was made on purpose:
      // somebody who mistypes their own address should not have to infer what
      // happened from which screen they landed on.
      setState({
        status: 'error',
        taken: true,
        message: 'That address already has an account.',
      })
      setPassword('')
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
          {/* An error that only names the problem leaves somebody stranded on a
              form that cannot succeed. Both routes out are here, because the
              two reasons to be holding a taken address — it is yours and you
              forgot, or it is yours and you are already registered — have
              different answers. Nothing they typed is cleared but the
              password: retyping a name and a phone number to read an error
              message is its own small insult. */}
          {state.taken ? (
            <>
              {' '}
              <Link
                href="/login"
                className="font-medium underline decoration-clay-300 underline-offset-2"
              >
                Sign in
              </Link>{' '}
              instead, or{' '}
              <Link
                href="/forgot-password"
                className="font-medium underline decoration-clay-300 underline-offset-2"
              >
                reset your password
              </Link>
              .
            </>
          ) : null}
        </div>
      ) : null}

      {/* Name first, because the next screen is a conversation and the agent
          opens it by name. Asking afterwards would mean greeting somebody as
          "there" for the one exchange where it matters most. */}
      <Field
        label="Your name"
        value={fullName}
        onChange={setFullName}
        autoComplete="name"
        placeholder="Parul Bhoite"
        hint="What NEXUS will call you."
        disabled={busy}
      />

      <Field
        required
        label="Work email"
        type="email"
        value={email}
        onChange={setEmail}
        autoComplete="email"
        placeholder="you@yourcompany.om"
        hint="Use an address on your company's domain — it is how you will claim the domain later."
        disabled={busy}
      />

      <Field
        required
        label="Password"
        type="password"
        value={password}
        onChange={setPassword}
        autoComplete="new-password"
        disabled={busy}
        revealable
        hint={`At least ${MIN_PASSWORD_LENGTH} characters. A passphrase beats a short complicated one.`}
        error={tooShort ? `${MIN_PASSWORD_LENGTH - password.length} more characters needed.` : undefined}
      />

      {/* Optional, and labelled so. Nothing in the product is gated on it and
          nothing verifies it, so presenting it as required would be asking for
          a phone number under false pretences. */}
      <Field
        label="Phone (optional)"
        type="tel"
        value={phone}
        onChange={setPhone}
        autoComplete="tel"
        placeholder="+968 9xxx xxxx"
        hint="Only so a person can reach you. Never used to sign in, and not verified."
        disabled={busy}
      />

      <Button
        type="submit"
        size="lg"
        disabled={busy || tooShort || email.trim() === '' || password === ''}
        icon={busy ? undefined : <ArrowRight />}
        className="mt-1 w-full"
      >
        {busy ? 'Creating your account…' : 'Create account'}
      </Button>

      {/* No "Already have an account?" link here — finding F13. `AuthShell`
          renders one in its footer for every auth page, and this put a second
          copy a few pixels above it. */}
    </form>
  )
}
