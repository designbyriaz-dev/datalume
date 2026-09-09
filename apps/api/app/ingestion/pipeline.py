"""The ingestion pipeline — architecture/02-data-platform.md §2.

UPLOAD -> VALIDATE -> UNDERSTAND -> MAP -> REVIEW -> IMPORT -> ANALYSE.

What's real in Sprint 3, and what's deliberately simplified:

- UPLOAD/VALIDATE/UNDERSTAND run synchronously inside the upload request
  (parse_csv -> validate_and_stage_rows -> propose_mapping), not as a
  background job. The architecture calls for a background-job pipeline
  specifically for performance at scale (spec §72) — that's a real
  requirement for large files, not yet met here. The DB shape (a
  persisted import_rows staging table, never a direct parse-and-insert)
  is exactly what the architecture specifies, so moving VALIDATE/
  UNDERSTAND into worker/jobs/ingestion.py behind an RQ enqueue later is
  a call-site change, not a data-model or pipeline-logic change.
- CSV only. XLSX/XLS (spec §13) need a real parsing library
  (openpyxl/Polars) — deferred rather than half-wired.
- IMPORT (committing staged rows into canonical domain entities) is a
  registered-importer seam (IMPORTERS dict below) that is empty in
  Sprint 3, because no canonical domain tables exist yet (those start
  Sprint 5). Running the import step today marks rows IMPORTED with no
  entity created — an honest no-op, not a fake success.
- Cleaning (spec §13/§76): whitespace trimming only, logged per-row.
  Number/date coercion is real "cleaning" work the architecture also
  calls for and is left for whichever sprint first needs it (property
  dates, component installation dates, ...) rather than implemented
  inconsistently now.
"""

import csv
import io
import re
from typing import Callable

from sqlalchemy.orm import Session

from app.ingestion.field_dictionary import get_field_dictionary
from app.ingestion.models import Dataset, DatasetStatus, ImportJob, ImportJobStatus, ImportRow, ImportRowStatus, MappingTemplate


class CsvParseError(ValueError):
    pass


class ParsedRow:
    """A raw CSV row after structural parsing. `structural_error` is set
    when the cell count doesn't match the header count (almost always an
    unescaped comma in an unquoted field) — `cells` is still the
    best-effort zip so the row is visible for review, but the pipeline
    must never treat a structurally-broken row's field values as
    trustworthy. This exists because an earlier version of this pipeline
    silently truncated/misaligned such rows into VALID, IMPORTED-looking
    data — caught by hand-testing against a real (accidentally
    malformed) CSV, not by the original test suite, which only used
    well-formed fixtures. See test_ragged_row_is_flagged_not_silently_misaligned."""

    def __init__(self, cells: dict[str, str], structural_error: str | None):
        self.cells = cells
        self.structural_error = structural_error


def parse_csv(raw_bytes: bytes) -> tuple[list[str], list[ParsedRow]]:
    try:
        text = raw_bytes.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise CsvParseError("File is not valid UTF-8 text") from exc

    reader = csv.reader(io.StringIO(text))
    rows = list(reader)
    if not rows:
        raise CsvParseError("File is empty")

    headers = [h.strip() for h in rows[0]]
    if not any(headers):
        raise CsvParseError("File has no column headers")

    data_rows: list[ParsedRow] = []
    for raw_row in rows[1:]:
        if not any(cell.strip() for cell in raw_row):
            continue  # skip fully-blank rows rather than staging noise

        structural_error = None
        if len(raw_row) != len(headers):
            structural_error = (
                f"Row has {len(raw_row)} values but {len(headers)} columns were expected "
                "(check for an unescaped comma in a field — it should be wrapped in quotes)"
            )
        padded = raw_row + [""] * (len(headers) - len(raw_row))
        cells = dict(zip(headers, padded[: len(headers)]))
        data_rows.append(ParsedRow(cells, structural_error))
    return headers, data_rows


def _clean_row(raw_row: dict[str, str]) -> tuple[dict[str, str], list[dict[str, str]]]:
    cleaned: dict[str, str] = {}
    log: list[dict[str, str]] = []
    for field, value in raw_row.items():
        stripped = value.strip()
        if stripped != value:
            log.append({"field": field, "before": value, "after": stripped})
        cleaned[field] = stripped
    return cleaned, log


