"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { StatusBadge } from "@/components/StatusBadge";
import { inputStyle, primaryBtn } from "@/components/formStyles";
import { api, type DevelopmentHierarchy, type DevelopmentOut } from "@/lib/api";

const SELECTED_ORG_KEY = "datalume.selectedOrganisationId";

function statusVariant(status: string) {
  if (status === "OPERATIONAL" || status === "COMPLETED") return "success" as const;
  if (status === "CANCELLED") return "critical" as const;
  return "neutral" as const;
}

export function DevelopmentDetailClient({ developmentId }: { developmentId: string }) {
  const [development, setDevelopment] = useState<DevelopmentOut | null>(null);
  const [hierarchy, setHierarchy] = useState<DevelopmentHierarchy | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [buildingName, setBuildingName] = useState("");
  const [storeys, setStoreys] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  function orgId(): string | null {
    return typeof window === "undefined" ? null : window.localStorage.getItem(SELECTED_ORG_KEY);
  }

  async function refreshHierarchy() {
    const id = orgId();
    if (!id) return;
    setHierarchy(await api.getDevelopmentHierarchy(id, developmentId));
  }

  useEffect(() => {
    (async () => {
      const id = orgId();
      if (!id) {
        setLoadError("No organisation selected.");
        return;
      }
      try {
        const [dev, tree] = await Promise.all([
          api.getDevelopment(id, developmentId),
          api.getDevelopmentHierarchy(id, developmentId),
        ]);
        setDevelopment(dev);
        setHierarchy(tree);
      } catch {
        setLoadError("Couldn't load this development.");
      }
    })();
  }, [developmentId]);

  async function onAddBuilding() {
    const id = orgId();
    if (!id || !buildingName.trim()) {
      setFormError("Give the building a name first.");
      return;
    }
    setSubmitting(true);
    setFormError(null);
    try {
      await api.createBuilding(id, {
        name: buildingName.trim(),
        development_id: developmentId,
        storeys: storeys ? Number(storeys) : undefined,
      });
      setBuildingName("");
      setStoreys("");
      await refreshHierarchy();
    } catch {
      setFormError("Couldn't add that building.");
    } finally {
      setSubmitting(false);
    }
  }

  if (loadError) {
    return <div style={{ color: "var(--text-secondary)" }}>{loadError}</div>;
  }

  if (!development || !hierarchy) {
    return <div style={{ color: "var(--text-secondary)" }}>Loading…</div>;
  }

  return (
    <div style={{ maxWidth: 720 }}>
      <Link href="/developments" style={{ fontSize: 13, color: "var(--color-primary)" }}>
        ← Developments
      </Link>

      <div style={{ display: "flex", alignItems: "center", gap: 12, margin: "8px 0 4px" }}>
        <h1 style={{ fontSize: 24, fontWeight: 700, margin: 0 }}>{development.name}</h1>
        <StatusBadge label={development.status} variant={statusVariant(development.status)} />
      </div>
      <p style={{ color: "var(--text-secondary)", marginBottom: 24, fontFamily: "monospace", fontSize: 13 }}>
        {development.development_reference}
      </p>

      {hierarchy.unbuilt_property_count > 0 && (
        <p style={{ fontSize: 13, color: "var(--text-secondary)", marginBottom: 16 }}>
          {hierarchy.unbuilt_property_count} propert{hierarchy.unbuilt_property_count === 1 ? "y" : "ies"} linked
          directly to this development, not yet assigned to a building.
        </p>
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
        <h2 style={{ fontSize: 16, fontWeight: 700, margin: 0, marginBottom: 16 }}>Add a building</h2>
        <div style={{ display: "grid", gap: 12, gridTemplateColumns: "2fr 1fr auto", alignItems: "end" }}>
          <div>
            <label style={{ fontSize: 12, color: "var(--text-secondary)", display: "block", marginBottom: 4 }}>
              Name
            </label>
            <input
              style={inputStyle}
              value={buildingName}
              onChange={(e) => setBuildingName(e.target.value)}
              placeholder="e.g. Block A"
            />
          </div>
          <div>
            <label style={{ fontSize: 12, color: "var(--text-secondary)", display: "block", marginBottom: 4 }}>
              Storeys
            </label>
            <input style={inputStyle} value={storeys} onChange={(e) => setStoreys(e.target.value)} />
          </div>
          <button style={primaryBtn} onClick={onAddBuilding} disabled={submitting}>
            {submitting ? "Adding…" : "Add"}
          </button>
        </div>
        {formError && <div style={{ color: "var(--color-critical)", fontSize: 13, marginTop: 10 }}>{formError}</div>}
      </div>

      <h2 style={{ fontSize: 16, fontWeight: 700, marginBottom: 12 }}>Buildings</h2>
      {hierarchy.buildings.length === 0 ? (
        <div style={{ color: "var(--text-secondary)", fontSize: 14 }}>No buildings yet.</div>
      ) : (
        <div style={{ display: "grid", gap: 12 }}>
          {hierarchy.buildings.map((b) => {
            const floorPropertyTotal = b.floors.reduce((sum, f) => sum + f.property_count, 0);
            const total = floorPropertyTotal + b.unfloored_property_count;
            return (
              <div
                key={b.id}
                style={{
                  background: "var(--bg-card)",
                  border: "1px solid var(--border-subtle)",
                  borderRadius: "var(--radius-card)",
                  padding: 16,
                }}
              >
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <div>
                    <Link href={`/buildings/${b.id}`} style={{ fontWeight: 600, color: "var(--color-primary)" }}>
                      {b.name}
                    </Link>
                    <span style={{ color: "var(--text-secondary)", fontSize: 12, marginLeft: 8 }}>
                      {b.building_reference}
                    </span>
                  </div>
                  <StatusBadge label={b.status} variant={statusVariant(b.status)} />
                </div>
                <div style={{ fontSize: 13, color: "var(--text-secondary)", marginTop: 8 }}>
                  {b.floors.length} floor{b.floors.length === 1 ? "" : "s"} · {total} propert
                  {total === 1 ? "y" : "ies"}
                  {b.unfloored_property_count > 0 && ` (${b.unfloored_property_count} unassigned to a floor)`}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
