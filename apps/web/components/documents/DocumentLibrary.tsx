'use client'

import Link from 'next/link'
import { useCallback, useEffect, useRef, useState } from 'react'
import { Button } from '@/components/ui/Button'
import { Empty, Failed } from '@/components/ui/States'
import { Waiting } from '@/components/ui/Waiting'
import {
  type StoredDocument,
  type UploadStage,
  listDocuments,
  megabytes,
  readAsks,
  requestDownload,
  uploadDocument,
} from '@/lib/documents-client'

/**
 * Documents, after onboarding.
 *
 * `DocumentsStep` uploads during setup and is the right shape for that: asks
 * grouped by department, and a Skip button, because at that point the question
 * is *what would help NEXUS understand you* and the honest answer may be "not
 * now". Neither belongs here. By the time somebody comes looking for this
 * screen they have a workspace and a reason, and what they need is the state of
 * what they have already sent.
 *
 * **The limit and the 422 are not re-implemented.** `uploadDocument` owns the
 * parse-failure case — a stored-but-unreadable file returns rather than throws,
 * because the row exists and the reason is the useful part — and
 * `stage.max_file_bytes` is the server's number, formatted by the shared
 * `megabytes`. Two implementations of one limit is how a client says fine and
 * the server says too big; that lesson is already written into
 * `app/documents/limits.py` and this screen does not relearn it.
 *
 * What *is* written twice is about fifteen lines of in-flight state, kept
 * separate on purpose rather than abstracted with the onboarding step: the two
 * screens agree on the mechanics and differ on everything a person sees, and a
 * shared component parameterised by both would be harder to read than either.
 */

const REFUSED_BY_THE_BROWSER = 'This file is larger than the workspace allows, so it was not sent.'

function statusOf(document: StoredDocument): { label: string; tone: string } {
  if (document.failure_reason) return { label: 'unreadable', tone: 'bg-clay-100 text-clay-600' }
  if (document.chunks_held_for_review > 0)
    return { label: 'awaiting review', tone: 'bg-gold-200 text-gold-700' }
  return { label: document.status, tone: 'bg-bone-200 text-ink-500' }
}

