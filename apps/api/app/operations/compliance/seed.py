"""Seeded compliance catalog — spec §45's 21 domains under one DataLume
default framework. Same lazy-seeding pattern as
app/development/component_types.py: nothing eagerly seeds this at
migration time, so callers ensure it's present before reading/writing
against it.
"""

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.operations.compliance.models import ComplianceDomain, ComplianceFramework

DEFAULT_FRAMEWORK_NAME = "DataLume Compliance Framework"

# spec §45 — "these are configurable domains, NOT a claim of exactly 21
# universal laws." Codes are DataLume's own stable identifiers, not a
# regulatory citation.
SEEDED_DOMAINS: dict[str, str] = {
    "GAS_SAFETY": "Gas Safety",
    "ELECTRICAL_SAFETY": "Electrical Safety",
    "FIRE_SAFETY": "Fire Safety",
    "ASBESTOS_MANAGEMENT": "Asbestos Management",
    "WATER_HYGIENE_LEGIONELLA": "Water Hygiene / Legionella",
    "LIFT_SAFETY": "Lift Safety",
    "SMOKE_CO_ALARMS": "Smoke & Carbon Monoxide Alarms",
    "DAMP_AND_MOULD": "Damp & Mould",
    "BUILDING_SAFETY": "Building Safety",
    "HHSRS_HAZARDS": "Housing Health & Safety / Property Hazards",
    "DECENT_HOMES": "Decent Homes",
    "STOCK_CONDITION": "Stock Condition",
    "REPAIRS_MAINTENANCE_SAFETY": "Repairs & Maintenance Safety",
    "EMERGENCY_HAZARD_RESPONSE": "Emergency / Significant Hazard Response",
    "EPC": "Energy Performance / EPC",
    "ACCESSIBILITY_ADAPTATIONS": "Accessibility & Adaptations",
    "STRUCTURAL_SAFETY": "Structural Safety",
    "COMMUNAL_AREA_SAFETY": "Communal Area Safety",
    "CONTRACTOR_SERVICING_EVIDENCE": "Contractor / Servicing Evidence",
    "STATUTORY_INSPECTION_TRACKING": "Statutory Inspection & Remedial Action Tracking",
    "SAFETY_DATA_ASSURANCE": "Safety Data / Evidence Assurance",
}


def get_or_create_default_framework(db: Session) -> ComplianceFramework:
    # Same narrow bootstrap race as app/development/component_types.py's
    # get_or_create_global_component_type, found the same way (a real
    # concurrency test) — migration 0028 is what makes the
    # IntegrityError below possible at all; this table had no unique
    # constraint before it.
    framework = (
        db.query(ComplianceFramework)
        .filter(ComplianceFramework.organisation_id.is_(None), ComplianceFramework.name == DEFAULT_FRAMEWORK_NAME)
        .first()
    )
    if framework is not None:
        return framework
    try:
        with db.begin_nested():
            framework = ComplianceFramework(organisation_id=None, name=DEFAULT_FRAMEWORK_NAME, version=1)
            db.add(framework)
            db.flush()
    except IntegrityError:
        framework = (
            db.query(ComplianceFramework)
            .filter(ComplianceFramework.organisation_id.is_(None), ComplianceFramework.name == DEFAULT_FRAMEWORK_NAME)
            .first()
        )
        if framework is None:
            raise
    return framework


def ensure_compliance_catalog_seeded(db: Session) -> ComplianceFramework:
    framework = get_or_create_default_framework(db)
    existing_codes = {
        d.code
        for d in db.query(ComplianceDomain).filter(
            ComplianceDomain.framework_id == framework.id, ComplianceDomain.organisation_id.is_(None)
        )
    }
    missing = {code: name for code, name in SEEDED_DOMAINS.items() if code not in existing_codes}
    if missing:
        # Same race as the framework above, batched: two concurrent
        # first-ever callers could both compute the same "missing" set
        # and both try to insert all 21 domains. If any single row in
        # this attempt collides, the whole nested transaction rolls
        # back together — the re-query below then finds every domain
        # the winning concurrent call actually committed, so the net
        # result is still complete and correct, just one wasted attempt
        # rather than a partial/duplicate seed.
        try:
            with db.begin_nested():
                for code, name in missing.items():
                    db.add(ComplianceDomain(organisation_id=None, framework_id=framework.id, code=code, name=name))
                db.flush()
        except IntegrityError:
            now_present = {
                d.code
                for d in db.query(ComplianceDomain).filter(
                    ComplianceDomain.framework_id == framework.id, ComplianceDomain.organisation_id.is_(None)
                )
            }
            if set(missing) - now_present:
                raise
    return framework
