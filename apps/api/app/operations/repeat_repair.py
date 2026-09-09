"""Repeat Repair / Component Failure engine — architecture/04-operations-domain.md
§2, spec §44: "Use deterministic rules... Do not let the LLM invent
calculations." Three independent, separately testable functions, each
returning `None` when the pattern isn't met rather than a zeroed-out
signal — callers (the router, Repairs Intelligence) treat `None` as
"nothing to report," not "reported nothing happened."

window_months/threshold/threshold_ratio/min_installed_base are read from
app.operations.models.RepairRuleConfig (per-organisation, lazily seeded
from RULE_DEFAULTS below) rather than hard-coded — the same
"deterministic, computed at read time" approach used throughout this
codebase (Data Health, Handover Readiness), so tuning sensitivity is a
config change, never a code change.
"""

import uuid
from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.development.models import Component
from app.operations.models import Repair, RepairRuleConfig, RepairStatus
from app.operations.schemas import ModelTrendSignalOut, RepeatFailureSignalOut, RepeatRepairSignalOut

REPEAT_REPAIRS_PER_PROPERTY = "REPEAT_REPAIRS_PER_PROPERTY"
REPEAT_FAILURES_PER_COMPONENT = "REPEAT_FAILURES_PER_COMPONENT"
COMPONENT_MODEL_TREND = "COMPONENT_MODEL_TREND"

RULE_DEFAULTS: dict[str, dict] = {
    REPEAT_REPAIRS_PER_PROPERTY: {"window_months": 12, "threshold": 3, "threshold_ratio": None, "min_installed_base": None},
    REPEAT_FAILURES_PER_COMPONENT: {"window_months": 18, "threshold": 3, "threshold_ratio": None, "min_installed_base": None},
    COMPONENT_MODEL_TREND: {"window_months": None, "threshold": None, "threshold_ratio": 0.15, "min_installed_base": 10},
}


def _rule_config(db: Session, organisation_id: uuid.UUID, rule_code: str) -> RepairRuleConfig:
    from app.operations.service import get_or_create_repair_rule_config

    return get_or_create_repair_rule_config(db, organisation_id, rule_code, RULE_DEFAULTS[rule_code])


def repeat_repairs_for_property(
    db: Session, organisation_id: uuid.UUID, property_id: uuid.UUID
) -> RepeatRepairSignalOut | None:
    """N+ repairs on the same property within window, regardless of
    category — flags a property-level pattern (e.g. persistent
    damp-adjacent repairs)."""
    config = _rule_config(db, organisation_id, REPEAT_REPAIRS_PER_PROPERTY)
    window_months, threshold = config.window_months, config.threshold
    cutoff = date.today() - timedelta(days=round(window_months * 30.44))

    repairs = (
        db.query(Repair)
        .filter(
            Repair.organisation_id == organisation_id,
            Repair.property_id == property_id,
            Repair.reported_date >= cutoff,
            Repair.status != RepairStatus.CANCELLED,
        )
        .all()
    )
    if len(repairs) < threshold:
        return None
    return RepeatRepairSignalOut(
        property_id=property_id,
        repair_count=len(repairs),
        window_months=window_months,
        threshold=threshold,
        repair_ids=[r.id for r in repairs],
    )


def repeat_failures_for_component(
    db: Session, organisation_id: uuid.UUID, component_id: uuid.UUID
) -> RepeatFailureSignalOut | None:
    """N+ repair interventions against the same component — spec
    example: "Component BOI-00428 has received 6 repair interventions
    within 18 months.\""""
    config = _rule_config(db, organisation_id, REPEAT_FAILURES_PER_COMPONENT)
    window_months, threshold = config.window_months, config.threshold
    cutoff = date.today() - timedelta(days=round(window_months * 30.44))

    repairs = (
        db.query(Repair)
        .filter(
            Repair.organisation_id == organisation_id,
            Repair.component_id == component_id,
            Repair.reported_date >= cutoff,
            Repair.status != RepairStatus.CANCELLED,
        )
        .all()
    )
    if len(repairs) < threshold:
        return None
    return RepeatFailureSignalOut(
        component_id=component_id,
        repair_count=len(repairs),
        window_months=window_months,
        threshold=threshold,
        repair_ids=[r.id for r in repairs],
    )


def component_model_trend(
    db: Session, organisation_id: uuid.UUID, component_type_id: uuid.UUID, manufacturer: str, model: str
) -> ModelTrendSignalOut | None:
    """Cross-property: what % of installed units of this exact model
    have had a failure — spec example: "17 boilers of Model X have
    experienced similar failures." Requires a minimum installed-base
    size to avoid false positives on small samples."""
    config = _rule_config(db, organisation_id, COMPONENT_MODEL_TREND)
    threshold_ratio, min_installed_base = config.threshold_ratio, config.min_installed_base

    components = (
        db.query(Component)
        .filter(
            Component.organisation_id == organisation_id,
            Component.component_type_id == component_type_id,
            Component.manufacturer == manufacturer,
            Component.model == model,
        )
        .all()
    )
    installed_count = len(components)
    if installed_count < min_installed_base:
        return None

    component_ids = [c.id for c in components]
    failed_component_ids = {
        row[0]
        for row in db.query(Repair.component_id)
        .filter(Repair.organisation_id == organisation_id, Repair.component_id.in_(component_ids))
        .distinct()
    }
    failed_count = len(failed_component_ids)
    failure_ratio = failed_count / installed_count

    if failure_ratio < threshold_ratio:
        return None
    return ModelTrendSignalOut(
        component_type_id=component_type_id,
        manufacturer=manufacturer,
        model=model,
        installed_count=installed_count,
        failed_count=failed_count,
        failure_ratio=round(failure_ratio, 3),
        threshold_ratio=threshold_ratio,
        component_ids=list(failed_component_ids),
    )
