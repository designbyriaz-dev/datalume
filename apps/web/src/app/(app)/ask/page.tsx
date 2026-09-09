"use client";

import { useEffect, useState } from "react";
import { StatusBadge } from "@/components/StatusBadge";
import { inputStyle, primaryBtn, secondaryBtn } from "@/components/formStyles";
import {
  api,
  type AskResponse,
  type BuildingOut,
  type ComponentOut,
  type LeaseOut,
  type PropertyOut,
} from "@/lib/api";

const SELECTED_ORG_KEY = "datalume.selectedOrganisationId";

const ENTITY_TYPES = ["building", "property", "component", "lease"] as const;
type EntityType = (typeof ENTITY_TYPES)[number];

type EntityOption = { id: string; label: string };

type ChatTurn = {
  question: string;
  entityType: string;
  entityLabel: string;
  response: AskResponse;
};

function ExplainabilityPanel({ response }: { response: AskResponse }) {
  const [expanded, setExpanded] = useState(false);
  if (response.tool_results.length === 0) return null;
  return (
    <div style={{ marginTop: 8 }}>
      <button
        style={{ background: "none", border: "none", color: "var(--color-primary)", fontSize: 12, cursor: "pointer", padding: 0 }}
        onClick={() => setExpanded((v) => !v)}
      >
        {expanded ? "Hide" : "Show"} the data behind this answer ({response.tool_results.length})
      </button>
      {expanded && (
        <ul style={{ listStyle: "none", padding: 0, margin: "8px 0 0", fontSize: 12 }}>
          {response.tool_results.map((tr, i) => (
            <li
              key={i}
              style={{
                background: "var(--bg-app)",
                border: "1px solid var(--border-subtle)",
                borderRadius: 6,
                padding: 10,
                marginBottom: 6,
              }}
            >
              <div style={{ fontWeight: 600, marginBottom: 4 }}>{tr.tool_name}</div>
              <div style={{ color: "var(--text-secondary)", marginBottom: 2 }}>Dataset: {tr.dataset}</div>
              <div style={{ color: "var(--text-secondary)", marginBottom: 2 }}>Fields: {tr.fields.join(", ") || "—"}</div>
              <div style={{ color: "var(--text-secondary)", marginBottom: 2 }}>
                Filters: {Object.entries(tr.filters).map(([k, v]) => `${k}=${v}`).join(", ") || "—"}
              </div>
              {tr.calculation && <div style={{ color: "var(--text-secondary)", marginBottom: 2 }}>Calculation: {tr.calculation}</div>}
              <div style={{ color: "var(--text-secondary)" }}>Records returned: {tr.records.length}</div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export default function AskPage() {
  const [entityType, setEntityType] = useState<EntityType>("property");
  const [options, setOptions] = useState<EntityOption[]>([]);
  const [entityId, setEntityId] = useState("");
  const [question, setQuestion] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [turns, setTurns] = useState<ChatTurn[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);

  function orgId(): string | null {
    return typeof window === "undefined" ? null : window.localStorage.getItem(SELECTED_ORG_KEY);
  }

  async function loadOptions(type: EntityType) {
    const id = orgId();
    if (!id) return;
    let opts: EntityOption[] = [];
    if (type === "building") {
      const buildings: BuildingOut[] = await api.listBuildings(id);
      opts = buildings.map((b) => ({ id: b.id, label: b.name || b.building_reference }));
    } else if (type === "property") {
      const properties: PropertyOut[] = await api.listProperties(id);
      opts = properties.map((p) => ({ id: p.id, label: p.address }));
    } else if (type === "component") {
      const components: ComponentOut[] = await api.listComponents(id);
      opts = components.map((c) => ({ id: c.id, label: `${c.component_reference} — ${c.component_type_name}` }));
    } else if (type === "lease") {
      const leases: LeaseOut[] = await api.listLeases(id);
      opts = leases.map((l) => ({ id: l.id, label: l.lease_reference }));
    }
    setOptions(opts);
    setEntityId(opts[0]?.id ?? "");
  }

  useEffect(() => {
    (async () => {
      const id = orgId();
      if (!id) {
        setLoadError("No organisation selected.");
        return;
      }
      try {
        await loadOptions(entityType);
      } catch {
        setLoadError("Couldn't load records to ask about.");
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function onEntityTypeChange(type: EntityType) {
    setEntityType(type);
    setOptions([]);
    setEntityId("");
    try {
      await loadOptions(type);
    } catch {
      setLoadError("Couldn't load records to ask about.");
    }
  }

  async function onAsk(questionText?: string) {
    const id = orgId();
    const q = (questionText ?? question).trim();
    if (!id || !entityId || !q) {
      setError("Pick a record and type a question first.");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const response = await api.askDataLume(id, { question: q, entity_type: entityType, entity_id: entityId });
      const entityLabel = options.find((o) => o.id === entityId)?.label ?? entityId.slice(0, 8);
      setTurns((prev) => [...prev, { question: q, entityType, entityLabel, response }]);
      setQuestion("");
    } catch {
      setError("Couldn't get an answer right now.");
    } finally {
      setSubmitting(false);
    }
  }

  if (loadError) {
    return <div style={{ color: "var(--text-secondary)" }}>{loadError}</div>;
  }

  return (
    <div style={{ maxWidth: 760 }}>
      <h1 style={{ fontSize: 24, fontWeight: 700, margin: 0, marginBottom: 4 }}>Ask DataLume</h1>
      <p style={{ color: "var(--text-secondary)", marginBottom: 24 }}>
        Every answer is grounded in DataLume&rsquo;s own records — never a guess. If nothing in your data can answer
        a question, that&rsquo;s exactly what you&rsquo;ll be told. Show the data behind any answer to see exactly
        what was queried.
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
        <div style={{ display: "grid", gap: 12, gridTemplateColumns: "1fr 1.5fr", marginBottom: 12 }}>
          <div>
            <label htmlFor="ask-entity-type" style={{ fontSize: 12, color: "var(--text-secondary)", display: "block", marginBottom: 4 }}>Ask about</label>
            <select id="ask-entity-type" style={inputStyle} value={entityType} onChange={(e) => onEntityTypeChange(e.target.value as EntityType)}>
              {ENTITY_TYPES.map((t) => (
                <option key={t} value={t}>
                  {t.charAt(0).toUpperCase() + t.slice(1)}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label htmlFor="ask-entity-id" style={{ fontSize: 12, color: "var(--text-secondary)", display: "block", marginBottom: 4 }}>Record</label>
            <select id="ask-entity-id" style={inputStyle} value={entityId} onChange={(e) => setEntityId(e.target.value)}>
              {options.length === 0 && <option value="">No records yet</option>}
              {options.map((o) => (
                <option key={o.id} value={o.id}>
                  {o.label}
                </option>
              ))}
            </select>
          </div>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <input
            aria-label="Question"
            style={inputStyle}
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && onAsk()}
            placeholder="e.g. Is this compliant? Any repeat repairs? What are the arrears?"
          />
          <button style={primaryBtn} onClick={() => onAsk()} disabled={submitting || !entityId}>
            {submitting ? "Asking…" : "Ask"}
          </button>
        </div>
        {error && <div style={{ color: "var(--color-critical)", fontSize: 13, marginTop: 10 }}>{error}</div>}
      </div>

      {turns.length === 0 ? (
        <div style={{ color: "var(--text-secondary)", fontSize: 14 }}>No questions asked yet.</div>
      ) : (
        <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
          {turns.map((turn, i) => (
            <li key={i} style={{ padding: "14px 0", borderTop: "1px solid var(--border-subtle)" }}>
              <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 6 }}>
                {turn.question} <span style={{ color: "var(--text-secondary)", fontWeight: 400 }}>({turn.entityType}: {turn.entityLabel})</span>
              </div>
              <div style={{ display: "flex", alignItems: "flex-start", gap: 8, marginBottom: 4 }}>
                <StatusBadge label={turn.response.grounded ? "Grounded" : "No data"} variant={turn.response.grounded ? "success" : "neutral"} />
                <div style={{ fontSize: 13 }}>{turn.response.answer_text}</div>
              </div>
              <ExplainabilityPanel response={turn.response} />
              {turn.response.suggested_follow_ups.length > 0 && (
                <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginTop: 10 }}>
                  {turn.response.suggested_follow_ups.map((f) => (
                    <button key={f} style={{ ...secondaryBtn, padding: "3px 10px", fontSize: 12 }} onClick={() => onAsk(f)}>
                      {f}
                    </button>
                  ))}
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
