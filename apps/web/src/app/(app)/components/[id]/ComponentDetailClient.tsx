"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { InspectionsPanel } from "@/components/InspectionsPanel";
import { StatusBadge } from "@/components/StatusBadge";
import { inputStyle, primaryBtn } from "@/components/formStyles";
import {
  api,
  type ChangeControlOut,
  type ComplianceRequirementOut,
  type ComplianceStatusOut,
  type ComponentOut,
  type ComponentType,
  type DocumentOut,
  type PlannedInvestmentScoreOut,
  type RequirementApplicabilityOut,
  type SpecificationOut,
} from "@/lib/api";

const SELECTED_ORG_KEY = "datalume.selectedOrganisationId";

const DOCUMENT_TYPES = ["EVIDENCE", "DRAWING", "SPECIFICATION", "CERTIFICATE", "REPORT", "PHOTOGRAPH", "OTHER"];

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

// Defined outside the component — same reasoning as data-and-uploads/
// page.tsx's own copy of this helper (react-hooks/immutability).
function triggerBlobDownload(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

function statusVariant(status: string) {
  if (status === "ACTIVE") return "success" as const;
  if (status === "DISPOSED") return "critical" as const;
  return "neutral" as const;
}

function specStatusVariant(status: string) {
  return status === "SUPERSEDED" ? ("neutral" as const) : ("success" as const);
}

function changeStatusVariant(status: string) {
  if (status === "IMPLEMENTED" || status === "APPROVED") return "success" as const;
  if (status === "REJECTED" || status === "CANCELLED") return "critical" as const;
  return "neutral" as const;
}

function orgId(): string | null {
  return typeof window === "undefined" ? null : window.localStorage.getItem(SELECTED_ORG_KEY);
}

export function ComponentDetailClient({ componentId }: { componentId: string }) {
  const [component, setComponent] = useState<ComponentOut | null>(null);
  const [children, setChildren] = useState<ComponentOut[] | null>(null);
  const [types, setTypes] = useState<ComponentType[]>([]);
  const [specifications, setSpecifications] = useState<SpecificationOut[] | null>(null);
  const [changes, setChanges] = useState<ChangeControlOut[] | null>(null);
  const [plannedInvestment, setPlannedInvestment] = useState<PlannedInvestmentScoreOut | null>(null);
  const [investmentExpanded, setInvestmentExpanded] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [childTypeId, setChildTypeId] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  const [specTitle, setSpecTitle] = useState("");
  const [specSubmitting, setSpecSubmitting] = useState(false);
  const [specFormError, setSpecFormError] = useState<string | null>(null);

  const [changeSpecId, setChangeSpecId] = useState("");
  const [changeProposedTitle, setChangeProposedTitle] = useState("");
  const [changeReason, setChangeReason] = useState("");
  const [changeSubmitting, setChangeSubmitting] = useState(false);
  const [changeFormError, setChangeFormError] = useState<string | null>(null);

  const [documents, setDocuments] = useState<DocumentOut[] | null>(null);
  const [docTitle, setDocTitle] = useState("");
  const [docType, setDocType] = useState<string>(DOCUMENT_TYPES[0] ?? "EVIDENCE");
  const [docFile, setDocFile] = useState<File | null>(null);
  const [docSubmitting, setDocSubmitting] = useState(false);
  const [docError, setDocError] = useState<string | null>(null);

  async function refreshDocuments() {
    const id = orgId();
    if (!id) return;
    setDocuments(await api.listDocuments(id, { related_entity_type: "component", related_entity_id: componentId }));
  }

  const [requirements, setRequirements] = useState<ComplianceRequirementOut[] | null>(null);
  const [applicability, setApplicability] = useState<RequirementApplicabilityOut[] | null>(null);
  const [complianceStatuses, setComplianceStatuses] = useState<ComplianceStatusOut[]>([]);
  const [applicabilityRequirementId, setApplicabilityRequirementId] = useState("");
  const [applicabilityBasis, setApplicabilityBasis] = useState("");
  const [applicabilitySubmitting, setApplicabilitySubmitting] = useState(false);
  const [applicabilityFormError, setApplicabilityFormError] = useState<string | null>(null);

  async function refreshApplicability() {
    const id = orgId();
    if (!id) return;
    const [applicabilityList, statusList] = await Promise.all([
      api.listApplicability(id, { entity_type: "component", entity_id: componentId }),
      api.listComplianceStatuses(id, "component", componentId),
    ]);
    setApplicability(applicabilityList);
    setComplianceStatuses(statusList);
  }

  async function refreshPlannedInvestment() {
    const id = orgId();
    if (!id) return;
    setPlannedInvestment(await api.getComponentPlannedInvestment(id, componentId));
  }

  // A new inspection changes both this component's own compliance
  // status AND its Planned Investment CONDITION_SIGNAL factor
  // (planned_investment.py reads the same Inspection table) — refresh
  // both rather than leaving the priority score stale after recording
  // one.
  async function onInspectionChanged() {
    await Promise.all([refreshApplicability(), refreshPlannedInvestment()]);
  }

  async function refreshChildren() {
    const id = orgId();
    if (!id) return;
    setChildren(await api.listComponentChildren(id, componentId));
  }

  async function refreshSpecifications() {
    const id = orgId();
    if (!id) return;
    const specList = await api.listSpecifications(id, {
      related_entity_type: "component",
      related_entity_id: componentId,
    });
    setSpecifications(specList);
    return specList;
  }

  async function refreshChanges() {
    const id = orgId();
    if (!id) return;
    // Filtered by related_entity_type/id (stable across a specification's
    // whole revision lineage), not specification_id — a change stays
    // visible in this component's history even after it's implemented
    // and the specification_id it targeted has since been superseded.
    setChanges(await api.listChangeControl(id, { related_entity_type: "component", related_entity_id: componentId }));
  }

  useEffect(() => {
    (async () => {
      const id = orgId();
      if (!id) {
        setLoadError("No organisation selected.");
        return;
      }
      try {
        const [comp, childList, typeList, specList, changeList, investment, documentList, requirementList, applicabilityList, statusList] =
          await Promise.all([
            api.getComponent(id, componentId),
            api.listComponentChildren(id, componentId),
            api.listComponentTypes(id),
            api.listSpecifications(id, { related_entity_type: "component", related_entity_id: componentId }),
            api.listChangeControl(id, { related_entity_type: "component", related_entity_id: componentId }),
            api.getComponentPlannedInvestment(id, componentId),
            api.listDocuments(id, { related_entity_type: "component", related_entity_id: componentId }),
            api.listComplianceRequirements(id, { current_only: true }),
            api.listApplicability(id, { entity_type: "component", entity_id: componentId }),
            api.listComplianceStatuses(id, "component", componentId),
          ]);
        setComponent(comp);
        setChildren(childList);
        setTypes(typeList);
        setSpecifications(specList);
        setChanges(changeList);
        setPlannedInvestment(investment);
        setDocuments(documentList);
        setRequirements(requirementList);
        setApplicability(applicabilityList);
        setComplianceStatuses(statusList);
        if (typeList[0]) setChildTypeId(typeList[0].id);
        if (specList[0]) setChangeSpecId(specList[0].id);
        if (requirementList[0]) setApplicabilityRequirementId(requirementList[0].id);
      } catch {
        setLoadError("Couldn't load this component.");
      }
    })();
  }, [componentId]);

  async function onAddChild() {
    const id = orgId();
    if (!id || !childTypeId) return;
    setSubmitting(true);
    setFormError(null);
    try {
      await api.createComponent(id, { component_type_id: childTypeId, parent_component_id: componentId });
      await refreshChildren();
    } catch {
      setFormError("Couldn't add that child component.");
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
        related_entity_type: "component",
        related_entity_id: componentId,
        title: specTitle.trim(),
      });
      setSpecTitle("");
      const specList = await refreshSpecifications();
      if (specList?.[0] && !changeSpecId) setChangeSpecId(specList[0].id);
    } catch {
      setSpecFormError("Couldn't add that specification.");
    } finally {
      setSpecSubmitting(false);
    }
  }

  async function onSubmitChange() {
    const id = orgId();
    if (!id || !changeSpecId || !changeProposedTitle.trim() || !changeReason.trim()) {
      setChangeFormError("Pick a specification, a proposed title, and a reason.");
      return;
    }
    setChangeSubmitting(true);
    setChangeFormError(null);
    try {
      await api.submitChangeControl(id, {
        specification_id: changeSpecId,
        proposed_value: { title: changeProposedTitle.trim() },
        reason: changeReason.trim(),
      });
      setChangeProposedTitle("");
      setChangeReason("");
      await refreshChanges();
    } catch {
      setChangeFormError("Couldn't submit that change.");
    } finally {
      setChangeSubmitting(false);
    }
  }

  async function onChangeTransition(changeId: string, action: "start-review" | "approve" | "reject" | "cancel" | "implement") {
    const id = orgId();
    if (!id) return;
    if (action === "start-review") await api.startChangeControlReview(id, changeId);
    else if (action === "approve") await api.approveChangeControl(id, changeId);
    else if (action === "reject") await api.rejectChangeControl(id, changeId);
    else if (action === "cancel") await api.cancelChangeControl(id, changeId);
    else if (action === "implement") await api.implementChangeControl(id, changeId);
    const [specList] = await Promise.all([refreshSpecifications(), refreshChanges()]);
    const activeSpec = specList?.find((s) => s.status === "ACTIVE");
    if (activeSpec) setChangeSpecId(activeSpec.id);
  }

  async function onUploadDocument() {
    const id = orgId();
    if (!id || !docFile || !docTitle.trim()) {
      setDocError("Give the evidence a title and choose a file first.");
      return;
    }
    setDocSubmitting(true);
    setDocError(null);
    try {
      await api.uploadDocument(id, docTitle.trim(), docType, docFile, {
        related_entity_type: "component",
        related_entity_id: componentId,
      });
      setDocTitle("");
      setDocFile(null);
      await refreshDocuments();
    } catch {
      setDocError("Upload failed.");
    } finally {
      setDocSubmitting(false);
    }
  }

  async function onDownloadDocument(doc: DocumentOut) {
    const id = orgId();
    if (!id) return;
    try {
      const blob = await api.downloadDocument(id, doc.id);
      triggerBlobDownload(blob, doc.title);
    } catch {
      setDocError("Download failed.");
    }
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
        entity_type: "component",
        entity_id: componentId,
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

  if (!component || !children || !specifications || !changes || !documents || !requirements || !applicability) {
    return <div style={{ color: "var(--text-secondary)" }}>Loading…</div>;
  }

  return (
    <div style={{ maxWidth: 720 }}>
      <Link href="/components" style={{ fontSize: 13, color: "var(--color-primary)" }}>
        ← Components
      </Link>

      <div style={{ display: "flex", alignItems: "center", gap: 12, margin: "8px 0 4px" }}>
        <h1 style={{ fontSize: 24, fontWeight: 700, margin: 0 }}>{component.component_type_name}</h1>
        <StatusBadge label={component.status} variant={statusVariant(component.status)} />
      </div>
      <p style={{ color: "var(--text-secondary)", marginBottom: 24, fontFamily: "monospace", fontSize: 13 }}>
        {component.component_reference}
      </p>

      <div
        style={{
          background: "var(--bg-card)",
          border: "1px solid var(--border-subtle)",
          borderRadius: "var(--radius-card)",
          padding: 20,
          marginBottom: 24,
          display: "grid",
          gridTemplateColumns: "repeat(2, 1fr)",
          gap: 16,
          fontSize: 13,
        }}
      >
        <div>
          <div style={{ color: "var(--text-secondary)", marginBottom: 2 }}>Manufacturer</div>
          <div>{component.manufacturer ?? "—"}</div>
        </div>
        <div>
          <div style={{ color: "var(--text-secondary)", marginBottom: 2 }}>Model</div>
          <div>{component.model ?? "—"}</div>
        </div>
        <div>
          <div style={{ color: "var(--text-secondary)", marginBottom: 2 }}>Serial number</div>
          <div>{component.serial_number ?? "—"}</div>
        </div>
        <div>
          <div style={{ color: "var(--text-secondary)", marginBottom: 2 }}>Installed</div>
          <div>{component.installation_date ?? "—"}</div>
        </div>
        <div>
          <div style={{ color: "var(--text-secondary)", marginBottom: 2 }}>Expected life</div>
          <div>{component.expected_life_years ? `${component.expected_life_years} years` : "—"}</div>
        </div>
        <div>
          <div style={{ color: "var(--text-secondary)", marginBottom: 2 }}>Indicative replacement</div>
          <div>
            {component.indicative_replacement_date ?? "—"}
            {component.indicative_replacement_date && (
              <span style={{ color: "var(--text-secondary)", fontSize: 11 }}> (indicative only)</span>
            )}
          </div>
        </div>
      </div>

      {plannedInvestment && (
        <div
          style={{
            background: "var(--bg-card)",
            border: "1px solid var(--border-subtle)",
            borderRadius: "var(--radius-card)",
            padding: 16,
            marginBottom: 24,
            fontSize: 13,
          }}
        >
          <div
            style={{ display: "flex", justifyContent: "space-between", alignItems: "center", cursor: "pointer" }}
            onClick={() => setInvestmentExpanded((v) => !v)}
          >
            <span style={{ fontWeight: 700 }}>Planned investment priority</span>
            <StatusBadge
              label={plannedInvestment.priority_score.toFixed(0)}
              variant={plannedInvestment.priority_score >= 70 ? "critical" : plannedInvestment.priority_score >= 40 ? "warning" : "success"}
            />
          </div>
          {investmentExpanded && (
            <ul style={{ listStyle: "none", padding: 0, margin: "10px 0 0", color: "var(--text-secondary)" }}>
              {plannedInvestment.factors.map((f) => (
                <li key={f.factor_code} style={{ padding: "3px 0" }}>
                  <strong>{f.label}</strong> (weight {f.weight}): {f.applicable ? f.detail : "not applicable — excluded"}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      <h2 style={{ fontSize: 16, fontWeight: 700, marginBottom: 12 }}>Specifications</h2>
      <div
        style={{
          background: "var(--bg-card)",
          border: "1px solid var(--border-subtle)",
          borderRadius: "var(--radius-card)",
          padding: 20,
          marginBottom: 16,
        }}
      >
        <div style={{ display: "grid", gap: 12, gridTemplateColumns: "2fr auto", alignItems: "end" }}>
          <div>
            <label htmlFor="component-spec-title" style={{ fontSize: 12, color: "var(--text-secondary)", display: "block", marginBottom: 4 }}>
              Title
            </label>
            <input
              id="component-spec-title"
              style={inputStyle}
              value={specTitle}
              onChange={(e) => setSpecTitle(e.target.value)}
              placeholder="e.g. Boiler installation specification"
            />
          </div>
          <button style={primaryBtn} onClick={onAddSpecification} disabled={specSubmitting}>
            {specSubmitting ? "Adding…" : "Add"}
          </button>
        </div>
        {specFormError && (
          <div style={{ color: "var(--color-critical)", fontSize: 13, marginTop: 10 }}>{specFormError}</div>
        )}
      </div>
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
              }}
            >
              <span>
                {s.title} <span style={{ color: "var(--text-secondary)" }}>rev {s.revision}</span>
              </span>
              <StatusBadge label={s.status} variant={specStatusVariant(s.status)} />
            </li>
          ))}
        </ul>
      )}

      <h2 style={{ fontSize: 16, fontWeight: 700, marginBottom: 12 }}>Evidence</h2>
      <div
        style={{
          background: "var(--bg-card)",
          border: "1px solid var(--border-subtle)",
          borderRadius: "var(--radius-card)",
          padding: 20,
          marginBottom: 16,
        }}
      >
        <div style={{ display: "grid", gap: 12, gridTemplateColumns: "1.5fr 1fr 1.5fr auto", alignItems: "end" }}>
          <div>
            <label htmlFor="evidence-title" style={{ fontSize: 12, color: "var(--text-secondary)", display: "block", marginBottom: 4 }}>
              Title
            </label>
            <input
              id="evidence-title"
              style={inputStyle}
              value={docTitle}
              onChange={(e) => setDocTitle(e.target.value)}
              placeholder="e.g. Boiler commissioning certificate"
            />
          </div>
          <div>
            <label htmlFor="evidence-type" style={{ fontSize: 12, color: "var(--text-secondary)", display: "block", marginBottom: 4 }}>
              Type
            </label>
            <select id="evidence-type" style={inputStyle} value={docType} onChange={(e) => setDocType(e.target.value)}>
              {DOCUMENT_TYPES.map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label htmlFor="evidence-file" style={{ fontSize: 12, color: "var(--text-secondary)", display: "block", marginBottom: 4 }}>
              File
            </label>
            <input id="evidence-file" style={inputStyle} type="file" onChange={(e) => setDocFile(e.target.files?.[0] ?? null)} />
          </div>
          <button style={primaryBtn} onClick={onUploadDocument} disabled={docSubmitting}>
            {docSubmitting ? "Uploading…" : "Upload"}
          </button>
        </div>
        {docError && <div style={{ color: "var(--color-critical)", fontSize: 13, marginTop: 10 }}>{docError}</div>}
      </div>
      {documents.length === 0 ? (
        <div style={{ color: "var(--text-secondary)", fontSize: 14, marginBottom: 24 }}>
          No evidence linked to this component yet.
        </div>
      ) : (
        <ul style={{ listStyle: "none", padding: 0, margin: "0 0 24px" }}>
          {documents.map((d) => (
            <li
              key={d.id}
              style={{
                padding: "10px 0",
                borderTop: "1px solid var(--border-subtle)",
                fontSize: 13,
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
              }}
            >
              <span>
                <span style={{ fontFamily: "monospace", color: "var(--text-secondary)", marginRight: 8 }}>
                  {d.document_reference}
                </span>
                {d.title} <span style={{ color: "var(--text-secondary)" }}>({d.document_type})</span>
              </span>
              <button style={{ ...primaryBtn, padding: "4px 10px", fontSize: 12 }} onClick={() => onDownloadDocument(d)}>
                Download
              </button>
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
            <label htmlFor="applicability-requirement" style={{ fontSize: 12, color: "var(--text-secondary)", display: "block", marginBottom: 4 }}>
              Requirement
            </label>
            <select
              id="applicability-requirement"
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
            <label htmlFor="applicability-basis" style={{ fontSize: 12, color: "var(--text-secondary)", display: "block", marginBottom: 4 }}>
              Basis
            </label>
            <input
              id="applicability-basis"
              style={inputStyle}
              value={applicabilityBasis}
              onChange={(e) => setApplicabilityBasis(e.target.value)}
              placeholder="e.g. Gas-fired appliance"
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
        <div style={{ color: "var(--text-secondary)", fontSize: 14, marginBottom: 24 }}>None applied to this component yet.</div>
      ) : (
        <ul style={{ listStyle: "none", padding: 0, margin: "0 0 24px" }}>
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
                      entityType="component"
                      entityId={componentId}
                      onChanged={onInspectionChanged}
                    />
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      )}

      <h2 style={{ fontSize: 16, fontWeight: 700, marginBottom: 12 }}>Change control</h2>
      <div
        style={{
          background: "var(--bg-card)",
          border: "1px solid var(--border-subtle)",
          borderRadius: "var(--radius-card)",
          padding: 20,
          marginBottom: 16,
        }}
      >
        <div style={{ display: "grid", gap: 12, gridTemplateColumns: "1.2fr 1.2fr 1.2fr auto", alignItems: "end" }}>
          <div>
            <label htmlFor="change-spec" style={{ fontSize: 12, color: "var(--text-secondary)", display: "block", marginBottom: 4 }}>
              Specification
            </label>
            <select id="change-spec" style={inputStyle} value={changeSpecId} onChange={(e) => setChangeSpecId(e.target.value)}>
              {specifications
                .filter((s) => s.status === "ACTIVE")
                .map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.title} (rev {s.revision})
                  </option>
                ))}
            </select>
          </div>
          <div>
            <label htmlFor="change-proposed-title" style={{ fontSize: 12, color: "var(--text-secondary)", display: "block", marginBottom: 4 }}>
              Proposed title
            </label>
            <input
              id="change-proposed-title"
              style={inputStyle}
              value={changeProposedTitle}
              onChange={(e) => setChangeProposedTitle(e.target.value)}
            />
          </div>
          <div>
            <label htmlFor="change-reason" style={{ fontSize: 12, color: "var(--text-secondary)", display: "block", marginBottom: 4 }}>
              Reason
            </label>
            <input id="change-reason" style={inputStyle} value={changeReason} onChange={(e) => setChangeReason(e.target.value)} />
          </div>
          <button style={primaryBtn} onClick={onSubmitChange} disabled={changeSubmitting}>
            {changeSubmitting ? "Submitting…" : "Propose"}
          </button>
        </div>
        {specifications.filter((s) => s.status === "ACTIVE").length === 0 && (
          <div style={{ color: "var(--text-secondary)", fontSize: 13, marginTop: 10 }}>
            Add a specification above before proposing a change to it.
          </div>
        )}
        {changeFormError && (
          <div style={{ color: "var(--color-critical)", fontSize: 13, marginTop: 10 }}>{changeFormError}</div>
        )}
      </div>
      {changes.length === 0 ? (
        <div style={{ color: "var(--text-secondary)", fontSize: 14, marginBottom: 24 }}>No change requests yet.</div>
      ) : (
        <ul style={{ listStyle: "none", padding: 0, margin: "0 0 24px" }}>
          {changes.map((c) => (
            <li
              key={c.id}
              style={{
                padding: "12px 0",
                borderTop: "1px solid var(--border-subtle)",
                fontSize: 13,
              }}
            >
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
                <span style={{ fontFamily: "monospace", color: "var(--text-secondary)" }}>{c.change_reference}</span>
                <StatusBadge label={c.status} variant={changeStatusVariant(c.status)} />
              </div>
              <div style={{ color: "var(--text-secondary)", marginBottom: 8 }}>{c.reason}</div>
              <div style={{ display: "flex", gap: 8 }}>
                {c.status === "PROPOSED" && (
                  <button
                    style={{ ...primaryBtn, padding: "4px 10px", fontSize: 12 }}
                    onClick={() => onChangeTransition(c.id, "start-review")}
                  >
                    Start review
                  </button>
                )}
                {(c.status === "PROPOSED" || c.status === "UNDER_REVIEW") && (
                  <button
                    style={{ ...primaryBtn, padding: "4px 10px", fontSize: 12 }}
                    onClick={() => onChangeTransition(c.id, "approve")}
                  >
                    Approve
                  </button>
                )}
                {(c.status === "PROPOSED" || c.status === "UNDER_REVIEW") && (
                  <button
                    style={{ ...primaryBtn, padding: "4px 10px", fontSize: 12, background: "var(--color-critical)" }}
                    onClick={() => onChangeTransition(c.id, "reject")}
                  >
                    Reject
                  </button>
                )}
                {c.status === "APPROVED" && (
                  <button
                    style={{ ...primaryBtn, padding: "4px 10px", fontSize: 12 }}
                    onClick={() => onChangeTransition(c.id, "implement")}
                  >
                    Implement
                  </button>
                )}
                {(c.status === "PROPOSED" || c.status === "UNDER_REVIEW" || c.status === "APPROVED") && (
                  <button
                    style={{ ...primaryBtn, padding: "4px 10px", fontSize: 12, background: "var(--text-secondary)" }}
                    onClick={() => onChangeTransition(c.id, "cancel")}
                  >
                    Cancel
                  </button>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}

      <h2 style={{ fontSize: 16, fontWeight: 700, marginBottom: 12 }}>Child components</h2>
      <div
        style={{
          background: "var(--bg-card)",
          border: "1px solid var(--border-subtle)",
          borderRadius: "var(--radius-card)",
          padding: 20,
          marginBottom: 16,
        }}
      >
        <div style={{ display: "grid", gap: 12, gridTemplateColumns: "2fr auto", alignItems: "end" }}>
          <div>
            <label htmlFor="child-component-type" style={{ fontSize: 12, color: "var(--text-secondary)", display: "block", marginBottom: 4 }}>
              Type
            </label>
            <select id="child-component-type" style={inputStyle} value={childTypeId} onChange={(e) => setChildTypeId(e.target.value)}>
              {types.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.name}
                </option>
              ))}
            </select>
          </div>
          <button style={primaryBtn} onClick={onAddChild} disabled={submitting}>
            {submitting ? "Adding…" : "Add child"}
          </button>
        </div>
        {formError && (
          <div style={{ color: "var(--color-critical)", fontSize: 13, marginTop: 10 }}>{formError}</div>
        )}
      </div>

      {children.length === 0 ? (
        <div style={{ color: "var(--text-secondary)", fontSize: 14 }}>No child components.</div>
      ) : (
        <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
          {children.map((c) => (
            <li
              key={c.id}
              style={{
                padding: "10px 0",
                borderTop: "1px solid var(--border-subtle)",
                fontSize: 13,
                display: "flex",
                justifyContent: "space-between",
              }}
            >
              <Link href={`/components/${c.id}`} style={{ color: "var(--color-primary)" }}>
                {c.component_reference}
              </Link>
              <span style={{ color: "var(--text-secondary)" }}>{c.component_type_name}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
