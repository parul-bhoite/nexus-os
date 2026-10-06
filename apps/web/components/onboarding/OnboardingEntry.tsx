'use client'

import { useEffect, useState } from 'react'
import { Button } from '@/components/ui/Button'
import { OnboardingShell } from '@/components/onboarding/OnboardingShell'
import { CompanyStage } from '@/components/onboarding/stages/CompanyStage'
import { ConversationalOnboarding } from '@/components/onboarding/ConversationalOnboarding'
import { AuthError } from '@/lib/auth-client'
import { fetchCompany } from '@/lib/settings-client'

/**
 * Mounted at both `/register-company` and `/onboarding/agent` (ADR 0069 phase 1).
 *
 * ## Company details stay a step ahead of the chat
 *
 * The conversational engine greets by name and reads the company's website —
 * both need a workspace to exist first. Rather than folding company creation
 * into the chat as its own turn, this reuses `CompanyStage` (already tested,
 * already wired to `registerCompany`/`looksLikeWebsite`/the domain-taken "ask
 * to join" path) as a single beat *before* the chat mounts. Two reasons:
 *
 * 1. **Account creation is a form, not a conversation.** A name field and a
 *    URL field with validation and a "this domain is already claimed" branch
 *    is exactly the shape `CompanyStage` already is. Re-deriving it as chat
 *    turns would be new surface for identical behaviour, and the domain-taken
 *    "ask to join" outcome reads far better as a form state than as something
 *    an agent apologises for mid-conversation.
 * 2. **Resume stays a single check.** `fetchCompany()` 403ing ("no workspace
 *    selected") is already the exact signal `StartFlow` resumes on. Mounting
 *    `CompanyStage` on that branch and the chat otherwise keeps the resume
 *    rule to one request, rather than teaching the chat engine to also handle
 *    "there is no company yet".
 *
 * Once a company exists, `ConversationalOnboarding` takes over entirely —
 * including department selection, which happens in the chat (its own doc
 * comment) rather than here.
 */

type Resume = { status: 'loading' } | { status: 'error'; message: string } | { status: 'company' } | { status: 'chat' }

export function OnboardingEntry() {
  const [resume, setResume] = useState<Resume>({ status: 'loading' })

  useEffect(() => {
    void resolve()
    // Run once on mount — `CompanyStage`'s own `onComplete` advances us locally.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  async function resolve() {
    setResume({ status: 'loading' })
    try {
      await fetchCompany()
      setResume({ status: 'chat' })
    } catch (error) {
      if (error instanceof AuthError && (error.status === 403 || error.status === 401)) {
        setResume({ status: 'company' })
        return
      }
      setResume({
        status: 'error',
        message: error instanceof AuthError ? error.message : 'Could not reach the account service.',
      })
    }
  }

  if (resume.status === 'loading') {
    return (
      <OnboardingShell part={1} eyebrow="loading your progress" stageKey="loading" aura="idle">
        <div aria-hidden className="flex flex-col gap-4">
          <div className="h-8 w-2/3 animate-breathe rounded-full bg-bone-200" />
          <div className="h-4 w-full animate-breathe rounded-full bg-bone-200" />
          <div className="h-4 w-5/6 animate-breathe rounded-full bg-bone-200" />
        </div>
      </OnboardingShell>
    )
  }

  if (resume.status === 'error') {
    return (
      <OnboardingShell part={1} eyebrow="something went wrong" stageKey="error" aura="idle">
        <div role="alert" className="rounded-data border border-clay-300 bg-clay-100 px-6 py-5">
          <h3 className="font-medium text-ink-800">Could not reach the account service</h3>
          <p className="mt-2 text-sm text-clay-600">{resume.message}</p>
          <Button variant="danger" size="sm" className="mt-4" onClick={() => void resolve()}>
            Retry
          </Button>
        </div>
      </OnboardingShell>
    )
  }

  if (resume.status === 'company') {
    return (
      <OnboardingShell part={1} eyebrow="a minute, then we start learning" stageKey="company" aura="idle">
        <CompanyStage onComplete={() => setResume({ status: 'chat' })} />
      </OnboardingShell>
    )
  }

  return <ConversationalOnboarding />
}
