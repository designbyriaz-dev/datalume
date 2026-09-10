"use client";

import { useEffect, useState } from "react";
import { StatusBadge } from "@/components/StatusBadge";
import { inputStyle, primaryBtn, secondaryBtn } from "@/components/formStyles";
import {
  api,
  type LeaseOut,
  type PaymentAllocationOut,
  type RentObligationOut,
} from "@/lib/api";

const SELECTED_ORG_KEY = "datalume.selectedOrganisationId";

const OBLIGATION_TYPES = ["RENT", "SERVICE_CHARGE", "INSURANCE_RECHARGE", "UTILITY_RECHARGE", "OTHER"] as const;

function money(pence: number) {
  return `£${(pence / 100).toFixed(2)}`;
}

function allocationVariant(status: string) {
  if (status === "MATCHED") return "success" as const;
  if (status === "POSSIBLE_MATCH") return "warning" as const;
  if (status === "NEEDS_REVIEW") return "critical" as const;
  return "neutral" as const;
}

function ResolveAllocationRow({
  organisationId,
  allocation,
  leaseObligations,
  onResolved,
}: {
  organisationId: string;
  allocation: PaymentAllocationOut;
  leaseObligations: RentObligationOut[];
  onResolved: () => void;
}) {
  const [obligationId, setObligationId] = useState(leaseObligations[0]?.id ?? "");
  const [amount, setAmount] = useState((allocation.amount_allocated_pence / 100).toFixed(2));
  const [submitting, setSubmitting] = useState(false);

  async function onResolve() {
    if (!obligationId) return;
    setSubmitting(true);
    try {
      await api.resolvePaymentAllocation(organisationId, allocation.id, {
        rent_obligation_id: obligationId,
        amount_allocated_pence: Math.round(parseFloat(amount) * 100),
      });
      onResolved();
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <li style={{ padding: "8px 0", borderTop: "1px solid var(--border-subtle)", fontSize: 13 }}>
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 6 }}>
        <span>Allocation {allocation.id.slice(0, 8)} — {money(allocation.amount_allocated_pence)}</span>
        <StatusBadge label={allocation.allocation_status.replace(/_/g, " ")} variant={allocationVariant(allocation.allocation_status)} />
      </div>
      {leaseObligations.length === 0 ? (
        <div style={{ color: "var(--text-secondary)", fontSize: 12 }}>No obligations recorded on this lease to resolve against yet.</div>
      ) : (
        <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
          <select aria-label="Obligation to resolve against" style={{ ...inputStyle, fontSize: 12 }} value={obligationId} onChange={(e) => setObligationId(e.target.value)}>
            {leaseObligations.map((o) => (
              <option key={o.id} value={o.id}>
                {o.obligation_type} due {o.due_date} — outstanding {money(o.outstanding_pence)}
              </option>
            ))}
          </select>
          <input aria-label="Amount to resolve" style={{ ...inputStyle, fontSize: 12, maxWidth: 100 }} type="number" step="0.01" value={amount} onChange={(e) => setAmount(e.target.value)} />
          <button style={{ ...secondaryBtn, padding: "4px 10px", fontSize: 12 }} onClick={onResolve} disabled={submitting}>
            Resolve
          </button>
        </div>
      )}
    </li>
  );
}

