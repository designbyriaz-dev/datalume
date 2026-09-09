"use client";

import { useEffect, useState } from "react";
import { StatusBadge } from "@/components/StatusBadge";
import { inputStyle, primaryBtn } from "@/components/formStyles";
import { api, type ArrearsSnapshot, type CollectionRate, type LeaseOut } from "@/lib/api";

const SELECTED_ORG_KEY = "datalume.selectedOrganisationId";

const AGE_BUCKET_ORDER = ["CURRENT", "1-30", "31-60", "61-90", "90+"];

function money(pence: number) {
  return `£${(pence / 100).toFixed(2)}`;
}

function bucketVariant(bucket: string) {
  if (bucket === "CURRENT") return "success" as const;
  if (bucket === "1-30") return "neutral" as const;
  if (bucket === "31-60") return "warning" as const;
  return "critical" as const;
}

export default function ArrearsPage() {
  const [leases, setLeases] = useState<LeaseOut[] | null>(null);
  const [leaseId, setLeaseId] = useState("");
  const [snapshot, setSnapshot] = useState<ArrearsSnapshot | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [periodStart, setPeriodStart] = useState(() => new Date(Date.now() - 30 * 24 * 60 * 60 * 1000).toISOString().slice(0, 10));
  const [periodEnd, setPeriodEnd] = useState(() => new Date().toISOString().slice(0, 10));
  const [collectionRate, setCollectionRate] = useState<CollectionRate | null>(null);

  function orgId(): string | null {
    return typeof window === "undefined" ? null : window.localStorage.getItem(SELECTED_ORG_KEY);
  }

  async function refreshSnapshot(id: string, lease: string) {
    if (!lease) return;
    setSnapshot(await api.getLeaseArrears(id, lease));
  }

  async function refreshCollectionRate(id: string) {
    setCollectionRate(await api.getCollectionRate(id, periodStart, periodEnd));
  }

  useEffect(() => {
    (async () => {
      const id = orgId();
      if (!id) {
        setLoadError("No organisation selected.");
        return;
      }
      try {
        const leaseList = await api.listLeases(id);
        setLeases(leaseList);
        if (leaseList[0]) {
          setLeaseId(leaseList[0].id);
          await refreshSnapshot(id, leaseList[0].id);
        }
        await refreshCollectionRate(id);
      } catch {
        setLoadError("Couldn't load arrears data.");
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function onSelectLease(nextLeaseId: string) {
    const id = orgId();
    setLeaseId(nextLeaseId);
    setSnapshot(null);
    if (id) await refreshSnapshot(id, nextLeaseId);
  }

  async function onRecomputeCollectionRate() {
    const id = orgId();
    if (!id) return;
    await refreshCollectionRate(id);
  }

  if (loadError) {
    return <div style={{ color: "var(--text-secondary)" }}>{loadError}</div>;
  }

  if (!leases) {
    return <div style={{ color: "var(--text-secondary)" }}>Loading…</div>;
  }

  return (
    <div style={{ maxWidth: 900 }}>
      <h1 style={{ fontSize: 24, fontWeight: 700, margin: 0, marginBottom: 4 }}>Arrears</h1>
      <p style={{ color: "var(--text-secondary)", marginBottom: 24 }}>
        Outstanding balance and ageing are always computed fresh from rent obligations and matched payments — never
        stored, so there&rsquo;s nothing to go stale between payments.
      </p>

      <h2 style={{ fontSize: 16, fontWeight: 700, marginBottom: 12 }}>Lease arrears snapshot</h2>
      {leases.length === 0 ? (
        <div style={{ color: "var(--text-secondary)", fontSize: 14, marginBottom: 24 }}>No leases recorded yet.</div>
      ) : (
        <>
          <select style={{ ...inputStyle, maxWidth: 300, marginBottom: 16 }} value={leaseId} onChange={(e) => onSelectLease(e.target.value)}>
            {leases.map((l) => (
              <option key={l.id} value={l.id}>
                {l.lease_reference}
              </option>
            ))}
          </select>

          {!snapshot ? (
            <div style={{ color: "var(--text-secondary)", fontSize: 14, marginBottom: 24 }}>Loading…</div>
          ) : (
            <div
              style={{
                background: "var(--bg-card)",
                border: "1px solid var(--border-subtle)",
                borderRadius: "var(--radius-card)",
                padding: 20,
                marginBottom: 24,
                fontSize: 13,
              }}
            >
              <div style={{ display: "flex", gap: 24, marginBottom: 16, flexWrap: "wrap" }}>
                <div>
                  <div style={{ color: "var(--text-secondary)", marginBottom: 2 }}>Total due</div>
                  <div style={{ fontSize: 18, fontWeight: 700 }}>{money(snapshot.total_due_pence)}</div>
                </div>
                <div>
                  <div style={{ color: "var(--text-secondary)", marginBottom: 2 }}>Outstanding</div>
                  <div style={{ fontSize: 18, fontWeight: 700, color: snapshot.outstanding_pence > 0 ? "var(--color-critical)" : undefined }}>
                    {money(snapshot.outstanding_pence)}
                  </div>
                </div>
                <div>
                  <div style={{ color: "var(--text-secondary)", marginBottom: 2 }}>Credits</div>
                  <div style={{ fontSize: 18, fontWeight: 700 }}>{money(snapshot.credits_pence)}</div>
                </div>
                <div>
                  <div style={{ color: "var(--text-secondary)", marginBottom: 2 }}>Unallocated payments</div>
                  <div style={{ fontSize: 18, fontWeight: 700 }}>{money(snapshot.unallocated_pence)}</div>
                </div>
              </div>
              <div style={{ color: "var(--text-secondary)", marginBottom: 8 }}>Ageing (as of {snapshot.as_of})</div>
              <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                {AGE_BUCKET_ORDER.map((bucket) => (
                  <StatusBadge key={bucket} label={`${bucket}: ${money(snapshot.ageing_pence[bucket] ?? 0)}`} variant={bucketVariant(bucket)} />
                ))}
              </div>
            </div>
          )}
        </>
      )}

      <h2 style={{ fontSize: 16, fontWeight: 700, marginBottom: 12 }}>Portfolio collection rate</h2>
      <div style={{ display: "flex", gap: 12, alignItems: "end", marginBottom: 16 }}>
        <div>
          <label htmlFor="arrears-period-start" style={{ fontSize: 12, color: "var(--text-secondary)", display: "block", marginBottom: 4 }}>Period start</label>
          <input id="arrears-period-start" style={inputStyle} type="date" value={periodStart} onChange={(e) => setPeriodStart(e.target.value)} />
        </div>
        <div>
          <label htmlFor="arrears-period-end" style={{ fontSize: 12, color: "var(--text-secondary)", display: "block", marginBottom: 4 }}>Period end</label>
          <input id="arrears-period-end" style={inputStyle} type="date" value={periodEnd} onChange={(e) => setPeriodEnd(e.target.value)} />
        </div>
        <button style={primaryBtn} onClick={onRecomputeCollectionRate}>
          Recompute
        </button>
      </div>
      {collectionRate && (
        <div
          style={{
            background: "var(--bg-card)",
            border: "1px solid var(--border-subtle)",
            borderRadius: "var(--radius-card)",
            padding: 20,
            fontSize: 13,
            display: "flex",
            gap: 24,
          }}
        >
          <div>
            <div style={{ color: "var(--text-secondary)", marginBottom: 2 }}>Due</div>
            <div style={{ fontSize: 18, fontWeight: 700 }}>{money(collectionRate.due_pence)}</div>
          </div>
          <div>
            <div style={{ color: "var(--text-secondary)", marginBottom: 2 }}>Collected</div>
            <div style={{ fontSize: 18, fontWeight: 700 }}>{money(collectionRate.collected_pence)}</div>
          </div>
          <div>
            <div style={{ color: "var(--text-secondary)", marginBottom: 2 }}>Collection rate</div>
            <div style={{ fontSize: 18, fontWeight: 700 }}>{(collectionRate.collection_rate * 100).toFixed(1)}%</div>
          </div>
        </div>
      )}
    </div>
  );
}
