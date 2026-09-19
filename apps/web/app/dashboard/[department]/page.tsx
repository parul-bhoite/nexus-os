import type { Metadata } from 'next'
import { notFound } from 'next/navigation'
import { DirectorPage } from '@/components/dashboard/DirectorPage'
import { departmentLabel } from '@/lib/onboarding-client'

/** The seven department keys, mirroring `Department` in `app/domain/scopes.py`. */
const DEPARTMENTS = [
  'marketing',
  'sales',
  'finance',
  'operations',
  'hr',
  'strategy',
  'executive',
] as const

export function generateStaticParams() {
  return DEPARTMENTS.map((department) => ({ department }))
}

// A static `metadata` literal here always read "Dashboard", whichever of the
// seven directors was actually open — every tab in a founder's browser looked
// the same. `params.department` is only known per-request, so it takes the
// async form.
export function generateMetadata({ params }: { params: { department: string } }): Metadata {
  return {
    title: DEPARTMENTS.includes(params.department as (typeof DEPARTMENTS)[number])
      ? departmentLabel(params.department)
      : 'Dashboard',
    robots: { index: false, follow: false },
  }
}

/**
 * One director's page.
 *
 * The department in the URL is checked against the known seven here, which
 * decides only whether a *page* exists. Whether this caller may see it is
 * decided by the API — a department they do not hold answers 404 there, and the
 * page renders that rather than assuming its own check was enough.
 */
export default function DepartmentDashboardPage({
  params,
}: {
  params: { department: string }
}) {
  if (!DEPARTMENTS.includes(params.department as (typeof DEPARTMENTS)[number])) {
    notFound()
  }

  return <DirectorPage department={params.department} />
}
