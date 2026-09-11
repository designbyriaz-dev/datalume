"""Cross-Domain Attention Engine — architecture/06-intelligence-layer.md
§3, spec §55. Each rule composes existing deterministic signals from
other domains (Warranty/Defect from Sprint 11, the repeat-repair engine
from Sprint 14, compliance_status from Sprint 17, arrears from Sprint
20) — it never restates their logic, only joins/thresholds over what
those domains already compute. See rules.py for the actual rule
functions and RULE_REGISTRY.

**Deliberate deviation from the SQL sketch**: architecture's own
sketch allows `attention_rules.organisation_id NULL` for a shared
global catalog, mirroring ComponentType/ComplianceDomain. This build
doesn't implement that: the four rule *types* here are fixed Python
functions (rules.py), not data-defined logic a generic interpreter
evaluates — there's no rule-authoring DSL, so there's nothing for an
org to browse/copy from a shared catalog the way there is with
component types or compliance domains. What genuinely varies per org
is configurability (is_active, rule_definition's threshold/window
values), which is exactly RepairRuleConfig/PlannedInvestmentWeight/
ComplianceStatusConfig's own shape: one row per (org, rule code),
lazily seeded, no NULL row. Building a real rule-authoring catalog
without also building the interpreter to evaluate arbitrary
`rule_definition` JSON would be misleading — a config field nobody's
code reads.

**This is genuinely the sprint that introduces this codebase's first
scheduled background job** (app/worker/jobs/attention_scan.py,
app/worker/main.py) — every "computed at read time, no job yet" note
in Sprints 17/18 pointed here. Data Health/Handover Readiness/
Planned Investment/compliance_status stay exactly as they were
(computed at read time, still no stored, potentially-stale value) —
only Attention Signals get a nightly-recomputed, upserted table,
because *this* is the one engine architecture explicitly specifies
that way: "so Home and Alerts read pre-computed signals — never
scanning the whole dataset on page load."
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Index, JSON, String, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class AttentionSeverity(str, enum.Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class SignalStatus(str, enum.Enum):
    OPEN = "OPEN"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    RESOLVED = "RESOLVED"
    DISMISSED = "DISMISSED"


class AttentionRule(Base):
    """One row per (organisation, rule code) — see this module's own
    docstring for why there's no NULL/global row. `rule_definition` is
    the rule's own configurable parameters (e.g. {"expiry_within_days":
    30}), never the rule's actual computation logic, which always lives
    in rules.py's Python code."""

    __tablename__ = "attention_rules"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organisation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.id"))
    code: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(255))
    domain_scope: Mapped[str] = mapped_column(String(255))
    rule_definition: Mapped[dict] = mapped_column(JSON, default=dict)
    severity_default: Mapped[AttentionSeverity] = mapped_column(Enum(AttentionSeverity))
    is_active: Mapped[bool] = mapped_column(default=True)


class AttentionSignal(Base):
    """architecture §3's own SQL sketch. `explanation` always stores
    {what, why, supporting_record_ids, recommended_investigation} —
    spec §55's four questions every signal must answer, stored as data
    so the UI renders every signal type uniformly rather than each
    needing bespoke copy. Upserted by attention_scan.py: a rule that
    fires again for the same (rule, entity) while an existing signal is
    still OPEN/ACKNOWLEDGED refreshes that row in place rather than
    creating a duplicate; a DISMISSED signal is never silently
    recreated (the human's dismissal is respected); a RESOLVED signal
    firing again gets a fresh row, since that's a genuine new
    occurrence, not a duplicate of the resolved one."""

    __tablename__ = "attention_signals"
    __table_args__ = (
        # At most one *live* signal per (org, rule, entity) at a time —
        # a scan can never produce two OPEN/ACKNOWLEDGED rows for the
        # same thing, even if it races another scan (the nightly job,
        # or a concurrent manual trigger — see app/attention/service.py
        # upsert_signal's IntegrityError recovery). Partial, not a plain
        # unique constraint: unlimited RESOLVED/DISMISSED history rows
        # for the same (org, rule, entity) are legitimate — only the
        # "currently live" state must be unique.
        Index(
            "uq_attention_signal_live_per_entity",
            "organisation_id",
            "rule_id",
            "entity_type",
            "entity_id",
            unique=True,
            sqlite_where=text("status IN ('OPEN', 'ACKNOWLEDGED')"),
            postgresql_where=text("status IN ('OPEN', 'ACKNOWLEDGED')"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organisation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.id"))
    rule_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("attention_rules.id"))
    entity_type: Mapped[str] = mapped_column(String(64))
    entity_id: Mapped[str] = mapped_column(String(64))
    severity: Mapped[AttentionSeverity] = mapped_column(Enum(AttentionSeverity))
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    explanation: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[SignalStatus] = mapped_column(Enum(SignalStatus), default=SignalStatus.OPEN)
