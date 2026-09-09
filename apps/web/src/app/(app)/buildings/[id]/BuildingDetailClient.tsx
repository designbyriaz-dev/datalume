"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { StatusBadge } from "@/components/StatusBadge";
import { inputStyle, primaryBtn, secondaryBtn } from "@/components/formStyles";
import {
  api,
  type BuildingOut,
  type ComplianceActionOut,
  type ComplianceRequirementOut,
  type ComplianceStatusOut,
  type DefectOut,
  type FloorOut,
  type GoldenThread,
  type InspectionOut,
  type PropertyOut,
  type RequirementApplicabilityOut,
  type SpecificationOut,
  type WarrantyOut,
} from "@/lib/api";

const COMPLIANCE_STATUS_VARIANT: Record<string, "success" | "warning" | "critical" | "neutral"> = {
  CURRENT: "success",
  DUE_SOON: "warning",
  NEEDS_REVIEW: "warning",
  OPEN_ACTION: "warning",
  UNKNOWN: "neutral",
  NOT_APPLICABLE: "neutral",
  MISSING_EVIDENCE: "critical",
  OVERDUE: "critical",
  OVERDUE_ACTION: "critical",
  EXPIRED: "warning",
};

const SELECTED_ORG_KEY = "datalume.selectedOrganisationId";

const DEFECT_SEVERITIES = ["LOW", "MEDIUM", "HIGH", "CRITICAL"] as const;

const DEFECT_TRANSITIONS: Record<string, string[]> = {
  OPEN: ["ASSIGNED", "REJECTED"],
  ASSIGNED: ["IN_PROGRESS", "REJECTED"],
  IN_PROGRESS: ["READY_FOR_INSPECTION", "REJECTED"],
  READY_FOR_INSPECTION: ["COMPLETED", "IN_PROGRESS"],
  COMPLETED: ["CLOSED"],
  REJECTED: ["CLOSED"],
  CLOSED: [],
};

function statusVariant(status: string) {
  if (status === "OPERATIONAL" || status === "COMPLETED") return "success" as const;
  return "neutral" as const;
}

function specStatusVariant(status: string) {
  return status === "SUPERSEDED" ? ("neutral" as const) : ("success" as const);
}

function defectStatusVariant(status: string) {
  if (status === "COMPLETED" || status === "CLOSED") return "success" as const;
  if (status === "REJECTED") return "critical" as const;
  return "neutral" as const;
}

function defectSeverityVariant(severity: string) {
  if (severity === "CRITICAL" || severity === "HIGH") return "critical" as const;
  if (severity === "MEDIUM") return "warning" as const;
  return "neutral" as const;
}

