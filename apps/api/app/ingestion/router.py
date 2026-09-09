import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.tenancy import AuthContext, get_auth_context, require_permission
from app.documents.models import Document, DocumentStatus
from app.documents.reference import next_document_reference
from app.ingestion.field_dictionary import FIELD_DICTIONARIES, FieldSpec, get_field_dictionary
from app.ingestion.models import (
    Dataset,
    DatasetStatus,
    ImportJob,
    ImportJobStatus,
    ImportRow,
    ImportRowStatus,
    MappingTemplate,
)
from app.ingestion.pipeline import CsvParseError, apply_mapping, import_dataset, parse_csv, propose_mapping, save_mapping_template, stage_rows
from app.ingestion.schemas import (
    ApplyMappingRequest,
    DatasetDetailOut,
    DatasetOut,
    ImportResultOut,
    ImportRowOut,
    UploadResponse,
)
from app.integrations.storage import get_document_storage, sha256_hex
from app.platform.entitlements import require_entitlement

router = APIRouter(prefix="/api/v1", tags=["ingestion"])


def _latest_job(db: Session, dataset_id: uuid.UUID) -> ImportJob | None:
    return (
        db.query(ImportJob)
        .filter(ImportJob.dataset_id == dataset_id)
        .order_by(ImportJob.started_at.desc())
        .first()
    )


def _get_org_dataset(db: Session, organisation_id: uuid.UUID, dataset_id: uuid.UUID) -> Dataset:
    dataset = (
        db.query(Dataset)
        .filter(Dataset.id == dataset_id, Dataset.organisation_id == organisation_id)
        .first()
    )
    if dataset is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Dataset not found")
    return dataset


@router.get("/datasets/field-dictionaries", response_model=dict[str, list[FieldSpec]])
def list_field_dictionaries():
    return FIELD_DICTIONARIES


@router.post("/uploads", response_model=UploadResponse, status_code=status.HTTP_201_CREATED)
def upload_dataset(
    dataset_type: str = Form(...),
    name: str = Form(...),
    file: UploadFile = File(...),
    ctx: AuthContext = Depends(require_permission("uploads.write")),
    _entitled: AuthContext = Depends(require_entitlement("bulk_import")),
    db: Session = Depends(get_db),
):
    if dataset_type not in FIELD_DICTIONARIES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Unknown dataset_type: {dataset_type}")

    raw_bytes = file.file.read()
    try:
        headers, data_rows = parse_csv(raw_bytes)
    except CsvParseError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    document_id = uuid.uuid4()
    checksum = sha256_hex(raw_bytes)
    storage_key = f"{ctx.organisation_id}/{document_id}"
    get_document_storage().save(storage_key, raw_bytes)
    source_document = Document(
        id=document_id,
        lineage_id=document_id,
        organisation_id=ctx.organisation_id,
        document_reference=next_document_reference(db, ctx.organisation_id),
        title=file.filename or name,
        document_type="DATA_UPLOAD",
        revision="A",
        status=DocumentStatus.ACTIVE,
        uploaded_by=ctx.user.id,
        source="dataset_upload",
        storage_key=storage_key,
        content_type=file.content_type or "text/csv",
        size_bytes=len(raw_bytes),
        checksum=checksum,
    )
    db.add(source_document)
    db.flush()

    dataset = Dataset(
        organisation_id=ctx.organisation_id,
        name=name,
        dataset_type=dataset_type,
        status=DatasetStatus.VALIDATED,
        row_count=len(data_rows),
        uploaded_by=ctx.user.id,
        source_file_document_id=source_document.id,
    )
    db.add(dataset)
    db.flush()

    # The document's related_entity_* couldn't be set before the dataset
    # existed — link it back now that we have an id.
    source_document.related_entity_type = "dataset"
    source_document.related_entity_id = str(dataset.id)

    import_job = ImportJob(
        organisation_id=ctx.organisation_id, dataset_id=dataset.id, status=ImportJobStatus.AWAITING_MAPPING
    )
    db.add(import_job)
    db.flush()

    stage_rows(db, import_job, data_rows)

    template = (
        db.query(MappingTemplate)
        .filter(
            MappingTemplate.organisation_id == ctx.organisation_id,
            MappingTemplate.dataset_type == dataset_type,
        )
        .first()
    )
    if template is not None:
        proposed = {h: template.column_mapping.get(h) for h in headers}
        from_template = True
    else:
        proposed = propose_mapping(dataset_type, headers)
        from_template = False

    db.commit()
    return UploadResponse(
        dataset_id=dataset.id,
        import_job_id=import_job.id,
        row_count=len(data_rows),
        proposed_mapping=proposed,
        field_dictionary=get_field_dictionary(dataset_type),
        suggested_mapping_from_template=from_template,
    )


