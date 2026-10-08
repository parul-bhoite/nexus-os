'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import { useRouter } from 'next/navigation'

import {
  type AgentState,
  ASSEMBLY_LABEL,
  ModelUnavailableError,
  assemblyDone,
  confirmBrief,
  declareTools,
  documentsDone,
  finish,
  read,
  readState,
  start,
} from '@/lib/agent-onboarding-client'
import { AuthError } from '@/lib/auth-client'
import { type CurrentCompany, fetchCompany, fetchDepartments } from '@/lib/settings-client'
import { type AuraState } from '@/components/onboarding/OnboardingAura'
import { StepperShell, type StepId } from '@/components/onboarding/OnboardingStepper'
import { CompanyStage } from '@/components/onboarding/stages/CompanyStage'
import { AreasStage } from '@/components/onboarding/stages/AreasStage'
import { ChatbotStep } from '@/components/onboarding/ChatbotStep'
import { DocumentsStep } from '@/components/onboarding/DocumentsStep'
import { ToolsStep } from '@/components/onboarding/ToolsStep'
import { BrainReview } from '@/components/onboarding/BrainReview'
import { PaymentStep } from '@/components/onboarding/PaymentStep'
import { fetchEntitlement } from '@/lib/billing-client'

/**
 * The stepped onboarding orchestrator (ADR 0073), mounted at both
 * `/register-company` and `/onboarding/agent`.
 *
 * Six steps with a visible stepper: Company → Areas of interest → Chatbot →
 * Documents → Tools → Company Brain, then the dashboard. It owns the engine
 * state once a company exists and maps the engine's phases onto the steps; the
 * chat, documents, tools and brain steps are thin over that state.
 *
 * ## Pre-warming the crawl
 *
 * The website read is the slow beat (~17s). It is kicked off the moment a
 * company exists — at the end of step 1, or on a resume that lands past it — so
 * it runs in the background while the founder picks their areas of interest. By
 * the time they reach the chatbot the read is usually done and the first
 * question is waiting; if it is not, the chatbot shows the "scanning your
 * company" loader. The `brief` the read produces is auto-confirmed here (no
 * inline correction step — ADR 0073), so the chatbot only ever sees the scan
 * loader, the unreadable fallback, or discovery questions.
 *
 * ## Resume
 *
 * On mount it resolves the founder's real position: no company → step 1; a
 * completed session → straight to the dashboard; a company but no areas chosen
 * → step 2; otherwise the engine's phase decides the step.
 */

type Boot =
  | { status: 'loading' }
  | { status: 'error'; message: string }
  | { status: 'blocked'; message: string }
  | { status: 'ready' }

/**
 * `fetchCompany`, retried on a transient server fault.
 *
 * The mount probe doubles as "does this founder have a company yet?" — a 403 or
 * 401 is the *answer* and must pass straight through to `resolve`, which places
 * the founder on step 1. A 5xx is not an answer: it is a blip in the account
 * service (a restart, a connection-pool hiccup) and must not eject somebody to
 * an error wall on what is their first authenticated page. So a 5xx is retried a
 * few times with a short backoff, and only a persistent one is surfaced. Any
 * other status (a 4xx) is a real response and is not retried.
 */
async function probeCompany(): Promise<CurrentCompany> {
  const backoffMs = [300, 800, 1500]
  for (let attempt = 0; ; attempt += 1) {
    try {
      return await fetchCompany()
    } catch (error) {
      const transient = error instanceof AuthError && error.status >= 500
      if (!transient || attempt >= backoffMs.length) throw error
      await new Promise((resolve) => setTimeout(resolve, backoffMs[attempt]))
    }
  }
}

