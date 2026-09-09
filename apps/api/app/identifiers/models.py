"""Identifier & Reference Engine — architecture/03-development-domain.md §3.

Two completely separate identifier classes, never conflated in schema:

- ReferencePattern: internal, DataLume-generated references
  (PROP-000001, DEV-000001, ...). One row per (organisation, entity
  type), holding the configurable pattern string and the next sequence
  number — see identifiers/service.py's generate_reference for how the
  sequence is reserved atomically.
- ExternalReference: official/external identifiers (UPRN, planning
  reference, BSR reference, ...) that DataLume must never fabricate.
  The CHECK constraint below is the hard, structural version of that
  rule — belt-and-braces alongside identifiers/service.py never exposing
  a code path that could set source_type=SYSTEM_GENERATED on one of
  these rows. A SYSTEM_GENERATED external reference is not just
  discouraged, it is a constraint violation.
"""

import enum
import uuid

from sqlalchemy import CheckConstraint, Enum, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.core.provenance import ProvenanceMixin


class ExternalReferenceType(str, enum.Enum):
    UPRN = "UPRN"
    PLANNING_REFERENCE = "PLANNING_REFERENCE"
    BUILDING_CONTROL_REFERENCE = "BUILDING_CONTROL_REFERENCE"
    BSR_REFERENCE = "BSR_REFERENCE"
    DEVELOPER_PLOT_NUMBER = "DEVELOPER_PLOT_NUMBER"
    CONTRACTOR_REFERENCE = "CONTRACTOR_REFERENCE"
    MANUFACTURER_SERIAL_NUMBER = "MANUFACTURER_SERIAL_NUMBER"
    LAND_REGISTRY_REFERENCE = "LAND_REGISTRY_REFERENCE"
    EXTERNAL_APPROVAL_REFERENCE = "EXTERNAL_APPROVAL_REFERENCE"


class ExternalReference(Base, ProvenanceMixin):
    __tablename__ = "external_references"
    __table_args__ = (
        CheckConstraint(
            "source_type IN ('MANUAL', 'FILE_UPLOAD', 'API', 'INTEGRATION')",
            name="ck_external_reference_never_system_generated",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organisation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.id"))
    entity_type: Mapped[str] = mapped_column(String(64))
    entity_id: Mapped[str] = mapped_column(String(64))
    reference_type: Mapped[ExternalReferenceType] = mapped_column(Enum(ExternalReferenceType))
    value: Mapped[str] = mapped_column(String(255))


class ReferencePattern(Base):
    """One row per (organisation, entity_type). next_sequence is only ever
    read/written inside generate_reference's row-locked transaction —
    see identifiers/service.py."""

    __tablename__ = "reference_patterns"
    __table_args__ = (UniqueConstraint("organisation_id", "entity_type", name="uq_reference_pattern_org_entity"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organisation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.id"))
    entity_type: Mapped[str] = mapped_column(String(64))
    pattern: Mapped[str] = mapped_column(String(128))
    next_sequence: Mapped[int] = mapped_column(Integer, default=1)
    is_active: Mapped[bool] = mapped_column(default=True)
