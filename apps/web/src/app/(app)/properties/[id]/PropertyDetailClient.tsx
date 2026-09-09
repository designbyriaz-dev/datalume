"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { StatusBadge } from "@/components/StatusBadge";
import { inputStyle, primaryBtn } from "@/components/formStyles";
import { api, type Property360, type SpaceOut } from "@/lib/api";

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

function severityVariant(severity: string) {
  if (severity === "HIGH") return "critical" as const;
  if (severity === "MEDIUM") return "warning" as const;
  return "neutral" as const;
}

function repairPriorityVariant(priority: string) {
  if (priority === "EMERGENCY") return "critical" as const;
  if (priority === "URGENT") return "warning" as const;
  return "neutral" as const;
}

function repairStatusVariant(status: string) {
  if (status === "COMPLETED") return "success" as const;
  if (status === "CANCELLED") return "critical" as const;
  return "neutral" as const;
}

export function PropertyDetailClient({ propertyId }: { propertyId: string }) {
  const [view, setView] = useState<Property360 | null>(null);
  const [spaces, setSpaces] = useState<SpaceOut[] | null>(null);
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

  async function refresh360() {
    const id = orgId();
    if (!id) return;
    setView(await api.getProperty360(id, propertyId));
  }

  useEffect(() => {
    (async () => {
      const id = orgId();
      if (!id) {
        setLoadError("No organisation selected.");
        return;
      }
      try {
        const [view360, spaceList] = await Promise.all([api.getProperty360(id, propertyId), api.listSpaces(id, propertyId)]);
        setView(view360);
        setSpaces(spaceList);
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
    if (!id || newStatus === view?.property.status) return;
    setStatusUpdating(true);
    setStatusError(null);
    try {
      await api.updatePropertyStatus(id, propertyId, newStatus);
      await refresh360();
    } catch (err) {
      setStatusError(err instanceof Error && err.message ? err.message : "Couldn't update status.");
    } finally {
      setStatusUpdating(false);
    }
  }

  if (loadError) {
    return <div style={{ color: "var(--text-secondary)" }}>{loadError}</div>;
  }

  if (!view || !spaces) {
    return <div style={{ color: "var(--text-secondary)" }}>Loading…</div>;
  }

  const { property, development, building, floor } = view;

  return (
    <div style={{ maxWidth: 860 }}>
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
        <label htmlFor="property-status" style={{ fontSize: 12, color: "var(--text-secondary)" }}>Change status:</label>
        <select
          id="property-status"
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
          <div style={{ color: "var(--text-secondary)", marginBottom: 2 }}>Development history</div>
          <div>
            {development ? (
              <Link href={`/developments/${development.id}`} style={{ color: "var(--color-primary)" }}>
                {development.name}
              </Link>
            ) : (
              "—"
            )}
            {building && (
              <>
                {" → "}
                <Link href={`/buildings/${building.id}`} style={{ color: "var(--color-primary)" }}>
                  {building.name}
                </Link>
              </>
            )}
            {floor && ` → ${floor.name}`}
          </div>
        </div>
        <div>
          <div style={{ color: "var(--text-secondary)", marginBottom: 2 }}>Source</div>
          <div>
            {property.source_type === "FILE_UPLOAD" ? "Imported" : "Manual"}
            {property.original_reference ? ` (${property.original_reference})` : ""}
          </div>
        </div>
        <div>
          <div style={{ color: "var(--text-secondary)", marginBottom: 2 }}>Handover</div>
          <div>
            {view.handover_record
              ? `${view.handover_record.readiness_score_pct}% at handover${view.handover_record.override_reason ? " (override)" : ""}`
              : "Not yet handed over"}
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
            <label htmlFor="space-name" style={{ fontSize: 12, color: "var(--text-secondary)", display: "block", marginBottom: 4 }}>
              Name
            </label>
            <input
              id="space-name"
              style={inputStyle}
              value={spaceName}
              onChange={(e) => setSpaceName(e.target.value)}
              placeholder="e.g. Kitchen"
            />
          </div>
          <div>
            <label htmlFor="space-type" style={{ fontSize: 12, color: "var(--text-secondary)", display: "block", marginBottom: 4 }}>
              Type
            </label>
            <input id="space-type" style={inputStyle} value={spaceType} onChange={(e) => setSpaceType(e.target.value)} />
          </div>
          <button style={primaryBtn} onClick={onAddSpace} disabled={submitting}>
            {submitting ? "Adding…" : "Add"}
          </button>
        </div>
        {formError && (
          <div style={{ color: "var(--color-critical)", fontSize: 13, marginTop: 10 }}>{formError}</div>
        )}
      </div>

      {spaces.length === 0 ? (
        <div style={{ color: "var(--text-secondary)", fontSize: 14, marginBottom: 24 }}>No spaces recorded yet.</div>
      ) : (
        <ul style={{ listStyle: "none", padding: 0, margin: "0 0 24px" }}>
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

      <h2 style={{ fontSize: 16, fontWeight: 700, marginBottom: 12 }}>Components</h2>
      {view.components.length === 0 ? (
        <div style={{ color: "var(--text-secondary)", fontSize: 14, marginBottom: 24 }}>No components yet.</div>
      ) : (
        <div style={{ display: "grid", gap: 12, marginBottom: 24 }}>
          {view.components.map((c) => (
            <div
              key={c.id}
              style={{
                background: "var(--bg-card)",
                border: "1px solid var(--border-subtle)",
                borderRadius: "var(--radius-card)",
                padding: 16,
                fontSize: 13,
              }}
            >
              <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 6 }}>
                <Link href={`/components/${c.id}`} style={{ color: "var(--color-primary)", fontWeight: 700 }}>
                  {c.component_reference} — {c.component_type_name}
                </Link>
                <StatusBadge label={c.status} variant={c.status === "ACTIVE" ? "success" : "neutral"} />
              </div>
              <div style={{ color: "var(--text-secondary)" }}>
                Specs: {c.specifications.length === 0 ? "none" : c.specifications.map((s) => s.title).join(", ")} ·
                Evidence: {c.evidence.length === 0 ? "none" : c.evidence.length} · Changes:{" "}
                {c.changes.length === 0 ? "none" : c.changes.length}
              </div>
            </div>
          ))}
        </div>
      )}

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 24, marginBottom: 24 }}>
        <div>
          <h2 style={{ fontSize: 16, fontWeight: 700, marginBottom: 12 }}>Warranties</h2>
          {view.warranties.length === 0 ? (
            <div style={{ color: "var(--text-secondary)", fontSize: 13 }}>None.</div>
          ) : (
            <ul style={{ listStyle: "none", padding: 0, margin: 0, fontSize: 13 }}>
              {view.warranties.map((w) => (
                <li key={w.id} style={{ padding: "6px 0", borderTop: "1px solid var(--border-subtle)" }}>
                  {w.provider} — {w.warranty_type}
                  <span style={{ color: "var(--text-secondary)" }}>
                    {" "}
                    ({w.is_expired ? "expired" : `${w.days_until_expiry}d left`})
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>
        <div>
          <h2 style={{ fontSize: 16, fontWeight: 700, marginBottom: 12 }}>Defects</h2>
          {view.defects.length === 0 ? (
            <div style={{ color: "var(--text-secondary)", fontSize: 13 }}>None.</div>
          ) : (
            <ul style={{ listStyle: "none", padding: 0, margin: 0, fontSize: 13 }}>
              {view.defects.map((d) => (
                <li
                  key={d.id}
                  style={{
                    padding: "6px 0",
                    borderTop: "1px solid var(--border-subtle)",
                    display: "flex",
                    justifyContent: "space-between",
                    gap: 8,
                  }}
                >
                  <span>{d.category}</span>
                  <span style={{ display: "flex", gap: 4 }}>
                    <StatusBadge label={d.severity} variant={severityVariant(d.severity)} />
                    <StatusBadge label={d.status} variant={d.status === "CLOSED" || d.status === "COMPLETED" ? "success" : "neutral"} />
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>

      <h2 style={{ fontSize: 16, fontWeight: 700, marginBottom: 12 }}>
        Repairs · <Link href="/repairs" style={{ color: "var(--color-primary)", fontWeight: 400, fontSize: 13 }}>Report one →</Link>
      </h2>
      {view.repairs.length === 0 ? (
        <div style={{ color: "var(--text-secondary)", fontSize: 14, marginBottom: 24 }}>None.</div>
      ) : (
        <ul style={{ listStyle: "none", padding: 0, margin: "0 0 24px", fontSize: 13 }}>
          {view.repairs.map((r) => (
            <li
              key={r.id}
              style={{
                padding: "6px 0",
                borderTop: "1px solid var(--border-subtle)",
                display: "flex",
                justifyContent: "space-between",
                gap: 8,
              }}
            >
              <span>
                <span style={{ fontFamily: "monospace", color: "var(--text-secondary)", marginRight: 8 }}>
                  {r.repair_reference}
                </span>
                {r.category}
              </span>
              <span style={{ display: "flex", gap: 4 }}>
                <StatusBadge label={r.priority} variant={repairPriorityVariant(r.priority)} />
                <StatusBadge label={r.status} variant={repairStatusVariant(r.status)} />
              </span>
            </li>
          ))}
        </ul>
      )}

      <h2 style={{ fontSize: 16, fontWeight: 700, marginBottom: 12 }}>
        Leases · <Link href="/leases" style={{ color: "var(--color-primary)", fontWeight: 400, fontSize: 13 }}>Manage →</Link>
      </h2>
      {view.leases.length === 0 ? (
        <div style={{ color: "var(--text-secondary)", fontSize: 14, marginBottom: 24 }}>None.</div>
      ) : (
        <ul style={{ listStyle: "none", padding: 0, margin: "0 0 24px", fontSize: 13 }}>
          {view.leases.map((l) => (
            <li
              key={l.id}
              style={{
                padding: "6px 0",
                borderTop: "1px solid var(--border-subtle)",
                display: "flex",
                justifyContent: "space-between",
                gap: 8,
              }}
            >
              <span>
                <span style={{ fontFamily: "monospace", color: "var(--text-secondary)", marginRight: 8 }}>
                  {l.lease_reference}
                </span>
                {l.lease_start} → {l.lease_expiry} · £{(l.contractual_rent_pence / 100).toFixed(2)} / {l.rent_frequency.toLowerCase()}
              </span>
              <span style={{ display: "flex", gap: 4 }}>
                <StatusBadge
                  label={l.lease_status}
                  variant={l.lease_status === "ACTIVE" || l.lease_status === "RENEWED" ? "success" : l.lease_status === "TERMINATED" ? "critical" : "neutral"}
                />
              </span>
            </li>
          ))}
        </ul>
      )}

      <h2 style={{ fontSize: 16, fontWeight: 700, marginBottom: 12 }}>Data Health</h2>
      {view.data_health_findings.length === 0 ? (
        <div style={{ color: "var(--text-secondary)", fontSize: 14, marginBottom: 24 }}>No issues found.</div>
      ) : (
        <ul style={{ listStyle: "none", padding: 0, margin: "0 0 24px", fontSize: 13 }}>
          {view.data_health_findings.map((f, i) => (
            <li key={i} style={{ padding: "6px 0", borderTop: "1px solid var(--border-subtle)" }}>
              {f.message}
            </li>
          ))}
        </ul>
      )}

      <h2 style={{ fontSize: 16, fontWeight: 700, marginBottom: 12 }}>Timeline</h2>
      {view.timeline.length === 0 ? (
        <div style={{ color: "var(--text-secondary)", fontSize: 14, marginBottom: 24 }}>No activity recorded yet.</div>
      ) : (
        <ul style={{ listStyle: "none", padding: 0, margin: "0 0 16px", fontSize: 13 }}>
          {view.timeline.map((e, i) => (
            <li
              key={i}
              style={{
                padding: "8px 0",
                borderTop: "1px solid var(--border-subtle)",
                display: "flex",
                justifyContent: "space-between",
                color: "var(--text-secondary)",
              }}
            >
              <span>
                {e.action_code}
                {e.actor_name ? ` · ${e.actor_name}` : ""}
              </span>
              <span>{new Date(e.created_at).toLocaleString()}</span>
            </li>
          ))}
        </ul>
      )}

      <div style={{ color: "var(--text-secondary)", fontSize: 12 }}>
        Not yet available: {view.not_yet_available.join(", ")}
      </div>
    </div>
  );
}
