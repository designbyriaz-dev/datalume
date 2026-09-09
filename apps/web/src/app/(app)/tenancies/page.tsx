"use client";

import { useEffect, useState } from "react";
import { inputStyle, primaryBtn } from "@/components/formStyles";
import { api, type TenantOut } from "@/lib/api";

const SELECTED_ORG_KEY = "datalume.selectedOrganisationId";

export default function TenanciesPage() {
  const [tenants, setTenants] = useState<TenantOut[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  function orgId(): string | null {
    return typeof window === "undefined" ? null : window.localStorage.getItem(SELECTED_ORG_KEY);
  }

  async function refresh() {
    const id = orgId();
    if (!id) return;
    setTenants(await api.listTenants(id));
  }

  useEffect(() => {
    (async () => {
      const id = orgId();
      if (!id) {
        setLoadError("No organisation selected.");
        return;
      }
      try {
        setTenants(await api.listTenants(id));
      } catch {
        setLoadError("Couldn't load tenants.");
      }
    })();
  }, []);

  async function onAddTenant() {
    const id = orgId();
    if (!id || !name.trim()) {
      setFormError("Give the tenant a name.");
      return;
    }
    setSubmitting(true);
    setFormError(null);
    try {
      const contact_details: Record<string, string> = {};
      if (email.trim()) contact_details.email = email.trim();
      if (phone.trim()) contact_details.phone = phone.trim();
      await api.createTenant(id, { name: name.trim(), contact_details });
      setName("");
      setEmail("");
      setPhone("");
      await refresh();
    } catch {
      setFormError("Couldn't add that tenant.");
    } finally {
      setSubmitting(false);
    }
  }

  if (loadError) {
    return <div style={{ color: "var(--text-secondary)" }}>{loadError}</div>;
  }

  if (!tenants) {
    return <div style={{ color: "var(--text-secondary)" }}>Loading…</div>;
  }

  return (
    <div style={{ maxWidth: 960 }}>
      <h1 style={{ fontSize: 24, fontWeight: 700, margin: 0, marginBottom: 4 }}>Tenancies</h1>
      <p style={{ color: "var(--text-secondary)", marginBottom: 24 }}>
        Tenants (occupiers) are recorded independently of any one lease — the same tenant can hold multiple leases
        over time. Attach a lease to a tenant and a property on the Leases page.
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
        <h2 style={{ fontSize: 16, fontWeight: 700, margin: 0, marginBottom: 16 }}>Add a tenant</h2>
        <div style={{ display: "grid", gap: 12, gridTemplateColumns: "1.5fr 1.5fr 1fr auto", alignItems: "end" }}>
          <div>
            <label htmlFor="tenant-name" style={{ fontSize: 12, color: "var(--text-secondary)", display: "block", marginBottom: 4 }}>Name</label>
            <input id="tenant-name" style={inputStyle} value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Acme Retail Ltd" />
          </div>
          <div>
            <label htmlFor="tenant-email" style={{ fontSize: 12, color: "var(--text-secondary)", display: "block", marginBottom: 4 }}>Email</label>
            <input id="tenant-email" style={inputStyle} value={email} onChange={(e) => setEmail(e.target.value)} placeholder="ops@acme.example" />
          </div>
          <div>
            <label htmlFor="tenant-phone" style={{ fontSize: 12, color: "var(--text-secondary)", display: "block", marginBottom: 4 }}>Phone</label>
            <input id="tenant-phone" style={inputStyle} value={phone} onChange={(e) => setPhone(e.target.value)} />
          </div>
          <button style={primaryBtn} onClick={onAddTenant} disabled={submitting}>
            {submitting ? "Adding…" : "Add"}
          </button>
        </div>
        {formError && <div style={{ color: "var(--color-critical)", fontSize: 13, marginTop: 10 }}>{formError}</div>}
      </div>

      <h2 style={{ fontSize: 16, fontWeight: 700, marginBottom: 12 }}>Tenants ({tenants.length})</h2>
      {tenants.length === 0 ? (
        <div style={{ color: "var(--text-secondary)", fontSize: 14 }}>No tenants added yet.</div>
      ) : (
        <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
          {tenants.map((t) => (
            <li key={t.id} style={{ padding: "10px 0", borderTop: "1px solid var(--border-subtle)", fontSize: 13 }}>
              <div style={{ fontWeight: 600 }}>{t.name}</div>
              {(t.contact_details.email || t.contact_details.phone) && (
                <div style={{ color: "var(--text-secondary)", marginTop: 2 }}>
                  {[t.contact_details.email, t.contact_details.phone].filter(Boolean).join(" · ")}
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
