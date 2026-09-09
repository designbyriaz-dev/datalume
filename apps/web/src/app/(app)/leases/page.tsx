"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { StatusBadge } from "@/components/StatusBadge";
import { inputStyle, primaryBtn } from "@/components/formStyles";
import { api, type LeaseOut, type PropertyOut, type TenantOut } from "@/lib/api";

const SELECTED_ORG_KEY = "datalume.selectedOrganisationId";

const RENT_FREQUENCIES = ["WEEKLY", "MONTHLY", "QUARTERLY", "ANNUALLY"] as const;

const LEASE_TRANSITIONS: Record<string, string[]> = {
  DRAFT: ["ACTIVE", "TERMINATED"],
  ACTIVE: ["EXPIRED", "TERMINATED", "RENEWED"],
  EXPIRED: [],
  TERMINATED: [],
  RENEWED: [],
};

const OCCUPANCY_OPTIONS = ["OCCUPIED", "NOTICE_GIVEN", "VACANT"] as const;

function leaseStatusVariant(status: string) {
  if (status === "ACTIVE" || status === "RENEWED") return "success" as const;
  if (status === "TERMINATED") return "critical" as const;
  if (status === "EXPIRED") return "warning" as const;
  return "neutral" as const;
}

function occupancyVariant(status: string) {
  if (status === "OCCUPIED") return "success" as const;
  if (status === "NOTICE_GIVEN") return "warning" as const;
  return "neutral" as const;
}

function formatRent(pence: number, frequency: string) {
  return `£${(pence / 100).toFixed(2)} / ${frequency.toLowerCase()}`;
}

