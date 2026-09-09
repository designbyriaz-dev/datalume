"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { StatusBadge } from "@/components/StatusBadge";
import { inputStyle, primaryBtn } from "@/components/formStyles";
import { api, type DevelopmentOut } from "@/lib/api";

const SELECTED_ORG_KEY = "datalume.selectedOrganisationId";

function statusVariant(status: string) {
  if (status === "OPERATIONAL" || status === "COMPLETED") return "success" as const;
  if (status === "CANCELLED") return "critical" as const;
  return "neutral" as const;
}

export default function DevelopmentsPage() {
  const [developments, setDevelopments] = useState<DevelopmentOut[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [name, setName] = useState("");
  const [address, setAddress] = useState("");
  const [planningReference, setPlanningReference] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  function orgId(): string | null {
    return typeof window === "undefined" ? null : window.localStorage.getItem(SELECTED_ORG_KEY);
  }

  useEffect(() => {
    (async () => {
      const id = orgId();
      if (!id) {
        setLoadError("No organisation selected.");
        return;
      }
      try {
        setDevelopments(await api.listDevelopments(id));
      } catch {
        setLoadError("Couldn't load developments.");
      }
    })();
  }, []);

  async function onAdd() {
    const id = orgId();
    if (!id || !name.trim()) {
      setFormError("Give the development a name first.");
      return;
    }
    setSubmitting(true);
    setFormError(null);
    try {
      await api.createDevelopment(id, {
        name: name.trim(),
        address: address.trim() || undefined,
        planning_reference: planningReference.trim() || undefined,
      });
      setName("");
      setAddress("");
      setPlanningReference("");
      setDevelopments(await api.listDevelopments(id));
    } catch {
      setFormError("Couldn't add that development.");
    } finally {
      setSubmitting(false);
    }
  }

  if (loadError) {
    return <div style={{ color: "var(--text-secondary)" }}>{loadError}</div>;
  }

  return (
    <div style={{ maxWidth: 880 }}>
      <h1 style={{ fontSize: 24, fontWeight: 700, margin: 0, marginBottom: 4 }}>Developments</h1>
      <p style={{ color: "var(--text-secondary)", marginBottom: 24 }}>
        A development is optional context for buildings and properties — existing stock doesn&rsquo;t need one.
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
        <h2 style={{ fontSize: 16, fontWeight: 700, margin: 0, marginBottom: 16 }}>Add a development</h2>
        <div style={{ display: "grid", gap: 12, gridTemplateColumns: "2fr 2fr 1fr auto", alignItems: "end" }}>
          <div>
            <label htmlFor="development-name" style={{ fontSize: 12, color: "var(--text-secondary)", display: "block", marginBottom: 4 }}>
              Name
            </label>
            <input id="development-name" style={inputStyle} value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Riverside Gardens" />
          </div>
          <div>
            <label htmlFor="development-address" style={{ fontSize: 12, color: "var(--text-secondary)", display: "block", marginBottom: 4 }}>
              Address
            </label>
            <input id="development-address" style={inputStyle} value={address} onChange={(e) => setAddress(e.target.value)} />
          </div>
          <div>
            <label htmlFor="development-planning-ref" style={{ fontSize: 12, color: "var(--text-secondary)", display: "block", marginBottom: 4 }}>
              Planning ref.
            </label>
            <input id="development-planning-ref" style={inputStyle} value={planningReference} onChange={(e) => setPlanningReference(e.target.value)} />
          </div>
          <button style={primaryBtn} onClick={onAdd} disabled={submitting}>
            {submitting ? "Adding…" : "Add"}
          </button>
        </div>
        {formError && <div style={{ color: "var(--color-critical)", fontSize: 13, marginTop: 10 }}>{formError}</div>}
      </div>

      {developments === null ? (
        <div style={{ color: "var(--text-secondary)" }}>Loading…</div>
      ) : developments.length === 0 ? (
        <div style={{ color: "var(--text-secondary)", fontSize: 14 }}>No developments yet.</div>
      ) : (
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
          <thead>
            <tr style={{ textAlign: "left", color: "var(--text-secondary)" }}>
              <th style={{ padding: "8px" }}>Reference</th>
              <th style={{ padding: "8px" }}>Name</th>
              <th style={{ padding: "8px" }}>Address</th>
              <th style={{ padding: "8px" }}>Status</th>
            </tr>
          </thead>
          <tbody>
            {developments.map((d) => (
              <tr key={d.id} style={{ borderTop: "1px solid var(--border-subtle)" }}>
                <td style={{ padding: "8px", fontFamily: "monospace" }}>
                  <Link href={`/developments/${d.id}`} style={{ color: "var(--color-primary)" }}>
                    {d.development_reference}
                  </Link>
                </td>
                <td style={{ padding: "8px" }}>{d.name}</td>
                <td style={{ padding: "8px" }}>{d.address ?? "—"}</td>
                <td style={{ padding: "8px" }}>
                  <StatusBadge label={d.status} variant={statusVariant(d.status)} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
