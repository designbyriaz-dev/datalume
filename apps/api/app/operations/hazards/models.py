"""Hazards, damp & mould — architecture/04-operations-domain.md §5, spec
§49. Damp & mould is deliberately a `hazard_type` value on this one
table, not a parallel schema, so it goes through the same state machine
and repeat-occurrence detection as every other hazard category
(architecture's own explicit instruction).

`hazard_type` is a plain string, not an enum or FK — same reasoning as
`Repair.category`/`Defect.category` (Sprints 11/14): HHSRS's 29 official
hazard categories are a real UK regulatory taxonomy this build has no
authoritative source to hard-code as if canonical, so orgs record
whatever hazard_type they actually use (e.g. "DAMP_AND_MOULD",
"EXCESS_COLD", "CARBON_MONOXIDE") rather than being constrained to a
fabricated fixed list — the same non-fabrication stance Sprint 15 took
with compliance requirement content.

`status` is this table's own coarse workflow state — REPORTED through
CLOSED (see HAZARD_TRANSITIONS in service.py) — a deliberate
simplification of the spec's full named chain ("REPORTED -> TRIAGE ->
INVESTIGATION -> DEADLINE -> FINDING -> ACTION -> DEADLINE ->
COMPLETION -> EVIDENCE -> FOLLOW-UP -> CLOSED"): the ACTION/DEADLINE/
COMPLETION/EVIDENCE portion of that chain is carried by `HazardAction`
rows instead of extra `Hazard.status` values, the same way Compliance's
INSPECTION/ACTION pair splits "what was found" from "what's being done
about it" onto two tables rather than one long status enum.
`investigation_status` is a separate field from `status`: it's the
*outcome* of the investigation stage (was a hazard actually confirmed?)
recorded once alongside `findings`, not another step in the same
progression.
"""

import enum
import uuid
from datetime import date

from sqlalchemy import Date, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.core.provenance import ProvenanceMixin


class HazardSeverity(str, enum.Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class HazardInvestigationStatus(str, enum.Enum):
    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"
    NOT_CONFIRMED = "NOT_CONFIRMED"
    INCONCLUSIVE = "INCONCLUSIVE"


class HazardStatus(str, enum.Enum):
    REPORTED = "REPORTED"
    TRIAGED = "TRIAGED"
    INVESTIGATING = "INVESTIGATING"
    INVESTIGATED = "INVESTIGATED"
    ACTION_IN_PROGRESS = "ACTION_IN_PROGRESS"
    FOLLOW_UP = "FOLLOW_UP"
    CLOSED = "CLOSED"


class Hazard(Base, ProvenanceMixin):
    __tablename__ = "hazards"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organisation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.id"))
    property_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("properties.id"))
    hazard_type: Mapped[str] = mapped_column(String(128))
    reported_date: Mapped[date] = mapped_column(Date)
    severity: Mapped[HazardSeverity] = mapped_column(Enum(HazardSeverity), default=HazardSeverity.MEDIUM)
    investigation_status: Mapped[HazardInvestigationStatus] = mapped_column(
        Enum(HazardInvestigationStatus), default=HazardInvestigationStatus.PENDING
    )
    findings: Mapped[str | None] = mapped_column(Text, nullable=True)
    deadline: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[HazardStatus] = mapped_column(Enum(HazardStatus), default=HazardStatus.REPORTED)


class HazardActionStatus(str, enum.Enum):
    OPEN = "OPEN"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class HazardAction(Base):
    """Carries the spec chain's own ACTION -> DEADLINE -> COMPLETION ->
    EVIDENCE segment. `organisation_id` is added here even though the
    architecture's abbreviated SQL sketch for this one table omits it
    (unlike every sibling table's sketch, which lists it explicitly) —
    this codebase's RLS policies always filter on the table's own
    organisation_id column directly (no cross-table join), so every
    RLS-protected table needs it regardless of what a parent table
    already has.
    """

    __tablename__ = "hazard_actions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organisation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.id"))
    hazard_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("hazards.id"))
    description: Mapped[str] = mapped_column(Text)
    deadline: Mapped[date] = mapped_column(Date)
    status: Mapped[HazardActionStatus] = mapped_column(Enum(HazardActionStatus), default=HazardActionStatus.OPEN)
    completed_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    evidence_document_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("documents.id"), nullable=True)


class HazardRuleConfig(Base):
    """Per-organisation repeat-occurrence window/threshold for
    app/operations/hazards/repeat_hazard.py — same lazily-seeded,
    per-org configurable pattern as RepairRuleConfig (Sprint 14):
    "do not permanently hard-code evolving legal deadlines [or
    thresholds]" (spec §49) applies to detection sensitivity as much as
    to deadline calculation."""

    __tablename__ = "hazard_rule_configs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organisation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.id"))
    rule_code: Mapped[str] = mapped_column(String(64))
    window_months: Mapped[int] = mapped_column(Integer)
    threshold: Mapped[int] = mapped_column(Integer)
