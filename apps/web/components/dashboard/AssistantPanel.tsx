import type { Assistant } from '@/lib/dashboard-client'

/**
 * The panel P15 reserves and P20 fills. Q67.
 *
 * **Reserved is a design, not a placeholder.** A blank region where a feature
 * is coming reads as a bug; a fake one reads as a lie. So this names the
 * director and lists the questions it will answer — `doc/08` §2E–§8E, in the
 * words a founder would actually type — and says plainly that it is not
 * available yet.
 *
 * The questions come from the API rather than from a list here, because they
 * are per-department and they are specification: *"Why are we shipping late?"*
 * is what the Operations Director is **for**, and a browser inventing a
 * plausible-sounding question would be describing a product nobody built.
 *
 * There is no input box. An input that accepts a question and cannot answer it
 * is worse than none: somebody types the thing they most want to know and gets
 * silence, and the next thing they conclude is that the product does not work.
 */
export function AssistantPanel({ assistant }: { assistant: Assistant }) {
  if (assistant.available) {
    // P20's job. Rendering a chat here before the injection evals are green
    // would be the one shortcut this product cannot take — a tainted turn with
    // an unconfirmed action is the failure the whole boundary exists to stop.
    return null
  }

  return (
    <aside className="mt-8 rounded-2xl border border-ink-100 bg-white px-5 py-5 shadow-paper">
      <p className="font-mono text-2xs uppercase tracking-[0.12em] text-ink-400">
        Ask the {assistant.director}
      </p>
      <ul className="mt-3 flex flex-col gap-2">
        {assistant.questions.map((question) => (
          <li key={question} className="text-[0.95rem] leading-relaxed text-ink-700">
            &ldquo;{question}&rdquo;
          </li>
        ))}
      </ul>
      <p className="mt-4 border-t border-ink-100 pt-3 text-sm leading-relaxed text-ink-500">
        Not available yet. When it is, every answer will cite what it was drawn from, and a
        question outside this department will be refused with the reason rather than answered
        thinly.
      </p>
    </aside>
  )
}
