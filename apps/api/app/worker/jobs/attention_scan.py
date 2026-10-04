"""Attention Engine nightly scan — architecture/06-intelligence-layer.md
§3: "A nightly worker job... evaluates active rules per organisation
and upserts attention_signals, so Home and Alerts read pre-computed
signals — never scanning the whole dataset on page load." This is the
one job registered in app/worker/main.py; see that module for the
scheduling loop (this codebase's first, per the roadmap's own plan).
"""

import uuid
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.attention.rules import RULE_REGISTRY
from app.attention.service import list_rules, upsert_signal


@dataclass
class ScanResult:
    rules_evaluated: int
    signals_created: int
    signals_refreshed: int


def run_attention_scan(db: Session, organisation_id: uuid.UUID) -> ScanResult:
    rules_by_code = {rule.code: rule for rule in list_rules(db, organisation_id)}

    rules_evaluated = 0
    signals_created = 0
    signals_refreshed = 0

    for code, definition in RULE_REGISTRY.items():
        rule = rules_by_code.get(code)
        if rule is None or not rule.is_active:
            continue
        rules_evaluated += 1

        candidates = definition.evaluate(db, organisation_id, rule.rule_definition)
        for candidate in candidates:
            _, created = upsert_signal(
                db,
                organisation_id,
                rule,
                entity_type=candidate.entity_type,
                entity_id=candidate.entity_id,
                severity=rule.severity_default,
                explanation=candidate.explanation,
            )
            if created:
                signals_created += 1
            else:
                signals_refreshed += 1

    return ScanResult(rules_evaluated=rules_evaluated, signals_created=signals_created, signals_refreshed=signals_refreshed)


def run_attention_scan_for_all_organisations(db: Session) -> dict[uuid.UUID, ScanResult]:
    """Used by worker/main.py's nightly loop — every organisation gets
    its own independent scan and its own rule configs.

    Unlike this module's own run_attention_scan (also called directly
    from attention/router.py's trigger_scan endpoint, where
    get_tenant_db already scopes `db` before this function ever runs),
    this entrypoint starts with no tenant context at all — organisations
    itself carries no RLS policy, so the id listing below works, but
    every table run_attention_scan actually reads (repairs, hazards,
    leases, compliance requirements, attention_rules/signals...) is
    RLS-protected and would silently see nothing for every single
    organisation without scoping to each one first."""
    from app.core.tenancy import TenantScopedSession
    from app.organisations.models import Organisation

    results = {}
    for (organisation_id,) in db.query(Organisation.id).all():
        TenantScopedSession(db, organisation_id)
        results[organisation_id] = run_attention_scan(db, organisation_id)
        db.commit()
    return results
