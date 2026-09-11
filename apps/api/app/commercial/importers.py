"""Registers the Commercial domain's CSV importers into the ingestion
pipeline's seam (app/ingestion/pipeline.py IMPORTERS) — spec §78's
"Import rent obligations"/"Import payments", the one Commercial
Acceptance Test item that genuinely didn't exist on either side of the
stack (Post-Sprint-24 audit). Same registration mechanism as
app/development/importers.py: importing this module performs the
registration as a side effect — see app/main.py.

Both importers resolve their lease the same way BUILDINGS/FLOORS
resolve a development/building: by the DataLume-generated
lease_reference (e.g. LSE-000001), the only stable identifier a CSV
can realistically carry.
"""

import uuid
from datetime import date

from sqlalchemy.orm import Session

from app.commercial.models import Lease, ObligationType, PaymentTransaction
from app.commercial.reconciliation import match_payment
from app.commercial.service import create_rent_obligation
from app.core.provenance import SourceType
from app.ingestion.models import Dataset, ImportJob, ImportRow
from app.ingestion.pipeline import IMPORTERS, ImporterRowError


def _parse_iso_date(value: str | None) -> date | None:
    # Same "ISO format only for now" scope line as every other importer
    # in this codebase — see app/development/importers.py's own copy.
    if not value:
        return None
    try:
        return date.fromisoformat(value.strip())
    except ValueError:
        return None


def _parse_pence(value: str | None) -> int | None:
    if not value:
        return None
    try:
        return round(float(value.strip()) * 100)
    except ValueError:
        return None


def _find_lease(db: Session, organisation_id: uuid.UUID, lease_reference: str | None) -> Lease | None:
    if not lease_reference:
        return None
    return (
        db.query(Lease)
        .filter(Lease.organisation_id == organisation_id, Lease.lease_reference == lease_reference.strip())
        .first()
    )


def import_rent_obligation_row(
    db: Session, dataset: Dataset, import_job: ImportJob, row: ImportRow, mapped_fields: dict
) -> tuple[str, uuid.UUID]:
    # Required, not optional — RentObligation.lease_id is a mandatory
    # FK (unlike PAYMENTS' lease_reference below, which mirrors
    # PaymentTransaction.lease_id staying nullable for the genuinely
    # "not yet matched to a lease" case spec §52 describes).
    lease_reference = (mapped_fields.get("lease_reference") or "").strip()
    if not lease_reference:
        raise ImporterRowError("lease_reference is required to import a rent obligation")
    lease = _find_lease(db, dataset.organisation_id, lease_reference)
    if lease is None:
        raise ImporterRowError(f"No lease found with reference {lease_reference!r}")

    due_date = _parse_iso_date(mapped_fields.get("due_date"))
    period_start = _parse_iso_date(mapped_fields.get("period_start"))
    period_end = _parse_iso_date(mapped_fields.get("period_end"))
    if due_date is None or period_start is None or period_end is None:
        raise ImporterRowError("due_date, period_start, and period_end must all be valid ISO dates")

    amount_due_pence = _parse_pence(mapped_fields.get("amount_due"))
    if amount_due_pence is None:
        raise ImporterRowError("amount_due is required and must be a number")

    obligation_type_raw = (mapped_fields.get("obligation_type") or "RENT").strip().upper()
    try:
        obligation_type = ObligationType(obligation_type_raw)
    except ValueError as exc:
        raise ImporterRowError(f"{obligation_type_raw!r} is not a recognised obligation type") from exc

    obligation = create_rent_obligation(
        db,
        dataset.organisation_id,
        lease_id=lease.id,
        obligation_type=obligation_type.value,
        due_date=due_date,
        period_start=period_start,
        period_end=period_end,
        amount_due_pence=amount_due_pence,
        currency=(mapped_fields.get("currency") or "GBP").strip() or "GBP",
        invoice_reference=mapped_fields.get("invoice_reference"),
        actor_user_id=dataset.uploaded_by,
        source_type=SourceType.FILE_UPLOAD,
        source_dataset_id=dataset.id,
        import_job_id=import_job.id,
        original_reference=f"row {row.row_number}",
    )
    return "rent_obligation", obligation.id


def import_payment_row(
    db: Session, dataset: Dataset, import_job: ImportJob, row: ImportRow, mapped_fields: dict
) -> tuple[str, uuid.UUID]:
    received_date = _parse_iso_date(mapped_fields.get("received_date"))
    if received_date is None:
        raise ImporterRowError("received_date is required and must be a valid ISO date")

    amount_pence = _parse_pence(mapped_fields.get("amount"))
    if amount_pence is None:
        raise ImporterRowError("amount is required and must be a number")

    # Unmatched is a real, honest outcome here (spec §52's "unallocated"
    # case) — not every payment arrives with a lease reference the
    # reconciler can use, same as the manual "Record a payment" form's
    # own optional Lease field.
    lease = _find_lease(db, dataset.organisation_id, mapped_fields.get("lease_reference"))

    payment = PaymentTransaction(
        organisation_id=dataset.organisation_id,
        lease_id=lease.id if lease else None,
        amount_pence=amount_pence,
        currency=(mapped_fields.get("currency") or "GBP").strip() or "GBP",
        received_date=received_date,
        payer_reference=mapped_fields.get("payer_reference"),
        method=mapped_fields.get("method"),
        source_type=SourceType.FILE_UPLOAD,
        source_dataset_id=dataset.id,
        import_job_id=import_job.id,
        original_reference=f"row {row.row_number}",
        created_by=dataset.uploaded_by,
        updated_by=dataset.uploaded_by,
    )
    db.add(payment)
    db.flush()

    # Same deterministic reconciler every manually-recorded payment runs
    # through (router.py's add_payment) — an imported payment gets the
    # same real matching, never a fabricated "MATCHED" just because it
    # arrived via a file.
    match_payment(db, dataset.organisation_id, payment, actor_user_id=dataset.uploaded_by)
    return "payment_transaction", payment.id


IMPORTERS["RENT_OBLIGATIONS"] = import_rent_obligation_row
IMPORTERS["PAYMENTS"] = import_payment_row
