'use client'

import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { useEffect, useState } from 'react'
import { Field } from '@/components/auth/Field'
import { ArrowRight, Button } from '@/components/ui/Button'
import {
  AuthError,
  type DepartmentChoice,
  DomainTakenError,
  fetchDepartments,
  registerCompany,
  requestToJoin,
  type JoinOffer,
} from '@/lib/auth-client'
import { useSlowLabel } from '@/lib/slow'

type State =
  | { status: 'idle' }
  | { status: 'submitting' }
  | { status: 'error'; message: string }
  | { status: 'taken'; offer: JoinOffer }
  | { status: 'requested' }

/**
 * Register a company. One step — verification comes later, in Settings.
 *
 * That ordering is D19, and it is the whole reason this screen exists: until
 * P5 a signed-up user had to publish a DNS record before they could see
 * anything at all, so the product's front door was a systems administration
 * task.
 *
 * **The website URL is mandatory** (`doc/11` Q13). It is the first fact NEXUS
 * holds and the input the research run is queued against, so a company without
 * one is a company the product cannot begin to learn.
 */
export function RegisterCompanyForm() {
  const router = useRouter()
  const [name, setName] = useState('')
  const [websiteUrl, setWebsiteUrl] = useState('')
  const [designation, setDesignation] = useState('')
  /**
   * The department **key** — `hr`, not "People".
   *
   * This stored the label first, on the reasoning that both readers of
   * `stated_department` were prose: the onboarding greeting renders it into a
   * sentence, and the agent's grounding hands it to a model. That reasoning
   * ended the same day. A question-catalogue audit found the agent binding 26%
   * of its questions to another department's fields, and the fix —
   * `askable_fields(department)` — narrows the catalogue by matching this value
   * against the `Department` enum. That needs the key.
   *
   * The greeting still says "in People": `_viewer` resolves the key to its
   * label in the one place the sentence is built, and passes free text from
   * before this was a dropdown through untouched.
   */
  const [department, setDepartment] = useState('')
  const [departments, setDepartments] = useState<DepartmentChoice[]>([])
  const [departmentsError, setDepartmentsError] = useState<string | null>(null)

  // Fetched rather than listed here. The seven labels live in the API's
  // catalogue, and a copy in this file is how "People" became "Hr" on one
  // surface and not the others (finding F13).
  //
  // A failure is not fatal and must not block the form: Department is optional,
  // so the select stays disabled with the reason in its own placeholder while
  // every required field still submits. Losing an optional field beats losing
  // the company.
  useEffect(() => {
    let live = true
    fetchDepartments()
      .then((choices) => {
        if (live) setDepartments(choices)
      })
      .catch(() => {
        if (live) setDepartmentsError('Department list unavailable — skip this')
      })
    return () => {
      live = false
    }
  }, [])
  const [state, setState] = useState<State>({ status: 'idle' })

  const busy = state.status === 'submitting'
  // Finding F9: company creation measured ~8 s against Neon behind one
  // static word, which reads as a hang on the very first thing a founder does.
  const createLabel = useSlowLabel(busy, 'Create company', 'Creating…', 'Still creating…')

  async function submit(confirmSeparateCompany: boolean) {
    setState({ status: 'submitting' })
    try {
      await registerCompany(
        {
          name: name.trim(),
          website_url: websiteUrl.trim(),
          designation: designation.trim() || null,
          department: department.trim() || null,
        },
        { confirmSeparateCompany },
      )
      // The guided onboarding. It reads the domain from the workspace that was
      // just created, so nothing needs threading through the URL.
      router.replace('/onboarding/agent')
    } catch (error) {
      // The domain is already held by a company that has proved it. Not an
      // error to apologise for — it is usually the right answer arriving early,
      // because a colleague got here first.
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
            icon={<ArrowRight />}
            onClick={async () => {
              try {
                await requestToJoin(websiteUrl.trim())
                setState({ status: 'requested' })
              } catch (error) {
                setState({
                  status: 'error',
                  message:
                    error instanceof AuthError ? error.message : 'Could not send that request.',
                })
              }
            }}
          >
            Ask to join them
          </Button>
          {/* The escape hatch, and it stays a hatch. Two genuinely different
              businesses can share a domain — an agency and its trading arm —
              so this is possible and must be chosen, never defaulted. */}
          <Button
            type="button"
            size="lg"
            variant="secondary"
            onClick={() => void submit(true)}
          >
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
        if (!busy) void submit(false)
      }}
      noValidate
      className="flex flex-col gap-5"
    >
      {state.status === 'error' ? (
        <div
          role="alert"
          className="rounded-xl border border-clay-300 bg-clay-100 px-4 py-3 text-sm text-clay-600"
        >
          {state.message}
        </div>
      ) : null}

      <Field label="Company name" value={name} onChange={setName} disabled={busy} />
      <Field
        label="Website"
        value={websiteUrl}
        onChange={setWebsiteUrl}
        disabled={busy}
        placeholder="yourcompany.om"
        hint="Where NEXUS starts learning about you. You can add more URLs later."
      />
      {/* Country, reporting currency and headcount used to be asked here.
          Nothing read any of them — three columns written at registration and
          named by no SELECT in the codebase — and the currency is asked properly
          later: the question catalogue has it as a constrained choice carrying a
          scope and a stated `why`, and the summary skill infers it from the
          domain and offers it as an assumption to confirm. Three mechanisms for
          one fact, and this was the weakest: free text with a length check, so
          `ZZ` and `ZZZ` stored fine, pre-filled with Oman for everybody.

          A wrong default on a field nothing reads is worse than no field. It
          costs the founder a correction on their first screen, and the moment
          something does start reading the column it inherits whatever they
          could not be bothered to fix. Ask once, where the answer lands
          classified and can cite the sentence it came from. */}

      {/* What you do, not what you may see.
          These two steer the conversation that follows — which questions are
          worth your time, and what your dashboard leads with. They are
          deliberately not permissions: what you can read is set by your
          membership of this workspace, and typing "CFO" here does not open the
          ledger. Saying so on the form matters more than saying it in a
          docstring, because this is the field somebody would try it in. */}
      <div className="grid gap-5 sm:grid-cols-2">
        <Field
          label="Your role"
          value={designation}
          onChange={setDesignation}
          disabled={busy}
          placeholder="Founder, Head of Sales…"
        />
        <Field
          label="Department"
          value={department}
          onChange={setDepartment}
          disabled={busy || departments.length === 0}
          // Short because the field is half-width in this grid: "Select your
          // department…" was clipped to "Select your departme…". The label
          // directly above it already says which department.
          placeholder={departmentsError ?? 'Select…'}
          // Value is the key, label is what is shown. The server narrows the
          // question catalogue by this value, so it has to be the enum member.
          options={departments}
        />
      </div>
      <p className="-mt-2 text-sm text-ink-500">
        Used to decide what NEXUS asks you and shows you first. It does not change what you
        are allowed to see — that comes from your membership of this workspace.
      </p>

      {/* "In Settings" is now a link, because there is now a Settings
          (finding F3). This sentence, its twin on the page's intro and the
          API's own invitation refusal all named a screen that did not exist. */}
      <p className="text-sm text-ink-500">
        You can start straight away. Proving you own the domain happens in{' '}
        <Link
          href="/settings"
          className="font-medium text-steel-600 underline decoration-steel-300 underline-offset-2 hover:text-steel-700"
        >
          Settings
        </Link>
        , and is what unlocks inviting colleagues and connecting tools.
      </p>

      <Button
        type="submit"
        size="lg"
        disabled={busy || name.trim() === '' || websiteUrl.trim() === ''}
        icon={busy ? undefined : <ArrowRight />}
        className="mt-1 w-full"
      >
        {createLabel}
      </Button>
    </form>
  )
}
