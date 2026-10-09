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

Sprint 5 only had Property to check against; component and handover
checks landed Post-Sprint-24, once those domain models existed.
Serial numbers/installation dates/conflicting references/invalid
dates/duplicate documents closed Post-Sprint-24 too (see those
functions' own docstrings). Missing warranties and missing external
references beyond UPRN closed in a later session still — see
check_missing_warranty_for_expected_component_type and
check_missing_bsr_reference_for_higher_risk_buildings's own docstrings
for how each one avoids being the "noisy blanket rule" earlier
versions of this docstring worried about, by scoping to a real,
specific subset rather than every row.

Missing evidence closed too, in a later session still: the earlier
claim here ("no document is currently linked to a specific compliance
requirement in a way 'missing evidence' could query") turned out to be
wrong, not just incomplete — app.operations.compliance.models.py's own
module docstring names EVIDENCE as the explicit link between
INSPECTION and ACTION in the compliance chain, and both `Inspection`
and `ComplianceAction` have carried a real `evidence_document_id`
column since Sprint 16, simply never queried this way before. See
check_missing_inspection_evidence and check_missing_completed_action_
evidence's own docstrings.

Still genuinely open, and still deliberately not implemented: missing
component types (Component.component_type_id is NOT NULL at the
schema level — no row can ever fail this, so there's nothing to
query), missing specifications (unlike warranties, there's no
defensible per-component-type "this type always needs one" list —
whether a specification document exists is project- and context-
specific in a way a fixed type list can't capture), and missing
building relationships (architecture 03's own design, and spec §19
explicitly, say not every hierarchy level is required — a property or
component with no building link is a deliberate, valid shape, not a
data problem, so this one isn't "not yet done", it's correctly out of
scope permanently).

Each check below queries narrow column projections (just the id/
reference and whatever the rule itself needs) or real SQL
GROUP BY/COUNT/window-function aggregation, rather than loading every
full Property/Component/Document row into Python — found and fixed by
the same load-testing pass documented in STATUS.md that fixed Repairs/
Defects Intelligence and the Board Assurance report. The one exception
is check_duplicate_properties' address-normalisation: collapsing
*internal* whitespace runs (not just leading/trailing) has no portable
SQL expression across SQLite (this codebase's test dialect) and
Postgres without a regex function SQLite doesn't have built in, so
that one check still normalises in Python — fed by a narrow
(id, reference, address) projection, not full Property rows.
"""

from collections import Counter
from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import func, insert
from sqlalchemy.orm import Session

from app.data_health.models import DataHealthFinding, FindingSeverity
from app.development.models import (
    Building,
    Component,
    ComponentType,
    HandoverRecord,
    Property,
    PropertyStatus,
    Warranty,
    WarrantyStatus,
)
from app.documents.models import Document, DocumentStatus
from app.identifiers.models import ExternalReference, ExternalReferenceType
from app.operations.compliance.models import ComplianceAction, ComplianceActionStatus, Inspection
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
    filters = [Property.organisation_id == organisation_id]
    applicable_count = db.query(Property).filter(*filters).count()
    missing = (
        db.query(Property.id, Property.property_reference)
        .filter(*filters, (Property.property_type.is_(None)) | (Property.property_type == ""))
        .all()
    )
    findings = [
        Finding("MISSING_PROPERTY_TYPE", FindingSeverity.MEDIUM, "property", str(pid), f"{pref} has no property type recorded.")
        for pid, pref in missing
    ]
    return CheckResult("MISSING_PROPERTY_TYPE", applicable_count, len(findings), findings)


def check_missing_uprn(db: Session, organisation_id) -> CheckResult:
    # UPRN moved off Property onto app.identifiers.models.ExternalReference
    # in Sprint 7 — see that module's docstring for why. One bulk lookup
    # of just the UPRN-bearing property ids, not a full ExternalReference
    # row per property.
    property_rows = db.query(Property.id, Property.property_reference).filter(Property.organisation_id == organisation_id).all()
    uprn_property_ids = {
        row[0]
        for row in db.query(ExternalReference.entity_id).filter(
            ExternalReference.organisation_id == organisation_id,
            ExternalReference.entity_type == "property",
            ExternalReference.reference_type == ExternalReferenceType.UPRN,
        )
    }
    findings = [
        Finding("MISSING_UPRN", FindingSeverity.LOW, "property", str(pid), f"{pref} has no UPRN recorded.")
        for pid, pref in property_rows
        if str(pid) not in uprn_property_ids
    ]
    return CheckResult("MISSING_UPRN", len(property_rows), len(findings), findings)


def check_missing_postcode(db: Session, organisation_id) -> CheckResult:
    filters = [Property.organisation_id == organisation_id]
    applicable_count = db.query(Property).filter(*filters).count()
    missing = (
        db.query(Property.id, Property.property_reference)
        .filter(*filters, (Property.postcode.is_(None)) | (Property.postcode == ""))
        .all()
    )
    findings = [
        Finding("MISSING_POSTCODE", FindingSeverity.LOW, "property", str(pid), f"{pref} has no postcode recorded.")
        for pid, pref in missing
    ]
    return CheckResult("MISSING_POSTCODE", applicable_count, len(findings), findings)


def _normalize_address(address: str) -> str:
    return " ".join(address.lower().split())


def check_duplicate_properties(db: Session, organisation_id) -> CheckResult:
    property_rows = (
        db.query(Property.id, Property.property_reference, Property.address)
        .filter(Property.organisation_id == organisation_id)
        .all()
    )
    counts = Counter(_normalize_address(address) for _, _, address in property_rows)
    findings = [
        Finding(
            "DUPLICATE_PROPERTIES",
            FindingSeverity.HIGH,
            "property",
            str(pid),
            f"{pref}'s address matches {counts[_normalize_address(address)] - 1} "
            "other propert(y/ies) in this organisation.",
        )
        for pid, pref, address in property_rows
        if counts[_normalize_address(address)] > 1
    ]
    return CheckResult("DUPLICATE_PROPERTIES", len(property_rows), len(findings), findings)


def check_missing_stock_condition_survey(db: Session, organisation_id) -> CheckResult:
    """architecture/04-operations-domain.md §6: a stock condition
    survey "feeds... Data Health (missing/stale surveys)" — Sprint 18's
    own instruction, closed here."""
    property_rows = db.query(Property.id, Property.property_reference).filter(Property.organisation_id == organisation_id).all()
    surveyed_property_ids = {
        row[0]
        for row in db.query(StockConditionSurvey.property_id)
        .filter(StockConditionSurvey.organisation_id == organisation_id)
        .distinct()
    }
    findings = [
        Finding("MISSING_STOCK_CONDITION_SURVEY", FindingSeverity.MEDIUM, "property", str(pid), f"{pref} has no stock condition survey recorded.")
        for pid, pref in property_rows
        if pid not in surveyed_property_ids
    ]
    return CheckResult("MISSING_STOCK_CONDITION_SURVEY", len(property_rows), len(findings), findings)


def check_stale_stock_condition_survey(db: Session, organisation_id) -> CheckResult:
    """Applies only to properties with at least one survey on record —
    a property with none is check_missing_stock_condition_survey's
    concern, not this one's, so it isn't double-counted as failing two
    checks for the same underlying gap. "Latest survey per property" is
    a window function rather than "fetch every survey, pick the newest
    in Python" — both SQLite and Postgres support ROW_NUMBER() OVER(...)
    identically, so this one has no portability concern."""
    latest_survey = (
        db.query(
            StockConditionSurvey.property_id.label("property_id"),
            StockConditionSurvey.next_survey_due.label("next_survey_due"),
            func.row_number()
            .over(partition_by=StockConditionSurvey.property_id, order_by=StockConditionSurvey.survey_date.desc())
            .label("rn"),
        )
        .filter(StockConditionSurvey.organisation_id == organisation_id)
        .subquery()
    )
    latest_rows = (
        db.query(Property.id, Property.property_reference, latest_survey.c.next_survey_due)
        .join(latest_survey, latest_survey.c.property_id == Property.id)
        .filter(Property.organisation_id == organisation_id, latest_survey.c.rn == 1)
        .all()
    )
    today = date.today()
    findings = [
        Finding("STALE_STOCK_CONDITION_SURVEY", FindingSeverity.MEDIUM, "property", str(pid), f"{pref}'s stock condition survey was due {due}.")
        for pid, pref, due in latest_rows
        if due is not None and due < today
    ]
    return CheckResult("STALE_STOCK_CONDITION_SURVEY", len(latest_rows), len(findings), findings)


def check_orphan_components(db: Session, organisation_id) -> CheckResult:
    """spec §42's "Orphan components". Component can attach to any
    combination of development/building/property/space (models.py's own
    docstring — a lift might belong to a building with no specific
    property) plus an optional parent_component_id for the sub-component
    hierarchy — a row with *all five* unset isn't "loosely scoped",
    it's disconnected from the property hierarchy entirely, which spec
    §24's whole point (every asset traceable to where it physically is)
    depends on."""
    filters = [Component.organisation_id == organisation_id]
    applicable_count = db.query(Component).filter(*filters).count()
    orphan_condition = (
        Component.development_id.is_(None)
        & Component.building_id.is_(None)
        & Component.property_id.is_(None)
        & Component.space_id.is_(None)
        & Component.parent_component_id.is_(None)
    )
    orphans = db.query(Component.id, Component.component_reference).filter(*filters, orphan_condition).all()
    findings = [
        Finding(
            "ORPHAN_COMPONENT",
            FindingSeverity.HIGH,
            "component",
            str(cid),
            f"{cref} has no development, building, property, space, or parent "
            "component linked — it isn't traceable to anywhere in the portfolio.",
        )
        for cid, cref in orphans
    ]
    return CheckResult("ORPHAN_COMPONENT", applicable_count, len(findings), findings)


def check_duplicate_components(db: Session, organisation_id) -> CheckResult:
    """Same "identical key seen more than once" shape as
    check_duplicate_properties above, but the key is location + type +
    make/model rather than an address — two components at the exact
    same place, of the exact same type and manufacturer/model, are a
    near-certain accidental double-entry (a real duplicate boiler two
    rows apart), not two genuinely different assets that happen to
    match. Unlike the address check, LOWER/TRIM/COALESCE are portable
    SQL functions (no internal-whitespace-collapse needed here), so
    this key is computed in SQL, not Python."""
    rows = (
        db.query(
            Component.id,
            Component.component_reference,
            Component.component_type_id,
            Component.development_id,
            Component.building_id,
            Component.property_id,
            Component.space_id,
            func.lower(func.trim(func.coalesce(Component.manufacturer, ""))).label("manufacturer_key"),
            func.lower(func.trim(func.coalesce(Component.model, ""))).label("model_key"),
        )
        .filter(Component.organisation_id == organisation_id)
        .all()
    )
    counts = Counter(row[2:] for row in rows)
    findings = [
        Finding(
            "DUPLICATE_COMPONENT",
            FindingSeverity.MEDIUM,
            "component",
            str(row.id),
            f"{row.component_reference} matches {counts[row[2:]] - 1} other component(s) of the same type, "
            "make and model at the same location.",
        )
        for row in rows
        if counts[row[2:]] > 1
    ]
    return CheckResult("DUPLICATE_COMPONENT", len(rows), len(findings), findings)


def check_missing_handover_information(db: Session, organisation_id) -> CheckResult:
    """spec §42's "Missing handover information". HandoverRecord
    (development/models.py) is written in the same transaction as a
    property's READY_FOR_HANDOVER -> HANDED_OVER flip
    (development/service.py.authorise_handover) — the permanent
    evidence handover actually happened and what was known at the time.
    A property already marked HANDED_OVER with no such row means that
    evidence is missing, whatever the reason (a status set some other
    way, a migrated/imported record, ...)."""
    property_rows = (
        db.query(Property.id, Property.property_reference)
        .filter(Property.organisation_id == organisation_id, Property.status == PropertyStatus.HANDED_OVER)
        .all()
    )
    recorded_property_ids = {
        row[0]
        for row in db.query(HandoverRecord.property_id).filter(HandoverRecord.organisation_id == organisation_id).distinct()
    }
    findings = [
        Finding(
            "MISSING_HANDOVER_INFORMATION",
            FindingSeverity.HIGH,
            "property",
            str(pid),
            f"{pref} is marked HANDED_OVER but has no handover record on file.",
        )
        for pid, pref in property_rows
        if pid not in recorded_property_ids
    ]
    return CheckResult("MISSING_HANDOVER_INFORMATION", len(property_rows), len(findings), findings)


def check_missing_serial_number(db: Session, organisation_id) -> CheckResult:
    """Component.serial_number lives in ExternalReference, not on
    Component itself (see that model's own docstring for why) — same
    UPRN-shaped check as check_missing_uprn, same LOW severity for the
    same reason: a component genuinely might not carry one (still being
    commissioned, or a non-serialised item like a fire door), not
    necessarily a data problem."""
    component_rows = db.query(Component.id, Component.component_reference).filter(Component.organisation_id == organisation_id).all()
    serial_component_ids = {
        row[0]
        for row in db.query(ExternalReference.entity_id).filter(
            ExternalReference.organisation_id == organisation_id,
            ExternalReference.entity_type == "component",
            ExternalReference.reference_type == ExternalReferenceType.MANUFACTURER_SERIAL_NUMBER,
        )
    }
    findings = [
        Finding("MISSING_SERIAL_NUMBER", FindingSeverity.LOW, "component", str(cid), f"{cref} has no manufacturer serial number recorded.")
        for cid, cref in component_rows
        if str(cid) not in serial_component_ids
    ]
    return CheckResult("MISSING_SERIAL_NUMBER", len(component_rows), len(findings), findings)


def check_missing_installation_date(db: Session, organisation_id) -> CheckResult:
    """installation_date feeds indicative_replacement_date (Component's
    own docstring) — without it, spec §26's Component Lifecycle
    Intelligence has nothing to compute a replacement date from."""
    filters = [Component.organisation_id == organisation_id]
    applicable_count = db.query(Component).filter(*filters).count()
    missing = db.query(Component.id, Component.component_reference).filter(*filters, Component.installation_date.is_(None)).all()
    findings = [
        Finding("MISSING_INSTALLATION_DATE", FindingSeverity.MEDIUM, "component", str(cid), f"{cref} has no installation date recorded.")
        for cid, cref in missing
    ]
    return CheckResult("MISSING_INSTALLATION_DATE", applicable_count, len(findings), findings)


def check_invalid_installation_date(db: Session, organisation_id) -> CheckResult:
    """Applies only to components that HAVE an installation_date —
    check_missing_installation_date's concern is the absent case, this
    one's is a present-but-impossible value, so the same gap isn't
    double-counted as failing two checks, same reasoning as
    check_stale_stock_condition_survey above."""
    today = date.today()
    filters = [Component.organisation_id == organisation_id, Component.installation_date.isnot(None)]
    applicable_count = db.query(Component).filter(*filters).count()
    invalid = (
        db.query(Component.id, Component.component_reference, Component.installation_date)
        .filter(*filters, Component.installation_date > today)
        .all()
    )
    findings = [
        Finding(
            "INVALID_INSTALLATION_DATE",
            FindingSeverity.HIGH,
            "component",
            str(cid),
            f"{cref}'s installation date ({installation_date}) is in the future.",
        )
        for cid, cref, installation_date in invalid
    ]
    return CheckResult("INVALID_INSTALLATION_DATE", applicable_count, len(findings), findings)


def check_conflicting_external_references(db: Session, organisation_id) -> CheckResult:
    """ExternalReference has no uniqueness constraint on (entity_type,
    entity_id, reference_type) — a real gap, not a hypothetical one: two
    different UPRNs recorded for the same property (a correction that
    added a row instead of updating one, or two separate imports) is
    exactly the kind of silent problem get_external_references_bulk's
    dict.setdefault would otherwise mask, by quietly keeping only
    whichever row it happened to see last."""
    filters = [ExternalReference.organisation_id == organisation_id]
    key_counts = (
        db.query(
            ExternalReference.entity_type.label("entity_type"),
            ExternalReference.entity_id.label("entity_id"),
            ExternalReference.reference_type.label("reference_type"),
            func.count(func.distinct(ExternalReference.value)).label("distinct_value_count"),
        )
        .filter(*filters)
        .group_by(ExternalReference.entity_type, ExternalReference.entity_id, ExternalReference.reference_type)
        .subquery()
    )
    applicable_count = db.query(key_counts).count()
    rows = (
        db.query(
            ExternalReference.entity_type,
            ExternalReference.entity_id,
            ExternalReference.reference_type,
            key_counts.c.distinct_value_count,
        )
        .join(
            key_counts,
            (key_counts.c.entity_type == ExternalReference.entity_type)
            & (key_counts.c.entity_id == ExternalReference.entity_id)
            & (key_counts.c.reference_type == ExternalReference.reference_type),
        )
        .filter(*filters, key_counts.c.distinct_value_count > 1)
        .all()
    )
    findings = [
        Finding(
            "CONFLICTING_EXTERNAL_REFERENCE",
            FindingSeverity.HIGH,
            entity_type,
            entity_id,
            f"{entity_type} {entity_id} has {distinct_value_count} different {reference_type.value} values recorded.",
        )
        for entity_type, entity_id, reference_type, distinct_value_count in rows
    ]
    failing_count = len({(entity_type, entity_id, reference_type) for entity_type, entity_id, reference_type, _ in rows})
    return CheckResult("CONFLICTING_EXTERNAL_REFERENCE", applicable_count, failing_count, findings)


def check_duplicate_documents(db: Session, organisation_id) -> CheckResult:
    """Same content (checksum) uploaded as two separate documents
    (different lineage_id) rather than as a new revision of one — scoped
    to ACTIVE only, since a SUPERSEDED/ARCHIVED row sharing a checksum
    with its own later revision is expected version history, not a
    duplicate."""
    filters = [Document.organisation_id == organisation_id, Document.status == DocumentStatus.ACTIVE]
    applicable_count = db.query(Document).filter(*filters).count()
    checksum_counts = (
        db.query(Document.checksum.label("checksum"), func.count(func.distinct(Document.lineage_id)).label("distinct_lineage_count"))
        .filter(*filters)
        .group_by(Document.checksum)
        .subquery()
    )
    rows = (
        db.query(Document.id, Document.document_reference, checksum_counts.c.distinct_lineage_count)
        .join(checksum_counts, checksum_counts.c.checksum == Document.checksum)
        .filter(*filters, checksum_counts.c.distinct_lineage_count > 1)
        .all()
    )
    findings = [
        Finding(
            "DUPLICATE_DOCUMENT",
            FindingSeverity.MEDIUM,
            "document",
            str(did),
            f"{dref} has the same content as {distinct_lineage_count - 1} "
            "other document(s) uploaded as separate files rather than a new revision.",
        )
        for did, dref, distinct_lineage_count in rows
    ]
    return CheckResult("DUPLICATE_DOCUMENT", applicable_count, len(findings), findings)


# Component types where a manufacturer/installer warranty is standard,
# universal UK housing-association practice: mechanical, electrical,
# and fire-safety plant. Deliberately narrower than "every component
# type" — a roof, a kitchen, or a structural element might carry a
# building-level NHBC-style structural warranty, a different thing
# entirely from a per-component manufacturer warranty, and plausibly
# has no warranty record of this kind at all. This list is the real,
# scoped answer to the "blanket rule would flag components that
# shouldn't be flagged" concern this check was originally left unbuilt
# over, not a workaround of it.
TYPES_EXPECTING_WARRANTY = {
    "BOILERS",
    "HEAT_PUMPS",
    "HEATING_SYSTEMS",
    "LIFTS",
    "SMOKE_ALARMS",
    "CO_ALARMS",
    "SPRINKLERS",
    "ELECTRICAL_INSTALLATIONS",
    "CONSUMER_UNITS",
    "SOLAR_PV",
    "EV_INFRASTRUCTURE",
}


def check_missing_warranty_for_expected_component_type(db: Session, organisation_id) -> CheckResult:
    """spec §42's "Missing warranties" — scoped to
    TYPES_EXPECTING_WARRANTY above, not every component (see that
    constant's own docstring for why). Checks against the real Warranty
    register (component_id set, status ACTIVE) — the same data source
    Handover Readiness's check_warranties_received already uses
    (app/development/handover.py) — not Component.warranty_start/
    warranty_expiry, a simpler parallel pair of columns with no form
    field in the UI to actually set them."""
    rows = (
        db.query(Component.id, Component.component_reference)
        .join(ComponentType, ComponentType.id == Component.component_type_id)
        .filter(Component.organisation_id == organisation_id, ComponentType.code.in_(TYPES_EXPECTING_WARRANTY))
        .all()
    )
    warrantied_component_ids = {
        row[0]
        for row in db.query(Warranty.component_id).filter(
            Warranty.organisation_id == organisation_id,
            Warranty.component_id.isnot(None),
            Warranty.status == WarrantyStatus.ACTIVE,
        )
    }
    findings = [
        Finding(
            "MISSING_WARRANTY",
            FindingSeverity.MEDIUM,
            "component",
            str(cid),
            f"{cref} is a type that should have a warranty on file, but none is recorded.",
        )
        for cid, cref in rows
        if cid not in warrantied_component_ids
    ]
    return CheckResult("MISSING_WARRANTY", len(rows), len(findings), findings)


# The Building Safety Act 2022's higher-risk building threshold — at
# least 18 metres in height or at least 7 storeys. Buildings below this
# genuinely don't need BSR registration, so flagging every building
# without a BSR reference would be exactly the kind of noisy,
# wrong-for-most-rows rule this check was originally left unbuilt over;
# scoping to the real statutory threshold instead of guessing is what
# makes this one correct rather than just quieter.
HIGHER_RISK_BUILDING_HEIGHT_METRES = 18.0
HIGHER_RISK_BUILDING_STOREYS = 7


def check_missing_bsr_reference_for_higher_risk_buildings(db: Session, organisation_id) -> CheckResult:
    """spec §42's "Missing external references" (beyond UPRN, which
    check_missing_uprn already covers) — scoped to BSR references on
    higher-risk buildings specifically. No other external reference
    type has a real "every X should have this" rule the way UPRN and
    this one do: planning/building-control references, for instance,
    genuinely don't apply to existing stock the way they do to a
    new-build development, so there's no single threshold to check them
    against the way there is here."""
    higher_risk = (
        db.query(Building.id, Building.building_reference)
        .filter(
            Building.organisation_id == organisation_id,
            (Building.height >= HIGHER_RISK_BUILDING_HEIGHT_METRES)
            | (Building.storeys >= HIGHER_RISK_BUILDING_STOREYS),
        )
        .all()
    )
    bsr_building_ids = {
        row[0]
        for row in db.query(ExternalReference.entity_id).filter(
            ExternalReference.organisation_id == organisation_id,
            ExternalReference.entity_type == "building",
            ExternalReference.reference_type == ExternalReferenceType.BSR_REFERENCE,
        )
    }
    findings = [
        Finding(
            "MISSING_BSR_REFERENCE",
            FindingSeverity.HIGH,
            "building",
            str(bid),
            f"{bref} meets the Building Safety Act's higher-risk threshold but has no BSR reference recorded.",
        )
        for bid, bref in higher_risk
        if str(bid) not in bsr_building_ids
    ]
    return CheckResult("MISSING_BSR_REFERENCE", len(higher_risk), len(findings), findings)


def check_missing_inspection_evidence(db: Session, organisation_id) -> CheckResult:
    """spec §42's "Missing evidence". architecture/04-operations-domain.md
    §3's own chain (app/operations/compliance/models.py's module
    docstring) is "...APPLICABILITY -> ... -> INSPECTION -> EVIDENCE ->
    ACTION..." — EVIDENCE is the explicit link right after INSPECTION,
    and `Inspection.evidence_document_id` is exactly that column,
    already real since Sprint 16. Scoped to inspections that already
    exist, not to "should an inspection exist at all" — that's a
    different, already-covered signal (status_engine.py's own
    MISSING_EVIDENCE/UNKNOWN compliance statuses for an applicable
    requirement with no inspection on record at all); this check is
    about an inspection that *was* carried out and recorded, with
    nothing proving it."""
    filters = [Inspection.organisation_id == organisation_id]
    applicable_count = db.query(Inspection).filter(*filters).count()
    missing = (
        db.query(Inspection.id, Inspection.inspector, Inspection.inspection_date)
        .filter(*filters, Inspection.evidence_document_id.is_(None))
        .all()
    )
    findings = [
        Finding(
            "MISSING_INSPECTION_EVIDENCE",
            FindingSeverity.MEDIUM,
            "inspection",
            str(iid),
            f"The {inspection_date} inspection by {inspector} has no evidence document attached.",
        )
        for iid, inspector, inspection_date in missing
    ]
    return CheckResult("MISSING_INSPECTION_EVIDENCE", applicable_count, len(findings), findings)


def check_missing_completed_action_evidence(db: Session, organisation_id) -> CheckResult:
    """The same real "Missing evidence" gap as
    check_missing_inspection_evidence above, for the chain's other
    `evidence_document_id` column — `ComplianceAction`, same since
    Sprint 16. Scoped to COMPLETED actions only: an OPEN action
    genuinely has no completion evidence yet, that's expected, not a
    data problem (same "don't flag the case that's supposed to be
    empty" reasoning check_invalid_installation_date and
    check_stale_stock_condition_survey already use elsewhere in this
    file); a CANCELLED action was never carried out, so it has nothing
    to provide evidence of either."""
    filters = [
        ComplianceAction.organisation_id == organisation_id,
        ComplianceAction.status == ComplianceActionStatus.COMPLETED,
    ]
    applicable_count = db.query(ComplianceAction).filter(*filters).count()
    missing = (
        db.query(ComplianceAction.id, ComplianceAction.description, ComplianceAction.completed_date)
        .filter(*filters, ComplianceAction.evidence_document_id.is_(None))
        .all()
    )
    findings = [
        Finding(
            "MISSING_ACTION_EVIDENCE",
            FindingSeverity.MEDIUM,
            "compliance_action",
            str(aid),
            f'Completed action "{description}" has no evidence document attached.',
        )
        for aid, description, completed_date in missing
    ]
    return CheckResult("MISSING_ACTION_EVIDENCE", applicable_count, len(findings), findings)


RULES = [
    check_missing_property_type,
    check_missing_uprn,
    check_missing_postcode,
    check_duplicate_properties,
    check_missing_stock_condition_survey,
    check_stale_stock_condition_survey,
    check_orphan_components,
    check_duplicate_components,
    check_missing_handover_information,
    check_missing_serial_number,
    check_missing_installation_date,
    check_invalid_installation_date,
    check_conflicting_external_references,
    check_duplicate_documents,
    check_missing_warranty_for_expected_component_type,
    check_missing_bsr_reference_for_higher_risk_buildings,
    check_missing_inspection_evidence,
    check_missing_completed_action_evidence,
]


def run_data_health_checks(db: Session, organisation_id) -> tuple[float, list[CheckResult]]:
    results = [rule(db, organisation_id) for rule in RULES]

    db.query(DataHealthFinding).filter(DataHealthFinding.organisation_id == organisation_id).delete()
    rows = [
        {
            "organisation_id": organisation_id,
            "check_code": f.check_code,
            "severity": f.severity,
            "affected_entity_type": f.affected_entity_type,
            "affected_entity_id": f.affected_entity_id,
            "message": f.message,
        }
        for result in results
        for f in result.findings
    ]
    if rows:
        db.execute(insert(DataHealthFinding), rows)
    db.flush()

    score = sum(r.pass_ratio for r in results) / len(results) * 100 if results else 100.0
    return round(score, 1), results