export default function LeasesPage() {
  const [leases, setLeases] = useState<LeaseOut[] | null>(null);
  const [properties, setProperties] = useState<PropertyOut[] | null>(null);
  const [tenants, setTenants] = useState<TenantOut[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [propertyId, setPropertyId] = useState("");
  const [tenantId, setTenantId] = useState("");
  const [leaseStart, setLeaseStart] = useState("");
  const [leaseExpiry, setLeaseExpiry] = useState("");
  const [rentAmount, setRentAmount] = useState("");
  const [rentFrequency, setRentFrequency] = useState<(typeof RENT_FREQUENCIES)[number]>("MONTHLY");
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  function orgId(): string | null {
    return typeof window === "undefined" ? null : window.localStorage.getItem(SELECTED_ORG_KEY);
  }

  async function refreshLeases() {
    const id = orgId();
    if (!id) return;
    setLeases(await api.listLeases(id));
  }

  useEffect(() => {
    (async () => {
      const id = orgId();
      if (!id) {
        setLoadError("No organisation selected.");
        return;
      }
      try {
        const [leaseList, propertyList, tenantList] = await Promise.all([
          api.listLeases(id),
          api.listProperties(id),
          api.listTenants(id),
        ]);
        setLeases(leaseList);
        setProperties(propertyList);
        setTenants(tenantList);
        if (propertyList[0]) setPropertyId(propertyList[0].id);
        if (tenantList[0]) setTenantId(tenantList[0].id);
      } catch {
        setLoadError("Couldn't load leases.");
      }
    })();
  }, []);

  async function onAddLease() {
    const id = orgId();
    if (!id || !propertyId || !tenantId || !leaseStart || !leaseExpiry || !rentAmount) {
      setFormError("Fill in property, tenant, lease dates, and rent.");
      return;
    }
    const pence = Math.round(parseFloat(rentAmount) * 100);
    if (Number.isNaN(pence) || pence <= 0) {
      setFormError("Rent must be a positive amount.");
      return;
    }
    setSubmitting(true);
    setFormError(null);
    try {
      await api.createLease(id, {
        property_id: propertyId,
        tenant_id: tenantId,
        lease_start: leaseStart,
        lease_expiry: leaseExpiry,
        contractual_rent_pence: pence,
        rent_frequency: rentFrequency,
      });
      setLeaseStart("");
      setLeaseExpiry("");
      setRentAmount("");
      await refreshLeases();
    } catch {
      setFormError("Couldn't add that lease.");
    } finally {
      setSubmitting(false);
    }
  }

  async function onStatusChange(leaseId: string, nextStatus: string) {
    const id = orgId();
    if (!id) return;
    await api.updateLeaseStatus(id, leaseId, nextStatus);
    await refreshLeases();
  }

  async function onOccupancyChange(leaseId: string, occupancyStatus: string) {
    const id = orgId();
    if (!id) return;
    await api.updateLeaseOccupancy(id, leaseId, occupancyStatus);
    await refreshLeases();
  }

  if (loadError) {
    return <div style={{ color: "var(--text-secondary)" }}>{loadError}</div>;
  }

  if (!leases || !properties || !tenants) {
    return <div style={{ color: "var(--text-secondary)" }}>Loading…</div>;
  }

  const propertyAddress = (id: string) => properties.find((p) => p.id === id)?.address ?? id.slice(0, 8);
  const tenantName = (id: string) => tenants.find((t) => t.id === id)?.name ?? id.slice(0, 8);

  return (
    <div style={{ maxWidth: 960 }}>
      <h1 style={{ fontSize: 24, fontWeight: 700, margin: 0, marginBottom: 4 }}>Leases</h1>
      <p style={{ color: "var(--text-secondary)", marginBottom: 24 }}>
        Every lease starts as a draft and moves through an enforced status workflow. Occupancy is a separate,
        freely-settable snapshot of who&rsquo;s physically there right now.
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
        <h2 style={{ fontSize: 16, fontWeight: 700, margin: 0, marginBottom: 16 }}>Add a lease</h2>
        <div style={{ display: "grid", gap: 12, gridTemplateColumns: "1.3fr 1.3fr 1fr 1fr 1fr 1fr auto", alignItems: "end" }}>
          <div>
            <label htmlFor="lease-property" style={{ fontSize: 12, color: "var(--text-secondary)", display: "block", marginBottom: 4 }}>Property</label>
            <select id="lease-property" style={inputStyle} value={propertyId} onChange={(e) => setPropertyId(e.target.value)}>
              {properties.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.address}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label htmlFor="lease-tenant" style={{ fontSize: 12, color: "var(--text-secondary)", display: "block", marginBottom: 4 }}>Tenant</label>
            <select id="lease-tenant" style={inputStyle} value={tenantId} onChange={(e) => setTenantId(e.target.value)}>
              {tenants.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.name}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label htmlFor="lease-start" style={{ fontSize: 12, color: "var(--text-secondary)", display: "block", marginBottom: 4 }}>Start</label>
            <input id="lease-start" style={inputStyle} type="date" value={leaseStart} onChange={(e) => setLeaseStart(e.target.value)} />
          </div>
          <div>
            <label htmlFor="lease-expiry" style={{ fontSize: 12, color: "var(--text-secondary)", display: "block", marginBottom: 4 }}>Expiry</label>
            <input id="lease-expiry" style={inputStyle} type="date" value={leaseExpiry} onChange={(e) => setLeaseExpiry(e.target.value)} />
          </div>
          <div>
            <label htmlFor="lease-rent" style={{ fontSize: 12, color: "var(--text-secondary)", display: "block", marginBottom: 4 }}>Rent (£)</label>
            <input id="lease-rent" style={inputStyle} type="number" min="0" step="0.01" value={rentAmount} onChange={(e) => setRentAmount(e.target.value)} />
          </div>
          <div>
            <label htmlFor="lease-frequency" style={{ fontSize: 12, color: "var(--text-secondary)", display: "block", marginBottom: 4 }}>Frequency</label>
            <select id="lease-frequency" style={inputStyle} value={rentFrequency} onChange={(e) => setRentFrequency(e.target.value as (typeof RENT_FREQUENCIES)[number])}>
              {RENT_FREQUENCIES.map((f) => (
                <option key={f} value={f}>
                  {f}
                </option>
              ))}
            </select>
          </div>
          <button style={primaryBtn} onClick={onAddLease} disabled={submitting}>
            {submitting ? "Adding…" : "Add"}
          </button>
        </div>
        {(properties.length === 0 || tenants.length === 0) && (
          <div style={{ color: "var(--text-secondary)", fontSize: 13, marginTop: 10 }}>
            Add a property and a tenant first before creating a lease.
          </div>
        )}
        {formError && <div style={{ color: "var(--color-critical)", fontSize: 13, marginTop: 10 }}>{formError}</div>}
      </div>

      <h2 style={{ fontSize: 16, fontWeight: 700, marginBottom: 12 }}>Register</h2>
      {leases.length === 0 ? (
        <div style={{ color: "var(--text-secondary)", fontSize: 14 }}>No leases recorded yet.</div>
      ) : (
        <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
          {leases.map((l) => (
            <li key={l.id} style={{ padding: "12px 0", borderTop: "1px solid var(--border-subtle)", fontSize: 13 }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6, flexWrap: "wrap", gap: 8 }}>
                <span>
                  <span style={{ fontFamily: "monospace", color: "var(--text-secondary)", marginRight: 8 }}>{l.lease_reference}</span>
                  <Link href={`/properties/${l.property_id}`} style={{ color: "var(--color-primary)" }}>
                    {propertyAddress(l.property_id)}
                  </Link>
                  {" · "}
                  {tenantName(l.tenant_id)}
                </span>
                <span style={{ display: "flex", gap: 6 }}>
                  <StatusBadge label={l.lease_status} variant={leaseStatusVariant(l.lease_status)} />
                  <StatusBadge label={l.occupancy_status.replace(/_/g, " ")} variant={occupancyVariant(l.occupancy_status)} />
                </span>
              </div>
              <div style={{ color: "var(--text-secondary)", marginBottom: 8 }}>
                {l.lease_start} → {l.lease_expiry} · {formatRent(l.contractual_rent_pence, l.rent_frequency)}
              </div>
              <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                {(LEASE_TRANSITIONS[l.lease_status] ?? []).map((next) => (
                  <button key={next} style={{ ...primaryBtn, padding: "4px 10px", fontSize: 12 }} onClick={() => onStatusChange(l.id, next)}>
                    {next.toLowerCase()}
                  </button>
                ))}
                {OCCUPANCY_OPTIONS.filter((o) => o !== l.occupancy_status).map((o) => (
                  <button
                    key={o}
                    style={{ ...primaryBtn, padding: "4px 10px", fontSize: 12, background: "var(--text-secondary)" }}
                    onClick={() => onOccupancyChange(l.id, o)}
                  >
                    mark {o.replace(/_/g, " ").toLowerCase()}
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
