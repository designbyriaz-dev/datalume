"""Registers the Housing Operations domain's CSV importers into the
ingestion pipeline's seam (app/ingestion/pipeline.py IMPORTERS) — spec
§77's "Upload repairs"/"Upload compliance", the two Housing Operations
Acceptance Test items that genuinely didn't exist on either side of the
stack (Post-Sprint-24 audit): repairs and compliance inspections could
only ever be entered one at a time through their manual forms. Same
registration mechanism as app/development/importers.py and
app/commercial/importers.py: importing this module performs the
registration as a side effect — see app/main.py.

Both importers resolve their linked entity by the DataLume-generated
reference (e.g. PROP-000001), the only stable identifier a CSV can
realistically carry — same reasoning as every other cross-reference
importer in this codebase.
"""

import uuid
from datetime import date

from sqlalchemy.orm import Session

from app.core.provenance import SourceType
from app.development.models import Building, Component, Property
from app.ingestion.models import Dataset, ImportJob, ImportRow
from app.ingestion.pipeline import IMPORTERS, ImporterRowError
from app.operations.compliance.models import ComplianceRequirement
from app.operations.compliance.service import create_inspection
from app.operations.service import create_repair


def _parse_iso_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value.strip())
    except ValueError:
        return None


def _find_property(db: Session, organisation_id: uuid.UUID, property_reference: str | None) -> Property | None:
    if not property_reference:
        return None
    return (
        db.query(Property)
        .filter(Property.organisation_id == organisation_id, Property.property_reference == property_reference.strip())
        .first()
    )


def _find_component(db: Session, organisation_id: uuid.UUID, component_reference: str | None) -> Component | None:
    if not component_reference:
        return None
    return (
        db.query(Component)
        .filter(Component.organisation_id == organisation_id, Component.component_reference == component_reference.strip())
        .first()
    )


def import_repair_row(
    db: Session, dataset: Dataset, import_job: ImportJob, row: ImportRow, mapped_fields: dict
) -> tuple[str, uuid.UUID]:
    # Required, not optional — Repair.property_id is a mandatory FK.
    property_reference = (mapped_fields.get("property_reference") or "").strip()
    if not property_reference:
        raise ImporterRowError("property_reference is required to import a repair")
    prop = _find_property(db, dataset.organisation_id, property_reference)
    if prop is None:
        raise ImporterRowError(f"No property found with reference {property_reference!r}")

    reported_date = _parse_iso_date(mapped_fields.get("reported_date"))
    if reported_date is None:
        raise ImporterRowError("reported_date is required and must be a valid ISO date")

    category = (mapped_fields.get("category") or "").strip()
    description = (mapped_fields.get("description") or "").strip()
    if not category or not description:
        raise ImporterRowError("category and description are both required to import a repair")

    # Optional — same permissiveness as BUILDINGS' development_reference:
    # a blank or unresolvable component_reference just leaves the repair
    # unlinked rather than failing the row.
    component = _find_component(db, dataset.organisation_id, mapped_fields.get("component_reference"))

    repair = create_repair(
        db,
        dataset.organisation_id,
        property_id=prop.id,
        component_id=component.id if component else None,
        category=category,
        description=description,
        reported_date=reported_date,
        priority=(mapped_fields.get("priority") or "ROUTINE").strip().upper() or "ROUTINE",
        contractor=mapped_fields.get("contractor") or None,
        source_type=SourceType.FILE_UPLOAD,
        source_dataset_id=dataset.id,
        import_job_id=import_job.id,
        original_reference=f"row {row.row_number}",
        actor_user_id=dataset.uploaded_by,
    )
    return "repair", repair.id


_ENTITY_FINDERS = {
    "property": lambda db, organisation_id, reference: (
        db.query(Property).filter(Property.organisation_id == organisation_id, Property.property_reference == reference).first()
    ),
    "building": lambda db, organisation_id, reference: (
        db.query(Building).filter(Building.organisation_id == organisation_id, Building.building_reference == reference).first()
    ),
    "component": lambda db, organisation_id, reference: (
        db.query(Component).filter(Component.organisation_id == organisation_id, Component.component_reference == reference).first()
    ),
}


def import_compliance_inspection_row(
    db: Session, dataset: Dataset, import_job: ImportJob, row: ImportRow, mapped_fields: dict
) -> tuple[str, uuid.UUID]:
    requirement_code = (mapped_fields.get("requirement_code") or "").strip()
    if not requirement_code:
        raise ImporterRowError("requirement_code is required to import a compliance inspection")
    requirement = (
        db.query(ComplianceRequirement)
        .filter(
            ComplianceRequirement.organisation_id == dataset.organisation_id,
            ComplianceRequirement.code == requirement_code,
            ComplianceRequirement.superseded_date.is_(None),
        )
        .first()
    )
    if requirement is None:
        raise ImporterRowError(f"No current compliance requirement found with code {requirement_code!r}")

    entity_type = (mapped_fields.get("entity_type") or "").strip().lower()
    if entity_type not in _ENTITY_FINDERS:
        raise ImporterRowError("entity_type must be one of property, building, component")
    entity_reference = (mapped_fields.get("entity_reference") or "").strip()
    if not entity_reference:
        raise ImporterRowError("entity_reference is required to import a compliance inspection")
    entity = _ENTITY_FINDERS[entity_type](db, dataset.organisation_id, entity_reference)
    if entity is None:
        raise ImporterRowError(f"No {entity_type} found with reference {entity_reference!r}")

    inspector = (mapped_fields.get("inspector") or "").strip()
    if not inspector:
        raise ImporterRowError("inspector is required to import a compliance inspection")
    inspection_date = _parse_iso_date(mapped_fields.get("inspection_date"))
    if inspection_date is None:
        raise ImporterRowError("inspection_date is required and must be a valid ISO date")
    result_raw = (mapped_fields.get("result") or "").strip().upper()
    if result_raw not in ("SATISFACTORY", "UNSATISFACTORY", "ADVISORY"):
        raise ImporterRowError(f"{result_raw!r} is not a recognised inspection result")

    inspection = create_inspection(
        db,
        dataset.organisation_id,
        requirement_id=requirement.id,
        entity_type=entity_type,
        entity_id=entity.id,
        inspector=inspector,
        inspection_date=inspection_date,
        result=result_raw,
        next_due_date=_parse_iso_date(mapped_fields.get("next_due_date")),
        evidence_document_id=None,
        actor_user_id=dataset.uploaded_by,
        source_type=SourceType.FILE_UPLOAD,
        source_dataset_id=dataset.id,
        import_job_id=import_job.id,
        original_reference=f"row {row.row_number}",
    )
    return "inspection", inspection.id


IMPORTERS["REPAIRS"] = import_repair_row
IMPORTERS["COMPLIANCE_INSPECTIONS"] = import_compliance_inspection_row
