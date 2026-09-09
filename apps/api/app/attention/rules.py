"""Rule registry — architecture/06-intelligence-layer.md §3: "Each rule
in attention_rules composes existing deterministic signals from other
domains (never restates their logic)... the rule is a join + threshold,
not a new calculation." Four rules, matching the four example signal
types architecture itself names (warranty+defect is the given example;
repeat failures, compliance breach, and lease+arrears overlap are its
other three named examples):

- WARRANTY_EXPIRING_WITH_OPEN_DEFECT: joins Warranty (Sprint 11) and
  Defect (Sprint 11) on the same component/property — architecture's
  own worked example, implemented exactly as given.
- REPEAT_FAILURE: wraps Sprint 14's repeat_repairs_for_property /
  repeat_failures_for_component — nothing here recomputes a repair
  count, it only reads that engine's own already-computed signal.
- COMPLIANCE_BREACH: wraps Sprint 17's compliance_status, surfacing
  entities where a currently-applicable requirement's computed status
  is a genuine breach (OVERDUE, OVERDUE_ACTION, MISSING_EVIDENCE) —
  not DUE_SOON/NEEDS_REVIEW, which are advisory rather than breaches.
- LEASE_ARREARS: wraps Sprint 20's arrears_for_lease, flagging active
  leases whose outstanding balance exceeds a configurable threshold.

Each `evaluate_*` function returns SignalCandidate rows; nothing here
writes to the database — attention_scan.py owns turning candidates
into upserted AttentionSignal rows.
"""

import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Callable

from sqlalchemy.orm import Session

from app.attention.models import AttentionSeverity
from app.commercial.arrears import arrears_for_lease
from app.commercial.models import Lease, LeaseStatus
from app.development.handover import OPEN_DEFECT_STATUSES
from app.development.models import Defect, Warranty, WarrantyStatus
from app.operations.compliance.models import ComplianceRequirement, RequirementApplicability
from app.operations.compliance.status_engine import compliance_status
from app.operations.models import Repair
from app.operations.repeat_repair import repeat_failures_for_component, repeat_repairs_for_property

DEFAULT_BREACH_STATUSES = ("OVERDUE", "OVERDUE_ACTION", "MISSING_EVIDENCE")


@dataclass
class SignalCandidate:
    entity_type: str
    entity_id: str
    explanation: dict = field(default_factory=dict)


def evaluate_warranty_expiring_with_open_defect(db: Session, organisation_id: uuid.UUID, config: dict) -> list[SignalCandidate]:
    expiry_within_days = config.get("expiry_within_days", 30)
    cutoff = date.today() + timedelta(days=expiry_within_days)
    warranties = (
        db.query(Warranty)
        .filter(
            Warranty.organisation_id == organisation_id,
            Warranty.status == WarrantyStatus.ACTIVE,
            Warranty.expiry_date >= date.today(),
            Warranty.expiry_date <= cutoff,
        )
        .all()
    )

    candidates = []
    for warranty in warranties:
        defect_query = db.query(Defect).filter(Defect.organisation_id == organisation_id, Defect.status.in_(OPEN_DEFECT_STATUSES))
        if warranty.component_id is not None:
            defects = defect_query.filter(Defect.component_id == warranty.component_id).all()
            scope = "component"
        elif warranty.property_id is not None:
            defects = defect_query.filter(Defect.property_id == warranty.property_id).all()
            scope = "property"
        else:
            defects = []
            scope = None
        if not defects:
            continue

        candidates.append(
            SignalCandidate(
                entity_type="warranty",
                entity_id=str(warranty.id),
                explanation={
                    "what": f"Warranty {warranty.warranty_reference} ({warranty.provider}) expires {warranty.expiry_date}, "
                    f"and {len(defects)} open defect(s) exist on the same {scope}.",
                    "why": "An expiring warranty with an unresolved defect on the same asset may mean the defect won't "
                    "be covered once the warranty lapses.",
                    "supporting_record_ids": [str(warranty.id)] + [str(d.id) for d in defects],
                    "recommended_investigation": "Confirm whether the open defect(s) will be claimed against this "
                    "warranty before it expires.",
                },
            )
        )
    return candidates


def evaluate_repeat_failure(db: Session, organisation_id: uuid.UUID, config: dict) -> list[SignalCandidate]:
    candidates: list[SignalCandidate] = []

    property_ids = {
        row[0] for row in db.query(Repair.property_id).filter(Repair.organisation_id == organisation_id).distinct()
    }
    for property_id in property_ids:
        signal = repeat_repairs_for_property(db, organisation_id, property_id)
        if signal is None:
            continue
        candidates.append(
            SignalCandidate(
                entity_type="property",
                entity_id=str(property_id),
                explanation={
                    "what": f"{signal.repair_count} repairs reported against this property in the last "
                    f"{signal.window_months} months (threshold {signal.threshold}).",
                    "why": "A high repair frequency at one property often indicates an underlying, unaddressed "
                    "issue rather than independent faults.",
                    "supporting_record_ids": [str(r) for r in signal.repair_ids],
                    "recommended_investigation": "Review the repair history for a common cause before authorising "
                    "another routine repair.",
                },
            )
        )

    component_ids = {
        row[0]
        for row in db.query(Repair.component_id)
        .filter(Repair.organisation_id == organisation_id, Repair.component_id.isnot(None))
        .distinct()
    }
    for component_id in component_ids:
        signal = repeat_failures_for_component(db, organisation_id, component_id)
        if signal is None:
            continue
        candidates.append(
            SignalCandidate(
                entity_type="component",
                entity_id=str(component_id),
                explanation={
                    "what": f"{signal.repair_count} repair interventions against this component in the last "
                    f"{signal.window_months} months (threshold {signal.threshold}).",
                    "why": "Repeated interventions on the same component often mean replacement is more "
                    "cost-effective than continued repair.",
                    "supporting_record_ids": [str(r) for r in signal.repair_ids],
                    "recommended_investigation": "Assess whether this component should be scheduled for "
                    "replacement instead of further repair.",
                },
            )
        )
    return candidates