export function OnboardingEntry() {
  const router = useRouter()
  const [boot, setBoot] = useState<Boot>({ status: 'loading' })
  const [step, setStep] = useState<StepId>('company')
  const [state, setState] = useState<AgentState | null>(null)
  const [departments, setDepartments] = useState<string[]>([])
  const [busy, setBusy] = useState(false)
  const [engineError, setEngineError] = useState<string | null>(null)
  const engineStarted = useRef(false)
  const assembling = useRef(false)

  /** Run engine work, routing the three outcomes that are not "try again". */
  const guard = useCallback(
    async <T,>(work: () => Promise<T>): Promise<T | undefined> => {
      setBusy(true)
      try {
        return await work()
      } catch (cause) {
        if (cause instanceof ModelUnavailableError) {
          setBoot({ status: 'blocked', message: cause.message })
          return undefined
        }
        if (cause instanceof AuthError && (cause.status === 401 || cause.status === 403)) {
          router.replace(`/login?next=${encodeURIComponent('/onboarding/agent')}`)
          return undefined
        }
        setBoot({ status: 'error', message: cause instanceof Error ? cause.message : 'Something went wrong.' })
        return undefined
      } finally {
        setBusy(false)
      }
    },
    [router],
  )

  /**
   * Start the engine, read the site, and auto-confirm the brief — idempotent,
   * so calling it again on a resume picks up wherever the session already is.
   */
  const warmEngine = useCallback(async () => {
    if (engineStarted.current) return
    engineStarted.current = true
    setBusy(true)
    setEngineError(null)
    try {
      let next = await readState()
      if (!next.active && !next.completed) next = await start()
      if (next.phase === 'analysing' && next.turns.length === 0 && !next.site_unreadable) {
        next = await read()
      }
      if (next.phase === 'brief') {
        next = await confirmBrief({})
      }
      setState(next)
    } catch (cause) {
      // A background pre-warm failure must not eject the founder from whatever
      // step they are on. The model being absent is terminal for onboarding
      // (ADR 0011/0022) and an expired session is a redirect; anything else is
      // held as a chat-local error the chatbot step surfaces with a retry.
      engineStarted.current = false
      if (cause instanceof ModelUnavailableError) {
        setBoot({ status: 'blocked', message: cause.message })
      } else if (cause instanceof AuthError && (cause.status === 401 || cause.status === 403)) {
        router.replace(`/login?next=${encodeURIComponent('/onboarding/agent')}`)
      } else {
        setEngineError(cause instanceof Error ? cause.message : 'Could not reach the setup assistant.')
      }
    } finally {
      setBusy(false)
    }
  }, [router])

  useEffect(() => {
    void resolve()
    // Once on mount; step transitions are driven by each step's own callback.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  async function resolve() {
    setBoot({ status: 'loading' })
    try {
      await probeCompany()
    } catch (error) {
      if (error instanceof AuthError && (error.status === 403 || error.status === 401)) {
        setStep('company')
        setBoot({ status: 'ready' })
        return
      }
      setBoot({
        status: 'error',
        message: error instanceof AuthError ? error.message : 'Could not reach the account service.',
      })
      return
    }

    // A company exists. Place the founder, and pre-warm the crawl.
    try {
      const existing = await readState()
      if (existing.completed) {
        // The Brain is assembled. The dashboard now requires entitlement
        // (payment or an active trial — ADR 0076); an unentitled founder
        // resumes at the Payment step rather than being waved through.
        const { entitled } = await fetchEntitlement()
        if (entitled) {
          router.replace('/dashboard')
          return
        }
        setState(existing)
        setStep('payment')
        setBoot({ status: 'ready' })
        return
      }
      const { departments: all } = await fetchDepartments()
      const chosen = all.filter((d) => d.value !== 'executive' && d.running).map((d) => d.value)
      setDepartments(chosen)
      setState(existing.active ? existing : null)

      if (chosen.length === 0) {
        setStep('areas')
      } else {
        setStep(stepForPhase(existing))
      }
      setBoot({ status: 'ready' })
      void warmEngine()
    } catch (error) {
      if (error instanceof ModelUnavailableError) {
        setBoot({ status: 'blocked', message: error.message })
        return
      }
      setBoot({
        status: 'error',
        message: error instanceof AuthError ? error.message : 'Could not reach the account service.',
      })
    }
  }

  /** Declare the stack and move to the Brain step; the assembly runs there. */
  function finishToBrain(providers: string[], skipped: boolean) {
    void guard(async () => {
      setState(await declareTools(providers, skipped))
      setStep('brain')
    })
  }

  /**
   * Drive the assembly to `ready` whenever the Brain step is showing an
   * unfinished session — after the tools click and on a resume that lands in
   * `persona`/`assembling`/`tools` alike. The ref keeps the loop single-flight
   * while each `finish()` updates `state` and re-runs this effect.
   */
  useEffect(() => {
    if (step !== 'brain' || !state) return
    if (state.phase === 'ready' || state.completed) {
      assembling.current = false
      return
    }
    if (assembling.current) return
    assembling.current = true
    const seed = state
    void guard(async () => {
      let next = seed
      for (let attempt = 0; attempt < 8 && !assemblyDone(next); attempt += 1) {
        const phaseBefore = next.phase
        const stepBefore = next.assembly_step ?? 0
        next = await finish()
        setState(next)
        if (next.phase === phaseBefore && (next.assembly_step ?? 0) === stepBefore) break
      }
    }).finally(() => {
      assembling.current = false
    })
  }, [step, state, guard])

  const aura: AuraState = busy ? 'thinking' : step === 'brain' && state?.phase === 'ready' ? 'ready' : 'idle'

  if (boot.status === 'loading') {
    return (
      <StepperShell current={step}>
        <div aria-hidden className="flex flex-col gap-4">
          <div className="h-8 w-2/3 animate-breathe rounded-full bg-bone-200" />
          <div className="h-4 w-full animate-breathe rounded-full bg-bone-200" />
          <div className="h-4 w-5/6 animate-breathe rounded-full bg-bone-200" />
        </div>
      </StepperShell>
    )
  }

  if (boot.status === 'blocked') {
    return (
      <StepperShell current={step}>
        <div className="max-w-md rounded-2xl border border-bone-300 bg-white p-6">
          <h1 className="font-display text-lg text-ink">Guided onboarding is unavailable</h1>
          <p className="mt-2 text-sm text-ink-600">{boot.message}</p>
          <p className="mt-3 text-xs text-ink-400">
            Sign-in and every existing workspace are unaffected. There is deliberately no fallback
            form — a questionnaire that quietly replaced the assistant would collect less and look
            the same.
          </p>
        </div>
      </StepperShell>
    )
  }

  if (boot.status === 'error') {
    return (
      <StepperShell current={step}>
        <div role="alert" className="rounded-data border border-clay-300 bg-clay-100 px-6 py-5">
          <h3 className="font-medium text-ink-800">Something went wrong</h3>
          <p className="mt-2 text-sm text-clay-600">{boot.message}</p>
          <button
            type="button"
            onClick={() => void resolve()}
            className="mt-4 min-h-[2.75rem] rounded-full bg-ink px-5 text-sm font-medium text-bone-50"
          >
            Retry
          </button>
        </div>
      </StepperShell>
    )
  }

  if (step === 'company') {
    return (
      <StepperShell current="company">
        <CompanyStage
          onComplete={() => {
            setStep('areas')
            void warmEngine()
          }}
        />
      </StepperShell>
    )
  }

  if (step === 'areas') {
    return (
      <StepperShell current="areas" wide>
        <AreasStage
          onComplete={(selected) => {
            setDepartments(selected)
            setStep('chat')
          }}
        />
      </StepperShell>
    )
  }

  if (step === 'chat') {
    return (
      <StepperShell current="chat" aura={aura} fill>
        {state ? (
          <ChatbotStep
            state={state}
            onState={setState}
            onComplete={() => setStep('documents')}
            onBusyChange={setBusy}
          />
        ) : engineError ? (
          <div className="mx-auto grid w-full max-w-2xl flex-1 place-items-center px-6 py-16">
            <div role="alert" className="max-w-md rounded-data border border-clay-300 bg-clay-100 px-6 py-5">
              <h3 className="font-medium text-ink-800">The setup assistant did not start</h3>
              <p className="mt-2 text-sm text-clay-600">{engineError}</p>
              <button
                type="button"
                onClick={() => void warmEngine()}
                disabled={busy}
                className="mt-4 min-h-[2.75rem] rounded-full bg-ink px-5 text-sm font-medium text-bone-50 disabled:opacity-50"
              >
                Try again
              </button>
            </div>
          </div>
        ) : (
          <div className="mx-auto grid w-full max-w-2xl flex-1 place-items-center px-6 py-16">
            <p role="status" aria-live="polite" className="text-sm text-ink-400">
              Scanning your company…
            </p>
          </div>
        )}
      </StepperShell>
    )
  }

  if (step === 'documents') {
    return (
      <StepperShell current="documents" aura={aura}>
        <DocumentsStep
          disabled={busy}
          onContinue={(skipped) =>
            void guard(async () => {
              setState(await documentsDone(skipped))
              setStep('tools')
            })
          }
        />
      </StepperShell>
    )
  }

  if (step === 'tools') {
    return (
      <StepperShell current="tools" aura={aura} wide>
        <ToolsStep
          disabled={busy}
          recommendedDepartments={departments}
          onContinue={(providers, skipped) => finishToBrain(providers, skipped)}
        />
      </StepperShell>
    )
  }

  if (step === 'brain') {
    return (
      <StepperShell current="brain" aura={aura}>
        {state ? (
          <BrainReview
            state={state}
            departments={departments}
            building={state.phase !== 'ready'}
            // The Brain is built; next is Payment (ADR 0076), not the dashboard.
            onOpen={() => setStep('payment')}
          />
        ) : (
          <p role="status" aria-live="polite" className="text-sm text-ink-400">
            {ASSEMBLY_LABEL.tools}
          </p>
        )}
      </StepperShell>
    )
  }

  // step === 'payment' — the costed summary + dummy gateway; on pay/trial the
  // workspace is entitled and we open the dashboard.
  return (
    <StepperShell current="payment" aura={aura}>
      <PaymentStep onDone={() => router.replace('/dashboard')} />
    </StepperShell>
  )
}

/** Which step an in-progress engine session resumes to. */
function stepForPhase(state: AgentState): StepId {
  switch (state.phase) {
    case 'analysing':
    case 'brief':
    case 'discovery':
      return 'chat'
    case 'documents':
      return 'documents'
    case 'tools':
      return 'tools'
    case 'persona':
    case 'assembling':
    case 'ready':
      return 'brain'
    default:
      return 'chat'
  }
}
