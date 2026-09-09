"""Development hierarchy — architecture/03-development-domain.md §1.

DEVELOPMENT -> BUILDING -> FLOOR -> PROPERTY -> SPACE, every level except
Property optional (spec: "do not require every customer to use every
hierarchy level"). A property or building created standalone (no
development context — e.g. existing stock, or a managing agent with no
new-build data) is exactly as valid as one created through a full
development; that's why every parent FK below is nullable, not why they
were missing before Sprint 6 — Sprint 5 just hadn't built the parent
tables yet (see git history on this file for that note).

Every field inherited from ProvenanceMixin (source_type,
source_dataset_id, import_job_id, created_by, ...) is genuinely
populated — Property/Space were the mixin's first consumers (Sprint 5),
Development/Building/Floor are new consumers this sprint.
"""

import enum
import uuid
from datetime import date

from sqlalchemy import CheckConstraint, Date, Enum, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.core.provenance import ProvenanceMixin


class DevelopmentStatus(str, enum.Enum):
    CONCEPT = "CONCEPT"
    DESIGN = "DESIGN"
    PRE_CONSTRUCTION = "PRE_CONSTRUCTION"
    CONSTRUCTION = "CONSTRUCTION"
    HANDOVER = "HANDOVER"
    COMPLETED = "COMPLETED"
    OPERATIONAL = "OPERATIONAL"
    CANCELLED = "CANCELLED"


class BuildingStatus(str, enum.Enum):
    PLANNED = "PLANNED"
    UNDER_CONSTRUCTION = "UNDER_CONSTRUCTION"
    COMPLETED = "COMPLETED"
    OPERATIONAL = "OPERATIONAL"


class PropertyStatus(str, enum.Enum):
    PLANNED = "PLANNED"
    UNDER_CONSTRUCTION = "UNDER_CONSTRUCTION"
    READY_FOR_HANDOVER = "READY_FOR_HANDOVER"
    HANDED_OVER = "HANDED_OVER"
    OPERATIONAL = "OPERATIONAL"
    VOID = "VOID"
    OCCUPIED = "OCCUPIED"
    DISPOSED = "DISPOSED"


# External/official identifiers (planning reference, building control
# reference, BSR reference, UPRN) live in app.identifiers.models.
# ExternalReference, not as columns here — architecture 03 §3's
# external_references model, formalised in Sprint 7. Earlier sprints had
# plain nullable columns for these as an honest interim version of the
# same rule; this is the real one, with the hard write-path constraint
# (identifiers/service.py.record_external_reference can never set
# source_type=SYSTEM_GENERATED on one).


class Development(Base, ProvenanceMixin):
    __tablename__ = "developments"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organisation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.id"))
    development_reference: Mapped[str] = mapped_column(String(32))
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    address: Mapped[str | None] = mapped_column(String(500), nullable=True)
    postcode: Mapped[str | None] = mapped_column(String(16), nullable=True)
    region: Mapped[str | None] = mapped_column(String(128), nullable=True)
    developer: Mapped[str | None] = mapped_column(String(255), nullable=True)
    principal_designer: Mapped[str | None] = mapped_column(String(255), nullable=True)
    principal_contractor: Mapped[str | None] = mapped_column(String(255), nullable=True)
    employer_agent: Mapped[str | None] = mapped_column(String(255), nullable=True)
    number_of_planned_properties: Mapped[int | None] = mapped_column(Integer, nullable=True)
    planned_start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    planned_completion_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    actual_completion_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[DevelopmentStatus] = mapped_column(Enum(DevelopmentStatus), default=DevelopmentStatus.CONCEPT)


class Building(Base, ProvenanceMixin):
    __tablename__ = "buildings"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organisation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.id"))
    development_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("developments.id"), nullable=True)
    building_reference: Mapped[str] = mapped_column(String(32))
    name: Mapped[str] = mapped_column(String(255))
    building_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    address: Mapped[str | None] = mapped_column(String(500), nullable=True)
    height: Mapped[float | None] = mapped_column(Float, nullable=True)
    storeys: Mapped[int | None] = mapped_column(Integer, nullable=True)
    construction_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    planned_completion: Mapped[date | None] = mapped_column(Date, nullable=True)
    actual_completion: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[BuildingStatus] = mapped_column(Enum(BuildingStatus), default=BuildingStatus.PLANNED)


