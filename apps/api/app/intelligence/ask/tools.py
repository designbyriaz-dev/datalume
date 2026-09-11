"""Tool registry — architecture/06-intelligence-layer.md §1: "intelligence/
ask/ exposes a fixed, versioned set of tools (Python functions with typed
signatures) that call the deterministic services in development,
operations, commercial — the LLM cannot execute arbitrary queries; it
can only call get_compliance_status(property_id), get_repeat_repairs
(property_id), get_arrears(lease_id), etc., and those tools are exactly
the same deterministic functions documented in 03/04/05."

Every tool below is a thin wrapper around an already-built engine from
an earlier sprint — none computes anything new. Each always returns a
ToolResultOut, even when the underlying signal is "nothing to report"
(e.g. no repeat-repair pattern) — a grounded negative answer is still
grounded, and still worth citing.

**Which tools run for a given question is decided entirely by
pipeline.py's deterministic keyword router below (`KEYWORDS`), never
by the LLM itself** — see app/integrations/llm_provider.py's own
docstring for why that's a stronger reading of spec §57's "never
invent" guarantee than native function-calling would give.
"""

import uuid
from dataclasses import dataclass, field
from typing import Callable

from sqlalchemy.orm import Session

from app.commercial.arrears import arrears_for_lease
from app.commercial.models import Lease
from app.development.composition import component_type_names_for
from app.development.handover import compute_handover_readiness, properties_in_development
from app.development.models import Building, Component, Defect, Development, Property
from app.development.planned_investment import compute_investment_priority
from app.development.property_360 import get_property_360
from app.intelligence.ask.schemas import ToolResultOut
from app.operations.compliance.status_engine import list_compliance_statuses_for_entity
from app.operations.repeat_repair import repeat_failures_for_component, repeat_repairs_for_property


def _tool_result(tool_name: str, dataset: str, fields: list[str], entity_type: str, entity_id: uuid.UUID, records: list[dict], calculation: str) -> ToolResultOut:
    return ToolResultOut(
        tool_name=tool_name,
        dataset=dataset,
        fields=fields,
        filters={"entity_type": entity_type, "entity_id": str(entity_id)},
        time_period=None,
        records=records,
        calculation=calculation,
    )


def tool_get_compliance_status(db: Session, organisation_id: uuid.UUID, entity_type: str, entity_id: uuid.UUID) -> ToolResultOut:
    statuses = list_compliance_statuses_for_entity(db, organisation_id, entity_type, entity_id)
    records = [
        {
            "requirement_id": str(s.requirement_id),
            "status": s.status.value,
            "days_to_due": s.days_to_due,
            "latest_inspection_date": s.latest_inspection.inspection_date.isoformat() if s.latest_inspection else None,
            "latest_inspection_result": s.latest_inspection.result.value if s.latest_inspection else None,
        }
        for s in statuses
    ]
    return _tool_result(
        "get_compliance_status",
        "compliance_status",
        ["requirement_id", "status", "days_to_due", "latest_inspection_date", "latest_inspection_result"],
        entity_type,
        entity_id,
        records,
        f"compliance_status() for every requirement currently applicable to this {entity_type} ({len(records)} found)",
    )


def tool_get_repeat_repairs(db: Session, organisation_id: uuid.UUID, entity_type: str, entity_id: uuid.UUID) -> ToolResultOut:
    signal = repeat_repairs_for_property(db, organisation_id, entity_id)
    records = (
        [{"repair_count": signal.repair_count, "window_months": signal.window_months, "threshold": signal.threshold, "repair_ids": [str(r) for r in signal.repair_ids]}]
        if signal
        else []
    )
    calc = (
        f"repeat_repairs_for_property(): {signal.repair_count} repairs in {signal.window_months} months, threshold {signal.threshold}"
        if signal
        else "repeat_repairs_for_property(): no repeat-repair pattern currently triggered for this property"
    )
    return _tool_result("get_repeat_repairs", "repairs", ["repair_count", "window_months", "threshold", "repair_ids"], entity_type, entity_id, records, calc)


def tool_get_repeat_failures(db: Session, organisation_id: uuid.UUID, entity_type: str, entity_id: uuid.UUID) -> ToolResultOut:
    signal = repeat_failures_for_component(db, organisation_id, entity_id)
    records = (
        [{"repair_count": signal.repair_count, "window_months": signal.window_months, "threshold": signal.threshold, "repair_ids": [str(r) for r in signal.repair_ids]}]
        if signal
        else []
    )
    calc = (
        f"repeat_failures_for_component(): {signal.repair_count} interventions in {signal.window_months} months, threshold {signal.threshold}"
        if signal
        else "repeat_failures_for_component(): no repeat-failure pattern currently triggered for this component"
    )
    return _tool_result("get_repeat_failures", "repairs", ["repair_count", "window_months", "threshold", "repair_ids"], entity_type, entity_id, records, calc)


