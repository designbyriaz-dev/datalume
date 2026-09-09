"use client";

import { useEffect, useState } from "react";
import { EmptyState } from "@/components/EmptyState";
import { KpiStatCard } from "@/components/KpiStatCard";
import { api, type DataHealth, type PropertyOut } from "@/lib/api";

const SELECTED_ORG_KEY = "datalume.selectedOrganisationId";

export default function HomePage() {
  const [properties, setProperties] = useState<PropertyOut[] | null>(null);
  const [dataHealth, setDataHealth] = useState<DataHealth | null>(null);

  useEffect(() => {
    (async () => {
      const id = typeof window === "undefined" ? null : window.localStorage.getItem(SELECTED_ORG_KEY);
      if (!id) return;
      try {
        const [props, health] = await Promise.all([api.listProperties(id), api.dataHealth(id)]);
        setProperties(props);
        setDataHealth(health);
      } catch {
        // Home degrades to the empty state below rather than showing an error —
        // KPIs are a nice-to-have here, not the page's core function.
      }
    })();
  }, []);

  const hasData = (properties?.length ?? 0) > 0;

  return (
    <div style={{ maxWidth: 720 }}>
      <h1 style={{ fontSize: 24, fontWeight: 700, margin: 0 }}>Good morning 👋</h1>
      <p style={{ color: "var(--text-secondary)", marginTop: 4, marginBottom: 24 }}>
        Here&rsquo;s what&rsquo;s happening across your portfolio.
      </p>

      {hasData ? (
        <div style={{ display: "flex", gap: 16, flexWrap: "wrap" }}>
          <KpiStatCard label="Total Properties" value={String(properties?.length ?? 0)} />
          {dataHealth && (
            <KpiStatCard
              label="Data Health Score"
              value={`${dataHealth.score_pct}%`}
              tint={dataHealth.score_pct >= 90 ? "var(--color-success)" : "var(--color-warning)"}
            />
          )}
        </div>
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
