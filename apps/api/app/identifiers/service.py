"""Identifier & Reference Engine service layer — architecture/03-development-domain.md §3.

generate_reference replaces the per-module COUNT-based generators used
by documents (Sprint 4), properties, developments and buildings
(Sprints 5-6) — each of those modules flagged the same caveat every
sprint: "not concurrency-safe, Sprint 7 replaces it properly." This is
that replacement: a per-(organisation, entity_type) counter row, updated
under a row lock (SELECT ... FOR UPDATE) in the same transaction as the
entity insert, so two concurrent creates can never read the same
sequence number. Default patterns render to the exact same strings the
old generators produced (PROP-000001, DEV-000001, ...) — the upgrade is
in the concurrency guarantee and the configurability, not a reference
format churn for its own sake.

record_external_reference is the hard write-path constraint from spec
§16: this is the ONLY function in the codebase that writes an
ExternalReference row, and it refuses SYSTEM_GENERATED (the ORM-level
check here is belt-and-braces alongside the DB CHECK constraint on the
table itself — see identifiers/models.py).
"""

import uuid

from sqlalchemy.orm import Session

from app.core.provenance import SourceType
from app.identifiers.models import ExternalReference, ExternalReferenceType, ReferencePattern
from app.platform.audit import record_audit_event

DEFAULT_PATTERNS: dict[str, str] = {
    "DEVELOPMENT": "DEV-{sequence:06d}",
    "BUILDING": "BLD-{sequence:06d}",
    "PROPERTY": "PROP-{sequence:06d}",
    "DOCUMENT": "DOC-{sequence:06d}",
}


def _get_or_create_pattern(db: Session, organisation_id: uuid.UUID, entity_type: str) -> ReferencePattern:
    # Row-locked read on the common path (pattern already exists — true
    # for every generate_reference call after an org's first entity of
    # this type). The one-time bootstrap insert below has a narrow,
    # documented race: two simultaneous *first-ever* creates of the same
    # entity_type for the same org could both attempt to insert this row.
    # The unique constraint on (organisation_id, entity_type) turns that
    # into a clean IntegrityError rather than a silent duplicate; it is
    # not caught/retried here because it is a one-time-per-org-per-type
    # edge case, not the steady-state path this function exists to fix.
    pattern = (
        db.query(ReferencePattern)
        .filter(ReferencePattern.organisation_id == organisation_id, ReferencePattern.entity_type == entity_type)
        .with_for_update()
        .first()
    )
    if pattern is not None:
        return pattern

    if entity_type not in DEFAULT_PATTERNS:
        raise ValueError(f"No default reference pattern for entity_type: {entity_type}")

    pattern = ReferencePattern(
        organisation_id=organisation_id,
        entity_type=entity_type,
        pattern=DEFAULT_PATTERNS[entity_type],
        next_sequence=1,
        is_active=True,
    )
    db.add(pattern)
    db.flush()
    return pattern


def generate_reference(db: Session, organisation_id: uuid.UUID, entity_type: str) -> str:
    pattern = _get_or_create_pattern(db, organisation_id, entity_type)
    sequence = pattern.next_sequence
    pattern.next_sequence = sequence + 1
    db.flush()
    return pattern.pattern.format(sequence=sequence)


def set_reference_pattern(db: Session, organisation_id: uuid.UUID, entity_type: str, pattern_str: str) -> ReferencePattern:
    """Org-configurable pattern — spec: 'Allow organisations to configure
    internal reference patterns.' Only the format string is editable;
    next_sequence is never set directly (would risk clashing/reusing a
    reference already handed out — spec: 'never silently reused')."""
    pattern = _get_or_create_pattern(db, organisation_id, entity_type)
    pattern.pattern = pattern_str
    db.flush()
    return pattern


def list_reference_patterns(db: Session, organisation_id: uuid.UUID) -> list[ReferencePattern]:
    for entity_type in DEFAULT_PATTERNS:
        _get_or_create_pattern(db, organisation_id, entity_type)  # ensure every type is visible, same as plans (Sprint 2)
    return db.query(ReferencePattern).filter(ReferencePattern.organisation_id == organisation_id).all()


def record_external_reference(
    db: Session,
    organisation_id: uuid.UUID,
    *,
    entity_type: str,
    entity_id: uuid.UUID,
    reference_type: ExternalReferenceType,
    value: str,
    source_type: SourceType,
    source_system: str | None = None,
    source_dataset_id: uuid.UUID | None = None,
    import_job_id: uuid.UUID | None = None,
    original_reference: str | None = None,
    actor_user_id: uuid.UUID | None = None,
) -> ExternalReference:
    if source_type == SourceType.SYSTEM_GENERATED:
        raise ValueError(
            "External references must never be SYSTEM_GENERATED — DataLume cannot fabricate an official identifier"
        )

    ref = ExternalReference(
        organisation_id=organisation_id,
        entity_type=entity_type,
        entity_id=str(entity_id),
        reference_type=reference_type,
        value=value,
        source_type=source_type,
        source_system=source_system,
        source_dataset_id=source_dataset_id,
        import_job_id=import_job_id,
        original_reference=original_reference,
        created_by=actor_user_id,
        updated_by=actor_user_id,
    )
    db.add(ref)
    db.flush()

    record_audit_event(
        db,
        organisation_id=organisation_id,
        actor_user_id=actor_user_id,
        action_code="external_reference.recorded",
        entity_type="external_reference",
        entity_id=str(ref.id),
        after={
            "for_entity_type": entity_type,
            "for_entity_id": str(entity_id),
            "reference_type": reference_type.value,
            "value": value,
        },
    )
    return ref


def get_external_references(db: Session, organisation_id: uuid.UUID, entity_type: str, entity_id: uuid.UUID) -> dict[str, str]:
    """entity's reference_type -> value map, e.g. {"UPRN": "100012345678"}
    — the shape every *Out schema needs to surface external identifiers
    alongside the entity's own internal reference."""
    rows = (
        db.query(ExternalReference)
        .filter(
            ExternalReference.organisation_id == organisation_id,
            ExternalReference.entity_type == entity_type,
            ExternalReference.entity_id == str(entity_id),
        )
        .all()
    )
    return {row.reference_type.value: row.value for row in rows}


def get_external_references_bulk(
    db: Session, organisation_id: uuid.UUID, entity_type: str, entity_ids: list[uuid.UUID]
) -> dict[str, dict[str, str]]:
    """Same as get_external_references but for a list view — one query
    instead of N, keyed by entity_id string."""
    if not entity_ids:
        return {}
    rows = (
        db.query(ExternalReference)
        .filter(
            ExternalReference.organisation_id == organisation_id,
            ExternalReference.entity_type == entity_type,
            ExternalReference.entity_id.in_([str(i) for i in entity_ids]),
        )
        .all()
    )
    result: dict[str, dict[str, str]] = {}
    for row in rows:
        result.setdefault(row.entity_id, {})[row.reference_type.value] = row.value
    return result
