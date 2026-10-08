"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { StatusBadge } from "@/components/StatusBadge";
import { inputStyle, primaryBtn } from "@/components/formStyles";
import {
  api,
  type DevelopmentHierarchy,
  type DevelopmentOut,
  type DocumentOut,
  type HandoverReadiness,
  type HandoverRecordOut,
} from "@/lib/api";

const SELECTED_ORG_KEY = "datalume.selectedOrganisationId";

const DOCUMENT_TYPES = ["O&M", "DRAWING", "EVIDENCE", "CERTIFICATE", "REPORT", "OTHER"];

// Defined outside the component — same reasoning as ComponentDetailClient.tsx's
// own copy of this helper (react-hooks/immutability).
function triggerBlobDownload(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

function statusVariant(status: string) {
  if (status === "OPERATIONAL" || status === "COMPLETED") return "success" as const;
  if (status === "CANCELLED") return "critical" as const;
  return "neutral" as const;
}

export function DevelopmentDetailClient({ developmentId }: { developmentId: string }) {
  const [development, setDevelopment] = useState<DevelopmentOut | null>(null);
  const [hierarchy, setHierarchy] = useState<DevelopmentHierarchy | null>(null);
  const [readiness, setReadiness] = useState<HandoverReadiness | null>(null);
  const [records, setRecords] = useState<HandoverRecordOut[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [buildingName, setBuildingName] = useState("");
  const [storeys, setStoreys] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  const [overrideReason, setOverrideReason] = useState("");
  const [authorising, setAuthorising] = useState(false);
  const [authoriseError, setAuthoriseError] = useState<string | null>(null);

  const [documents, setDocuments] = useState<DocumentOut[] | null>(null);
  const [docTitle, setDocTitle] = useState("");
  const [docType, setDocType] = useState<string>(DOCUMENT_TYPES[0] ?? "O&M");
  const [docFile, setDocFile] = useState<File | null>(null);
  const [docSubmitting, setDocSubmitting] = useState(false);
  const [docError, setDocError] = useState<string | null>(null);

  function orgId(): string | null {
    return typeof window === "undefined" ? null : window.localStorage.getItem(SELECTED_ORG_KEY);
  }

  async function refreshHierarchy() {
    const id = orgId();
    if (!id) return;
    setHierarchy(await api.getDevelopmentHierarchy(id, developmentId));
  }

  async function refreshDocuments() {
    const id = orgId();
    if (!id) return;
    setDocuments(await api.listDocuments(id, { related_entity_type: "development", related_entity_id: developmentId }));
  }

  async function refreshHandover() {
    const id = orgId();
    if (!id) return;
    const [readinessResult, recordList] = await Promise.all([
      api.getHandoverReadiness(id, developmentId),
      api.listHandoverRecords(id, developmentId),
    ]);
    setReadiness(readinessResult);
    setRecords(recordList);
  }

  useEffect(() => {
    (async () => {
      const id = orgId();
      if (!id) {
        setLoadError("No organisation selected.");
        return;
      }
      try {
        const [dev, tree, readinessResult, recordList, documentList] = await Promise.all([
          api.getDevelopment(id, developmentId),
          api.getDevelopmentHierarchy(id, developmentId),
          api.getHandoverReadiness(id, developmentId),
          api.listHandoverRecords(id, developmentId),
          api.listDocuments(id, { related_entity_type: "development", related_entity_id: developmentId }),
        ]);
        setDevelopment(dev);
        setHierarchy(tree);
        setReadiness(readinessResult);
        setRecords(recordList);
        setDocuments(documentList);
      } catch {
        setLoadError("Couldn't load this development.");
      }
    })();
  }, [developmentId]);

  async function onAddBuilding() {
    const id = orgId();
    if (!id || !buildingName.trim()) {
      setFormError("Give the building a name first.");
      return;
    }
    setSubmitting(true);
    setFormError(null);
    try {
      await api.createBuilding(id, {
        name: buildingName.trim(),
        development_id: developmentId,
        storeys: storeys ? Number(storeys) : undefined,
      });
      setBuildingName("");
      setStoreys("");
      await refreshHierarchy();
    } catch {
      setFormError("Couldn't add that building.");
    } finally {
      setSubmitting(false);
    }
  }

  async function onAuthoriseHandover() {
    const id = orgId();
    if (!id) return;
    setAuthorising(true);
    setAuthoriseError(null);
    try {
      await api.authoriseHandover(id, developmentId, overrideReason.trim() || undefined);
      setOverrideReason("");
      await refreshHandover();
    } catch (err) {
      setAuthoriseError(
        err instanceof Error && err.message ? err.message : "Couldn't authorise handover.",
      );
    } finally {
      setAuthorising(false);
    }
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
        related_entity_type: "development",
        related_entity_id: developmentId,
      });
      setDocTitle("");
      setDocFile(null);
      // Evidence against this development can be exactly what
      // OM_DOCUMENTATION (and, once backed by real data, other checks)
      // was waiting on — refresh readiness alongside the document list
      // so the score reflects it without requiring a full page reload.
      await Promise.all([refreshDocuments(), refreshHandover()]);
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

  if (loadError) {
    return <div style={{ color: "var(--text-secondary)" }}>{loadError}</div>;
  }

  if (!development || !hierarchy || !readiness || !records || !documents) {
    return <div style={{ color: "var(--text-secondary)" }}>Loading…</div>;
  }

  return (
    <div style={{ maxWidth: 720 }}>
      <Link href="/developments" style={{ fontSize: 13, color: "var(--color-primary)" }}>
        ← Developments
      </Link>

      <div style={{ display: "flex", alignItems: "center", gap: 12, margin: "8px 0 4px" }}>
        <h1 style={{ fontSize: 24, fontWeight: 700, margin: 0 }}>{development.name}</h1>
        <StatusBadge label={development.status} variant={statusVariant(development.status)} />
      </div>
      <p style={{ color: "var(--text-secondary)", marginBottom: 24, fontFamily: "monospace", fontSize: 13 }}>
        {development.development_reference}
        {development.planning_reference && <> · Planning: {development.planning_reference}</>}
      </p>

      {hierarchy.unbuilt_property_count > 0 && (
        <p style={{ fontSize: 13, color: "var(--text-secondary)", marginBottom: 16 }}>
          {hierarchy.unbuilt_property_count} propert{hierarchy.unbuilt_property_count === 1 ? "y" : "ies"} linked
          directly to this development, not yet assigned to a building.
        </p>
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
        <h2 style={{ fontSize: 16, fontWeight: 700, margin: 0, marginBottom: 16 }}>Add a building</h2>
        <div style={{ display: "grid", gap: 12, gridTemplateColumns: "2fr 1fr auto", alignItems: "end" }}>
          <div>
            <label htmlFor="dev-building-name" style={{ fontSize: 12, color: "var(--text-secondary)", display: "block", marginBottom: 4 }}>
              Name
            </label>
            <input
              id="dev-building-name"
              style={inputStyle}
              value={buildingName}
              onChange={(e) => setBuildingName(e.target.value)}
              placeholder="e.g. Block A"
            />
          </div>
          <div>
            <label htmlFor="dev-building-storeys" style={{ fontSize: 12, color: "var(--text-secondary)", display: "block", marginBottom: 4 }}>
              Storeys
            </label>
            <input id="dev-building-storeys" style={inputStyle} value={storeys} onChange={(e) => setStoreys(e.target.value)} />
          </div>
          <button style={primaryBtn} onClick={onAddBuilding} disabled={submitting}>
            {submitting ? "Adding…" : "Add"}
          </button>
        </div>
        {formError && <div style={{ color: "var(--color-critical)", fontSize: 13, marginTop: 10 }}>{formError}</div>}
      </div>

      <h2 style={{ fontSize: 16, fontWeight: 700, marginBottom: 12 }}>Buildings</h2>
      {hierarchy.buildings.length === 0 ? (
        <div style={{ color: "var(--text-secondary)", fontSize: 14 }}>No buildings yet.</div>
      ) : (
        <div style={{ display: "grid", gap: 12 }}>
          {hierarchy.buildings.map((b) => {
            const floorPropertyTotal = b.floors.reduce((sum, f) => sum + f.property_count, 0);
            const total = floorPropertyTotal + b.unfloored_property_count;
            return (
              <div
                key={b.id}
                style={{
                  background: "var(--bg-card)",
                  border: "1px solid var(--border-subtle)",
                  borderRadius: "var(--radius-card)",
                  padding: 16,
                }}
              >
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <div>
                    <Link href={`/buildings/${b.id}`} style={{ fontWeight: 600, color: "var(--color-primary)" }}>
                      {b.name}
                    </Link>
                    <span style={{ color: "var(--text-secondary)", fontSize: 12, marginLeft: 8 }}>
                      {b.building_reference}
                    </span>
                  </div>
                  <StatusBadge label={b.status} variant={statusVariant(b.status)} />
                </div>
                <div style={{ fontSize: 13, color: "var(--text-secondary)", marginTop: 8 }}>
                  {b.floors.length} floor{b.floors.length === 1 ? "" : "s"} · {total} propert
                  {total === 1 ? "y" : "ies"}
                  {b.unfloored_property_count > 0 && ` (${b.unfloored_property_count} unassigned to a floor)`}
                </div>
              </div>
            );
          })}
        </div>
      )}

      <h2 style={{ fontSize: 16, fontWeight: 700, marginBottom: 12, marginTop: 24 }}>Evidence</h2>
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
            <label htmlFor="development-evidence-title" style={{ fontSize: 12, color: "var(--text-secondary)", display: "block", marginBottom: 4 }}>
              Title
            </label>
            <input
              id="development-evidence-title"
              style={inputStyle}
              value={docTitle}
              onChange={(e) => setDocTitle(e.target.value)}
              placeholder="e.g. Operation & Maintenance manual"
            />
          </div>
          <div>
            <label htmlFor="development-evidence-type" style={{ fontSize: 12, color: "var(--text-secondary)", display: "block", marginBottom: 4 }}>
              Type
            </label>
            <select id="development-evidence-type" style={inputStyle} value={docType} onChange={(e) => setDocType(e.target.value)}>
              {DOCUMENT_TYPES.map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label htmlFor="development-evidence-file" style={{ fontSize: 12, color: "var(--text-secondary)", display: "block", marginBottom: 4 }}>
              File
            </label>
            <input id="development-evidence-file" style={inputStyle} type="file" onChange={(e) => setDocFile(e.target.files?.[0] ?? null)} />
          </div>
          <button style={primaryBtn} onClick={onUploadDocument} disabled={docSubmitting}>
            {docSubmitting ? "Uploading…" : "Upload"}
          </button>
        </div>
        {docError && <div style={{ color: "var(--color-critical)", fontSize: 13, marginTop: 10 }}>{docError}</div>}
      </div>
      {documents.length === 0 ? (
        <div style={{ color: "var(--text-secondary)", fontSize: 14, marginBottom: 24 }}>
          No evidence linked to this development yet.
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

      <h2 style={{ fontSize: 16, fontWeight: 700, marginBottom: 4, marginTop: 24 }}>Handover readiness</h2>
      <p style={{ color: "var(--text-secondary)", fontSize: 13, marginBottom: 16 }}>
        Only properties currently marked READY_FOR_HANDOVER are transitioned by authorising handover — everything
        else in this development is left untouched.
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
        <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 12 }}>
          <span style={{ fontSize: 28, fontWeight: 700 }}>{readiness.score_pct}%</span>
          <StatusBadge
            label={readiness.ready ? "Ready" : "Not ready"}
            variant={readiness.ready ? "success" : "warning"}
          />
        </div>
        {readiness.missing.length > 0 && (
          <div style={{ fontSize: 13, marginBottom: 16 }}>
            <div style={{ color: "var(--text-secondary)", marginBottom: 4 }}>Missing:</div>
            <ul style={{ margin: 0, paddingLeft: 18 }}>
              {readiness.missing.map((item, i) => (
                <li key={i}>{item}</li>
              ))}
            </ul>
          </div>
        )}
        <div style={{ display: "grid", gap: 12, gridTemplateColumns: "2fr auto", alignItems: "end" }}>
          <div>
            <label htmlFor="handover-override-reason" style={{ fontSize: 12, color: "var(--text-secondary)", display: "block", marginBottom: 4 }}>
              Override reason (only needed below {readiness.threshold_pct}%)
            </label>
            <input
              id="handover-override-reason"
              style={inputStyle}
              value={overrideReason}
              onChange={(e) => setOverrideReason(e.target.value)}
              placeholder="e.g. Client accepted risk on outstanding O&M documentation"
            />
          </div>
          <button style={primaryBtn} onClick={onAuthoriseHandover} disabled={authorising}>
            {authorising ? "Authorising…" : "Authorise handover"}
          </button>
        </div>
        {authoriseError && (
          <div style={{ color: "var(--color-critical)", fontSize: 13, marginTop: 10 }}>{authoriseError}</div>
        )}
      </div>

      <h2 style={{ fontSize: 16, fontWeight: 700, marginBottom: 12 }}>Handover history</h2>
      {records.length === 0 ? (
        <div style={{ color: "var(--text-secondary)", fontSize: 14 }}>No properties handed over yet.</div>
      ) : (
        <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
          {records.map((r) => (
            <li key={r.id} style={{ padding: "10px 0", borderTop: "1px solid var(--border-subtle)", fontSize: 13 }}>
              <div style={{ display: "flex", justifyContent: "space-between" }}>
                <Link href={`/properties/${r.property_id}`} style={{ color: "var(--color-primary)" }}>
                  Property {r.property_id.slice(0, 8)}
                </Link>
                <span style={{ color: "var(--text-secondary)" }}>{r.readiness_score_pct}% at handover</span>
              </div>
              {r.override_reason && (
                <div style={{ color: "var(--text-secondary)", marginTop: 4 }}>Override: {r.override_reason}</div>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
