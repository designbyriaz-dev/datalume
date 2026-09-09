"use client";

import { useEffect, useState } from "react";
import { StatusBadge } from "@/components/StatusBadge";
import { inputStyle, primaryBtn } from "@/components/formStyles";
import { api, ApiError, type BoardAssuranceReport, type ComplianceDomainOut, type ComplianceRequirementOut } from "@/lib/api";

const SELECTED_ORG_KEY = "datalume.selectedOrganisationId";

const ASSURANCE_STATUS_ORDER = [
  "OVERDUE_ACTION",
  "OVERDUE",
  "MISSING_EVIDENCE",
  "OPEN_ACTION",
  "NEEDS_REVIEW",
  "DUE_SOON",
  "EXPIRED",
  "UNKNOWN",
  "CURRENT",
  "NOT_APPLICABLE",
];

function assuranceStatusVariant(statusCode: string) {
  if (statusCode === "CURRENT") return "success" as const;
  if (["OVERDUE", "OVERDUE_ACTION", "MISSING_EVIDENCE"].includes(statusCode)) return "critical" as const;
  if (["DUE_SOON", "NEEDS_REVIEW", "OPEN_ACTION", "EXPIRED"].includes(statusCode)) return "warning" as const;
  return "neutral" as const;
}

function BoardAssurance() {
  const [report, setReport] = useState<BoardAssuranceReport | null>(null);
  const [error, setError] = useState<"forbidden" | "other" | null>(null);

  useEffect(() => {
    (async () => {
      const id = typeof window === "undefined" ? null : window.localStorage.getItem(SELECTED_ORG_KEY);
      if (!id) return;
      try {
        setReport(await api.getAssuranceReport(id));
      } catch (err) {
        setError(err instanceof ApiError && err.status === 403 ? "forbidden" : "other");
      }
    })();
  }, []);

  if (error === "forbidden") return null; // Board Assurance is reports.board-gated — quietly absent for other roles.
  if (error === "other") {
    return <div style={{ color: "var(--text-secondary)", fontSize: 13, marginBottom: 24 }}>Couldn&rsquo;t load the Board Assurance report.</div>;
  }
  if (!report) return <div style={{ color: "var(--text-secondary)", fontSize: 13, marginBottom: 24 }}>Loading Board Assurance report…</div>;

  return (
    <div style={{ marginBottom: 24 }}>
      <h2 style={{ fontSize: 16, fontWeight: 700, marginBottom: 4 }}>Board Assurance</h2>
      <p style={{ color: "var(--text-secondary)", fontSize: 13, marginBottom: 12 }}>
        A read-only rollup of computed compliance status, open/overdue actions, and hazard status — never a scored
        or narrated summary, always a count of what status_engine.py already determined.
      </p>
      {report.domains.length === 0 ? (
        <div style={{ color: "var(--text-secondary)", fontSize: 14 }}>No applicable requirements recorded yet.</div>
      ) : (
        <div style={{ overflowX: "auto", marginBottom: 12 }}>
          <table style={{ borderCollapse: "collapse", width: "100%", fontSize: 12 }}>
            <thead>
              <tr>
                <th style={{ textAlign: "left", padding: "6px 8px", borderBottom: "1px solid var(--border-subtle)" }}>Domain</th>
                {ASSURANCE_STATUS_ORDER.map((s) => (
                  <th key={s} style={{ textAlign: "center", padding: "6px 8px", borderBottom: "1px solid var(--border-subtle)" }}>
                    {s.replace(/_/g, " ")}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {report.domains.map((d) => (
                <tr key={d.domain_id}>
                  <td style={{ padding: "6px 8px", borderBottom: "1px solid var(--border-subtle)" }}>{d.domain_name}</td>
                  {ASSURANCE_STATUS_ORDER.map((s) => {
                    const count = d.status_counts[s] ?? 0;
                    return (
                      <td key={s} style={{ textAlign: "center", padding: "6px 8px", borderBottom: "1px solid var(--border-subtle)" }}>
                        {count > 0 ? (
                          <StatusBadge label={String(count)} variant={assuranceStatusVariant(s)} />
                        ) : (
                          <span style={{ color: "var(--text-secondary)" }}>—</span>
                        )}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <div style={{ display: "flex", gap: 16, flexWrap: "wrap", fontSize: 13 }}>
        <span>Open actions: <strong>{report.total_open_actions}</strong></span>
        <span>Overdue actions: <strong>{report.total_overdue_actions}</strong></span>
        <span>
          Hazards:{" "}
          {Object.entries(report.hazard_status_counts).length === 0
            ? "none"
            : Object.entries(report.hazard_status_counts)
                .map(([status, count]) => `${count} ${status.replace(/_/g, " ").toLowerCase()}`)
                .join(", ")}
        </span>
      </div>
    </div>
  );
}

export default function CompliancePage() {
  const [domains, setDomains] = useState<ComplianceDomainOut[] | null>(null);
  const [selectedDomainId, setSelectedDomainId] = useState("");
  const [requirements, setRequirements] = useState<ComplianceRequirementOut[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [domainCode, setDomainCode] = useState("");
  const [domainName, setDomainName] = useState("");
  const [domainSubmitting, setDomainSubmitting] = useState(false);
  const [domainFormError, setDomainFormError] = useState<string | null>(null);

  const [reqCode, setReqCode] = useState("");
  const [reqTitle, setReqTitle] = useState("");
  const [reqCadence, setReqCadence] = useState("");
  const [reqSubmitting, setReqSubmitting] = useState(false);
  const [reqFormError, setReqFormError] = useState<string | null>(null);

  function orgId(): string | null {
    return typeof window === "undefined" ? null : window.localStorage.getItem(SELECTED_ORG_KEY);
  }

  async function refreshDomains() {
    const id = orgId();
    if (!id) return;
    setDomains(await api.listComplianceDomains(id));
  }

  async function refreshRequirements(domainId: string) {
    const id = orgId();
    if (!id || !domainId) return;
    setRequirements(await api.listComplianceRequirements(id, { domain_id: domainId }));
  }

  useEffect(() => {
    (async () => {
      const id = orgId();
      if (!id) {
        setLoadError("No organisation selected.");
        return;
      }
      try {
        const domainList = await api.listComplianceDomains(id);
        setDomains(domainList);
        if (domainList[0]) {
          setSelectedDomainId(domainList[0].id);
          setRequirements(await api.listComplianceRequirements(id, { domain_id: domainList[0].id }));
        }
      } catch {
        setLoadError("Couldn't load the compliance framework.");
      }
    })();
  }, []);

  async function onSelectDomain(domainId: string) {
    setSelectedDomainId(domainId);
    setRequirements(null);
    await refreshRequirements(domainId);
  }

  async function onAddDomain() {
    const id = orgId();
    if (!id || !domainCode.trim() || !domainName.trim()) {
      setDomainFormError("Give the domain a code and a name.");
      return;
    }
    setDomainSubmitting(true);
    setDomainFormError(null);
    try {
      await api.createComplianceDomain(id, { code: domainCode.trim().toUpperCase(), name: domainName.trim() });
      setDomainCode("");
      setDomainName("");
      await refreshDomains();
    } catch {
      setDomainFormError("Couldn't add that domain — codes must be unique.");
    } finally {
      setDomainSubmitting(false);
    }
  }

  async function onAddRequirement() {
    const id = orgId();
    if (!id || !selectedDomainId || !reqCode.trim() || !reqTitle.trim()) {
      setReqFormError("Give the requirement a code and a title.");
      return;
    }
    setReqSubmitting(true);
    setReqFormError(null);
    try {
      await api.createComplianceRequirement(id, {
        domain_id: selectedDomainId,
        code: reqCode.trim(),
        title: reqTitle.trim(),
        cadence: reqCadence.trim() || undefined,
        effective_date: new Date().toISOString().slice(0, 10),
      });
      setReqCode("");
      setReqTitle("");
      setReqCadence("");
      await refreshRequirements(selectedDomainId);
    } catch {
      setReqFormError("Couldn't add that requirement.");
    } finally {
      setReqSubmitting(false);
    }
  }

  if (loadError) {
    return <div style={{ color: "var(--text-secondary)" }}>{loadError}</div>;
  }

  if (!domains) {
    return <div style={{ color: "var(--text-secondary)" }}>Loading…</div>;
  }

  return (
    <div style={{ maxWidth: 960 }}>
      <h1 style={{ fontSize: 24, fontWeight: 700, margin: 0, marginBottom: 4 }}>Compliance</h1>
      <p style={{ color: "var(--text-secondary)", marginBottom: 24 }}>
        Framework → Domain → Requirement → Applicability → Inspection → Action → Status. The 21 domains below are
        DataLume&rsquo;s seeded starting set, not a claim of exactly 21 universal laws — add your own where you need
        to.
      </p>

      <BoardAssurance />

      <div
        style={{
          background: "var(--bg-card)",
          border: "1px solid var(--border-subtle)",
          borderRadius: "var(--radius-card)",
          padding: 20,
          marginBottom: 24,
        }}
      >
        <h2 style={{ fontSize: 16, fontWeight: 700, margin: 0, marginBottom: 16 }}>Add a domain</h2>
        <div style={{ display: "grid", gap: 12, gridTemplateColumns: "1fr 2fr auto", alignItems: "end" }}>
          <div>
            <label style={{ fontSize: 12, color: "var(--text-secondary)", display: "block", marginBottom: 4 }}>
              Code
            </label>
            <input
              style={inputStyle}
              value={domainCode}
              onChange={(e) => setDomainCode(e.target.value)}
              placeholder="e.g. COMMERCIAL_EICR"
            />
          </div>
          <div>
            <label style={{ fontSize: 12, color: "var(--text-secondary)", display: "block", marginBottom: 4 }}>
              Name
            </label>
            <input
              style={inputStyle}
              value={domainName}
              onChange={(e) => setDomainName(e.target.value)}
              placeholder="e.g. EICR — commercial units"
            />
          </div>
          <button style={primaryBtn} onClick={onAddDomain} disabled={domainSubmitting}>
            {domainSubmitting ? "Adding…" : "Add"}
          </button>
        </div>
        {domainFormError && (
          <div style={{ color: "var(--color-critical)", fontSize: 13, marginTop: 10 }}>{domainFormError}</div>
        )}
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 2fr", gap: 24 }}>
        <div>
          <h2 style={{ fontSize: 16, fontWeight: 700, marginBottom: 12 }}>Domains ({domains.length})</h2>
          <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
            {domains.map((d) => (
              <li key={d.id}>
                <button
                  onClick={() => onSelectDomain(d.id)}
                  style={{
                    display: "block",
                    width: "100%",
                    textAlign: "left",
                    padding: "8px 10px",
                    marginBottom: 2,
                    borderRadius: 6,
                    border: "none",
                    cursor: "pointer",
                    fontSize: 13,
                    background: d.id === selectedDomainId ? "var(--color-primary)" : "transparent",
                    color: d.id === selectedDomainId ? "white" : "var(--text-primary)",
                  }}
                >
                  {d.name}
                  {d.organisation_id && (
                    <span style={{ fontSize: 11, opacity: 0.7, marginLeft: 6 }}>(custom)</span>
                  )}
                </button>
              </li>
            ))}
          </ul>
        </div>

        <div>
          <h2 style={{ fontSize: 16, fontWeight: 700, marginBottom: 12 }}>Requirements</h2>
          <div
            style={{
              background: "var(--bg-card)",
              border: "1px solid var(--border-subtle)",
              borderRadius: "var(--radius-card)",
              padding: 16,
              marginBottom: 16,
            }}
          >
            <div style={{ display: "grid", gap: 10, gridTemplateColumns: "1fr 2fr 1fr auto", alignItems: "end" }}>
              <div>
                <label style={{ fontSize: 12, color: "var(--text-secondary)", display: "block", marginBottom: 4 }}>
                  Code
                </label>
                <input style={inputStyle} value={reqCode} onChange={(e) => setReqCode(e.target.value)} placeholder="GAS-001" />
              </div>
              <div>
                <label style={{ fontSize: 12, color: "var(--text-secondary)", display: "block", marginBottom: 4 }}>
                  Title
                </label>
                <input style={inputStyle} value={reqTitle} onChange={(e) => setReqTitle(e.target.value)} />
              </div>
              <div>
                <label style={{ fontSize: 12, color: "var(--text-secondary)", display: "block", marginBottom: 4 }}>
                  Cadence
                </label>
                <input style={inputStyle} value={reqCadence} onChange={(e) => setReqCadence(e.target.value)} placeholder="annual" />
              </div>
              <button style={primaryBtn} onClick={onAddRequirement} disabled={reqSubmitting}>
                {reqSubmitting ? "Adding…" : "Add"}
              </button>
            </div>
            {reqFormError && (
              <div style={{ color: "var(--color-critical)", fontSize: 13, marginTop: 10 }}>{reqFormError}</div>
            )}
          </div>

          {requirements === null ? (
            <div style={{ color: "var(--text-secondary)", fontSize: 14 }}>Loading…</div>
          ) : requirements.length === 0 ? (
            <div style={{ color: "var(--text-secondary)", fontSize: 14 }}>No requirements added to this domain yet.</div>
          ) : (
            <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
              {requirements.map((r) => (
                <li key={r.id} style={{ padding: "10px 0", borderTop: "1px solid var(--border-subtle)", fontSize: 13 }}>
                  <div style={{ display: "flex", justifyContent: "space-between" }}>
                    <span>
                      <span style={{ fontFamily: "monospace", color: "var(--text-secondary)", marginRight: 8 }}>
                        {r.code}
                      </span>
                      {r.title}
                    </span>
                    <StatusBadge label={`v${r.version}`} variant="neutral" />
                  </div>
                  {r.cadence && <div style={{ color: "var(--text-secondary)", marginTop: 4 }}>Cadence: {r.cadence}</div>}
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}
