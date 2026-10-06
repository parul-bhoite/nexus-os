'use client'

import Link from 'next/link'
import { useState } from 'react'
import { Field } from '@/components/auth/Field'
import { ArrowRight, Button } from '@/components/ui/Button'
import {
  AuthError,
  DomainTakenError,
  registerCompany,
  requestToJoin,
  type JoinOffer,
} from '@/lib/auth-client'
import { useSlowLabel } from '@/lib/slow'
import { looksLikeWebsite } from '@/lib/website-url'

type State =
  | { status: 'idle' }
  | { status: 'submitting' }
  | { status: 'error'; message: string }
  | { status: 'taken'; offer: JoinOffer }
  | { status: 'requested' }

/**
 * Part 1 of 3 — company details, inline in the combined onboarding flow.
 *
 * A sibling of `components/auth/RegisterCompanyForm.tsx`, not a reskin of it:
 * this stage never redirects (it calls `onComplete` and `StartFlow` advances
 * in place), and it carries no Department field — Areas of Interest (stage 2,
 * `AreasStage`) replaces the single stated-department select with a real
 * multi-select backed by `workspace_department`, per ADR 0067. `looksLikeWebsite`
 * and the `DomainTakenError` → "ask to join" handling are shared with the old
 * form via `lib/website-url.ts` and `lib/auth-client.ts` respectively, rather
 * than duplicated.
 */
export function CompanyStage({ onComplete }: { onComplete: () => void }) {
  const [name, setName] = useState('')
  const [websiteUrl, setWebsiteUrl] = useState('')
  const [designation, setDesignation] = useState('')
  const [state, setState] = useState<State>({ status: 'idle' })
  const [joining, setJoining] = useState(false)

  const busy = state.status === 'submitting'
  const createLabel = useSlowLabel(busy, 'Continue', 'Creating…', 'Still creating…')

  const blockedBy =
    name.trim() === ''
      ? 'Name the company.'
      : websiteUrl.trim() === ''
        ? 'Add the website NEXUS should read first.'
        : !looksLikeWebsite(websiteUrl)
          ? 'That does not look like a website address. Try acme.om.'
          : undefined

  async function submit(confirmSeparateCompany: boolean) {
    setState({ status: 'submitting' })
    try {
      await registerCompany(
        {
          name: name.trim(),
          website_url: websiteUrl.trim(),
          designation: designation.trim() || null,
          // The single stated-department field is gone. Areas of Interest
          // (stage 2) is the real, multi-select replacement — see the module
          // doc comment.
          department: null,
        },
        { confirmSeparateCompany },
      )
      onComplete()
    } catch (error) {
      if (error instanceof DomainTakenError) {
        setState({ status: 'taken', offer: error.offer })
        return
      }
      setState({
        status: 'error',
        message:
          error instanceof AuthError
            ? error.message
            : 'Could not reach the account service. Try again in a moment.',
      })
    }
  }

  if (state.status === 'requested') {
    return (
      <div className="flex flex-col gap-4">
        <p className="text-ink-700">
          Your request is with that company&rsquo;s administrators. You will be able to sign in
          once somebody approves it.
        </p>
      </div>
    )
  }

  if (state.status === 'taken') {
    return (
      <div className="flex flex-col gap-6">
        <div
          role="status"
          className="rounded-xl border border-gold-300 bg-gold-100 px-4 py-3 text-sm text-ink-800"
        >
          {state.offer.detail}
        </div>
        <div className="flex flex-col gap-3">
          <Button
            type="button"
            size="lg"
            icon={joining ? undefined : <ArrowRight />}
            loading={joining}
            loadingLabel="Sending…"
            disabled={joining}
            onClick={async () => {
              if (joining) return
              setJoining(true)
              try {
                await requestToJoin(websiteUrl.trim())
                setState({ status: 'requested' })
              } catch (error) {
                setState({
                  status: 'error',
                  message: error instanceof AuthError ? error.message : 'Could not send that request.',
                })
              } finally {
                setJoining(false)
              }
            }}
          >
            Ask to join them
          </Button>
          <Button type="button" size="lg" variant="secondary" onClick={() => void submit(true)}>
            This is a different company on the same domain
          </Button>
        </div>
      </div>
    )
  }

  return (
    <form
      onSubmit={(event) => {
        event.preventDefault()
        if (busy) return
        if (blockedBy) {
          setState({ status: 'error', message: blockedBy })
          return
        }
        void submit(false)
      }}
      noValidate
      className="flex flex-col gap-5"
    >
      <h1 className="font-display text-page text-ink-900">Let&rsquo;s start with your company.</h1>
      <p className="-mt-2 max-w-read text-body text-ink-600">
        Just enough to begin. Verifying you own the domain happens later, in{' '}
        <Link
          href="/settings"
          className="font-medium text-steel-600 underline decoration-steel-300 underline-offset-2 hover:text-steel-700"
        >
          Settings
        </Link>
        — you can start straight away.
      </p>

      {state.status === 'error' ? (
        <div
          role="alert"
          aria-live="assertive"
          className="rounded-xl border border-clay-300 bg-clay-100 px-4 py-3 text-sm text-clay-600"
        >
          {state.message}
        </div>
      ) : null}

      <Field required label="Company name" value={name} onChange={setName} disabled={busy} />
      <Field
        required
        label="Website"
        value={websiteUrl}
        onChange={setWebsiteUrl}
        disabled={busy}
        placeholder="yourcompany.om"
        hint="Where NEXUS starts learning about you. You can add more URLs later."
      />
      <Field
        label="Your role (optional)"
        value={designation}
        onChange={setDesignation}
        disabled={busy}
        placeholder="Founder, Head of Sales…"
      />

      <Button
        type="submit"
        size="lg"
        disabled={busy}
        icon={busy ? undefined : <ArrowRight />}
        className="mt-1 w-full"
      >
        {createLabel}
      </Button>
      <p className="text-meta text-ink-500">Takes under a minute</p>
    </form>
  )
}
