"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { StatusBadge } from "@/components/StatusBadge";
import { inputStyle, primaryBtn } from "@/components/formStyles";
import { api, type ComponentOut, type ComponentType } from "@/lib/api";

const SELECTED_ORG_KEY = "datalume.selectedOrganisationId";

function statusVariant(status: string) {
  if (status === "ACTIVE") return "success" as const;
  if (status === "DISPOSED") return "critical" as const;
  return "neutral" as const;
}

export default function ComponentsPage() {
  const [components, setComponents] = useState<ComponentOut[] | null>(null);
  const [types, setTypes] = useState<ComponentType[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [componentTypeId, setComponentTypeId] = useState("");
  const [manufacturer, setManufacturer] = useState("");
  const [model, setModel] = useState("");
  const [serialNumber, setSerialNumber] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  function orgId(): string | null {
    return typeof window === "undefined" ? null : window.localStorage.getItem(SELECTED_ORG_KEY);
  }

  async function refresh() {
    const id = orgId();
    if (!id) return;
    setComponents(await api.listComponents(id));
  }

  useEffect(() => {
    (async () => {
      const id = orgId();
      if (!id) {
        setLoadError("No organisation selected.");
        return;
      }
      try {
        const [componentList, typeList] = await Promise.all([api.listComponents(id), api.listComponentTypes(id)]);
        setComponents(componentList);
        setTypes(typeList);
        if (typeList[0]) setComponentTypeId(typeList[0].id);
      } catch {
        setLoadError("Couldn't load components.");
      }
    })();
  }, []);

  async function onAdd() {
    const id = orgId();
    if (!id || !componentTypeId) {
      setFormError("Choose a component type first.");
      return;
    }
    setSubmitting(true);
    setFormError(null);
    try {
      await api.createComponent(id, {
        component_type_id: componentTypeId,
        manufacturer: manufacturer.trim() || undefined,
        model: model.trim() || undefined,
        serial_number: serialNumber.trim() || undefined,
      });
      setManufacturer("");
      setModel("");
      setSerialNumber("");
      await refresh();
    } catch {
      setFormError("Couldn't add that component.");
    } finally {
      setSubmitting(false);
    }
  }

  if (loadError) {
    return <div style={{ color: "var(--text-secondary)" }}>{loadError}</div>;
  }

  return (
    <div style={{ maxWidth: 960 }}>
      <h1 style={{ fontSize: 24, fontWeight: 700, margin: 0, marginBottom: 4 }}>Components</h1>
      <p style={{ color: "var(--text-secondary)", marginBottom: 24 }}>
        Boilers, fire doors, lifts and every other asset DataLume tracks — added manually here or imported
        via{" "}
        <Link href="/data-and-uploads" style={{ color: "var(--color-primary)" }}>
          Data &amp; Uploads
        </Link>
        .
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
        <h2 style={{ fontSize: 16, fontWeight: 700, margin: 0, marginBottom: 16 }}>Add a component</h2>
        <div style={{ display: "grid", gap: 12, gridTemplateColumns: "1.5fr 1fr 1fr 1fr auto", alignItems: "end" }}>
          <div>
            <label htmlFor="component-type" style={{ fontSize: 12, color: "var(--text-secondary)", display: "block", marginBottom: 4 }}>
              Type
            </label>
            <select id="component-type" style={inputStyle} value={componentTypeId} onChange={(e) => setComponentTypeId(e.target.value)}>
              {types.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.name}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label htmlFor="component-manufacturer" style={{ fontSize: 12, color: "var(--text-secondary)", display: "block", marginBottom: 4 }}>
              Manufacturer
            </label>
            <input id="component-manufacturer" style={inputStyle} value={manufacturer} onChange={(e) => setManufacturer(e.target.value)} />
          </div>
          <div>
            <label htmlFor="component-model" style={{ fontSize: 12, color: "var(--text-secondary)", display: "block", marginBottom: 4 }}>
              Model
            </label>
            <input id="component-model" style={inputStyle} value={model} onChange={(e) => setModel(e.target.value)} />
          </div>
          <div>
            <label htmlFor="component-serial" style={{ fontSize: 12, color: "var(--text-secondary)", display: "block", marginBottom: 4 }}>
              Serial number
            </label>
            <input id="component-serial" style={inputStyle} value={serialNumber} onChange={(e) => setSerialNumber(e.target.value)} />
          </div>
          <button style={primaryBtn} onClick={onAdd} disabled={submitting}>
            {submitting ? "Adding…" : "Add"}
          </button>
        </div>
        {formError && (
          <div style={{ color: "var(--color-critical)", fontSize: 13, marginTop: 10 }}>{formError}</div>
        )}
      </div>

      {components === null ? (
        <div style={{ color: "var(--text-secondary)" }}>Loading…</div>
      ) : components.length === 0 ? (
        <div style={{ color: "var(--text-secondary)", fontSize: 14 }}>No components yet.</div>
      ) : (
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
          <thead>
            <tr style={{ textAlign: "left", color: "var(--text-secondary)" }}>
              <th style={{ padding: "8px" }}>Reference</th>
              <th style={{ padding: "8px" }}>Type</th>
              <th style={{ padding: "8px" }}>Manufacturer</th>
              <th style={{ padding: "8px" }}>Model</th>
              <th style={{ padding: "8px" }}>Serial</th>
              <th style={{ padding: "8px" }}>Status</th>
              <th style={{ padding: "8px" }}>Source</th>
            </tr>
          </thead>
          <tbody>
            {components.map((c) => (
              <tr key={c.id} style={{ borderTop: "1px solid var(--border-subtle)" }}>
                <td style={{ padding: "8px", fontFamily: "monospace" }}>
                  <Link href={`/components/${c.id}`} style={{ color: "var(--color-primary)" }}>
                    {c.component_reference}
                  </Link>
                </td>
                <td style={{ padding: "8px" }}>{c.component_type_name}</td>
                <td style={{ padding: "8px" }}>{c.manufacturer ?? "—"}</td>
                <td style={{ padding: "8px" }}>{c.model ?? "—"}</td>
                <td style={{ padding: "8px" }}>{c.serial_number ?? "—"}</td>
                <td style={{ padding: "8px" }}>
                  <StatusBadge label={c.status} variant={statusVariant(c.status)} />
                </td>
                <td style={{ padding: "8px", color: "var(--text-secondary)" }}>
                  {c.source_type === "FILE_UPLOAD" ? "Import" : "Manual"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
