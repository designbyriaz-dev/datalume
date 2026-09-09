"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { StatusBadge } from "@/components/StatusBadge";
import { inputStyle, primaryBtn } from "@/components/formStyles";
import { api, type ComponentOut, type ComponentType, type SpecificationOut } from "@/lib/api";

const SELECTED_ORG_KEY = "datalume.selectedOrganisationId";

function statusVariant(status: string) {
  if (status === "ACTIVE") return "success" as const;
  if (status === "DISPOSED") return "critical" as const;
  return "neutral" as const;
}

function specStatusVariant(status: string) {
  return status === "SUPERSEDED" ? ("neutral" as const) : ("success" as const);
}

function orgId(): string | null {
  return typeof window === "undefined" ? null : window.localStorage.getItem(SELECTED_ORG_KEY);
}

export function ComponentDetailClient({ componentId }: { componentId: string }) {
  const [component, setComponent] = useState<ComponentOut | null>(null);
  const [children, setChildren] = useState<ComponentOut[] | null>(null);
  const [types, setTypes] = useState<ComponentType[]>([]);
  const [specifications, setSpecifications] = useState<SpecificationOut[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [childTypeId, setChildTypeId] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  const [specTitle, setSpecTitle] = useState("");
  const [specSubmitting, setSpecSubmitting] = useState(false);
  const [specFormError, setSpecFormError] = useState<string | null>(null);

  async function refreshChildren() {
    const id = orgId();
    if (!id) return;
    setChildren(await api.listComponentChildren(id, componentId));
  }

  async function refreshSpecifications() {
    const id = orgId();
    if (!id) return;
    setSpecifications(await api.listSpecifications(id, { related_entity_type: "component", related_entity_id: componentId }));
  }

  useEffect(() => {
    (async () => {
      const id = orgId();
      if (!id) {
        setLoadError("No organisation selected.");
        return;
      }
      try {
        const [comp, childList, typeList, specList] = await Promise.all([
          api.getComponent(id, componentId),
          api.listComponentChildren(id, componentId),
          api.listComponentTypes(id),
          api.listSpecifications(id, { related_entity_type: "component", related_entity_id: componentId }),
        ]);
        setComponent(comp);
        setChildren(childList);
        setTypes(typeList);
        setSpecifications(specList);
        if (typeList[0]) setChildTypeId(typeList[0].id);
      } catch {
        setLoadError("Couldn't load this component.");
      }
    })();
  }, [componentId]);

  async function onAddChild() {
    const id = orgId();
    if (!id || !childTypeId) return;
    setSubmitting(true);
    setFormError(null);
    try {
      await api.createComponent(id, { component_type_id: childTypeId, parent_component_id: componentId });
      await refreshChildren();
    } catch {
      setFormError("Couldn't add that child component.");
    } finally {
      setSubmitting(false);
    }
  }

  async function onAddSpecification() {
    const id = orgId();
    if (!id || !specTitle.trim()) {
      setSpecFormError("Give the specification a title first.");
      return;
    }
    setSpecSubmitting(true);
    setSpecFormError(null);
    try {
      await api.createSpecification(id, {
        related_entity_type: "component",
        related_entity_id: componentId,
        title: specTitle.trim(),
      });
      setSpecTitle("");
      await refreshSpecifications();
    } catch {
      setSpecFormError("Couldn't add that specification.");
    } finally {
      setSpecSubmitting(false);
    }
  }

  if (loadError) {
    return <div style={{ color: "var(--text-secondary)" }}>{loadError}</div>;
  }

  if (!component || !children || !specifications) {
    return <div style={{ color: "var(--text-secondary)" }}>Loading…</div>;
  }

  return (
    <div style={{ maxWidth: 720 }}>
      <Link href="/components" style={{ fontSize: 13, color: "var(--color-primary)" }}>
        ← Components
      </Link>

      <div style={{ display: "flex", alignItems: "center", gap: 12, margin: "8px 0 4px" }}>
        <h1 style={{ fontSize: 24, fontWeight: 700, margin: 0 }}>{component.component_type_name}</h1>
        <StatusBadge label={component.status} variant={statusVariant(component.status)} />
      </div>
      <p style={{ color: "var(--text-secondary)", marginBottom: 24, fontFamily: "monospace", fontSize: 13 }}>
        {component.component_reference}
      </p>

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
          <div style={{ color: "var(--text-secondary)", marginBottom: 2 }}>Manufacturer</div>
          <div>{component.manufacturer ?? "—"}</div>
        </div>
        <div>
          <div style={{ color: "var(--text-secondary)", marginBottom: 2 }}>Model</div>
          <div>{component.model ?? "—"}</div>
        </div>
        <div>
          <div style={{ color: "var(--text-secondary)", marginBottom: 2 }}>Serial number</div>
          <div>{component.serial_number ?? "—"}</div>
        </div>
        <div>
          <div style={{ color: "var(--text-secondary)", marginBottom: 2 }}>Installed</div>
          <div>{component.installation_date ?? "—"}</div>
        </div>
        <div>
          <div style={{ color: "var(--text-secondary)", marginBottom: 2 }}>Expected life</div>
          <div>{component.expected_life_years ? `${component.expected_life_years} years` : "—"}</div>
        </div>
        <div>
          <div style={{ color: "var(--text-secondary)", marginBottom: 2 }}>Indicative replacement</div>
          <div>
            {component.indicative_replacement_date ?? "—"}
            {component.indicative_replacement_date && (
              <span style={{ color: "var(--text-secondary)", fontSize: 11 }}> (indicative only)</span>
            )}
          </div>
        </div>
      </div>

      <h2 style={{ fontSize: 16, fontWeight: 700, marginBottom: 12 }}>Specifications</h2>
      <div
        style={{
          background: "var(--bg-card)",
          border: "1px solid var(--border-subtle)",
          borderRadius: "var(--radius-card)",
          padding: 20,
          marginBottom: 16,
        }}
      >
        <div style={{ display: "grid", gap: 12, gridTemplateColumns: "2fr auto", alignItems: "end" }}>
          <div>
            <label style={{ fontSize: 12, color: "var(--text-secondary)", display: "block", marginBottom: 4 }}>
              Title
            </label>
            <input
              style={inputStyle}
              value={specTitle}
              onChange={(e) => setSpecTitle(e.target.value)}
              placeholder="e.g. Boiler installation specification"
            />
          </div>
          <button style={primaryBtn} onClick={onAddSpecification} disabled={specSubmitting}>
            {specSubmitting ? "Adding…" : "Add"}
          </button>
        </div>
        {specFormError && (
          <div style={{ color: "var(--color-critical)", fontSize: 13, marginTop: 10 }}>{specFormError}</div>
        )}
      </div>
      {specifications.length === 0 ? (
        <div style={{ color: "var(--text-secondary)", fontSize: 14, marginBottom: 24 }}>No specifications yet.</div>
      ) : (
        <ul style={{ listStyle: "none", padding: 0, margin: "0 0 24px" }}>
          {specifications.map((s) => (
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
              <span>
                {s.title} <span style={{ color: "var(--text-secondary)" }}>rev {s.revision}</span>
              </span>
              <StatusBadge label={s.status} variant={specStatusVariant(s.status)} />
            </li>
          ))}
        </ul>
      )}

      <h2 style={{ fontSize: 16, fontWeight: 700, marginBottom: 12 }}>Child components</h2>
      <div
        style={{
          background: "var(--bg-card)",
          border: "1px solid var(--border-subtle)",
          borderRadius: "var(--radius-card)",
          padding: 20,
          marginBottom: 16,
        }}
      >
        <div style={{ display: "grid", gap: 12, gridTemplateColumns: "2fr auto", alignItems: "end" }}>
          <div>
            <label style={{ fontSize: 12, color: "var(--text-secondary)", display: "block", marginBottom: 4 }}>
              Type
            </label>
            <select style={inputStyle} value={childTypeId} onChange={(e) => setChildTypeId(e.target.value)}>
              {types.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.name}
                </option>
              ))}
            </select>
          </div>
          <button style={primaryBtn} onClick={onAddChild} disabled={submitting}>
            {submitting ? "Adding…" : "Add child"}
          </button>
        </div>
        {formError && (
          <div style={{ color: "var(--color-critical)", fontSize: 13, marginTop: 10 }}>{formError}</div>
        )}
      </div>

      {children.length === 0 ? (
        <div style={{ color: "var(--text-secondary)", fontSize: 14 }}>No child components.</div>
      ) : (
        <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
          {children.map((c) => (
            <li
              key={c.id}
              style={{
                padding: "10px 0",
                borderTop: "1px solid var(--border-subtle)",
                fontSize: 13,
                display: "flex",
                justifyContent: "space-between",
              }}
            >
              <Link href={`/components/${c.id}`} style={{ color: "var(--color-primary)" }}>
                {c.component_reference}
              </Link>
              <span style={{ color: "var(--text-secondary)" }}>{c.component_type_name}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
