# 06 — Intelligence Layer: Attention Engine, Ask DataLume, Explainability, Reporting

Covers spec items 55, 56–59, 66–71: Analytics Architecture, Cross-Domain
Attention Engine, Ask DataLume, AI Grounding, Explainability, Reporting.

## 1. The non-negotiable AI architecture pipeline

```
DATA → VALIDATION → RECOGNITION → APPROVED MAPPING → CLEANING →
CANONICAL DATA → DETERMINISTIC ANALYTICS → CONTROLLED AI TOOLS →
LLM INTERPRETATION → USER
```

The LLM (via `@anthropic-ai/sdk`, already a project dependency) sits at
the very end of this pipeline and is **only ever given tool results**,
never database access, never raw table read access, never write access
of any kind. This is enforced structurally: `intelligence/ask/` exposes a
fixed, versioned set of **tools** (Python functions with typed
signatures) that call the deterministic services in `development`,
`operations`, `commercial` — the LLM cannot execute arbitrary queries; it
can only call `get_compliance_status(property_id)`,
`get_repeat_repairs(property_id)`, `get_arrears(lease_id)`, etc., and
those tools are exactly the same deterministic functions documented in
03/04/05 above.

**Decision:** tool-use (function-calling) architecture, not
retrieval-augmented free-text generation over the database.
**Rationale:** spec §57 lists an explicit forbidden list — the LLM must
never invent Building Control references, BSR references, UPRNs,
compliance status, defect counts, warranty dates, repair counts, rent,
payments, arrears or lease dates. The only way to make that a structural
guarantee rather than a prompting hope is for every number the LLM ever
states to have come from a typed tool return value that the response
renderer can trace back and cite — never from the model's own token
generation.

## 2. Ask DataLume

```python
class ToolResult(BaseModel):
    tool_name: str
    dataset: str
    fields: list[str]
    filters: dict
    time_period: DateRange | None
    records: list[dict]          # the actual grounding data returned to the model
    calculation: str | None      # e.g. "count of repairs where status=OPEN, window=90d"

class AskResponse(BaseModel):
    answer_text: str             # LLM interpretation ONLY — no numbers not present in tool_results
    tool_results: list[ToolResult]
    grounded: bool                # false if no tool could answer the question
    suggested_follow_ups: list[str]
```

If no registered tool can answer the question (`grounded=False`), the
response renderer forces a fixed "I don't have data to answer that"
family of responses rather than letting the model attempt a general
answer — spec §56/§91 (mobile spec, same rule): "if mock/real data can't
answer a question, say so explicitly rather than guessing." This is
enforced in the API layer (the frontend never sees an ungrounded
free-text answer with a fabricated-looking number), not just in the
system prompt.

Every `AskResponse` is rendered with the tool_results directly below the
message — dataset, fields, filters, time period, calculation — matching
spec §58 Explainability requirement and the mobile app's `<GroundedClaim>`
pattern, so web and mobile share the same response contract
(`AskResponse` is the shape both clients consume).

## 3. Cross-Domain Attention Engine

```sql
attention_rules(id, organisation_id NULL, code, name, domain_scope,
                 rule_definition JSONB, severity_default, is_active)
attention_signals(id, organisation_id, rule_id, entity_type, entity_id,
                   severity, detected_at, explanation JSONB, status)
                   -- status: OPEN | ACKNOWLEDGED | RESOLVED | DISMISSED
```

Each rule in `attention_rules` composes existing deterministic signals
from other domains (never restates their logic) — e.g. "warranty expiring
+ unresolved defect" reads `warranties.expiry_date` and open
`defects.status`, both already computed elsewhere; the rule is a join +
threshold, not a new calculation. `explanation` always stores `{what,
why, supporting_record_ids, recommended_investigation}` — the four
questions spec §55 requires every signal to answer, stored as data so the
UI renders them uniformly across every signal type (missing handover
evidence, repeat failures, compliance breach, lease+arrears overlap,
etc.) rather than each having bespoke copy.

A nightly worker job (`worker/jobs/attention_scan.py`) evaluates active
rules per organisation and upserts `attention_signals`, so Home and
Alerts read pre-computed signals — never scanning the whole dataset on
page load.

## 4. Reporting & export

`reports/` templates (one per spec §59 report type — Development
Summary, Handover Readiness, Compliance Executive Summary, Board
Assurance, Commercial Portfolio, etc.) are Jinja/ReportLab templates fed
by the same service-layer functions as the UI and Ask DataLume — a report
is a rendering target, not a separate data path. Export formats: PDF
(ReportLab/WeasyPrint), XLSX (openpyxl), CSV (native). Report generation
runs as a background job for anything beyond a small dataset, with the
finished file placed in object storage and a signed download link
returned — never generated synchronously in the request/response cycle
for large portfolios (same rationale as §72 performance elsewhere in this
pack).
