import uuid
from datetime import date

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile, status
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.tenancy import AuthContext, get_auth_context, require_permission
from app.core.uploads import read_upload_within_limit
from app.documents.models import Document, DocumentStatus
from app.documents.reference import next_document_reference
from app.documents.schemas import DocumentDetailOut, DocumentOut
from app.integrations.storage import get_document_storage, sha256_hex
from app.platform.audit import record_audit_event

router = APIRouter(prefix="/api/v1/documents", tags=["documents"])


def _get_org_document(db: Session, organisation_id: uuid.UUID, document_id: uuid.UUID) -> Document:
    document = (
        db.query(Document)
        .filter(Document.id == document_id, Document.organisation_id == organisation_id)
        .first()
    )
    if document is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")
    return document


@router.post("", response_model=DocumentOut, status_code=status.HTTP_201_CREATED)
def upload_document(
    title: str = Form(...),
    document_type: str = Form(...),
    file: UploadFile = File(...),
    related_entity_type: str | None = Form(None),
    related_entity_id: str | None = Form(None),
    effective_date: date | None = Form(None),
    source: str | None = Form(None),
    ctx: AuthContext = Depends(require_permission("documents.write")),
    db: Session = Depends(get_db),
):
    content = read_upload_within_limit(file)
    if not content:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "File is empty")

    document_id = uuid.uuid4()
    checksum = sha256_hex(content)
    storage_key = f"{ctx.organisation_id}/{document_id}"
    get_document_storage().save(storage_key, content)

    document = Document(
        id=document_id,
        lineage_id=document_id,
        organisation_id=ctx.organisation_id,
        document_reference=next_document_reference(db, ctx.organisation_id),
        title=title,
        document_type=document_type,
        revision="A",
        status=DocumentStatus.ACTIVE,
        uploaded_by=ctx.user.id,
        effective_date=effective_date,
        related_entity_type=related_entity_type,
        related_entity_id=related_entity_id,
        source=source,
        storage_key=storage_key,
        content_type=file.content_type or "application/octet-stream",
        size_bytes=len(content),
        checksum=checksum,
    )
    db.add(document)
    record_audit_event(
        db,
        organisation_id=ctx.organisation_id,
        actor_user_id=ctx.user.id,
        action_code="document.uploaded",
        entity_type="document",
        entity_id=str(document.id),
        after={"title": title, "document_type": document_type, "document_reference": document.document_reference},
    )
    db.commit()
    db.refresh(document)
    return document


@router.post("/{document_id}/versions", response_model=DocumentOut, status_code=status.HTTP_201_CREATED)
def upload_new_version(
    document_id: uuid.UUID,
    file: UploadFile = File(...),
    revision: str = Form("B"),
    effective_date: date | None = Form(None),
    ctx: AuthContext = Depends(require_permission("documents.write")),
    db: Session = Depends(get_db),
):
    previous = _get_org_document(db, ctx.organisation_id, document_id)
    if previous.status == DocumentStatus.SUPERSEDED:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "This is not the current version — upload a new version from the latest one instead",
        )

    content = read_upload_within_limit(file)
    if not content:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "File is empty")

    new_id = uuid.uuid4()
    checksum = sha256_hex(content)
    storage_key = f"{ctx.organisation_id}/{new_id}"
    get_document_storage().save(storage_key, content)

    new_version = Document(
        id=new_id,
        lineage_id=previous.lineage_id,
        organisation_id=ctx.organisation_id,
        document_reference=previous.document_reference,
        title=previous.title,
        document_type=previous.document_type,
        revision=revision,
        status=DocumentStatus.ACTIVE,
        uploaded_by=ctx.user.id,
        effective_date=effective_date,
        related_entity_type=previous.related_entity_type,
        related_entity_id=previous.related_entity_id,
        source=previous.source,
        storage_key=storage_key,
        content_type=file.content_type or "application/octet-stream",
        size_bytes=len(content),
        checksum=checksum,
    )
    db.add(new_version)
    db.flush()

    # Append-only: the previous row is never edited to hold the new
    # content, only marked superseded — spec §28.
    previous.status = DocumentStatus.SUPERSEDED
    previous.superseded_by_document_id = new_version.id

    record_audit_event(
        db,
        organisation_id=ctx.organisation_id,
        actor_user_id=ctx.user.id,
        action_code="document.new_version",
        entity_type="document",
        entity_id=str(new_version.id),
        before={"superseded_document_id": str(previous.id)},
        after={"revision": revision},
    )
    db.commit()
    db.refresh(new_version)
    return new_version


@router.get("", response_model=list[DocumentOut])
def list_documents(
    related_entity_type: str | None = None,
    related_entity_id: str | None = None,
    current_only: bool = True,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    if ctx.organisation_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "X-Organisation-Id header is required")
    query = db.query(Document).filter(Document.organisation_id == ctx.organisation_id)
    if related_entity_type:
        query = query.filter(Document.related_entity_type == related_entity_type)
    if related_entity_id:
        query = query.filter(Document.related_entity_id == related_entity_id)
    if current_only:
        query = query.filter(Document.status != DocumentStatus.SUPERSEDED)
    return query.order_by(Document.uploaded_at.desc()).all()


@router.get("/{document_id}", response_model=DocumentDetailOut)
def get_document(
    document_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    if ctx.organisation_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "X-Organisation-Id header is required")
    document = _get_org_document(db, ctx.organisation_id, document_id)
    versions = (
        db.query(Document)
        .filter(Document.lineage_id == document.lineage_id)
        .order_by(Document.uploaded_at)
        .all()
    )
    return DocumentDetailOut(**DocumentOut.model_validate(document).model_dump(), versions=versions)


@router.get("/{document_id}/download")
def download_document(
    document_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    if ctx.organisation_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "X-Organisation-Id header is required")
    document = _get_org_document(db, ctx.organisation_id, document_id)
    content = get_document_storage().read(document.storage_key)
    return Response(
        content=content,
        media_type=document.content_type,
        headers={"Content-Disposition": f'attachment; filename="{document.title}"'},
    )
