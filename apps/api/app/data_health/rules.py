"""Rule registry v1 — architecture/02-data-platform.md §5.

Each rule is a plain, individually-testable function returning a
CheckResult: how many records the check applies to, how many failed it,
and one Finding per failure. `run_data_health_checks` runs every
registered rule, replaces the organisation's stored findings, and
computes an overall score as an unweighted mean of per-check pass
ratios — spec calls for *configurable* weights eventually; v1 is
deliberately the simplest version that's still transparent (every
contributing check_code and its own pass ratio is returned, not just
the headline number).

Sprint 5 only had Property to check against; component and handover
checks landed Post-Sprint-24, once those domain models existed. Spec
§42's full 15-item list still has more unimplemented than done —
missing component types/serial numbers/installation dates/warranties/
specifications/evidence, conflicting references, invalid dates,
duplicate documents — added the same way, one function each, as the
next one is worth the real query logic it needs (several genuinely
need new tracking this codebase doesn't have yet, e.g. no evidence
document is currently linked to a specific compliance requirement in
a way "missing evidence" could query).
"""

from collections import Counter
from dataclasses import dataclass, field
from datetime import date

from sqlalchemy.orm import Session

from app.data_health.models import DataHealthFinding, FindingSeverity
from app.development.models import Component, HandoverRecord, Property, PropertyStatus
from app.identifiers.service import get_external_references_bulk
from app.operations.stock_condition.models import StockConditionSurvey


@dataclass
class Finding:
    check_code: str
    severity: FindingSeverity
    affected_entity_type: str
    affected_entity_id: str
    message: str


@dataclass
class CheckResult:
    check_code: str
    applicable_count: int
    failing_count: int
    findings: list[Finding] = field(default_factory=list)

    @property
    def pass_ratio(self) -> float:
        if self.applicable_count == 0:
            return 1.0
        return (self.applicable_count - self.failing_count) / self.applicable_count


def check_missing_property_type(db: Session, organisation_id) -> CheckResult:
    properties = db.query(Property).filter(Property.organisation_id == organisation_id).all()
    findings = [
        Finding(
            "MISSING_PROPERTY_TYPE",
            FindingSeverity.MEDIUM,
            "property",
            str(p.id),
            f"{p.property_reference} has no property type recorded.",
        )
        for p in properties
        if not p.property_type
    ]
    return CheckResult("MISSING_PROPERTY_TYPE", len(properties), len(findings), findings)


def check_missing_uprn(db: Session, organisation_id) -> CheckResult:
    # UPRN moved off Property onto app.identifiers.models.ExternalReference
    # in Sprint 7 — see that module's docstring for why. One bulk lookup
    # here rather than N, same reasoning as development/presenters.py.
    properties = db.query(Property).filter(Property.organisation_id == organisation_id).all()
    refs_by_id = get_external_references_bulk(db, organisation_id, "property", [p.id for p in properties])
    findings = [
        Finding(
            "MISSING_UPRN",
            FindingSeverity.LOW,
            "property",
            str(p.id),
            f"{p.property_reference} has no UPRN recorded.",
        )
        for p in properties
        if not refs_by_id.get(str(p.id), {}).get("UPRN")
    ]
    return CheckResult("MISSING_UPRN", len(properties), len(findings), findings)


def check_missing_postcode(db: Session, organisation_id) -> CheckResult:
    properties = db.query(Property).filter(Property.organisation_id == organisation_id).all()
    findings = [
        Finding(
            "MISSING_POSTCODE",
            FindingSeverity.LOW,
            "property",
            str(p.id),
            f"{p.property_reference} has no postcode recorded.",
        )
        for p in properties
        if not p.postcode
    ]
    return CheckResult("MISSING_POSTCODE", len(properties), len(findings), findings)


def _normalize_address(address: str) -> str:
    return " ".join(address.lower().split())


def check_duplicate_properties(db: Session, organisation_id) -> CheckResult:
    properties = db.query(Property).filter(Property.organisation_id == organisation_id).all()
    counts = Counter(_normalize_address(p.address) for p in properties)
    findings = [
        Finding(
            "DUPLICATE_PROPERTIES",
            FindingSeverity.HIGH,
            "property",
            str(p.id),
            f"{p.property_reference}'s address matches {counts[_normalize_address(p.address)] - 1} "
            "other propert(y/ies) in this organisation.",
        )
        for p in properties
        if counts[_normalize_address(p.address)] > 1
    ]
    return CheckResult("DUPLICATE_PROPERTIES", len(properties), len(findings), findings)


def check_missing_stock_condition_survey(db: Session, organisation_id) -> CheckResult:
    """architecture/04-operations-domain.md §6: a stock condition
    survey "feeds... Data Health (missing/stale surveys)" — Sprint 18's
    own instruction, closed here."""
    properties = db.query(Property).filter(Property.organisation_id == organisation_id).all()
    surveyed_property_ids = {
        row[0]
        for row in db.query(StockConditionSurvey.property_id)
        .filter(StockConditionSurvey.organisation_id == organisation_id)
        .distinct()
    }
    findings = [
        Finding(
            "MISSING_STOCK_CONDITION_SURVEY",
            FindingSeverity.MEDIUM,
            "property",
            str(p.id),
            f"{p.property_reference} has no stock condition survey recorded.",
        )
        for p in properties
        if p.id not in surveyed_property_ids
    ]
    return CheckResult("MISSING_STOCK_CONDITION_SURVEY", len(properties), len(findings), findings)


