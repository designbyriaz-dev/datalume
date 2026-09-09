"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { StatusBadge } from "@/components/StatusBadge";
import { inputStyle, primaryBtn } from "@/components/formStyles";
import { api, type BuildingOut, type PropertyOut, type SpaceOut } from "@/lib/api";

const SELECTED_ORG_KEY = "datalume.selectedOrganisationId";

// HANDED_OVER excluded — only app.development.service.authorise_handover
// can set that status, so offering it here would just produce a 400.
const PROPERTY_STATUSES = [
  "PLANNED",
  "UNDER_CONSTRUCTION",
  "READY_FOR_HANDOVER",
  "OPERATIONAL",
  "OCCUPIED",
  "VOID",
  "DISPOSED",
] as const;

function statusVariant(status: string) {
  if (status === "OPERATIONAL" || status === "OCCUPIED") return "success" as const;
  if (status === "VOID" || status === "DISPOSED") return "critical" as const;
  return "neutral" as const;
}

export function PropertyDetailClient({ propertyId }: { propertyId: string }) {
  const [property, setProperty] = useState<PropertyOut | null>(null);
  const [spaces, setSpaces] = useState<SpaceOut[] | null>(null);
  const [building, setBuilding] = useState<BuildingOut | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [spaceName, setSpaceName] = useState("");
  const [spaceType, setSpaceType] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  const [statusUpdating, setStatusUpdating] = useState(false);
  const [statusError, setStatusError] = useState<string | null>(null);

  function orgId(): string | null {
    return typeof window === "undefined" ? null : window.localStorage.getItem(SELECTED_ORG_KEY);
  }

  async function refreshSpaces() {
    const id = orgId();
    if (!id) return;
    setSpaces(await api.listSpaces(id, propertyId));
  }

  useEffect(() => {
    (async () => {
      const id = orgId();
      if (!id) {
        setLoadError("No organisation selected.");
        return;
      }
      try {
        const [prop, spaceList] = await Promise.all([
          api.getProperty(id, propertyId),
          api.listSpaces(id, propertyId),
        ]);
        setProperty(prop);
        setSpaces(spaceList);
        if (prop.building_id) {
          setBuilding(await api.getBuilding(id, prop.building_id));
        }
      } catch {
        setLoadError("Couldn't load this property.");
      }
    })();
  }, [propertyId]);

  async function onAddSpace() {
    const id = orgId();
    if (!id || !spaceName.trim()) {
      setFormError("Give the space a name first.");
      return;
    }
    setSubmitting(true);
    setFormError(null);
    try {
      await api.createSpace(id, propertyId, {
        name: spaceName.trim(),
        space_type: spaceType.trim() || undefined,
      });
      setSpaceName("");
      setSpaceType("");
      await refreshSpaces();
    } catch {
      setFormError("Couldn't add that space.");
    } finally {
      setSubmitting(false);
    }
  }

  async function onChangeStatus(newStatus: string) {
    const id = orgId();
    if (!id || newStatus === property?.status) return;
    setStatusUpdating(true);
    setStatusError(null);
    try {
      setProperty(await api.updatePropertyStatus(id, propertyId, newStatus));
    } catch (err) {
      setStatusError(err instanceof Error && err.message ? err.message : "Couldn't update status.");
    } finally {
      setStatusUpdating(false);
    }
  }

  if (loadError) {
    return <div style={{ color: "var(--text-secondary)" }}>{loadError}</div>;
  }

  if (!property) {
    return <div style={{ color: "var(--text-secondary)" }}>Loading…</div>;
  }

  return (
    <div style={{ maxWidth: 720 }}>
      <Link href="/properties" style={{ fontSize: 13, color: "var(--color-primary)" }}>
        ← Properties
      </Link>

      <div style={{ display: "flex", alignItems: "center", gap: 12, margin: "8px 0 4px" }}>
        <h1 style={{ fontSize: 24, fontWeight: 700, margin: 0 }}>{property.address}</h1>
        <StatusBadge label={property.status} variant={statusVariant(property.status)} />
      </div>
      <p style={{ color: "var(--text-secondary)", marginBottom: 8, fontFamily: "monospace", fontSize: 13 }}>
        {property.property_reference}
      </p>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 24 }}>
        <label style={{ fontSize: 12, color: "var(--text-secondary)" }}>Change status:</label>
        <select
          style={{ ...inputStyle, width: "auto", padding: "4px 8px", fontSize: 12 }}
          value={property.status}
          disabled={statusUpdating}
          onChange={(e) => onChangeStatus(e.target.value)}
        >
          {property.status === "HANDED_OVER" && <option value="HANDED_OVER">HANDED_OVER</option>}
          {PROPERTY_STATUSES.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
        {statusError && <span style={{ color: "var(--color-critical)", fontSize: 12 }}>{statusError}</span>}
      </div>

      <div
        style={{
          background: "var(--bg-card)",
          border: "1px solid var(--border-subtle)",
          borderRadius: "var(--radius-card)",
          padding: 20,
          marginBottom: 24,
          display: "grid",
          gridTemplateColumns: "repeat(2, 1fr)",
          gap: 16,
          fontSize: 13,
        }}
      >
        <div>
          <div style={{ color: "var(--text-secondary)", marginBottom: 2 }}>Postcode</div>
          <div>{property.postcode ?? "—"}</div>
        </div>
        <div>
          <div style={{ color: "var(--text-secondary)", marginBottom: 2 }}>UPRN</div>
          <div>{property.uprn ?? "—"}</div>
        </div>
        <div>
          <div style={{ color: "var(--text-secondary)", marginBottom: 2 }}>Type</div>
          <div>{property.property_type ?? "—"}</div>
        </div>
        <div>
          <div style={{ color: "var(--text-secondary)", marginBottom: 2 }}>Building</div>
          <div>
            {building ? (
              <Link href={`/buildings/${building.id}`} style={{ color: "var(--color-primary)" }}>
                {building.name}
              </Link>
            ) : (
              "—"
            )}
          </div>
        </div>
        <div>
          <div style={{ color: "var(--text-secondary)", marginBottom: 2 }}>Source</div>
          <div>
            {property.source_type === "FILE_UPLOAD" ? "Imported" : "Manual"}
            {property.original_reference ? ` (${property.original_reference})` : ""}
          </div>
        </div>
      </div>

      <h2 style={{ fontSize: 16, fontWeight: 700, marginBottom: 12 }}>Spaces</h2>
      <div
        style={{
          background: "var(--bg-card)",
          border: "1px solid var(--border-subtle)",
          borderRadius: "var(--radius-card)",
          padding: 20,
          marginBottom: 16,
        }}
      >
        <div style={{ display: "grid", gap: 12, gridTemplateColumns: "2fr 1fr auto", alignItems: "end" }}>
          <div>
            <label style={{ fontSize: 12, color: "var(--text-secondary)", display: "block", marginBottom: 4 }}>
              Name
            </label>
            <input
              style={inputStyle}
              value={spaceName}
              onChange={(e) => setSpaceName(e.target.value)}
              placeholder="e.g. Kitchen"
            />
          </div>
          <div>
            <label style={{ fontSize: 12, color: "var(--text-secondary)", display: "block", marginBottom: 4 }}>
              Type
            </label>
            <input style={inputStyle} value={spaceType} onChange={(e) => setSpaceType(e.target.value)} />
          </div>
          <button style={primaryBtn} onClick={onAddSpace} disabled={submitting}>
            {submitting ? "Adding…" : "Add"}
          </button>
        </div>
        {formError && (
          <div style={{ color: "var(--color-critical)", fontSize: 13, marginTop: 10 }}>{formError}</div>
        )}
      </div>

      {spaces === null ? (
        <div style={{ color: "var(--text-secondary)" }}>Loading…</div>
      ) : spaces.length === 0 ? (
        <div style={{ color: "var(--text-secondary)", fontSize: 14 }}>No spaces recorded yet.</div>
      ) : (
        <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
          {spaces.map((s) => (
            <li
              key={s.id}
              style={{
                padding: "10px 0",
                borderTop: "1px solid var(--border-subtle)",
                fontSize: 13,
                display: "flex",
                justifyContent: "space-between",
              }}
            >
              <span>{s.name}</span>
              <span style={{ color: "var(--text-secondary)" }}>{s.space_type ?? "—"}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
