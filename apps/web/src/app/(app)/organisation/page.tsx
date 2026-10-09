"use client";

import { useEffect, useState } from "react";
import { inputStyle, primaryBtn } from "@/components/formStyles";
import {
  api,
  ApiError,
  type ReferencePattern,
  type ComplianceStatusConfig,
  type PaymentReconciliationConfig,
  type PlannedInvestmentConfig,
  type RepairRuleConfig,
  type AttentionRuleOut,
} from "@/lib/api";

const SELECTED_ORG_KEY = "datalume.selectedOrganisationId";

const ENTITY_LABELS: Record<string, string> = {
  DEVELOPMENT: "Developments",
  BUILDING: "Buildings",
  PROPERTY: "Properties",
  DOCUMENT: "Documents",
};

// Every engine below computes deterministically from a plain config row —
// no code change needed to retune sensitivity (same "config, not code"
// design each engine's own module already documents) — but until now
// none of these rows had any UI at all; only GET /api/v1/data-health's own
// equivalent gap (closed separately) had ever been found this way.
const cardStyle: React.CSSProperties = {
  background: "var(--bg-card)",
  border: "1px solid var(--border-subtle)",
  borderRadius: "var(--radius-card)",
  padding: 20,
};

const sectionStyle: React.CSSProperties = { marginTop: 32, maxWidth: 720 };

const thStyle: React.CSSProperties = {
  textAlign: "left",
  fontSize: 12,
  color: "var(--text-secondary)",
  fontWeight: 600,
  padding: "0 10px 8px 0",
  borderBottom: "1px solid var(--border-subtle)",
};

const tdStyle: React.CSSProperties = {
  padding: "8px 10px 8px 0",
  fontSize: 13,
  verticalAlign: "top",
  borderBottom: "1px solid var(--border-subtle)",
};

const numberInputStyle: React.CSSProperties = { ...inputStyle, width: 90 };

const PERMISSION_DENIED = "You don't have permission to change this setting.";

function orgId(): string | null {
  return typeof window === "undefined" ? null : window.localStorage.getItem(SELECTED_ORG_KEY);
}

// Every rule/check code in this codebase is an UPPER_SNAKE_CASE constant
// — same helper as the Data Health page's own checkLabel, so a new rule
// code reads sensibly here with no label map to keep in sync.
function codeLabel(code: string): string {
  return code.replace(/_/g, " ").toLowerCase().replace(/^./, (c) => c.toUpperCase());
}

function numOrUndefined(value: string): number | undefined {
  if (value.trim() === "") return undefined;
  const n = Number(value);
  return Number.isNaN(n) ? undefined : n;
}

type RepairRuleDraft = { window_months: string; threshold: string; threshold_ratio: string; min_installed_base: string };

function toRepairRuleDraft(r: RepairRuleConfig): RepairRuleDraft {
  return {
    window_months: r.window_months?.toString() ?? "",
    threshold: r.threshold?.toString() ?? "",
    threshold_ratio: r.threshold_ratio?.toString() ?? "",
    min_installed_base: r.min_installed_base?.toString() ?? "",
  };
}

