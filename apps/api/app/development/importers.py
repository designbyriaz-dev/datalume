"""Registers this module's canonical-entity importers into the ingestion
pipeline's seam (app/ingestion/pipeline.py IMPORTERS, left empty in
Sprint 3 because nothing existed to import into). Importing this module
is what performs the registration — see app/main.py, which imports it
once at startup specifically for this side effect. PROPERTIES was the
first entry (Sprint 5); COMPONENTS is the second (Sprint 8) — it's what
finally closes the "honest no-op" case app/tests/test_ingestion.py used
COMPONENTS to demonstrate all the way back in Sprint 5's own test suite.
"""

import uuid
from datetime import date

from sqlalchemy.orm import Session

from app.core.provenance import SourceType
from app.development.component_types import ensure_component_type_catalog_seeded, get_or_create_org_component_type
from app.development.models import Development
from app.development.service import create_building, create_component, create_development, create_property
from app.ingestion.models import Dataset, ImportJob, ImportRow
from app.ingestion.pipeline import IMPORTERS


def import_property_row(
    db: Session, dataset: Dataset, import_job: ImportJob, row: ImportRow, mapped_fields: dict
) -> tuple[str, uuid.UUID]:
    prop = create_property(
        db,
        dataset.organisation_id,
        address=mapped_fields.get("address") or "",
        postcode=mapped_fields.get("postcode"),
        uprn=mapped_fields.get("uprn"),
        property_type=mapped_fields.get("property_type"),
        source_type=SourceType.FILE_UPLOAD,
        source_dataset_id=dataset.id,
        import_job_id=import_job.id,
        original_reference=f"row {row.row_number}",
        actor_user_id=dataset.uploaded_by,
    )
    return "property", prop.id


def _parse_int(value: str | None) -> int | None:
    if not value:
        return None
    try:
        return int(value.strip())
    except ValueError:
        return None


def import_development_row(
    db: Session, dataset: Dataset, import_job: ImportJob, row: ImportRow, mapped_fields: dict
) -> tuple[str, uuid.UUID]:
    dev = create_development(
        db,
        dataset.organisation_id,
        name=mapped_fields.get("name") or "",
        description=mapped_fields.get("description"),
        address=mapped_fields.get("address"),
        postcode=mapped_fields.get("postcode"),
        number_of_planned_properties=_parse_int(mapped_fields.get("number_of_planned_properties")),
        planning_reference=mapped_fields.get("planning_reference"),
        building_control_reference=mapped_fields.get("building_control_reference"),
        bsr_reference=mapped_fields.get("bsr_reference"),
        source_type=SourceType.FILE_UPLOAD,
        source_dataset_id=dataset.id,
        import_job_id=import_job.id,
        original_reference=f"row {row.row_number}",
        actor_user_id=dataset.uploaded_by,
    )
    return "development", dev.id


def import_building_row(
    db: Session, dataset: Dataset, import_job: ImportJob, row: ImportRow, mapped_fields: dict
) -> tuple[str, uuid.UUID]:
    # An optional link to an already-imported Development, matched by its
    # DataLume-generated reference (e.g. DEV-000001) — the only stable
    # identifier a CSV can realistically carry, since the underlying UUID
    # doesn't exist until that row was created. No match (blank, typo, or
    # imported out of order) leaves development_id unset rather than
    # failing the row — same permissiveness as PROPERTIES' importer,
    # which doesn't attempt a hierarchy link at all today.
    development_id = None
    dev_reference = mapped_fields.get("development_reference")
    if dev_reference:
        dev = (
            db.query(Development)
            .filter(Development.organisation_id == dataset.organisation_id, Development.development_reference == dev_reference.strip())
            .first()
        )
        if dev is not None:
            development_id = dev.id

    building = create_building(
        db,
        dataset.organisation_id,
        name=mapped_fields.get("name") or "",
        development_id=development_id,
        building_type=mapped_fields.get("building_type"),
        address=mapped_fields.get("address"),
        storeys=_parse_int(mapped_fields.get("storeys")),
        building_control_reference=mapped_fields.get("building_control_reference"),
        bsr_reference=mapped_fields.get("bsr_reference"),
        source_type=SourceType.FILE_UPLOAD,
        source_dataset_id=dataset.id,
        import_job_id=import_job.id,
        original_reference=f"row {row.row_number}",
        actor_user_id=dataset.uploaded_by,
    )
    return "building", building.id


def _parse_iso_date(value: str | None) -> date | None:
    # CSV dates arrive as free text. ISO format (YYYY-MM-DD) only for
    # now — flexible format detection/locale handling is real "cleaning"
    # work the architecture calls for (02 §6) and is left for whichever
    # sprint first needs it, same reasoning as everywhere else this
    # pipeline has drawn a line around scope.
    if not value:
        return None
    try:
        return date.fromisoformat(value.strip())
    except ValueError:
        return None


def import_component_row(
    db: Session, dataset: Dataset, import_job: ImportJob, row: ImportRow, mapped_fields: dict
) -> tuple[str, uuid.UUID]:
    # Must run before matching, not just before creating — a fresh org
    # (or a fresh test DB, which is how this was caught: see
    # test_csv_import_creates_components_and_custom_types) has no
    # component_types rows at all until something seeds them, and
    # find_component_type_by_name has nothing to match "Boiler" against
    # if the global "Boilers" row doesn't exist yet.
    ensure_component_type_catalog_seeded(db)
    type_name = mapped_fields.get("component_type") or "Other"
    component_type = get_or_create_org_component_type(db, dataset.organisation_id, type_name)

    component = create_component(
        db,
        dataset.organisation_id,
        component_type_id=component_type.id,
        manufacturer=mapped_fields.get("manufacturer"),
        model=mapped_fields.get("model"),
        serial_number=mapped_fields.get("serial_number"),
        installation_date=_parse_iso_date(mapped_fields.get("installation_date")),
        source_type=SourceType.FILE_UPLOAD,
        source_dataset_id=dataset.id,
        import_job_id=import_job.id,
        original_reference=f"row {row.row_number}",
        actor_user_id=dataset.uploaded_by,
    )
    return "component", component.id


IMPORTERS["PROPERTIES"] = import_property_row
IMPORTERS["COMPONENTS"] = import_component_row
IMPORTERS["DEVELOPMENTS"] = import_development_row
IMPORTERS["BUILDINGS"] = import_building_row
