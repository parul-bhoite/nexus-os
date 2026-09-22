'use client'

import { useState } from 'react'
import { Button } from '@/components/ui/Button'
import { AuthError } from '@/lib/auth-client'
import {
  checkDomainClaim,
  startDomainClaim,
  type ClaimMethod,
  type DomainClaim,
} from '@/lib/settings-client'

type State =
  | { status: 'idle' }
  /** Starting verification for the first time — no claim exists yet. */
  | { status: 'starting' }
  | { status: 'claimed'; claim: DomainClaim; note: string | null }
  /**
   * F-09: "Check now" used to set `{ status: 'working' }`, a state the render
   * below matched nothing against — the instructions vanished while the
   * check ran, with no visible sign anything was happening. Carrying `claim`
   * here is what lets the instructions stay on screen through the check.
   */
  | { status: 'checking'; claim: DomainClaim }
  | { status: 'verified' }
  /**
   * F-09's other half: the catch on "Check now" used to discard `claim`
   * entirely, losing the one-time challenge token and forcing a restart from
   * scratch for what is usually just "not visible yet". `claim` is `null`
   * only for a failure to *start* verification, where there was never one to
   * keep.
   */
  | { status: 'error'; message: string; claim: DomainClaim | null }

/**
 * The four methods, in the order a person should consider them.
 *
 * DNS and file are `strong`; email is `weak` and says so on the card rather
 * than only in the API's `strength` field, because the consequence of picking
 * it — the workspace gets flagged for review if a colleague registers the same
 * domain — is a thing to know *before* choosing, not after.
 *
 * `manual` is offered last and honestly: it is a support conversation, not a
 * check this screen can run.
 */
const METHODS: { value: ClaimMethod; label: string; blurb: string }[] = [
  {
    value: 'dns_txt',
    label: 'DNS record',
    blurb: 'Add a TXT record. The strongest proof, and the usual choice.',
  },
  {
    value: 'file',
    label: 'File on your site',
    blurb: 'Publish a file at a known path. As strong as DNS, and often faster.',
  },
  {
    value: 'email',
    label: 'Email on the domain',
    blurb:
      'Only works if your own account is on this domain — a free provider is refused. ' +
      'Weaker: the workspace is flagged for review if somebody else from the company registers.',
  },
  {
    value: 'manual',
    label: 'Talk to support',
    blurb: 'For a domain none of the above can prove. Nothing is checked automatically.',
  },
]

/**
 * Proving the domain — after registration, not before it.
 *
 * D19 moved this here. It used to stand between a signed-up user and the whole
 * product: no workspace existed without a verified domain, so every scoped
 * endpoint answered 403 until somebody published a DNS record.
 *
 * **The card says what verification unlocks.** A step with no stated purpose
 * reads as bureaucracy, and the honest answer — that it is what stops somebody
 * else registering your domain and inviting your colleagues — is also the most
 * persuasive one.
 *
 * Finding F3: this component was written, tested by nothing, and imported by
 * nowhere, while three screens and one API refusal all told the user to come
 * here. It now has a route.
 */
