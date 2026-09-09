"""Simple per-organisation sequential property reference — same interim
approach and same caveat as app/documents/reference.py: not
concurrency-safe under simultaneous creates, superseded by the real
configurable Identifier & Reference Engine in Sprint 7."""

import uuid

from sqlalchemy.orm import Session

from app.development.models import Property


def next_property_reference(db: Session, organisation_id: uuid.UUID) -> str:
    count = db.query(Property).filter(Property.organisation_id == organisation_id).count()
    return f"PROP-{count + 1:06d}"
