"""The department question bank, from `doc/08` §2-7.

Five questions per department, six departments. **Not the thirty-nine the
earlier drafts carried** — `doc/08` had already applied Q33's rule when it was
written, and this module applies it again on the way in: every question
declares, in `consumed_by`, the capability that reads it.

**A question with no consumer is not a question, it is a form field.** That is
Q33 in one line, and `tests/test_question_bank.py` enforces it — the guard
against this bank drifting back towards thirty-nine, which is what happens when
somebody adds "it would be useful to know" to a screen a founder has to get
through.

The `consumed_by` strings are the *capability* names, not table names or
function names. What matters is that a human can trace a question to the thing
that stops working without it, and argue about whether that thing is worth the
question.

**Scope.** Department questions are `L3_DEPARTMENT`, owned by the department
they are asked for, with two deliberate exceptions marked at their definitions.
Doc 06 §2.5's "tag them at capture" applies here exactly as it does to the
company stage: the scope travels with the question, not with the caller.
"""

from __future__ import annotations

from typing import Final

from app.domain.onboarding import AnswerType, Choice, Pass, Question
from app.domain.scopes import Department, Scope

GRACE_DAYS: Final[tuple[Choice, ...]] = (
    Choice("0", "The day after the date we promised"),
    Choice("1", "One day past it"),
    Choice("2", "Two days past it"),
    Choice("3", "Three days past it"),
    Choice("7", "A week past it"),
)
"""How much grace an order gets before it counts as late.

**The values are days, and that is the point.** This question was typed
`SINGLE_CHOICE` with no options for as long as it existed, so it collected free
prose — and `operations.on_time_dispatch` declared it consumed while nothing
could read it. D32 had to invent a separate numeric setting because no parser
can turn "a day or two after we said" into a threshold without choosing one on
the customer's behalf.

A closed set fixes the question rather than working around it: the answer is
already the number the figure needs, and `routes/spine` writes it to
`workspace.dispatch_grace_days` — the single place the rate reads (ADR 0036).

Five options, not a free number. A grace measured in weeks is a different promise
rather than a longer one, and a text box invites "it depends", which is the state
this question exists to leave.
"""


def _q(
    key: str,
    prompt: str,
    department: Department,
    answer_type: AnswerType,
    why: str,
    consumed_by: str,
    scope: Scope = Scope.L3_DEPARTMENT,
    options: tuple[Choice, ...] = (),
) -> Question:
    return Question(
        key=key,
        prompt=prompt,
        stage=Pass.TWO,
        answer_type=answer_type,
        scope=scope,
        department=department,
        why=why,
        consumed_by=consumed_by,
        options=options,
    )


MARKETING = (
    _q(
        "lead_definition",
        "What counts as a lead worth passing to Sales?",
        Department.MARKETING,
        AnswerType.LONG_TEXT,
        "The denominator of every conversion figure. Without it, "
        '"conversion rate" is a number with no agreed meaning.',
        consumed_by="marketing.conversion_funnel",
    ),
    _q(
        "active_channels",
        "Which channels do you actively run?",
        Department.MARKETING,
        AnswerType.MULTI_CHOICE,
        "Which channel rows appear, and which absent channels are reported as "
        "*not run* rather than as zero.",
        consumed_by="marketing.channel_performance",
    ),
    _q(
        "acquisition_budget",
        "Monthly budget you are willing to spend on acquisition?",
        Department.MARKETING,
        AnswerType.MONEY,
        "Budget-versus-actual, and the Growth Plan's allocation must sum to it.",
        consumed_by="marketing.growth_planner",
    ),
    _q(
        "lost_to",
        "Who do you most often lose to?",
        Department.MARKETING,
        AnswerType.TEXT,
        "Seeds competitor tracking before discovery runs.",
        consumed_by="strategy.competitor_watch",
    ),
    _q(
        "arabic_in_scope",
        "Is Arabic-language content in scope this year?",
        Department.MARKETING,
        AnswerType.SINGLE_CHOICE,
        "Whether the Arabic-language gap is reported as an opportunity or "
        "suppressed as out of scope.",
        consumed_by="marketing.seo_gaps",
    ),
)

