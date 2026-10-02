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
  const [submitting, setSubmitting] = useState(false);
  const [showActionForm, setShowActionForm] = useState(false);
  const [actionDescription, setActionDescription] = useState("");
  const [actionDeadline, setActionDeadline] = useState("");
  const [actionSubmitting, setActionSubmitting] = useState(false);

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
      await api.createInspection(organisationId, {
        requirement_id: requirementId,
        entity_type: entityType,
        entity_id: entityId,
        inspector: inspector.trim(),
        inspection_date: inspectionDate,
        result,
        next_due_date: nextDueDate || undefined,
      });
      setInspector("");
      setInspectionDate("");
      setNextDueDate("");
      setShowForm(false);
      await refresh();
      onChanged?.();
    } finally {
      setSubmitting(false);
    }
  }

  async function onCompleteAction(actionId: string) {
    await api.updateComplianceActionStatus(organisationId, actionId, { status: "COMPLETED" });
    await refresh();
    onChanged?.();
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
          </>
        ) : (
          "No inspections recorded yet."
        )}
      </div>
      {openActions.length > 0 && (
        <ul style={{ listStyle: "none", padding: 0, margin: "0 0 6px" }}>
          {openActions.map((a) => (
            <li key={a.id} style={{ display: "flex", justifyContent: "space-between", padding: "2px 0" }}>
              <span>
                {a.description} — due {a.deadline}
              </span>
              <button style={{ ...secondaryBtn, padding: "1px 8px", fontSize: 11 }} onClick={() => onCompleteAction(a.id)}>
                complete
              </button>
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
