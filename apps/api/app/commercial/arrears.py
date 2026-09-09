"""Rent & arrears intelligence — architecture/05-commercial-domain.md
§3, spec §75's "rent -> payment -> arrears" integration test. Both
functions follow architecture's own pseudocode closely:

    def arrears_for_lease(lease_id, as_of=today()) -> ArrearsSnapshot:
        obligations = due_obligations(lease_id, as_of)
        allocated = matched_allocations(lease_id, as_of)
        outstanding = obligations.total_due - allocated.total_matched
        ageing = age_buckets(obligations, allocated, as_of)
        return ArrearsSnapshot(outstanding, ageing, credits=allocated.overpaid,
                                unallocated=unallocated_payments(lease_id, as_of))

    def collection_rate(organisation_id, period) -> float:
        due = sum_rent_obligations(organisation_id, period)
        collected = sum_matched_payments(organisation_id, period)
        return collected / due if due else 1.0

Pure, deterministic, computed at read time — same boundary as every
other analytics function in this codebase: "deterministic analytics,
AI explains" (architecture's own words, restated identically for this
domain). Only MATCHED allocations count as "collected" —
POSSIBLE_MATCH/NEEDS_REVIEW/UNALLOCATED represent money received but
not yet confirmed against a specific obligation, so counting them here
would blur spec §52's "never silently allocate ambiguous money" into
the reporting layer too.
"""

import uuid
from datetime import date

from sqlalchemy.orm import Session

from app.commercial.models import AllocationStatus, PaymentAllocation, PaymentTransaction, RentObligation, RentObligationStatus
from app.commercial.schemas import ArrearsSnapshotOut, CollectionRateOut
from app.commercial.service import matched_amount_for_obligation

AGE_BUCKETS = ("CURRENT", "1-30", "31-60", "61-90", "90+")


def _bucket_for(days_overdue: int) -> str:
    if days_overdue <= 0:
        return "CURRENT"
    if days_overdue <= 30:
        return "1-30"
    if days_overdue <= 60:
        return "31-60"
    if days_overdue <= 90:
        return "61-90"
    return "90+"


def arrears_for_lease(db: Session, organisation_id: uuid.UUID, lease_id: uuid.UUID, as_of: date | None = None) -> ArrearsSnapshotOut:
    as_of = as_of or date.today()
    obligations = (
        db.query(RentObligation)
        .filter(
            RentObligation.organisation_id == organisation_id,
            RentObligation.lease_id == lease_id,
            RentObligation.status == RentObligationStatus.ACTIVE,
        )
        .all()
    )

    total_due = sum(o.amount_due_pence for o in obligations)
    ageing_pence = {bucket: 0 for bucket in AGE_BUCKETS}
    total_outstanding = 0
    credits_pence = 0

    for obligation in obligations:
        matched = matched_amount_for_obligation(db, organisation_id, obligation.id)
        outstanding = obligation.amount_due_pence - matched
        if outstanding > 0:
            total_outstanding += outstanding
            days_overdue = (as_of - obligation.due_date).days
            ageing_pence[_bucket_for(days_overdue)] += outstanding
        elif outstanding < 0:
            credits_pence += -outstanding

    # "Unallocated" money for a lease is the full amount of any payment
    # that has no MATCHED allocation at all — not the allocation row's
    # own amount_allocated_pence, which is 0 for UNALLOCATED/
    # NEEDS_REVIEW rows and only a tentative figure for POSSIBLE_MATCH.
    matched_payment_ids = {
        row[0]
        for row in (
            db.query(PaymentAllocation.payment_transaction_id)
            .join(PaymentTransaction, PaymentTransaction.id == PaymentAllocation.payment_transaction_id)
            .filter(
                PaymentAllocation.organisation_id == organisation_id,
                PaymentAllocation.allocation_status == AllocationStatus.MATCHED,
                PaymentTransaction.lease_id == lease_id,
            )
        )
    }
    payments = (
        db.query(PaymentTransaction)
        .filter(PaymentTransaction.organisation_id == organisation_id, PaymentTransaction.lease_id == lease_id)
        .all()
    )
    unallocated_total = sum(p.amount_pence for p in payments if p.id not in matched_payment_ids)

    return ArrearsSnapshotOut(
        lease_id=lease_id,
        as_of=as_of,
        total_due_pence=total_due,
        outstanding_pence=total_outstanding,
        ageing_pence=ageing_pence,
        credits_pence=credits_pence,
        unallocated_pence=unallocated_total,
    )


def collection_rate(db: Session, organisation_id: uuid.UUID, period_start: date, period_end: date) -> CollectionRateOut:
    obligations = (
        db.query(RentObligation)
        .filter(
            RentObligation.organisation_id == organisation_id,
            RentObligation.status == RentObligationStatus.ACTIVE,
            RentObligation.due_date >= period_start,
            RentObligation.due_date <= period_end,
        )
        .all()
    )
    due = sum(o.amount_due_pence for o in obligations)
    collected = sum(matched_amount_for_obligation(db, organisation_id, o.id) for o in obligations)
    rate = collected / due if due else 1.0

    return CollectionRateOut(
        period_start=period_start, period_end=period_end, due_pence=due, collected_pence=collected, collection_rate=round(rate, 4)
    )