export function DocumentLibrary() {
  const [stage, setStage] = useState<UploadStage | null>(null)
  const [documents, setDocuments] = useState<StoredDocument[]>([])
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState<string[]>([])
  /** Refusals that never became rows — a file over the limit has no
   *  `document_id`, so it would vanish on the next read. Shown now or not at
   *  all. */
  const [refused, setRefused] = useState<{ filename: string; why: string }[]>([])
  /** A download that could not be minted, against the row it belongs to. */
  const [unavailable, setUnavailable] = useState<Record<string, string>>({})
  const input = useRef<HTMLInputElement>(null)

  const load = useCallback(async () => {
    setError(null)
    try {
      const [asks, stored] = await Promise.all([readAsks(), listDocuments()])
      setStage(asks)
      setDocuments(stored)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not load your documents.')
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  const send = useCallback(
    async (files: FileList) => {
      if (stage === null) return
      setRefused([])

      for (const file of Array.from(files)) {
        if (file.size > stage.max_file_bytes) {
          setRefused((prev) => [...prev, { filename: file.name, why: REFUSED_BY_THE_BROWSER }])
          continue
        }
        setBusy((prev) => [...prev, file.name])
        try {
          const result = await uploadDocument(file)
          if (result.status !== 'indexed') {
            // Stored and unreadable. `message` is the parser's own reason, and
            // it is the only part anybody can act on.
            setRefused((prev) => [...prev, { filename: result.filename, why: result.message }])
          }
        } catch (cause) {
          setRefused((prev) => [
            ...prev,
            {
              filename: file.name,
              why: cause instanceof Error ? cause.message : 'That upload failed.',
            },
          ])
        } finally {
          setBusy((prev) => prev.filter((name) => name !== file.name))
        }
      }

      // Re-read rather than appending the upload's own response: the row
      // carries what the classifier decided and how much it withheld, and those
      // are the server's answers rather than this screen's guesses.
      await load()
      if (input.current) input.current.value = ''
    },
    [load, stage],
  )

  async function download(document: StoredDocument) {
    setUnavailable((prev) => {
      const next = { ...prev }
      delete next[document.document_id]
      return next
    })
    try {
      const signed = await requestDownload(document.document_id)
      // A plain navigation, because the response carries
      // `Content-Disposition: attachment` — the browser saves it and stays put.
      // Fetching the bytes here to build a blob would hold a 25 MB document in
      // the tab for no gain, and would lose the filename the server sets.
      window.location.assign(signed.url)
    } catch (cause) {
      setUnavailable((prev) => ({
        ...prev,
        [document.document_id]:
          cause instanceof Error ? cause.message : 'That download could not be prepared.',
      }))
    }
  }

  // F-15: `send()` re-reads the library with `load()` after every upload, and
  // `load()` can fail on that *re*-read exactly as it can on the first one.
  // This used to be one `if (error !== null)` gating the entire component, so
  // a reload that failed after a successful upload replaced the whole screen
  // with `Failed` — discarding `refused`, the one thing telling the reader
  // which of the files they just picked actually made it. Only a failure with
  // nothing loaded yet takes over the whole view now; a failure with `stage`
  // already in hand renders above the library instead, next to `refused`.
  if (error !== null && stage === null) {
    return (
      <Failed title="Your documents did not load" retry={() => void load()}>
        {error}
      </Failed>
    )
  }

  if (stage === null) {
    return <Waiting>Loading what you have already sent.</Waiting>
  }

  const held = documents.reduce((total, d) => total + d.chunks_held_for_review, 0)

  return (
    <div className="flex flex-col gap-5">
      {error !== null ? (
        <Failed title="Could not refresh your documents" retry={() => void load()}>
          {error}
        </Failed>
      ) : null}
      <div className="rounded-2xl border border-bone-300 bg-white/90 p-5">
        <label
          htmlFor="document-upload"
          className="font-mono text-2xs uppercase tracking-[0.16em] text-ink-400"
        >
          Add a document
        </label>
        <input
          id="document-upload"
          ref={input}
          type="file"
          multiple
          disabled={busy.length > 0}
          onChange={(event) => {
            if (event.target.files && event.target.files.length > 0) void send(event.target.files)
          }}
          className="mt-2 block w-full text-sm text-ink-600 file:mr-3 file:rounded-full file:border file:border-bone-300 file:bg-bone-100 file:px-4 file:py-1.5 file:text-sm file:text-ink-700 hover:file:bg-bone-200"
        />
        <p className="mt-2.5 text-xs leading-relaxed text-ink-400">
          Up to {megabytes(stage.max_file_bytes)} each. Uploading is a warranty that you are
          entitled to share the file with your workspace — {stage.consent.text}
        </p>
        {/* The quota is shared across the workspace and the API already sends
            it. Saying it here rather than only in a refusal means the limit is
            knowable before somebody hits it — and it is stated as used-of-total
            rather than as a percentage, because a bar implies a proportion of
            something finished and this is a ceiling. */}
        <p className="mt-1 font-mono text-2xs text-ink-400">
          {megabytes(stage.bytes_used)} of {megabytes(stage.workspace_quota_bytes)} used across the
          workspace
        </p>
        {busy.length > 0 && (
          <p className="mt-2 font-mono text-2xs text-ink-400">Sending {busy.join(', ')}…</p>
        )}
      </div>

      {refused.length > 0 && (
        <ul role="alert" className="flex flex-col gap-2">
          {refused.map((item) => (
            <li
              key={`${item.filename}-${item.why}`}
              className="rounded-xl bg-clay-100 px-4 py-2.5 text-sm text-clay-600"
            >
              <span className="font-medium">{item.filename}</span> — {item.why}
            </li>
          ))}
        </ul>
      )}

      {held > 0 && (
        <p className="rounded-xl border border-gold-300 bg-gold-100 px-4 py-2.5 text-sm text-ink-700">
          {held} {held === 1 ? 'passage is' : 'passages are'} withheld until someone places{' '}
          {held === 1 ? 'it' : 'them'}.{' '}
          <Link href="/review-queue" className="underline decoration-gold-500 underline-offset-2">
            Review them
          </Link>
          .
        </p>
      )}

      {documents.length === 0 ? (
        <Empty title="You have not sent anything yet" action={null}>
          A price list, a proposal, a policy — whatever NEXUS would otherwise have to ask you to
          retype. Nothing is readable by your workspace until the classifier places it, and
          anything it will not place waits for a person.
        </Empty>
      ) : (
        <ul className="flex flex-col gap-2">
          {documents.map((document) => {
            const status = statusOf(document)
            return (
              <li
                key={document.document_id}
                // The anchor an assistant citation lands on. Without it a
                // citation is decoration — which is the one thing the answer's
                // sources must not be.
                id={`doc-${document.document_id}`}
                className="flex flex-wrap items-center gap-x-3 gap-y-1 scroll-mt-24 rounded-xl border border-bone-300 bg-white/90 px-4 py-3 target:border-gold-500 target:bg-gold-100"
              >
                <span className="text-sm font-medium text-ink-800">{document.filename}</span>
                <span
                  className={`rounded-md px-1.5 py-0.5 font-mono text-2xs uppercase tracking-[0.12em] ${status.tone}`}
                >
                  {status.label}
                </span>
                {document.page_count !== null && (
                  <span className="font-mono text-2xs text-ink-400">
                    {document.page_count} {document.page_count === 1 ? 'page' : 'pages'}
                  </span>
                )}
                {/* Offered for an unreadable file too: a scan with no text
                    layer is exactly the one somebody needs back to check what
                    they sent. */}
                <button
                  type="button"
                  onClick={() => void download(document)}
                  className="ml-auto rounded-full border border-bone-300 px-3 py-1 text-xs text-ink-600 hover:bg-bone-100"
                >
                  Download
                </button>
                {document.failure_reason && (
                  <span className="w-full text-xs leading-relaxed text-clay-600">
                    {document.failure_reason}
                  </span>
                )}
                {unavailable[document.document_id] && (
                  <span role="alert" className="w-full text-xs leading-relaxed text-clay-600">
                    {unavailable[document.document_id]}
                  </span>
                )}
              </li>
            )
          })}
        </ul>
      )}
    </div>
  )
}
