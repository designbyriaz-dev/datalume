"""Commercial domain — architecture/05-commercial-domain.md §1, spec
items 50-54. Sprint 19 builds the first two tables of that section's
own schema sketch (Tenant, Lease); rent_obligations/payment_transactions/
payment_allocations and the reconciliation/arrears engines are Sprint
20's own explicit split in the roadmap, not this sprint's.

`Tenant`/`Lease` are org-scoped for every organisation type, not just
commercial landlords — the adaptive workspace layout
(app/organisations/adaptive.py) only controls whether "Tenancies"/
"Leases" appear in a given org's nav and whether "tenant" is relabelled
"occupier"; it's a UI-terminology decision, not an API capability gate,
the same way a housing-association org can still call the Repairs API
even though its nav happens to show it too (every domain's nav slicing
is presentational, never enforced at the router).
"""

import enum
import uuid
from datetime import date

from sqlalchemy import Date, Enum, ForeignKey, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.core.provenance import ProvenanceMixin


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
