"use client";

import { useEffect, useState } from "react";
import { StatusBadge } from "@/components/StatusBadge";
import { api, ApiError, type Plan, type Subscription } from "@/lib/api";

const SELECTED_ORG_KEY = "datalume.selectedOrganisationId";

function formatPence(pence: number | null): string {
  if (pence === null) return "Custom";
  return `£${(pence / 100).toLocaleString(undefined, { minimumFractionDigits: 0 })}/mo`;
}

function statusVariant(status: Subscription["status"]) {
  if (status === "ACTIVE") return "success" as const;
  if (status === "TRIALING") return "neutral" as const;
  if (status === "PAST_DUE") return "warning" as const;
  return "critical" as const;
}

// Defined outside the component so the navigation side effect isn't
// attributed to component/hook body purity analysis (react-hooks/immutability).
function redirectTo(url: string) {
  window.location.href = url;
}

export default function BillingPage() {
  const [subscription, setSubscription] = useState<Subscription | null>(null);
  const [plans, setPlans] = useState<Plan[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionMessage, setActionMessage] = useState<string | null>(null);
  const [pendingPlan, setPendingPlan] = useState<string | null>(null);
  const [portalPending, setPortalPending] = useState(false);

  useEffect(() => {
    (async () => {
      const orgId = window.localStorage.getItem(SELECTED_ORG_KEY);
      if (!orgId) {
        setError("No organisation selected.");
        setLoading(false);
        return;
      }
      try {
        const [sub, planList] = await Promise.all([api.subscription(orgId), api.listPlans()]);
        setSubscription(sub);
        setPlans(planList);
      } catch {
        setError("Couldn't load billing information.");
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  async function onUpgrade(planCode: string) {
    const orgId = window.localStorage.getItem(SELECTED_ORG_KEY);
    if (!orgId) return;
    setPendingPlan(planCode);
    setActionMessage(null);
    try {
      const { checkout_url } = await api.startCheckout(orgId, planCode);
      redirectTo(checkout_url);
    } catch (err) {
      if (err instanceof ApiError && err.status === 503) {
        setActionMessage(
          "Billing isn't wired up to Stripe yet in this environment — get in touch and we'll upgrade your plan manually.",
        );
      } else {
        setActionMessage("Something went wrong starting checkout. Please try again.");
      }
    } finally {
      setPendingPlan(null);
    }
  }

  async function onManageBilling() {
    const orgId = window.localStorage.getItem(SELECTED_ORG_KEY);
    if (!orgId) return;
    setPortalPending(true);
    setActionMessage(null);
    try {
      const { portal_url } = await api.startBillingPortal(orgId);
      redirectTo(portal_url);
    } catch (err) {
      if (err instanceof ApiError && err.status === 503) {
        setActionMessage(
          "Billing isn't wired up to Stripe yet in this environment — get in touch and we'll manage your plan manually.",
        );
      } else {
        setActionMessage("Something went wrong opening the billing portal. Please try again.");
      }
    } finally {
      setPortalPending(false);
    }
  }

  if (loading) {
    return <div style={{ color: "var(--text-secondary)" }}>Loading…</div>;
  }

  if (error) {
    return <div style={{ color: "var(--text-secondary)" }}>{error}</div>;
  }

  return (
    <div style={{ maxWidth: 880 }}>
      <h1 style={{ fontSize: 24, fontWeight: 700, margin: 0, marginBottom: 4 }}>Billing</h1>
      <p style={{ color: "var(--text-secondary)", marginBottom: 24 }}>
        Your DataLume subscription — separate from any rent or tenant payments tracked elsewhere in
        the product.
      </p>

      {subscription && (
        <div
          style={{
            background: "var(--bg-card)",
            border: "1px solid var(--border-subtle)",
            borderRadius: "var(--radius-card)",
            padding: 24,
            marginBottom: 32,
            display: "flex",
            justifyContent: "space-between",
            alignItems: "flex-start",
          }}
        >
          <div>
            <div style={{ fontSize: 13, color: "var(--text-secondary)", marginBottom: 4 }}>
              Current plan
            </div>
            <div style={{ fontSize: 20, fontWeight: 700 }}>{subscription.plan.name}</div>
            {subscription.current_period_end && (
              <div style={{ fontSize: 13, color: "var(--text-secondary)", marginTop: 6 }}>
                {subscription.status === "TRIALING" ? "Trial ends" : "Renews"}{" "}
                {new Date(subscription.current_period_end).toLocaleDateString()}
              </div>
            )}
          </div>
          <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 12 }}>
            <StatusBadge label={subscription.status} variant={statusVariant(subscription.status)} />
            <button
              onClick={onManageBilling}
              disabled={portalPending}
              style={{
                padding: "7px 14px",
                borderRadius: 8,
                border: "1px solid var(--border-subtle)",
                background: "var(--bg-app)",
                color: "var(--text-primary)",
                fontWeight: 600,
                fontSize: 13,
                cursor: portalPending ? "default" : "pointer",
              }}
            >
              {portalPending ? "Opening…" : "Manage billing"}
            </button>
          </div>
        </div>
      )}

      {actionMessage && (
        <div
          style={{
            background: "#fef3c7",
            color: "#92400e",
            borderRadius: 8,
            padding: "12px 16px",
            fontSize: 14,
            marginBottom: 24,
          }}
        >
          {actionMessage}
        </div>
      )}

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: 16 }}>
        {plans.map((plan) => {
          const isCurrent = subscription?.plan.code === plan.code;
          return (
            <div
              key={plan.code}
              style={{
                background: "var(--bg-card)",
                border: isCurrent ? "2px solid var(--color-primary)" : "1px solid var(--border-subtle)",
                borderRadius: "var(--radius-card)",
                padding: 20,
              }}
            >
              <div style={{ fontWeight: 700, marginBottom: 4 }}>{plan.name}</div>
              <div style={{ fontSize: 22, fontWeight: 700, marginBottom: 8 }}>
                {formatPence(plan.price_monthly_pence)}
              </div>
              <div style={{ fontSize: 13, color: "var(--text-secondary)", marginBottom: 16 }}>
                Up to {plan.property_count_tier_max ?? "unlimited"} properties
              </div>
              <button
                onClick={() => onUpgrade(plan.code)}
                disabled={isCurrent || pendingPlan === plan.code}
                style={{
                  width: "100%",
                  padding: "9px 0",
                  borderRadius: 8,
                  border: isCurrent ? "1px solid var(--border-subtle)" : "none",
                  background: isCurrent ? "var(--bg-app)" : "var(--color-primary)",
                  color: isCurrent ? "var(--text-secondary)" : "#fff",
                  fontWeight: 600,
                  fontSize: 13,
                  cursor: isCurrent ? "default" : "pointer",
                }}
              >
                {isCurrent ? "Current plan" : pendingPlan === plan.code ? "Starting…" : "Upgrade"}
              </button>
            </div>
          );
        })}
      </div>
    </div>
  );
}