export function DomainVerificationCard({
  domain,
  verified,
  mayAdminister,
  onVerified,
}: {
  domain: string
  verified: boolean
  mayAdminister: boolean
  onVerified?: () => void
}) {
  const [state, setState] = useState<State>(verified ? { status: 'verified' } : { status: 'idle' })
  const [method, setMethod] = useState<ClaimMethod>('dns_txt')

  // F-09: whichever claim this render has, regardless of whether it arrived
  // via `claimed`, is mid-`checking`, or survived into an `error` — so the
  // instructions and the challenge token they carry stay on screen through
  // all three, rather than vanishing the moment "Check now" is pressed or
  // failing to find the record.
  const activeClaim =
    state.status === 'claimed' || state.status === 'checking'
      ? state.claim
      : state.status === 'error'
        ? state.claim
        : null

  if (state.status === 'verified') {
    return (
      <section className="rounded-2xl border border-ink-100 bg-white px-5 py-5 shadow-paper">
        <h2 className="font-display text-lg font-medium text-ink-900">Domain verified</h2>
        <p className="mt-2 text-[0.95rem] leading-relaxed text-ink-700">
          <strong>{domain}</strong> is proved yours. You can invite colleagues and connect tools.
        </p>
      </section>
    )
  }

  return (
    <section className="rounded-2xl border border-gold-300 bg-gold-100 px-5 py-5">
      <h2 className="font-display text-lg font-medium text-ink-900">Verify {domain}</h2>
      <p className="mt-2 text-[0.95rem] leading-relaxed text-ink-800">
        Everything works without this except the two things that reach beyond you:{' '}
        <strong>inviting colleagues</strong> and <strong>connecting tools</strong>. Proving the
        domain is what stops somebody else registering it and inviting your team.
      </p>

      {!mayAdminister ? (
        <p className="mt-4 text-[0.95rem] leading-relaxed text-ink-700">
          An owner or executive does this. Your account can see that it is outstanding and
          nothing more.
        </p>
      ) : null}

      {state.status === 'error' ? (
        <div
          role="alert"
          className="mt-4 rounded-xl border border-clay-300 bg-clay-100 px-4 py-3 text-sm text-clay-600"
        >
          {state.message}
        </div>
      ) : null}

      {activeClaim ? (
        <div className="mt-4 flex flex-col gap-3">
          {/* The instruction comes from the API and carries the challenge
              token. Rendered `whitespace-pre-line` because it is written as
              lines — a DNS value on the same line as the sentence explaining it
              is a value somebody will copy wrong. */}
          <p className="whitespace-pre-line rounded-xl border border-ink-200 bg-white px-4 py-3 font-mono text-[0.8rem] leading-relaxed text-ink-800">
            {activeClaim.instruction}
          </p>

          {state.status === 'claimed' && state.note ? (
            <p className="text-[0.95rem] text-ink-800">{state.note}</p>
          ) : null}

          {activeClaim.method === 'manual' ? null : (
            <div className="flex flex-wrap items-center gap-3">
              <Button
                type="button"
                className="w-fit"
                loading={state.status === 'checking'}
                loadingLabel="Checking…"
                onClick={async () => {
                  const claim = activeClaim
                  setState({ status: 'checking', claim })
                  try {
                    const checked = await checkDomainClaim(claim.claim_id)
                    if (checked.state === 'verified') {
                      setState({ status: 'verified' })
                      onVerified?.()
                      return
                    }
                    // A check that has not found the record yet is not a
                    // failure — DNS propagates on its own schedule, and telling
                    // somebody their record is wrong when it is merely young
                    // sends them to edit a correct record. The API's own
                    // evidence is shown when it has any, because "no TXT
                    // records found" and "a TXT record that does not match" are
                    // different problems with different fixes.
                    setState({
                      status: 'claimed',
                      claim: checked,
                      note:
                        checked.evidence ??
                        'Not visible yet. DNS can take a few minutes to propagate — try again shortly.',
                    })
                  } catch (error) {
                    // F-09: `claim` travels into the error too, rather than
                    // being discarded — losing it meant losing the one-time
                    // challenge token, forcing a restart from scratch for
                    // what is usually just "try again in a minute".
                    setState({
                      status: 'error',
                      message: error instanceof AuthError ? error.message : 'Could not check.',
                      claim,
                    })
                  }
                }}
              >
                Check now
              </Button>
              <button
                type="button"
                className="text-sm font-medium text-steel-600 underline decoration-steel-300 underline-offset-2 hover:text-steel-700"
                onClick={() => setState({ status: 'idle' })}
              >
                Use a different method
              </button>
            </div>
          )}
        </div>
      ) : (
        <fieldset className="mt-5" disabled={!mayAdminister || state.status === 'starting'}>
          <legend className="font-mono text-2xs uppercase tracking-[0.12em] text-clay-600">
            How you want to prove it
          </legend>
          <div className="mt-3 flex flex-col gap-2">
            {METHODS.map((option) => (
              <label
                key={option.value}
                className="flex items-start gap-2 rounded-xl bg-white/60 px-3 py-2 text-[0.95rem] text-ink-800"
              >
                <input
                  type="radio"
                  name="domain-method"
                  value={option.value}
                  checked={method === option.value}
                  onChange={() => setMethod(option.value)}
                  className="mt-1.5"
                />
                <span>
                  <span className="font-medium">{option.label}</span>
                  <span className="mt-0.5 block text-sm text-ink-600">{option.blurb}</span>
                </span>
              </label>
            ))}
          </div>

          <div className="mt-4">
            <Button
              type="button"
              loading={state.status === 'starting'}
              loadingLabel="Starting…"
              onClick={async () => {
                setState({ status: 'starting' })
                try {
                  const claim = await startDomainClaim(domain, method)
                  setState({ status: 'claimed', claim, note: null })
                } catch (error) {
                  setState({
                    status: 'error',
                    message:
                      error instanceof AuthError
                        ? error.message
                        : 'Could not start verification.',
                    claim: null,
                  })
                }
              }}
            >
              Start verification
            </Button>
          </div>
        </fieldset>
      )}
    </section>
  )
}
