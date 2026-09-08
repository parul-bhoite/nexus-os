'use client'

import { useCallback, useEffect, useRef, useState } from 'react'

/**
 * Speaking an answer instead of typing one.
 *
 * Onboarding asks a person to describe their own job in prose — the longest
 * free-text answers in the product, given by people who are often not at a
 * keyboard when they have the answer. Dictation is the cheapest way to make
 * those answers longer and truer, and a longer answer here is the whole input
 * to the Brain.
 *
 * **The browser does the transcription.** `SpeechRecognition` is a platform
 * API: the audio goes wherever the browser sends it, no audio reaches this
 * product's servers, and nothing is recorded to disk. That is the reason to
 * prefer it over uploading a blob to an ASR endpoint — the alternative would
 * put a recording of somebody's voice into a system whose entire premise is
 * that you can see what it stored about you.
 *
 * **It is an accessory, never the only way in.** `supported` is false on
 * Firefox and on any browser without the vendor-prefixed constructor, and the
 * button is simply not rendered there. The textarea is untouched either way, so
 * a failure of this hook costs a person nothing but the microphone.
 *
 * Interim results are surfaced separately from final ones rather than being
 * written into the draft as they arrive. Interim text is rewritten in place by
 * the recogniser as it changes its mind; splicing that into a controlled
 * textarea makes the caret jump and eats anything typed alongside it. Final
 * transcripts are appended once and are stable.
 */

type Recognition = {
  lang: string
  continuous: boolean
  interimResults: boolean
  start: () => void
  stop: () => void
  abort: () => void
  onresult: ((event: SpeechRecognitionEventLike) => void) | null
  onerror: ((event: { error?: string }) => void) | null
  onend: (() => void) | null
}

type SpeechRecognitionEventLike = {
  resultIndex: number
  results: ArrayLike<ArrayLike<{ transcript: string }> & { isFinal: boolean }>
}

type RecognitionConstructor = new () => Recognition

function constructorFor(): RecognitionConstructor | null {
  if (typeof window === 'undefined') return null
  const scope = window as unknown as {
    SpeechRecognition?: RecognitionConstructor
    webkitSpeechRecognition?: RecognitionConstructor
  }
  return scope.SpeechRecognition ?? scope.webkitSpeechRecognition ?? null
}

export type Dictation = {
  /** Whether this browser has the API at all. False hides the button entirely. */
  supported: boolean
  listening: boolean
  /** Words the recogniser has not committed to yet. Shown, never stored. */
  interim: string
  /** Denied permission, no microphone, or a recogniser fault. Shown once. */
  error: string | null
  start: () => void
  stop: () => void
  toggle: () => void
}

/**
 * @param onTranscript called with each finalised phrase, in order.
 */
export function useDictation(onTranscript: (text: string) => void): Dictation {
  const [supported, setSupported] = useState(false)
  const [listening, setListening] = useState(false)
  const [interim, setInterim] = useState('')
  const [error, setError] = useState<string | null>(null)
  const recognition = useRef<Recognition | null>(null)

  // Held in a ref so the effect below can stay keyed on nothing and the
  // recogniser is built exactly once. A callback identity that changes every
  // render would otherwise tear down and rebuild the recogniser mid-sentence.
  const sink = useRef(onTranscript)
  sink.current = onTranscript

  useEffect(() => {
    const Ctor = constructorFor()
    // Detected at run time rather than assumed: this is the one API in the
    // product that a mainstream desktop browser simply does not have.
    if (!Ctor) return
    setSupported(true)

    const engine = new Ctor()
    // `navigator.language`, not a hardcoded locale. Onboarding already asks
    // which language the workspace writes in, and a recogniser pinned to en-US
    // transcribes a Dutch founder into confident nonsense.
    engine.lang = typeof navigator !== 'undefined' ? navigator.language || 'en-US' : 'en-US'
    engine.continuous = true
    engine.interimResults = true

    engine.onresult = (event) => {
      let pending = ''
      for (let index = event.resultIndex; index < event.results.length; index += 1) {
        const result = event.results[index]
        const text = result[0]?.transcript ?? ''
        if (result.isFinal) sink.current(text.trim())
        else pending += text
      }
      setInterim(pending)
    }

    engine.onerror = (event) => {
      // `aborted` and `no-speech` are what a normal stop and a normal pause
      // look like. Surfacing either as an error would put a red line on screen
      // every time somebody thinks for a moment.
      const code = event.error ?? ''
      if (code === 'aborted' || code === 'no-speech') return
      setError(
        code === 'not-allowed' || code === 'service-not-allowed'
          ? 'The microphone is blocked. Allow it in your browser, or just type.'
          : 'The microphone stopped. You can type the answer instead.',
      )
      setListening(false)
    }

    engine.onend = () => {
      setListening(false)
      setInterim('')
    }

    recognition.current = engine
    return () => {
      engine.onresult = null
      engine.onerror = null
      engine.onend = null
      engine.abort()
      recognition.current = null
    }
  }, [])

  const start = useCallback(() => {
    const engine = recognition.current
    if (!engine) return
    setError(null)
    try {
      engine.start()
      setListening(true)
    } catch {
      // `start` on an already-running recogniser throws `InvalidStateError`.
      // Double-clicking the button is not worth an error message.
    }
  }, [])

  const stop = useCallback(() => {
    recognition.current?.stop()
    setListening(false)
    setInterim('')
  }, [])

  const toggle = useCallback(() => {
    if (listening) stop()
    else start()
  }, [listening, start, stop])

  return { supported, listening, interim, error, start, stop, toggle }
}
