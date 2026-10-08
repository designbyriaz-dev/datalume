"use client";

import { useEffect, useState } from "react";
import { inputStyle, primaryBtn, secondaryBtn } from "@/components/formStyles";
import { api, ApiError, type AuditEventOut } from "@/lib/api";

const SELECTED_ORG_KEY = "datalume.selectedOrganisationId";
const PAGE_SIZE = 50;

const cardStyle: React.CSSProperties = {
  background: "var(--bg-card)",
  border: "1px solid var(--border-subtle)",
  borderRadius: "var(--radius-card)",
  padding: 20,
};

const thStyle: React.CSSProperties = {
  textAlign: "left",
  fontSize: 12,
  color: "var(--text-secondary)",
  fontWeight: 600,
  padding: "0 12px 8px 0",
  borderBottom: "1px solid var(--border-subtle)",
};

const tdStyle: React.CSSProperties = {
  padding: "10px 12px 10px 0",
  fontSize: 13,
  verticalAlign: "top",
  borderBottom: "1px solid var(--border-subtle)",
};

type Filters = {
  entity_type: string;
  entity_id: string;
  created_from: string;
  created_to: string;
};

const EMPTY_FILTERS: Filters = { entity_type: "", entity_id: "", created_from: "", created_to: "" };

function orgId(): string | null {
  return typeof window === "undefined" ? null : window.localStorage.getItem(SELECTED_ORG_KEY);
}

function actionLabel(actionCode: string): string {
  // "property.created" -> "Property created" — every action_code in this
  // codebase follows that "<entity>.<verb>" shape (see app/platform/audit.py
  // call sites), so this covers every event without a lookup table to keep in sync.
  return actionCode.replace(/_/g, " ").replace(/\./g, " — ").replace(/^./, (c) => c.toUpperCase());
}

function ChangeDetails({ event }: { event: AuditEventOut }) {
  if (!event.before && !event.after) return <span style={{ color: "var(--text-secondary)" }}>—</span>;
  return (
    <details>
      <summary style={{ cursor: "pointer", color: "var(--color-primary)", fontSize: 12 }}>View</summary>
      <pre
        style={{
          margin: "8px 0 0",
          background: "var(--bg-app)",
          borderRadius: 6,
          padding: "8px 10px",
          fontSize: 11,
          fontFamily: "monospace",
          maxWidth: 420,
          overflowX: "auto",
          whiteSpace: "pre-wrap",
          wordBreak: "break-word",
        }}
      >
        {event.before && `before: ${JSON.stringify(event.before, null, 2)}\n`}
        {event.after && `after: ${JSON.stringify(event.after, null, 2)}`}
      </pre>
    </details>
  );
}

