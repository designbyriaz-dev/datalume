"use client";

import { useEffect, useState } from "react";
import { StatusBadge } from "@/components/StatusBadge";
import {
  api,
  type Dataset,
  type DatasetDetail,
  type DocumentOut,
  type FieldSpec,
  type ImportResult,
  type UploadResponse,
} from "@/lib/api";

const SELECTED_ORG_KEY = "datalume.selectedOrganisationId";

const DOCUMENT_TYPES = ["EVIDENCE", "DRAWING", "SPECIFICATION", "CERTIFICATE", "REPORT", "PHOTOGRAPH", "OTHER"];

function datasetStatusVariant(status: string) {
  if (status === "IMPORTED") return "success" as const;
  if (status === "FAILED") return "critical" as const;
  return "neutral" as const;
}

function documentStatusVariant(status: string) {
  if (status === "ACTIVE") return "success" as const;
  if (status === "ARCHIVED") return "neutral" as const;
  return "neutral" as const;
}

// Defined outside the component — same reasoning as
// organisation/billing/page.tsx's redirectTo (react-hooks/immutability).
function triggerBlobDownload(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

const inputStyle: React.CSSProperties = {
  width: "100%",
  padding: "8px 10px",
  borderRadius: 6,
  border: "1px solid var(--border-subtle)",
  fontSize: 13,
};

const primaryBtn: React.CSSProperties = {
  padding: "8px 16px",
  borderRadius: 6,
  border: "none",
  background: "var(--color-primary)",
  color: "#fff",
  fontWeight: 600,
  fontSize: 13,
  cursor: "pointer",
};

const secondaryBtn: React.CSSProperties = {
  ...primaryBtn,
  background: "var(--bg-app)",
  color: "var(--text-primary)",
  border: "1px solid var(--border-subtle)",
};

export default function DataAndUploadsPage() {
  const [datasets, setDatasets] = useState<Dataset[] | null>(null);
  const [fieldDictionaries, setFieldDictionaries] = useState<Record<string, FieldSpec[]> | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [datasetType, setDatasetType] = useState("PROPERTIES");
  const [uploadName, setUploadName] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  const [uploadResult, setUploadResult] = useState<UploadResponse | null>(null);
  const [mapping, setMapping] = useState<Record<string, string | null>>({});
  const [datasetDetail, setDatasetDetail] = useState<DatasetDetail | null>(null);
  const [importResult, setImportResult] = useState<ImportResult | null>(null);

  const [documents, setDocuments] = useState<DocumentOut[] | null>(null);
  const [docTitle, setDocTitle] = useState("");
  const [docType, setDocType] = useState<string>(DOCUMENT_TYPES[0] ?? "EVIDENCE");
  const [docFile, setDocFile] = useState<File | null>(null);
  const [docSubmitting, setDocSubmitting] = useState(false);
  const [docError, setDocError] = useState<string | null>(null);

  function orgId(): string | null {
    return typeof window === "undefined" ? null : window.localStorage.getItem(SELECTED_ORG_KEY);
  }

  async function refreshDatasets() {
    const id = orgId();
    if (!id) return;
    setDatasets(await api.listDatasets(id));
  }

  async function refreshDocuments() {
    const id = orgId();
    if (!id) return;
    setDocuments(await api.listDocuments(id));
  }

  useEffect(() => {
    (async () => {
      const id = orgId();
      if (!id) {
        setLoadError("No organisation selected.");
        return;
      }
      try {
        const [dicts, list, docs] = await Promise.all([
          api.fieldDictionaries(),
          api.listDatasets(id),
          api.listDocuments(id),
        ]);
        setFieldDictionaries(dicts);
        setDatasets(list);
        setDocuments(docs);
        setDatasetType(Object.keys(dicts)[0] ?? "PROPERTIES");
      } catch {
        setLoadError("Couldn't load data & uploads.");
      }
    })();
  }, []);

  async function onUploadDocument() {
    const id = orgId();
    if (!id || !docFile || !docTitle.trim()) {
      setDocError("Give the document a title and choose a file first.");
      return;
    }
    setDocSubmitting(true);
    setDocError(null);
    try {
      await api.uploadDocument(id, docTitle.trim(), docType, docFile);
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

  function resetUploadFlow() {
    setUploadResult(null);
    setMapping({});
    setDatasetDetail(null);
    setImportResult(null);
    setUploadName("");
    setFile(null);
  }

  async function onSubmitUpload() {
    const id = orgId();
    if (!id || !file || !uploadName.trim()) {
      setFormError("Give the upload a name and choose a file first.");
      return;
    }
    setSubmitting(true);
    setFormError(null);
    try {
      const result = await api.uploadDataset(id, datasetType, uploadName.trim(), file);
      setUploadResult(result);
      setMapping(result.proposed_mapping);
      await refreshDatasets();
    } catch {
      setFormError("Upload failed — check the file is a valid CSV.");
    } finally {
      setSubmitting(false);
    }
  }

  async function onApplyMapping() {
    const id = orgId();
    if (!id || !uploadResult) return;
    setSubmitting(true);
    try {
      const detail = await api.applyMapping(id, uploadResult.dataset_id, mapping);
      setDatasetDetail(detail);
      await refreshDatasets();
    } catch {
      setFormError("Couldn't apply that mapping.");
    } finally {
      setSubmitting(false);
    }
  }

  async function onTriggerImport() {
    const id = orgId();
    if (!id || !uploadResult) return;
    setSubmitting(true);
    try {
      const result = await api.triggerImport(id, uploadResult.dataset_id);
      setImportResult(result);
      await refreshDatasets();
    } catch {
      setFormError("Import failed.");
    } finally {
      setSubmitting(false);
    }
  }

  if (loadError) {
    return <div style={{ color: "var(--text-secondary)" }}>{loadError}</div>;
  }

  return (
    <div style={{ maxWidth: 960 }}>
      <h1 style={{ fontSize: 24, fontWeight: 700, margin: 0, marginBottom: 4 }}>Data & Uploads</h1>
      <p style={{ color: "var(--text-secondary)", marginBottom: 24 }}>
        Upload → Validate → Understand → Map → Review → Import. CSV only for now — XLSX support is
        planned but not built yet.
      </p>

      <div
        style={{
          background: "var(--bg-card)",
          border: "1px solid var(--border-subtle)",
          borderRadius: "var(--radius-card)",
          padding: 20,
          marginBottom: 32,
        }}
      >
        <h2 style={{ fontSize: 16, fontWeight: 700, margin: 0, marginBottom: 16 }}>Upload a dataset</h2>

        {!uploadResult && fieldDictionaries && (
          <div style={{ display: "grid", gap: 12, maxWidth: 480 }}>
            <div>
              <label style={{ fontSize: 12, color: "var(--text-secondary)", display: "block", marginBottom: 4 }}>
                Dataset type
              </label>
              <select style={inputStyle} value={datasetType} onChange={(e) => setDatasetType(e.target.value)}>
                {Object.keys(fieldDictionaries).map((key) => (
                  <option key={key} value={key}>
                    {key}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label style={{ fontSize: 12, color: "var(--text-secondary)", display: "block", marginBottom: 4 }}>
                Name
              </label>
              <input
                style={inputStyle}
                value={uploadName}
                onChange={(e) => setUploadName(e.target.value)}
                placeholder="e.g. Stock condition export — Sept 2026"
              />
            </div>
            <div>
              <label style={{ fontSize: 12, color: "var(--text-secondary)", display: "block", marginBottom: 4 }}>
                CSV file
              </label>
              <input
                style={inputStyle}
                type="file"
                accept=".csv,text/csv"
                onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              />
            </div>
            {formError && <div style={{ color: "var(--color-critical)", fontSize: 13 }}>{formError}</div>}
            <div>
              <button style={primaryBtn} onClick={onSubmitUpload} disabled={submitting}>
                {submitting ? "Uploading…" : "Upload"}
              </button>
            </div>
          </div>
        )}

        {uploadResult && !datasetDetail && (
          <div>
            <p style={{ fontSize: 13, color: "var(--text-secondary)", marginBottom: 12 }}>
              {uploadResult.row_count} rows staged.{" "}
              {uploadResult.suggested_mapping_from_template
                ? "Mapping suggested from a saved template — review before applying."
                : "Review the proposed column mapping below."}
            </p>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13, marginBottom: 16 }}>
              <thead>
                <tr style={{ textAlign: "left", color: "var(--text-secondary)" }}>
                  <th style={{ padding: "6px 8px" }}>Column in file</th>
                  <th style={{ padding: "6px 8px" }}>Maps to</th>
                </tr>
              </thead>
              <tbody>
                {Object.keys(uploadResult.proposed_mapping).map((header) => (
                  <tr key={header} style={{ borderTop: "1px solid var(--border-subtle)" }}>
                    <td style={{ padding: "6px 8px" }}>{header}</td>
                    <td style={{ padding: "6px 8px" }}>
                      <select
                        style={inputStyle}
                        value={mapping[header] ?? ""}
                        onChange={(e) =>
                          setMapping((prev) => ({ ...prev, [header]: e.target.value || null }))
                        }
                      >
                        <option value="">— Not imported —</option>
                        {uploadResult.field_dictionary.map((f) => (
                          <option key={f.key} value={f.key}>
                            {f.label}
                            {f.required ? " (required)" : ""}
                          </option>
                        ))}
                      </select>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {formError && (
              <div style={{ color: "var(--color-critical)", fontSize: 13, marginBottom: 12 }}>{formError}</div>
            )}
            <div style={{ display: "flex", gap: 8 }}>
              <button style={primaryBtn} onClick={onApplyMapping} disabled={submitting}>
                {submitting ? "Applying…" : "Apply mapping"}
              </button>
              <button style={secondaryBtn} onClick={resetUploadFlow}>
                Cancel
              </button>
            </div>
          </div>
        )}

        {datasetDetail && !importResult && (
          <div>
            <p style={{ fontSize: 13, marginBottom: 12 }}>
              Mapping applied.{" "}
              {Object.entries(datasetDetail.row_status_counts)
                .map(([s, n]) => `${n} ${s.toLowerCase()}`)
                .join(", ")}
              .
            </p>
            {formError && (
              <div style={{ color: "var(--color-critical)", fontSize: 13, marginBottom: 12 }}>{formError}</div>
            )}
            <div style={{ display: "flex", gap: 8 }}>
              <button style={primaryBtn} onClick={onTriggerImport} disabled={submitting}>
                {submitting ? "Importing…" : "Start import"}
              </button>
              <button style={secondaryBtn} onClick={resetUploadFlow}>
                Cancel
              </button>
            </div>
          </div>
        )}

        {importResult && (
          <div>
            <p style={{ fontSize: 13, marginBottom: 4 }}>
              {importResult.rows_processed} rows processed, {importResult.entities_created} entities created.
            </p>
            {!importResult.importer_registered && (
              <p style={{ fontSize: 13, color: "var(--text-secondary)", marginBottom: 12 }}>
                No domain model exists yet for &ldquo;{datasetType}&rdquo; — rows are validated and staged,
                but nothing was created. This dataset type&rsquo;s canonical table lands in a later sprint.
              </p>
            )}
            <button style={secondaryBtn} onClick={resetUploadFlow}>
              Upload another
            </button>
          </div>
        )}
      </div>

      <h2 style={{ fontSize: 16, fontWeight: 700, marginBottom: 12 }}>Datasets</h2>
      {datasets === null ? (
        <div style={{ color: "var(--text-secondary)" }}>Loading…</div>
      ) : datasets.length === 0 ? (
        <div style={{ color: "var(--text-secondary)", fontSize: 14 }}>No datasets uploaded yet.</div>
      ) : (
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
          <thead>
            <tr style={{ textAlign: "left", color: "var(--text-secondary)" }}>
              <th style={{ padding: "8px" }}>Name</th>
              <th style={{ padding: "8px" }}>Type</th>
              <th style={{ padding: "8px" }}>Rows</th>
              <th style={{ padding: "8px" }}>Status</th>
              <th style={{ padding: "8px" }}>Uploaded</th>
              <th style={{ padding: "8px" }}>Source file</th>
            </tr>
          </thead>
          <tbody>
            {datasets.map((d) => (
              <tr key={d.id} style={{ borderTop: "1px solid var(--border-subtle)" }}>
                <td style={{ padding: "8px" }}>{d.name}</td>
                <td style={{ padding: "8px" }}>{d.dataset_type}</td>
                <td style={{ padding: "8px" }}>{d.row_count}</td>
                <td style={{ padding: "8px" }}>
                  <StatusBadge label={d.status} variant={datasetStatusVariant(d.status)} />
                </td>
                <td style={{ padding: "8px", color: "var(--text-secondary)" }}>
                  {new Date(d.uploaded_at).toLocaleString()}
                </td>
                <td style={{ padding: "8px" }}>
                  {d.source_file_document_id ? (
                    <button
                      style={{ ...secondaryBtn, padding: "4px 10px" }}
                      onClick={async () => {
                        const id = orgId();
                        if (!id || !d.source_file_document_id) return;
                        const blob = await api.downloadDocument(id, d.source_file_document_id);
                        triggerBlobDownload(blob, d.name);
                      }}
                    >
                      Download
                    </button>
                  ) : (
                    <span style={{ color: "var(--text-secondary)" }}>—</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <h2 style={{ fontSize: 16, fontWeight: 700, margin: "32px 0 12px" }}>Documents</h2>
      <div
        style={{
          background: "var(--bg-card)",
          border: "1px solid var(--border-subtle)",
          borderRadius: "var(--radius-card)",
          padding: 20,
          marginBottom: 24,
        }}
      >
        <div style={{ display: "grid", gap: 12, maxWidth: 480 }}>
          <div>
            <label style={{ fontSize: 12, color: "var(--text-secondary)", display: "block", marginBottom: 4 }}>
              Title
            </label>
            <input
              style={inputStyle}
              value={docTitle}
              onChange={(e) => setDocTitle(e.target.value)}
              placeholder="e.g. Fire door installation certificate — Block A"
            />
          </div>
          <div>
            <label style={{ fontSize: 12, color: "var(--text-secondary)", display: "block", marginBottom: 4 }}>
              Document type
            </label>
            <select style={inputStyle} value={docType} onChange={(e) => setDocType(e.target.value)}>
              {DOCUMENT_TYPES.map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label style={{ fontSize: 12, color: "var(--text-secondary)", display: "block", marginBottom: 4 }}>
              File
            </label>
            <input style={inputStyle} type="file" onChange={(e) => setDocFile(e.target.files?.[0] ?? null)} />
          </div>
          {docError && <div style={{ color: "var(--color-critical)", fontSize: 13 }}>{docError}</div>}
          <div>
            <button style={primaryBtn} onClick={onUploadDocument} disabled={docSubmitting}>
              {docSubmitting ? "Uploading…" : "Upload document"}
            </button>
          </div>
        </div>
      </div>

      {documents === null ? (
        <div style={{ color: "var(--text-secondary)" }}>Loading…</div>
      ) : documents.length === 0 ? (
        <div style={{ color: "var(--text-secondary)", fontSize: 14 }}>No documents uploaded yet.</div>
      ) : (
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
          <thead>
            <tr style={{ textAlign: "left", color: "var(--text-secondary)" }}>
              <th style={{ padding: "8px" }}>Reference</th>
              <th style={{ padding: "8px" }}>Title</th>
              <th style={{ padding: "8px" }}>Type</th>
              <th style={{ padding: "8px" }}>Revision</th>
              <th style={{ padding: "8px" }}>Status</th>
              <th style={{ padding: "8px" }}></th>
            </tr>
          </thead>
          <tbody>
            {documents.map((doc) => (
              <tr key={doc.id} style={{ borderTop: "1px solid var(--border-subtle)" }}>
                <td style={{ padding: "8px", fontFamily: "monospace" }}>{doc.document_reference}</td>
                <td style={{ padding: "8px" }}>{doc.title}</td>
                <td style={{ padding: "8px" }}>{doc.document_type}</td>
                <td style={{ padding: "8px" }}>{doc.revision}</td>
                <td style={{ padding: "8px" }}>
                  <StatusBadge label={doc.status} variant={documentStatusVariant(doc.status)} />
                </td>
                <td style={{ padding: "8px" }}>
                  <button style={{ ...secondaryBtn, padding: "4px 10px" }} onClick={() => onDownloadDocument(doc)}>
                    Download
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
