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
 * Somebody saying an entity's list is all of it — ADR 0035 (D29).
 *
 * The one fact the database cannot hold about itself: every project row is
 * evidence a project exists, and nothing in the table is evidence that no other
 * project does.
 */
export type Confirmation = {
  entity: string
  /** The date the claim is about. */
  complete_as_of: string
  /** The day it was made. Separate, because somebody catching up on Monday can
   *  honestly vouch for Friday. */
  confirmed_on: string
}

/**
 * What this workspace has recorded.
 *
 * `recorded_at` is empty exactly when nothing has ever been recorded — the
 * state that leaves the tiles locked, and **not** the same as a workspace with
 * everything marked done.
 *
 * `completeness` lists only the entities somebody has vouched for. An entity
 * nobody has confirmed is **absent**, not null: the empty state is ordinary and
 * a null entry invites a client to render "not confirmed: null".
 */
export type Ops = {
  projects: Project[]
  tasks: Task[]
  completeness: Confirmation[]
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

/**
 * Record that an entity's list is all of them — `doc/15` S10.2.
 *
 * Every call appends; nothing is replaced. The question is asked again as the
 * business changes, and when somebody last vouched for the record is exactly
 * what a reader of a rate needs.
 */
export function confirmComplete(entity: string, completeAsOf: string | null): Promise<Confirmation> {
  return send<Confirmation>(
    '/ops/completeness',
    { method: 'POST', body: JSON.stringify({ entity, complete_as_of: completeAsOf }) },
    'Could not record that confirmation.',
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
