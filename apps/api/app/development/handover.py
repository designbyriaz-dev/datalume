"""Handover Readiness Engine — architecture/03-development-domain.md §8,
spec §37. A registry of independent, weighted checks over a
development's properties/components — same shape as Data Health's rule
registry (Sprint 5), but weighted and per-org configurable rather than
an unweighted mean, because spec §37 calls that out explicitly ("all
scoring methodology must be transparent/configurable") as core to this
engine, not a later enhancement the way Data Health's weighting was.

Ten checks are named in spec §37's own list. Nine are implemented as
independent registry entries below. "Outstanding remedial actions" is
deliberately not a tenth: there is no remedial-action table yet (that
concept belongs to Compliance Operations, Sprint 16) — adding a check
that always passes would be dishonest, so it's simply absent, and the
active checks' weights are renormalised to still sum to 100%. "Missing
evidence" and "Data-quality problems" from the same list aren't
separate checks either — they're what checks 3-6 (component fields,
warranties, certificates, commissioning evidence) and the existing Data
Health module (Sprint 5) already cover.
"""

import uuid
from dataclasses import dataclass, field

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.development.models import Building, Component, Defect, DefectStatus, Floor, Property, Warranty
from app.documents.models import Document
from app.identifiers.service import get_external_references_bulk

OPEN_DEFECT_STATUSES = (
    DefectStatus.OPEN,
    DefectStatus.ASSIGNED,
    DefectStatus.IN_PROGRESS,
    DefectStatus.READY_FOR_INSPECTION,
)

DEFAULT_CHECK_WEIGHTS: dict[str, float] = {
    "PROPERTIES_CREATED": 0.10,
    "COMPONENTS_CAPTURED": 0.15,
    "REQUIRED_COMPONENT_FIELDS": 0.10,
    "WARRANTIES_RECEIVED": 0.15,
    "CERTIFICATES_RECEIVED": 0.15,
    "COMMISSIONING_EVIDENCE": 0.10,
    "OM_DOCUMENTATION": 0.05,
    "BUILDING_CONTROL_REFERENCE": 0.10,
    "OUTSTANDING_DEFECTS": 0.05,
}
CHECK_LABELS: dict[str, str] = {
    "PROPERTIES_CREATED": "Properties created",
    "COMPONENTS_CAPTURED": "Components captured",
    "REQUIRED_COMPONENT_FIELDS": "Required component fields present",
    "WARRANTIES_RECEIVED": "Warranties received",
    "CERTIFICATES_RECEIVED": "Certificates received",
    "COMMISSIONING_EVIDENCE": "Commissioning evidence received",
    "OM_DOCUMENTATION": "O&M documentation received",
    "BUILDING_CONTROL_REFERENCE": "Building Control references captured",
    "OUTSTANDING_DEFECTS": "No outstanding defects",
}


@dataclass
class HandoverCheckResult:
    check_code: str
    label: str
    weight: float
    applicable_count: int
    failing_count: int
    missing_items: list[str] = field(default_factory=list)

    @property
    def pass_ratio(self) -> float:
        if self.applicable_count == 0:
            return 1.0
        return (self.applicable_count - self.failing_count) / self.applicable_count


def properties_in_development(db: Session, organisation_id: uuid.UUID, development_id: uuid.UUID) -> list[Property]:
    building_ids = [
        row[0]
        for row in db.query(Building.id).filter(
            Building.development_id == development_id, Building.organisation_id == organisation_id
        )
    ]
    floor_ids = (
        [row[0] for row in db.query(Floor.id).filter(Floor.building_id.in_(building_ids))] if building_ids else []
    )
    conditions = [Property.development_id == development_id]
    if building_ids:
        conditions.append(Property.building_id.in_(building_ids))
    if floor_ids:
        conditions.append(Property.floor_id.in_(floor_ids))
    return db.query(Property).filter(Property.organisation_id == organisation_id, or_(*conditions)).all()


def _components_in_scope(
    db: Session, organisation_id: uuid.UUID, development_id: uuid.UUID, property_ids: list[uuid.UUID]
) -> list[Component]:
    building_ids = [
        row[0]
        for row in db.query(Building.id).filter(
            Building.development_id == development_id, Building.organisation_id == organisation_id
        )
    ]
    conditions = [Component.development_id == development_id]
    if building_ids:
        conditions.append(Component.building_id.in_(building_ids))
    if property_ids:
        conditions.append(Component.property_id.in_(property_ids))
    return db.query(Component).filter(Component.organisation_id == organisation_id, or_(*conditions)).all()