export default function AuditLogPage() {
  const [events, setEvents] = useState<AuditEventOut[] | null>(null);
  const [offset, setOffset] = useState(0);
  const [filters, setFilters] = useState<Filters>(EMPTY_FILTERS);
  const [draftFilters, setDraftFilters] = useState<Filters>(EMPTY_FILTERS);
  const [forbidden, setForbidden] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function refresh(atOffset: number, withFilters: Filters) {
    const id = orgId();
    if (!id) return;
    setLoading(true);
    setError(null);
    try {
      const result = await api.listAuditEvents(id, {
        entity_type: withFilters.entity_type || undefined,
        entity_id: withFilters.entity_id || undefined,
        created_from: withFilters.created_from ? `${withFilters.created_from}T00:00:00` : undefined,
        created_to: withFilters.created_to ? `${withFilters.created_to}T23:59:59` : undefined,
        limit: PAGE_SIZE,
        offset: atOffset,
      });
      setEvents(result);
      setForbidden(false);
    } catch (err) {
      if (err instanceof ApiError && err.status === 403) {
        setForbidden(true);
      } else {
        setError("Couldn't load the audit log.");
      }
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    (async () => {
      if (!orgId()) {
        setLoading(false);
        setError("No organisation selected.");
        return;
      }
      await refresh(0, EMPTY_FILTERS);
    })();
  }, []);

  function onApplyFilters(e: React.FormEvent) {
    e.preventDefault();
    setFilters(draftFilters);
    setOffset(0);
    refresh(0, draftFilters);
  }

  function onClearFilters() {
    setDraftFilters(EMPTY_FILTERS);
    setFilters(EMPTY_FILTERS);
    setOffset(0);
    refresh(0, EMPTY_FILTERS);
  }

  function onPrevious() {
    const next = Math.max(0, offset - PAGE_SIZE);
    setOffset(next);
    refresh(next, filters);
  }

  function onNext() {
    const next = offset + PAGE_SIZE;
    setOffset(next);
    refresh(next, filters);
  }

  return (
    <div style={{ maxWidth: 980 }}>
      <h1 style={{ fontSize: 24, fontWeight: 700, margin: 0, marginBottom: 4 }}>Audit log</h1>
      <p style={{ color: "var(--text-secondary)", marginBottom: 24 }}>
        Every significant change made across your organisation — who did what, and when. Only owners and
        admins can see this.
      </p>

      {forbidden ? (
        <div style={cardStyle}>
          <p style={{ margin: 0, color: "var(--text-secondary)" }}>
            Only an Owner or Admin can view the audit log. Ask one of your organisation&rsquo;s Owners for
            access.
          </p>
        </div>
      ) : (
        <>
          <form
            onSubmit={onApplyFilters}
            style={{ ...cardStyle, display: "flex", gap: 12, alignItems: "flex-end", flexWrap: "wrap", marginBottom: 16 }}
          >
            <div style={{ flex: "1 1 160px" }}>
              <label htmlFor="audit-entity-type" style={{ display: "block", fontSize: 12, color: "var(--text-secondary)", marginBottom: 4 }}>
                Entity type
              </label>
              <input
                id="audit-entity-type"
                style={inputStyle}
                placeholder="e.g. property"
                value={draftFilters.entity_type}
                onChange={(e) => setDraftFilters((prev) => ({ ...prev, entity_type: e.target.value }))}
              />
            </div>
            <div style={{ flex: "1 1 200px" }}>
              <label htmlFor="audit-entity-id" style={{ display: "block", fontSize: 12, color: "var(--text-secondary)", marginBottom: 4 }}>
                Entity ID
              </label>
              <input
                id="audit-entity-id"
                style={inputStyle}
                value={draftFilters.entity_id}
                onChange={(e) => setDraftFilters((prev) => ({ ...prev, entity_id: e.target.value }))}
              />
            </div>
            <div style={{ flex: "1 1 140px" }}>
              <label htmlFor="audit-from" style={{ display: "block", fontSize: 12, color: "var(--text-secondary)", marginBottom: 4 }}>
                From
              </label>
              <input
                id="audit-from"
                type="date"
                style={inputStyle}
                value={draftFilters.created_from}
                onChange={(e) => setDraftFilters((prev) => ({ ...prev, created_from: e.target.value }))}
              />
            </div>
            <div style={{ flex: "1 1 140px" }}>
              <label htmlFor="audit-to" style={{ display: "block", fontSize: 12, color: "var(--text-secondary)", marginBottom: 4 }}>
                To
              </label>
              <input
                id="audit-to"
                type="date"
                style={inputStyle}
                value={draftFilters.created_to}
                onChange={(e) => setDraftFilters((prev) => ({ ...prev, created_to: e.target.value }))}
              />
            </div>
            <button type="submit" style={primaryBtn}>
              Apply
            </button>
            <button type="button" style={secondaryBtn} onClick={onClearFilters}>
              Clear
            </button>
          </form>

          {error && <p style={{ color: "var(--color-critical)", fontSize: 13, marginBottom: 16 }}>{error}</p>}

          <div style={cardStyle}>
            {loading ? (
              <div style={{ color: "var(--text-secondary)" }}>Loading…</div>
            ) : !events || events.length === 0 ? (
              <div style={{ color: "var(--text-secondary)", fontSize: 14 }}>
                No audit events match these filters.
              </div>
            ) : (
              <table style={{ width: "100%", borderCollapse: "collapse" }}>
                <thead>
                  <tr>
                    <th style={thStyle}>When</th>
                    <th style={thStyle}>Actor</th>
                    <th style={thStyle}>Action</th>
                    <th style={thStyle}>Entity</th>
                    <th style={thStyle}>Changes</th>
                  </tr>
                </thead>
                <tbody>
                  {events.map((event) => (
                    <tr key={event.id}>
                      <td style={tdStyle}>{new Date(event.created_at).toLocaleString()}</td>
                      <td style={tdStyle}>{event.actor_name ?? "System"}</td>
                      <td style={tdStyle}>{actionLabel(event.action_code)}</td>
                      <td style={tdStyle}>
                        {event.entity_type}
                        {event.entity_id && (
                          <div style={{ color: "var(--text-secondary)", fontSize: 11, fontFamily: "monospace" }}>
                            {event.entity_id}
                          </div>
                        )}
                      </td>
                      <td style={tdStyle}>
                        <ChangeDetails event={event} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>

          <div style={{ display: "flex", justifyContent: "flex-end", gap: 12, marginTop: 16 }}>
            <button style={secondaryBtn} onClick={onPrevious} disabled={offset === 0 || loading}>
              Previous
            </button>
            <button
              style={secondaryBtn}
              onClick={onNext}
              disabled={loading || !events || events.length < PAGE_SIZE}
            >
              Next
            </button>
          </div>
        </>
      )}
    </div>
  );
}
