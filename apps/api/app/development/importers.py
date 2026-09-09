"""Registers this module's canonical-entity importer into the ingestion
pipeline's seam (app/ingestion/pipeline.py IMPORTERS, left empty in
Sprint 3 because nothing existed to import into). Importing this module
is what performs the registration — see app/main.py, which imports it
once at startup specifically for this side effect. This is the first
IMPORTERS entry; it's what makes Sprint 3's "honest no-op" import_dataset
path actually create something for dataset_type == "PROPERTIES".
"""

import uuid

from sqlalchemy.orm import Session

from app.core.provenance import SourceType
from app.development.service import create_property
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


IMPORTERS["PROPERTIES"] = import_property_row
