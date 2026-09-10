"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { StatusBadge } from "@/components/StatusBadge";
import { inputStyle, primaryBtn, secondaryBtn } from "@/components/formStyles";
import {
  api,
  type HazardActionOut,
  type HazardOut,
  type PropertyOut,
  type RepeatHazardSignal,
} from "@/lib/api";

const SELECTED_ORG_KEY = "datalume.selectedOrganisationId";

const SEVERITIES = ["LOW", "MEDIUM", "HIGH", "CRITICAL"] as const;

const HAZARD_TRANSITIONS: Record<string, string[]> = {
  REPORTED: ["TRIAGED"],
  TRIAGED: ["INVESTIGATING"],
  INVESTIGATING: [], // handled by the findings form instead of a plain button
  INVESTIGATED: ["ACTION_IN_PROGRESS", "FOLLOW_UP", "CLOSED"],
  ACTION_IN_PROGRESS: ["FOLLOW_UP", "CLOSED"],
  FOLLOW_UP: ["ACTION_IN_PROGRESS", "CLOSED"],
  CLOSED: [],
};

function severityVariant(severity: string) {
  if (severity === "CRITICAL" || severity === "HIGH") return "critical" as const;
  if (severity === "MEDIUM") return "warning" as const;
  return "neutral" as const;
}

function statusVariant(status: string) {
  if (status === "CLOSED") return "success" as const;
  if (status === "ACTION_IN_PROGRESS") return "warning" as const;
  return "neutral" as const;
}

function HazardActionsPanel({ organisationId, hazard }: { organisationId: string; hazard: HazardOut }) {
  const [actions, setActions] = useState<HazardActionOut[] | null>(null);
  const [description, setDescription] = useState("");
  const [deadline, setDeadline] = useState("");
  const [submitting, setSubmitting] = useState(false);

  async function refresh() {
    setActions(await api.listHazardActions(organisationId, hazard.id));
  }

  useEffect(() => {
    (async () => {
      await refresh();
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hazard.id]);

  async function onAdd() {
    if (!description.trim() || !deadline) return;
    setSubmitting(true);
    try {
      await api.createHazardAction(organisationId, hazard.id, { description: description.trim(), deadline });
      setDescription("");
      setDeadline("");
      await refresh();
    } finally {
      setSubmitting(false);
    }
  }

  async function onComplete(actionId: string) {
    await api.updateHazardActionStatus(organisationId, actionId, { status: "COMPLETED" });
    await refresh();
  }

  return (
    <div style={{ marginTop: 10, paddingTop: 10, borderTop: "1px dashed var(--border-subtle)" }}>
      <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 6, color: "var(--text-secondary)" }}>Actions</div>
      {actions === null ? (
        <div style={{ fontSize: 12, color: "var(--text-secondary)" }}>Loading…</div>
      ) : (
        <ul style={{ listStyle: "none", padding: 0, margin: "0 0 8px" }}>
          {actions.map((a) => (
            <li key={a.id} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", fontSize: 12, padding: "4px 0" }}>
              <span>
                {a.description} <span style={{ color: "var(--text-secondary)" }}>— due {a.deadline}</span>
              </span>
              <span style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <StatusBadge label={a.status} variant={a.status === "COMPLETED" ? "success" : "neutral"} />
                {a.status === "OPEN" && (
                  <button style={{ ...secondaryBtn, padding: "2px 8px", fontSize: 11 }} onClick={() => onComplete(a.id)}>
                    complete
                  </button>
                )}
              </span>
            </li>
          ))}
          {actions.length === 0 && <li style={{ fontSize: 12, color: "var(--text-secondary)" }}>No actions raised yet.</li>}
        </ul>
      )}
      <div style={{ display: "flex", gap: 6 }}>
        <input
          aria-label="Hazard action description"
          style={{ ...inputStyle, fontSize: 12 }}
          placeholder="e.g. Install extractor fan"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
        />
        <input aria-label="Hazard action deadline" style={{ ...inputStyle, fontSize: 12, maxWidth: 150 }} type="date" value={deadline} onChange={(e) => setDeadline(e.target.value)} />
        <button style={{ ...secondaryBtn, padding: "6px 10px", fontSize: 12 }} onClick={onAdd} disabled={submitting}>
          Raise
        </button>
      </div>
    </div>
  );
}

