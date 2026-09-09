"""Planned Investment scoring — architecture/03-development-domain.md
§6, spec §40: "do not use age alone." `investment_priority` is a
weighted, fully explainable score with every contributing factor
returned (`PlannedInvestmentFactorOut.detail`/`value`/`applicable`),
never a single opaque number — same reasoning and shape as Handover
Readiness's checks (Sprint 12).

architecture's own pseudocode frames this as a nightly scheduled job
(`worker/jobs/component_lifecycle.py`) that upserts a stored
`planned_investment_signal` row. This build has no job/worker
infrastructure yet — the roadmap's own Sprint 21 ("Cross-Domain
Attention Engine... nightly scan job") is explicitly where that
infrastructure first appears. Rather than build a job runner two
sprints early for one engine, this follows every other scoring engine
in this codebase (Data Health, Handover Readiness, the repeat-repair/
repeat-hazard signals, Sprint 17's compliance_status): computed fresh
on every read, nothing persisted, so there is nothing to go stale
between writes. The nightly-job framing becomes real infrastructure
once Sprint 21 actually builds a job runner other engines can adopt
too, not invented early for this one.

Five factors, matching architecture's own pseudocode:
- AGE_RATIO: age / expected_life_years (spec explicitly forbids using
  this alone — it's one of five, default weight 0.35, still the
  largest single factor since it's the most universally available
  signal, but never the whole score).
- CONDITION_SIGNAL: the component's own most recent compliance
  Inspection result (any requirement, entity_type="component") —
  reusing Sprint 16's Inspection table rather than inventing a second,
  parallel condition-tracking mechanism. Deliberately NOT derived from
  StockConditionSurvey.condition_ratings: that JSONB blob is a
  free-form {element: rating} map with no documented mapping onto
  individual components, and inventing one would be exactly the kind
  of unfounded interpretation this codebase avoids elsewhere (see
  operations/stock_condition/models.py's own docstring).
- REPAIR_FREQUENCY: Repair count against this component within a
  per-org configurable window (PlannedInvestmentConfig), reusing
  Sprint 14's Repair table.
- FAILURE_PATTERN: whether repeat_failures_for_component (Sprint 14)
  currently flags this component.
- COMPLIANCE_LINKED: whether an OPEN ComplianceAction (Sprint 16)
  currently exists against this component.

A factor with nothing to go on (no inspection ever recorded; no
installation_date/expected_life_years) is `applicable=False` and
excluded from the weighted average — the same "vacuous exclude, not a
free pass or an automatic penalty" renormalisation Handover Readiness
uses, just applied per-component instead of per-development.
"""

import uuid
from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.development.composition import component_type_names_for
from app.development.models import Component
from app.development.schemas import PlannedInvestmentFactorOut, PlannedInvestmentScoreOut
from app.operations.compliance.models import ComplianceAction, ComplianceActionStatus, Inspection, InspectionResult
from app.operations.models import Repair, RepairStatus
from app.operations.repeat_repair import repeat_failures_for_component

DEFAULT_FACTOR_WEIGHTS: dict[str, float] = {
    "AGE_RATIO": 0.35,
    "CONDITION_SIGNAL": 0.25,
    "REPAIR_FREQUENCY": 0.20,
    "FAILURE_PATTERN": 0.10,
    "COMPLIANCE_LINKED": 0.10,
}
FACTOR_LABELS: dict[str, str] = {
    "AGE_RATIO": "Age vs expected life",
    "CONDITION_SIGNAL": "Latest inspection condition",
    "REPAIR_FREQUENCY": "Repair frequency",
    "FAILURE_PATTERN": "Repeat failure pattern",
    "COMPLIANCE_LINKED": "Linked open compliance action",
}

_CONDITION_VALUES: dict[InspectionResult, float] = {
    InspectionResult.SATISFACTORY: 0.0,
    InspectionResult.ADVISORY: 0.5,
    InspectionResult.UNSATISFACTORY: 1.0,
}


def _factor(code: str, weight: float, *, applicable: bool, value: float | None, detail: str) -> PlannedInvestmentFactorOut:
    return PlannedInvestmentFactorOut(
        factor_code=code, label=FACTOR_LABELS[code], weight=weight, applicable=applicable, value=value, detail=detail
    )


def _age_ratio_factor(component: Component, weight: float) -> PlannedInvestmentFactorOut:
    if component.installation_date is None or not component.expected_life_years:
        return _factor("AGE_RATIO", weight, applicable=False, value=None, detail="No installation date or expected life recorded")
    age_years = (date.today() - component.installation_date).days / 365.25
    ratio = age_years / component.expected_life_years
    value = min(max(ratio, 0.0), 1.0)
    detail = f"{age_years:.1f} years old of an expected {component.expected_life_years}-year life ({ratio * 100:.0f}%)"
    return _factor("AGE_RATIO", weight, applicable=True, value=value, detail=detail)


def _condition_signal_factor(db: Session, organisation_id: uuid.UUID, component: Component, weight: float) -> PlannedInvestmentFactorOut:
    latest = (
        db.query(Inspection)
        .filter(
            Inspection.organisation_id == organisation_id,
            Inspection.entity_type == "component",
            Inspection.entity_id == str(component.id),
        )
        .order_by(Inspection.inspection_date.desc())
        .first()
    )
    if latest is None:
        return _factor("CONDITION_SIGNAL", weight, applicable=False, value=None, detail="No inspection ever recorded against this component")
    value = _CONDITION_VALUES[latest.result]
    detail = f"Last inspection ({latest.inspection_date}) result: {latest.result.value}"
    return _factor("CONDITION_SIGNAL", weight, applicable=True, value=value, detail=detail)


