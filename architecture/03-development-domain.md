# 03 — Development & New-Build Domain

Covers spec items 20–43: Development, Building, Hierarchy, Planned
Property, Space, Component Model & Taxonomy, Identifier Engine, Reference
Pattern Configuration, External Identifier Model, Specification Model,
Document Versioning (see 02 §4), Golden Thread, Building Control Record,
Regulatory Mapping, Construction Evidence, Change Control, Defects,
Warranties, Handover, Handover Readiness Formula, Development→Operational
transition, Component Lifecycle, Planned Investment Logic.

## 1. Hierarchy

```
Development → Building/Block → Core/Entrance → Floor → Property/Unit → Space/Communal Area → Component
```

Every level is optional except `Development` and `Property` — a tenant
that doesn't use "cores" or tracks components at property-level only is
fully supported (spec §19: "do not require every customer to use every
hierarchy level"). Modelled as a nullable-parent chain, not a fixed-depth
tree:

```sql
developments(id, organisation_id, development_reference, name, description,
             address, postcode, region, developer, principal_designer,
             principal_contractor, employer_agent,
             number_of_planned_properties, planned_start_date,
             planned_completion_date, actual_completion_date, status,
             planning_reference, building_control_reference, bsr_reference,
             source, ...ProvenanceMixin)
buildings(id, organisation_id, development_id NULL, building_reference, name,
          building_type, address, height, storeys, construction_type,
          planned_completion, actual_completion,
          building_control_reference, bsr_reference, status, ...ProvenanceMixin)
floors(id, organisation_id, building_id, name, level_index, ...)
properties(id, organisation_id, development_id NULL, building_id NULL, floor_id NULL,
           property_reference, uprn NULL, address, property_type,
           status,   -- PLANNED | UNDER_CONSTRUCTION | READY_FOR_HANDOVER |
                     -- HANDED_OVER | OPERATIONAL | VOID | OCCUPIED | DISPOSED
           ...ProvenanceMixin)
spaces(id, organisation_id, property_id NULL, building_id NULL, name, space_type, ...)
```

`buildings.development_id` and `properties.{development_id,building_id,
floor_id}` are all nullable: a property created directly (no development
context, e.g. an existing stock upload) is exactly as valid as one
created through a development. This is what lets §21 hold — "a planned
property should become the SAME logical property when operational" — the
row never gets recreated, only its `status` and relationships change.

## 2. Component model & taxonomy

```sql
component_types(id, code, name, parent_type_id NULL)   -- seeded taxonomy, org-extensible
components(id, organisation_id, development_id NULL, building_id NULL,
           property_id NULL, space_id NULL, parent_component_id NULL,
           component_reference, component_type_id, component_subtype,
           manufacturer, model, serial_number, specification_reference,
           installer, installation_date, commissioning_date,
           warranty_start, warranty_expiry, expected_life_years,
           indicative_replacement_date, status, ...ProvenanceMixin)
```

`parent_component_id` supports the parent/child example in spec §24
(Heating System → Boiler → Pump → Control) without a fixed depth.
`component_types` ships seeded with the spec §22 list (roof, windows,
fire doors, boilers, heat pumps, consumer units, smoke/CO alarms,
fire-stopping, cladding, lifts, kitchens, bathrooms, etc.) and orgs can
add subtypes — never a closed enum, since new asset categories appear
constantly in this domain.

**Decision:** `indicative_replacement_date` is a stored, recomputed field
(not calculated on read) driven by the Component Lifecycle job (§6
below), clearly labelled indicative in every UI surface.
**Rationale:** spec §23 explicitly: "do not treat indicative lifecycle
dates as guaranteed replacement requirements" — storing it recomputed
lets Planned Investment query cheaply while the UI/API contract keeps the
"indicative" framing impossible to drop by accident (it's a field name,
not a derived label applied late).

## 3. Identifier & reference engine — the critical new-build feature

Two completely separate identifier classes, never conflated in schema or
API:

```sql
-- internal, DataLume-generated, always present
{development,building,property,component,defect,change}.
    {development,building,property,component,defect,change}_reference  -- human-readable
    id                                                                 -- UUID, machine

-- external, only ever supplied/imported, nullable
external_references(id, organisation_id, entity_type, entity_id,
                     reference_type,   -- UPRN | PLANNING_REFERENCE |
                                       -- BUILDING_CONTROL_REFERENCE | BSR_REFERENCE |
                                       -- DEVELOPER_PLOT_NUMBER | CONTRACTOR_REFERENCE |
                                       -- MANUFACTURER_SERIAL_NUMBER | LAND_REGISTRY_REFERENCE
                     value, source, ...ProvenanceMixin)
```

**The single hardest constraint in this spec, enforced at the type
level:** there is no code path anywhere in the service layer that can
write a value into `reference_type IN (UPRN, PLANNING_REFERENCE,
BUILDING_CONTROL_REFERENCE, BSR_REFERENCE, ...)` except an explicit
"import/enter external reference" endpoint that requires `source_type IN
(MANUAL, FILE_UPLOAD, API, INTEGRATION)` — `SYSTEM_GENERATED` is
structurally disallowed for these reference types by a DB check
constraint, not just a code convention. The AI layer and internal
reference generator physically cannot populate this table.

**Internal reference generator:**

```sql
reference_patterns(id, organisation_id, entity_type, pattern,  -- e.g. "[ORG]-[DEVELOPMENT]-[BUILDING]-[TYPE]-[SEQUENCE]"
                    scope, next_sequence, is_active)
```

`ReferenceGenerator.generate(entity_type, context)` renders the pattern
against context tokens, reserves the next sequence atomically
(`SELECT ... FOR UPDATE` on `reference_patterns` row, or a Postgres
sequence per org+entity_type — see trade-off below), and writes the
result as immutable once the entity is created; changing it later
requires an explicit authorised "re-reference" action that is itself
audited and versioned (old reference retained, not deleted).

**Decision:** row-locked counter per `(organisation_id, entity_type,
scope)` rather than a global UUID-derived reference.
**Rationale:** the spec's example format
(`NTH-RIV-B01-FD-000238`) is a sequential, human-meaningful reference —
that requires a real counter, not a hash. Row-level locking on a small
counter table is a well-understood, cheap way to get gap-free-enough
sequential numbers per scope without a hot global lock.
**Alternative:** Postgres `SEQUENCE` per org+entity_type — simpler, but
harder to make failure-safe against a generated-but-unused number when a
request rolls back after reserving; the counter-table approach ties the
reservation to the same transaction as the entity insert.
**Trade-off:** slightly more write contention under very high concurrent
creation within one org/scope — acceptable at Build 1 scale (bulk import
batches sequence-reserve once per batch, not per row).

## 4. Specifications & Golden Thread

```sql
specifications(id, organisation_id, related_entity_type, related_entity_id,
               reference, title, description, revision, status,
               effective_date, superseded_date, related_component_type,
               source_document_id, created_by, approved_by NULL, ...)
```

**Golden Thread** is not a new table — it's a read-composition across
existing tables, expressed as one service function:

```
GoldenThreadView(building_id) →
  building → design (specifications) → component →
  responsible_party (from provenance/import metadata + contractor refs) →
  evidence (documents linked to component) →
  inspection (compliance inspections linked to component) →
  change (change_control rows for the component) →
  approval/external_reference (external_references) →
  handover (handover_records) → operation (current property/component state)
```

**Decision:** compose, don't duplicate. Golden Thread is a query/view
layer, not a parallel data model.
**Rationale:** spec §29 requires Golden Thread to be "linked to relevant
building/property/component" and traceable — duplicating data into a
separate Golden Thread table would create exactly the two-sources-of-truth
problem the whole spec is designed to avoid. The view is what's exported
as a Golden Thread report/PDF.
**Constraint honoured:** the UI copy and API docs explicitly state
storing this information does not by itself satisfy every legal Golden
Thread obligation (spec §29) — this is enforced as a review checklist
item on any Golden Thread-labelled screen, not something the architecture
alone can guarantee.

## 5. Building Control & regulatory mapping

`building_control_records` capture body, application reference/date,
approval date, status, conditions, completion reference/certificate
metadata, BSR reference, evidence, external source — every reference
field here routes through `external_references`, per §3's hard rule.

`regulatory_requirements(id, code, domain, description, effective_date,
superseded_date, version)` + `requirement_applicability(requirement_id,
entity_type, entity_id, status)` implement the configurable
`REQUIREMENT → DEVELOPMENT → BUILDING → DESIGN ELEMENT → COMPONENT →
EVIDENCE → INSPECTION → ACTION → EXTERNAL APPROVAL` chain from spec §31.
Versioned and effective-dated so a rule change doesn't silently rewrite
history — old requirement versions stay attached to the inspections that
were assessed against them.

## 6. Component lifecycle & planned investment

Deterministic scheduled job (`worker/jobs/component_lifecycle.py`), run
nightly per organisation:

```
for component in components_with_expected_life:
    indicative_replacement_date = installation_date + expected_life_years
    condition_signal = latest_inspection_condition(component)      # if any
    repair_frequency = repair_count(component, window=18mo)
    failure_pattern = repeat_failure_flag(component)                # see 04 §2
    investment_priority = score(
        age_ratio = age / expected_life_years,
        condition_signal,
        repair_frequency,
        failure_pattern,
        compliance_linked = has_open_compliance_action(component),
    )                                                                 # weights configurable per org
    upsert planned_investment_signal(component, investment_priority, factors_json)
```

**Decision:** `investment_priority` is a weighted, fully explainable
score with every contributing factor stored (`factors_json`), never a
single opaque number.
**Rationale:** spec §40 explicitly forbids using age alone; storing the
factor breakdown is what lets Explainability (see 06) answer "why is this
flagged" without re-deriving it.

## 7. Construction evidence & change control

`construction_evidence` links documents (02 §4) to an exact location in
the hierarchy (`DEVELOPMENT → BLOCK A → FLOOR 4 → FLAT 42 → VENTILATION
SYSTEM → INSTALLATION EVIDENCE`, spec §32) via a polymorphic
`(related_entity_type, related_entity_id)` pair down to component/space
granularity.

```sql
change_control(id, organisation_id, change_reference, development_id NULL,
                building_id NULL, property_id NULL, component_id NULL,
                previous_value JSONB, proposed_value JSONB, reason,
                impact_description, submitted_by, submitted_date,
                approval_status, approved_by NULL, approved_date NULL,
                external_approval_reference NULL, supporting_documents,
                ...)
```

`previous_value`/`proposed_value` are JSONB snapshots of the specification
fields being changed — a change never overwrites `specifications` in
place; on approval, a *new* `specifications` row is created with
`superseded_date` set on the old one, and `change_control.previous_value`
remains the permanent record of what was proposed and why (spec §33: "a
change must NOT simply overwrite the previous specification").

## 8. Defects, warranties, handover readiness

```sql
defects(id, organisation_id, defect_reference, development_id NULL,
        building_id NULL, property_id NULL, component_id NULL, category,
        description, severity, reported_date, contractor,
        responsible_party, target_date, completion_date, status,
        estimated_cost NULL, actual_cost NULL, evidence, warranty_related,
        ...ProvenanceMixin)
warranties(id, organisation_id, warranty_reference, provider,
           development_id NULL, building_id NULL, property_id NULL,
           component_id NULL, warranty_type, start_date, expiry_date,
           terms_reference, document_id NULL, status)
```

**Handover Readiness Formula** — deterministic, transparent, versioned:

```python
def handover_readiness(development_id: UUID) -> HandoverReadiness:
    properties = properties_in(development_id)
    checks = [
        PropertiesCreatedCheck(weight=0.10),
        ComponentsCapturedCheck(weight=0.15),
        RequiredComponentFieldsCheck(weight=0.10),   # serial numbers where expected
        WarrantiesReceivedCheck(weight=0.15),
        CertificatesReceivedCheck(weight=0.15),
        CommissioningEvidenceCheck(weight=0.10),
        OMDocumentationCheck(weight=0.05),
        BuildingControlReferenceCheck(weight=0.10),
        OutstandingDefectsCheck(weight=0.05),
        OutstandingRemedialActionsCheck(weight=0.05),
    ]
    results = [c.evaluate(properties) for c in checks]
    score = sum(r.weight * r.pass_ratio for r in results)
    missing = [item for r in results for item in r.missing_items]
    return HandoverReadiness(score_pct=round(score * 100), missing=missing, checks=results)
```

Weights live in `handover_readiness_config` per organisation (spec: "all
scoring methodology must be transparent/configurable" §37) and every
`HandoverReadiness` response includes the full `checks` breakdown, not
just the headline percentage — this is what renders the
`RIVERSIDE GARDENS — 84 PROPERTIES — 91% — MISSING: ...` view in §37
directly from the API response, no separate summarisation step.

## 9. Development → Operational transition

Handover is a `status` transition on the *same* `properties` /
`components` rows (never a copy), executed inside one transaction by
`HandoverService.authorise(development_id, actor)`:

1. Assert `handover_readiness(development_id).score_pct` meets the
   organisation's configured threshold, or an explicit override reason is
   supplied by a permitted role (`HANDOVER_MANAGER`+).
2. Set every `properties.status` in scope from `READY_FOR_HANDOVER` →
   `HANDED_OVER` (then `OPERATIONAL` once occupied/void-managed).
3. Write a `handover_records` row per property capturing the readiness
   snapshot, authoriser, timestamp — the permanent evidence that handover
   happened and what was known at the time.
4. Emit an audit event per property.

Nothing in `operations` (repairs, compliance) or `commercial` (tenancies)
creates a new property record — they all query the same `properties`
table, so "preserve development history" (spec §39, acceptance items
38–43) is automatic: the component register, specifications, evidence,
warranties, defects and Golden Thread composition are unchanged by the
status flip, because they were never keyed to a "development-phase"
record that gets swapped out.
