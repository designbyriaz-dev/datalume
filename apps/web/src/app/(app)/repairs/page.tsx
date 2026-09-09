"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { KpiStatCard } from "@/components/KpiStatCard";
import { StatusBadge } from "@/components/StatusBadge";
import { inputStyle, primaryBtn } from "@/components/formStyles";
import { api, type PropertyOut, type RepairOut, type RepairsIntelligence } from "@/lib/api";

const SELECTED_ORG_KEY = "datalume.selectedOrganisationId";

const PRIORITIES = ["ROUTINE", "URGENT", "EMERGENCY", "PLANNED"] as const;

const REPAIR_TRANSITIONS: Record<string, string[]> = {
  REPORTED: ["SCHEDULED", "CANCELLED"],
  SCHEDULED: ["IN_PROGRESS", "CANCELLED"],
  IN_PROGRESS: ["COMPLETED", "CANCELLED"],
  COMPLETED: [],
  CANCELLED: [],
};

function statusVariant(status: string) {
  if (status === "COMPLETED") return "success" as const;
  if (status === "CANCELLED") return "critical" as const;
  return "neutral" as const;
}

function priorityVariant(priority: string) {
  if (priority === "EMERGENCY") return "critical" as const;
  if (priority === "URGENT") return "warning" as const;
  return "neutral" as const;
}

