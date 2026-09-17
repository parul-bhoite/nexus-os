'use client'

import { useId, type ComponentProps, type ReactNode } from 'react'

/**
 * The form layer: one label style, one control shape, one way to say a field is
 * wrong.
 *
 * ## What the audit found
 *
 * Three form surfaces, three conventions. `/work` labelled fields in
 * sentence-case sans and marked the optional ones `(optional)`, leaving the
 * required ones unmarked — the inverse of what a reader expects, so a field
 * with no marker read as optional. `/settings` labelled the same kind of field
 * in 11px tracked-out uppercase mono at 4.4:1 contrast. And every `<select>`
 * and `<input type="date">` in both was the browser default, rendering in the
 * system font with native chrome beside controls with a 14px radius and a warm
 * border — the single largest source of "this looks unfinished" in the product.
 *
 * So: `Field` owns the label, the hint, the error and the id wiring.
 * `TextInput`, `TextArea` and `Select` own the control's appearance and nothing
 * else. A feature composes them and cannot invent a fourth convention.
 *
 * ## Errors
 *
 * An error replaces the hint rather than stacking under it, is announced via
 * `aria-describedby`, and sets `aria-invalid`. It is **never** communicated by
 * the border alone: a red border is invisible to a colour-blind reader and
 * meaningless to a screen reader.
 *
 * The error does not animate in. A field that shakes or slides while somebody
 * is typing in it moves the caret's neighbourhood at the worst moment; the
 * brief asks for error animation "used sparingly", and inside a form the
 * sparing amount is none.
 */

const control =
  'w-full rounded-control border bg-white text-body text-ink-800 placeholder:text-ink-300 ' +
  'transition-[border-color,box-shadow] duration-base ease-out ' +
  'focus:outline-none focus:ring-2 focus:ring-steel-500 focus:ring-offset-2 focus:ring-offset-white ' +
  'disabled:cursor-not-allowed disabled:bg-bone-100 disabled:text-ink-400'

const rest = 'border-ink-200 hover:border-ink-300'
const wrong = 'border-clay-500 hover:border-clay-600'

function shell(invalid: boolean, extra = '') {
  return `${control} ${invalid ? wrong : rest} ${extra}`
}

/**
 * The label, hint and error around one control.
 *
 * Takes a render function rather than `children` so the generated ids reach
 * the control without the caller having to declare them — the audit found
 * labels on `/login` rendered as `<span>` with `aria-labelledby`, which works
 * for a screen reader but means clicking the word "Password" does not focus the
 * field. A real `<label htmlFor>` does both, and the only way to guarantee one
 * is to own the id here.
 */
export function Field({
  label,
  hint,
  error,
  required,
  optional,
  children,
  className = '',
}: {
  label: ReactNode
  hint?: ReactNode
  error?: string | null
  /** Marks the field required — on the *required* ones, not the optional ones. */
  required?: boolean
  /** For the rare field where "you may leave this blank" is worth saying. */
  optional?: boolean
  children: (props: {
    id: string
    'aria-describedby': string | undefined
    'aria-invalid': true | undefined
    'aria-required': true | undefined
  }) => ReactNode
  className?: string
}) {
  const id = useId()
  const hintId = `${id}-hint`
  const errorId = `${id}-error`
  const describedBy = error ? errorId : hint ? hintId : undefined

  return (
    <div className={`flex flex-col gap-1.5 ${className}`}>
      <label htmlFor={id} className="field-label">
        {label}
        {required ? (
          <span className="ml-1 text-clay-600" aria-hidden="true">
            *
          </span>
        ) : null}
        {optional ? <span className="ml-1.5 font-normal text-ink-400">optional</span> : null}
      </label>

      {children({
        id,
        'aria-describedby': describedBy,
        'aria-invalid': error ? true : undefined,
        'aria-required': required ? true : undefined,
      })}

      {error ? (
        <p id={errorId} className="flex items-start gap-1.5 text-meta text-clay-600">
          <svg viewBox="0 0 16 16" aria-hidden="true" className="mt-0.5 h-3.5 w-3.5 shrink-0">
            <circle cx="8" cy="8" r="7" fill="none" stroke="currentColor" strokeWidth="1.5" />
            <path d="M8 4.75v4M8 11.4v.1" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
          </svg>
          {error}
        </p>
      ) : hint ? (
        <p id={hintId} className="field-hint">
          {hint}
        </p>
      ) : null}
    </div>
  )
}

export function TextInput({
  invalid,
  className = '',
  ...props
}: { invalid?: boolean } & ComponentProps<'input'>) {
  return <input {...props} className={shell(Boolean(invalid), `h-11 px-3.5 ${className}`)} />
}

/**
 * A textarea that grows with its content up to a limit.
 *
 * The onboarding conversation asks "what does the company do?" and offers two
 * rows — so the invited sentence scrolls out of sight as it is typed, inside a
 * box with a resize handle the reader has to find. `rows` is the *minimum*
 * here; `field-sizing: content` grows it where supported and the
 * `min-h`/`max-h` pair bounds it everywhere else.
 */
export function TextArea({
  invalid,
  className = '',
  rows = 3,
  ...props
}: { invalid?: boolean } & ComponentProps<'textarea'>) {
  return (
    <textarea
      {...props}
      rows={rows}
      className={shell(
        Boolean(invalid),
        `min-h-[5.5rem] max-h-64 resize-y px-3.5 py-2.5 leading-relaxed [field-sizing:content] ${className}`,
      )}
    />
  )
}