def _document_types_by_entity(
    db: Session, organisation_id: uuid.UUID, entity_type: str, entity_ids: list[uuid.UUID], contains: str
) -> set[str]:
    """entity_ids that have at least one Document of this entity_type
    whose document_type contains `contains` (case-insensitive)."""
    if not entity_ids:
        return set()
    docs = (
        db.query(Document.related_entity_id, Document.document_type)
        .filter(
            Document.organisation_id == organisation_id,
            Document.related_entity_type == entity_type,
            Document.related_entity_id.in_([str(i) for i in entity_ids]),
        )
        .all()
    )
    return {entity_id for entity_id, document_type in docs if contains.lower() in document_type.lower()}


def check_properties_created(properties: list[Property]) -> HandoverCheckResult:
    failing = 0 if properties else 1
    missing = [] if properties else ["No properties recorded for this development"]
    return HandoverCheckResult("PROPERTIES_CREATED", CHECK_LABELS["PROPERTIES_CREATED"], 0, 1, failing, missing)


def check_components_captured(db: Session, organisation_id: uuid.UUID, properties: list[Property]) -> HandoverCheckResult:
    property_ids = [p.id for p in properties]
    covered = {
        row[0]
        for row in db.query(Component.property_id).filter(Component.property_id.in_(property_ids)).distinct()
    }
    failing = len(property_ids) - len(covered)
    missing = [f"{failing} properties have no components recorded"] if failing else []
    return HandoverCheckResult(
        "COMPONENTS_CAPTURED", CHECK_LABELS["COMPONENTS_CAPTURED"], 0, len(property_ids), failing, missing
    )


def check_required_component_fields(
    db: Session, organisation_id: uuid.UUID, components: list[Component]
) -> HandoverCheckResult:
    component_ids = [c.id for c in components]
    serials = get_external_references_bulk(db, organisation_id, "component", component_ids)
    missing_install_date = sum(1 for c in components if c.installation_date is None)
    missing_manufacturer_or_model = sum(1 for c in components if not c.manufacturer and not c.model)
    missing_serial = sum(1 for c in components if "MANUFACTURER_SERIAL_NUMBER" not in serials.get(str(c.id), {}))
    failing_ids = {
        c.id
        for c in components
        if c.installation_date is None
        or (not c.manufacturer and not c.model)
        or "MANUFACTURER_SERIAL_NUMBER" not in serials.get(str(c.id), {})
    }
    missing = []
    if missing_install_date:
        missing.append(f"{missing_install_date} components missing an installation date")
    if missing_manufacturer_or_model:
        missing.append(f"{missing_manufacturer_or_model} components missing manufacturer/model")
    if missing_serial:
        missing.append(f"{missing_serial} components missing a serial number")
    return HandoverCheckResult(
        "REQUIRED_COMPONENT_FIELDS",
        CHECK_LABELS["REQUIRED_COMPONENT_FIELDS"],
        0,
        len(components),
        len(failing_ids),
        missing,
    )


def check_warranties_received(db: Session, organisation_id: uuid.UUID, components: list[Component]) -> HandoverCheckResult:
    component_ids = [c.id for c in components]
    covered = (
        {row[0] for row in db.query(Warranty.component_id).filter(Warranty.component_id.in_(component_ids)).distinct()}
        if component_ids
        else set()
    )
    failing = len(component_ids) - len(covered)
    missing = [f"{failing} component warranties missing"] if failing else []
    return HandoverCheckResult(
        "WARRANTIES_RECEIVED", CHECK_LABELS["WARRANTIES_RECEIVED"], 0, len(component_ids), failing, missing
    )


def check_certificates_received(db: Session, organisation_id: uuid.UUID, components: list[Component]) -> HandoverCheckResult:
    component_ids = [c.id for c in components]
    covered = _document_types_by_entity(db, organisation_id, "component", component_ids, "CERTIFICATE")
    failing = len(component_ids) - len(covered)
    missing = [f"{failing} certificates missing"] if failing else []
    return HandoverCheckResult(
        "CERTIFICATES_RECEIVED", CHECK_LABELS["CERTIFICATES_RECEIVED"], 0, len(component_ids), failing, missing
    )


