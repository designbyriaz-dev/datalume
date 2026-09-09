"""Compliance Framework — architecture/04-operations-domain.md §3, spec
§45-46. "FRAMEWORK -> DOMAIN -> REQUIREMENT -> APPLICABILITY -> BUILDING/
PROPERTY/COMPONENT -> INSPECTION -> EVIDENCE -> ACTION -> DEADLINE ->
STATUS -> RISK -> ASSURANCE -> AUDIT." Sprint 15 builds the first four
links in that chain — everything from INSPECTION onward is Sprint 16
(Compliance Operations) and the STATUS engine is Sprint 17 (Compliance
Assurance), per the roadmap's own split.

`ComplianceFramework`/`ComplianceDomain`/`ComplianceRequirement` all
reuse the exact global+org-specific catalog pattern `ComponentType`
established in Sprint 8: organisation_id NULL is the DataLume-seeded
default, a non-NULL row is one org's own addition — "an org add/rename
a domain... without a migration" (architecture §3), not a claim that
every org shares one rigid table.
"""

import uuid
from datetime import date

from sqlalchemy import Date, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


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