/**
 * A select that looks like the rest of the product.
 *
 * Still a native `<select>`, deliberately. A custom listbox is a keyboard
 * interaction contract — type-ahead, Home/End, PageUp, the mobile wheel — that
 * takes a lot of code to get right and is worse than the platform's until it
 * is. What was actually wrong was the *appearance*: the default arrow and the
 * system font. `appearance-none` plus one inline chevron fixes that and keeps
 * every behaviour the platform already gets right.
 */
export function Select({
  invalid,
  className = '',
  children,
  ...props
}: { invalid?: boolean } & ComponentProps<'select'>) {
  return (
    <div className="relative">
      <select
        {...props}
        className={shell(
          Boolean(invalid),
          `h-11 cursor-pointer appearance-none pl-3.5 pr-10 ${className}`,
        )}
      >
        {children}
      </select>
      <svg
        viewBox="0 0 16 16"
        fill="none"
        aria-hidden="true"
        className="pointer-events-none absolute right-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-400"
      >
        <path d="m4 6.5 4 4 4-4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    </div>
  )
}

/**
 * A date input, styled to match and with the native picker kept.
 *
 * `::-webkit-calendar-picker-indicator` is restyled rather than hidden: hiding
 * it leaves a text field that silently demands `dd/mm/yyyy`, and the audit's
 * note about a product built for Oman is exactly why that matters — the
 * placeholder order is locale-dependent and the picker is not.
 */
export function DateInput({
  invalid,
  className = '',
  ...props
}: { invalid?: boolean } & ComponentProps<'input'>) {
  return (
    <input
      {...props}
      type="date"
      className={shell(
        Boolean(invalid),
        'h-11 px-3.5 [&::-webkit-calendar-picker-indicator]:cursor-pointer ' +
          `[&::-webkit-calendar-picker-indicator]:opacity-50 [&::-webkit-calendar-picker-indicator]:hover:opacity-100 ${className}`,
      )}
    />
  )
}

/**
 * A checkbox with its label as one target.
 *
 * The whole row is the hit area — `/settings` rendered a 16px native checkbox
 * beside unassociated text, which is a 16px target next to the words that
 * describe it. This is 44px tall including the label.
 */
export function Checkbox({
  label,
  hint,
  className = '',
  ...props
}: { label: ReactNode; hint?: ReactNode } & ComponentProps<'input'>) {
  const id = useId()
  const hintId = `${id}-hint`

  return (
    <div className={`flex items-start gap-3 ${className}`}>
      <input
        {...props}
        id={id}
        type="checkbox"
        aria-describedby={hint ? hintId : undefined}
        className="mt-0.5 h-[1.15rem] w-[1.15rem] shrink-0 cursor-pointer rounded-[0.3rem] border-ink-300 text-ink-800 transition-colors duration-micro ease-out accent-ink-800 focus-visible:ring-2 focus-visible:ring-steel-500 focus-visible:ring-offset-2"
      />
      <label htmlFor={id} className="cursor-pointer text-body leading-snug text-ink-700">
        {label}
        {hint ? (
          <span id={hintId} className="mt-0.5 block text-meta text-ink-500">
            {hint}
          </span>
        ) : null}
      </label>
    </div>
  )
}

/**
 * A fieldset of radios rendered as selectable cards.
 *
 * Used by domain verification, where each option carries a sentence explaining
 * what it costs the reader. A bare radio with that sentence beside it makes the
 * sentence unclickable; making the card the target means the explanation is
 * part of the choice rather than a footnote to it.
 */
export function RadioCards<T extends string>({
  name,
  legend,
  value,
  onChange,
  options,
  className = '',
}: {
  name: string
  legend: ReactNode
  value: T
  onChange: (next: T) => void
  options: { value: T; label: ReactNode; hint?: ReactNode }[]
  className?: string
}) {
  return (
    <fieldset className={className}>
      <legend className="field-label mb-2">{legend}</legend>
      <div className="flex flex-col gap-2">
        {options.map((option) => {
          const checked = option.value === value
          return (
            <label
              key={option.value}
              className={`flex cursor-pointer items-start gap-3 rounded-control border px-3.5 py-3 transition-[background-color,border-color] duration-base ease-out ${
                checked
                  ? 'border-ink-300 bg-white shadow-e1'
                  : 'border-ink-100 bg-white/40 hover:border-ink-200 hover:bg-white'
              }`}
            >
              <input
                type="radio"
                name={name}
                value={option.value}
                checked={checked}
                onChange={() => onChange(option.value)}
                className="mt-0.5 h-[1.15rem] w-[1.15rem] shrink-0 cursor-pointer accent-ink-800 focus-visible:ring-2 focus-visible:ring-steel-500 focus-visible:ring-offset-2"
              />
              <span className="text-body leading-snug text-ink-700">
                <span className="font-medium text-ink-800">{option.label}</span>
                {option.hint ? (
                  <span className="mt-0.5 block text-meta text-ink-500">{option.hint}</span>
                ) : null}
              </span>
            </label>
          )
        })}
      </div>
    </fieldset>
  )
}

/**
 * The form's own error, above its submit.
 *
 * `role="alert"` so it is announced the moment it appears — a submission that
 * failed is exactly the case where the reader's attention is elsewhere, on the
 * button they just pressed.
 */
export function FormError({ children }: { children: ReactNode }) {
  if (!children) return null
  return (
    <p
      role="alert"
      className="flex items-start gap-2 rounded-control border border-clay-300 bg-clay-100 px-3.5 py-2.5 text-meta leading-relaxed text-clay-600"
    >
      <svg viewBox="0 0 16 16" aria-hidden="true" className="mt-px h-4 w-4 shrink-0">
        <circle cx="8" cy="8" r="7" fill="none" stroke="currentColor" strokeWidth="1.5" />
        <path d="M8 4.75v4M8 11.4v.1" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
      </svg>
      {children}
    </p>
  )
}
