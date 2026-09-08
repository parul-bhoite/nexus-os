'use client'

import { useCallback, useEffect, useRef, useState } from 'react'

import {
  type StoredDocument,
  type UploadStage,
  listDocuments,
  megabytes,
  readAsks,
  uploadDocument,
} from '@/lib/documents-client'

/**
 * The documents step: three named files per department, and what each unlocks.
 *
 * **Named asks, not a drop zone.** "Upload some documents" gets nothing; "your
 * current price list, a proposal you were proud of, your services one-pager"
 * gets three files, because a person can picture each one and knows where it
 * lives. The asks come from `GET /documents/asks`, chosen from the departments
 * this company actually runs — asking a company with no finance function for
 * its budget is the same mistake as showing it a Finance dashboard.
 *
 * **Every ask says what it turns on, and never what it will find.** The same
 * rule the API's catalogue is written under: "Quoting at your real prices" is a
 * promise kept the moment the file arrives; "you are underpricing by 12%" would
 * be a conclusion invented before anything had been read.
 *
 * **A failed upload is visible and the file is kept.** A scanned PDF with no
 * text layer comes back `422` with a reason — the document is on record, and it
 * is not searchable. Doc 07 M5 requires that to be said out loud, and the reason
 * it matters is the alternative: a customer who believes a file is searchable
 * finds out it is not when an answer omits it, which reads as the product being
 * wrong rather than the upload having failed.
 *
 * **It is skippable, and skipping is a real choice rather than a dead end.**
 * `doc/09` §6.2. What the button must not do is imply otherwise later: a
 * workspace that skipped has no price list, and nothing downstream may pretend
 * it quoted from one.
 */
