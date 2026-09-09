"""Commercial domain — architecture/05-commercial-domain.md, spec items
50-54, 58-65 (rent/payment portion). Sprint 19 built §1's Tenant/Lease
tables. Sprint 20 builds the rest of §1 (RentObligation,
PaymentTransaction, PaymentAllocation) plus §2's reconciliation engine
(reconciliation.py) and §3's arrears/collection-rate intelligence
(arrears.py) — the roadmap's own two-sprint split of one architecture
section, same pattern as Compliance (Sprints 15-17).

`Tenant`/`Lease` are org-scoped for every organisation type, not just
commercial landlords — the adaptive workspace layout
(app/organisations/adaptive.py) only controls whether "Tenancies"/
"Leases" appear in a given org's nav and whether "tenant" is relabelled
"occupier"; it's a UI-terminology decision, not an API capability gate,
the same way a housing-association org can still call the Repairs API
even though its nav happens to show it too (every domain's nav slicing
is presentational, never enforced at the router).

**Payment boundary (spec §54, architecture §4) — read this before
touching payment_transactions**: Build 1 does not hold tenant money,
act as a bank, process cards/Direct Debits, transfer funds, or operate
stored value. `PaymentTransaction` is a *record* of a payment that
happened elsewhere (bank feed import, manual entry, or — in a later
build — a read-only webhook), never a payment *initiation*. There is
no `POST /payments/charge` endpoint anywhere in this codebase, by
design — only `POST /payments` (router.py) to record a transaction
that already occurred. This is why the endpoint is literally named
`/payments`, not `/payment-transactions` — matching the architecture
doc's own wording exactly, since the distinction it's making (record
vs. initiate) is the whole point.
"""

import enum
import uuid
from datetime import date

from sqlalchemy import Date, Enum, ForeignKey, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.core.provenance import ProvenanceMixin, SourceType


class Tenant(Base, ProvenanceMixin):
    __tablename__ = "tenants"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organisation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.id"))
    name: Mapped[str] = mapped_column(String(255))
    # Free-form {email, phone, ...} map rather than fixed columns — same
    # reasoning as StockConditionSurvey.condition_ratings (Sprint 18):
    # this build has no authoritative source for exactly which contact
    # fields every org needs, so it doesn't invent one.
    contact_details: Mapped[dict] = mapped_column(JSON, default=dict)


class LeaseStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    EXPIRED = "EXPIRED"
    TERMINATED = "TERMINATED"
    RENEWED = "RENEWED"


class OccupancyStatus(str, enum.Enum):
    OCCUPIED = "OCCUPIED"
    VACANT = "VACANT"
    NOTICE_GIVEN = "NOTICE_GIVEN"


class RentFrequency(str, enum.Enum):
    WEEKLY = "WEEKLY"
    MONTHLY = "MONTHLY"
    QUARTERLY = "QUARTERLY"
    ANNUALLY = "ANNUALLY"


class Lease(Base, ProvenanceMixin):
    """architecture §1's own SQL sketch. `contractual_rent`/
    `service_charge_amount` are pence (integer), never a float — same
    convention as every other money column in this codebase (Repair.
    cost_pence, Defect.estimated_cost_pence, Plan pricing).

    `lease_status` is a workflow state with an enforced transition graph
    (service.py.LEASE_TRANSITIONS) the same way Repair/Defect/Hazard
    status is. `occupancy_status` deliberately is NOT — it's a
    descriptive snapshot of who's physically there right now, not a
    directional process (a tenant can go OCCUPIED -> NOTICE_GIVEN ->
    OCCUPIED again if notice is withdrawn), so it's freely settable.
    """

    __tablename__ = "leases"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organisation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.id"))
    property_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("properties.id"))
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    lease_reference: Mapped[str] = mapped_column(String(32))
    lease_start: Mapped[date] = mapped_column(Date)
    lease_expiry: Mapped[date] = mapped_column(Date)
    break_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    rent_review_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    contractual_rent_pence: Mapped[int] = mapped_column(Integer)
    rent_frequency: Mapped[RentFrequency] = mapped_column(Enum(RentFrequency))
    service_charge_amount_pence: Mapped[int | None] = mapped_column(Integer, nullable=True)
    occupancy_status: Mapped[OccupancyStatus] = mapped_column(Enum(OccupancyStatus), default=OccupancyStatus.OCCUPIED)
    lease_status: Mapped[LeaseStatus] = mapped_column(Enum(LeaseStatus), default=LeaseStatus.DRAFT)


class ObligationType(str, enum.Enum):
    RENT = "RENT"
    SERVICE_CHARGE = "SERVICE_CHARGE"
    INSURANCE_RECHARGE = "INSURANCE_RECHARGE"
    UTILITY_RECHARGE = "UTILITY_RECHARGE"
    OTHER = "OTHER"


