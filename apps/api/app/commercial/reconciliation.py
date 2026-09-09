"""PaymentReconciler — architecture/05-commercial-domain.md §2, spec
§52: "never silently allocate ambiguous money." `match_payment` runs
four deterministic rules in order, exactly as architecture specifies:

    exact reference match -> exact amount+lease+due-date-window match
    -> partial-amount candidate -> no match -> UNALLOCATED

with NEEDS_REVIEW for anything ambiguous at any step. "Ambiguous" is
made concrete here as: a rule finds more than one equally-plausible
candidate obligation. A rule finding exactly one candidate auto-
allocates (MATCHED for the confident rules, POSSIBLE_MATCH for the
partial-amount rule, since a partial payment is inherently less
certain than an exact one — it could be an instalment on this
obligation, or a full payment misapplied against the wrong one). A
rule finding zero candidates simply falls through to the next rule;
only exhausting all four rules with nothing produces UNALLOCATED.

Every PaymentTransaction gets exactly one PaymentAllocation row from
this first automatic pass (see PaymentAllocation's own docstring for
why that row exists even when nothing matched). A RENT_MANAGER
resolving a NEEDS_REVIEW/UNALLOCATED/POSSIBLE_MATCH row later
(router.py's /payment-allocations/{id}/resolve) updates that same row
in place with source_type=MANUAL — this is the "audited... manual
resolution" architecture §2 describes. Splitting one payment across
several obligations, or applying one payment across instalments, is a
human, manual act (router.py's /payments/{id}/allocations) — the
automatic reconciler deliberately never does this itself, since
picking how to split ambiguous money is exactly the kind of judgement
call spec §52 reserves for a person.
"""

import uuid
from datetime import date

from sqlalchemy.orm import Session

from app.commercial.models import AllocationStatus, PaymentAllocation, PaymentTransaction, RentObligation, RentObligationStatus
from app.commercial.service import get_or_create_reconciliation_config, outstanding_for_obligation
from app.core.provenance import SourceType
from app.platform.audit import record_audit_event


def _open_obligations(db: Session, organisation_id: uuid.UUID, lease_id: uuid.UUID | None) -> list[RentObligation]:
    if lease_id is None:
        return []
    obligations = (
        db.query(RentObligation)
        .filter(
            RentObligation.organisation_id == organisation_id,
            RentObligation.lease_id == lease_id,
            RentObligation.status == RentObligationStatus.ACTIVE,
        )
        .all()
    )
    return [o for o in obligations if outstanding_for_obligation(db, organisation_id, o) > 0]


def _record_allocation(
    db: Session,
    organisation_id: uuid.UUID,
    payment: PaymentTransaction,
    obligation: RentObligation | None,
    amount_allocated_pence: int,
    status: AllocationStatus,
    actor_user_id: uuid.UUID | None,
) -> PaymentAllocation:
    allocation = PaymentAllocation(
        organisation_id=organisation_id,
        payment_transaction_id=payment.id,
        rent_obligation_id=obligation.id if obligation else None,
        amount_allocated_pence=amount_allocated_pence,
        allocation_status=status,
        source_type=SourceType.SYSTEM_GENERATED,
    )
    db.add(allocation)
    db.flush()

    record_audit_event(
        db,
        organisation_id=organisation_id,
        actor_user_id=actor_user_id,
        action_code="payment_allocation.auto_matched",
        entity_type="payment_allocation",
        entity_id=str(allocation.id),
        after={
            "payment_transaction_id": str(payment.id),
            "rent_obligation_id": str(obligation.id) if obligation else None,
            "allocation_status": status.value,
        },
    )
    return allocation


def match_payment(
    db: Session, organisation_id: uuid.UUID, payment: PaymentTransaction, *, actor_user_id: uuid.UUID | None
) -> PaymentAllocation:
    config = get_or_create_reconciliation_config(db, organisation_id)
    window_days = config.due_date_window_days
    candidates = _open_obligations(db, organisation_id, payment.lease_id)

    def within_window(obligation: RentObligation) -> bool:
        return abs((obligation.due_date - payment.received_date).days) <= window_days

    # Rule 1: exact reference match.
    if payment.payer_reference:
        ref_matches = [o for o in candidates if o.invoice_reference == payment.payer_reference]
        if len(ref_matches) == 1:
            obligation = ref_matches[0]
            amount = min(payment.amount_pence, outstanding_for_obligation(db, organisation_id, obligation))
            return _record_allocation(db, organisation_id, payment, obligation, amount, AllocationStatus.MATCHED, actor_user_id)
        if len(ref_matches) > 1:
            return _record_allocation(db, organisation_id, payment, None, 0, AllocationStatus.NEEDS_REVIEW, actor_user_id)

    # Rule 2: exact amount + lease + due-date window.
    exact = [
        o
        for o in candidates
        if outstanding_for_obligation(db, organisation_id, o) == payment.amount_pence and within_window(o)
    ]
    if len(exact) == 1:
        return _record_allocation(db, organisation_id, payment, exact[0], payment.amount_pence, AllocationStatus.MATCHED, actor_user_id)
    if len(exact) > 1:
        return _record_allocation(db, organisation_id, payment, None, 0, AllocationStatus.NEEDS_REVIEW, actor_user_id)

    # Rule 3: partial-amount candidate — a plausible instalment, not a
    # confident match, so POSSIBLE_MATCH rather than MATCHED.
    partial = [
        o
        for o in candidates
        if payment.amount_pence < outstanding_for_obligation(db, organisation_id, o) and within_window(o)
    ]
    if len(partial) == 1:
        return _record_allocation(
            db, organisation_id, payment, partial[0], payment.amount_pence, AllocationStatus.POSSIBLE_MATCH, actor_user_id
        )
    if len(partial) > 1:
        return _record_allocation(db, organisation_id, payment, None, 0, AllocationStatus.NEEDS_REVIEW, actor_user_id)

    # Rule 4: no match found by any rule.
    return _record_allocation(db, organisation_id, payment, None, 0, AllocationStatus.UNALLOCATED, actor_user_id)