export function DocumentsStep({
  onContinue,
  disabled,
}: {
  /** `skipped` is a record, not a permission — the server advances either way. */
  onContinue: (skipped: boolean) => void
  disabled: boolean
}) {
  const [stage, setStage] = useState<UploadStage | null>(null)
  const [uploaded, setUploaded] = useState<StoredDocument[]>([])
  /**
   * Files in flight, and files that came back refused, keyed by name.
   *
   * Kept beside `uploaded` rather than merged into it because the two lists
   * come from different places and only one of them is the database. A refusal
   * over the size limit never became a row at all, so it has no `document_id`
   * to key on and would vanish on the next refresh — which is right, and is
   * also why it has to be shown *now*.
   */
  const [busy, setBusy] = useState<string[]>([])
  const [refused, setRefused] = useState<{ filename: string; why: string }[]>([])
  const [error, setError] = useState<string | null>(null)
  const input = useRef<HTMLInputElement>(null)

  const load = useCallback(async () => {
    try {
      const [asks, docs] = await Promise.all([readAsks(), listDocuments()])
      setStage(asks)
      setUploaded(docs)
    } catch (cause) {
      // Not fatal to the step. The asks are the *wording* of a screen whose job
      // is to accept files, and the file input works without them — so a failed
      // fetch loses the three suggestions and not the ability to continue.
      setError(cause instanceof Error ? cause.message : 'Could not load the document list.')
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  const send = useCallback(
    async (files: FileList) => {
      setError(null)
      // A snapshot: `FileList` is live against the input element, and clearing
      // the input below would empty the very list being iterated.
      const chosen = Array.from(files)
      setBusy((prev) => [...prev, ...chosen.map((file) => file.name)])

      for (const file of chosen) {
        // Checked here as well as server-side, and the server's answer is the
        // one that counts. This exists so a person on a slow connection is told
        // about a 40 MB file in the moment rather than after waiting for it to
        // arrive and be refused.
        if (stage && file.size > stage.max_file_bytes) {
          setRefused((prev) => [
            ...prev,
            {
              filename: file.name,
              why: `Over the ${megabytes(stage.max_file_bytes)} limit for one file.`,
            },
          ])
          setBusy((prev) => prev.filter((name) => name !== file.name))
          continue
        }

        try {
          const result = await uploadDocument(file)
          if (result.status !== 'indexed') {
            // Stored, unreadable, and said so. `message` is the parser's own
            // reason — "no text layer", "unsupported type" — because "upload
            // failed" tells somebody nothing they can act on.
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

      // Re-read rather than appending what was just returned: the row carries
      // the status the classifier decided and the count held for review, and
      // those are the server's answers, not the upload response's guesses.
      await load()
      if (input.current) input.current.value = ''
    },
    [load, stage],
  )

  const indexed = uploaded.filter((doc) => doc.status === 'indexed').length
  const held = uploaded.reduce((sum, doc) => sum + doc.chunks_held_for_review, 0)
  const atLimit =
    stage !== null && uploaded.length >= stage.max_files_at_onboarding

  return (
    <div className="rounded-2xl border border-bone-300 bg-white/90 p-4 backdrop-blur-sm">
      <h2 className="font-display text-lg text-ink">Now, a few of your own documents</h2>
      <p className="mt-2 text-sm text-ink-600">
        This is what makes an answer yours rather than generic. Nothing here is required — you can
        add these later, and the workspace will say what is still missing.
      </p>

      {stage?.departments.map((group) => (
        <div key={group.department} className="mt-4">
          <p className="font-mono text-[11px] uppercase tracking-[0.18em] text-ink-400">
            {group.department}
          </p>
          <ul className="mt-1.5 divide-y divide-bone-200">
            {group.asks.map((ask) => (
              <li key={ask.name} className="py-2">
                <p className="text-sm font-medium text-ink">{ask.name}</p>
                {/* What it turns on, never what it will find. */}
                <p className="mt-0.5 text-xs text-ink-400">{ask.unlocks}</p>
              </li>
            ))}
          </ul>
        </div>
      ))}

      {/* The consent warranty, in the API's own words and version. The upload
          sends `consent: true` and the API refuses it without — so this is the
          statement being made rather than a checkbox decorating one. */}
      {stage && (
        <p className="mt-4 border-l-2 border-gold pl-2 text-[11px] leading-snug text-ink-400">
          {stage.consent.text}
        </p>
      )}

      <div className="mt-4 flex flex-wrap items-center gap-3">
        <label
          className={`cursor-pointer rounded-full border border-ink px-5 py-2 text-sm font-medium text-ink ${
            disabled || atLimit ? 'pointer-events-none opacity-50' : 'hover:bg-bone-100'
          }`}
        >
          <input
            ref={input}
            type="file"
            multiple
            className="sr-only"
            disabled={disabled || atLimit}
            onChange={(event) => {
              if (event.target.files?.length) void send(event.target.files)
            }}
          />
          Choose files
        </label>

        {stage && (
          <span className="text-xs text-ink-400">
            Up to {stage.max_files_at_onboarding} files now, {megabytes(stage.max_file_bytes)} each
            {uploaded.length > 0 && ` · ${uploaded.length} added`}
          </span>
        )}
      </div>

      {busy.length > 0 && (
        <p className="mt-3 text-xs text-ink-400" role="status">
          Reading {busy.join(', ')}…
        </p>
      )}

      {uploaded.length > 0 && (
        <ul className="mt-3 divide-y divide-bone-200">
          {uploaded.map((doc) => (
            <li key={doc.document_id} className="flex items-baseline justify-between gap-3 py-2">
              <span className="min-w-0 truncate text-sm text-ink">{doc.filename}</span>
              <span className="shrink-0 text-xs text-ink-400">
                {doc.status === 'indexed'
                  ? doc.page_count
                    ? `${doc.page_count} pages`
                    : 'Read'
                  : /* The row exists and the file is on the disk. What failed is
                       our reading of it, which is what the reason says. */
                    (doc.failure_reason ?? 'Could not be read')}
              </span>
            </li>
          ))}
        </ul>
      )}

      {refused.length > 0 && (
        <div className="mt-3 rounded-lg bg-clay-100 px-3 py-2">
          {refused.map((item, index) => (
            <p key={`${item.filename}-${index}`} className="text-xs text-clay-600">
              <span className="font-medium">{item.filename}</span> — {item.why}
            </p>
          ))}
        </div>
      )}

      {held > 0 && (
        // Said here rather than discovered later. Default-deny classification
        // (I4) withholds a chunk it is unsure about, and a person who is not
        // told will read the gap as the document not having been read at all.
        <p className="mt-3 text-xs text-ink-400">
          {held} passage{held === 1 ? '' : 's'} held for your review — anything sensitive waits for
          you rather than being indexed on a guess.
        </p>
      )}

      {error && (
        <p role="alert" className="mt-3 text-xs text-clay-600">
          {error}
        </p>
      )}

      <div className="mt-4 flex flex-wrap items-center gap-3">
        <button
          type="button"
          disabled={disabled || busy.length > 0}
          onClick={() => onContinue(indexed === 0)}
          className="rounded-full bg-ink px-5 py-2 text-sm font-medium text-bone-50 disabled:opacity-50"
        >
          {indexed > 0 ? 'Continue' : 'Skip for now'}
        </button>
        {indexed > 0 && (
          <button
            type="button"
            disabled={disabled || busy.length > 0}
            onClick={() => onContinue(true)}
            className="text-sm text-ink-400 underline decoration-bone-300 underline-offset-4 hover:text-ink-600 disabled:opacity-50"
          >
            Skip the rest
          </button>
        )}
      </div>
    </div>
  )
}
