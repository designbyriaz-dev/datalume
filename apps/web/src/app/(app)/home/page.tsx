"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { EmptyState } from "@/components/EmptyState";
import { KpiStatCard } from "@/components/KpiStatCard";
import { StatusBadge } from "@/components/StatusBadge";
import { api, type PortfolioSummary } from "@/lib/api";

const SELECTED_ORG_KEY = "datalume.selectedOrganisationId";

export default function HomePage() {
  const [summary, setSummary] = useState<PortfolioSummary | null>(null);

  useEffect(() => {
    (async () => {
      const id = typeof window === "undefined" ? null : window.localStorage.getItem(SELECTED_ORG_KEY);
      if (!id) return;
      try {
        setSummary(await api.portfolioSummary(id));
      } catch {
        // Home degrades to the empty state below rather than showing an error —
        // KPIs are a nice-to-have here, not the page's core function.
      }
    })();
  }, []);

  const hasData = (summary?.total_properties ?? 0) > 0;

  return (
    <div style={{ maxWidth: 860 }}>
      <h1 style={{ fontSize: 24, fontWeight: 700, margin: 0 }}>Good morning 👋</h1>
      <p style={{ color: "var(--text-secondary)", marginTop: 4, marginBottom: 24 }}>
        Here&rsquo;s what&rsquo;s happening across your portfolio.
      </p>

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
