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
from app.development.service import create_component, create_property
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
