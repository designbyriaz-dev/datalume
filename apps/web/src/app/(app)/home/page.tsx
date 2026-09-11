"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { EmptyState } from "@/components/EmptyState";
import { KpiStatCard } from "@/components/KpiStatCard";
import { StatusBadge } from "@/components/StatusBadge";
import { api, ApiError, type AttentionSignalOut, type PortfolioSummary } from "@/lib/api";

const SELECTED_ORG_KEY = "datalume.selectedOrganisationId";

const ENTITY_LINK_PREFIX: Record<string, string> = {
  property: "/properties",
  component: "/components",
  building: "/buildings",
};

// POST /api/v1/attention/scan is gated to reports.board (app/attention/
// router.py) — granted explicitly to EXECUTIVE, and to OWNER/ADMIN via
// their wildcard permission set (app/auth/rbac.py). Checked client-side
// too so the button doesn't invite a click that can only ever 403.
const CAN_RUN_SCAN_ROLES = new Set(["OWNER", "ADMIN", "EXECUTIVE"]);

function severityVariant(severity: string) {
  if (severity === "CRITICAL" || severity === "HIGH") return "critical" as const;
  if (severity === "MEDIUM") return "warning" as const;
  return "neutral" as const;
}

export default function HomePage() {
  const [summary, setSummary] = useState<PortfolioSummary | null>(null);
  const [signals, setSignals] = useState<AttentionSignalOut[] | null>(null);
  const [canRunScan, setCanRunScan] = useState(false);
  const [scanning, setScanning] = useState(false);
  const [scanMessage, setScanMessage] = useState<string | null>(null);

  function orgId(): string | null {
    return typeof window === "undefined" ? null : window.localStorage.getItem(SELECTED_ORG_KEY);
  }

  async function refreshSignals() {
    const id = orgId();
    if (!id) return;
    try {
      setSignals(await api.listAttentionSignals(id, { signal_status: "OPEN" }));
    } catch {
      // Attention signals are a nice-to-have surface here too — Home
      // still works without them for a role that can't see reports.
    }
  }

  useEffect(() => {
    (async () => {
      const id = orgId();
      if (!id) return;
      try {
        setSummary(await api.portfolioSummary(id));
      } catch {
        // Home degrades to the empty state below rather than showing an error —
        // KPIs are a nice-to-have here, not the page's core function.
      }
      await refreshSignals();
      try {
        const me = await api.me();
        const membership = me.memberships.find((m) => m.organisation_id === id);
        setCanRunScan(!!membership && CAN_RUN_SCAN_ROLES.has(membership.role_code));
      } catch {
        // Leave the scan button hidden if we can't confirm the role.
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function onRunScan() {
    const id = orgId();
    if (!id) return;
    setScanning(true);
    setScanMessage(null);
    try {
      const result = await api.triggerAttentionScan(id);
      setScanMessage(
        result.signals_created > 0 || result.signals_refreshed > 0
          ? `${result.signals_created} new, ${result.signals_refreshed} updated.`
          : "No new signals — everything checked out.",
      );
      await refreshSignals();
    } catch (err) {
      setScanMessage(err instanceof ApiError ? err.message : "Something went wrong running the scan.");
    } finally {
      setScanning(false);
    }
  }

  async function onSignalAction(signalId: string, nextStatus: string) {
    const id = orgId();
    if (!id) return;
    await api.updateAttentionSignalStatus(id, signalId, nextStatus);
    await refreshSignals();
  }

  const hasData = (summary?.total_properties ?? 0) > 0;

  return (
    <div style={{ maxWidth: 860 }}>
      <h1 style={{ fontSize: 24, fontWeight: 700, margin: 0 }}>Good morning 👋</h1>
      <p style={{ color: "var(--text-secondary)", marginTop: 4, marginBottom: 24 }}>
        Here&rsquo;s what&rsquo;s happening across your portfolio.
      </p>

      {((signals && signals.length > 0) || canRunScan) && (
        <div style={{ marginBottom: 24 }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12, gap: 12, flexWrap: "wrap" }}>
            <h2 style={{ fontSize: 16, fontWeight: 700, margin: 0 }}>
              Needs attention {signals && signals.length > 0 ? `(${signals.length})` : ""}
            </h2>
            {canRunScan && (
              <button
                onClick={onRunScan}
                disabled={scanning}
                style={{
                  padding: "5px 12px",
                  borderRadius: 6,
                  border: "1px solid var(--border-subtle)",
                  background: "var(--bg-app)",
                  color: "var(--text-primary)",
                  fontSize: 12,
                  fontWeight: 600,
                  cursor: scanning ? "default" : "pointer",
                }}
              >
                {scanning ? "Scanning…" : "Run scan now"}
              </button>
            )}
          </div>
          {scanMessage && (
            <p style={{ color: "var(--text-secondary)", fontSize: 13, marginTop: -4, marginBottom: 12 }}>{scanMessage}</p>
          )}
          {signals && signals.length === 0 && (
            <p style={{ color: "var(--text-secondary)", fontSize: 13 }}>Nothing needs attention right now.</p>
          )}
          <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
            {signals?.map((s) => {
              const linkPrefix = ENTITY_LINK_PREFIX[s.entity_type];
              return (
                <li key={s.id} style={{ padding: "10px 0", borderTop: "1px solid var(--border-subtle)", fontSize: 13 }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 4, gap: 8, flexWrap: "wrap" }}>
                    <span>
                      {linkPrefix ? (
                        <Link href={`${linkPrefix}/${s.entity_id}`} style={{ color: "var(--color-primary)" }}>
                          {s.explanation.what}
                        </Link>
                      ) : (
                        s.explanation.what
                      )}
                    </span>
                    <StatusBadge label={s.severity} variant={severityVariant(s.severity)} />
                  </div>
                  <div style={{ color: "var(--text-secondary)", marginBottom: 6 }}>{s.explanation.why}</div>
                  <div style={{ display: "flex", gap: 8 }}>
                    <button
                      style={{ background: "none", border: "1px solid var(--border-subtle)", borderRadius: 6, padding: "3px 10px", fontSize: 12, cursor: "pointer" }}
                      onClick={() => onSignalAction(s.id, "ACKNOWLEDGED")}
                    >
                      Acknowledge
                    </button>
                    <button
                      style={{ background: "none", border: "1px solid var(--border-subtle)", borderRadius: 6, padding: "3px 10px", fontSize: 12, cursor: "pointer" }}
                      onClick={() => onSignalAction(s.id, "RESOLVED")}
                    >
                      Resolve
                    </button>
                    <button
                      style={{ background: "none", border: "1px solid var(--border-subtle)", borderRadius: 6, padding: "3px 10px", fontSize: 12, cursor: "pointer" }}
                      onClick={() => onSignalAction(s.id, "DISMISSED")}
                    >
                      Dismiss
                    </button>
                  </div>
                </li>
              );
            })}
          </ul>
        </div>
      )}

      {hasData && summary ? (
        <>
          <div style={{ display: "flex", gap: 16, flexWrap: "wrap", marginBottom: 24 }}>
            <KpiStatCard label="Total Properties" value={String(summary.total_properties)} />
            <KpiStatCard label="Developments" value={String(summary.total_developments)} />
            <KpiStatCard label="Components" value={String(summary.total_components)} />
            <KpiStatCard
              label="Data Health Score"
              value={`${summary.data_health_score_pct}%`}
              tint={summary.data_health_score_pct >= 90 ? "var(--color-success)" : "var(--color-warning)"}
            />
            <KpiStatCard
              label="Open Defects"
              value={String(summary.open_defects_count)}
              tint={summary.overdue_defects_count > 0 ? "var(--color-critical)" : "var(--color-primary)"}
            />
            <KpiStatCard
              label="Warranties Expiring (90d)"
              value={String(summary.warranties_expiring_within_90_days_count)}
              tint={summary.warranties_expiring_within_90_days_count > 0 ? "var(--color-warning)" : "var(--color-primary)"}
            />
          </div>

          {summary.properties_by_status.length > 0 && (
            <>
              <h2 style={{ fontSize: 16, fontWeight: 700, marginBottom: 12 }}>Properties by status</h2>
              <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 24 }}>
                {summary.properties_by_status.map((s) => (
                  <StatusBadge key={s.key} label={`${s.key}: ${s.count}`} variant="neutral" />
                ))}
              </div>
            </>
          )}

          {summary.development_readiness.length > 0 && (
            <>
              <h2 style={{ fontSize: 16, fontWeight: 700, marginBottom: 12 }}>Development handover readiness</h2>
              <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
                {summary.development_readiness.map((d) => (
                  <li
                    key={d.development_id}
                    style={{
                      padding: "10px 0",
                      borderTop: "1px solid var(--border-subtle)",
                      fontSize: 13,
                      display: "flex",
                      justifyContent: "space-between",
                    }}
                  >
                    <Link href={`/developments/${d.development_id}`} style={{ color: "var(--color-primary)" }}>
                      {d.name}
                    </Link>
                    <span style={{ color: "var(--text-secondary)" }}>{d.score_pct}% ready</span>
                  </li>
                ))}
              </ul>
            </>
          )}
        </>
      ) : (
        <EmptyState
          title="No property data yet"
          body="Once you upload a dataset or add records manually, your Home dashboard will show KPIs, compliance status, repairs, and DataLume Intelligence insights here — all traceable back to the records behind them."
          actionLabel="Add Data"
          actionHref="/data-and-uploads"
        />
      )}
    </div>
  );
}
