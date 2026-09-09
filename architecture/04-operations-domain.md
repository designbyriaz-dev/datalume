# 04 — Operations Domain: Repairs, Compliance, Hazards, Stock Condition

Covers spec items 44–57 (minus the intelligence-layer items covered in
06): Repairs Model, Repeat Repair Algorithm, Component Failure Algorithm,
Compliance Framework, Domains, Requirements, Applicability, Inspections,
Evidence, Actions, Hazards, Damp & Mould, Compliance Status, Assurance
Methodology.

## 1. Repairs

```sql
repairs(id, organisation_id, repair_reference, property_id, component_id NULL,
        category, description, priority, reported_date, contractor_id NULL,
        completed_date NULL, cost NULL, status, is_emergency, ...ProvenanceMixin)
```

## 2. Repeat repair / component failure engine — deterministic, not AI

Two independent, separately testable rule functions (spec §44: "do not
let the LLM invent calculations"):

```python
def repeat_repairs_for_property(property_id: UUID, window_months: int = 12,
                                 threshold: int = 3) -> RepeatRepairSignal | None:
    """N+ repairs on the same property within window, regardless of category —
    flags a property-level pattern (e.g. persistent damp-adjacent repairs)."""

def repeat_failures_for_component(component_id: UUID, window_months: int = 18,
                                   threshold: int = 3) -> RepeatFailureSignal | None:
    """N+ repair interventions against the same component — e.g. spec example
    'Component BOI-00428 has received 6 repair interventions within 18 months'."""

def component_model_trend(component_type_id: UUID, manufacturer: str, model: str,
                           threshold_ratio: float = 0.15) -> ModelTrendSignal | None:
    """Cross-property: what % of installed units of this exact model have had a
    failure — spec example '17 boilers of Model X have experienced similar
    failures'. Requires a minimum installed-base size to avoid false positives
    on small samples (configurable floor, default 10 installed units)."""
```

`window_months` and `threshold` are per-organisation configurable
(`repair_rule_config`), thresholds are never hard-coded constants buried
in the function body — they are queried at call time so a housing
provider can tune sensitivity without a code change.

Every signal produced stores its inputs (`repair_ids`, `window`,
`threshold`) so Explainability (06) can answer "what records support
this" without recomputation drift.

## 3. Compliance framework — configurable, not 21 hard-coded tables

```sql
compliance_frameworks(id, organisation_id NULL, name, version)   -- org NULL = DataLume default
compliance_domains(id, framework_id, code, name, description)
compliance_requirements(id, domain_id, code, title, description,
                         cadence,            -- e.g. "annual", "5-yearly"
                         effective_date, superseded_date, version)
requirement_applicability(id, requirement_id, entity_type, entity_id,
                           applicable_from, applicable_to NULL, basis)
inspections(id, organisation_id, requirement_id, entity_type, entity_id,
            inspector, inspection_date, result, next_due_date,
            evidence_document_id NULL, ...ProvenanceMixin)
compliance_actions(id, organisation_id, inspection_id NULL, requirement_id,
                    entity_type, entity_id, description, deadline,
                    status, completed_date NULL, evidence_document_id NULL,
                    ...ProvenanceMixin)
```

**Decision:** the "21 domains" (spec §45: Gas Safety, Electrical Safety,
Fire Safety, Asbestos, Water Hygiene/Legionella, Lift Safety, Smoke &
CO Alarms, Damp & Mould, Building Safety, HHSRS/Hazards, Decent Homes,
Stock Condition, Repairs & Maintenance Safety, Emergency Response, EPC,
Accessibility, Structural Safety, Communal Area Safety, Contractor
Evidence, Statutory Inspection Tracking, Safety Data Assurance) are
seeded rows in `compliance_domains` under a DataLume default
`compliance_frameworks` row, not an enum and not 21 separate tables.
**Rationale:** spec explicitly: "these are configurable domains, NOT a
claim of exactly 21 universal laws" and "do not create isolated
hard-coded compliance tables" (§46). One generic
framework→domain→requirement→applicability chain, seeded with the
default 21, lets an org add/rename a domain (e.g. a commercial landlord
adding an "EICR — commercial units" nuance) without a migration.
**Future impact:** a second framework version (e.g. updated regulatory
guidance) is a new `compliance_frameworks` row with its own versioned
requirements — old assessments stay linked to the requirement version
they were assessed against (spec §31: "do not hard-code permanent
interpretations of evolving Building Regulations").

## 4. Compliance status engine

Deterministic status per `(entity, requirement)`, computed — never
LLM-set (spec §47):

```python
def compliance_status(entity_id: UUID, requirement_id: UUID) -> ComplianceStatus:
    latest = latest_inspection(entity_id, requirement_id)
    open_action = open_action_exists(entity_id, requirement_id)
    if not applicable(entity_id, requirement_id): return NOT_APPLICABLE
    if latest is None: return UNKNOWN if never_assessed else MISSING_EVIDENCE
    if open_action and action_overdue(open_action): return OVERDUE_ACTION
    if open_action: return OPEN_ACTION
    days_to_due = (latest.next_due_date - today()).days
    if days_to_due < 0: return OVERDUE if hard_deadline else EXPIRED
    if days_to_due <= org_due_soon_threshold(): return DUE_SOON
    if requires_review(latest): return NEEDS_REVIEW
    return CURRENT
```

The AI layer (Ask DataLume, Attention Engine) only ever *reads*
`compliance_status` values already computed and stored — it explains and
summarises, it never sets or infers a status itself, closing the "AI may
explain results but never invent status" requirement (spec §47) at the
architecture level (there is no write path from `intelligence/` into
`compliance_actions.status` or any status enum).

## 5. Hazards, damp & mould

```sql
hazards(id, organisation_id, property_id, hazard_type, reported_date,
        severity, investigation_status, findings, deadline NULL,
        status, ...ProvenanceMixin)
hazard_actions(id, hazard_id, description, deadline, status,
               completed_date NULL, evidence_document_id NULL)
```

Damp & mould is modelled as a `hazard_type` on the same table (not a
parallel schema) so it participates in the same
`REPORTED → TRIAGE → INVESTIGATION → DEADLINE → FINDING → ACTION →
DEADLINE → COMPLETION → EVIDENCE → FOLLOW-UP → CLOSED` state machine
(spec §49) and the same repeat-occurrence detection reused from §2's
repeat-signal pattern (same property, same `hazard_type`, within a
configurable window).

Deadlines (`hazard_actions.deadline`) are computed from
`compliance_requirements.cadence`/rule config, never a literal hard-coded
number of days in Python — spec §49: "do not permanently hard-code
evolving legal deadlines."

## 6. Stock condition & assurance methodology

`stock_condition_surveys(id, organisation_id, property_id, survey_date,
surveyor, condition_ratings JSONB, next_survey_due, document_id NULL)`
feeds both Data Health (missing/stale surveys) and Planned Investment
(03 §6) as one more input signal, not a separate scoring system.

**Assurance methodology** (spec item 57): the Board Assurance report
(06) is a read-only rollup of `compliance_status` counts + open/overdue
`compliance_actions` + hazard status, grouped by domain and
property/portfolio — assurance is a *view* over the deterministic status
engine, giving the same "never invent, only explain" guarantee at
executive-reporting altitude that §4 gives at the individual-check level.
