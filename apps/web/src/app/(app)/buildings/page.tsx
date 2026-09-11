"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { StatusBadge } from "@/components/StatusBadge";
import { inputStyle, primaryBtn } from "@/components/formStyles";
import { api, type BuildingOut, type DevelopmentOut } from "@/lib/api";

const SELECTED_ORG_KEY = "datalume.selectedOrganisationId";

function statusVariant(status: string) {
  if (status === "OPERATIONAL" || status === "COMPLETED") return "success" as const;
  return "neutral" as const;
}

export default function BuildingsPage() {
  const [buildings, setBuildings] = useState<BuildingOut[] | null>(null);
  const [developments, setDevelopments] = useState<DevelopmentOut[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [name, setName] = useState("");
  const [developmentId, setDevelopmentId] = useState("");
  const [buildingControlReference, setBuildingControlReference] = useState("");
  const [bsrReference, setBsrReference] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  function orgId(): string | null {
    return typeof window === "undefined" ? null : window.localStorage.getItem(SELECTED_ORG_KEY);
  }

  async function refresh() {
    const id = orgId();
    if (!id) return;
    setBuildings(await api.listBuildings(id));
  }

  useEffect(() => {
    (async () => {
      const id = orgId();
      if (!id) {
        setLoadError("No organisation selected.");
        return;
      }
      try {
        const [buildingList, devList] = await Promise.all([api.listBuildings(id), api.listDevelopments(id)]);
        setBuildings(buildingList);
        setDevelopments(devList);
      } catch {
        setLoadError("Couldn't load buildings.");
      }
    })();
  }, []);

  async function onAdd() {
    const id = orgId();
    if (!id || !name.trim()) {
      setFormError("Give the building a name first.");
      return;
    }
    setSubmitting(true);
    setFormError(null);
    try {
      await api.createBuilding(id, {
        name: name.trim(),
        development_id: developmentId || undefined,
        building_control_reference: buildingControlReference.trim() || undefined,
        bsr_reference: bsrReference.trim() || undefined,
      });
      setName("");
      setDevelopmentId("");
      setBuildingControlReference("");
      setBsrReference("");
      await refresh();
    } catch {
      setFormError("Couldn't add that building.");
    } finally {
      setSubmitting(false);
    }
  }

  if (loadError) {
    return <div style={{ color: "var(--text-secondary)" }}>{loadError}</div>;
  }

  const developmentName = (id: string | null) => developments.find((d) => d.id === id)?.name ?? "—";

  return (
    <div style={{ maxWidth: 880 }}>
      <h1 style={{ fontSize: 24, fontWeight: 700, margin: 0, marginBottom: 4 }}>Buildings</h1>
      <p style={{ color: "var(--text-secondary)", marginBottom: 24 }}>
        A building can stand alone or belong to a development — link it below, or from the development&rsquo;s
        own page.
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
        <h2 style={{ fontSize: 16, fontWeight: 700, margin: 0, marginBottom: 16 }}>Add a building</h2>
        <div style={{ display: "grid", gap: 12, gridTemplateColumns: "2fr 2fr", marginBottom: 12 }}>
          <div>
            <label htmlFor="building-name" style={{ fontSize: 12, color: "var(--text-secondary)", display: "block", marginBottom: 4 }}>
              Name
            </label>
            <input id="building-name" style={inputStyle} value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Block A" />
          </div>
          <div>
            <label htmlFor="building-development" style={{ fontSize: 12, color: "var(--text-secondary)", display: "block", marginBottom: 4 }}>
              Development (optional)
            </label>
            <select id="building-development" style={inputStyle} value={developmentId} onChange={(e) => setDevelopmentId(e.target.value)}>
              <option value="">— None —</option>
              {developments.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.name}
                </option>
              ))}
            </select>
          </div>
        </div>
        <div style={{ display: "grid", gap: 12, gridTemplateColumns: "2fr 2fr auto", alignItems: "end" }}>
          <div>
            <label htmlFor="building-control-reference" style={{ fontSize: 12, color: "var(--text-secondary)", display: "block", marginBottom: 4 }}>
              Building Control reference (optional)
            </label>
            <input
              id="building-control-reference"
              style={inputStyle}
              value={buildingControlReference}
              onChange={(e) => setBuildingControlReference(e.target.value)}
              placeholder="e.g. BC/2026/0042"
            />
          </div>
          <div>
            <label htmlFor="building-bsr-reference" style={{ fontSize: 12, color: "var(--text-secondary)", display: "block", marginBottom: 4 }}>
              BSR reference (optional)
            </label>
            <input
              id="building-bsr-reference"
              style={inputStyle}
              value={bsrReference}
              onChange={(e) => setBsrReference(e.target.value)}
              placeholder="Where applicable"
            />
          </div>
          <button style={primaryBtn} onClick={onAdd} disabled={submitting}>
            {submitting ? "Adding…" : "Add"}
          </button>
        </div>
        {formError && <div style={{ color: "var(--color-critical)", fontSize: 13, marginTop: 10 }}>{formError}</div>}
      </div>

      {buildings === null ? (
        <div style={{ color: "var(--text-secondary)" }}>Loading…</div>
      ) : buildings.length === 0 ? (
        <div style={{ color: "var(--text-secondary)", fontSize: 14 }}>No buildings yet.</div>
      ) : (
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
          <thead>
            <tr style={{ textAlign: "left", color: "var(--text-secondary)" }}>
              <th style={{ padding: "8px" }}>Reference</th>
              <th style={{ padding: "8px" }}>Name</th>
              <th style={{ padding: "8px" }}>Development</th>
              <th style={{ padding: "8px" }}>Status</th>
            </tr>
          </thead>
          <tbody>
            {buildings.map((b) => (
              <tr key={b.id} style={{ borderTop: "1px solid var(--border-subtle)" }}>
                <td style={{ padding: "8px", fontFamily: "monospace" }}>
                  <Link href={`/buildings/${b.id}`} style={{ color: "var(--color-primary)" }}>
                    {b.building_reference}
                  </Link>
                </td>
                <td style={{ padding: "8px" }}>{b.name}</td>
                <td style={{ padding: "8px" }}>{developmentName(b.development_id)}</td>
                <td style={{ padding: "8px" }}>
                  <StatusBadge label={b.status} variant={statusVariant(b.status)} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
