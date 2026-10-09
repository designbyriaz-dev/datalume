"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { secondaryBtn } from "@/components/formStyles";
import { StatusBadge } from "@/components/StatusBadge";
import { api, ApiError, type DataHealth, type DataHealthCheck } from "@/lib/api";

const SELECTED_ORG_KEY = "datalume.selectedOrganisationId";
const PAGE_SIZE = 50;

// Only entity types with a real detail page get a link — findings for the
// rest (inspection, compliance_action, ...) still show their type and id as
// plain text, same degrading pattern the Audit log page uses.
const ENTITY_LINK_PREFIX: Record<string, string> = {
  property: "/properties",
  component: "/components",
  building: "/buildings",
};

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

function orgId(): string | null {
  return typeof window === "undefined" ? null : window.localStorage.getItem(SELECTED_ORG_KEY);
}

function checkLabel(checkCode: string): string {
  // check_code is always an UPPER_SNAKE_CASE constant — lowercase it
  // first so this reads as "Orphan component", not "ORPHAN COMPONENT".
  return checkCode.replace(/_/g, " ").toLowerCase().replace(/^./, (c) => c.toUpperCase());
}

function severityVariant(severity: string) {
  if (severity === "HIGH") return "critical" as const;
  if (severity === "MEDIUM") return "warning" as const;
  return "neutral" as const;
}

function EntityCell({ type, id }: { type: string; id: string }) {
  const prefix = ENTITY_LINK_PREFIX[type];
  return (
    <>
      {type}
      <div style={{ fontSize: 11, fontFamily: "monospace" }}>
        {prefix ? (
          <Link href={`${prefix}/${id}`} style={{ color: "var(--color-primary)" }}>
            {id}
          </Link>
        ) : (
          <span style={{ color: "var(--text-secondary)" }}>{id}</span>
        )}
      </div>
    </>
  );
}

export default function DataHealthPage() {
  const [checks, setChecks] = useState<DataHealthCheck[] | null>(null);
  const [scorePct, setScorePct] = useState<number | null>(null);
  const [data, setData] = useState<DataHealth | null>(null);
  const [offset, setOffset] = useState(0);
  const [checkCode, setCheckCode] = useState("");
  const [forbidden, setForbidden] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function refresh(atOffset: number, withCheckCode: string) {
    const id = orgId();
    if (!id) return;
    setLoading(true);
    setError(null);
    try {
      const result = await api.dataHealth(id, {
        check_code: withCheckCode || undefined,
        limit: PAGE_SIZE,
        offset: atOffset,
      });
      setData(result);
      setChecks(result.checks);
      setScorePct(result.score_pct);
      setForbidden(false);
    } catch (err) {
      if (err instanceof ApiError && err.status === 403) {
        setForbidden(true);
      } else {
        setError("Couldn't load Data Health findings.");
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
      await refresh(0, "");
    })();
  }, []);

  function onFilterByCheck(code: string) {
    const next = checkCode === code ? "" : code;
    setCheckCode(next);
    setOffset(0);
    refresh(0, next);
  }

  function onClearFilter() {
    setCheckCode("");
    setOffset(0);
    refresh(0, "");
  }

  function onPrevious() {
    const next = Math.max(0, offset - PAGE_SIZE);
    setOffset(next);
    refresh(next, checkCode);
  }

  function onNext() {
    const next = offset + PAGE_SIZE;
    setOffset(next);
    refresh(next, checkCode);
  }

  return (
    <div style={{ maxWidth: 1080 }}>
      <h1 style={{ fontSize: 24, fontWeight: 700, margin: 0, marginBottom: 4 }}>Data Health</h1>
      <p style={{ color: "var(--text-secondary)", marginBottom: 24 }}>
        Every data quality check run across your organisation, and every record currently failing one —
        not just the ones that happen to show up on a property page.
      </p>

      {forbidden ? (
        <div style={cardStyle}>
          <p style={{ margin: 0, color: "var(--text-secondary)" }}>
            You don&rsquo;t have permission to view Data Health for this organisation.
          </p>
        </div>
      ) : (
        <>
          {scorePct !== null && (
            <div style={{ ...cardStyle, marginBottom: 16, display: "flex", alignItems: "baseline", gap: 10 }}>
              <span style={{ fontSize: 28, fontWeight: 700 }}>{scorePct}%</span>
              <span style={{ color: "var(--text-secondary)", fontSize: 13 }}>overall data health score</span>
            </div>
          )}

          {error && <p style={{ color: "var(--color-critical)", fontSize: 13, marginBottom: 16 }}>{error}</p>}

          <div style={{ ...cardStyle, marginBottom: 16, overflowX: "auto" }}>
            {!checks ? (
              <div style={{ color: "var(--text-secondary)" }}>Loading…</div>
            ) : (
              <table style={{ width: "100%", borderCollapse: "collapse" }}>
                <thead>
                  <tr>
                    <th style={thStyle}>Check</th>
                    <th style={thStyle}>Applicable</th>
                    <th style={thStyle}>Failing</th>
                    <th style={thStyle}>Pass rate</th>
                    <th style={thStyle}></th>
                  </tr>
                </thead>
                <tbody>
                  {checks.map((c) => (
                    <tr key={c.check_code}>
                      <td style={tdStyle}>{checkLabel(c.check_code)}</td>
                      <td style={tdStyle}>{c.applicable_count}</td>
                      <td style={tdStyle}>{c.failing_count}</td>
                      <td style={tdStyle}>{Math.round(c.pass_ratio * 100)}%</td>
                      <td style={tdStyle}>
                        {c.failing_count > 0 && (
                          <button
                            style={{ ...secondaryBtn, padding: "2px 10px", fontSize: 11 }}
                            onClick={() => onFilterByCheck(c.check_code)}
                          >
                            {checkCode === c.check_code ? "Clear filter" : "View findings"}
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>

          {checkCode && (
            <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 12, fontSize: 13 }}>
              <span>
                Showing findings for <strong>{checkLabel(checkCode)}</strong> only
              </span>
              <button style={secondaryBtn} onClick={onClearFilter}>
                Clear
              </button>
            </div>
          )}

          <div style={cardStyle}>
            {loading ? (
              <div style={{ color: "var(--text-secondary)" }}>Loading…</div>
            ) : !data || data.findings.length === 0 ? (
              <div style={{ color: "var(--text-secondary)", fontSize: 14 }}>
                No findings {checkCode ? "for this check" : "at all"} — everything&rsquo;s in order.
              </div>
            ) : (
              <table style={{ width: "100%", borderCollapse: "collapse" }}>
                <thead>
                  <tr>
                    <th style={thStyle}>Check</th>
                    <th style={thStyle}>Severity</th>
                    <th style={thStyle}>Affected record</th>
                    <th style={thStyle}>Message</th>
                  </tr>
                </thead>
                <tbody>
                  {data.findings.map((f, i) => (
                    <tr key={`${f.check_code}-${f.affected_entity_id}-${i}`}>
                      <td style={tdStyle}>{checkLabel(f.check_code)}</td>
                      <td style={tdStyle}>
                        <StatusBadge label={f.severity} variant={severityVariant(f.severity)} />
                      </td>
                      <td style={tdStyle}>
                        <EntityCell type={f.affected_entity_type} id={f.affected_entity_id} />
                      </td>
                      <td style={tdStyle}>{f.message}</td>
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
              disabled={loading || !data || offset + data.findings.length >= data.findings_total}
            >
              Next
            </button>
          </div>
        </>
      )}
    </div>
  );
}