def check_commissioning_evidence(
    db: Session, organisation_id: uuid.UUID, components: list[Component]
) -> HandoverCheckResult:
    component_ids = [c.id for c in components]
    covered = _document_types_by_entity(db, organisation_id, "component", component_ids, "COMMISSIONING")
    failing = len(component_ids) - len(covered)
    missing = [f"{failing} commissioning records missing"] if failing else []
    return HandoverCheckResult(
        "COMMISSIONING_EVIDENCE", CHECK_LABELS["COMMISSIONING_EVIDENCE"], 0, len(component_ids), failing, missing
    )


def check_om_documentation(db: Session, organisation_id: uuid.UUID, development_id: uuid.UUID) -> HandoverCheckResult:
    # O&M documentation is normally issued once per development, not
    # once per property/component — a single development-level check,
    # not scaled by property count.
    covered = _document_types_by_entity(db, organisation_id, "development", [development_id], "O&M")
    failing = 0 if covered else 1
    missing = [] if covered else ["O&M documentation missing"]
    return HandoverCheckResult("OM_DOCUMENTATION", CHECK_LABELS["OM_DOCUMENTATION"], 0, 1, failing, missing)


def check_building_control_reference(
    db: Session, organisation_id: uuid.UUID, development_id: uuid.UUID
) -> HandoverCheckResult:
    buildings = db.query(Building).filter(
        Building.development_id == development_id, Building.organisation_id == organisation_id
    ).all()
    refs_by_id = get_external_references_bulk(db, organisation_id, "building", [b.id for b in buildings])
    failing = sum(1 for b in buildings if "BUILDING_CONTROL_REFERENCE" not in refs_by_id.get(str(b.id), {}))
    missing = [f"{failing} buildings missing a Building Control reference"] if failing else []
    return HandoverCheckResult(
        "BUILDING_CONTROL_REFERENCE",
        CHECK_LABELS["BUILDING_CONTROL_REFERENCE"],
        0,
        len(buildings),
        failing,
        missing,
    )


def check_outstanding_defects(
    db: Session, organisation_id: uuid.UUID, development_id: uuid.UUID, property_ids: list[uuid.UUID]
) -> HandoverCheckResult:
    conditions = [Defect.development_id == development_id]
    if property_ids:
        conditions.append(Defect.property_id.in_(property_ids))
    count = (
        db.query(Defect)
        .filter(Defect.organisation_id == organisation_id, or_(*conditions), Defect.status.in_(OPEN_DEFECT_STATUSES))
        .count()
    )
    failing = 1 if count else 0
    missing = [f"{count} outstanding defects"] if count else []
    return HandoverCheckResult("OUTSTANDING_DEFECTS", CHECK_LABELS["OUTSTANDING_DEFECTS"], 0, 1, failing, missing)


def get_check_weights(db, organisation_id: uuid.UUID) -> dict[str, float]:
    from app.development.service import get_or_create_handover_readiness_weight

    return {
        code: get_or_create_handover_readiness_weight(db, organisation_id, code, default).weight
        for code, default in DEFAULT_CHECK_WEIGHTS.items()
    }


def compute_handover_readiness(
    db: Session, organisation_id: uuid.UUID, development_id: uuid.UUID
) -> tuple[float, list[HandoverCheckResult]]:
    properties = properties_in_development(db, organisation_id, development_id)
    property_ids = [p.id for p in properties]
    components = _components_in_scope(db, organisation_id, development_id, property_ids)
    weights = get_check_weights(db, organisation_id)

    results = [
        check_properties_created(properties),
        check_components_captured(db, organisation_id, properties),
        check_required_component_fields(db, organisation_id, components),
        check_warranties_received(db, organisation_id, components),
        check_certificates_received(db, organisation_id, components),
        check_commissioning_evidence(db, organisation_id, components),
        check_om_documentation(db, organisation_id, development_id),
        check_building_control_reference(db, organisation_id, development_id),
        check_outstanding_defects(db, organisation_id, development_id, property_ids),
    ]
    for result in results:
        result.weight = weights.get(result.check_code, DEFAULT_CHECK_WEIGHTS[result.check_code])

    if not properties:
        # A development with zero properties recorded scores 0%, full
        # stop — not the weighted-average of eight checks that all
        # vacuously "pass" (HandoverCheckResult.pass_ratio is 1.0 when
        # applicable_count is 0) purely because there's nothing to check
        # yet. That vacuous-pass rule is correct and useful once real
        # properties/components exist and a given check genuinely has
        # nothing applicable to it; it would be actively misleading here.
        return 0.0, results

    total_weight = sum(r.weight for r in results) or 1.0
    score = sum(r.weight * r.pass_ratio for r in results) / total_weight * 100
    return round(score, 1), results