def _repair_frequency_factor(
    db: Session, organisation_id: uuid.UUID, component: Component, weight: float, *, window_months: int, threshold: int
) -> PlannedInvestmentFactorOut:
    cutoff = date.today() - timedelta(days=round(window_months * 30.44))
    count = (
        db.query(Repair)
        .filter(
            Repair.organisation_id == organisation_id,
            Repair.component_id == component.id,
            Repair.reported_date >= cutoff,
            Repair.status != RepairStatus.CANCELLED,
        )
        .count()
    )
    value = min(count / threshold, 1.0) if threshold else 0.0
    detail = f"{count} repair(s) in the last {window_months} months (threshold {threshold})"
    return _factor("REPAIR_FREQUENCY", weight, applicable=True, value=value, detail=detail)


def _failure_pattern_factor(db: Session, organisation_id: uuid.UUID, component: Component, weight: float) -> PlannedInvestmentFactorOut:
    signal = repeat_failures_for_component(db, organisation_id, component.id)
    if signal is None:
        return _factor("FAILURE_PATTERN", weight, applicable=True, value=0.0, detail="No repeat-failure signal currently flagged")
    detail = f"Repeat-failure signal flagged: {signal.repair_count} interventions in {signal.window_months} months"
    return _factor("FAILURE_PATTERN", weight, applicable=True, value=1.0, detail=detail)


def _compliance_linked_factor(db: Session, organisation_id: uuid.UUID, component: Component, weight: float) -> PlannedInvestmentFactorOut:
    open_count = (
        db.query(ComplianceAction)
        .filter(
            ComplianceAction.organisation_id == organisation_id,
            ComplianceAction.entity_type == "component",
            ComplianceAction.entity_id == str(component.id),
            ComplianceAction.status == ComplianceActionStatus.OPEN,
        )
        .count()
    )
    value = 1.0 if open_count > 0 else 0.0
    detail = f"{open_count} open compliance action(s)" if open_count else "No open compliance actions"
    return _factor("COMPLIANCE_LINKED", weight, applicable=True, value=value, detail=detail)


def get_factor_weights(db: Session, organisation_id: uuid.UUID) -> dict[str, float]:
    from app.development.service import get_or_create_planned_investment_weight

    return {
        code: get_or_create_planned_investment_weight(db, organisation_id, code, default).weight
        for code, default in DEFAULT_FACTOR_WEIGHTS.items()
    }


def compute_investment_priority(
    db: Session, organisation_id: uuid.UUID, component: Component, component_type_name: str
) -> PlannedInvestmentScoreOut:
    from app.development.service import get_or_create_planned_investment_config

    weights = get_factor_weights(db, organisation_id)
    config = get_or_create_planned_investment_config(db, organisation_id)

    factors = [
        _age_ratio_factor(component, weights["AGE_RATIO"]),
        _condition_signal_factor(db, organisation_id, component, weights["CONDITION_SIGNAL"]),
        _repair_frequency_factor(
            db,
            organisation_id,
            component,
            weights["REPAIR_FREQUENCY"],
            window_months=config.repair_frequency_window_months,
            threshold=config.repair_frequency_threshold,
        ),
        _failure_pattern_factor(db, organisation_id, component, weights["FAILURE_PATTERN"]),
        _compliance_linked_factor(db, organisation_id, component, weights["COMPLIANCE_LINKED"]),
    ]

    applicable = [f for f in factors if f.applicable]
    total_weight = sum(f.weight for f in applicable)
    priority_score = (
        sum(f.weight * f.value for f in applicable) / total_weight * 100 if total_weight and applicable else 0.0
    )

    return PlannedInvestmentScoreOut(
        component_id=component.id,
        component_reference=component.component_reference,
        component_type_name=component_type_name,
        priority_score=round(priority_score, 1),
        factors=factors,
    )


def list_planned_investment(
    db: Session,
    organisation_id: uuid.UUID,
    *,
    development_id: uuid.UUID | None = None,
    building_id: uuid.UUID | None = None,
    property_id: uuid.UUID | None = None,
) -> list[PlannedInvestmentScoreOut]:
    """Only components with expected_life_years recorded are scored —
    the pseudocode's own "components_with_expected_life" scope. A
    component with no expected life has no age_ratio and, in practice,
    is usually not the kind of major asset (boiler, roof, lift) this
    engine exists to flag."""
    query = db.query(Component).filter(Component.organisation_id == organisation_id, Component.expected_life_years.isnot(None))
    if development_id is not None:
        query = query.filter(Component.development_id == development_id)
    if building_id is not None:
        query = query.filter(Component.building_id == building_id)
    if property_id is not None:
        query = query.filter(Component.property_id == property_id)
    components = query.all()

    component_type_names = component_type_names_for(db, components)
    scores = [
        compute_investment_priority(db, organisation_id, c, component_type_names.get(c.component_type_id, "Unknown"))
        for c in components
    ]
    return sorted(scores, key=lambda s: s.priority_score, reverse=True)