SALES = (
    _q(
        "pipeline_stages",
        "What are your pipeline stages, in order?",
        Department.SALES,
        AnswerType.TEXT,
        "The board columns, and the order progress is measured against.",
        consumed_by="sales.pipeline_board",
    ),
    _q(
        "stale_deal_days",
        "After how many days of silence should NEXUS flag a deal?",
        Department.SALES,
        AnswerType.SINGLE_CHOICE,
        "The stale-deal threshold. A judgement only this company can make.",
        consumed_by="sales.stale_deal_alert",
    ),
    _q(
        "lead_assignment",
        "How are new leads assigned?",
        Department.SALES,
        AnswerType.SINGLE_CHOICE,
        "Whether an unassigned lead is an error state or the normal one.",
        consumed_by="sales.lead_routing",
    ),
    _q(
        "quota_period",
        "What is the quota period?",
        Department.SALES,
        AnswerType.SINGLE_CHOICE,
        'The attainment window. "No formal quota" suppresses attainment entirely '
        "rather than showing it against nothing.",
        consumed_by="sales.quota_attainment",
    ),
    _q(
        "disqualifiers",
        "What disqualifies a deal outright?",
        Department.SALES,
        AnswerType.LONG_TEXT,
        "Which deals are excluded from forecasting rather than counted at low probability.",
        consumed_by="sales.forecast",
    ),
)

FINANCE = (
    # `doc/08` 4.1 asked when the financial year *ends*. It is cut: P6's company
    # stage already asks when it starts, and the same fact asked from both ends
    # is two rows that can disagree. Q33 cuts questions nothing consumes; this
    # is the neighbouring case — a question something consumes, that something
    # else already answers. Recorded in ADR 0020.
    _q(
        "payment_terms",
        "Standard payment terms you offer?",
        Department.FINANCE,
        AnswerType.SINGLE_CHOICE,
        "The ageing buckets, and what counts as overdue.",
        consumed_by="finance.receivables_ageing",
    ),
    _q(
        "approval_threshold",
        "Above what amount does spend need approval?",
        Department.FINANCE,
        AnswerType.MONEY,
        "Which requests enter the approvals queue at all.",
        consumed_by="finance.approvals_queue",
    ),
    _q(
        "approver",
        "Who approves spend above that?",
        Department.FINANCE,
        AnswerType.SINGLE_CHOICE,
        "Where an approval routes.",
        consumed_by="finance.approvals_queue",
    ),
    _q(
        "runway_alert_months",
        "How many months of runway would worry you?",
        Department.FINANCE,
        AnswerType.SINGLE_CHOICE,
        "The runway alert threshold — a judgement, not a benchmark, and wrong "
        "for somebody else's business.",
        consumed_by="finance.runway_alert",
    ),
)

OPERATIONS = (
    _q(
        "promised_lead_time",
        "What do you promise customers as a lead time?",
        Department.OPERATIONS,
        AnswerType.TEXT,
        "The baseline on-time dispatch is measured against.",
        consumed_by="operations.on_time_dispatch",
    ),
    _q(
        "common_delay_cause",
        "What usually causes a delay?",
        Department.OPERATIONS,
        AnswerType.SINGLE_CHOICE,
        "Which bottleneck NEXUS checks first when something slips.",
        consumed_by="operations.bottleneck_diagnosis",
    ),
    _q(
        "stock_posture",
        "Do you hold stock, or order per job?",
        Department.OPERATIONS,
        AnswerType.SINGLE_CHOICE,
        "Whether stock levels and reorder minimums apply at all.",
        consumed_by="operations.stock_levels",
    ),
    _q(
        "late_definition",
        "At what point is an order officially late?",
        Department.OPERATIONS,
        AnswerType.SINGLE_CHOICE,
        'The definition of "late". Every lateness figure is meaningless without it.',
        consumed_by="operations.on_time_dispatch",
        options=GRACE_DAYS,
    ),
    _q(
        "supplier_concentration",
        "Which supplier are you most exposed to?",
        Department.OPERATIONS,
        AnswerType.TEXT,
        "Concentration risk, before purchase history exists to infer it.",
        consumed_by="operations.supplier_risk",
    ),
)

