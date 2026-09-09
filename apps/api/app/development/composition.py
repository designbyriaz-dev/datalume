"""Shared read-composition helpers — extracted from golden_thread.py
(Sprint 9-10) once Property 360 (Sprint 13) needed the exact same
per-component "specs + evidence + changes + responsible party +
external references" bundle Golden Thread already built. Nothing here
writes anything; every field is read from tables that already have
their own create/write paths (Specification, Document, ChangeControl,
ExternalReference) — same "compose, don't duplicate" reasoning as
Golden Thread itself, now shared across two composed views instead of
copied into both.
"""

import uuid

from sqlalchemy.orm import Session

from app.auth.models import User
from app.development.models import ChangeControl, Component, ComponentType, Specification, SpecificationStatus
from app.development.presenters import changes_to_out
from app.development.schemas import GoldenThreadComponentOut, GoldenThreadResponsiblePartyOut, SpecificationOut
from app.documents.models import Document
from app.documents.schemas import DocumentOut
from app.identifiers.service import get_external_references


def current_specifications(db: Session, organisation_id: uuid.UUID, entity_type: str, entity_id: uuid.UUID) -> list:
    return (
        db.query(Specification)
        .filter(
            Specification.organisation_id == organisation_id,
            Specification.related_entity_type == entity_type,
            Specification.related_entity_id == str(entity_id),
            Specification.status != SpecificationStatus.SUPERSEDED,
        )
        .order_by(Specification.created_at.desc())
        .all()
    )


def evidence_for(db: Session, organisation_id: uuid.UUID, entity_type: str, entity_id: uuid.UUID) -> list:
    return (
        db.query(Document)
        .filter(
            Document.organisation_id == organisation_id,
            Document.related_entity_type == entity_type,
            Document.related_entity_id == str(entity_id),
        )
        .order_by(Document.uploaded_at.desc())
        .all()
    )


def changes_for(db: Session, organisation_id: uuid.UUID, entity_type: str, entity_id: uuid.UUID) -> list:
    return (
        db.query(ChangeControl)
        .filter(
            ChangeControl.organisation_id == organisation_id,
            ChangeControl.related_entity_type == entity_type,
            ChangeControl.related_entity_id == str(entity_id),
        )
        .order_by(ChangeControl.created_at.desc())
        .all()
    )


def responsible_party_for(
    db: Session, component: Component, external_references: dict[str, str]
) -> GoldenThreadResponsiblePartyOut:
    creator = db.query(User).filter(User.id == component.created_by).first() if component.created_by else None
    return GoldenThreadResponsiblePartyOut(
        created_by_name=creator.name if creator else None,
        created_by_email=creator.email if creator else None,
        source_type=component.source_type.value,
        source_system=component.source_system,
        contractor_reference=external_references.get("CONTRACTOR_REFERENCE"),
    )


def component_type_names_for(db: Session, components: list[Component]) -> dict[uuid.UUID, str]:
    if not components:
        return {}
    type_ids = {c.component_type_id for c in components}
    return {ct.id: ct.name for ct in db.query(ComponentType).filter(ComponentType.id.in_(type_ids))}


def build_component_view(
    db: Session, organisation_id: uuid.UUID, component: Component, component_type_names: dict[uuid.UUID, str]
) -> GoldenThreadComponentOut:
    """The full per-component bundle both Golden Thread (building-scoped)
    and Property 360 (property-scoped) compose identically — only which
    components they gather differs."""
    external_references = get_external_references(db, organisation_id, "component", component.id)
    return GoldenThreadComponentOut(
        id=component.id,
        component_reference=component.component_reference,
        component_type_name=component_type_names.get(component.component_type_id, "Unknown"),
        status=component.status.value,
        specifications=[
            SpecificationOut.model_validate(s)
            for s in current_specifications(db, organisation_id, "component", component.id)
        ],
        responsible_party=responsible_party_for(db, component, external_references),
        evidence=[DocumentOut.model_validate(d) for d in evidence_for(db, organisation_id, "component", component.id)],
        changes=changes_to_out(db, organisation_id, changes_for(db, organisation_id, "component", component.id)),
        external_references=external_references,
    )