def tool_get_arrears(db: Session, organisation_id: uuid.UUID, entity_type: str, entity_id: uuid.UUID) -> ToolResultOut:
    lease = db.query(Lease).filter(Lease.id == entity_id, Lease.organisation_id == organisation_id).first()
    if lease is None:
        return _tool_result("get_arrears", "arrears", [], entity_type, entity_id, [], "arrears_for_lease(): lease not found")
    snapshot = arrears_for_lease(db, organisation_id, entity_id)
    records = [
        {
            "total_due_pence": snapshot.total_due_pence,
            "outstanding_pence": snapshot.outstanding_pence,
            "ageing_pence": snapshot.ageing_pence,
            "credits_pence": snapshot.credits_pence,
            "unallocated_pence": snapshot.unallocated_pence,
        }
    ]
    return _tool_result(
        "get_arrears",
        "arrears",
        ["total_due_pence", "outstanding_pence", "ageing_pence", "credits_pence", "unallocated_pence"],
        entity_type,
        entity_id,
        records,
        f"arrears_for_lease() as of {snapshot.as_of}",
    )


def tool_get_planned_investment(db: Session, organisation_id: uuid.UUID, entity_type: str, entity_id: uuid.UUID) -> ToolResultOut:
    component = db.query(Component).filter(Component.id == entity_id, Component.organisation_id == organisation_id).first()
    if component is None:
        return _tool_result("get_planned_investment", "planned_investment", [], entity_type, entity_id, [], "compute_investment_priority(): component not found")
    type_names = component_type_names_for(db, [component])
    score = compute_investment_priority(db, organisation_id, component, type_names.get(component.component_type_id, "Unknown"))
    records = [
        {
            "priority_score": score.priority_score,
            "factors": [{"factor_code": f.factor_code, "applicable": f.applicable, "value": f.value, "detail": f.detail} for f in score.factors],
        }
    ]
    return _tool_result(
        "get_planned_investment",
        "planned_investment",
        ["priority_score", "factors"],
        entity_type,
        entity_id,
        records,
        f"compute_investment_priority(): score {score.priority_score}/100",
    )


def tool_get_property_360(db: Session, organisation_id: uuid.UUID, entity_type: str, entity_id: uuid.UUID) -> ToolResultOut:
    prop = db.query(Property).filter(Property.id == entity_id, Property.organisation_id == organisation_id).first()
    if prop is None:
        return _tool_result("get_property_360", "property_360", [], entity_type, entity_id, [], "get_property_360(): property not found")
    view = get_property_360(db, organisation_id, prop)
    records = [
        {
            "address": view.property.address,
            "status": view.property.status,
            "components_count": len(view.components),
            "open_defects_count": sum(1 for d in view.defects if d.status not in ("COMPLETED", "CLOSED", "REJECTED")),
            "warranties_count": len(view.warranties),
            "repairs_count": len(view.repairs),
            "leases_count": len(view.leases),
            "data_health_findings_count": len(view.data_health_findings),
        }
    ]
    return _tool_result(
        "get_property_360",
        "property_360",
        list(records[0].keys()),
        entity_type,
        entity_id,
        records,
        "get_property_360(): composed summary across every domain with a canonical table",
    )


_DEFECT_FK_BY_ENTITY_TYPE = {"building": Defect.building_id, "property": Defect.property_id, "component": Defect.component_id}


def tool_get_defects(db: Session, organisation_id: uuid.UUID, entity_type: str, entity_id: uuid.UUID) -> ToolResultOut:
    fk_column = _DEFECT_FK_BY_ENTITY_TYPE.get(entity_type)
    if fk_column is None:
        return _tool_result("get_defects", "defects", [], entity_type, entity_id, [], f"defects aren't tracked directly against a {entity_type}")
    defects = db.query(Defect).filter(Defect.organisation_id == organisation_id, fk_column == entity_id).order_by(Defect.reported_date.desc()).all()
    records = [{"defect_reference": d.defect_reference, "category": d.category, "severity": d.severity.value, "status": d.status.value, "reported_date": d.reported_date.isoformat()} for d in defects]
    return _tool_result(
        "get_defects",
        "defects",
        ["defect_reference", "category", "severity", "status", "reported_date"],
        entity_type,
        entity_id,
        records,
        f"{len(records)} defect(s) recorded against this {entity_type}",
    )