class Floor(Base, ProvenanceMixin):
    __tablename__ = "floors"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organisation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.id"))
    building_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("buildings.id"))
    name: Mapped[str] = mapped_column(String(64))
    level_index: Mapped[int | None] = mapped_column(Integer, nullable=True)


class Property(Base, ProvenanceMixin):
    __tablename__ = "properties"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organisation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.id"))
    development_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("developments.id"), nullable=True)
    building_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("buildings.id"), nullable=True)
    floor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("floors.id"), nullable=True)
    property_reference: Mapped[str] = mapped_column(String(32))
    address: Mapped[str] = mapped_column(String(500))
    postcode: Mapped[str | None] = mapped_column(String(16), nullable=True)
    property_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[PropertyStatus] = mapped_column(Enum(PropertyStatus), default=PropertyStatus.OPERATIONAL)


class Space(Base, ProvenanceMixin):
    __tablename__ = "spaces"
    __table_args__ = (
        CheckConstraint("property_id IS NOT NULL OR building_id IS NOT NULL", name="ck_space_has_a_parent"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organisation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.id"))
    # A space is a room/unit inside a property OR a communal area
    # belonging directly to a building (spec: "spaces(... property_id
    # NULL, building_id NULL ...)") — never neither, enforced above.
    property_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("properties.id"), nullable=True)
    building_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("buildings.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(255))
    space_type: Mapped[str | None] = mapped_column(String(64), nullable=True)


class ComponentStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    REPLACED = "REPLACED"
    DISPOSED = "DISPOSED"


class ComponentType(Base):
    """Seeded taxonomy, org-extensible — spec §22. organisation_id NULL
    is the global seeded catalog (visible to every org, same pattern as
    system roles/plans); a non-NULL row is one org's own custom addition,
    e.g. an unrecognised type auto-created during CSV import
    (app/development/importers.py) rather than hard-failing the row."""

    __tablename__ = "component_types"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organisation_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("organisations.id"), nullable=True)
    code: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(128))
    parent_type_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("component_types.id"), nullable=True)


class Component(Base, ProvenanceMixin):
    """architecture/03-development-domain.md §2. Can attach to any
    combination of development/building/property/space (spec §24: not a
    strict single-parent tree the way Property's hierarchy is — a lift
    might belong to a building with no specific property, for instance)
    plus an optional parent_component_id for the HEATING SYSTEM -> BOILER
    -> PUMP -> CONTROL style hierarchy from spec §24.

    serial_number is NOT a column here — it's a manufacturer-supplied
    external identifier (app.identifiers.models.ExternalReferenceType.
    MANUFACTURER_SERIAL_NUMBER), same reasoning as Property.uprn since
    Sprint 7: spec §25 "never confuse internal component codes with
    manufacturer serial numbers" is enforced by them literally living in
    different tables, not just different columns.

    indicative_replacement_date is computed once, at write time, from
    installation_date + expected_life_years (see
    app/development/service.py.create_component) — a real but partial
    version of spec §26's Component Lifecycle Intelligence, which also
    factors in condition/repair/failure signals that don't exist until
    Repairs (Sprint 14) and Stock Condition (Sprint 18) land. Recomputing
    it against those signals is that later sprint's job, not this one's.
    """

    __tablename__ = "components"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organisation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.id"))
    development_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("developments.id"), nullable=True)
    building_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("buildings.id"), nullable=True)
    property_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("properties.id"), nullable=True)
    space_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("spaces.id"), nullable=True)
    parent_component_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("components.id"), nullable=True)
    component_reference: Mapped[str] = mapped_column(String(32))
    component_type_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("component_types.id"))
    component_subtype: Mapped[str | None] = mapped_column(String(128), nullable=True)
    manufacturer: Mapped[str | None] = mapped_column(String(255), nullable=True)
    model: Mapped[str | None] = mapped_column(String(255), nullable=True)
    installer: Mapped[str | None] = mapped_column(String(255), nullable=True)
    installation_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    commissioning_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    warranty_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    warranty_expiry: Mapped[date | None] = mapped_column(Date, nullable=True)
    expected_life_years: Mapped[int | None] = mapped_column(Integer, nullable=True)
    indicative_replacement_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[ComponentStatus] = mapped_column(Enum(ComponentStatus), default=ComponentStatus.ACTIVE)
