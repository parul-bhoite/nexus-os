import { redirect } from 'next/navigation'

export const dynamic = 'force-dynamic'

/**
 * The old questionnaire lived here. The guided conversation replaced it.
 *
 * A redirect rather than a deletion, because this path is in bookmarks and in
 * at least one email template — a 404 would strand somebody mid-signup with no
 * way to tell that the flow had moved rather than broken.
 */
export default function Page() {
  redirect('/onboarding/agent')
}