export default function RentAndPaymentsPage() {
  const [leases, setLeases] = useState<LeaseOut[] | null>(null);
  const [obligations, setObligations] = useState<RentObligationOut[] | null>(null);
  const [pendingAllocations, setPendingAllocations] = useState<PaymentAllocationOut[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [selectedLeaseId, setSelectedLeaseId] = useState("");

  const [obligationType, setObligationType] = useState<(typeof OBLIGATION_TYPES)[number]>("RENT");
  const [dueDate, setDueDate] = useState("");
  const [periodStart, setPeriodStart] = useState("");
  const [periodEnd, setPeriodEnd] = useState("");
  const [amountDue, setAmountDue] = useState("");
  const [invoiceReference, setInvoiceReference] = useState("");
  const [obligationSubmitting, setObligationSubmitting] = useState(false);
  const [obligationError, setObligationError] = useState<string | null>(null);

  const [paymentLeaseId, setPaymentLeaseId] = useState("");
  const [paymentAmount, setPaymentAmount] = useState("");
  const [paymentDate, setPaymentDate] = useState("");
  const [payerReference, setPayerReference] = useState("");
  const [paymentSubmitting, setPaymentSubmitting] = useState(false);
  const [paymentError, setPaymentError] = useState<string | null>(null);
  const [lastPaymentResult, setLastPaymentResult] = useState<string | null>(null);

  function orgId(): string | null {
    return typeof window === "undefined" ? null : window.localStorage.getItem(SELECTED_ORG_KEY);
  }

  async function refreshObligations(leaseId: string) {
    const id = orgId();
    if (!id || !leaseId) return;
    setObligations(await api.listRentObligations(id, { lease_id: leaseId }));
  }

  async function refreshPendingAllocations() {
    const id = orgId();
    if (!id) return;
    const [needsReview, unallocated, possible] = await Promise.all([
      api.listPaymentAllocations(id, { allocation_status: "NEEDS_REVIEW" }),
      api.listPaymentAllocations(id, { allocation_status: "UNALLOCATED" }),
      api.listPaymentAllocations(id, { allocation_status: "POSSIBLE_MATCH" }),
    ]);
    setPendingAllocations([...needsReview, ...unallocated, ...possible]);
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
          setSelectedLeaseId(leaseList[0].id);
          setPaymentLeaseId(leaseList[0].id);
          setObligations(await api.listRentObligations(id, { lease_id: leaseList[0].id }));
        } else {
          setObligations([]);
        }
        await refreshPendingAllocations();
      } catch {
        setLoadError("Couldn't load rent & payments data.");
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function onSelectLease(leaseId: string) {
    setSelectedLeaseId(leaseId);
    setObligations(null);
    await refreshObligations(leaseId);
  }

  async function onAddObligation() {
    const id = orgId();
    if (!id || !selectedLeaseId || !dueDate || !periodStart || !periodEnd || !amountDue) {
      setObligationError("Fill in due date, period, and amount.");
      return;
    }
    setObligationSubmitting(true);
    setObligationError(null);
    try {
      await api.createRentObligation(id, {
        lease_id: selectedLeaseId,
        obligation_type: obligationType,
        due_date: dueDate,
        period_start: periodStart,
        period_end: periodEnd,
        amount_due_pence: Math.round(parseFloat(amountDue) * 100),
        invoice_reference: invoiceReference.trim() || undefined,
      });
      setDueDate("");
      setPeriodStart("");
      setPeriodEnd("");
      setAmountDue("");
      setInvoiceReference("");
      await refreshObligations(selectedLeaseId);
    } catch {
      setObligationError("Couldn't add that obligation.");
    } finally {
      setObligationSubmitting(false);
    }
  }

  async function onRecordPayment() {
    const id = orgId();
    if (!id || !paymentAmount || !paymentDate) {
      setPaymentError("Fill in amount and received date.");
      return;
    }
    setPaymentSubmitting(true);
    setPaymentError(null);
    setLastPaymentResult(null);
    try {
      const result = await api.createPayment(id, {
        lease_id: paymentLeaseId || undefined,
        amount_pence: Math.round(parseFloat(paymentAmount) * 100),
        received_date: paymentDate,
        payer_reference: payerReference.trim() || undefined,
      });
      setLastPaymentResult(`Recorded — reconciliation result: ${result.allocation.allocation_status.replace(/_/g, " ")}`);
      setPaymentAmount("");
      setPayerReference("");
      if (selectedLeaseId) await refreshObligations(selectedLeaseId);
      await refreshPendingAllocations();
    } catch {
      setPaymentError("Couldn't record that payment.");
    } finally {
      setPaymentSubmitting(false);
    }
  }

  if (loadError) {
    return <div style={{ color: "var(--text-secondary)" }}>{loadError}</div>;
  }

  if (!leases || !pendingAllocations) {
    return <div style={{ color: "var(--text-secondary)" }}>Loading…</div>;
  }

  const leaseObligationsFor = (leaseId: string | null) =>
    leaseId ? (obligations ?? []).filter((o) => o.status === "ACTIVE") : [];

  return (
    <div style={{ maxWidth: 1000 }}>
      <h1 style={{ fontSize: 24, fontWeight: 700, margin: 0, marginBottom: 4 }}>Rent &amp; Payments</h1>
      <p style={{ color: "var(--text-secondary)", marginBottom: 24 }}>
        Payments are records of money received elsewhere, never a charge — DataLume doesn&rsquo;t hold tenant money
        or move it. Every payment is run through deterministic reconciliation the moment it&rsquo;s recorded;
        anything ambiguous lands in the queue below for manual resolution rather than being silently guessed.
      </p>

      {pendingAllocations.length > 0 && (
        <div style={{ marginBottom: 24 }}>
          <h2 style={{ fontSize: 16, fontWeight: 700, marginBottom: 12 }}>Needs attention ({pendingAllocations.length})</h2>
          <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
            {pendingAllocations.map((a) => (
              <ResolveAllocationRow
                key={a.id}
                organisationId={orgId() ?? ""}
                allocation={a}
                leaseObligations={leaseObligationsFor(selectedLeaseId)}
                onResolved={async () => {
                  await refreshPendingAllocations();
                  if (selectedLeaseId) await refreshObligations(selectedLeaseId);
                }}
              />
            ))}
          </ul>
          <div style={{ color: "var(--text-secondary)", fontSize: 12, marginTop: 6 }}>
            Obligation choices shown are for the lease currently selected below — switch lease to resolve against a
            different one.
          </div>
        </div>
      )}

      <div
        style={{
          background: "var(--bg-card)",
          border: "1px solid var(--border-subtle)",
          borderRadius: "var(--radius-card)",
          padding: 20,
          marginBottom: 24,
        }}
      >
        <h2 style={{ fontSize: 16, fontWeight: 700, margin: 0, marginBottom: 16 }}>Record a payment</h2>
        <div style={{ display: "grid", gap: 12, gridTemplateColumns: "1.3fr 1fr 1fr 1.3fr auto", alignItems: "end" }}>
          <div>
            <label htmlFor="payment-lease" style={{ fontSize: 12, color: "var(--text-secondary)", display: "block", marginBottom: 4 }}>Lease (optional)</label>
            <select id="payment-lease" style={inputStyle} value={paymentLeaseId} onChange={(e) => setPaymentLeaseId(e.target.value)}>
              <option value="">Unassigned</option>
              {leases.map((l) => (
                <option key={l.id} value={l.id}>
                  {l.lease_reference}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label htmlFor="payment-amount" style={{ fontSize: 12, color: "var(--text-secondary)", display: "block", marginBottom: 4 }}>Amount (£)</label>
            <input id="payment-amount" style={inputStyle} type="number" step="0.01" value={paymentAmount} onChange={(e) => setPaymentAmount(e.target.value)} />
          </div>
          <div>
            <label htmlFor="payment-received-date" style={{ fontSize: 12, color: "var(--text-secondary)", display: "block", marginBottom: 4 }}>Received</label>
            <input id="payment-received-date" style={inputStyle} type="date" value={paymentDate} onChange={(e) => setPaymentDate(e.target.value)} />
          </div>
          <div>
            <label htmlFor="payment-payer-reference" style={{ fontSize: 12, color: "var(--text-secondary)", display: "block", marginBottom: 4 }}>Payer reference</label>
            <input id="payment-payer-reference" style={inputStyle} value={payerReference} onChange={(e) => setPayerReference(e.target.value)} placeholder="e.g. INV-001" />
          </div>
          <button style={primaryBtn} onClick={onRecordPayment} disabled={paymentSubmitting}>
            {paymentSubmitting ? "Recording…" : "Record"}
          </button>
        </div>
        {lastPaymentResult && <div style={{ color: "var(--color-primary)", fontSize: 13, marginTop: 10 }}>{lastPaymentResult}</div>}
        {paymentError && <div style={{ color: "var(--color-critical)", fontSize: 13, marginTop: 10 }}>{paymentError}</div>}
      </div>

      <h2 style={{ fontSize: 16, fontWeight: 700, marginBottom: 12 }}>Rent obligations</h2>
      <div style={{ marginBottom: 12 }}>
        <label htmlFor="obligations-lease" style={{ fontSize: 12, color: "var(--text-secondary)", display: "block", marginBottom: 4 }}>Lease</label>
        <select id="obligations-lease" style={{ ...inputStyle, maxWidth: 300 }} value={selectedLeaseId} onChange={(e) => onSelectLease(e.target.value)}>
          {leases.map((l) => (
            <option key={l.id} value={l.id}>
              {l.lease_reference}
            </option>
          ))}
        </select>
      </div>

      <div
        style={{
          background: "var(--bg-card)",
          border: "1px solid var(--border-subtle)",
          borderRadius: "var(--radius-card)",
          padding: 16,
          marginBottom: 16,
        }}
      >
        <div style={{ display: "grid", gap: 10, gridTemplateColumns: "1fr 1fr 1fr 1fr 1fr 1fr auto", alignItems: "end" }}>
          <div>
            <label htmlFor="obligation-type" style={{ fontSize: 11, color: "var(--text-secondary)", display: "block", marginBottom: 4 }}>Type</label>
            <select id="obligation-type" style={{ ...inputStyle, fontSize: 12 }} value={obligationType} onChange={(e) => setObligationType(e.target.value as (typeof OBLIGATION_TYPES)[number])}>
              {OBLIGATION_TYPES.map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label htmlFor="obligation-due-date" style={{ fontSize: 11, color: "var(--text-secondary)", display: "block", marginBottom: 4 }}>Due date</label>
            <input id="obligation-due-date" style={{ ...inputStyle, fontSize: 12 }} type="date" value={dueDate} onChange={(e) => setDueDate(e.target.value)} />
          </div>
          <div>
            <label htmlFor="obligation-period-start" style={{ fontSize: 11, color: "var(--text-secondary)", display: "block", marginBottom: 4 }}>Period start</label>
            <input id="obligation-period-start" style={{ ...inputStyle, fontSize: 12 }} type="date" value={periodStart} onChange={(e) => setPeriodStart(e.target.value)} />
          </div>
          <div>
            <label htmlFor="obligation-period-end" style={{ fontSize: 11, color: "var(--text-secondary)", display: "block", marginBottom: 4 }}>Period end</label>
            <input id="obligation-period-end" style={{ ...inputStyle, fontSize: 12 }} type="date" value={periodEnd} onChange={(e) => setPeriodEnd(e.target.value)} />
          </div>
          <div>
            <label htmlFor="obligation-amount" style={{ fontSize: 11, color: "var(--text-secondary)", display: "block", marginBottom: 4 }}>Amount (£)</label>
            <input id="obligation-amount" style={{ ...inputStyle, fontSize: 12 }} type="number" step="0.01" value={amountDue} onChange={(e) => setAmountDue(e.target.value)} />
          </div>
          <div>
            <label htmlFor="obligation-invoice-ref" style={{ fontSize: 11, color: "var(--text-secondary)", display: "block", marginBottom: 4 }}>Invoice ref</label>
            <input id="obligation-invoice-ref" style={{ ...inputStyle, fontSize: 12 }} value={invoiceReference} onChange={(e) => setInvoiceReference(e.target.value)} />
          </div>
          <button style={{ ...primaryBtn, padding: "6px 12px", fontSize: 12 }} onClick={onAddObligation} disabled={obligationSubmitting}>
            {obligationSubmitting ? "Adding…" : "Add"}
          </button>
        </div>
        {obligationError && <div style={{ color: "var(--color-critical)", fontSize: 12, marginTop: 8 }}>{obligationError}</div>}
      </div>

      {obligations === null ? (
        <div style={{ color: "var(--text-secondary)", fontSize: 14 }}>Loading…</div>
      ) : obligations.length === 0 ? (
        <div style={{ color: "var(--text-secondary)", fontSize: 14 }}>No obligations recorded for this lease yet.</div>
      ) : (
        <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
          {obligations.map((o) => (
            <li key={o.id} style={{ padding: "8px 0", borderTop: "1px solid var(--border-subtle)", fontSize: 13, display: "flex", justifyContent: "space-between" }}>
              <span>
                {o.obligation_type} · due {o.due_date} {o.invoice_reference && `· ${o.invoice_reference}`}
              </span>
              <span>
                {money(o.amount_due_pence)}{" "}
                <span style={{ color: o.outstanding_pence > 0 ? "var(--color-critical)" : "var(--text-secondary)" }}>
                  ({o.outstanding_pence > 0 ? `${money(o.outstanding_pence)} outstanding` : "settled"})
                </span>
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
