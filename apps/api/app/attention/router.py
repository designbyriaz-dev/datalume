"""Cross-Domain Attention Engine — architecture/06-intelligence-layer.md
§3. Rule/signal viewing and signal triage (acknowledge/resolve/dismiss)
are gated by `reports.read` — broadly held across every domain manager
role, since attention signals are inherently cross-domain and belong
to the same "insights" surface as reporting. Reshaping which rules run
(toggling `is_active`, editing `rule_definition`) and manually forcing
a rescan are gated by `reports.board` — an org-wide decision about how
the whole insights feed is computed, the same executive-level gate
Board Assurance (Sprint 17) uses."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.attention.models import AttentionRule, AttentionSignal
from app.attention.schemas import (
    AttentionRuleOut,
    AttentionScanResultOut,
    AttentionSignalOut,
    UpdateAttentionRuleRequest,
    UpdateSignalStatusRequest,
)
from app.attention.service import AttentionNotFoundError, list_rules, list_signals, update_rule, update_signal_status
from app.core.db import get_db
from app.core.tenancy import AuthContext, get_auth_context, require_permission
from app.worker.jobs.attention_scan import run_attention_scan

router = APIRouter(prefix="/api/v1/attention", tags=["attention"])


def _signal_to_out(db: Session, organisation_id: uuid.UUID, signal: AttentionSignal) -> AttentionSignalOut:
    rule = db.query(AttentionRule).filter(AttentionRule.id == signal.rule_id, AttentionRule.organisation_id == organisation_id).first()
    return AttentionSignalOut(
        id=signal.id,
        rule_id=signal.rule_id,
        rule_code=rule.code if rule else "UNKNOWN",
        entity_type=signal.entity_type,
        entity_id=signal.entity_id,
        severity=signal.severity.value,
        detected_at=signal.detected_at,
        explanation=signal.explanation,
        status=signal.status.value,
    )


@router.get("/rules", response_model=list[AttentionRuleOut])
def get_rules(
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    if ctx.organisation_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "X-Organisation-Id header is required")
    rules = list_rules(db, ctx.organisation_id)
    db.commit()
    return rules


@router.patch("/rules/{rule_id}", response_model=AttentionRuleOut)
def update_rule_endpoint(
    rule_id: uuid.UUID,
    payload: UpdateAttentionRuleRequest,
    ctx: AuthContext = Depends(require_permission("reports.board")),
    db: Session = Depends(get_db),
):
    try:
        rule = update_rule(db, ctx.organisation_id, rule_id, is_active=payload.is_active, rule_definition=payload.rule_definition)
    except AttentionNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    db.commit()
    db.refresh(rule)
    return rule


@router.get("/signals", response_model=list[AttentionSignalOut])
def get_signals(
    signal_status: str | None = None,
    entity_type: str | None = None,
    severity: str | None = None,
    ctx: AuthContext = Depends(require_permission("reports.read")),
    db: Session = Depends(get_db),
):
    signals = list_signals(db, ctx.organisation_id, status=signal_status, entity_type=entity_type, severity=severity)
    return [_signal_to_out(db, ctx.organisation_id, s) for s in signals]


@router.post("/signals/{signal_id}/status", response_model=AttentionSignalOut)
def update_signal_status_endpoint(
    signal_id: uuid.UUID,
    payload: UpdateSignalStatusRequest,
    ctx: AuthContext = Depends(require_permission("reports.read")),
    db: Session = Depends(get_db),
):
    try:
        signal = update_signal_status(db, ctx.organisation_id, signal_id, new_status=payload.status)
    except AttentionNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    db.commit()
    db.refresh(signal)
    return _signal_to_out(db, ctx.organisation_id, signal)


@router.post("/scan", response_model=AttentionScanResultOut)
def trigger_scan(
    ctx: AuthContext = Depends(require_permission("reports.board")),
    db: Session = Depends(get_db),
):
    """Manually forces this organisation's scan — the nightly worker
    job (app/worker/jobs/attention_scan.py) runs this same function
    automatically, but a demo/pilot org shouldn't have to wait for
    actual nightfall to see the engine work."""
    result = run_attention_scan(db, ctx.organisation_id)
    db.commit()
    return AttentionScanResultOut(
        rules_evaluated=result.rules_evaluated, signals_created=result.signals_created, signals_refreshed=result.signals_refreshed
    )
