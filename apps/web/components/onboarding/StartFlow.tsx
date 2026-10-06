'use client'

import { useEffect, useState } from 'react'
import { Button } from '@/components/ui/Button'
import { type AuraState } from '@/components/onboarding/OnboardingAura'
import { OnboardingShell } from '@/components/onboarding/OnboardingShell'
import { CompanyStage } from '@/components/onboarding/stages/CompanyStage'
import { AreasStage } from '@/components/onboarding/stages/AreasStage'
import { QuestionsStage } from '@/components/onboarding/stages/QuestionsStage'
import { WrapStage } from '@/components/onboarding/stages/WrapStage'
import { AuthError } from '@/lib/auth-client'
import { fetchCompany, fetchDepartments } from '@/lib/settings-client'
import { fetchQuestions } from '@/lib/onboarding-client'

/**
 * The combined onboarding flow — company details, Areas of Interest, tailored
 * questions, arrival — as one continuous experience (ADR 0067).
 *
 * ## Routing decision
 *
 * ADR 0067 (Flow A) keeps the entry at `/register-company` and has
 * `/onboarding/agent` redirect into the combined flow so bookmarks and
 * in-progress resumes survive. This component implements that by being
 * **mounted at both routes** rather than by issuing a server redirect from
 * one to the other: on mount it always resolves the founder's real position —
 * no company, no Areas chosen, questions outstanding, or done — from the API,
 * and renders that stage regardless of which URL was opened. A visitor who
 * bookmarks `/onboarding/agent` mid-flow and a visitor who bookmarks
 * `/register-company` after finishing both land in the same place, which is
 * what a redirect would also achieve, with one request saved and no risk of
 * the two routes disagreeing about the resume rule. `app/onboarding/agent/page.tsx`
 * documents this same reasoning next to the mount.
 *
 * ## Resume
 *
 * `fetchCompany()` answers "does a workspace exist yet" — `CurrentScope`
 * refuses with 403 ("no workspace selected") before one does, which this reads
 * as "start at Company" rather than as a failure. Once a company exists,
 * `fetchDepartments()` says whether Areas of Interest has ever been saved
 * (`running` on at least one non-`executive` department), and `fetchQuestions()`
 * says whether any catalogue question scoped to those areas is still
 * unanswered. Any other failure (not 401/403) is shown as a real error with a
 * retry, rather than guessed at — silently defaulting to "start over" on a
 * transient network blip would be worse than asking the founder to wait a
 * moment and try again.
 */

type Stage = 'company' | 'areas' | 'questions' | 'wrap'

const PART_FOR_STAGE: Record<Stage, 1 | 2 | 3> = {
  company: 1,
  areas: 2,
  questions: 2,
  wrap: 3,
}

const EYEBROW_FOR_STAGE: Record<Stage, string> = {
  company: 'a minute, then we start learning',
  areas: 'Areas of interest',
  questions: 'one question at a time',
  wrap: 'building your workspace',
}

type Resume = { status: 'loading' } | { status: 'error'; message: string } | { status: 'done' }

function hasValue(value: unknown): boolean {
  if (value === null || value === undefined) return false
  if (typeof value === 'string') return value.trim() !== ''
  if (Array.isArray(value)) return value.length > 0
  return true
}

export function StartFlow() {
  const [resume, setResume] = useState<Resume>({ status: 'loading' })
  const [stage, setStage] = useState<Stage>('company')
  const [selectedDepartments, setSelectedDepartments] = useState<string[]>([])
  const [aura, setAura] = useState<AuraState>('idle')

  useEffect(() => {
    void resolveStage()
    // Intentionally run once on mount — stage transitions afterwards are
    // driven by the stage components' own `onComplete` callbacks, not by
    // re-running this resolution.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  async function resolveStage() {
    setResume({ status: 'loading' })
    try {
      await fetchCompany()
    } catch (error) {
      if (error instanceof AuthError && (error.status === 403 || error.status === 401)) {
        setStage('company')
        setResume({ status: 'done' })
        return
      }
      setResume({
        status: 'error',
        message: error instanceof AuthError ? error.message : 'Could not reach the account service.',
      })
      return
    }

    try {
      const { departments } = await fetchDepartments()
      const selectable = departments.filter((d) => d.value !== 'executive')
      const selected = selectable.filter((d) => d.running).map((d) => d.value)
      if (selected.length === 0) {
        setStage('areas')
        setResume({ status: 'done' })
        return
      }
      setSelectedDepartments(selected)

      const { questions } = await fetchQuestions()
      const relevant = questions.filter(
        (q) => q.writable && (q.department === null || selected.includes(q.department)),
      )
      const unanswered = relevant.some((q) => !hasValue(q.value))
      setStage(unanswered ? 'questions' : 'wrap')
      setResume({ status: 'done' })
    } catch (error) {
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
          <Button variant="danger" size="sm" className="mt-4" onClick={() => void resolveStage()}>
            Retry
          </Button>
        </div>
      </OnboardingShell>
    )
  }

  return (
    <OnboardingShell part={PART_FOR_STAGE[stage]} eyebrow={EYEBROW_FOR_STAGE[stage]} stageKey={stage} aura={aura}>
      {stage === 'company' ? <CompanyStage onComplete={() => setStage('areas')} /> : null}
      {stage === 'areas' ? (
        <AreasStage
          onComplete={(selected) => {
            setSelectedDepartments(selected)
            setStage('questions')
          }}
        />
      ) : null}
      {stage === 'questions' ? (
        <QuestionsStage
          selectedDepartments={selectedDepartments}
          onAuraChange={setAura}
          onComplete={() => setStage('wrap')}
        />
      ) : null}
      {stage === 'wrap' ? <WrapStage /> : null}
    </OnboardingShell>
  )
}