def check_stale_stock_condition_survey(db: Session, organisation_id) -> CheckResult:
    """Applies only to properties with at least one survey on record —
    a property with none is check_missing_stock_condition_survey's
    concern, not this one's, so it isn't double-counted as failing two
    checks for the same underlying gap."""
    properties = db.query(Property).filter(Property.organisation_id == organisation_id).all()
    surveys = (
        db.query(StockConditionSurvey)
        .filter(StockConditionSurvey.organisation_id == organisation_id)
        .order_by(StockConditionSurvey.survey_date.desc())
        .all()
    )
    latest_by_property = {}
    for s in surveys:
        latest_by_property.setdefault(s.property_id, s)

    applicable = [p for p in properties if p.id in latest_by_property]
    findings = [
        Finding(
            "STALE_STOCK_CONDITION_SURVEY",
            FindingSeverity.MEDIUM,
            "property",
            str(p.id),
            f"{p.property_reference}'s stock condition survey was due {latest_by_property[p.id].next_survey_due}.",
        )
        for p in applicable
        if latest_by_property[p.id].next_survey_due is not None and latest_by_property[p.id].next_survey_due < date.today()
    ]
    return CheckResult("STALE_STOCK_CONDITION_SURVEY", len(applicable), len(findings), findings)


def check_orphan_components(db: Session, organisation_id) -> CheckResult:
    """spec §42's "Orphan components". Component can attach to any
    combination of development/building/property/space (models.py's own
    docstring — a lift might belong to a building with no specific
    property) plus an optional parent_component_id for the sub-component
    hierarchy — a row with *all five* unset isn't "loosely scoped",
    it's disconnected from the property hierarchy entirely, which spec
    §24's whole point (every asset traceable to where it physically is)
    depends on."""
    components = db.query(Component).filter(Component.organisation_id == organisation_id).all()
    findings = [
        Finding(
            "ORPHAN_COMPONENT",
            FindingSeverity.HIGH,
            "component",
            str(c.id),
            f"{c.component_reference} has no development, building, property, space, or parent "
            "component linked — it isn't traceable to anywhere in the portfolio.",
        )
        for c in components
        if not any((c.development_id, c.building_id, c.property_id, c.space_id, c.parent_component_id))
    ]
    return CheckResult("ORPHAN_COMPONENT", len(components), len(findings), findings)


def check_duplicate_components(db: Session, organisation_id) -> CheckResult:
    """Same "identical key seen more than once" shape as
    check_duplicate_properties above, but the key is location + type +
    make/model rather than an address — two components at the exact
    same place, of the exact same type and manufacturer/model, are a
    near-certain accidental double-entry (a real duplicate boiler two
    rows apart), not two genuinely different assets that happen to
    match."""
    components = db.query(Component).filter(Component.organisation_id == organisation_id).all()

    def key(c: Component) -> tuple:
        return (
            c.component_type_id,
            c.development_id,
            c.building_id,
            c.property_id,
            c.space_id,
            (c.manufacturer or "").strip().lower(),
            (c.model or "").strip().lower(),
        )

    counts = Counter(key(c) for c in components)
    findings = [
        Finding(
            "DUPLICATE_COMPONENT",
            FindingSeverity.MEDIUM,
            "component",
            str(c.id),
            f"{c.component_reference} matches {counts[key(c)] - 1} other component(s) of the same type, "
            "make and model at the same location.",
        )
        for c in components
        if counts[key(c)] > 1
    ]
    return CheckResult("DUPLICATE_COMPONENT", len(components), len(findings), findings)


def check_missing_handover_information(db: Session, organisation_id) -> CheckResult:
    """spec §42's "Missing handover information". HandoverRecord
    (development/models.py) is written in the same transaction as a
    property's READY_FOR_HANDOVER -> HANDED_OVER flip
    (development/service.py.authorise_handover) — the permanent
    evidence handover actually happened and what was known at the time.
    A property already marked HANDED_OVER with no such row means that
    evidence is missing, whatever the reason (a status set some other
    way, a migrated/imported record, ...)."""
    properties = (
        db.query(Property)
        .filter(Property.organisation_id == organisation_id, Property.status == PropertyStatus.HANDED_OVER)
        .all()
    )
    recorded_property_ids = {
        row[0]
        for row in db.query(HandoverRecord.property_id).filter(HandoverRecord.organisation_id == organisation_id).distinct()
    }
    findings = [
        Finding(
            "MISSING_HANDOVER_INFORMATION",
            FindingSeverity.HIGH,
            "property",
            str(p.id),
            f"{p.property_reference} is marked HANDED_OVER but has no handover record on file.",
        )
        for p in properties
        if p.id not in recorded_property_ids
    ]
    return CheckResult("MISSING_HANDOVER_INFORMATION", len(properties), len(findings), findings)


RULES = [
    check_missing_property_type,
    check_missing_uprn,
    check_missing_postcode,
    check_duplicate_properties,
    check_missing_stock_condition_survey,
    check_stale_stock_condition_survey,
    check_orphan_components,
    check_duplicate_components,
    check_missing_handover_information,
]


def run_data_health_checks(db: Session, organisation_id) -> tuple[float, list[CheckResult]]:
    results = [rule(db, organisation_id) for rule in RULES]

    db.query(DataHealthFinding).filter(DataHealthFinding.organisation_id == organisation_id).delete()
    for result in results:
        for f in result.findings:
            db.add(
                DataHealthFinding(
                    organisation_id=organisation_id,
                    check_code=f.check_code,
                    severity=f.severity,
                    affected_entity_type=f.affected_entity_type,
                    affected_entity_id=f.affected_entity_id,
                    message=f.message,
                )
            )
    db.flush()

    score = sum(r.pass_ratio for r in results) / len(results) * 100 if results else 100.0
    return round(score, 1), results
