"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { StatusBadge } from "@/components/StatusBadge";
import { inputStyle, primaryBtn } from "@/components/formStyles";
import { api, type BuildingOut, type PropertyOut } from "@/lib/api";

const SELECTED_ORG_KEY = "datalume.selectedOrganisationId";

function statusVariant(status: string) {
  if (status === "OPERATIONAL" || status === "OCCUPIED") return "success" as const;
  if (status === "VOID" || status === "DISPOSED") return "critical" as const;
  return "neutral" as const;
}

export default function PropertiesPage() {
  const [properties, setProperties] = useState<PropertyOut[] | null>(null);
  const [buildings, setBuildings] = useState<BuildingOut[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [address, setAddress] = useState("");
  const [postcode, setPostcode] = useState("");
  const [propertyType, setPropertyType] = useState("");
  const [buildingId, setBuildingId] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  function orgId(): string | null {
    return typeof window === "undefined" ? null : window.localStorage.getItem(SELECTED_ORG_KEY);
  }

  async function refresh() {
    const id = orgId();
    if (!id) return;
    setProperties(await api.listProperties(id));
  }

  useEffect(() => {
    (async () => {
      const id = orgId();
      if (!id) {
        setLoadError("No organisation selected.");
        return;
      }
      try {
        const [propertyList, buildingList] = await Promise.all([api.listProperties(id), api.listBuildings(id)]);
        setProperties(propertyList);
        setBuildings(buildingList);
      } catch {
        setLoadError("Couldn't load properties.");
      }
    })();
  }, []);

  async function onAddProperty() {
    const id = orgId();
    if (!id || !address.trim()) {
      setFormError("Give the property an address first.");
      return;
    }
    setSubmitting(true);
    setFormError(null);
    try {
      await api.createProperty(id, {
        address: address.trim(),
        postcode: postcode.trim() || undefined,
        property_type: propertyType.trim() || undefined,
        building_id: buildingId || undefined,
      });
      setAddress("");
      setPostcode("");
      setPropertyType("");
      setBuildingId("");
      await refresh();
    } catch {
      setFormError("Couldn't add that property.");
    } finally {
      setSubmitting(false);
    }
  }

  if (loadError) {
    return <div style={{ color: "var(--text-secondary)" }}>{loadError}</div>;
  }

  return (
    <div style={{ maxWidth: 880 }}>
      <h1 style={{ fontSize: 24, fontWeight: 700, margin: 0, marginBottom: 4 }}>Properties</h1>
      <p style={{ color: "var(--text-secondary)", marginBottom: 24 }}>
        Added manually here or imported via{" "}
        <Link href="/data-and-uploads" style={{ color: "var(--color-primary)" }}>
          Data & Uploads
        </Link>{" "}
        — both paths create the same kind of record.
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
        <h2 style={{ fontSize: 16, fontWeight: 700, margin: 0, marginBottom: 16 }}>Add a property</h2>
        <div style={{ display: "grid", gap: 12, gridTemplateColumns: "2fr 1fr 1fr 1.5fr auto", alignItems: "end" }}>
          <div>
            <label style={{ fontSize: 12, color: "var(--text-secondary)", display: "block", marginBottom: 4 }}>
              Address
            </label>
            <input style={inputStyle} value={address} onChange={(e) => setAddress(e.target.value)} />
          </div>
          <div>
            <label style={{ fontSize: 12, color: "var(--text-secondary)", display: "block", marginBottom: 4 }}>
              Postcode
            </label>
            <input style={inputStyle} value={postcode} onChange={(e) => setPostcode(e.target.value)} />
          </div>
          <div>
            <label style={{ fontSize: 12, color: "var(--text-secondary)", display: "block", marginBottom: 4 }}>
              Type
            </label>
            <input style={inputStyle} value={propertyType} onChange={(e) => setPropertyType(e.target.value)} />
          </div>
          <div>
            <label style={{ fontSize: 12, color: "var(--text-secondary)", display: "block", marginBottom: 4 }}>
              Building (optional)
            </label>
            <select style={inputStyle} value={buildingId} onChange={(e) => setBuildingId(e.target.value)}>
              <option value="">— None —</option>
              {buildings.map((b) => (
                <option key={b.id} value={b.id}>
                  {b.name}
                </option>
              ))}
            </select>
          </div>
          <button style={primaryBtn} onClick={onAddProperty} disabled={submitting}>
            {submitting ? "Adding…" : "Add"}
          </button>
        </div>
        {formError && (
          <div style={{ color: "var(--color-critical)", fontSize: 13, marginTop: 10 }}>{formError}</div>
        )}
      </div>

      {properties === null ? (
        <div style={{ color: "var(--text-secondary)" }}>Loading…</div>
      ) : properties.length === 0 ? (
        <div style={{ color: "var(--text-secondary)", fontSize: 14 }}>No properties yet.</div>
      ) : (
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
          <thead>
            <tr style={{ textAlign: "left", color: "var(--text-secondary)" }}>
              <th style={{ padding: "8px" }}>Reference</th>
              <th style={{ padding: "8px" }}>Address</th>
              <th style={{ padding: "8px" }}>Postcode</th>
              <th style={{ padding: "8px" }}>Type</th>
              <th style={{ padding: "8px" }}>Status</th>
              <th style={{ padding: "8px" }}>Source</th>
            </tr>
          </thead>
          <tbody>
            {properties.map((p) => (
              <tr key={p.id} style={{ borderTop: "1px solid var(--border-subtle)" }}>
                <td style={{ padding: "8px", fontFamily: "monospace" }}>
                  <Link href={`/properties/${p.id}`} style={{ color: "var(--color-primary)" }}>
                    {p.property_reference}
                  </Link>
                </td>
                <td style={{ padding: "8px" }}>{p.address}</td>
                <td style={{ padding: "8px" }}>{p.postcode ?? "—"}</td>
                <td style={{ padding: "8px" }}>{p.property_type ?? "—"}</td>
                <td style={{ padding: "8px" }}>
                  <StatusBadge label={p.status} variant={statusVariant(p.status)} />
                </td>
                <td style={{ padding: "8px", color: "var(--text-secondary)" }}>
                  {p.source_type === "FILE_UPLOAD" ? "Import" : "Manual"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
