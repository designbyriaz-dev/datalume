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
  UNDERSTAND into the same worker/jobs/ingestion.py poll loop that now
  runs IMPORT (see that module) later is a call-site change, not a
  data-model or pipeline-logic change.
- CSV and XLSX (spec §13). Legacy binary .xls is deliberately still
  out of scope — it needs a different, largely-unmaintained library
  (xlrd dropped .xls-adjacent support years ago) for a format Office
  hasn't defaulted to since 2007; every real housing-association
  spreadsheet this build's demo data models is XLSX.
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
from datetime import date, datetime, timezone
from typing import Callable

import openpyxl
from sqlalchemy.orm import Session

from app.ingestion.field_dictionary import get_field_dictionary
from app.ingestion.models import Dataset, DatasetStatus, ImportJob, ImportJobStatus, ImportRow, ImportRowStatus, MappingTemplate


class FileParseError(ValueError):
    pass


class ImporterRowError(ValueError):
    """An importer raises this for a row whose data is well-formed
    (VALID at the VALIDATE stage — every required field present) but
    doesn't resolve to something real — e.g. a FLOORS row whose
    building_reference doesn't match any building in the org. Deliberately
    a distinct type from a bare exception: import_dataset only recovers
    from this one, so a genuine bug in an importer still surfaces as a
    real 500 instead of being silently swallowed as "row failed"."""


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
        raise FileParseError("File is not valid UTF-8 text") from exc

    reader = csv.reader(io.StringIO(text))
    rows = list(reader)
    if not rows:
        raise FileParseError("File is empty")

    headers = [h.strip() for h in rows[0]]
    if not any(headers):
        raise FileParseError("File has no column headers")

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


def _xlsx_cell_to_str(value: object) -> str:
    # openpyxl hands back typed Python values (str/int/float/bool/date/
    # datetime/None), not text — every downstream consumer (field
    # validation, the per-domain importers' own _parse_int/
    # _parse_iso_date helpers) expects the same plain strings parse_csv
    # already produces, so cells are normalised here, once, rather than
    # leaking openpyxl's types into the rest of the pipeline.
    if value is None:
        return ""
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, float):
        return str(int(value)) if value.is_integer() else str(value)
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def parse_xlsx(raw_bytes: bytes) -> tuple[list[str], list[ParsedRow]]:
    """Same (headers, ParsedRow list) contract as parse_csv, so every
    caller downstream of UPLOAD is format-agnostic. Only the first
    (active) worksheet is read — multi-sheet workbooks aren't a
    documented gap this pipeline claims to solve. openpyxl always
    returns every row padded to the sheet's used-column width, so the
    comma-in-an-unquoted-field misalignment parse_csv guards against
    (ParsedRow.structural_error) has no real equivalent here."""
    try:
        workbook = openpyxl.load_workbook(io.BytesIO(raw_bytes), read_only=True, data_only=True)
    except Exception as exc:  # openpyxl raises several different exception types for a bad/corrupt file
        raise FileParseError("File is not a valid XLSX workbook") from exc

    worksheet = workbook.active
    rows = list(worksheet.iter_rows(values_only=True))
    if not rows:
        raise FileParseError("File is empty")

    headers = [_xlsx_cell_to_str(h).strip() for h in rows[0]]
    if not any(headers):
        raise FileParseError("File has no column headers")

    data_rows: list[ParsedRow] = []
    for raw_row in rows[1:]:
        str_cells = [_xlsx_cell_to_str(c) for c in raw_row]
        if not any(cell.strip() for cell in str_cells):
            continue  # skip fully-blank rows rather than staging noise
        padded = str_cells + [""] * (len(headers) - len(str_cells))
        cells = dict(zip(headers, padded[: len(headers)]))
        data_rows.append(ParsedRow(cells, structural_error=None))
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


# Populated per domain as canonical tables land (Sprint 5+ — the first
# registration is app/development/importers.py, at import time). Each
# importer takes (db, dataset, import_job, row, mapped_fields) — the full
# dataset/job/row objects, not just organisation_id, so the created
# entity can carry real provenance (source_dataset_id, import_job_id,
# original_reference) back to the exact row it came from, not just a
# bare organisation scope — and returns (entity_type, entity_id).
IMPORTERS: dict[str, Callable] = {}


def parse_upload(filename: str | None, raw_bytes: bytes) -> tuple[list[str], list[ParsedRow]]:
    """Dispatches by file extension — the only signal a browser upload
    reliably carries; UploadFile.content_type is client-supplied and
    spoofable (same reasoning app/core/uploads.py already documents for
    why this pipeline doesn't attempt content-type allow-listing as a
    security control). This is a format-detection convenience, not a
    security gate: parse_xlsx still rejects anything that isn't a real
    XLSX workbook regardless of what the filename claimed."""
    if (filename or "").lower().endswith(".xlsx"):
        return parse_xlsx(raw_bytes)
    return parse_csv(raw_bytes)


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
    failed_count = 0
    for row in valid_rows:
        if importer is not None:
            mapped_fields = {
                field_key: row.raw_data.get(header)
                for header, field_key in (import_job.column_mapping or {}).items()
                if field_key
            }
            try:
                entity_type, entity_id = importer(db, dataset, import_job, row, mapped_fields)
            except ImporterRowError as exc:
                # This row's own data doesn't resolve to something real
                # (e.g. an unmatched cross-reference) — mark it and move
                # on rather than aborting every remaining valid row in
                # the job over one bad row.
                row.status = ImportRowStatus.INVALID
                row.errors = [str(exc)]
                failed_count += 1
                continue
            row.mapped_entity_type = entity_type
            row.mapped_entity_id = str(entity_id)
            imported_count += 1
        row.status = ImportRowStatus.IMPORTED

    result = {
        "rows_processed": len(valid_rows),
        "entities_created": imported_count,
        "rows_failed": failed_count,
        "importer_registered": importer is not None,
    }

    import_job.status = ImportJobStatus.COMPLETED
    import_job.finished_at = datetime.now(timezone.utc)
    import_job.rows_processed = result["rows_processed"]
    import_job.entities_created = result["entities_created"]
    import_job.rows_failed = result["rows_failed"]
    import_job.importer_registered = result["importer_registered"]
    dataset.status = DatasetStatus.IMPORTED
    db.flush()
    return result


def process_import_job(db: Session, import_job_id) -> ImportJob | None:
    """Idempotent-ish: only ever picks up a job still IMPORTING (the
    worker's own query already filters on that), so re-invoking this on
    an already-COMPLETED/FAILED job is a no-op that returns the job as
    found rather than reprocessing it — mirrors
    app.reports.service.process_report_job's same convention.

    Row-level failures (a single bad row's data) are already handled
    inside import_dataset itself via ImporterRowError, marking just that
    row INVALID without raising. What lands here is a genuine bug — a
    real exception means there's no per-row story to tell, so the whole
    job is marked FAILED with the exception recorded."""
    import_job = db.get(ImportJob, import_job_id)
    if import_job is None or import_job.status != ImportJobStatus.IMPORTING:
        return import_job

    dataset = db.get(Dataset, import_job.dataset_id)
    try:
        import_dataset(db, dataset, import_job)
    except Exception as exc:  # noqa: BLE001 — reported on the job row, not swallowed
        import_job.status = ImportJobStatus.FAILED
        import_job.error_summary = str(exc)[:1024]
        import_job.finished_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(import_job)
    return import_job