def evaluate_compliance_breach(db: Session, organisation_id: uuid.UUID, config: dict) -> list[SignalCandidate]:
    breach_statuses = set(config.get("breach_statuses", list(DEFAULT_BREACH_STATUSES)))

    applicable_rows = (
        db.query(RequirementApplicability)
        .filter(
            RequirementApplicability.organisation_id == organisation_id,
            RequirementApplicability.applicable_from <= date.today(),
            (RequirementApplicability.applicable_to.is_(None)) | (RequirementApplicability.applicable_to >= date.today()),
        )
        .all()
    )
    requirement_ids = {row.requirement_id for row in applicable_rows}
    requirements_by_id = (
        {
            r.id: r
            for r in db.query(ComplianceRequirement).filter(
                ComplianceRequirement.id.in_(requirement_ids),
                (ComplianceRequirement.organisation_id == organisation_id) | (ComplianceRequirement.organisation_id.is_(None)),
            )
        }
        if requirement_ids
        else {}
    )

    # Grouped by entity, not one signal per requirement — an entity in
    # breach of several requirements at once gets one consolidated
    # signal, since AttentionSignal has no requirement_id column of its
    # own (entity_type/entity_id is this table's own identity key).
    breaches_by_entity: dict[tuple[str, str], list] = defaultdict(list)
    for row in applicable_rows:
        requirement = requirements_by_id.get(row.requirement_id)
        if requirement is None:
            continue
        result = compliance_status(
            db, organisation_id, entity_type=row.entity_type, entity_id=uuid.UUID(row.entity_id), requirement=requirement
        )
        if result.status.value in breach_statuses:
            breaches_by_entity[(row.entity_type, row.entity_id)].append((requirement, result))

    candidates = []
    for (entity_type, entity_id), breaches in breaches_by_entity.items():
        labels = ", ".join(f"{req.code} ({res.status.value})" for req, res in breaches)
        supporting_ids = []
        for req, res in breaches:
            supporting_ids.append(str(req.id))
            if res.open_action is not None:
                supporting_ids.append(str(res.open_action.id))
        candidates.append(
            SignalCandidate(
                entity_type=entity_type,
                entity_id=entity_id,
                explanation={
                    "what": f"{len(breaches)} compliance requirement(s) in breach for this {entity_type}: {labels}.",
                    "why": "These statuses represent a genuine breach or evidence gap, not just an upcoming due date.",
                    "supporting_record_ids": supporting_ids,
                    "recommended_investigation": "Review each requirement's inspection/action history and resolve "
                    "the breach.",
                },
            )
        )
    return candidates


def evaluate_lease_arrears(db: Session, organisation_id: uuid.UUID, config: dict) -> list[SignalCandidate]:
    threshold_pence = config.get("outstanding_threshold_pence", 50000)
    leases = db.query(Lease).filter(Lease.organisation_id == organisation_id, Lease.lease_status == LeaseStatus.ACTIVE).all()

    candidates = []
    for lease in leases:
        snapshot = arrears_for_lease(db, organisation_id, lease.id)
        if snapshot.outstanding_pence < threshold_pence:
            continue
        candidates.append(
            SignalCandidate(
                entity_type="lease",
                entity_id=str(lease.id),
                explanation={
                    "what": f"Lease {lease.lease_reference} has £{snapshot.outstanding_pence / 100:.2f} outstanding.",
                    "why": "Arrears on an active lease above the configured threshold may need a collection action.",
                    "supporting_record_ids": [str(lease.id)],
                    "recommended_investigation": "Review this lease's payment history and consider a collection action.",
                },
            )
        )
    return candidates


@dataclass
class RuleDefinition:
    name: str
    domain_scope: str
    default_config: dict
    default_severity: AttentionSeverity
    evaluate: Callable[[Session, uuid.UUID, dict], list[SignalCandidate]]


RULE_REGISTRY: dict[str, RuleDefinition] = {
    "WARRANTY_EXPIRING_WITH_OPEN_DEFECT": RuleDefinition(
        name="Warranty expiring with an open defect",
        domain_scope="Development",
        default_config={"expiry_within_days": 30},
        default_severity=AttentionSeverity.HIGH,
        evaluate=evaluate_warranty_expiring_with_open_defect,
    ),
    "REPEAT_FAILURE": RuleDefinition(
        name="Repeat repair or component failure pattern",
        domain_scope="Operations",
        default_config={},
        default_severity=AttentionSeverity.MEDIUM,
        evaluate=evaluate_repeat_failure,
    ),
    "COMPLIANCE_BREACH": RuleDefinition(
        name="Compliance requirement in breach",
        domain_scope="Operations",
        default_config={"breach_statuses": list(DEFAULT_BREACH_STATUSES)},
        default_severity=AttentionSeverity.CRITICAL,
        evaluate=evaluate_compliance_breach,
    ),
    "LEASE_ARREARS": RuleDefinition(
        name="Active lease with material arrears",
        domain_scope="Commercial",
        default_config={"outstanding_threshold_pence": 50000},
        default_severity=AttentionSeverity.HIGH,
        evaluate=evaluate_lease_arrears,
    ),
}
