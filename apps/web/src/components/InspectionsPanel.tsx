"use client";

import { useEffect, useState } from "react";
import { inputStyle, primaryBtn, secondaryBtn } from "@/components/formStyles";
import { api, type ComplianceActionOut, type InspectionOut } from "@/lib/api";

// Shared between BuildingDetailClient.tsx and ComponentDetailClient.tsx
// — recording an inspection against a compliance requirement's
// applicability is the same flow regardless of which entity type it's
// scoped to (listInspections/createInspection both take a plain
// entity_type/entity_id pair).
export function InspectionsPanel({
  organisationId,
  requirementId,
  entityType,
  entityId,
  onChanged,
}: {
  organisationId: string;
  requirementId: string;
  entityType: string;
  entityId: string;
  onChanged?: () => void;
}) {
  const [inspections, setInspections] = useState<InspectionOut[] | null>(null);
  const [actions, setActions] = useState<ComplianceActionOut[] | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [inspector, setInspector] = useState("");
  const [inspectionDate, setInspectionDate] = useState("");
  const [result, setResult] = useState("SATISFACTORY");
  const [nextDueDate, setNextDueDate] = useState("");
  const [evidenceFile, setEvidenceFile] = useState<File | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [showActionForm, setShowActionForm] = useState(false);
  const [actionDescription, setActionDescription] = useState("");
  const [actionDeadline, setActionDeadline] = useState("");
  const [actionSubmitting, setActionSubmitting] = useState(false);
  // "Complete" is a per-action toggle — only one action's inline
  // complete-with-evidence form is open at a time, keyed by its own id,
  // same pattern as this codebase's other "New version"/"Manage" toggles.
  const [completingActionId, setCompletingActionId] = useState<string | null>(null);
  const [completionEvidenceFile, setCompletionEvidenceFile] = useState<File | null>(null);
  const [completingSubmitting, setCompletingSubmitting] = useState(false);

  async function refresh() {
    if (!organisationId) return;
    const [i, a] = await Promise.all([
      api.listInspections(organisationId, { entity_type: entityType, entity_id: entityId, requirement_id: requirementId }),
      api.listComplianceActions(organisationId, { entity_type: entityType, entity_id: entityId, requirement_id: requirementId }),
    ]);
    setInspections(i);
    setActions(a);
  }

  useEffect(() => {
    (async () => {
      await refresh();
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [organisationId, requirementId, entityId]);

  async function onRecord() {
    if (!inspector.trim() || !inspectionDate) return;
    setSubmitting(true);
    try {
      let evidenceDocumentId: string | undefined;
      if (evidenceFile) {
        const doc = await api.uploadDocument(
          organisationId,
          `Inspection evidence — ${inspector.trim()}, ${inspectionDate}`,
          "CERTIFICATE",
          evidenceFile,
          { related_entity_type: entityType, related_entity_id: entityId },
        );
        evidenceDocumentId = doc.id;
      }
      await api.createInspection(organisationId, {
        requirement_id: requirementId,
        entity_type: entityType,
        entity_id: entityId,
        inspector: inspector.trim(),
        inspection_date: inspectionDate,
        result,
        next_due_date: nextDueDate || undefined,
        evidence_document_id: evidenceDocumentId,
      });
      setInspector("");
      setInspectionDate("");
      setNextDueDate("");
      setEvidenceFile(null);
      setShowForm(false);
      await refresh();
      onChanged?.();
    } finally {
      setSubmitting(false);
    }
  }

  function onStartCompletingAction(actionId: string) {
    setCompletingActionId(actionId);
    setCompletionEvidenceFile(null);
  }

  async function onConfirmCompleteAction(actionId: string) {
    setCompletingSubmitting(true);
    try {
      let evidenceDocumentId: string | undefined;
      if (completionEvidenceFile) {
        const doc = await api.uploadDocument(
          organisationId,
          `Action completion evidence — ${new Date().toISOString().slice(0, 10)}`,
          "CERTIFICATE",
          completionEvidenceFile,
          { related_entity_type: entityType, related_entity_id: entityId },
        );
        evidenceDocumentId = doc.id;
      }
      await api.updateComplianceActionStatus(organisationId, actionId, {
        status: "COMPLETED",
        evidence_document_id: evidenceDocumentId,
      });
      setCompletingActionId(null);
      setCompletionEvidenceFile(null);
      await refresh();
      onChanged?.();
    } finally {
      setCompletingSubmitting(false);
    }
  }

  async function onRaiseAction() {
    if (!actionDescription.trim() || !actionDeadline) return;
    setActionSubmitting(true);
    try {
      await api.createComplianceAction(organisationId, {
        requirement_id: requirementId,
        entity_type: entityType,
        entity_id: entityId,
        description: actionDescription.trim(),
        deadline: actionDeadline,
        inspection_id: latest?.id,
      });
      setActionDescription("");
      setActionDeadline("");
      setShowActionForm(false);
      await refresh();
      onChanged?.();
    } finally {
      setActionSubmitting(false);
    }
  }

  const latest = inspections?.[0];
  const openActions = actions?.filter((a) => a.status === "OPEN") ?? [];

  return (
    <div style={{ marginTop: 8, paddingTop: 8, borderTop: "1px dashed var(--border-subtle)", fontSize: 12 }}>
      <div style={{ color: "var(--text-secondary)", marginBottom: 6 }}>
        {latest ? (
          <>
            Last inspection: {latest.inspection_date} by {latest.inspector} — <strong>{latest.result}</strong>
            {latest.next_due_date && ` (next due ${latest.next_due_date})`}
            {!latest.evidence_document_id && (
              <span style={{ color: "var(--color-warning)" }}> — no evidence document attached</span>
            )}
          </>
        ) : (
          "No inspections recorded yet."
        )}
      </div>
      {openActions.length > 0 && (
        <ul style={{ listStyle: "none", padding: 0, margin: "0 0 6px" }}>
          {openActions.map((a) => (
            <li key={a.id} style={{ padding: "2px 0" }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <span>
                  {a.description} — due {a.deadline}
                </span>
                <button
                  style={{ ...secondaryBtn, padding: "1px 8px", fontSize: 11 }}
                  onClick={() => (completingActionId === a.id ? setCompletingActionId(null) : onStartCompletingAction(a.id))}
                >
                  complete
                </button>
              </div>
              {completingActionId === a.id && (
                <div style={{ display: "flex", gap: 6, alignItems: "center", marginTop: 4, flexWrap: "wrap" }}>
                  <input
                    aria-label="Completion evidence file"
                    type="file"
                    style={{ fontSize: 11 }}
                    onChange={(e) => setCompletionEvidenceFile(e.target.files?.[0] ?? null)}
                  />
                  <button
                    style={{ ...primaryBtn, padding: "1px 8px", fontSize: 11 }}
                    onClick={() => onConfirmCompleteAction(a.id)}
                    disabled={completingSubmitting}
                  >
                    {completingSubmitting ? "Completing…" : "Confirm"}
                  </button>
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
      {showActionForm ? (
        <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 6 }}>
          <input
            aria-label="Compliance action description"
            style={{ ...inputStyle, fontSize: 12, minWidth: 160 }}
            placeholder="e.g. Replace smoke detector"
            value={actionDescription}
            onChange={(e) => setActionDescription(e.target.value)}
          />
          <input
            aria-label="Compliance action deadline"
            style={{ ...inputStyle, fontSize: 12, maxWidth: 130 }}
            type="date"
            value={actionDeadline}
            onChange={(e) => setActionDeadline(e.target.value)}
          />
          <button style={{ ...primaryBtn, padding: "4px 10px", fontSize: 12 }} onClick={onRaiseAction} disabled={actionSubmitting}>
            Save
          </button>
        </div>
      ) : (
        <button style={{ ...secondaryBtn, padding: "3px 8px", fontSize: 11, marginBottom: 6 }} onClick={() => setShowActionForm(true)}>
          + Raise action
        </button>
      )}
      {showForm ? (
        <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
          <input
            aria-label="Inspector"
            style={{ ...inputStyle, fontSize: 12, maxWidth: 140 }}
            placeholder="Inspector"
            value={inspector}
            onChange={(e) => setInspector(e.target.value)}
          />
          <input
            aria-label="Inspection date"
            style={{ ...inputStyle, fontSize: 12, maxWidth: 130 }}
            type="date"
            value={inspectionDate}
            onChange={(e) => setInspectionDate(e.target.value)}
          />
          <select aria-label="Result" style={{ ...inputStyle, fontSize: 12, width: "auto" }} value={result} onChange={(e) => setResult(e.target.value)}>
            <option value="SATISFACTORY">Satisfactory</option>
            <option value="UNSATISFACTORY">Unsatisfactory</option>
            <option value="ADVISORY">Advisory</option>
          </select>
          <input
            aria-label="Next due date"
            style={{ ...inputStyle, fontSize: 12, maxWidth: 130 }}
            type="date"
            title="Next due date"
            value={nextDueDate}
            onChange={(e) => setNextDueDate(e.target.value)}
          />
          <input
            aria-label="Inspection evidence file"
            type="file"
            style={{ fontSize: 12 }}
            onChange={(e) => setEvidenceFile(e.target.files?.[0] ?? null)}
          />
          <button style={{ ...primaryBtn, padding: "4px 10px", fontSize: 12 }} onClick={onRecord} disabled={submitting}>
            Save
          </button>
        </div>
      ) : (
        <button style={{ ...secondaryBtn, padding: "3px 8px", fontSize: 11 }} onClick={() => setShowForm(true)}>
          + Record inspection
        </button>
      )}
    </div>
  );
}
