# 02 — Data Platform: Provenance, Ingestion, Mapping, Cleaning, Data Health

## 1. Provenance model

Every important record carries the provenance columns from spec §15,
implemented as a reusable mixin so no domain table can opt out:

```python
class ProvenanceMixin:
    source_type: SourceType        # MANUAL | FILE_UPLOAD | API | SCHEDULED_IMPORT
                                    # | INTEGRATION | SYSTEM_GENERATED
    source_system: str | None
    source_dataset_id: UUID | None # FK -> datasets.id
    import_job_id: UUID | None     # FK -> import_jobs.id
    original_reference: str | None # the value as it appeared in the source
    created_by: UUID               # FK -> users.id
    created_at: datetime
    updated_by: UUID
    updated_at: datetime
```

Every domain entity in `development`, `operations` and `commercial`
inherits this mixin. "Where did this come from?" is always answerable
from the record itself, satisfying spec §15 and feeding Property 360's
Timeline (§41).

## 2. Dataset & upload pipeline

```sql
datasets(id, organisation_id, name, dataset_type, status, row_count,
         uploaded_by, uploaded_at, source_file_document_id)
import_jobs(id, dataset_id, status, started_at, finished_at, error_summary)
import_rows(id, import_job_id, row_number, raw_data JSONB,
            status,            -- PENDING | VALID | INVALID | IMPORTED | SKIPPED
            errors JSONB,
            mapped_entity_type, mapped_entity_id)
```

Flow (spec §13): **UPLOAD → VALIDATE → UNDERSTAND → MAP → REVIEW → IMPORT
→ ANALYSE**, implemented as a background-job pipeline so large files
never block the request thread or load into browser memory (spec §72):

1. **Upload** — file goes to object storage first (pre-signed URL from
   `apps/web`), API only ever receives the storage key. A `dataset` +
   `import_job` row is created, job enqueued.
2. **Validate** — worker parses with Polars, checks structural validity
   (encoding, column count, empty file), writes `import_rows` with raw
   data.
3. **Understand** — column/type/schema recognition: `SchemaRecognizer`
   fuzzy-matches uploaded headers against known field dictionaries per
   `dataset_type` (e.g. "Properties" dataset expects address/UPRN/type
   fields) and proposes a mapping.
4. **Map** — user reviews/edits the proposed column→field mapping in the
   UI (persisted as a reusable `mapping_template` per organisation +
   dataset type, so repeat imports of the same source system don't
   require re-mapping).
5. **Review** — validation results shown per row (valid/invalid/warning)
   before commit; nothing is imported silently.
6. **Import** — worker upserts canonical entities inside a transaction
   per batch, stamping `ProvenanceMixin` fields, and links each
   `import_row` to the entity it produced.
7. **Analyse** — Data Health and Attention Engine recompute for affected
   entities (queued, not synchronous).

**Decision:** background-job pipeline with a persisted `import_rows`
staging table, not a synchronous "parse and insert" endpoint.
**Rationale:** spec §72 requires designing for tens of thousands of
properties and never loading full datasets into browser memory; a
staging table also gives a per-row audit trail of exactly what was
imported from what raw input, which the "where did this come from"
requirement (§15) needs at row granularity, not just dataset granularity.
**Trade-off:** more moving parts than a synchronous importer; justified
by the explicit performance and provenance requirements.

## 3. Manual entry

Every "+ Add X" form (spec §14) is a thin UI wrapper over the same
service functions the import pipeline calls to create canonical
entities — so manual entry and file import produce identical, equally
valid records, both stamped with `ProvenanceMixin` (`source_type =
MANUAL`), both RBAC-checked, both audited. There is no separate
"manual record" model.

## 4. Document management

```sql
documents(id, organisation_id, document_reference, title, document_type,
          revision, version, status, uploaded_by, uploaded_at,
          effective_date, superseded_by_document_id,
          related_entity_type, related_entity_id,
          source, external_reference, storage_key, checksum)
```

**Decision:** append-only versioning — a new upload creates a new
`documents` row with `superseded_by_document_id` set on the prior
version, never an in-place file overwrite.
**Rationale:** spec §28 explicitly: "never silently overwrite previous
versions"; this also gives Golden Thread and Change Control a real
history to point at.

## 5. Data Health

Deterministic, versioned rule engine — not an LLM score. Each rule
produces `{check_code, severity, affected_entity_type, affected_entity_id,
message}` rows into `data_health_findings`, and a per-organisation score
is an aggregate (weighted % of applicable checks passing), recomputed by
the worker whenever relevant entities change (debounced, not on every
write).

Initial rule set (from spec §42, both development and operational):
missing property IDs, missing building relationships, duplicate
properties, duplicate components, missing component types, missing
serial numbers where expected, missing installation dates, missing
warranties, missing specifications, missing evidence, missing external
references, conflicting references, missing handover information,
invalid dates, orphan components, duplicate documents — plus the
operational checks reused by other domains (missing compliance evidence,
etc., defined alongside their own domain rather than duplicated here).

**Decision:** rules are plain Python functions registered in a
`data_health/rules/` registry with a stable `check_code`, each unit
tested in isolation (spec §75).
**Rationale:** "transparent Data Health" (§42) means a user must be able
to see *why* a score is what it is — a registry of named, individually
testable rules is directly inspectable and reportable, unlike a single
opaque scoring function.

## 6. Cleaning

Cleaning operations (trim whitespace, normalise casing, coerce
numbers-stored-as-text, standardise dates, dedupe candidates) run as part
of the **Validate** stage of the pipeline and are logged per-row as
`cleaning_applied: [{rule, before, after}]` inside `import_rows.raw_data`
metadata — cleaning is visible and reversible during Review, never silent.
