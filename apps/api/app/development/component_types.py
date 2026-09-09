"""Seeded component-type catalog — architecture/03-development-domain.md
§22. Lazily upserted into the DB the same way system roles (Sprint 1)
and the plan catalog (Sprint 2) are: get_or_create per code, so the
catalog is always visible regardless of which types anyone has actually
used yet (see app/platform/billing.py.ensure_plan_catalog_seeded for the
identical pattern this mirrors).

organisation_id stays NULL for every seeded row — these are global,
available to every org. An org's own custom addition (e.g. an
unrecognised type auto-created during CSV import) gets its
organisation_id set instead; see app/development/importers.py.
"""

import uuid

from sqlalchemy.orm import Session

from app.development.models import ComponentType

# code -> display name. Spec §22's list, verbatim categories.
SEEDED_COMPONENT_TYPES: dict[str, str] = {
    "ROOF": "Roof",
    "WINDOWS": "Windows",
    "EXTERNAL_DOORS": "External doors",
    "FIRE_DOORS": "Fire doors",
    "BOILERS": "Boilers",
    "HEAT_PUMPS": "Heat pumps",
    "HEATING_SYSTEMS": "Heating systems",
    "CONSUMER_UNITS": "Consumer units",
    "ELECTRICAL_INSTALLATIONS": "Electrical installations",
    "SMOKE_ALARMS": "Smoke alarms",
    "CO_ALARMS": "CO alarms",
    "SPRINKLERS": "Sprinklers",
    "FIRE_STOPPING": "Fire-stopping systems",
    "CLADDING_FACADE": "Cladding/façade",
    "LIFTS": "Lifts",
    "WATER_SYSTEMS": "Water systems",
    "KITCHENS": "Kitchens",
    "BATHROOMS": "Bathrooms",
    "VENTILATION": "Ventilation",
    "STRUCTURAL_ELEMENTS": "Structural elements",
    "INSULATION": "Insulation",
    "SOLAR_PV": "Solar PV",
    "EV_INFRASTRUCTURE": "EV infrastructure",
    "OTHER": "Other",
}


def get_or_create_global_component_type(db: Session, code: str) -> ComponentType:
    component_type = (
        db.query(ComponentType).filter(ComponentType.organisation_id.is_(None), ComponentType.code == code).first()
    )
    if component_type is not None:
        return component_type
    if code not in SEEDED_COMPONENT_TYPES:
        raise ValueError(f"Unknown seeded component type code: {code}")
    component_type = ComponentType(organisation_id=None, code=code, name=SEEDED_COMPONENT_TYPES[code])
    db.add(component_type)
    db.flush()
    return component_type


def ensure_component_type_catalog_seeded(db: Session) -> list[ComponentType]:
    return [get_or_create_global_component_type(db, code) for code in SEEDED_COMPONENT_TYPES]


def _singularish(s: str) -> str:
    """Naive de-pluralisation for matching purposes only (never stored,
    never shown) — good enough to match "Boiler" against the seeded
    "Boilers" without pulling in a real NLP dependency for one column."""
    return s[:-1] if s.endswith("s") and not s.endswith("ss") else s


def find_component_type_by_name(db: Session, organisation_id: uuid.UUID, name: str) -> ComponentType | None:
    """Case-insensitive, singular/plural-tolerant match against the org's
    own custom types first, then the global seeded catalog — used by CSV
    import (app/development/importers.py) to resolve free-text "Boiler"
    etc. from a spreadsheet column into a component_type_id. Exact match
    wins; a real CSV upload surfaced a case (Sprint 8's own test suite:
    "Boiler" vs. the seeded "Boilers") where naive exact-match would have
    created a needless duplicate custom type instead of matching the
    existing one — hence the singular/plural fallback below."""
    normalized = name.strip().lower()
    candidates = (
        db.query(ComponentType)
        .filter((ComponentType.organisation_id == organisation_id) | (ComponentType.organisation_id.is_(None)))
        .all()
    )
    for candidate in candidates:
        if candidate.name.strip().lower() == normalized:
            return candidate
    normalized_singular = _singularish(normalized)
    for candidate in candidates:
        if _singularish(candidate.name.strip().lower()) == normalized_singular:
            return candidate
    return None


def get_or_create_org_component_type(db: Session, organisation_id: uuid.UUID, name: str) -> ComponentType:
    """Import hit a component_type name that matches nothing, global or
    custom — rather than reject the whole row, create a new org-specific
    type on the fly. Matches the taxonomy's "org-extensible" design
    (spec §22) instead of forcing every customer's naming to fit the
    seeded list exactly."""
    existing = find_component_type_by_name(db, organisation_id, name)
    if existing is not None:
        return existing
    code = "".join(c.upper() if c.isalnum() else "_" for c in name.strip()).strip("_") or f"CUSTOM_{uuid.uuid4().hex[:8]}"
    component_type = ComponentType(organisation_id=organisation_id, code=code, name=name.strip())
    db.add(component_type)
    db.flush()
    return component_type