def stage_rows(db: Session, import_job: ImportJob, data_rows: list["ParsedRow"]) -> None:
    """VALIDATE (structural) — every row becomes an import_row with
    cleaning already applied and logged, ready for UNDERSTAND/MAP/REVIEW.
    A row whose cell count didn't match the header count is staged
    INVALID immediately, with its field values kept only for display —
    they are not reliable enough to run through MAP/IMPORT."""
    for i, parsed in enumerate(data_rows, start=1):
        cleaned, cleaning_log = _clean_row(parsed.cells)
        raw_data = {**cleaned, "_cleaning": cleaning_log} if cleaning_log else dict(cleaned)
        if parsed.structural_error:
            raw_data["_structural_error"] = parsed.structural_error
        db.add(
            ImportRow(
                organisation_id=import_job.organisation_id,
                import_job_id=import_job.id,
                row_number=i,
                raw_data=raw_data,
                status=ImportRowStatus.INVALID if parsed.structural_error else ImportRowStatus.PENDING,
                errors=[parsed.structural_error] if parsed.structural_error else [],
            )
        )
    db.flush()


def _normalize(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def propose_mapping(dataset_type: str, headers: list[str]) -> dict[str, str | None]:
    """UNDERSTAND — fuzzy-match uploaded headers to the field dictionary.
    Returns header -> field_key (or None if nothing matched); the caller
    reviews/edits this before it's applied (MAP)."""
    fields = get_field_dictionary(dataset_type)
    alias_lookup: dict[str, str] = {}
    for f in fields:
        for alias in [f.key, f.label, *f.aliases]:
            alias_lookup[_normalize(alias)] = f.key
    return {h: alias_lookup.get(_normalize(h)) for h in headers}


def apply_mapping(db: Session, dataset: Dataset, import_job: ImportJob, column_mapping: dict[str, str]) -> None:
    """MAP + REVIEW — commits the (human-reviewed) mapping, re-validates
    every staged row against the field dictionary's required fields."""
    fields = get_field_dictionary(dataset.dataset_type)
    required_keys = {f.key for f in fields if f.required}

    rows = db.query(ImportRow).filter(ImportRow.import_job_id == import_job.id).all()
    for row in rows:
        if row.raw_data.get("_structural_error"):
            continue  # already INVALID from staging; field values aren't trustworthy — see stage_rows
        mapped = {
            field_key: row.raw_data.get(header)
            for header, field_key in column_mapping.items()
            if field_key
        }
        missing = sorted(k for k in required_keys if not mapped.get(k))
        if missing:
            row.status = ImportRowStatus.INVALID
            row.errors = [f"Missing required field: {k}" for k in missing]
        else:
            row.status = ImportRowStatus.VALID
            row.errors = []

    import_job.column_mapping = column_mapping
    import_job.status = ImportJobStatus.MAPPED
    dataset.status = DatasetStatus.MAPPED
    db.flush()


def save_mapping_template(db: Session, organisation_id, dataset_type: str, column_mapping: dict[str, str]) -> None:
    template = (
        db.query(MappingTemplate)
        .filter(MappingTemplate.organisation_id == organisation_id, MappingTemplate.dataset_type == dataset_type)
        .first()
    )
    if template is None:
        template = MappingTemplate(
            organisation_id=organisation_id, dataset_type=dataset_type, column_mapping=column_mapping
        )
        db.add(template)
    else:
        template.column_mapping = column_mapping
    db.flush()


# Populated per domain as canonical tables land (Sprint 5+). Each importer
# takes (db, organisation_id, mapped_fields) and returns (entity_type,
# entity_id) for provenance linkage, or None to leave the row unmapped.
IMPORTERS: dict[str, Callable] = {}


def import_dataset(db: Session, dataset: Dataset, import_job: ImportJob) -> dict:
    """IMPORT — commits VALID rows via a registered importer if one exists
    for this dataset_type; otherwise an honest no-op (see module
    docstring: no canonical domain tables exist yet in Sprint 3)."""
    importer = IMPORTERS.get(dataset.dataset_type)
    valid_rows = (
        db.query(ImportRow)
        .filter(ImportRow.import_job_id == import_job.id, ImportRow.status == ImportRowStatus.VALID)
        .all()
    )

    imported_count = 0
    for row in valid_rows:
        if importer is not None:
            mapped_fields = {
                field_key: row.raw_data.get(header)
                for header, field_key in (import_job.column_mapping or {}).items()
                if field_key
            }
            entity_type, entity_id = importer(db, dataset.organisation_id, mapped_fields)
            row.mapped_entity_type = entity_type
            row.mapped_entity_id = str(entity_id)
            imported_count += 1
        row.status = ImportRowStatus.IMPORTED

    import_job.status = ImportJobStatus.COMPLETED
    dataset.status = DatasetStatus.IMPORTED
    db.flush()
    return {
        "rows_processed": len(valid_rows),
        "entities_created": imported_count,
        "importer_registered": importer is not None,
    }