@router.get("/datasets", response_model=list[DatasetOut])
def list_datasets(
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    if ctx.organisation_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "X-Organisation-Id header is required")
    return (
        db.query(Dataset)
        .filter(Dataset.organisation_id == ctx.organisation_id)
        .order_by(Dataset.uploaded_at.desc())
        .all()
    )


@router.get("/datasets/{dataset_id}", response_model=DatasetDetailOut)
def get_dataset(
    dataset_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    if ctx.organisation_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "X-Organisation-Id header is required")
    dataset = _get_org_dataset(db, ctx.organisation_id, dataset_id)
    job = _latest_job(db, dataset.id)

    counts_query = (
        db.query(ImportRow.status, func.count(ImportRow.id))
        .filter(ImportRow.import_job_id == job.id)
        .group_by(ImportRow.status)
        .all()
        if job
        else []
    )
    row_status_counts = {status_val.value: count for status_val, count in counts_query}

    return DatasetDetailOut(
        id=dataset.id,
        name=dataset.name,
        dataset_type=dataset.dataset_type,
        status=dataset.status.value,
        row_count=dataset.row_count,
        uploaded_at=dataset.uploaded_at,
        source_file_document_id=dataset.source_file_document_id,
        latest_job_status=job.status.value if job else None,
        row_status_counts=row_status_counts,
    )


@router.get("/datasets/{dataset_id}/rows", response_model=list[ImportRowOut])
def list_dataset_rows(
    dataset_id: uuid.UUID,
    row_status: ImportRowStatus | None = None,
    limit: int = 100,
    offset: int = 0,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    if ctx.organisation_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "X-Organisation-Id header is required")
    dataset = _get_org_dataset(db, ctx.organisation_id, dataset_id)
    job = _latest_job(db, dataset.id)
    if job is None:
        return []
    query = db.query(ImportRow).filter(ImportRow.import_job_id == job.id)
    if row_status is not None:
        query = query.filter(ImportRow.status == row_status)
    return (
        query.order_by(ImportRow.row_number)
        .offset(offset)
        .limit(min(limit, 500))
        .all()
    )


@router.post("/datasets/{dataset_id}/mapping", response_model=DatasetDetailOut)
def apply_dataset_mapping(
    dataset_id: uuid.UUID,
    payload: ApplyMappingRequest,
    ctx: AuthContext = Depends(require_permission("uploads.write")),
    db: Session = Depends(get_db),
):
    dataset = _get_org_dataset(db, ctx.organisation_id, dataset_id)
    job = _latest_job(db, dataset.id)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No import job found for this dataset")

    column_mapping = {k: v for k, v in payload.column_mapping.items() if v}
    apply_mapping(db, dataset, job, column_mapping)
    save_mapping_template(db, ctx.organisation_id, dataset.dataset_type, column_mapping)
    db.commit()

    return get_dataset(dataset_id, ctx, db)


@router.post("/datasets/{dataset_id}/import", response_model=ImportResultOut)
def trigger_dataset_import(
    dataset_id: uuid.UUID,
    ctx: AuthContext = Depends(require_permission("uploads.write")),
    db: Session = Depends(get_db),
):
    dataset = _get_org_dataset(db, ctx.organisation_id, dataset_id)
    job = _latest_job(db, dataset.id)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No import job found for this dataset")
    if job.column_mapping is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Apply a column mapping before importing")

    result = import_dataset(db, dataset, job)
    db.commit()
    return ImportResultOut(**result)