export default function OrganisationPage() {
  const [patterns, setPatterns] = useState<ReferencePattern[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState<string | null>(null);
  const [rowError, setRowError] = useState<Record<string, string>>({});

  const [complianceConfig, setComplianceConfig] = useState<ComplianceStatusConfig | null>(null);
  const [complianceDraft, setComplianceDraft] = useState({ due_soon_days: "", never_assessed_grace_days: "" });
  const [complianceSaving, setComplianceSaving] = useState(false);
  const [complianceError, setComplianceError] = useState<string | null>(null);

  const [paymentConfig, setPaymentConfig] = useState<PaymentReconciliationConfig | null>(null);
  const [paymentDraft, setPaymentDraft] = useState("");
  const [paymentSaving, setPaymentSaving] = useState(false);
  const [paymentError, setPaymentError] = useState<string | null>(null);

  const [investmentConfig, setInvestmentConfig] = useState<PlannedInvestmentConfig | null>(null);
  const [investmentDraft, setInvestmentDraft] = useState({ repair_frequency_window_months: "", repair_frequency_threshold: "" });
  const [investmentSaving, setInvestmentSaving] = useState(false);
  const [investmentError, setInvestmentError] = useState<string | null>(null);

  const [repairRuleConfigs, setRepairRuleConfigs] = useState<RepairRuleConfig[] | null>(null);
  const [repairDrafts, setRepairDrafts] = useState<Record<string, RepairRuleDraft>>({});
  const [repairSaving, setRepairSaving] = useState<string | null>(null);
  const [repairRowError, setRepairRowError] = useState<Record<string, string>>({});

  const [attentionRules, setAttentionRules] = useState<AttentionRuleOut[] | null>(null);
  const [attentionSaving, setAttentionSaving] = useState<string | null>(null);
  const [attentionRowError, setAttentionRowError] = useState<Record<string, string>>({});

  async function refresh() {
    const id = orgId();
    if (!id) return;
    const list = await api.listReferencePatterns(id);
    setPatterns(list);
    setDrafts(Object.fromEntries(list.map((p) => [p.entity_type, p.pattern])));
  }

  async function refreshComplianceConfig() {
    const id = orgId();
    if (!id) return;
    const config = await api.getComplianceStatusConfig(id);
    setComplianceConfig(config);
    setComplianceDraft({
      due_soon_days: String(config.due_soon_days),
      never_assessed_grace_days: String(config.never_assessed_grace_days),
    });
  }

  async function refreshPaymentConfig() {
    const id = orgId();
    if (!id) return;
    const config = await api.getPaymentReconciliationConfig(id);
    setPaymentConfig(config);
    setPaymentDraft(String(config.due_date_window_days));
  }

  async function refreshInvestmentConfig() {
    const id = orgId();
    if (!id) return;
    const config = await api.getPlannedInvestmentConfig(id);
    setInvestmentConfig(config);
    setInvestmentDraft({
      repair_frequency_window_months: String(config.repair_frequency_window_months),
      repair_frequency_threshold: String(config.repair_frequency_threshold),
    });
  }

  async function refreshRepairRuleConfigs() {
    const id = orgId();
    if (!id) return;
    const list = await api.listRepairRuleConfigs(id);
    setRepairRuleConfigs(list);
    setRepairDrafts(Object.fromEntries(list.map((r) => [r.rule_code, toRepairRuleDraft(r)])));
  }

  async function refreshAttentionRules() {
    const id = orgId();
    if (!id) return;
    setAttentionRules(await api.listAttentionRules(id));
  }

  useEffect(() => {
    (async () => {
      const id = orgId();
      if (!id) {
        setLoadError("No organisation selected.");
        return;
      }
      try {
        await Promise.all([
          refresh(),
          refreshComplianceConfig(),
          refreshPaymentConfig(),
          refreshInvestmentConfig(),
          refreshRepairRuleConfigs(),
          refreshAttentionRules(),
        ]);
      } catch {
        setLoadError("Couldn't load organisation settings.");
      }
    })();
  }, []);

  async function onSave(entityType: string) {
    const id = orgId();
    const draft = drafts[entityType];
    if (!id || !draft) return;
    setSaving(entityType);
    setRowError((prev) => ({ ...prev, [entityType]: "" }));
    try {
      await api.updateReferencePattern(id, entityType, draft);
      await refresh();
    } catch (err) {
      const message =
        err instanceof ApiError && err.status === 403
          ? "Only an owner or admin can change reference patterns."
          : "Couldn't save that pattern — it must include a {sequence} placeholder.";
      setRowError((prev) => ({ ...prev, [entityType]: message }));
    } finally {
      setSaving(null);
    }
  }

  async function onSaveCompliance() {
    const id = orgId();
    if (!id) return;
    setComplianceSaving(true);
    setComplianceError(null);
    try {
      await api.updateComplianceStatusConfig(id, {
        due_soon_days: numOrUndefined(complianceDraft.due_soon_days),
        never_assessed_grace_days: numOrUndefined(complianceDraft.never_assessed_grace_days),
      });
      await refreshComplianceConfig();
    } catch (err) {
      setComplianceError(err instanceof ApiError && err.status === 403 ? PERMISSION_DENIED : "Couldn't save that.");
    } finally {
      setComplianceSaving(false);
    }
  }

  async function onSavePayment() {
    const id = orgId();
    const days = numOrUndefined(paymentDraft);
    if (!id || days === undefined) return;
    setPaymentSaving(true);
    setPaymentError(null);
    try {
      await api.updatePaymentReconciliationConfig(id, days);
      await refreshPaymentConfig();
    } catch (err) {
      setPaymentError(err instanceof ApiError && err.status === 403 ? PERMISSION_DENIED : "Couldn't save that.");
    } finally {
      setPaymentSaving(false);
    }
  }

  async function onSaveInvestment() {
    const id = orgId();
    if (!id) return;
    setInvestmentSaving(true);
    setInvestmentError(null);
    try {
      await api.updatePlannedInvestmentConfig(id, {
        repair_frequency_window_months: numOrUndefined(investmentDraft.repair_frequency_window_months),
        repair_frequency_threshold: numOrUndefined(investmentDraft.repair_frequency_threshold),
      });
      await refreshInvestmentConfig();
    } catch (err) {
      setInvestmentError(err instanceof ApiError && err.status === 403 ? PERMISSION_DENIED : "Couldn't save that.");
    } finally {
      setInvestmentSaving(false);
    }
  }

  async function onSaveRepairRule(ruleCode: string) {
    const id = orgId();
    const draft = repairDrafts[ruleCode];
    if (!id || !draft) return;
    setRepairSaving(ruleCode);
    setRepairRowError((prev) => ({ ...prev, [ruleCode]: "" }));
    try {
      await api.updateRepairRuleConfig(id, ruleCode, {
        window_months: numOrUndefined(draft.window_months),
        threshold: numOrUndefined(draft.threshold),
        threshold_ratio: numOrUndefined(draft.threshold_ratio),
        min_installed_base: numOrUndefined(draft.min_installed_base),
      });
      await refreshRepairRuleConfigs();
    } catch (err) {
      const message = err instanceof ApiError && err.status === 403 ? PERMISSION_DENIED : "Couldn't save that.";
      setRepairRowError((prev) => ({ ...prev, [ruleCode]: message }));
    } finally {
      setRepairSaving(null);
    }
  }

  async function onToggleAttentionRule(rule: AttentionRuleOut) {
    const id = orgId();
    if (!id) return;
    setAttentionSaving(rule.id);
    setAttentionRowError((prev) => ({ ...prev, [rule.id]: "" }));
    try {
      await api.updateAttentionRule(id, rule.id, { is_active: !rule.is_active });
      await refreshAttentionRules();
    } catch (err) {
      const message = err instanceof ApiError && err.status === 403 ? PERMISSION_DENIED : "Couldn't save that.";
      setAttentionRowError((prev) => ({ ...prev, [rule.id]: message }));
    } finally {
      setAttentionSaving(null);
    }
  }

  if (loadError) {
    return <div style={{ color: "var(--text-secondary)" }}>{loadError}</div>;
  }

  return (
    <div style={{ maxWidth: 720 }}>
      <h1 style={{ fontSize: 24, fontWeight: 700, margin: 0, marginBottom: 4 }}>Organisation</h1>
      <p style={{ color: "var(--text-secondary)", marginBottom: 24 }}>
        Internal reference formats — every reference below is generated by DataLume, never an official
        identifier. Only an owner or admin can change these.
      </p>

      <h2 style={{ fontSize: 16, fontWeight: 700, marginBottom: 12 }}>Reference patterns</h2>
      {patterns === null ? (
        <div style={{ color: "var(--text-secondary)" }}>Loading…</div>
      ) : (
        <div
          style={{
            background: "var(--bg-card)",
            border: "1px solid var(--border-subtle)",
            borderRadius: "var(--radius-card)",
            padding: 20,
          }}
        >
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
            <thead>
              <tr style={{ textAlign: "left", color: "var(--text-secondary)" }}>
                <th style={{ padding: "8px" }}>Type</th>
                <th style={{ padding: "8px" }}>Pattern</th>
                <th style={{ padding: "8px" }}>Next sequence</th>
                <th style={{ padding: "8px" }}></th>
              </tr>
            </thead>
            <tbody>
              {patterns.map((p) => (
                <tr key={p.entity_type} style={{ borderTop: "1px solid var(--border-subtle)" }}>
                  <td style={{ padding: "8px" }}>{ENTITY_LABELS[p.entity_type] ?? p.entity_type}</td>
                  <td style={{ padding: "8px" }}>
                    <input
                      aria-label={`${ENTITY_LABELS[p.entity_type] ?? p.entity_type} identifier pattern`}
                      style={{ ...inputStyle, fontFamily: "monospace" }}
                      value={drafts[p.entity_type] ?? ""}
                      onChange={(e) => setDrafts((prev) => ({ ...prev, [p.entity_type]: e.target.value }))}
                    />
                    {rowError[p.entity_type] && (
                      <div style={{ color: "var(--color-critical)", fontSize: 12, marginTop: 4 }}>
                        {rowError[p.entity_type]}
                      </div>
                    )}
                  </td>
                  <td style={{ padding: "8px", color: "var(--text-secondary)" }}>{p.next_sequence}</td>
                  <td style={{ padding: "8px" }}>
                    <button
                      style={{ ...primaryBtn, padding: "4px 12px" }}
                      onClick={() => onSave(p.entity_type)}
                      disabled={saving === p.entity_type || drafts[p.entity_type] === p.pattern}
                    >
                      {saving === p.entity_type ? "Saving…" : "Save"}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div style={sectionStyle}>
        <h2 style={{ fontSize: 16, fontWeight: 700, marginBottom: 4 }}>Compliance status thresholds</h2>
        <p style={{ color: "var(--text-secondary)", fontSize: 13, marginBottom: 12 }}>
          How many days before a deadline a requirement is flagged &ldquo;due soon&rdquo;, and how long a
          newly-applicable requirement has before it&rsquo;s flagged as never assessed.
        </p>
        <div style={cardStyle}>
          {complianceConfig === null ? (
            <div style={{ color: "var(--text-secondary)" }}>Loading…</div>
          ) : (
            <div style={{ display: "flex", gap: 16, flexWrap: "wrap", alignItems: "flex-end" }}>
              <div>
                <label htmlFor="config-due-soon-days" style={{ display: "block", fontSize: 12, color: "var(--text-secondary)", marginBottom: 4 }}>
                  Due soon (days)
                </label>
                <input
                  id="config-due-soon-days"
                  type="number"
                  style={numberInputStyle}
                  value={complianceDraft.due_soon_days}
                  onChange={(e) => setComplianceDraft((prev) => ({ ...prev, due_soon_days: e.target.value }))}
                />
              </div>
              <div>
                <label htmlFor="config-never-assessed-days" style={{ display: "block", fontSize: 12, color: "var(--text-secondary)", marginBottom: 4 }}>
                  Never-assessed grace period (days)
                </label>
                <input
                  id="config-never-assessed-days"
                  type="number"
                  style={numberInputStyle}
                  value={complianceDraft.never_assessed_grace_days}
                  onChange={(e) => setComplianceDraft((prev) => ({ ...prev, never_assessed_grace_days: e.target.value }))}
                />
              </div>
              <button style={primaryBtn} onClick={onSaveCompliance} disabled={complianceSaving}>
                {complianceSaving ? "Saving…" : "Save"}
              </button>
            </div>
          )}
          {complianceError && <p style={{ color: "var(--color-critical)", fontSize: 12, marginTop: 10 }}>{complianceError}</p>}
        </div>
      </div>

      <div style={sectionStyle}>
        <h2 style={{ fontSize: 16, fontWeight: 700, marginBottom: 4 }}>Payment reconciliation</h2>
        <p style={{ color: "var(--text-secondary)", fontSize: 13, marginBottom: 12 }}>
          How many days either side of a rent obligation&rsquo;s due date a payment is still matched to it
          automatically.
        </p>
        <div style={cardStyle}>
          {paymentConfig === null ? (
            <div style={{ color: "var(--text-secondary)" }}>Loading…</div>
          ) : (
            <div style={{ display: "flex", gap: 16, flexWrap: "wrap", alignItems: "flex-end" }}>
              <div>
                <label htmlFor="config-due-date-window" style={{ display: "block", fontSize: 12, color: "var(--text-secondary)", marginBottom: 4 }}>
                  Due date window (days)
                </label>
                <input
                  id="config-due-date-window"
                  type="number"
                  style={numberInputStyle}
                  value={paymentDraft}
                  onChange={(e) => setPaymentDraft(e.target.value)}
                />
              </div>
              <button style={primaryBtn} onClick={onSavePayment} disabled={paymentSaving}>
                {paymentSaving ? "Saving…" : "Save"}
              </button>
            </div>
          )}
          {paymentError && <p style={{ color: "var(--color-critical)", fontSize: 12, marginTop: 10 }}>{paymentError}</p>}
        </div>
      </div>

      <div style={sectionStyle}>
        <h2 style={{ fontSize: 16, fontWeight: 700, marginBottom: 4 }}>Planned investment</h2>
        <p style={{ color: "var(--text-secondary)", fontSize: 13, marginBottom: 12 }}>
          The repair-frequency window and threshold that drive every component&rsquo;s Repair frequency
          factor in its planned investment priority score.
        </p>
        <div style={cardStyle}>
          {investmentConfig === null ? (
            <div style={{ color: "var(--text-secondary)" }}>Loading…</div>
          ) : (
            <div style={{ display: "flex", gap: 16, flexWrap: "wrap", alignItems: "flex-end" }}>
              <div>
                <label htmlFor="config-repair-window" style={{ display: "block", fontSize: 12, color: "var(--text-secondary)", marginBottom: 4 }}>
                  Repair frequency window (months)
                </label>
                <input
                  id="config-repair-window"
                  type="number"
                  style={numberInputStyle}
                  value={investmentDraft.repair_frequency_window_months}
                  onChange={(e) => setInvestmentDraft((prev) => ({ ...prev, repair_frequency_window_months: e.target.value }))}
                />
              </div>
              <div>
                <label htmlFor="config-repair-threshold" style={{ display: "block", fontSize: 12, color: "var(--text-secondary)", marginBottom: 4 }}>
                  Repair frequency threshold
                </label>
                <input
                  id="config-repair-threshold"
                  type="number"
                  style={numberInputStyle}
                  value={investmentDraft.repair_frequency_threshold}
                  onChange={(e) => setInvestmentDraft((prev) => ({ ...prev, repair_frequency_threshold: e.target.value }))}
                />
              </div>
              <button style={primaryBtn} onClick={onSaveInvestment} disabled={investmentSaving}>
                {investmentSaving ? "Saving…" : "Save"}
              </button>
            </div>
          )}
          {investmentError && <p style={{ color: "var(--color-critical)", fontSize: 12, marginTop: 10 }}>{investmentError}</p>}
        </div>
      </div>

      <div style={sectionStyle}>
        <h2 style={{ fontSize: 16, fontWeight: 700, marginBottom: 4 }}>Repair detection rules</h2>
        <p style={{ color: "var(--text-secondary)", fontSize: 13, marginBottom: 12 }}>
          The window, threshold, and installed-base settings behind each repeat-repair/failure signal. A
          blank field is unset for that rule and won&rsquo;t change when you save.
        </p>
        <div style={{ ...cardStyle, overflowX: "auto" }}>
          {repairRuleConfigs === null ? (
            <div style={{ color: "var(--text-secondary)" }}>Loading…</div>
          ) : (
            <table style={{ width: "100%", borderCollapse: "collapse" }}>
              <thead>
                <tr>
                  <th style={thStyle}>Rule</th>
                  <th style={thStyle}>Window (months)</th>
                  <th style={thStyle}>Threshold</th>
                  <th style={thStyle}>Threshold ratio</th>
                  <th style={thStyle}>Min installed base</th>
                  <th style={thStyle}></th>
                </tr>
              </thead>
              <tbody>
                {repairRuleConfigs.map((r) => {
                  const draft = repairDrafts[r.rule_code] ?? toRepairRuleDraft(r);
                  return (
                    <tr key={r.rule_code}>
                      <td style={tdStyle}>{codeLabel(r.rule_code)}</td>
                      {(["window_months", "threshold", "threshold_ratio", "min_installed_base"] as const).map((field) => (
                        <td key={field} style={tdStyle}>
                          <input
                            aria-label={`${codeLabel(r.rule_code)} ${field.replace(/_/g, " ")}`}
                            type="number"
                            style={numberInputStyle}
                            value={draft[field]}
                            onChange={(e) =>
                              setRepairDrafts((prev) => ({ ...prev, [r.rule_code]: { ...draft, [field]: e.target.value } }))
                            }
                          />
                        </td>
                      ))}
                      <td style={tdStyle}>
                        <button
                          style={{ ...primaryBtn, padding: "4px 12px" }}
                          onClick={() => onSaveRepairRule(r.rule_code)}
                          disabled={repairSaving === r.rule_code}
                        >
                          {repairSaving === r.rule_code ? "Saving…" : "Save"}
                        </button>
                        {repairRowError[r.rule_code] && (
                          <div style={{ color: "var(--color-critical)", fontSize: 11, marginTop: 4, maxWidth: 160 }}>
                            {repairRowError[r.rule_code]}
                          </div>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>
      </div>

      <div style={sectionStyle}>
        <h2 style={{ fontSize: 16, fontWeight: 700, marginBottom: 4 }}>Attention rules</h2>
        <p style={{ color: "var(--text-secondary)", fontSize: 13, marginBottom: 12 }}>
          Every rule the Attention Engine scans for. Switch one off to stop it raising new signals for your
          organisation — existing signals it already raised are unaffected.
        </p>
        <div style={{ ...cardStyle, overflowX: "auto" }}>
          {attentionRules === null ? (
            <div style={{ color: "var(--text-secondary)" }}>Loading…</div>
          ) : (
            <table style={{ width: "100%", borderCollapse: "collapse" }}>
              <thead>
                <tr>
                  <th style={thStyle}>Rule</th>
                  <th style={thStyle}>Domain</th>
                  <th style={thStyle}>Default severity</th>
                  <th style={thStyle}>Definition</th>
                  <th style={thStyle}>Active</th>
                </tr>
              </thead>
              <tbody>
                {attentionRules.map((rule) => (
                  <tr key={rule.id}>
                    <td style={tdStyle}>{rule.name}</td>
                    <td style={tdStyle}>{rule.domain_scope}</td>
                    <td style={tdStyle}>{rule.severity_default}</td>
                    <td style={tdStyle}>
                      <details>
                        <summary style={{ cursor: "pointer", color: "var(--color-primary)", fontSize: 12 }}>View</summary>
                        <pre
                          style={{
                            margin: "6px 0 0",
                            background: "var(--bg-app)",
                            borderRadius: 6,
                            padding: "6px 8px",
                            fontSize: 11,
                            fontFamily: "monospace",
                            whiteSpace: "pre-wrap",
                          }}
                        >
                          {JSON.stringify(rule.rule_definition, null, 2)}
                        </pre>
                      </details>
                    </td>
                    <td style={tdStyle}>
                      <label style={{ display: "inline-flex", alignItems: "center", gap: 6, cursor: "pointer" }}>
                        <input
                          type="checkbox"
                          aria-label={`${rule.name} active`}
                          checked={rule.is_active}
                          disabled={attentionSaving === rule.id}
                          onChange={() => onToggleAttentionRule(rule)}
                        />
                        {attentionSaving === rule.id ? "Saving…" : rule.is_active ? "Active" : "Inactive"}
                      </label>
                      {attentionRowError[rule.id] && (
                        <div style={{ color: "var(--color-critical)", fontSize: 11, marginTop: 4, maxWidth: 160 }}>
                          {attentionRowError[rule.id]}
                        </div>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
  );
}
