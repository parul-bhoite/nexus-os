import type { Metadata } from 'next'
import Link from 'next/link'
import { Suspense } from 'react'
import { AuthShell } from '@/components/auth/AuthShell'
import { LoginForm } from '@/components/auth/LoginForm'

export const metadata: Metadata = {
  title: 'Sign in',
  // Auth pages have no business in search results.
  robots: { index: false, follow: false },
}

export default function LoginPage() {
  return (
    <AuthShell
      title="Sign in"
      intro="Welcome back. Your workspace and everything in it stays exactly where you left it."
      footer={
        <p>
          No account yet?{' '}
          <Link
            href="/register"
            className="font-medium text-ink-900 underline decoration-gold-400 underline-offset-2 hover:decoration-gold-500"
          >
            Create one
          </Link>
          .
        </p>
      }
    >
      {/* `useSearchParams` reads the post-reset flag; without this boundary
          `next build` fails the route with a prerender error. */}
      <Suspense fallback={null}>
        <LoginForm />
      </Suspense>
    </AuthShell>
  )
}
