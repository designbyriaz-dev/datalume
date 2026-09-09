"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { StatusBadge } from "@/components/StatusBadge";
import { inputStyle, primaryBtn } from "@/components/formStyles";
import { api, type BuildingOut, type FloorOut, type PropertyOut } from "@/lib/api";

const SELECTED_ORG_KEY = "datalume.selectedOrganisationId";

function statusVariant(status: string) {
  if (status === "OPERATIONAL" || status === "COMPLETED") return "success" as const;
  return "neutral" as const;
}

export function BuildingDetailClient({ buildingId }: { buildingId: string }) {
  const [building, setBuilding] = useState<BuildingOut | null>(null);
  const [floors, setFloors] = useState<FloorOut[] | null>(null);
  const [properties, setProperties] = useState<PropertyOut[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [floorName, setFloorName] = useState("");
  const [levelIndex, setLevelIndex] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  function orgId(): string | null {
    return typeof window === "undefined" ? null : window.localStorage.getItem(SELECTED_ORG_KEY);
  }

  async function refreshFloors() {
    const id = orgId();
    if (!id) return;
    setFloors(await api.listFloors(id, buildingId));
  }

  useEffect(() => {
    (async () => {
      const id = orgId();
      if (!id) {
        setLoadError("No organisation selected.");
        return;
      }
      try {
        const [b, floorList, propertyList] = await Promise.all([
          api.getBuilding(id, buildingId),
          api.listFloors(id, buildingId),
          api.listProperties(id, { building_id: buildingId }),
        ]);
        setBuilding(b);
        setFloors(floorList);
        setProperties(propertyList);
      } catch {
        setLoadError("Couldn't load this building.");
      }
    })();
  }, [buildingId]);

  async function onAddFloor() {
    const id = orgId();
    if (!id || !floorName.trim()) {
      setFormError("Give the floor a name first.");
      return;
    }
    setSubmitting(true);
    setFormError(null);
    try {
      await api.createFloor(id, {
        building_id: buildingId,
        name: floorName.trim(),
        level_index: levelIndex ? Number(levelIndex) : undefined,
      });
      setFloorName("");
      setLevelIndex("");
      await refreshFloors();
    } catch {
      setFormError("Couldn't add that floor.");
    } finally {
      setSubmitting(false);
    }
  }

  if (loadError) {
    return <div style={{ color: "var(--text-secondary)" }}>{loadError}</div>;
  }

  if (!building || !floors || !properties) {
    return <div style={{ color: "var(--text-secondary)" }}>Loading…</div>;
  }

  return (
    <div style={{ maxWidth: 720 }}>
      <Link href="/buildings" style={{ fontSize: 13, color: "var(--color-primary)" }}>
        ← Buildings
      </Link>

      <div style={{ display: "flex", alignItems: "center", gap: 12, margin: "8px 0 4px" }}>
        <h1 style={{ fontSize: 24, fontWeight: 700, margin: 0 }}>{building.name}</h1>
        <StatusBadge label={building.status} variant={statusVariant(building.status)} />
      </div>
      <p style={{ color: "var(--text-secondary)", marginBottom: 24, fontFamily: "monospace", fontSize: 13 }}>
        {building.building_reference}
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
        <h2 style={{ fontSize: 16, fontWeight: 700, margin: 0, marginBottom: 16 }}>Add a floor</h2>
        <div style={{ display: "grid", gap: 12, gridTemplateColumns: "2fr 1fr auto", alignItems: "end" }}>
          <div>
            <label style={{ fontSize: 12, color: "var(--text-secondary)", display: "block", marginBottom: 4 }}>
              Name
            </label>
            <input
              style={inputStyle}
              value={floorName}
              onChange={(e) => setFloorName(e.target.value)}
              placeholder="e.g. Ground Floor"
            />
          </div>
          <div>
            <label style={{ fontSize: 12, color: "var(--text-secondary)", display: "block", marginBottom: 4 }}>
              Level index
            </label>
            <input style={inputStyle} value={levelIndex} onChange={(e) => setLevelIndex(e.target.value)} placeholder="0" />
          </div>
          <button style={primaryBtn} onClick={onAddFloor} disabled={submitting}>
            {submitting ? "Adding…" : "Add"}
          </button>
        </div>
        {formError && <div style={{ color: "var(--color-critical)", fontSize: 13, marginTop: 10 }}>{formError}</div>}
      </div>

      <h2 style={{ fontSize: 16, fontWeight: 700, marginBottom: 12 }}>Floors</h2>
      {floors.length === 0 ? (
        <div style={{ color: "var(--text-secondary)", fontSize: 14, marginBottom: 24 }}>No floors yet.</div>
      ) : (
        <ul style={{ listStyle: "none", padding: 0, margin: "0 0 24px" }}>
          {floors.map((f) => (
            <li
              key={f.id}
              style={{
                padding: "10px 0",
                borderTop: "1px solid var(--border-subtle)",
                fontSize: 13,
                display: "flex",
                justifyContent: "space-between",
              }}
            >
              <span>{f.name}</span>
              <span style={{ color: "var(--text-secondary)" }}>
                {f.level_index !== null ? `Level ${f.level_index}` : "—"}
              </span>
            </li>
          ))}
        </ul>
      )}

      <h2 style={{ fontSize: 16, fontWeight: 700, marginBottom: 12 }}>Properties on this building</h2>
      {properties.length === 0 ? (
        <div style={{ color: "var(--text-secondary)", fontSize: 14 }}>None yet.</div>
      ) : (
        <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
          {properties.map((p) => (
            <li key={p.id} style={{ padding: "10px 0", borderTop: "1px solid var(--border-subtle)", fontSize: 13 }}>
              <Link href={`/properties/${p.id}`} style={{ color: "var(--color-primary)" }}>
                {p.property_reference}
              </Link>{" "}
              — {p.address}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