PEOPLE = (
    _q(
        "leave_accrual",
        "Is leave accrued monthly or granted annually?",
        Department.HR,
        AnswerType.SINGLE_CHOICE,
        "How the leave liability is calculated.",
        consumed_by="people.leave_liability",
    ),
    _q(
        "hire_signoff",
        "Who signs off a new hire?",
        Department.HR,
        AnswerType.SINGLE_CHOICE,
        "Where a requisition routes.",
        consumed_by="people.requisition_routing",
    ),
    _q(
        "people_risk",
        "What is your biggest people risk right now?",
        Department.HR,
        AnswerType.LONG_TEXT,
        "Seeds the cross-department risk register before there is history to infer it from.",
        consumed_by="executive.risk_register",
    ),
    _q(
        "review_cycle",
        "Do you run performance reviews on a cycle?",
        Department.HR,
        AnswerType.SINGLE_CHOICE,
        "Whether review timing appears on the calendar at all.",
        consumed_by="people.review_calendar",
    ),
    _q(
        "track_document_expiry",
        "Should NEXUS track visa and document expiry?",
        Department.HR,
        AnswerType.SINGLE_CHOICE,
        "A GCC-specific capability, opt-in because it involves sensitive personal "
        "documents and nobody should be enrolled into holding them by default.",
        # L4: the answer decides whether the product holds immigration documents,
        # which is a decision about people rather than about the department.
        scope=Scope.L4_RESTRICTED,
        consumed_by="people.document_expiry",
    ),
)

STRATEGY = (
    _q(
        "success_in_twelve_months",
        "What would make the next twelve months a success?",
        Department.STRATEGY,
        AnswerType.LONG_TEXT,
        "What every recommendation is judged against.",
        consumed_by="strategy.goal_alignment",
    ),
    _q(
        "watched_competitors",
        "Which competitors should NEXUS watch?",
        Department.STRATEGY,
        AnswerType.TEXT,
        "Seeds the tracked set before discovery runs.",
        consumed_by="strategy.competitor_watch",
    ),
    _q(
        "target_market",
        "Which market or segment are you trying to enter?",
        Department.STRATEGY,
        AnswerType.TEXT,
        "Whether a regional signal is an opportunity or noise.",
        consumed_by="strategy.market_position",
    ),
    _q(
        "binding_constraint",
        "What is the binding constraint today?",
        Department.STRATEGY,
        AnswerType.SINGLE_CHOICE,
        "Which recommendations are suppressed as unactionable. Recommending a "
        "hire to a company constrained by cash is how advice stops being read.",
        consumed_by="executive.recommendation_filter",
    ),
    _q(
        "deliberately_not_doing",
        "What are you deliberately not doing?",
        Department.STRATEGY,
        AnswerType.LONG_TEXT,
        "Prevents NEXUS recommending something already ruled out — the fastest "
        "way for a product like this to lose credibility.",
        consumed_by="executive.recommendation_filter",
    ),
)

BANK: tuple[Question, ...] = (*MARKETING, *SALES, *FINANCE, *OPERATIONS, *PEOPLE, *STRATEGY)

BY_DEPARTMENT: dict[Department, tuple[Question, ...]] = {
    Department.MARKETING: MARKETING,
    Department.SALES: SALES,
    Department.FINANCE: FINANCE,
    Department.OPERATIONS: OPERATIONS,
    Department.HR: PEOPLE,
    Department.STRATEGY: STRATEGY,
}


# The bank joins the lookup `store_answer` resolves scope through.
#
# Registered here rather than in `onboarding.py` because this module imports
# from that one, and the reverse import would be circular. Same pattern the
# company stage uses, and the same hazard: a key defined in two places is a
# lookup that silently returns whichever was registered last, which is exactly
# what happened in P6. `tests/test_question_bank.py` asserts no bank key
# collides with the company stage, and `test_onboarding_scope.py` asserts
# uniqueness across every source.
from app.domain.onboarding import BY_KEY  # noqa: E402

BY_KEY.update({q.key: q for q in BANK})
