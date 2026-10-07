# 0078. Password strength: 8-character minimum plus composition rules

- **Status:** Proposed
- **Date:** 2026-10-08
- **Deciders:** @parul

## Context

Account passwords were validated at **minimum 12 characters, no composition
rules** — a length-only policy, enforced in `services/api/app/auth/passwords.py`
and mirrored in the browser by `apps/web/lib/auth-client.ts` so the sign-up and
reset forms could warn before the round trip.

A product request asked to lower the floor to **8 characters** and add two
composition rules: **at least one capital letter and at least one number.** The
motivation is sign-up friction — 12 characters with no guidance reads as a high
bar to a founder creating their first account.

The constraint worth stating plainly: current security guidance (NIST SP
800-63B) favours **length over composition**. Composition rules push users toward
predictable substitutions (`Password1`) and do not add the entropy their presence
implies. So this is a usability-vs-strength trade, not a strict improvement, and
it is being made with eyes open.

## Options considered

### A. 8-char minimum + require one capital + one number
Lower length floor, two composition rules. Lower friction; a weaker theoretical
minimum (`Abcdefg1` now passes); composition rules are easy to explain on the
form.

### B. Keep 12-char minimum, no composition rules
The status quo. Strongest minimum by the length-over-composition reasoning; the
highest sign-up friction and no inline guidance on *what* makes a password
acceptable beyond length.

### C. 8-char minimum, no composition rules, nudge toward a passphrase
Lowest friction and avoids the composition-rule trap, but an 8-char lowercase
password with no other rule is a genuinely weak floor, and "a passphrase beats a
short complicated one" is advice, not enforcement.

## Decision

Option A. The minimum is 8 characters and the password must contain at least one
uppercase letter and at least one digit. The rule is enforced server-side in
`validate_password` (the authority) and mirrored client-side by a shared
`passwordProblem()` helper so the forms fail first. The 1024-character upper
bound (an argon2 memory-cost DoS guard) is unchanged.

## Reasoning

Option A was chosen for reduced sign-up friction with a visible, explainable bar,
accepting a weaker theoretical minimum than B. B is stronger on paper but the
request explicitly prioritised the first-account experience. C was rejected
because an 8-char floor with no further rule is weak enough to be worth avoiding,
and because a visible "capital + number" rule gives the form something concrete to
say inline, which the composition rules make possible.

The security cost is acknowledged rather than denied: per NIST, length-only would
be the stronger policy at the same friction budget if the floor were kept high.
That is the tradeoff being made, not an oversight.

## Consequences

- Sign-up and reset forms can state and enforce an inline, rule-by-rule hint
  ("Add a capital letter." / "Add a number.").
- One source of truth: the browser helper mirrors the server rule, so length and
  composition logic are not duplicated as drifting literals.
- The theoretical minimum-strength of an account password drops (`Abcdefg1`
  now validates). Composition rules invite predictable substitutions.
- Existing stored hashes are unaffected — this gates new passwords only, so no
  migration or forced reset.
- Test fixtures that used length-only passwords (e.g.
  `correct-horse-battery-staple`) had to be made composition-compliant.

## Revisit trigger

Reopen if account-takeover incidents trace to weak-but-valid passwords, if a
breach-password (HIBP-style) check is adopted (which would let the floor drop
further *and* get safer), or if the team decides to move to a length-forward
policy (e.g. 12+ with no composition rules) in line with NIST guidance.