class RentObligationStatus(str, enum.Enum):
    """Deliberately just ACTIVE/CANCELLED, not PAID/OVERDUE/PARTIAL —
    whether an obligation is settled is always computed from its
    PaymentAllocation rows at read time (arrears.py), never stored
    here, so there's nothing to go stale between payments. CANCELLED
    is the one genuinely independent fact: a billing correction that
    should stop counting toward arrears without deleting the record."""

    ACTIVE = "ACTIVE"
    CANCELLED = "CANCELLED"


class RentObligation(Base):
    """architecture §1's own SQL sketch — "what is owed." `amount_due`
    is pence, never a float, same convention as every money column in
    this codebase. `invoice_reference` is an external, org-supplied
    identifier (e.g. from accounting software) — not an internally
    generated sequential reference the way Repair/Lease references
    are, so it doesn't go through the Identifier & Reference Engine."""

    __tablename__ = "rent_obligations"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organisation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.id"))
    lease_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("leases.id"))
    obligation_type: Mapped[ObligationType] = mapped_column(Enum(ObligationType))
    due_date: Mapped[date] = mapped_column(Date)
    period_start: Mapped[date] = mapped_column(Date)
    period_end: Mapped[date] = mapped_column(Date)
    amount_due_pence: Mapped[int] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(3), default="GBP")
    invoice_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[RentObligationStatus] = mapped_column(Enum(RentObligationStatus), default=RentObligationStatus.ACTIVE)


class PaymentTransaction(Base, ProvenanceMixin):
    """architecture §1's own SQL sketch — "what was received," a record
    of money that arrived elsewhere (see this module's own docstring on
    the payment boundary). `lease_id` is nullable: a payment can arrive
    before the reconciler — or a human — knows which lease it belongs
    to (spec §52's "unallocated" case starts here). `method` is a plain
    free-text string (e.g. "BANK_TRANSFER", "CHEQUE"), not an enum —
    same reasoning as Repair.contractor: descriptive metadata, not a
    workflow state this codebase enforces transitions over.
    """

    __tablename__ = "payment_transactions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organisation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.id"))
    lease_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("leases.id"), nullable=True)
    amount_pence: Mapped[int] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(3), default="GBP")
    received_date: Mapped[date] = mapped_column(Date)
    payer_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    method: Mapped[str | None] = mapped_column(String(64), nullable=True)


class AllocationStatus(str, enum.Enum):
    MATCHED = "MATCHED"
    POSSIBLE_MATCH = "POSSIBLE_MATCH"
    UNALLOCATED = "UNALLOCATED"
    NEEDS_REVIEW = "NEEDS_REVIEW"


class PaymentAllocation(Base):
    """architecture §2: the only join between "what's owed" and "what
    was received" — spec §52 requires exact/possible/partial/
    overpayment/unallocated matches, inherently many-to-many (one
    payment can cover several obligations; one obligation can be paid
    in instalments), which a single combined ledger row can't
    represent without duplication or lossy simplification.

    Every PaymentTransaction gets at least one PaymentAllocation row
    once reconciliation.match_payment runs, even when nothing could be
    matched (`rent_obligation_id` NULL, `allocation_status` UNALLOCATED
    or NEEDS_REVIEW) — the row itself is the "this payment was
    considered and here's what happened" record, not just a record of
    successful matches.

    `organisation_id` is added here even though architecture's own
    abbreviated SQL sketch for this one table omits it — same
    deviation, same reason, as HazardAction (Sprint 16): this
    codebase's RLS policies always filter on the table's own
    organisation_id column directly, never via a join.

    `source_type` (not full ProvenanceMixin — sketch doesn't list one
    here) distinguishes the reconciler's own automatic matches
    (SYSTEM_GENERATED) from a RENT_MANAGER's manual resolution
    (MANUAL) — architecture §2's own words: "that manual resolution is
    itself an audited payment_allocations write with source_type =
    MANUAL." "Never silently allocate ambiguous money."
    """

    __tablename__ = "payment_allocations"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organisation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.id"))
    payment_transaction_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("payment_transactions.id"))
    rent_obligation_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("rent_obligations.id"), nullable=True)
    amount_allocated_pence: Mapped[int] = mapped_column(Integer)
    allocation_status: Mapped[AllocationStatus] = mapped_column(Enum(AllocationStatus))
    source_type: Mapped[SourceType] = mapped_column(Enum(SourceType))


class PaymentReconciliationConfig(Base):
    """Per-organisation singleton tunable for reconciliation.py's
    due-date-window match rule — same lazily-seeded singleton pattern
    as ComplianceStatusConfig (Sprint 17) and PlannedInvestmentConfig
    (Sprint 18): "do not permanently hard-code" a matching-window
    constant that different orgs' billing cycles will disagree on."""

    __tablename__ = "payment_reconciliation_configs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organisation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.id"))
    due_date_window_days: Mapped[int] = mapped_column(Integer, default=14)
