"""Thirty questions over ten authored documents. `doc/20` A9's measurement half.

**No customer data.** Every document in `documents/` was written for this
fixture, for a company that does not exist. The content rule that governs the
landing page governs test data too.

**What each field is for.** `answered_by` names the document that contains the
answer, and it is what the deterministic half measures: did retrieval put that
document in front of the model at all? A question the corpus cannot answer
carries `answered_by=None`, and the *expectation* is a refusal — but nothing
here can check that without a model, because retrieval returns its top matches
whether or not any of them are relevant. That is the live half's job.

**Why `Outcome` is not just answered/refused.** Three of these outcomes are
things the assistant must get right that look like failures if you only count
answers:

- `REFUSE_ABSENT` — the corpus genuinely does not cover it. Refusing is correct,
  and a product that answered would be inventing.
- `REFUSE_ARITHMETIC` — the figures are present and the answer requires doing
  sums on them. ADR 0053 forbids it: quoting is permitted, computing is not.
  This is the category most likely to be "fixed" by somebody who mistakes a
  correct refusal for a miss.
- `ANSWER_MULTI` — the answer needs two documents. Retrieval has to surface
  both, and the answer has to cite both.

`note` is written for the human doing the hand-judging in A9's third count —
answers whose citation does not support the claim. Nothing automates that, so
the note says what a right answer would contain.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

DOCUMENTS = Path(__file__).parent / "documents"


class Outcome(StrEnum):
    ANSWER = "answer"
    """One document holds it. Quote and cite."""

    ANSWER_MULTI = "answer_multi"
    """Two documents are needed, and both must be cited."""

    REFUSE_ABSENT = "refuse_absent"
    """The corpus does not cover it. Refusing is the correct product behaviour."""

    REFUSE_ARITHMETIC = "refuse_arithmetic"
    """The figures are there and the question invites a calculation over them.

    **The name is narrower than the requirement, and the first live run showed
    why.** Refusing outright is *not* the only right answer — quoting the stated
    figures and declining the sum is better, and it is what the model did on all
    three: *"No total annual interest figure is stated, so that amount isn't
    given directly in the passages."* What must never appear is the **computed**
    value, which is what `forbidden` names and what ADR 0053 actually forbids.
    """


@dataclass(frozen=True, slots=True)
class Question:
    text: str
    department: str
    expect: Outcome
    answered_by: tuple[str, ...]
    note: str
    forbidden: tuple[str, ...] = ()
    """Figures that must never appear, because only arithmetic produces them.

    This automates part of A9's third count. It was written off as
    hand-judgement — and the hand-judging of the first run showed that the
    *arithmetic* slice of it is mechanical: the sum either appears or it does
    not. What stays human is whether a citation supports a **qualitative**
    claim.
    """


QUESTIONS: tuple[Question, ...] = (
    # ── Straightforward: one document, quoted verbatim ────────
    Question(
        "What are our payment terms?",
        "finance",
        Outcome.ANSWER,
        ("supplier-agreement.txt",),
        "30 days from invoice date.",
    ),
    Question(
        "What interest do we charge on late payment?",
        "finance",
        Outcome.ANSWER,
        ("supplier-agreement.txt",),
        "8 percent per annum, daily on the outstanding balance.",
    ),
    Question(
        "How much notice do we need to give to terminate the supplier agreement?",
        "operations",
        Outcome.ANSWER,
        ("supplier-agreement.txt",),
        "Ninety days written notice; immediate for material breach.",
    ),
    Question(
        "What is our liability cap per incident?",
        "finance",
        Outcome.ANSWER,
        ("supplier-agreement.txt",),
        "50,000 OMR per incident. 150,000 OMR aggregate is a different figure.",
    ),
    Question(
        "How many days of annual leave do employees get?",
        "hr",
        Outcome.ANSWER,
        ("employment-handbook.txt",),
        "30 calendar days per completed year, accruing at 2.5 days a month.",
    ),
    Question(
        "How long is the probation period?",
        "hr",
        Outcome.ANSWER,
        ("employment-handbook.txt",),
        "3 months, extendable once by a further 3 with written notice.",
    ),
    Question(
        "What are the working hours during Ramadan?",
        "hr",
        Outcome.ANSWER,
        ("employment-handbook.txt",),
        "6 hours a day, against a standard 45-hour week.",
    ),
    Question(
        "How is end of service gratuity calculated?",
        "hr",
        Outcome.ANSWER,
        ("employment-handbook.txt",),
        "15 days basic per year for the first 3 years, one month per year after.",
    ),
    Question(
        "What is the annual rent on the office?",
        "finance",
        Outcome.ANSWER,
        ("office-lease.txt",),
        "18,000 OMR, quarterly in advance.",
    ),
    Question(
        "How much notice do we need to give to leave the office?",
        "operations",
        Outcome.ANSWER,
        ("office-lease.txt",),
        "6 months written notice, at the end of a lease year.",
    ),
    Question(
        "What is our public liability cover?",
        "finance",
        Outcome.ANSWER,
        ("insurance-policy.txt",),
        "1,000,000 OMR per occurrence, with no excess.",
    ),
    Question(
        "Does our insurance cover cyber incidents?",
        "operations",
        Outcome.ANSWER,
        ("insurance-policy.txt",),
        "No — excluded, and available only as a separate endorsement.",
    ),
    Question(
        "What uptime do we guarantee?",
        "operations",
        Outcome.ANSWER,
        ("service-level-agreement.txt",),
        "99.5 percent monthly, excluding scheduled maintenance.",
    ),
    Question(
        "How quickly must a priority 1 incident be resolved?",
        "operations",
        Outcome.ANSWER,
        ("service-level-agreement.txt",),
        "Acknowledged in 30 minutes, resolved in 4 hours.",
    ),
    Question(
        "Who can approve a purchase of 3,000 rial?",
        "finance",
        Outcome.ANSWER,
        ("procurement-policy.txt",),
        "A department head — the 500 to 5,000 band. Also needs three quotes.",
    ),
    Question(
        "How many quotes do we need for a large purchase?",
        "operations",
        Outcome.ANSWER,
        ("procurement-policy.txt",),
        "Three written quotations above 2,000 OMR.",
    ),
    Question(
        "How long do we keep employee records?",
        "hr",
        Outcome.ANSWER,
        ("data-protection-policy.txt",),
        "7 years after the end of employment.",
    ),
    Question(
        "How quickly must we answer a data access request?",
        "hr",
        Outcome.ANSWER,
        ("data-protection-policy.txt",),
        "30 days, at no charge.",
    ),
    Question(
        "What happens to traffic fines on company vehicles?",
        "hr",
        Outcome.ANSWER,
        ("vehicle-fleet-policy.txt",),
        "The driver's responsibility, deducted from salary unless appealed.",
    ),
    Question(
        "How often are company vehicles serviced?",
        "operations",
        Outcome.ANSWER,
        ("vehicle-fleet-policy.txt",),
        "Every 10,000 km or 6 months, whichever comes first.",
    ),
    Question(
        "What is our overdraft limit?",
        "finance",
        Outcome.ANSWER,
        ("bank-facility-letter.txt",),
        "75,000 OMR, repayable on demand.",
    ),
    Question(
        "When do we have to give the bank our audited accounts?",
        "finance",
        Outcome.ANSWER,
        ("bank-facility-letter.txt",),
        "Within 120 days of financial year end.",
    ),
    Question(
        "How long is the equipment warranty?",
        "operations",
        Outcome.ANSWER,
        ("warranty-terms.txt",),
        "24 months from delivery.",
    ),
    Question(
        "Is onsite warranty attendance included?",
        "operations",
        Outcome.ANSWER,
        ("warranty-terms.txt",),
        "Within 100 km of Muscat; beyond that travel is charged at cost.",
    ),
    # ── Two documents ─────────────────────────────────────────
    Question(
        "What are all the notice periods we are committed to?",
        "executive",
        Outcome.ANSWER_MULTI,
        ("supplier-agreement.txt", "office-lease.txt"),
        "Ninety days on the supplier agreement, 6 months on the lease. Both cited.",
    ),
    Question(
        "What record retention periods apply to us?",
        "executive",
        Outcome.ANSWER_MULTI,
        ("data-protection-policy.txt", "procurement-policy.txt"),
        "7 and 10 years for personal data, 7 years for purchase records.",
    ),
    # ── Arithmetic: the figures are there, the sum is not ─────
    Question(
        "What is our total annual cost for the office including service charge?",
        "finance",
        Outcome.REFUSE_ARITHMETIC,
        ("office-lease.txt",),
        "18,000 + 1,200 is a calculation. Quoting both figures is fine; "
        "stating 19,200 is not (ADR 0053).",
        forbidden=("19,200", "19200"),
    ),
    Question(
        "How much interest would we pay on a fully drawn overdraft for a year?",
        "finance",
        Outcome.REFUSE_ARITHMETIC,
        ("bank-facility-letter.txt",),
        "75,000 at 6.5 percent is arithmetic the model must not do.",
        forbidden=("4,875", "4875"),
    ),
    Question(
        "What is the monthly equivalent of our annual leave entitlement?",
        "hr",
        Outcome.REFUSE_ARITHMETIC,
        ("employment-handbook.txt",),
        "A trap: the handbook states 2.5 days a month, so quoting it is correct "
        "and dividing 30 by 12 is not. Either may appear — judge the citation.",
        forbidden=("2.50 days",),
    ),
    # ── Absent: the corpus does not cover it ──────────────────
    Question(
        "How long is our cash runway?",
        "finance",
        Outcome.REFUSE_ABSENT,
        (),
        "Needs accounting, not documents. The refusal must name no department.",
    ),
    Question(
        "What is in our sales pipeline?",
        "sales",
        Outcome.REFUSE_ABSENT,
        (),
        "Needs a CRM. Nothing in the corpus is about deals.",
    ),
    Question(
        "How many people work here?",
        "hr",
        Outcome.REFUSE_ABSENT,
        (),
        "Headcount is exactly what the roster cannot answer (doc/21).",
    ),
    Question(
        "What did we spend on marketing last quarter?",
        "marketing",
        Outcome.REFUSE_ABSENT,
        (),
        "No marketing document and no accounting connector.",
    ),
)

BY_OUTCOME: dict[Outcome, tuple[Question, ...]] = {
    outcome: tuple(q for q in QUESTIONS if q.expect is outcome) for outcome in Outcome
}
