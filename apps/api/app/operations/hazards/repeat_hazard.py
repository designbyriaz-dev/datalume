"""Repeat hazard-occurrence detection — architecture/04-operations-domain.md
§5: "the same repeat-occurrence detection reused from §2's repeat-signal
pattern (same property, same hazard_type, within a configurable
window)." One function, mirroring
app/operations/repeat_repair.repeat_repairs_for_property exactly except
scoped additionally by hazard_type — a repeat *pattern* is about the
same kind of hazard recurring at the same property (e.g. damp and mould
coming back), not any two unrelated hazards happening to share a
property.

window_months/threshold come from HazardRuleConfig (per-organisation,
lazily seeded from RULE_DEFAULTS below), never hard-coded — same
"deterministic, computed at read time, config not code" approach as
Sprint 14's repeat-repair engine.
"""

import uuid
from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.operations.hazards.models import Hazard
from app.operations.hazards.schemas import RepeatHazardSignalOut

REPEAT_HAZARDS_PER_PROPERTY = "REPEAT_HAZARDS_PER_PROPERTY"

RULE_DEFAULTS: dict[str, dict] = {
    REPEAT_HAZARDS_PER_PROPERTY: {"window_months": 24, "threshold": 2},
}


def _rule_config(db: Session, organisation_id: uuid.UUID, rule_code: str):
    from app.operations.hazards.service import get_or_create_hazard_rule_config

    return get_or_create_hazard_rule_config(db, organisation_id, rule_code, RULE_DEFAULTS[rule_code])


def repeat_hazards_for_property(
    db: Session, organisation_id: uuid.UUID, property_id: uuid.UUID, hazard_type: str
) -> RepeatHazardSignalOut | None:
    """N+ hazards of the same type on the same property within window —
    e.g. damp and mould reported, closed, then reported again at the
    same property. Unlike repeat_repairs_for_property, no status is
    excluded here: a CLOSED hazard is still a genuine past occurrence
    that counts toward recurrence (there's no CANCELLED-equivalent
    "this never actually happened" status on Hazard)."""
    config = _rule_config(db, organisation_id, REPEAT_HAZARDS_PER_PROPERTY)
    window_months, threshold = config.window_months, config.threshold
    cutoff = date.today() - timedelta(days=round(window_months * 30.44))

    hazards = (
        db.query(Hazard)
        .filter(
            Hazard.organisation_id == organisation_id,
            Hazard.property_id == property_id,
            Hazard.hazard_type == hazard_type,
            Hazard.reported_date >= cutoff,
        )
        .all()
    )
    if len(hazards) < threshold:
        return None
    return RepeatHazardSignalOut(
        property_id=property_id,
        hazard_type=hazard_type,
        hazard_count=len(hazards),
        window_months=window_months,
        threshold=threshold,
        hazard_ids=[h.id for h in hazards],
    )
