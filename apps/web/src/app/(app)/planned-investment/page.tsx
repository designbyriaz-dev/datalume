"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { StatusBadge } from "@/components/StatusBadge";
import { inputStyle } from "@/components/formStyles";
import { api, type PlannedInvestmentScoreOut, type PlannedInvestmentWeightOut } from "@/lib/api";

const SELECTED_ORG_KEY = "datalume.selectedOrganisationId";

function scoreVariant(score: number) {
  if (score >= 70) return "critical" as const;
  if (score >= 40) return "warning" as const;
  return "success" as const;
}

function ScoreRow({ score }: { score: PlannedInvestmentScoreOut }) {
  const [expanded, setExpanded] = useState(false);
  return (
    <li style={{ padding: "10px 0", borderTop: "1px solid var(--border-subtle)", fontSize: 13 }}>
      <div
        style={{ display: "flex", justifyContent: "space-between", alignItems: "center", cursor: "pointer" }}
        onClick={() => setExpanded((v) => !v)}
      >
        <span>
          <Link
            href={`/components/${score.component_id}`}
            style={{ color: "var(--color-primary)" }}
            onClick={(e) => e.stopPropagation()}
          >
            {score.component_reference}
          </Link>
          {" — "}
          {score.component_type_name}
        </span>
        <StatusBadge label={`${score.priority_score.toFixed(0)}`} variant={scoreVariant(score.priority_score)} />
      </div>
      {expanded && (
        <ul style={{ listStyle: "none", padding: 0, margin: "8px 0 0", fontSize: 12, color: "var(--text-secondary)" }}>
          {score.factors.map((f) => (
            <li key={f.factor_code} style={{ padding: "3px 0" }}>
              <strong>{f.label}</strong> (weight {f.weight}): {f.applicable ? f.detail : "not applicable — excluded"}
            </li>
          ))}
        </ul>
      )}
    </li>
  );
}

export default function PlannedInvestmentPage() {
  const [scores, setScores] = useState<PlannedInvestmentScoreOut[] | null>(null);
  const [weights, setWeights] = useState<PlannedInvestmentWeightOut[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [weightError, setWeightError] = useState<string | null>(null);

  function orgId(): string | null {
    return typeof window === "undefined" ? null : window.localStorage.getItem(SELECTED_ORG_KEY);
  }

  async function refreshWeights() {
    const id = orgId();
    if (!id) return;
    setWeights(await api.listPlannedInvestmentWeights(id));
  }

  useEffect(() => {
    (async () => {
      const id = orgId();
      if (!id) {
        setLoadError("No organisation selected.");
        return;
      }
      try {
        const [scoreList, weightList] = await Promise.all([
          api.listPlannedInvestment(id),
          api.listPlannedInvestmentWeights(id),
        ]);
        setScores(scoreList);
        setWeights(weightList);
      } catch {
        setLoadError("Couldn't load planned investment data.");
      }
    })();
  }, []);

  async function onWeightChange(factorCode: string, weight: number) {
    const id = orgId();
    if (!id || Number.isNaN(weight)) return;
    setWeightError(null);
    try {
      await api.updatePlannedInvestmentWeight(id, factorCode, weight);
      await refreshWeights();
      setScores(await api.listPlannedInvestment(id));
    } catch {
      setWeightError("Couldn't update that weight.");
    }
  }

  if (loadError) {
    return <div style={{ color: "var(--text-secondary)" }}>{loadError}</div>;
  }

  if (!scores || !weights) {
    return <div style={{ color: "var(--text-secondary)" }}>Loading…</div>;
  }

  return (
    <div style={{ maxWidth: 960 }}>
      <h1 style={{ fontSize: 24, fontWeight: 700, margin: 0, marginBottom: 4 }}>Planned Investment</h1>
      <p style={{ color: "var(--text-secondary)", marginBottom: 24 }}>
        Components ranked by a weighted, fully explainable investment priority score — age is one of five factors,
        never the whole story. Only components with an expected life recorded are scored. Click a row to see the
        factor breakdown.
      </p>

      <div
        style={{
          background: "var(--bg-card)",
          border: "1px solid var(--border-subtle)",
          borderRadius: "var(--radius-card)",
          padding: 16,
          marginBottom: 24,
        }}
      >
        <h2 style={{ fontSize: 14, fontWeight: 700, margin: 0, marginBottom: 10 }}>Factor weights</h2>
        <div style={{ display: "flex", gap: 16, flexWrap: "wrap" }}>
          {weights.map((w) => (
            <div key={w.factor_code}>
              <label htmlFor={`weight-${w.factor_code}`} style={{ fontSize: 11, color: "var(--text-secondary)", display: "block", marginBottom: 2 }}>{w.label}</label>
              <input
                id={`weight-${w.factor_code}`}
                style={{ ...inputStyle, width: 80 }}
                type="number"
                step="0.05"
                min="0"
                max="1"
                defaultValue={w.weight}
                onBlur={(e) => onWeightChange(w.factor_code, parseFloat(e.target.value))}
              />
            </div>
          ))}
        </div>
        {weightError && <div style={{ color: "var(--color-critical)", fontSize: 12, marginTop: 8 }}>{weightError}</div>}
      </div>

      <h2 style={{ fontSize: 16, fontWeight: 700, marginBottom: 12 }}>Components ({scores.length})</h2>
      {scores.length === 0 ? (
        <div style={{ color: "var(--text-secondary)", fontSize: 14 }}>
          No components with an expected life recorded yet.
        </div>
      ) : (
        <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
          {scores.map((s) => (
            <ScoreRow key={s.component_id} score={s} />
          ))}
        </ul>
      )}
    </div>
  );
}
