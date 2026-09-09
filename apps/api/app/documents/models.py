"""Document — architecture/02-data-platform.md §4.

Append-only versioning: a new upload creates a NEW row with
superseded_by_document_id set on the prior version — never an in-place
file overwrite (spec §28: "never silently overwrite previous versions").
`related_entity_type`/`related_entity_id` is a plain polymorphic
reference (no FK) so a document can attach to anything, including entity
types that don't have a table yet — Sprint 4's real use is linking a
Dataset's source file (Sprint 3) to a Document; Sprint 9+ (Construction
Evidence, Specifications, Golden Thread) attach the same way once those
tables exist.
"""

import enum
import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, Enum, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class DocumentStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    SUPERSEDED = "SUPERSEDED"
    ARCHIVED = "ARCHIVED"


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organisation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.id"))
    # Shared across every version of the same document (equals this row's
    # own id for the first version — set explicitly at creation, since a
    # column default can't reference the row's own generated id). Lets
    # "get all versions" be a plain WHERE lineage_id = :x query instead of
    # walking superseded_by links.
    lineage_id: Mapped[uuid.UUID] = mapped_column()
    # Simple per-org sequential reference for Sprint 4 (e.g. "DOC-000123").
    # The full configurable Reference & Identifier Engine (architecture 03
    # §3) lands in Sprint 7 — this field migrates to use it then rather
    # than staying a bespoke format.
    document_reference: Mapped[str] = mapped_column(String(32))
    title: Mapped[str] = mapped_column(String(255))
    document_type: Mapped[str] = mapped_column(String(64))
    revision: Mapped[str] = mapped_column(String(32), default="A")
    status: Mapped[DocumentStatus] = mapped_column(Enum(DocumentStatus), default=DocumentStatus.ACTIVE)
    uploaded_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    effective_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    superseded_by_document_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("documents.id"), nullable=True)
    related_entity_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    related_entity_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source: Mapped[str | None] = mapped_column(String(128), nullable=True)
    external_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    storage_key: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(128))
    size_bytes: Mapped[int] = mapped_column(Integer)
    checksum: Mapped[str] = mapped_column(String(64))