def tool_get_development_summary(db: Session, organisation_id: uuid.UUID, entity_type: str, entity_id: uuid.UUID) -> ToolResultOut:
    """A thin wrapper around the same deterministic computations the
    Development detail page and the Handover Readiness report already
    use (compute_handover_readiness, properties_in_development) — no
    new calculation invented, same "every tool is an already-built
    engine" rule this module's own docstring states."""
    development = db.query(Development).filter(Development.id == entity_id, Development.organisation_id == organisation_id).first()
    if development is None:
        return _tool_result("get_development_summary", "development_summary", [], entity_type, entity_id, [], "get_development_summary(): development not found")

    buildings_count = db.query(Building).filter(Building.development_id == development.id).count()
    properties = properties_in_development(db, organisation_id, development.id)
    score_pct, _checks = compute_handover_readiness(db, organisation_id, development.id)
    status_counts: dict[str, int] = {}
    for p in properties:
        status_counts[p.status.value] = status_counts.get(p.status.value, 0) + 1

    records = [
        {
            "development_reference": development.development_reference,
            "name": development.name,
            "buildings_count": buildings_count,
            "properties_count": len(properties),
            "properties_by_status": status_counts,
            "handover_readiness_score_pct": score_pct,
            "handover_ready": score_pct >= 100.0,
        }
    ]
    return _tool_result(
        "get_development_summary",
        "development_summary",
        list(records[0].keys()),
        entity_type,
        entity_id,
        records,
        f"{len(properties)} propert(y/ies) across {buildings_count} building(s); handover readiness {score_pct:.1f}%",
    )


@dataclass
class ToolDefinition:
    name: str
    description: str
    applicable_entity_types: tuple[str, ...]
    keywords: tuple[str, ...]
    execute: Callable[[Session, uuid.UUID, str, uuid.UUID], ToolResultOut] = field(repr=False)


TOOL_REGISTRY: dict[str, ToolDefinition] = {
    "get_compliance_status": ToolDefinition(
        name="get_compliance_status",
        description="Deterministic compliance status (Sprint 17) for every requirement currently applicable to an entity.",
        applicable_entity_types=("building", "property", "component"),
        keywords=("compliance", "gas safety", "fire safety", "certificate", "inspection", "overdue", "safety check", "legal"),
        execute=tool_get_compliance_status,
    ),
    "get_repeat_repairs": ToolDefinition(
        name="get_repeat_repairs",
        description="Whether a property currently shows a repeat-repair pattern (Sprint 14).",
        applicable_entity_types=("property",),
        keywords=("repeat repair", "recurring repair", "repair pattern", "repairs", "repair history"),
        execute=tool_get_repeat_repairs,
    ),
    "get_repeat_failures": ToolDefinition(
        name="get_repeat_failures",
        description="Whether a component currently shows a repeat-failure pattern (Sprint 14).",
        applicable_entity_types=("component",),
        keywords=("repeat failure", "component failure", "failing", "keeps breaking", "keeps failing"),
        execute=tool_get_repeat_failures,
    ),
    "get_arrears": ToolDefinition(
        name="get_arrears",
        description="A lease's current arrears snapshot (Sprint 20): outstanding balance, ageing, credits, unallocated payments.",
        applicable_entity_types=("lease",),
        keywords=("arrears", "rent owed", "outstanding rent", "overdue rent", "behind on rent", "unpaid rent"),
        execute=tool_get_arrears,
    ),
    "get_planned_investment": ToolDefinition(
        name="get_planned_investment",
        description="A component's planned-investment priority score and factor breakdown (Sprint 18).",
        applicable_entity_types=("component",),
        keywords=("planned investment", "replacement", "investment priority", "should we replace", "end of life"),
        execute=tool_get_planned_investment,
    ),
    "get_property_360": ToolDefinition(
        name="get_property_360",
        description="A composed summary of a property across every domain with a canonical table (Sprint 13).",
        applicable_entity_types=("property",),
        keywords=("overview", "summary", "tell me about", "360", "what do we know"),
        execute=tool_get_property_360,
    ),
    "get_defects": ToolDefinition(
        name="get_defects",
        description="Defects recorded against an entity (Sprint 11).",
        applicable_entity_types=("building", "property", "component"),
        keywords=("defect", "snag", "snagging", "fault"),
        execute=tool_get_defects,
    ),
    "get_development_summary": ToolDefinition(
        name="get_development_summary",
        description="A development's building/property counts and handover readiness score (Sprint 12).",
        applicable_entity_types=("development",),
        keywords=("overview", "summary", "tell me about", "handover", "ready", "readiness", "how many properties", "how many buildings"),
        execute=tool_get_development_summary,
    ),
}
