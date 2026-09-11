"""Cross-Domain Attention Engine — rule config and signal CRUD. See
models.py for why AttentionRule is always org-scoped (no NULL/global
row) and rules.py for the actual rule-composition functions."""

import uuid
from datetime import datetime, timezone

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.attention.models import AttentionRule, AttentionSeverity, AttentionSignal, SignalStatus


class AttentionNotFoundError(ValueError):
    """A given rule_id/signal_id doesn't exist in this organisation —
    the router maps this to a 404."""


class UnknownRuleCodeError(ValueError):
    """A rule_code isn't in RULE_REGISTRY — the router maps this to a
    404."""


def get_or_create_rule(
    db: Session, organisation_id: uuid.UUID, code: str, *, name: str, domain_scope: str, default_definition: dict, default_severity: AttentionSeverity
) -> AttentionRule:
    rule = (
        db.query(AttentionRule)
        .filter(AttentionRule.organisation_id == organisation_id, AttentionRule.code == code)
        .with_for_update()
        .first()
    )
    if rule is not None:
        return rule
    rule = AttentionRule(
        organisation_id=organisation_id,
        code=code,
        name=name,
        domain_scope=domain_scope,
        rule_definition=default_definition,
        severity_default=default_severity,
        is_active=True,
    )
    db.add(rule)
    db.flush()
    return rule


def list_rules(db: Session, organisation_id: uuid.UUID) -> list[AttentionRule]:
    from app.attention.rules import RULE_REGISTRY

    for code, definition in RULE_REGISTRY.items():
        get_or_create_rule(
            db,
            organisation_id,
            code,
            name=definition.name,
            domain_scope=definition.domain_scope,
            default_definition=definition.default_config,
            default_severity=definition.default_severity,
        )
    return db.query(AttentionRule).filter(AttentionRule.organisation_id == organisation_id).order_by(AttentionRule.code).all()


def _get_org_rule(db: Session, organisation_id: uuid.UUID, rule_id: uuid.UUID) -> AttentionRule:
    rule = db.query(AttentionRule).filter(AttentionRule.id == rule_id, AttentionRule.organisation_id == organisation_id).first()
    if rule is None:
        raise AttentionNotFoundError(f"Attention rule {rule_id} not found")
    return rule


def update_rule(
    db: Session, organisation_id: uuid.UUID, rule_id: uuid.UUID, *, is_active: bool | None, rule_definition: dict | None
) -> AttentionRule:
    rule = _get_org_rule(db, organisation_id, rule_id)
    if is_active is not None:
        rule.is_active = is_active
    if rule_definition is not None:
        rule.rule_definition = rule_definition
    db.flush()
    return rule


def list_signals(
    db: Session,
    organisation_id: uuid.UUID,
    *,
    status: str | None = None,
    entity_type: str | None = None,
    severity: str | None = None,
) -> list[AttentionSignal]:
    query = db.query(AttentionSignal).filter(AttentionSignal.organisation_id == organisation_id)
    if status is not None:
        query = query.filter(AttentionSignal.status == SignalStatus(status))
    if entity_type is not None:
        query = query.filter(AttentionSignal.entity_type == entity_type)
    if severity is not None:
        query = query.filter(AttentionSignal.severity == AttentionSeverity(severity))
    return query.order_by(AttentionSignal.detected_at.desc()).all()


def _get_org_signal(db: Session, organisation_id: uuid.UUID, signal_id: uuid.UUID) -> AttentionSignal:
    signal = (
        db.query(AttentionSignal).filter(AttentionSignal.id == signal_id, AttentionSignal.organisation_id == organisation_id).first()
    )
    if signal is None:
        raise AttentionNotFoundError(f"Attention signal {signal_id} not found")
    return signal


def update_signal_status(db: Session, organisation_id: uuid.UUID, signal_id: uuid.UUID, *, new_status: str) -> AttentionSignal:
    signal = _get_org_signal(db, organisation_id, signal_id)
    signal.status = SignalStatus(new_status)
    db.flush()
    return signal


def _select_live_signal(
    db: Session, organisation_id: uuid.UUID, rule_id: uuid.UUID, entity_type: str, entity_id: str
) -> AttentionSignal | None:
    return (
        db.query(AttentionSignal)
        .filter(
            AttentionSignal.organisation_id == organisation_id,
            AttentionSignal.rule_id == rule_id,
            AttentionSignal.entity_type == entity_type,
            AttentionSignal.entity_id == entity_id,
            AttentionSignal.status.in_((SignalStatus.OPEN, SignalStatus.ACKNOWLEDGED)),
        )
        .first()
    )


def upsert_signal(
    db: Session,
    organisation_id: uuid.UUID,
    rule: AttentionRule,
    *,
    entity_type: str,
    entity_id: str,
    severity: AttentionSeverity,
    explanation: dict,
) -> tuple[AttentionSignal, bool]:
    """Returns (signal, created). See AttentionSignal's own docstring
    for the upsert semantics."""
    still_open = _select_live_signal(db, organisation_id, rule.id, entity_type, entity_id)
    if still_open is not None:
        still_open.explanation = explanation
        still_open.severity = severity
        still_open.detected_at = datetime.now(timezone.utc)
        db.flush()
        return still_open, False

    # A DISMISSED signal for this exact (rule, entity) is a human's
    # explicit "don't flag this again" — respected by not creating a
    # new row. A RESOLVED one is *not* suppressed: the rule firing
    # again after resolution is a genuine new occurrence, so it falls
    # through to the create below, same as if nothing had ever fired.
    dismissed = (
        db.query(AttentionSignal)
        .filter(
            AttentionSignal.organisation_id == organisation_id,
            AttentionSignal.rule_id == rule.id,
            AttentionSignal.entity_type == entity_type,
            AttentionSignal.entity_id == entity_id,
            AttentionSignal.status == SignalStatus.DISMISSED,
        )
        .first()
    )
    if dismissed is not None:
        return dismissed, False

    try:
        with db.begin_nested():
            signal = AttentionSignal(
                organisation_id=organisation_id,
                rule_id=rule.id,
                entity_type=entity_type,
                entity_id=entity_id,
                severity=severity,
                explanation=explanation,
                status=SignalStatus.OPEN,
            )
            db.add(signal)
            db.flush()
    except IntegrityError:
        # Another scan (the nightly job, or a second concurrent manual
        # trigger) won the race and already inserted the live row for
        # this exact (rule, entity) between our SELECT above and this
        # insert — the partial unique index in AttentionSignal.
        # __table_args__ is what actually catches this. Recover by
        # reading the winner's row rather than surfacing the error.
        winner = _select_live_signal(db, organisation_id, rule.id, entity_type, entity_id)
        if winner is None:
            raise
        return winner, False
    return signal, True
