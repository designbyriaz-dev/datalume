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
from datetime import date, datetime

from sqlalchemy import JSON, Boolean, CheckConstraint, Date, DateTime, Enum, Float, ForeignKey, Integer, String, Text
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


class SpecificationStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    SUPERSEDED = "SUPERSEDED"


class Specification(Base, ProvenanceMixin):
    """architecture/03-development-domain.md §4 — spec §27. Attaches to a
    development, building, property, space, or component via a plain
    polymorphic (related_entity_type, related_entity_id) pair, same
    pattern as Document (app/documents/models.py) rather than five
    nullable FK columns, since exactly one of those five is ever set for
    a specification (unlike Component, which can genuinely attach at
    several levels at once).

    Versioning mirrors Document's append-only model exactly: a new
    revision is a NEW row sharing lineage_id and specification_reference
    with row 1, never an in-place edit — the prior row is only ever
    marked SUPERSEDED with superseded_date set (see
    app/development/service.py.create_specification_revision). "A change
    must NOT simply overwrite the previous specification" (spec §26).

    approved_by/approved_at stay NULL until a real approval action is
    taken (app/development/service.py.approve_specification) — never
    defaulted to the creator, same reasoning as Component's serial number
    living outside the write-path-constrained columns: an unapproved
    specification must not be mistakable for an approved one.
    """

    __tablename__ = "specifications"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organisation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.id"))
    lineage_id: Mapped[uuid.UUID] = mapped_column()
    specification_reference: Mapped[str] = mapped_column(String(32))
    related_entity_type: Mapped[str] = mapped_column(String(64))
    related_entity_id: Mapped[str] = mapped_column(String(64))
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    revision: Mapped[str] = mapped_column(String(32), default="A")
    status: Mapped[SpecificationStatus] = mapped_column(Enum(SpecificationStatus), default=SpecificationStatus.ACTIVE)
    effective_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    superseded_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    related_component_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    source_document_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("documents.id"), nullable=True)
    approved_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ChangeControlStatus(str, enum.Enum):
    PROPOSED = "PROPOSED"
    UNDER_REVIEW = "UNDER_REVIEW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    IMPLEMENTED = "IMPLEMENTED"
    CANCELLED = "CANCELLED"


class ChangeControl(Base, ProvenanceMixin):
    """architecture/03-development-domain.md §7, spec §33 — CHANGE CONTROL
    REGISTER. "A change must NOT simply overwrite the previous
    specification."

    BUILD_PROMPT.md §33 sketches change_control with its own
    development_id/building_id/property_id/component_id columns
    alongside previous_value/proposed_value, but those are marked
    "Conceptual fields", not literal DDL — duplicating Specification's
    own (related_entity_type, related_entity_id) here as four more
    nullable FKs would let a change's recorded location drift out of
    sync with the specification it's actually revising. Instead every
    change targets exactly one specification_id, and related_entity_type/
    related_entity_id are copied from that specification at submission
    time (immutable snapshot, not a live join) purely so list/filter
    queries don't need to join through specifications — the same
    "compose, don't duplicate" reasoning as Golden Thread (§4), applied
    to writes instead of reads.

    previous_value is captured automatically from the target
    specification's current fields at submission time — never supplied
    by the caller — so it stays a trustworthy record of what was
    actually being changed, independent of whatever the specification
    itself looks like by the time this row is read later.

    Approval and implementation are deliberately two different actions
    (app/development/service.py.approve_change_control vs.
    implement_change_control): approving is a decision (approved_by/
    approved_date recorded), implementing is the action that actually
    calls create_specification_revision using proposed_value and records
    which new Specification row resulted
    (implemented_specification_id) — matching the architecture's "on
    approval, a new specifications row is created" while still giving
    the six distinct statuses spec §33 asks for (a real workflow can
    approve now and implement at a scheduled cutover later).
    """

    __tablename__ = "change_controls"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organisation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.id"))
    change_reference: Mapped[str] = mapped_column(String(32))
    specification_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("specifications.id"))
    related_entity_type: Mapped[str] = mapped_column(String(64))
    related_entity_id: Mapped[str] = mapped_column(String(64))
    previous_value: Mapped[dict] = mapped_column(JSON)
    proposed_value: Mapped[dict] = mapped_column(JSON)
    reason: Mapped[str] = mapped_column(Text)
    impact_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[ChangeControlStatus] = mapped_column(Enum(ChangeControlStatus), default=ChangeControlStatus.PROPOSED)
    approved_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    approved_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    implemented_specification_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("specifications.id"), nullable=True
    )


