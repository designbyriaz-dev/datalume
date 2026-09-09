"""Simple per-organisation sequential document reference — interim,
ahead of the real configurable Identifier & Reference Engine
(architecture/03-development-domain.md §3, Sprint 7). Not
concurrency-safe under simultaneous uploads for the same org (a
COUNT-based number, not a row-locked counter) — acceptable for Sprint 4
since a genuinely gap-free, race-safe generator is exactly what Sprint 7
is for; do not copy this pattern for a domain entity's reference."""

import uuid

from sqlalchemy.orm import Session

from app.documents.models import Document


def next_document_reference(db: Session, organisation_id: uuid.UUID) -> str:
    count = db.query(Document).filter(Document.organisation_id == organisation_id).count()
    return f"DOC-{count + 1:06d}"
