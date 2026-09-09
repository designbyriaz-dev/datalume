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

Sprint 5 only has Property to check against — component/development/
compliance rules from the full spec §42 list get added the same way,
one function each, as their domain models land.
"""

from collections import Counter
from dataclasses import dataclass, field
from datetime import date

from sqlalchemy.orm import Session

from app.data_health.models import DataHealthFinding, FindingSeverity
from app.development.models import Property
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


RULES = [
    check_missing_property_type,
    check_missing_uprn,
    check_missing_postcode,
    check_duplicate_properties,
    check_missing_stock_condition_survey,
    check_stale_stock_condition_survey,
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