class DefectSeverity(str, enum.Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class DefectStatus(str, enum.Enum):
    OPEN = "OPEN"
    ASSIGNED = "ASSIGNED"
    IN_PROGRESS = "IN_PROGRESS"
    READY_FOR_INSPECTION = "READY_FOR_INSPECTION"
    COMPLETED = "COMPLETED"
    REJECTED = "REJECTED"
    CLOSED = "CLOSED"


class Defect(Base, ProvenanceMixin):
    """DEFECT & SNAGGING REGISTER — spec §34. Attaches like Component
    (app/development/models.py.Component), not like Specification: any
    combination of development/building/property/component, independent
    and non-cross-validated, since a defect can genuinely be reported
    at whichever level it was actually observed at (spec §24's same
    reasoning — "not a strict single-parent tree").

    `evidence` from the spec's conceptual field list isn't a column —
    photos/reports attach the same way Construction Evidence does
    (Sprint 10): a Document with related_entity_type="defect".

    estimated_cost/actual_cost are stored in pence (integer), never a
    float — same reasoning as Plan pricing (app/platform/billing.py).
    """

    __tablename__ = "defects"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organisation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.id"))
    defect_reference: Mapped[str] = mapped_column(String(32))
    development_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("developments.id"), nullable=True)
    building_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("buildings.id"), nullable=True)
    property_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("properties.id"), nullable=True)
    component_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("components.id"), nullable=True)
    category: Mapped[str] = mapped_column(String(128))
    description: Mapped[str] = mapped_column(Text)
    severity: Mapped[DefectSeverity] = mapped_column(Enum(DefectSeverity), default=DefectSeverity.MEDIUM)
    reported_date: Mapped[date] = mapped_column(Date)
    contractor: Mapped[str | None] = mapped_column(String(255), nullable=True)
    responsible_party: Mapped[str | None] = mapped_column(String(255), nullable=True)
    target_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    completion_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[DefectStatus] = mapped_column(Enum(DefectStatus), default=DefectStatus.OPEN)
    estimated_cost_pence: Mapped[int | None] = mapped_column(Integer, nullable=True)
    actual_cost_pence: Mapped[int | None] = mapped_column(Integer, nullable=True)
    warranty_related: Mapped[bool] = mapped_column(Boolean, default=False)


class WarrantyStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    VOID = "VOID"


class Warranty(Base, ProvenanceMixin):
    """WARRANTY REGISTER — spec §36. Same independent, non-cross-
    validated attachment pattern as Defect/Component.

    status only ever tracks ACTIVE/VOID, set by an explicit action
    (app/development/service.py.void_warranty) — "EXPIRED" is
    deliberately not a stored status a job has to keep in sync. It's
    computed from expiry_date at read time (WarrantyOut.is_expired,
    days_until_expiry), same "deterministic, computed at read time"
    approach as Component.indicative_replacement_date and Data Health's
    score — never a value that can go stale between writes.

    "Generate configurable alerts before expiry" (spec §36) is served by
    GET /api/v1/warranties?expiring_within_days=N — the caller/UI
    controls the window, since there's no notification/email
    infrastructure in this codebase to push an alert through (same
    honest-scoping reasoning as StripeBillingProvider being deferred in
    Sprint 2: nothing here fabricates a delivery mechanism that isn't
    actually wired to anything).
    """

    __tablename__ = "warranties"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organisation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.id"))
    warranty_reference: Mapped[str] = mapped_column(String(32))
    provider: Mapped[str] = mapped_column(String(255))
    development_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("developments.id"), nullable=True)
    building_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("buildings.id"), nullable=True)
    property_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("properties.id"), nullable=True)
    component_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("components.id"), nullable=True)
    warranty_type: Mapped[str] = mapped_column(String(128))
    start_date: Mapped[date] = mapped_column(Date)
    expiry_date: Mapped[date] = mapped_column(Date)
    terms_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    document_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("documents.id"), nullable=True)
    status: Mapped[WarrantyStatus] = mapped_column(Enum(WarrantyStatus), default=WarrantyStatus.ACTIVE)
