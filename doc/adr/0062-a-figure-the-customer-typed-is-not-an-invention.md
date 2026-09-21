# 0062. A figure the customer typed is not an invention

- **Status:** Accepted
- **Date:** 21 September 2026
- **Deciders:** Parul
- **Decides:** D38
- **Amends:** ADR 0053, which permits numerals only from cited passages
- **Affects:** `app/assistant/grounding.py`, `app/assistant/ask.py`

## Context

ADR 0053 says a figure is permitted only by the passage the answer cited. A9's
first live run over 33 authored questions produced 25 answers, 4 correct
refusals, 0 inventions — and **one refusal that was wrong**:

> *"Who can approve a purchase of 3,000 rial?"*
> over a policy stating *"purchases from 500 to 5,000 OMR require department
> head approval"*
> → `INVENTED_NUMBER`: *"it stated a figure that appears in none of the passages
> it quoted."*

The figure was **3,000, and the customer typed it.** `also_permitted` is built
from cited passages alone, so a numeral from the question is indistinguishable
from one the model made up. The product told a founder their own number was
fabricated, on the question shape — *"can I approve X?"*, *"is X covered?"* —
most likely to carry a threshold.

One in twenty-six answerable questions, measured.

## Options considered

### A. Permit numerals from the question
Small: fold `numerals_supplied(question.text)` into `also_permitted`.

### B. Leave it
The refusal is safe, and rephrasing without the figure gets an answer.

### C. Permit only where the answer cites a passage holding a band the figure
falls within
Precise, and needs range parsing this product does not have.

## Decision

**A, narrowed twice.**

1. A question's numerals are permitted **only for an answer that cites at least
   one passage.** An answer pointing at nothing keeps ADR 0053's original set.
2. When an answer states a figure that came from the question and not from a
   cited passage, `input_snapshot.question_numerals_echoed` records it.

## Reasoning

**Against B, which is the tempting one.** A safe refusal is not free: it is the
product contradicting the reader about an input they supplied, and it teaches
them the assistant is unreliable at exactly the moment it is being careful. The
"just rephrase" workaround also requires the founder to guess *why* it refused,
and the sentence deliberately does not say — it reads as though their documents
were at fault.

**Against C**, on cost only. Range parsing would be the right answer if the
question were "is this figure consistent with the cited band", but that is a
faithfulness check, and this product does not have one yet (A2's stated limit).
Building half of one to fix a numeral rule would put an unreviewed inference in
the guard.

**Why the citation narrowing is not decoration.** A question is
**attacker-reachable** in a way a passage is not — anyone who can type can put a
figure in it. *"Is our revenue 5,000,000?"* would, under unnarrowed A, permit
the model to hand 5,000,000 straight back with the numeral check silent. Tying
the permission to a citation means the answer must still point at a passage a
reader can open and check; the figure is no longer laundered, it is attributed
to something falsifiable.

**Why the echo is recorded rather than trusted.** The narrowing reduces the risk
and does not remove it. `question_numerals_echoed` makes an echo **findable
afterwards** — a reviewer can ask which answers relied on this permission rather
than inferring it from prose. A guard that loosens without leaving a trace is a
guard that quietly becomes something else.

## Consequences

- One eval question moves from wrongly-refused to answered. The measured
  wrongly-refused count goes to **0 of 26**.
- `check` gains a keyword argument, defaulted to empty — so every existing
  caller, including the deterministic evals, keeps ADR 0053's exact behaviour.
- `generation.input_snapshot` gains a field. Additive, no migration.
- I1 is now slightly weaker than "every numeral traces to a passage": it is
  "every numeral traces to a passage **or to the question**, and which one is
  recorded". That is a real reduction and is stated here rather than discovered
  later.

## Revisit trigger

If `question_numerals_echoed` is ever non-empty on an answer whose prose makes a
**claim about** the figure rather than locating it in a band — *"yes, revenue is
5,000,000"* as opposed to *"a purchase of 3,000 needs department head
approval"* — then the citation narrowing is not doing the work this ADR assumes,
and option C's range check becomes the honest fix.

The field makes that query possible, which is why it exists.