function InspectionsPanel({
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
      {showForm ? (
        <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
          <input
            style={{ ...inputStyle, fontSize: 12, maxWidth: 140 }}
            placeholder="Inspector"
            value={inspector}
            onChange={(e) => setInspector(e.target.value)}
          />
          <input
            style={{ ...inputStyle, fontSize: 12, maxWidth: 130 }}
            type="date"
            value={inspectionDate}
            onChange={(e) => setInspectionDate(e.target.value)}
          />
          <select style={{ ...inputStyle, fontSize: 12, width: "auto" }} value={result} onChange={(e) => setResult(e.target.value)}>
            <option value="SATISFACTORY">Satisfactory</option>
            <option value="UNSATISFACTORY">Unsatisfactory</option>
            <option value="ADVISORY">Advisory</option>
          </select>
          <input
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

export function BuildingDetailClient({ buildingId }: { buildingId: string }) {
  const [building, setBuilding] = useState<BuildingOut | null>(null);
  const [floors, setFloors] = useState<FloorOut[] | null>(null);
  const [properties, setProperties] = useState<PropertyOut[] | null>(null);
  const [specifications, setSpecifications] = useState<SpecificationOut[] | null>(null);
  const [goldenThread, setGoldenThread] = useState<GoldenThread | null>(null);
  const [defects, setDefects] = useState<DefectOut[] | null>(null);
  const [warranties, setWarranties] = useState<WarrantyOut[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [floorName, setFloorName] = useState("");
  const [levelIndex, setLevelIndex] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  const [specTitle, setSpecTitle] = useState("");
  const [specDescription, setSpecDescription] = useState("");
  const [specSubmitting, setSpecSubmitting] = useState(false);
  const [specFormError, setSpecFormError] = useState<string | null>(null);

  const [defectCategory, setDefectCategory] = useState("");
  const [defectDescription, setDefectDescription] = useState("");
  const [defectSeverity, setDefectSeverity] = useState<(typeof DEFECT_SEVERITIES)[number]>("MEDIUM");
  const [defectSubmitting, setDefectSubmitting] = useState(false);
  const [defectFormError, setDefectFormError] = useState<string | null>(null);

  const [warrantyProvider, setWarrantyProvider] = useState("");
  const [warrantyType, setWarrantyType] = useState("");
  const [warrantyExpiryDate, setWarrantyExpiryDate] = useState("");
  const [warrantySubmitting, setWarrantySubmitting] = useState(false);
  const [warrantyFormError, setWarrantyFormError] = useState<string | null>(null);

  const [applicability, setApplicability] = useState<RequirementApplicabilityOut[] | null>(null);
  const [requirements, setRequirements] = useState<ComplianceRequirementOut[] | null>(null);
  const [complianceStatuses, setComplianceStatuses] = useState<ComplianceStatusOut[]>([]);
  const [applicabilityRequirementId, setApplicabilityRequirementId] = useState("");
  const [applicabilityBasis, setApplicabilityBasis] = useState("");
  const [applicabilitySubmitting, setApplicabilitySubmitting] = useState(false);
  const [applicabilityFormError, setApplicabilityFormError] = useState<string | null>(null);

  function orgId(): string | null {
    return typeof window === "undefined" ? null : window.localStorage.getItem(SELECTED_ORG_KEY);
  }

  async function refreshFloors() {
    const id = orgId();
    if (!id) return;
    setFloors(await api.listFloors(id, buildingId));
  }

  async function refreshSpecifications() {
    const id = orgId();
    if (!id) return;
    setSpecifications(await api.listSpecifications(id, { related_entity_type: "building", related_entity_id: buildingId }));
  }

  async function refreshGoldenThread() {
    const id = orgId();
    if (!id) return;
    setGoldenThread(await api.getGoldenThread(id, buildingId));
  }

  async function refreshDefects() {
    const id = orgId();
    if (!id) return;
    setDefects(await api.listDefects(id, { building_id: buildingId }));
  }

  async function refreshWarranties() {
    const id = orgId();
    if (!id) return;
    setWarranties(await api.listWarranties(id, { building_id: buildingId }));
  }

  async function refreshApplicability() {
    const id = orgId();
    if (!id) return;
    setApplicability(await api.listApplicability(id, { entity_type: "building", entity_id: buildingId }));
    setComplianceStatuses(await api.listComplianceStatuses(id, "building", buildingId));
  }

  useEffect(() => {
    (async () => {
      const id = orgId();
      if (!id) {
        setLoadError("No organisation selected.");
        return;
      }
      try {
        const [
          b,
          floorList,
          propertyList,
          specList,
          thread,
          defectList,
          warrantyList,
          applicabilityList,
          requirementList,
          statusList,
        ] = await Promise.all([
          api.getBuilding(id, buildingId),
          api.listFloors(id, buildingId),
          api.listProperties(id, { building_id: buildingId }),
          api.listSpecifications(id, { related_entity_type: "building", related_entity_id: buildingId }),
          api.getGoldenThread(id, buildingId),
          api.listDefects(id, { building_id: buildingId }),
          api.listWarranties(id, { building_id: buildingId }),
          api.listApplicability(id, { entity_type: "building", entity_id: buildingId }),
          api.listComplianceRequirements(id),
          api.listComplianceStatuses(id, "building", buildingId),
        ]);
        setBuilding(b);
        setFloors(floorList);
        setProperties(propertyList);
        setSpecifications(specList);
        setGoldenThread(thread);
        setDefects(defectList);
        setWarranties(warrantyList);
        setApplicability(applicabilityList);
        setRequirements(requirementList);
        setComplianceStatuses(statusList);
        if (requirementList[0]) setApplicabilityRequirementId(requirementList[0].id);
      } catch {
        setLoadError("Couldn't load this building.");
      }
    })();
  }, [buildingId]);

  async function onAddFloor() {
    const id = orgId();
    if (!id || !floorName.trim()) {
      setFormError("Give the floor a name first.");
      return;
    }
    setSubmitting(true);
    setFormError(null);
    try {
      await api.createFloor(id, {
        building_id: buildingId,
        name: floorName.trim(),
        level_index: levelIndex ? Number(levelIndex) : undefined,
      });
      setFloorName("");
      setLevelIndex("");
      await refreshFloors();
    } catch {
      setFormError("Couldn't add that floor.");
    } finally {
      setSubmitting(false);
    }
  }

  async function onAddSpecification() {
    const id = orgId();
    if (!id || !specTitle.trim()) {
      setSpecFormError("Give the specification a title first.");
      return;
    }
    setSpecSubmitting(true);
    setSpecFormError(null);
    try {
      await api.createSpecification(id, {
        related_entity_type: "building",
        related_entity_id: buildingId,
        title: specTitle.trim(),
        description: specDescription.trim() || undefined,
      });
      setSpecTitle("");
      setSpecDescription("");
      await Promise.all([refreshSpecifications(), refreshGoldenThread()]);
    } catch {
      setSpecFormError("Couldn't add that specification.");
    } finally {
      setSpecSubmitting(false);
    }
  }

  async function onApproveSpecification(specificationId: string) {
    const id = orgId();
    if (!id) return;
    await api.approveSpecification(id, specificationId);
    await refreshSpecifications();
  }

  async function onAddDefect() {
    const id = orgId();
    if (!id || !defectCategory.trim() || !defectDescription.trim()) {
      setDefectFormError("Give the defect a category and description first.");
      return;
    }
    setDefectSubmitting(true);
    setDefectFormError(null);
    try {
      await api.createDefect(id, {
        category: defectCategory.trim(),
        description: defectDescription.trim(),
        reported_date: new Date().toISOString().slice(0, 10),
        severity: defectSeverity,
        building_id: buildingId,
      });
      setDefectCategory("");
      setDefectDescription("");
      await refreshDefects();
    } catch {
      setDefectFormError("Couldn't add that defect.");
    } finally {
      setDefectSubmitting(false);
    }
  }

  async function onDefectStatusChange(defectId: string, nextStatus: string) {
    const id = orgId();
    if (!id) return;
    await api.updateDefectStatus(id, defectId, { status: nextStatus });
    await refreshDefects();
  }

  async function onAddWarranty() {
    const id = orgId();
    if (!id || !warrantyProvider.trim() || !warrantyType.trim() || !warrantyExpiryDate) {
      setWarrantyFormError("Give the warranty a provider, type, and expiry date.");
      return;
    }
    setWarrantySubmitting(true);
    setWarrantyFormError(null);
    try {
      await api.createWarranty(id, {
        provider: warrantyProvider.trim(),
        warranty_type: warrantyType.trim(),
        start_date: new Date().toISOString().slice(0, 10),
        expiry_date: warrantyExpiryDate,
        building_id: buildingId,
      });
      setWarrantyProvider("");
      setWarrantyType("");
      setWarrantyExpiryDate("");
      await refreshWarranties();
    } catch {
      setWarrantyFormError("Couldn't add that warranty.");
    } finally {
      setWarrantySubmitting(false);
    }
  }

  async function onVoidWarranty(warrantyId: string) {
    const id = orgId();
    if (!id) return;
    await api.voidWarranty(id, warrantyId);
    await refreshWarranties();
  }

  async function onAddApplicability() {
    const id = orgId();
    if (!id || !applicabilityRequirementId) {
      setApplicabilityFormError("Add a compliance requirement first (see the Compliance page).");
      return;
    }
    setApplicabilitySubmitting(true);
    setApplicabilityFormError(null);
    try {
      await api.createApplicability(id, {
        requirement_id: applicabilityRequirementId,
        entity_type: "building",
        entity_id: buildingId,
        applicable_from: new Date().toISOString().slice(0, 10),
        basis: applicabilityBasis.trim() || undefined,
      });
      setApplicabilityBasis("");
      await refreshApplicability();
    } catch {
      setApplicabilityFormError("Couldn't add that.");
    } finally {
      setApplicabilitySubmitting(false);
    }
  }

  async function onEndApplicability(applicabilityId: string) {
    const id = orgId();
    if (!id) return;
    await api.endApplicability(id, applicabilityId, new Date().toISOString().slice(0, 10));
    await refreshApplicability();
  }

  if (loadError) {
    return <div style={{ color: "var(--text-secondary)" }}>{loadError}</div>;
  }

  if (!building || !floors || !properties || !specifications || !defects || !warranties || !applicability || !requirements) {
    return <div style={{ color: "var(--text-secondary)" }}>Loading…</div>;
  }

  return (
    <div style={{ maxWidth: 860 }}>
      <Link href="/buildings" style={{ fontSize: 13, color: "var(--color-primary)" }}>
        ← Buildings
      </Link>

      <div style={{ display: "flex", alignItems: "center", gap: 12, margin: "8px 0 4px" }}>
        <h1 style={{ fontSize: 24, fontWeight: 700, margin: 0 }}>{building.name}</h1>
        <StatusBadge label={building.status} variant={statusVariant(building.status)} />
      </div>
      <p style={{ color: "var(--text-secondary)", marginBottom: 24, fontFamily: "monospace", fontSize: 13 }}>
        {building.building_reference}
      </p>

      <div
        style={{
          background: "var(--bg-card)",
          border: "1px solid var(--border-subtle)",
          borderRadius: "var(--radius-card)",
          padding: 20,
          marginBottom: 24,
        }}
      >
        <h2 style={{ fontSize: 16, fontWeight: 700, margin: 0, marginBottom: 16 }}>Add a floor</h2>
        <div style={{ display: "grid", gap: 12, gridTemplateColumns: "2fr 1fr auto", alignItems: "end" }}>
          <div>
            <label style={{ fontSize: 12, color: "var(--text-secondary)", display: "block", marginBottom: 4 }}>
              Name
            </label>
            <input
              style={inputStyle}
              value={floorName}
              onChange={(e) => setFloorName(e.target.value)}
              placeholder="e.g. Ground Floor"
            />
          </div>
          <div>
            <label style={{ fontSize: 12, color: "var(--text-secondary)", display: "block", marginBottom: 4 }}>
              Level index
            </label>
            <input style={inputStyle} value={levelIndex} onChange={(e) => setLevelIndex(e.target.value)} placeholder="0" />
          </div>
          <button style={primaryBtn} onClick={onAddFloor} disabled={submitting}>
            {submitting ? "Adding…" : "Add"}
          </button>
        </div>
        {formError && <div style={{ color: "var(--color-critical)", fontSize: 13, marginTop: 10 }}>{formError}</div>}
      </div>

      <h2 style={{ fontSize: 16, fontWeight: 700, marginBottom: 12 }}>Floors</h2>
      {floors.length === 0 ? (
        <div style={{ color: "var(--text-secondary)", fontSize: 14, marginBottom: 24 }}>No floors yet.</div>
      ) : (
        <ul style={{ listStyle: "none", padding: 0, margin: "0 0 24px" }}>
          {floors.map((f) => (
            <li
              key={f.id}
              style={{
                padding: "10px 0",
                borderTop: "1px solid var(--border-subtle)",
                fontSize: 13,
                display: "flex",
                justifyContent: "space-between",
              }}
            >
              <span>{f.name}</span>
              <span style={{ color: "var(--text-secondary)" }}>
                {f.level_index !== null ? `Level ${f.level_index}` : "—"}
              </span>
            </li>
          ))}
        </ul>
      )}

      <h2 style={{ fontSize: 16, fontWeight: 700, marginBottom: 12 }}>Properties on this building</h2>
      {properties.length === 0 ? (
        <div style={{ color: "var(--text-secondary)", fontSize: 14, marginBottom: 24 }}>None yet.</div>
      ) : (
        <ul style={{ listStyle: "none", padding: 0, margin: "0 0 24px" }}>
          {properties.map((p) => (
            <li key={p.id} style={{ padding: "10px 0", borderTop: "1px solid var(--border-subtle)", fontSize: 13 }}>
              <Link href={`/properties/${p.id}`} style={{ color: "var(--color-primary)" }}>
                {p.property_reference}
              </Link>{" "}
              — {p.address}
            </li>
          ))}
        </ul>
      )}

      <div
        style={{
          background: "var(--bg-card)",
          border: "1px solid var(--border-subtle)",
          borderRadius: "var(--radius-card)",
          padding: 20,
          marginBottom: 24,
        }}
      >
        <h2 style={{ fontSize: 16, fontWeight: 700, margin: 0, marginBottom: 16 }}>Add a specification</h2>
        <div style={{ display: "grid", gap: 12, gridTemplateColumns: "1fr 2fr auto", alignItems: "end" }}>
          <div>
            <label style={{ fontSize: 12, color: "var(--text-secondary)", display: "block", marginBottom: 4 }}>
              Title
            </label>
            <input
              style={inputStyle}
              value={specTitle}
              onChange={(e) => setSpecTitle(e.target.value)}
              placeholder="e.g. External wall insulation system"
            />
          </div>
          <div>
            <label style={{ fontSize: 12, color: "var(--text-secondary)", display: "block", marginBottom: 4 }}>
              Description
            </label>
            <input style={inputStyle} value={specDescription} onChange={(e) => setSpecDescription(e.target.value)} />
          </div>
          <button style={primaryBtn} onClick={onAddSpecification} disabled={specSubmitting}>
            {specSubmitting ? "Adding…" : "Add"}
          </button>
        </div>
        {specFormError && (
          <div style={{ color: "var(--color-critical)", fontSize: 13, marginTop: 10 }}>{specFormError}</div>
        )}
      </div>

      <h2 style={{ fontSize: 16, fontWeight: 700, marginBottom: 12 }}>Specifications</h2>
      {specifications.length === 0 ? (
        <div style={{ color: "var(--text-secondary)", fontSize: 14, marginBottom: 24 }}>No specifications yet.</div>
      ) : (
        <ul style={{ listStyle: "none", padding: 0, margin: "0 0 24px" }}>
          {specifications.map((s) => (
            <li
              key={s.id}
              style={{
                padding: "10px 0",
                borderTop: "1px solid var(--border-subtle)",
                fontSize: 13,
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                gap: 12,
              }}
            >
              <span>
                <span style={{ fontFamily: "monospace", color: "var(--text-secondary)", marginRight: 8 }}>
                  {s.specification_reference}
                </span>
                {s.title}{" "}
                <span style={{ color: "var(--text-secondary)" }}>rev {s.revision}</span>
              </span>
              <span style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <StatusBadge label={s.status} variant={specStatusVariant(s.status)} />
                {s.approved_by ? (
                  <StatusBadge label="Approved" variant="success" />
                ) : (
                  <button
                    style={{ ...primaryBtn, padding: "4px 10px", fontSize: 12 }}
                    onClick={() => onApproveSpecification(s.id)}
                  >
                    Approve
                  </button>
                )}
              </span>
            </li>
          ))}
        </ul>
      )}

      <h2 style={{ fontSize: 16, fontWeight: 700, marginBottom: 4 }}>Golden Thread</h2>
      <p style={{ color: "var(--text-secondary)", fontSize: 13, marginBottom: 16 }}>
        Everything DataLume can currently trace for this building — design, components, responsible parties,
        evidence and approvals. Storing this information does not by itself satisfy every legal Golden Thread
        obligation.
      </p>
      {!goldenThread ? (
        <div style={{ color: "var(--text-secondary)" }}>Loading…</div>
      ) : (
        <div style={{ marginBottom: 24 }}>
          {goldenThread.components.length === 0 ? (
            <div style={{ color: "var(--text-secondary)", fontSize: 14, marginBottom: 12 }}>
              No components linked to this building yet.
            </div>
          ) : (
            goldenThread.components.map((c) => (
              <div
                key={c.id}
                style={{
                  background: "var(--bg-card)",
                  border: "1px solid var(--border-subtle)",
                  borderRadius: "var(--radius-card)",
                  padding: 16,
                  marginBottom: 12,
                  fontSize: 13,
                }}
              >
                <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 8 }}>
                  <Link href={`/components/${c.id}`} style={{ color: "var(--color-primary)", fontWeight: 700 }}>
                    {c.component_reference} — {c.component_type_name}
                  </Link>
                  <StatusBadge label={c.status} variant={c.status === "ACTIVE" ? "success" : "neutral"} />
                </div>
                <div style={{ color: "var(--text-secondary)", marginBottom: 4 }}>
                  Specifications: {c.specifications.length === 0 ? "none" : c.specifications.map((s) => s.title).join(", ")}
                </div>
                <div style={{ color: "var(--text-secondary)", marginBottom: 4 }}>
                  Evidence: {c.evidence.length === 0 ? "none" : c.evidence.map((d) => d.title).join(", ")}
                </div>
                <div style={{ color: "var(--text-secondary)", marginBottom: 4 }}>
                  Change control:{" "}
                  {c.changes.length === 0
                    ? "none"
                    : c.changes.map((ch) => `${ch.change_reference} (${ch.status})`).join(", ")}
                </div>
                <div style={{ color: "var(--text-secondary)", marginBottom: 4 }}>
                  Inspections:{" "}
                  {c.inspections.length === 0
                    ? "none"
                    : c.inspections.map((i) => `${i.inspection_date} (${i.result})`).join(", ")}
                </div>
                <div style={{ color: "var(--text-secondary)" }}>
                  Responsible party:{" "}
                  {c.responsible_party.created_by_name ?? c.responsible_party.source_type}
                  {c.responsible_party.contractor_reference ? ` · ${c.responsible_party.contractor_reference}` : ""}
                </div>
              </div>
            ))
          )}
          <div style={{ color: "var(--text-secondary)", fontSize: 13, marginBottom: 4 }}>
            Building-level inspections:{" "}
            {goldenThread.inspections.length === 0
              ? "none"
              : goldenThread.inspections.map((i) => `${i.inspection_date} (${i.result})`).join(", ")}
          </div>
          {goldenThread.not_yet_available.length > 0 && (
            <div style={{ color: "var(--text-secondary)", fontSize: 12 }}>
              Not yet available: {goldenThread.not_yet_available.join(", ")}
            </div>
          )}
        </div>
      )}

      <div
        style={{
          background: "var(--bg-card)",
          border: "1px solid var(--border-subtle)",
          borderRadius: "var(--radius-card)",
          padding: 20,
          marginBottom: 24,
        }}
      >
        <h2 style={{ fontSize: 16, fontWeight: 700, margin: 0, marginBottom: 16 }}>Report a defect</h2>
        <div style={{ display: "grid", gap: 12, gridTemplateColumns: "1fr 1.5fr 1fr auto", alignItems: "end" }}>
          <div>
            <label style={{ fontSize: 12, color: "var(--text-secondary)", display: "block", marginBottom: 4 }}>
              Category
            </label>
            <input
              style={inputStyle}
              value={defectCategory}
              onChange={(e) => setDefectCategory(e.target.value)}
              placeholder="e.g. Windows"
            />
          </div>
          <div>
            <label style={{ fontSize: 12, color: "var(--text-secondary)", display: "block", marginBottom: 4 }}>
              Description
            </label>
            <input
              style={inputStyle}
              value={defectDescription}
              onChange={(e) => setDefectDescription(e.target.value)}
            />
          </div>
          <div>
            <label style={{ fontSize: 12, color: "var(--text-secondary)", display: "block", marginBottom: 4 }}>
              Severity
            </label>
            <select
              style={inputStyle}
              value={defectSeverity}
              onChange={(e) => setDefectSeverity(e.target.value as (typeof DEFECT_SEVERITIES)[number])}
            >
              {DEFECT_SEVERITIES.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </div>
          <button style={primaryBtn} onClick={onAddDefect} disabled={defectSubmitting}>
            {defectSubmitting ? "Reporting…" : "Report"}
          </button>
        </div>
        {defectFormError && (
          <div style={{ color: "var(--color-critical)", fontSize: 13, marginTop: 10 }}>{defectFormError}</div>
        )}
      </div>

      <h2 style={{ fontSize: 16, fontWeight: 700, marginBottom: 12 }}>Defects</h2>
      {defects.length === 0 ? (
        <div style={{ color: "var(--text-secondary)", fontSize: 14, marginBottom: 24 }}>No defects reported.</div>
      ) : (
        <ul style={{ listStyle: "none", padding: 0, margin: "0 0 24px" }}>
          {defects.map((d) => (
            <li key={d.id} style={{ padding: "12px 0", borderTop: "1px solid var(--border-subtle)", fontSize: 13 }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
                <span>
                  <span style={{ fontFamily: "monospace", color: "var(--text-secondary)", marginRight: 8 }}>
                    {d.defect_reference}
                  </span>
                  {d.category}
                </span>
                <span style={{ display: "flex", gap: 6 }}>
                  <StatusBadge label={d.severity} variant={defectSeverityVariant(d.severity)} />
                  <StatusBadge label={d.status} variant={defectStatusVariant(d.status)} />
                </span>
              </div>
              <div style={{ color: "var(--text-secondary)", marginBottom: 8 }}>{d.description}</div>
              <div style={{ display: "flex", gap: 8 }}>
                {(DEFECT_TRANSITIONS[d.status] ?? []).map((next) => (
                  <button
                    key={next}
                    style={{ ...primaryBtn, padding: "4px 10px", fontSize: 12 }}
                    onClick={() => onDefectStatusChange(d.id, next)}
                  >
                    {next.replace(/_/g, " ").toLowerCase()}
                  </button>
                ))}
              </div>
            </li>
          ))}
        </ul>
      )}

      <div
        style={{
          background: "var(--bg-card)",
          border: "1px solid var(--border-subtle)",
          borderRadius: "var(--radius-card)",
          padding: 20,
          marginBottom: 24,
        }}
      >
        <h2 style={{ fontSize: 16, fontWeight: 700, margin: 0, marginBottom: 16 }}>Add a warranty</h2>
        <div style={{ display: "grid", gap: 12, gridTemplateColumns: "1.2fr 1.2fr 1fr auto", alignItems: "end" }}>
          <div>
            <label style={{ fontSize: 12, color: "var(--text-secondary)", display: "block", marginBottom: 4 }}>
              Provider
            </label>
            <input style={inputStyle} value={warrantyProvider} onChange={(e) => setWarrantyProvider(e.target.value)} />
          </div>
          <div>
            <label style={{ fontSize: 12, color: "var(--text-secondary)", display: "block", marginBottom: 4 }}>
              Type
            </label>
            <input
              style={inputStyle}
              value={warrantyType}
              onChange={(e) => setWarrantyType(e.target.value)}
              placeholder="e.g. Structural warranty"
            />
          </div>
          <div>
            <label style={{ fontSize: 12, color: "var(--text-secondary)", display: "block", marginBottom: 4 }}>
              Expiry date
            </label>
            <input
              style={inputStyle}
              type="date"
              value={warrantyExpiryDate}
              onChange={(e) => setWarrantyExpiryDate(e.target.value)}
            />
          </div>
          <button style={primaryBtn} onClick={onAddWarranty} disabled={warrantySubmitting}>
            {warrantySubmitting ? "Adding…" : "Add"}
          </button>
        </div>
        {warrantyFormError && (
          <div style={{ color: "var(--color-critical)", fontSize: 13, marginTop: 10 }}>{warrantyFormError}</div>
        )}
      </div>

      <h2 style={{ fontSize: 16, fontWeight: 700, marginBottom: 12 }}>Warranties</h2>
      {warranties.length === 0 ? (
        <div style={{ color: "var(--text-secondary)", fontSize: 14 }}>No warranties yet.</div>
      ) : (
        <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
          {warranties.map((w) => (
            <li
              key={w.id}
              style={{
                padding: "10px 0",
                borderTop: "1px solid var(--border-subtle)",
                fontSize: 13,
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                gap: 12,
              }}
            >
              <span>
                <span style={{ fontFamily: "monospace", color: "var(--text-secondary)", marginRight: 8 }}>
                  {w.warranty_reference}
                </span>
                {w.provider} — {w.warranty_type}{" "}
                <span style={{ color: "var(--text-secondary)" }}>
                  (expires {w.expiry_date}
                  {w.is_expired ? ", expired" : `, ${w.days_until_expiry}d left`})
                </span>
              </span>
              <span style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <StatusBadge
                  label={w.status === "VOID" ? "VOID" : w.is_expired ? "EXPIRED" : "ACTIVE"}
                  variant={w.status === "VOID" ? "critical" : w.is_expired ? "warning" : "success"}
                />
                {w.status === "ACTIVE" && (
                  <button
                    style={{ ...primaryBtn, padding: "4px 10px", fontSize: 12, background: "var(--text-secondary)" }}
                    onClick={() => onVoidWarranty(w.id)}
                  >
                    Void
                  </button>
                )}
              </span>
            </li>
          ))}
        </ul>
      )}

      <div
        style={{
          background: "var(--bg-card)",
          border: "1px solid var(--border-subtle)",
          borderRadius: "var(--radius-card)",
          padding: 20,
          marginBottom: 24,
        }}
      >
        <h2 style={{ fontSize: 16, fontWeight: 700, margin: 0, marginBottom: 16 }}>Add a compliance requirement</h2>
        <div style={{ display: "grid", gap: 12, gridTemplateColumns: "2fr 2fr auto", alignItems: "end" }}>
          <div>
            <label style={{ fontSize: 12, color: "var(--text-secondary)", display: "block", marginBottom: 4 }}>
              Requirement
            </label>
            <select
              style={inputStyle}
              value={applicabilityRequirementId}
              onChange={(e) => setApplicabilityRequirementId(e.target.value)}
            >
              {requirements.map((r) => (
                <option key={r.id} value={r.id}>
                  {r.code} — {r.title}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label style={{ fontSize: 12, color: "var(--text-secondary)", display: "block", marginBottom: 4 }}>
              Basis
            </label>
            <input
              style={inputStyle}
              value={applicabilityBasis}
              onChange={(e) => setApplicabilityBasis(e.target.value)}
              placeholder="e.g. Communal gas installation present"
            />
          </div>
          <button style={primaryBtn} onClick={onAddApplicability} disabled={applicabilitySubmitting}>
            {applicabilitySubmitting ? "Adding…" : "Add"}
          </button>
        </div>
        {requirements.length === 0 && (
          <div style={{ color: "var(--text-secondary)", fontSize: 13, marginTop: 10 }}>
            No compliance requirements defined yet — add one on the Compliance page first.
          </div>
        )}
        {applicabilityFormError && (
          <div style={{ color: "var(--color-critical)", fontSize: 13, marginTop: 10 }}>{applicabilityFormError}</div>
        )}
      </div>

      <h2 style={{ fontSize: 16, fontWeight: 700, marginBottom: 12 }}>Compliance requirements</h2>
      {applicability.length === 0 ? (
        <div style={{ color: "var(--text-secondary)", fontSize: 14 }}>None applied to this building yet.</div>
      ) : (
        <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
          {applicability.map((a) => {
            const requirement = requirements.find((r) => r.id === a.requirement_id);
            const computed = complianceStatuses.find((s) => s.requirement_id === a.requirement_id);
            return (
              <li
                key={a.id}
                style={{
                  padding: "10px 0",
                  borderTop: "1px solid var(--border-subtle)",
                  fontSize: 13,
                  display: "flex",
                  flexWrap: "wrap",
                  justifyContent: "space-between",
                  alignItems: "center",
                  gap: 12,
                }}
              >
                <span>
                  {requirement ? `${requirement.code} — ${requirement.title}` : a.requirement_id.slice(0, 8)}
                  {a.basis && <span style={{ color: "var(--text-secondary)" }}> ({a.basis})</span>}
                </span>
                <span style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  {!a.applicable_to && computed && (
                    <StatusBadge
                      label={computed.status.replace(/_/g, " ")}
                      variant={COMPLIANCE_STATUS_VARIANT[computed.status] ?? "neutral"}
                    />
                  )}
                  <StatusBadge
                    label={a.applicable_to ? `Ended ${a.applicable_to}` : "Applicable"}
                    variant={a.applicable_to ? "neutral" : "success"}
                  />
                  {!a.applicable_to && (
                    <button
                      style={{ ...primaryBtn, padding: "4px 10px", fontSize: 12, background: "var(--text-secondary)" }}
                      onClick={() => onEndApplicability(a.id)}
                    >
                      End
                    </button>
                  )}
                </span>
                {!a.applicable_to && (
                  <div style={{ width: "100%" }}>
                    <InspectionsPanel
                      organisationId={orgId() ?? ""}
                      requirementId={a.requirement_id}
                      entityType="building"
                      entityId={buildingId}
                      onChanged={refreshApplicability}
                    />
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
