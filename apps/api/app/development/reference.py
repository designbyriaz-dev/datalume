"""Simple per-organisation sequential references — same interim approach
and same caveat as app/documents/reference.py: not concurrency-safe
under simultaneous creates, superseded by the real configurable
Identifier & Reference Engine in Sprint 7. Floors don't get one — a
floor is identified by name ("Ground Floor", "1st Floor") in practice,
not a generated code."""

import uuid

from sqlalchemy.orm import Session

from app.development.models import Building, Development, Property


def next_development_reference(db: Session, organisation_id: uuid.UUID) -> str:
    count = db.query(Development).filter(Development.organisation_id == organisation_id).count()
    return f"DEV-{count + 1:06d}"


def next_building_reference(db: Session, organisation_id: uuid.UUID) -> str:
    count = db.query(Building).filter(Building.organisation_id == organisation_id).count()
    return f"BLD-{count + 1:06d}"


def next_property_reference(db: Session, organisation_id: uuid.UUID) -> str:
    count = db.query(Property).filter(Property.organisation_id == organisation_id).count()
    return f"PROP-{count + 1:06d}"