function InvestigationForm({ organisationId, hazard, onDone }: { organisationId: string; hazard: HazardOut; onDone: () => void }) {
  const [outcome, setOutcome] = useState("CONFIRMED");
  const [findings, setFindings] = useState("");
  const [submitting, setSubmitting] = useState(false);

  async function onSubmit() {
    if (!findings.trim()) return;
    setSubmitting(true);
    try {
      await api.updateHazardStatus(organisationId, hazard.id, {
        status: "INVESTIGATED",
        investigation_status: outcome,
        findings: findings.trim(),
      });
      onDone();
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div style={{ marginTop: 8, display: "flex", gap: 6, alignItems: "center", flexWrap: "wrap" }}>
      <select aria-label="Investigation outcome" style={{ ...inputStyle, width: "auto" }} value={outcome} onChange={(e) => setOutcome(e.target.value)}>
        <option value="CONFIRMED">Confirmed</option>
        <option value="NOT_CONFIRMED">Not confirmed</option>
        <option value="INCONCLUSIVE">Inconclusive</option>
      </select>
      <input
        aria-label="Findings"
        style={{ ...inputStyle, flex: 1, minWidth: 220 }}
        placeholder="Findings"
        value={findings}
        onChange={(e) => setFindings(e.target.value)}
      />
      <button style={{ ...primaryBtn, padding: "6px 12px", fontSize: 12 }} onClick={onSubmit} disabled={submitting}>
        Record findings
      </button>
    </div>
  );
}

export default function SafetyPage() {
  const [hazards, setHazards] = useState<HazardOut[] | null>(null);
  const [properties, setProperties] = useState<PropertyOut[] | null>(null);
  const [signals, setSignals] = useState<RepeatHazardSignal[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [propertyId, setPropertyId] = useState("");
  const [hazardType, setHazardType] = useState("");
  const [severity, setSeverity] = useState<(typeof SEVERITIES)[number]>("MEDIUM");
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  function orgId(): string | null {
    return typeof window === "undefined" ? null : window.localStorage.getItem(SELECTED_ORG_KEY);
  }

  async function refreshSignals(hazardList: HazardOut[]) {
    const id = orgId();
    if (!id) return;
    const combos = new Map<string, { property_id: string; hazard_type: string }>();
    for (const h of hazardList) combos.set(`${h.property_id}::${h.hazard_type}`, { property_id: h.property_id, hazard_type: h.hazard_type });
    const results = await Promise.all(
      Array.from(combos.values()).map((c) => api.repeatHazardsForProperty(id, c.property_id, c.hazard_type)),
    );
    setSignals(results.filter((s): s is RepeatHazardSignal => s !== null));
  }

  async function refresh() {
    const id = orgId();
    if (!id) return;
    const hazardList = await api.listHazards(id);
    setHazards(hazardList);
    await refreshSignals(hazardList);
  }

  useEffect(() => {
    (async () => {
      const id = orgId();
      if (!id) {
        setLoadError("No organisation selected.");
        return;
      }
      try {
        const [hazardList, propertyList] = await Promise.all([api.listHazards(id), api.listProperties(id)]);
        setHazards(hazardList);
        setProperties(propertyList);
        if (propertyList[0]) setPropertyId(propertyList[0].id);
        await refreshSignals(hazardList);
      } catch {
        setLoadError("Couldn't load hazards.");
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function onReportHazard() {
    const id = orgId();
    if (!id || !propertyId || !hazardType.trim()) {
      setFormError("Pick a property and a hazard type.");
      return;
    }
    setSubmitting(true);
    setFormError(null);
    try {
      await api.createHazard(id, {
        property_id: propertyId,
        hazard_type: hazardType.trim().toUpperCase().replace(/\s+/g, "_"),
        reported_date: new Date().toISOString().slice(0, 10),
        severity,
      });
      setHazardType("");
      await refresh();
    } catch {
      setFormError("Couldn't report that hazard.");
    } finally {
      setSubmitting(false);
    }
  }

  async function onStatusChange(hazard: HazardOut, nextStatus: string) {
    const id = orgId();
    if (!id) return;
    await api.updateHazardStatus(id, hazard.id, { status: nextStatus });
    await refresh();
  }

  if (loadError) {
    return <div style={{ color: "var(--text-secondary)" }}>{loadError}</div>;
  }

  if (!hazards || !properties) {
    return <div style={{ color: "var(--text-secondary)" }}>Loading…</div>;
  }

  const propertyAddress = (id: string) => properties.find((p) => p.id === id)?.address ?? id.slice(0, 8);

  return (
    <div style={{ maxWidth: 960 }}>
      <h1 style={{ fontSize: 24, fontWeight: 700, margin: 0, marginBottom: 4 }}>Safety &amp; Hazards</h1>
      <p style={{ color: "var(--text-secondary)", marginBottom: 24 }}>
        Damp &amp; mould and every other property hazard go through the same reported → triaged → investigated →
        action → follow-up → closed workflow — hazard_type is free text (e.g. DAMP_AND_MOULD, EXCESS_COLD), not a
        fixed HHSRS category list this build has no authoritative source for.
      </p>

      {signals.length > 0 && (
        <>
          <h2 style={{ fontSize: 16, fontWeight: 700, marginBottom: 12 }}>Repeat hazard patterns</h2>
          <ul style={{ listStyle: "none", padding: 0, margin: "0 0 24px", fontSize: 13 }}>
            {signals.map((s) => (
              <li key={`${s.property_id}-${s.hazard_type}`} style={{ padding: "6px 0", borderTop: "1px solid var(--border-subtle)" }}>
                <Link href={`/properties/${s.property_id}`} style={{ color: "var(--color-primary)" }}>
                  {propertyAddress(s.property_id)}
                </Link>{" "}
                — {s.hazard_count} {s.hazard_type.replace(/_/g, " ").toLowerCase()} hazards in the last {s.window_months} months
                (threshold {s.threshold})
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
        <h2 style={{ fontSize: 16, fontWeight: 700, margin: 0, marginBottom: 16 }}>Report a hazard</h2>
        <div style={{ display: "grid", gap: 12, gridTemplateColumns: "1.5fr 1.5fr 1fr auto", alignItems: "end" }}>
          <div>
            <label htmlFor="hazard-property" style={{ fontSize: 12, color: "var(--text-secondary)", display: "block", marginBottom: 4 }}>Property</label>
            <select id="hazard-property" style={inputStyle} value={propertyId} onChange={(e) => setPropertyId(e.target.value)}>
              {properties.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.address}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label htmlFor="hazard-type" style={{ fontSize: 12, color: "var(--text-secondary)", display: "block", marginBottom: 4 }}>Hazard type</label>
            <input id="hazard-type" style={inputStyle} value={hazardType} onChange={(e) => setHazardType(e.target.value)} placeholder="e.g. DAMP_AND_MOULD" />
          </div>
          <div>
            <label htmlFor="hazard-severity" style={{ fontSize: 12, color: "var(--text-secondary)", display: "block", marginBottom: 4 }}>Severity</label>
            <select id="hazard-severity" style={inputStyle} value={severity} onChange={(e) => setSeverity(e.target.value as (typeof SEVERITIES)[number])}>
              {SEVERITIES.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </div>
          <button style={primaryBtn} onClick={onReportHazard} disabled={submitting}>
            {submitting ? "Reporting…" : "Report"}
          </button>
        </div>
        {properties.length === 0 && (
          <div style={{ color: "var(--text-secondary)", fontSize: 13, marginTop: 10 }}>Add a property first before reporting a hazard.</div>
        )}
        {formError && <div style={{ color: "var(--color-critical)", fontSize: 13, marginTop: 10 }}>{formError}</div>}
      </div>

      <h2 style={{ fontSize: 16, fontWeight: 700, marginBottom: 12 }}>Register</h2>
      {hazards.length === 0 ? (
        <div style={{ color: "var(--text-secondary)", fontSize: 14 }}>No hazards reported yet.</div>
      ) : (
        <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
          {hazards.map((h) => (
            <li key={h.id} style={{ padding: "12px 0", borderTop: "1px solid var(--border-subtle)", fontSize: 13 }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
                <span>
                  <span style={{ fontWeight: 600, marginRight: 8 }}>{h.hazard_type.replace(/_/g, " ")}</span>
                  <Link href={`/properties/${h.property_id}`} style={{ color: "var(--color-primary)" }}>
                    {propertyAddress(h.property_id)}
                  </Link>
                </span>
                <span style={{ display: "flex", gap: 6 }}>
                  <StatusBadge label={h.severity} variant={severityVariant(h.severity)} />
                  <StatusBadge label={h.status.replace(/_/g, " ")} variant={statusVariant(h.status)} />
                </span>
              </div>
              {h.findings && <div style={{ color: "var(--text-secondary)", marginBottom: 6 }}>Findings: {h.findings}</div>}

              {h.status === "INVESTIGATING" ? (
                <InvestigationForm organisationId={orgId() ?? ""} hazard={h} onDone={refresh} />
              ) : (
                (HAZARD_TRANSITIONS[h.status] ?? []).length > 0 && (
                  <div style={{ display: "flex", gap: 8 }}>
                    {(HAZARD_TRANSITIONS[h.status] ?? []).map((next) => (
                      <button key={next} style={{ ...primaryBtn, padding: "4px 10px", fontSize: 12 }} onClick={() => onStatusChange(h, next)}>
                        {next.replace(/_/g, " ").toLowerCase()}
                      </button>
                    ))}
                  </div>
                )
              )}

              {(h.status === "ACTION_IN_PROGRESS" || h.status === "FOLLOW_UP") && (
                <HazardActionsPanel organisationId={orgId() ?? ""} hazard={h} />
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
