# 05 — Commercial Domain: Tenancies, Leases, Rent, Payments, Arrears

Covers spec items 50–54, 58–65 (rent/payment portion): Tenancy Model,
Lease Model, Rent Obligation, Payment Transaction, Payment Allocation,
Arrears, Collection Rate, Service Charges, Payment Boundary.

## 1. Core schema

```sql
tenants(id, organisation_id, name, contact_details JSONB, ...ProvenanceMixin)
leases(id, organisation_id, property_id, tenant_id, lease_reference,
       lease_start, lease_expiry, break_date NULL, rent_review_date NULL,
       contractual_rent, rent_frequency, service_charge_amount NULL,
       occupancy_status, lease_status, ...ProvenanceMixin)
rent_obligations(id, organisation_id, lease_id, obligation_type,
                  -- RENT | SERVICE_CHARGE | INSURANCE_RECHARGE | UTILITY_RECHARGE | OTHER
                  due_date, period_start, period_end, amount_due, currency,
                  invoice_reference NULL, status)
payment_transactions(id, organisation_id, lease_id NULL, amount, currency,
                      received_date, payer_reference NULL, method NULL,
                      ...ProvenanceMixin)
payment_allocations(id, payment_transaction_id, rent_obligation_id NULL,
                     amount_allocated, allocation_status)
                     -- MATCHED | POSSIBLE_MATCH | UNALLOCATED | NEEDS_REVIEW
```

**Decision:** `rent_obligations` (what is owed) and `payment_transactions`
(what was received) are separate tables joined only through
`payment_allocations`, never a single "ledger row" that conflates the
two.
**Rationale:** spec §52 requires supporting exact/possible/partial/
overpayment/unallocated matches — that is inherently a many-to-many
relationship (one payment can cover several obligations; one obligation
can be paid in instalments), which a single combined ledger row cannot
represent without duplication or lossy simplification.

## 2. Reconciliation

`PaymentReconciler.match(payment_transaction)` runs deterministic
matching rules in order: exact reference match → exact
amount+lease+due-date-window match → partial-amount candidate → no match
→ `UNALLOCATED`, `NEEDS_REVIEW` for anything ambiguous. **Never
auto-allocates an ambiguous payment** (spec §52: "never silently allocate
ambiguous money") — `NEEDS_REVIEW` rows surface in a work queue for a
`RENT_MANAGER` to resolve manually, and that manual resolution is itself
an audited `payment_allocations` write with `source_type = MANUAL`.

## 3. Rent & arrears intelligence

```python
def arrears_for_lease(lease_id: UUID, as_of: date = today()) -> ArrearsSnapshot:
    obligations = due_obligations(lease_id, as_of)
    allocated = matched_allocations(lease_id, as_of)
    outstanding = obligations.total_due - allocated.total_matched
    ageing = age_buckets(obligations, allocated, as_of)  # CURRENT, 1-30, 31-60, 61-90, 90+
    return ArrearsSnapshot(outstanding, ageing, credits=allocated.overpaid,
                            unallocated=unallocated_payments(lease_id, as_of))

def collection_rate(organisation_id: UUID, period: DateRange) -> float:
    due = sum_rent_obligations(organisation_id, period)
    collected = sum_matched_payments(organisation_id, period)
    return collected / due if due else 1.0
```

Both are pure, deterministic, unit-tested functions over the schema
above (spec §75: "rent → payment → arrears" integration test) — the same
"deterministic analytics, AI explains" boundary from the operations
domain applies here identically.

## 4. Payment boundary — what Build 1 explicitly does not do

Spec §54 is unambiguous: Build 1 does not hold tenant money, act as a
bank, directly process cards or Direct Debits, transfer funds, or operate
stored value. `payment_transactions` is a **record of a payment that
happened elsewhere** (bank feed import, manual entry, or — in a later
build — a read-only webhook from an authorised payment provider), never
a payment *initiation* API. There is no `POST /payments/charge` endpoint
anywhere in this architecture, by design — only `POST /payments` to
record a transaction that already occurred. DataLume's own SaaS billing
(Stripe, spec §65) is a completely separate system from this domain (see
07) — this is explicitly called out to prevent the two "billing" concepts
(what a tenant pays their landlord vs. what the landlord pays DataLume)
from ever sharing a code path.
