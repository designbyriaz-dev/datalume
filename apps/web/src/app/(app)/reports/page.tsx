"use client";

import { useEffect, useRef, useState } from "react";
import { StatusBadge } from "@/components/StatusBadge";
import { inputStyle, primaryBtn, secondaryBtn } from "@/components/formStyles";
import {
  api,
  ApiError,
  REPORT_FORMATS,
  REPORT_TYPES,
  type BuildingOut,
  type PropertyOut,
  type ReportFormatValue,
  type ReportJobOut,
  type ReportType,
} from "@/lib/api";

const SELECTED_ORG_KEY = "datalume.selectedOrganisationId";

const BOARD_LEVEL_TYPES: ReportType[] = ["BOARD_ASSURANCE", "COMPLIANCE_EXECUTIVE_SUMMARY"];
const NEEDS_PERIOD: ReportType[] = ["COMMERCIAL_PORTFOLIO"];

function triggerBlobDownload(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

function statusVariant(status: ReportJobOut["status"]) {
  if (status === "READY") return "success" as const;
  if (status === "FAILED") return "critical" as const;
  return "neutral" as const;
}

function defaultPeriod() {
  const today = new Date();
  const start = new Date(today.getFullYear(), today.getMonth(), 1);
  return { start: start.toISOString().slice(0, 10), end: today.toISOString().slice(0, 10) };
}

export default function ReportsPage() {
  const [reportType, setReportType] = useState<ReportType>("DEVELOPMENT_SUMMARY");
  const [format, setFormat] = useState<ReportFormatValue>("PDF");
  const [buildings, setBuildings] = useState<BuildingOut[]>([]);
  const [properties, setProperties] = useState<PropertyOut[]>([]);
  const [buildingId, setBuildingId] = useState("");
  const [propertyId, setPropertyId] = useState("");
  const [period] = useState(defaultPeriod());
  const [jobs, setJobs] = useState<ReportJobOut[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  function orgId(): string | null {
    return typeof window === "undefined" ? null : window.localStorage.getItem(SELECTED_ORG_KEY);
  }

  async function refreshJobs() {
    const id = orgId();
    if (!id) return;
    try {
      setJobs(await api.listReports(id));
    } catch {
      setLoadError("Couldn't load reports.");
    }
  }

  useEffect(() => {
    (async () => {
      const id = orgId();
      if (!id) {
        setLoadError("No organisation selected.");
        return;
      }
      try {
        const [b, p] = await Promise.all([api.listBuildings(id), api.listProperties(id)]);
        setBuildings(b);
        setProperties(p);
        await refreshJobs();
      } catch {
        setLoadError("Couldn't load report data.");
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Report generation runs on the worker's poll loop (every 5s), not in
  // the request/response cycle — architecture §4. Poll job status while
  // anything is still PENDING/RUNNING, same "grounded, not guessed"
  // honesty as everywhere else: the UI shows the real async state, not
  // a fake instant result.
  const hasInFlight = jobs.some((j) => j.status === "PENDING" || j.status === "RUNNING");
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  useEffect(() => {
    if (hasInFlight && !pollRef.current) {
      pollRef.current = setInterval(refreshJobs, 3000);
    } else if (!hasInFlight && pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
    return () => {
      if (pollRef.current) {
        clearInterval(pollRef.current);
        pollRef.current = null;
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hasInFlight]);

  async function onGenerate() {
    const id = orgId();
    if (!id) return;
    setSubmitting(true);
    setError(null);
    try {
      await api.requestReport(id, {
        report_type: reportType,
        format,
        building_id: BOARD_LEVEL_TYPES.includes(reportType) && buildingId ? buildingId : undefined,
        property_id: BOARD_LEVEL_TYPES.includes(reportType) && propertyId ? propertyId : undefined,
        period_start: NEEDS_PERIOD.includes(reportType) ? period.start : undefined,
        period_end: NEEDS_PERIOD.includes(reportType) ? period.end : undefined,
      });
      await refreshJobs();
    } catch (err) {
      setError(
        err instanceof ApiError && err.status === 403
          ? "You don't have permission to generate this report."
          : "Couldn't request that report.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  async function onDownload(job: ReportJobOut) {
    const id = orgId();
    if (!id) return;
    try {
      const blob = await api.downloadReport(id, job.id);
      triggerBlobDownload(blob, `${job.report_type.toLowerCase()}.${job.format.toLowerCase()}`);
    } catch {
      setError("Download failed.");
    }
  }

  if (loadError) {
    return <div style={{ color: "var(--text-secondary)" }}>{loadError}</div>;
  }

  return (
    <div style={{ maxWidth: 860 }}>
      <h1 style={{ fontSize: 24, fontWeight: 700, margin: 0, marginBottom: 4 }}>Reports</h1>
      <p style={{ color: "var(--text-secondary)", marginBottom: 24 }}>
        Every report is built from the same computed-at-read-time data DataLume shows you elsewhere — nothing is
        recalculated just for export. Generation runs in the background; this page updates automatically.
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
        <div style={{ display: "grid", gap: 12, gridTemplateColumns: "1.5fr 1fr", marginBottom: 12 }}>
          <div>
            <label htmlFor="report-type" style={{ fontSize: 12, color: "var(--text-secondary)", display: "block", marginBottom: 4 }}>Report</label>
            <select id="report-type" style={inputStyle} value={reportType} onChange={(e) => setReportType(e.target.value as ReportType)}>
              {REPORT_TYPES.map((t) => (
                <option key={t.value} value={t.value}>
                  {t.label}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label htmlFor="report-format" style={{ fontSize: 12, color: "var(--text-secondary)", display: "block", marginBottom: 4 }}>Format</label>
            <select id="report-format" style={inputStyle} value={format} onChange={(e) => setFormat(e.target.value as ReportFormatValue)}>
              {REPORT_FORMATS.map((f) => (
                <option key={f} value={f}>
                  {f}
                </option>
              ))}
            </select>
          </div>
        </div>

        {BOARD_LEVEL_TYPES.includes(reportType) && (
          <div style={{ display: "grid", gap: 12, gridTemplateColumns: "1fr 1fr", marginBottom: 12 }}>
            <div>
              <label htmlFor="report-building" style={{ fontSize: 12, color: "var(--text-secondary)", display: "block", marginBottom: 4 }}>
                Building (optional — narrows scope)
              </label>
              <select id="report-building" style={inputStyle} value={buildingId} onChange={(e) => setBuildingId(e.target.value)}>
                <option value="">Whole portfolio</option>
                {buildings.map((b) => (
                  <option key={b.id} value={b.id}>
                    {b.name || b.building_reference}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label htmlFor="report-property" style={{ fontSize: 12, color: "var(--text-secondary)", display: "block", marginBottom: 4 }}>
                Property (optional — narrows scope)
              </label>
              <select id="report-property" style={inputStyle} value={propertyId} onChange={(e) => setPropertyId(e.target.value)}>
                <option value="">Whole portfolio</option>
                {properties.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.address}
                  </option>
                ))}
              </select>
            </div>
          </div>
        )}
        {NEEDS_PERIOD.includes(reportType) && (
          <div style={{ fontSize: 12, color: "var(--text-secondary)", marginBottom: 12 }}>
            Collection rate period: {period.start} to {period.end} (current month to date)
          </div>
        )}

        <button style={primaryBtn} onClick={onGenerate} disabled={submitting}>
          {submitting ? "Requesting…" : "Generate report"}
        </button>
        {error && <div style={{ color: "var(--color-critical)", fontSize: 13, marginTop: 10 }}>{error}</div>}
      </div>

      <h2 style={{ fontSize: 16, fontWeight: 600, marginBottom: 10 }}>Recent reports</h2>
      {jobs.length === 0 ? (
        <div style={{ color: "var(--text-secondary)", fontSize: 14 }}>No reports requested yet.</div>
      ) : (
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
          <thead>
            <tr style={{ textAlign: "left", color: "var(--text-secondary)", fontSize: 12 }}>
              <th style={{ padding: "6px 8px" }}>Report</th>
              <th style={{ padding: "6px 8px" }}>Format</th>
              <th style={{ padding: "6px 8px" }}>Requested</th>
              <th style={{ padding: "6px 8px" }}>Status</th>
              <th style={{ padding: "6px 8px" }} />
            </tr>
          </thead>
          <tbody>
            {jobs.map((job) => (
              <tr key={job.id} style={{ borderTop: "1px solid var(--border-subtle)" }}>
                <td style={{ padding: "8px" }}>{REPORT_TYPES.find((t) => t.value === job.report_type)?.label ?? job.report_type}</td>
                <td style={{ padding: "8px" }}>{job.format}</td>
                <td style={{ padding: "8px" }}>{new Date(job.requested_at).toLocaleString()}</td>
                <td style={{ padding: "8px" }}>
                  <StatusBadge label={job.status} variant={statusVariant(job.status)} />
                  {job.status === "FAILED" && job.error_message && (
                    <div style={{ color: "var(--color-critical)", fontSize: 11, marginTop: 2 }}>{job.error_message}</div>
                  )}
                </td>
                <td style={{ padding: "8px" }}>
                  {job.status === "READY" ? (
                    <button style={{ ...secondaryBtn, padding: "3px 10px", fontSize: 12 }} onClick={() => onDownload(job)}>
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
    </div>
  );
}
