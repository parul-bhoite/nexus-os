import type { Metadata } from 'next'
import Link from 'next/link'
import { AuthShell } from '@/components/auth/AuthShell'
import { RegisterForm } from '@/components/auth/RegisterForm'

export const metadata: Metadata = {
  title: 'Create your account',
  robots: { index: false, follow: false },
}

export default function RegisterPage() {
  return (
    <AuthShell
      title="Create your account"
      // Both lines here were wrong, and each was retired by a different phase.
      //
      // The intro said claiming the domain is "what creates the workspace".
      // That was true until D19 (P5) split them: registering creates the
      // company, and verification gates inviting and connecting instead. A new
      // user was being told the wrong order of the flow they were standing in.
      //
      // The footer offered a free audit needing no account. Phase 2 retired
      // that endpoint — this was the third place it survived, after
      // `AccountPanel` and `FinalCta`.
      intro="One account per person. Next you will create your company — that takes one step, and you can start straight away."
      footer={
        <p>
          Already have an account?{' '}
          <Link
            href="/login"
            className="font-medium text-ink-900 underline decoration-gold-400 underline-offset-2 hover:decoration-gold-500"
          >
            Sign in
          </Link>
          .
        </p>
      }
    >
      <RegisterForm />
    </AuthShell>
  )
}
