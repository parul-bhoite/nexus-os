import { messageFrom } from '@/lib/api-error'
import { AuthError, csrfToken } from '@/lib/auth-client'

/**
 * Recording work — `doc/15` S10.1.
 *
 * **The first client in this app that writes a customer's own records.** Every
 * other call reads something we fetched or computed; these send rows a founder
 * typed and expect them back.
 *
 * One consequence worth stating: **no permission rule is duplicated here.**
 * Whether this caller may record work is `routes/ops._may_write`'s decision,
 * and it arrives as a 403 carrying a sentence written for a person. A client
 * that pre-hid the form would be a second copy of the rule, free to disagree
 * with the first — and the copy that disagrees silently is always the one on
 * the screen.
 */

export type Project = {
  id: string
  name: string
  status: string
  client: string | null
  due_on: string | null
}

export type Task = {
  id: string
  project_id: string | null
  title: string
  status: string
  assignee_id: string | null
  due_on: string | null
}

/**
 * What this workspace has recorded.
 *
 * `recorded_at` is empty exactly when nothing has ever been recorded — the
 * state that leaves the tiles locked, and **not** the same as a workspace with
 * everything marked done.
 */
export type Ops = {
  projects: Project[]
  tasks: Task[]
  recorded_at: string
}

export const PROJECT_STATUSES = ['planned', 'active', 'blocked', 'done'] as const
export const TASK_STATUSES = ['todo', 'doing', 'done'] as const

async function send<T>(path: string, init: RequestInit, fallback: string): Promise<T> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  const token = csrfToken()
  if (token) headers['X-CSRF-Token'] = token

  const response = await fetch(`/api${path}`, {
    ...init,
    headers,
    credentials: 'same-origin',
    cache: 'no-store',
  })

  // 204 on archive. `.json()` on an empty body throws, and the catch would then
  // report a parse failure for a request that succeeded.
  if (response.status === 204) return null as T

  const payload = await response.json().catch(() => null)
  if (!response.ok) {
    throw new AuthError(messageFrom(payload, fallback), response.status)
  }
  return payload as T
}

export function fetchOps(): Promise<Ops> {
  return send<Ops>('/ops', { method: 'GET' }, 'Could not read what you have recorded.')
}

export function createProject(body: {
  name: string
  status: string
  client: string | null
  due_on: string | null
}): Promise<Project> {
  return send<Project>(
    '/ops/projects',
    { method: 'POST', body: JSON.stringify(body) },
    'Could not record that project.',
  )
}

export function createTask(body: {
  title: string
  status: string
  project_id: string | null
  due_on: string | null
}): Promise<Task> {
  return send<Task>(
    '/ops/tasks',
    { method: 'POST', body: JSON.stringify(body) },
    'Could not record that task.',
  )
}

/** Archive, never delete. A row somebody put away stops counting without
 *  ceasing to exist, so a mis-click is recoverable in the database. */
export function archiveProject(id: string): Promise<void> {
  return send<void>(
    `/ops/projects/${encodeURIComponent(id)}`,
    { method: 'DELETE' },
    'Could not archive that project.',
  )
}

export function archiveTask(id: string): Promise<void> {
  return send<void>(
    `/ops/tasks/${encodeURIComponent(id)}`,
    { method: 'DELETE' },
    'Could not archive that task.',
  )
}
