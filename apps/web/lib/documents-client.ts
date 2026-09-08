import { messageFrom } from '@/lib/api-error'
import { AuthError, csrfToken } from '@/lib/auth-client'

/**
 * Browser-side calls for document upload.
 *
 * Like every other client here these go to this app's own `/api/*` routes
 * rather than to the API directly — the session cookie is `httponly` and
 * `SameSite=Lax`, and both only hold while the request is first-party.
 *
 * **Nothing in this file decides what is stored.** The asks come from the
 * server, the consent wording comes from the server, the limits come from the
 * server and are re-checked there, and the sensitivity every chunk lands at is
 * decided by the classifier. What this file does is put a file on a wire and
 * report honestly what came back — which, for a document, includes the case
 * where the file was kept and could not be read.
 */

export type DocumentAsk = {
  name: string
  /** What NEXUS can do once it has this. A capability, never a finding. */
  unlocks: string
}

export type DepartmentAsks = {
  department: string
  asks: DocumentAsk[]
}

export type UploadStage = {
  /**
   * The warranty text, and the version it is recorded under.
   *
   * Rendered from here rather than written into the component. What a customer
   * consented to is a question about the wording in force at the time, and a
   * second copy in TypeScript would be a second answer to it.
   */
  consent: { text: string; version: string }
  departments: DepartmentAsks[]
  max_file_bytes: number
  max_files_at_onboarding: number
  workspace_quota_bytes: number
  bytes_used: number
  files_uploaded: number
}

/**
 * What one upload produced.
 *
 * `status` is `indexed` or `failed`, and the distinction is the whole point of
 * the type: a file that could not be parsed is **kept** — it is the customer's
 * file and our parser is what failed — and it is not searchable. A client that
 * showed every accepted response as success would tell somebody their scanned
 * PDF was readable, and they would find out when an answer omitted it.
 */
export type Uploaded = {
  document_id: string
  filename: string
  status: string
  chunks_indexed: number
  chunks_held_for_review: number
  page_count: number | null
  /** Empty on success. Never empty on failure. */
  message: string
}

export type StoredDocument = {
  document_id: string
  filename: string
  status: string
  page_count: number | null
  failure_reason: string | null
  created_at: string
  chunks_held_for_review: number
}

async function call<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = {}
  const token = csrfToken()
  if (token) headers['X-CSRF-Token'] = token

  const response = await fetch(path, { ...init, headers, credentials: 'same-origin' })
  if (response.ok) return (await response.json()) as T

  const payload = await response.json().catch(() => null)
  throw new AuthError(
    messageFrom(payload, `The request failed (${response.status}).`),
    response.status,
    payload?.detail,
  )
}

export function readAsks(): Promise<UploadStage> {
  return call<UploadStage>('/api/documents/asks')
}

export function listDocuments(): Promise<StoredDocument[]> {
  return call<StoredDocument[]>('/api/documents')
}

/**
 * Upload one file, with its consent warranty.
 *
 * **`Content-Type` is deliberately not set.** The browser generates it with the
 * multipart boundary when handed a `FormData`; writing one here produces a
 * boundary that does not match the body, and the API reads the whole request as
 * a single unnamed blob.
 *
 * **A 422 is not thrown.** It is the response for a file that was stored and
 * could not be parsed — a scanned PDF with no text layer, a corrupt file — and
 * the body carries the document id and the reason. Throwing would discard both
 * and leave the screen saying "the request failed" about a document that is on
 * record; returning it lets the list show the file with what went wrong beside
 * it, which is what doc 07 M5 requires. Every other non-2xx still throws.
 */
export async function uploadDocument(file: File): Promise<Uploaded> {
  const body = new FormData()
  body.append('file', file)
  // Sent as a form field rather than implied by the request. An upload that
  // consents by virtue of being an upload is not a warranty anyone could rely
  // on — and the API refuses it outright, which is the honest arrangement.
  body.append('consent', 'true')

  const headers: Record<string, string> = {}
  const token = csrfToken()
  if (token) headers['X-CSRF-Token'] = token

  const response = await fetch('/api/documents', {
    method: 'POST',
    headers,
    body,
    credentials: 'same-origin',
  })

  const payload = await response.json().catch(() => null)
  if (response.ok || response.status === 422) {
    return payload as Uploaded
  }
  throw new AuthError(
    messageFrom(payload, `That upload failed (${response.status}).`),
    response.status,
    payload?.detail,
  )
}

/**
 * A byte count as a person would say it.
 *
 * **1024², not 1,000,000.** `app/documents/limits.py` defines `MB` as
 * `1024 * 1024` and phrases its own refusal as "This file is over 25 MB", so
 * dividing by a million here would put "over the 26 MB limit" on the screen
 * beside a server that says 25 about the same file. That module's docstring
 * names this exact failure: two implementations of one limit is how a client
 * says fine and the server says too big.
 */
export function megabytes(bytes: number): string {
  const mb = bytes / (1024 * 1024)
  return mb >= 10 ? `${Math.round(mb)} MB` : `${mb.toFixed(1)} MB`
}