export default function RepairsPage() {
  const [repairs, setRepairs] = useState<RepairOut[] | null>(null);
  const [properties, setProperties] = useState<PropertyOut[] | null>(null);
  const [intelligence, setIntelligence] = useState<RepairsIntelligence | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [propertyId, setPropertyId] = useState("");
  const [category, setCategory] = useState("");
  const [description, setDescription] = useState("");
  const [priority, setPriority] = useState<(typeof PRIORITIES)[number]>("ROUTINE");
  const [contractor, setContractor] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  function orgId(): string | null {
    return typeof window === "undefined" ? null : window.localStorage.getItem(SELECTED_ORG_KEY);
  }

  async function refresh() {
    const id = orgId();
    if (!id) return;
    const [repairList, intel] = await Promise.all([api.listRepairs(id), api.repairsIntelligence(id)]);
    setRepairs(repairList);
    setIntelligence(intel);
  }

  useEffect(() => {
    (async () => {
      const id = orgId();
      if (!id) {
        setLoadError("No organisation selected.");
        return;
      }
      try {
        const [repairList, propertyList, intel] = await Promise.all([
          api.listRepairs(id),
          api.listProperties(id),
          api.repairsIntelligence(id),
        ]);
        setRepairs(repairList);
        setProperties(propertyList);
        setIntelligence(intel);
        if (propertyList[0]) setPropertyId(propertyList[0].id);
      } catch {
        setLoadError("Couldn't load repairs.");
      }
    })();
  }, []);

  async function onAddRepair() {
    const id = orgId();
    if (!id || !propertyId || !category.trim() || !description.trim()) {
      setFormError("Pick a property, a category, and a description.");
      return;
    }
    setSubmitting(true);
    setFormError(null);
    try {
      await api.createRepair(id, {
        property_id: propertyId,
        category: category.trim(),
        description: description.trim(),
        reported_date: new Date().toISOString().slice(0, 10),
        priority,
        contractor: contractor.trim() || undefined,
      });
      setCategory("");
      setDescription("");
      setContractor("");
      await refresh();
    } catch {
      setFormError("Couldn't add that repair.");
    } finally {
      setSubmitting(false);
    }
  }

  async function onStatusChange(repairId: string, nextStatus: string) {
    const id = orgId();
    if (!id) return;
    await api.updateRepairStatus(id, repairId, { status: nextStatus });
    await refresh();
  }

  if (loadError) {
    return <div style={{ color: "var(--text-secondary)" }}>{loadError}</div>;
  }

  if (!repairs || !properties || !intelligence) {
    return <div style={{ color: "var(--text-secondary)" }}>Loading…</div>;
  }

  const propertyAddress = (id: string) => properties.find((p) => p.id === id)?.address ?? id.slice(0, 8);

  return (
    <div style={{ maxWidth: 960 }}>
      <h1 style={{ fontSize: 24, fontWeight: 700, margin: 0, marginBottom: 4 }}>Repairs</h1>
      <p style={{ color: "var(--text-secondary)", marginBottom: 24 }}>
        Reported against a property, optionally linked to the component that failed — deterministic repeat-repair
        and component-failure signals are computed from this register, never guessed.
      </p>

      <div style={{ display: "flex", gap: 16, flexWrap: "wrap", marginBottom: 24 }}>
        <KpiStatCard label="Total Repairs" value={String(intelligence.total_count)} />
        <KpiStatCard label="Open" value={String(intelligence.open_count)} />
        <KpiStatCard label="Completed" value={String(intelligence.completed_count)} />
        <KpiStatCard
          label="Emergencies"
          value={String(intelligence.emergency_count)}
          tint={intelligence.emergency_count > 0 ? "var(--color-critical)" : "var(--color-primary)"}
        />
        <KpiStatCard label="Total Cost" value={`£${(intelligence.total_cost_pence / 100).toFixed(2)}`} />
      </div>

      {(intelligence.repeat_repair_properties.length > 0 || intelligence.repeat_failure_components.length > 0) && (
        <>
          <h2 style={{ fontSize: 16, fontWeight: 700, marginBottom: 12 }}>Repeat repair patterns</h2>
          <ul style={{ listStyle: "none", padding: 0, margin: "0 0 24px", fontSize: 13 }}>
            {intelligence.repeat_repair_properties.map((s) => (
              <li key={s.property_id} style={{ padding: "6px 0", borderTop: "1px solid var(--border-subtle)" }}>
                <Link href={`/properties/${s.property_id}`} style={{ color: "var(--color-primary)" }}>
                  {propertyAddress(s.property_id)}
                </Link>{" "}
                — {s.repair_count} repairs in the last {s.window_months} months (threshold {s.threshold})
              </li>
            ))}
            {intelligence.repeat_failure_components.map((s) => (
              <li key={s.component_id} style={{ padding: "6px 0", borderTop: "1px solid var(--border-subtle)" }}>
                <Link href={`/components/${s.component_id}`} style={{ color: "var(--color-primary)" }}>
                  Component {s.component_id.slice(0, 8)}
                </Link>{" "}
                — {s.repair_count} repair interventions in the last {s.window_months} months (threshold {s.threshold})
              </li>
            ))}
          </ul>
        </>
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
        <h2 style={{ fontSize: 16, fontWeight: 700, margin: 0, marginBottom: 16 }}>Report a repair</h2>
        <div style={{ display: "grid", gap: 12, gridTemplateColumns: "1.5fr 1fr 1.5fr 1fr 1fr auto", alignItems: "end" }}>
          <div>
            <label style={{ fontSize: 12, color: "var(--text-secondary)", display: "block", marginBottom: 4 }}>
              Property
            </label>
            <select style={inputStyle} value={propertyId} onChange={(e) => setPropertyId(e.target.value)}>
              {properties.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.address}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label style={{ fontSize: 12, color: "var(--text-secondary)", display: "block", marginBottom: 4 }}>
              Category
            </label>
            <input style={inputStyle} value={category} onChange={(e) => setCategory(e.target.value)} placeholder="e.g. Plumbing" />
          </div>
          <div>
            <label style={{ fontSize: 12, color: "var(--text-secondary)", display: "block", marginBottom: 4 }}>
              Description
            </label>
            <input style={inputStyle} value={description} onChange={(e) => setDescription(e.target.value)} />
          </div>
          <div>
            <label style={{ fontSize: 12, color: "var(--text-secondary)", display: "block", marginBottom: 4 }}>
              Priority
            </label>
            <select style={inputStyle} value={priority} onChange={(e) => setPriority(e.target.value as (typeof PRIORITIES)[number])}>
              {PRIORITIES.map((p) => (
                <option key={p} value={p}>
                  {p}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label style={{ fontSize: 12, color: "var(--text-secondary)", display: "block", marginBottom: 4 }}>
              Contractor
            </label>
            <input style={inputStyle} value={contractor} onChange={(e) => setContractor(e.target.value)} />
          </div>
          <button style={primaryBtn} onClick={onAddRepair} disabled={submitting}>
            {submitting ? "Reporting…" : "Report"}
          </button>
        </div>
        {properties.length === 0 && (
          <div style={{ color: "var(--text-secondary)", fontSize: 13, marginTop: 10 }}>
            Add a property first before reporting a repair.
          </div>
        )}
        {formError && <div style={{ color: "var(--color-critical)", fontSize: 13, marginTop: 10 }}>{formError}</div>}
      </div>

      <h2 style={{ fontSize: 16, fontWeight: 700, marginBottom: 12 }}>Register</h2>
      {repairs.length === 0 ? (
        <div style={{ color: "var(--text-secondary)", fontSize: 14 }}>No repairs reported yet.</div>
      ) : (
        <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
          {repairs.map((r) => (
            <li key={r.id} style={{ padding: "12px 0", borderTop: "1px solid var(--border-subtle)", fontSize: 13 }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
                <span>
                  <span style={{ fontFamily: "monospace", color: "var(--text-secondary)", marginRight: 8 }}>
                    {r.repair_reference}
                  </span>
                  <Link href={`/properties/${r.property_id}`} style={{ color: "var(--color-primary)" }}>
                    {propertyAddress(r.property_id)}
                  </Link>
                  {" · "}
                  {r.category}
                </span>
                <span style={{ display: "flex", gap: 6 }}>
                  <StatusBadge label={r.priority} variant={priorityVariant(r.priority)} />
                  <StatusBadge label={r.status} variant={statusVariant(r.status)} />
                </span>
              </div>
              <div style={{ color: "var(--text-secondary)", marginBottom: 8 }}>{r.description}</div>
              <div style={{ display: "flex", gap: 8 }}>
                {(REPAIR_TRANSITIONS[r.status] ?? []).map((next) => (
                  <button
                    key={next}
                    style={{ ...primaryBtn, padding: "4px 10px", fontSize: 12 }}
                    onClick={() => onStatusChange(r.id, next)}
                  >
                    {next.replace(/_/g, " ").toLowerCase()}
                  </button>
                ))}
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
