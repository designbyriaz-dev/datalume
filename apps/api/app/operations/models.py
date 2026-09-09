"""Repairs — architecture/04-operations-domain.md §1-2, spec §43-44.
First table in a new domain package (`app.operations`), distinct from
`app.development` the way architecture/04 is its own document from
architecture/03 — repairs are an *operational* concern (day-to-day,
post-handover) even though a repair can still reference a component
that a development-phase sprint created.

`contractor` is a plain string, not a `contractor_id` FK to a
Contractor table — same reasoning as `Defect.contractor`
(app/development/models.py, Sprint 11): no Contractor domain exists
anywhere in this build, and BUILD_PROMPT.md's own "Conceptual fields"
list for repairs names `contractor_id NULL` but nothing in the spec
actually calls for a contractor management domain to back it, so this
follows the precedent already set rather than inventing one.
"""

import enum
import uuid
from datetime import date

from sqlalchemy import Boolean, Date, Enum, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.core.provenance import ProvenanceMixin


class RepairPriority(str, enum.Enum):
    EMERGENCY = "EMERGENCY"
    URGENT = "URGENT"
    ROUTINE = "ROUTINE"
    PLANNED = "PLANNED"


class RepairStatus(str, enum.Enum):
    REPORTED = "REPORTED"
    SCHEDULED = "SCHEDULED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class Repair(Base, ProvenanceMixin):
    """architecture/04-operations-domain.md §1. `is_emergency` is not an
    independent input — it's derived from `priority == EMERGENCY` at
    write time (app/operations/service.py.create_repair) so the two
    can never disagree, even though the spec's own SQL sketch lists
    them as separate columns.

    `evidence` (before/after photos, invoices) attaches the same way
    Construction Evidence and Defect evidence do (Sprints 10-11): a
    Document with related_entity_type="repair", no column here.
    """

    __tablename__ = "repairs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organisation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.id"))
    repair_reference: Mapped[str] = mapped_column(String(32))
    property_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("properties.id"))
    component_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("components.id"), nullable=True)
    category: Mapped[str] = mapped_column(String(128))
    description: Mapped[str] = mapped_column(Text)
    priority: Mapped[RepairPriority] = mapped_column(Enum(RepairPriority), default=RepairPriority.ROUTINE)
    is_emergency: Mapped[bool] = mapped_column(Boolean, default=False)
    reported_date: Mapped[date] = mapped_column(Date)
    contractor: Mapped[str | None] = mapped_column(String(255), nullable=True)
    completed_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    cost_pence: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[RepairStatus] = mapped_column(Enum(RepairStatus), default=RepairStatus.REPORTED)


class RepairRuleConfig(Base):
    """Per-organisation parameters for the Repeat Repair / Component
    Failure engine (app/operations/repeat_repair.py) — architecture §2:
    "window_months and threshold are per-organisation configurable...
    never hard-coded constants." One row per (organisation, rule_code),
    lazily seeded with defaults exactly like Sprint 7's ReferencePattern
    and Sprint 12's HandoverReadinessCheckWeight. Which fields apply
    depends on the rule: the two window-based rules use
    window_months/threshold; the cross-property model-trend rule uses
    threshold_ratio/min_installed_base instead — unused fields stay
    NULL for a given rule_code rather than forcing every rule into the
    same shape.
    """

    __tablename__ = "repair_rule_configs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organisation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.id"))
    rule_code: Mapped[str] = mapped_column(String(64))
    window_months: Mapped[int | None] = mapped_column(Integer, nullable=True)
    threshold: Mapped[int | None] = mapped_column(Integer, nullable=True)
    threshold_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)
    min_installed_base: Mapped[int | None] = mapped_column(Integer, nullable=True)
