"""Compliance Framework — architecture/04-operations-domain.md §3, spec
§45-46. "FRAMEWORK -> DOMAIN -> REQUIREMENT -> APPLICABILITY -> BUILDING/
PROPERTY/COMPONENT -> INSPECTION -> EVIDENCE -> ACTION -> DEADLINE ->
STATUS -> RISK -> ASSURANCE -> AUDIT." Sprint 15 built the first four
links (Framework/Domain/Requirement/Applicability). Sprint 16 adds
Inspection and ComplianceAction below — the STATUS engine that reads
them (deterministic, never LLM-set — spec §47) is still Sprint 17
(Compliance Assurance), per the roadmap's own split.

`ComplianceFramework`/`ComplianceDomain`/`ComplianceRequirement` all
reuse the exact global+org-specific catalog pattern `ComponentType`
established in Sprint 8: organisation_id NULL is the DataLume-seeded
default, a non-NULL row is one org's own addition — "an org add/rename
a domain... without a migration" (architecture §3), not a claim that
every org shares one rigid table.
"""

import enum
import uuid
from datetime import date

from sqlalchemy import Date, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.core.provenance import ProvenanceMixin


class ComplianceFramework(Base):
    __tablename__ = "compliance_frameworks"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organisation_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("organisations.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(255))
    version: Mapped[int] = mapped_column(Integer, default=1)


class ComplianceDomain(Base):
    """The 21 spec §45 domains are seeded rows here (app/operations/
    compliance/seed.py), not an enum and not 21 tables (architecture
    §3's explicit decision) — "these are configurable domains, NOT a
    claim of exactly 21 universal laws.\""""

    __tablename__ = "compliance_domains"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organisation_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("organisations.id"), nullable=True)
    framework_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("compliance_frameworks.id"))
    code: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)


class ComplianceRequirement(Base):
    """Versioned, never edited in place (spec §31: "do not hard-code
    permanent interpretations of evolving Building Regulations") — a new
    version is a new row sharing (organisation_id, domain_id, code) with
    `version` incremented and the prior row's superseded_date set, same
    append-only pattern as Specification (Sprint 9). `code` scoped to
    (organisation_id, domain_id) is the lineage key across versions —
    a stable regulatory identifier (e.g. "GAS-001"), not a title that
    could coincidentally repeat, so no separate lineage_id column is
    needed the way Specification/Document required one.

    No default requirements are seeded alongside the 21 domains: unlike
    the domain names themselves (a stable taxonomy spec §45 names
    explicitly), specific requirement text/cadence is real regulatory
    content this build has no authoritative source for — inventing
    plausible-sounding obligations would be exactly the kind of
    fabricated compliance interpretation spec §31/§47 warns against.
    Each org (or a future curated DataLume content set) adds real
    requirements under the seeded domains.
    """

    __tablename__ = "compliance_requirements"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organisation_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("organisations.id"), nullable=True)
    domain_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("compliance_domains.id"))
    code: Mapped[str] = mapped_column(String(64))
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    cadence: Mapped[str | None] = mapped_column(String(64), nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    effective_date: Mapped[date] = mapped_column(Date)
    superseded_date: Mapped[date | None] = mapped_column(Date, nullable=True)


class RequirementApplicability(Base):
    """"APPLICABILITY -> BUILDING/PROPERTY/COMPONENT" (spec §46) — a
    requirement applying to one specific entity for a date range, e.g.
    "the Gas Safety requirement applies to Building X from 2024-01-01."
    Always organisation-scoped for real (never a NULL global row like
    its parents) — applicability is inherently about one org's own
    assets."""

    __tablename__ = "requirement_applicability"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organisation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.id"))
    requirement_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("compliance_requirements.id"))
    entity_type: Mapped[str] = mapped_column(String(64))
    entity_id: Mapped[str] = mapped_column(String(64))
    applicable_from: Mapped[date] = mapped_column(Date)
    applicable_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    basis: Mapped[str | None] = mapped_column(String(255), nullable=True)


class InspectionResult(str, enum.Enum):
    """UK compliance certification's usual pass/fail/advisory shape (e.g.
    a Gas Safety Certificate's "satisfactory"/"unsatisfactory" outcome) —
    a generic operational categorisation, not a claim about any specific
    regulatory scheme's own terminology."""

    SATISFACTORY = "SATISFACTORY"
    UNSATISFACTORY = "UNSATISFACTORY"
    ADVISORY = "ADVISORY"


class Inspection(Base, ProvenanceMixin):
    """"APPLICABILITY -> BUILDING/PROPERTY/COMPONENT -> INSPECTION ->
    EVIDENCE -> ACTION" (models.py module docstring) — the first Sprint
    16 link. `entity_type`/`entity_id` mirror `RequirementApplicability`
    rather than pointing back at an applicability row, since an
    inspection is itself a fact about one entity+requirement — it can be
    recorded even before applicability is formally configured (spec
    doesn't require the two to be pre-linked).

    `evidence_document_id` is a plain FK to an already-uploaded Document
    (POST /api/v1/documents, then reference its id here) — same
    two-step "upload separately, then link" flow as every other
    evidence_document_id column in this sprint, not a bespoke inline
    upload endpoint.
    """

    __tablename__ = "inspections"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organisation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.id"))
    requirement_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("compliance_requirements.id"))
    entity_type: Mapped[str] = mapped_column(String(64))
    entity_id: Mapped[str] = mapped_column(String(64))
    inspector: Mapped[str] = mapped_column(String(255))
    inspection_date: Mapped[date] = mapped_column(Date)
    result: Mapped[InspectionResult] = mapped_column(Enum(InspectionResult))
    next_due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    evidence_document_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("documents.id"), nullable=True)


class ComplianceActionStatus(str, enum.Enum):
    OPEN = "OPEN"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class ComplianceAction(Base, ProvenanceMixin):
    """"...ACTION -> DEADLINE -> STATUS" — a remedial action arising from
    an inspection (`inspection_id` set) or raised independently
    (`inspection_id` NULL, e.g. a self-reported gap ahead of any
    inspection). `status`/`deadline` here are this sprint's own
    OPEN/COMPLETED/CANCELLED workflow state — the deterministic
    `compliance_status` *engine* that reads these (OVERDUE_ACTION,
    OPEN_ACTION, ...) is Sprint 17, not this table.
    """

    __tablename__ = "compliance_actions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organisation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.id"))
    inspection_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("inspections.id"), nullable=True)
    requirement_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("compliance_requirements.id"))
    entity_type: Mapped[str] = mapped_column(String(64))
    entity_id: Mapped[str] = mapped_column(String(64))
    description: Mapped[str] = mapped_column(Text)
    deadline: Mapped[date] = mapped_column(Date)
    status: Mapped[ComplianceActionStatus] = mapped_column(Enum(ComplianceActionStatus), default=ComplianceActionStatus.OPEN)
    completed_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    evidence_document_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("documents.id"), nullable=True)
