"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { StatusBadge } from "@/components/StatusBadge";
import { inputStyle, primaryBtn } from "@/components/formStyles";
import {
  api,
  type ChangeControlOut,
  type ComponentOut,
  type ComponentType,
  type PlannedInvestmentScoreOut,
  type SpecificationOut,
} from "@/lib/api";

const SELECTED_ORG_KEY = "datalume.selectedOrganisationId";

function statusVariant(status: string) {
  if (status === "ACTIVE") return "success" as const;
  if (status === "DISPOSED") return "critical" as const;
  return "neutral" as const;
}

function specStatusVariant(status: string) {
  return status === "SUPERSEDED" ? ("neutral" as const) : ("success" as const);
}

function changeStatusVariant(status: string) {
  if (status === "IMPLEMENTED" || status === "APPROVED") return "success" as const;
  if (status === "REJECTED" || status === "CANCELLED") return "critical" as const;
  return "neutral" as const;
}

function orgId(): string | null {
  return typeof window === "undefined" ? null : window.localStorage.getItem(SELECTED_ORG_KEY);
}

export function ComponentDetailClient({ componentId }: { componentId: string }) {
  const [component, setComponent] = useState<ComponentOut | null>(null);
  const [children, setChildren] = useState<ComponentOut[] | null>(null);
  const [types, setTypes] = useState<ComponentType[]>([]);
  const [specifications, setSpecifications] = useState<SpecificationOut[] | null>(null);
  const [changes, setChanges] = useState<ChangeControlOut[] | null>(null);
  const [plannedInvestment, setPlannedInvestment] = useState<PlannedInvestmentScoreOut | null>(null);
  const [investmentExpanded, setInvestmentExpanded] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [childTypeId, setChildTypeId] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  const [specTitle, setSpecTitle] = useState("");
  const [specSubmitting, setSpecSubmitting] = useState(false);
  const [specFormError, setSpecFormError] = useState<string | null>(null);

  const [changeSpecId, setChangeSpecId] = useState("");
  const [changeProposedTitle, setChangeProposedTitle] = useState("");
  const [changeReason, setChangeReason] = useState("");
  const [changeSubmitting, setChangeSubmitting] = useState(false);
  const [changeFormError, setChangeFormError] = useState<string | null>(null);

  async function refreshChildren() {
    const id = orgId();
    if (!id) return;
    setChildren(await api.listComponentChildren(id, componentId));
  }

  async function refreshSpecifications() {
    const id = orgId();
    if (!id) return;
    const specList = await api.listSpecifications(id, {
      related_entity_type: "component",
      related_entity_id: componentId,
    });
    setSpecifications(specList);
    return specList;
  }

  async function refreshChanges() {
    const id = orgId();
    if (!id) return;
    // Filtered by related_entity_type/id (stable across a specification's
    // whole revision lineage), not specification_id — a change stays
    // visible in this component's history even after it's implemented
    // and the specification_id it targeted has since been superseded.
    setChanges(await api.listChangeControl(id, { related_entity_type: "component", related_entity_id: componentId }));
  }

  useEffect(() => {
    (async () => {
      const id = orgId();
      if (!id) {
        setLoadError("No organisation selected.");
        return;
      }
      try {
        const [comp, childList, typeList, specList, changeList, investment] = await Promise.all([
          api.getComponent(id, componentId),
          api.listComponentChildren(id, componentId),
          api.listComponentTypes(id),
          api.listSpecifications(id, { related_entity_type: "component", related_entity_id: componentId }),
          api.listChangeControl(id, { related_entity_type: "component", related_entity_id: componentId }),
          api.getComponentPlannedInvestment(id, componentId),
        ]);
        setComponent(comp);
        setChildren(childList);
        setTypes(typeList);
        setSpecifications(specList);
        setChanges(changeList);
        setPlannedInvestment(investment);
        if (typeList[0]) setChildTypeId(typeList[0].id);
        if (specList[0]) setChangeSpecId(specList[0].id);
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
      const specList = await refreshSpecifications();
      if (specList?.[0] && !changeSpecId) setChangeSpecId(specList[0].id);
    } catch {
      setSpecFormError("Couldn't add that specification.");
    } finally {
      setSpecSubmitting(false);
    }
  }

  async function onSubmitChange() {
    const id = orgId();
    if (!id || !changeSpecId || !changeProposedTitle.trim() || !changeReason.trim()) {
      setChangeFormError("Pick a specification, a proposed title, and a reason.");
      return;
    }
    setChangeSubmitting(true);
    setChangeFormError(null);
    try {
      await api.submitChangeControl(id, {
        specification_id: changeSpecId,
        proposed_value: { title: changeProposedTitle.trim() },
        reason: changeReason.trim(),
      });
      setChangeProposedTitle("");
      setChangeReason("");
      await refreshChanges();
    } catch {
      setChangeFormError("Couldn't submit that change.");
    } finally {
      setChangeSubmitting(false);
    }
  }

  async function onChangeTransition(changeId: string, action: "start-review" | "approve" | "reject" | "cancel" | "implement") {
    const id = orgId();
    if (!id) return;
    if (action === "start-review") await api.startChangeControlReview(id, changeId);
    else if (action === "approve") await api.approveChangeControl(id, changeId);
    else if (action === "reject") await api.rejectChangeControl(id, changeId);
    else if (action === "cancel") await api.cancelChangeControl(id, changeId);
    else if (action === "implement") await api.implementChangeControl(id, changeId);
    const [specList] = await Promise.all([refreshSpecifications(), refreshChanges()]);
    const activeSpec = specList?.find((s) => s.status === "ACTIVE");
    if (activeSpec) setChangeSpecId(activeSpec.id);
  }

  if (loadError) {
    return <div style={{ color: "var(--text-secondary)" }}>{loadError}</div>;
  }

  if (!component || !children || !specifications || !changes) {
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

      {plannedInvestment && (
        <div
          style={{
            background: "var(--bg-card)",
            border: "1px solid var(--border-subtle)",
            borderRadius: "var(--radius-card)",
            padding: 16,
            marginBottom: 24,
            fontSize: 13,
          }}
        >
          <div
            style={{ display: "flex", justifyContent: "space-between", alignItems: "center", cursor: "pointer" }}
            onClick={() => setInvestmentExpanded((v) => !v)}
          >
            <span style={{ fontWeight: 700 }}>Planned investment priority</span>
            <StatusBadge
              label={plannedInvestment.priority_score.toFixed(0)}
              variant={plannedInvestment.priority_score >= 70 ? "critical" : plannedInvestment.priority_score >= 40 ? "warning" : "success"}
            />
          </div>
          {investmentExpanded && (
            <ul style={{ listStyle: "none", padding: 0, margin: "10px 0 0", color: "var(--text-secondary)" }}>
              {plannedInvestment.factors.map((f) => (
                <li key={f.factor_code} style={{ padding: "3px 0" }}>
                  <strong>{f.label}</strong> (weight {f.weight}): {f.applicable ? f.detail : "not applicable — excluded"}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

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

      <h2 style={{ fontSize: 16, fontWeight: 700, marginBottom: 12 }}>Change control</h2>
      <div
        style={{
          background: "var(--bg-card)",
          border: "1px solid var(--border-subtle)",
          borderRadius: "var(--radius-card)",
          padding: 20,
          marginBottom: 16,
        }}
      >
        <div style={{ display: "grid", gap: 12, gridTemplateColumns: "1.2fr 1.2fr 1.2fr auto", alignItems: "end" }}>
          <div>
            <label style={{ fontSize: 12, color: "var(--text-secondary)", display: "block", marginBottom: 4 }}>
              Specification
            </label>
            <select style={inputStyle} value={changeSpecId} onChange={(e) => setChangeSpecId(e.target.value)}>
              {specifications
                .filter((s) => s.status === "ACTIVE")
                .map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.title} (rev {s.revision})
                  </option>
                ))}
            </select>
          </div>
          <div>
            <label style={{ fontSize: 12, color: "var(--text-secondary)", display: "block", marginBottom: 4 }}>
              Proposed title
            </label>
            <input
              style={inputStyle}
              value={changeProposedTitle}
              onChange={(e) => setChangeProposedTitle(e.target.value)}
            />
          </div>
          <div>
            <label style={{ fontSize: 12, color: "var(--text-secondary)", display: "block", marginBottom: 4 }}>
              Reason
            </label>
            <input style={inputStyle} value={changeReason} onChange={(e) => setChangeReason(e.target.value)} />
          </div>
          <button style={primaryBtn} onClick={onSubmitChange} disabled={changeSubmitting}>
            {changeSubmitting ? "Submitting…" : "Propose"}
          </button>
        </div>
        {specifications.filter((s) => s.status === "ACTIVE").length === 0 && (
          <div style={{ color: "var(--text-secondary)", fontSize: 13, marginTop: 10 }}>
            Add a specification above before proposing a change to it.
          </div>
        )}
        {changeFormError && (
          <div style={{ color: "var(--color-critical)", fontSize: 13, marginTop: 10 }}>{changeFormError}</div>
        )}
      </div>
      {changes.length === 0 ? (
        <div style={{ color: "var(--text-secondary)", fontSize: 14, marginBottom: 24 }}>No change requests yet.</div>
      ) : (
        <ul style={{ listStyle: "none", padding: 0, margin: "0 0 24px" }}>
          {changes.map((c) => (
            <li
              key={c.id}
              style={{
                padding: "12px 0",
                borderTop: "1px solid var(--border-subtle)",
                fontSize: 13,
              }}
            >
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
                <span style={{ fontFamily: "monospace", color: "var(--text-secondary)" }}>{c.change_reference}</span>
                <StatusBadge label={c.status} variant={changeStatusVariant(c.status)} />
              </div>
              <div style={{ color: "var(--text-secondary)", marginBottom: 8 }}>{c.reason}</div>
              <div style={{ display: "flex", gap: 8 }}>
                {c.status === "PROPOSED" && (
                  <button
                    style={{ ...primaryBtn, padding: "4px 10px", fontSize: 12 }}
                    onClick={() => onChangeTransition(c.id, "start-review")}
                  >
                    Start review
                  </button>
                )}
                {(c.status === "PROPOSED" || c.status === "UNDER_REVIEW") && (
                  <button
                    style={{ ...primaryBtn, padding: "4px 10px", fontSize: 12 }}
                    onClick={() => onChangeTransition(c.id, "approve")}
                  >
                    Approve
                  </button>
                )}
                {(c.status === "PROPOSED" || c.status === "UNDER_REVIEW") && (
                  <button
                    style={{ ...primaryBtn, padding: "4px 10px", fontSize: 12, background: "var(--color-critical)" }}
                    onClick={() => onChangeTransition(c.id, "reject")}
                  >
                    Reject
                  </button>
                )}
                {c.status === "APPROVED" && (
                  <button
                    style={{ ...primaryBtn, padding: "4px 10px", fontSize: 12 }}
                    onClick={() => onChangeTransition(c.id, "implement")}
                  >
                    Implement
                  </button>
                )}
                {(c.status === "PROPOSED" || c.status === "UNDER_REVIEW" || c.status === "APPROVED") && (
                  <button
                    style={{ ...primaryBtn, padding: "4px 10px", fontSize: 12, background: "var(--text-secondary)" }}
                    onClick={() => onChangeTransition(c.id, "cancel")}
                  >
                    Cancel
                  </button>
                )}
              </div>
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
