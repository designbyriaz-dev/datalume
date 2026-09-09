import uuid
from datetime import date, datetime

from pydantic import BaseModel


class DocumentOut(BaseModel):
    id: uuid.UUID
    document_reference: str
    title: str
    document_type: str
    revision: str
    status: str
    uploaded_by: uuid.UUID
    uploaded_at: datetime
    effective_date: date | None
    superseded_by_document_id: uuid.UUID | None
    related_entity_type: str | None
    related_entity_id: str | None
    content_type: str
    size_bytes: int
    checksum: str

    model_config = {"from_attributes": True}


class DocumentDetailOut(DocumentOut):
    versions: list[DocumentOut]
