const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(
  path: string,
  options: RequestInit & { organisationId?: string } = {},
): Promise<T> {
  const { organisationId, headers, ...rest } = options;
  const res = await fetch(`${API_URL}${path}`, {
    ...rest,
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...(organisationId ? { "X-Organisation-Id": organisationId } : {}),
      ...headers,
    },
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new ApiError(res.status, body.detail ?? "Request failed");
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export type Membership = {
  organisation_id: string;
  organisation_name: string;
  role_code: string;
};

export type Me = {
  id: string;
  name: string;
  email: string;
  memberships: Membership[];
};

export type NavSection = {
  key: string;
  label: string;
  icon: string;
  href: string;
};

export type WorkspaceLayout = {
  nav_sections: NavSection[];
  home_kpis: string[];
  terminology: Record<string, string>;
  compliance_domains: string[];
};

export type Plan = {
  code: string;
  name: string;
  price_monthly_pence: number | null;
  price_annual_pence: number | null;
  property_count_tier_min: number;
  property_count_tier_max: number | null;
  entitlements: Record<string, boolean | number | null>;
};

export type Subscription = {
  id: string;
  status: "TRIALING" | "ACTIVE" | "PAST_DUE" | "CANCELLED";
  current_period_end: string | null;
  plan: Plan;
  entitlements: Record<string, boolean | number | null>;
};

export const api = {
  signup: (payload: {
    name: string;
    email: string;
    password: string;
    organisation_name: string;
    organisation_type: string;
    goals: string[];
  }) =>
    request<{ organisation_id: string; organisation_slug: string; user_id: string }>(
      "/api/v1/auth/signup",
      { method: "POST", body: JSON.stringify(payload) },
    ),
  login: (payload: { email: string; password: string }) =>
    request<{ user_id: string }>("/api/v1/auth/login", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  logout: () => request<{ ok: boolean }>("/api/v1/auth/logout", { method: "POST" }),
  me: () => request<Me>("/api/v1/auth/me"),
  workspaceLayout: (organisationId: string) =>
    request<WorkspaceLayout>("/api/v1/workspaces/layout", { organisationId }),
  listPlans: () => request<Plan[]>("/api/v1/subscriptions/plans"),
  subscription: (organisationId: string) =>
    request<Subscription>("/api/v1/subscriptions", { organisationId }),
  startCheckout: (organisationId: string, planCode: string) =>
    request<{ checkout_url: string }>(
      `/api/v1/subscriptions/checkout?plan_code=${encodeURIComponent(planCode)}`,
      { method: "POST", organisationId },
    ),
  startBillingPortal: (organisationId: string) =>
    request<{ portal_url: string }>("/api/v1/subscriptions/portal", {
      method: "POST",
      organisationId,
    }),
};

export const ORGANISATION_TYPES = [
  { value: "HOUSING_ASSOCIATION", label: "Housing Association" },
  { value: "LOCAL_AUTHORITY", label: "Local Authority" },
  { value: "MANAGING_AGENT", label: "Managing Agent" },
  { value: "PRIVATE_LANDLORD", label: "Private Landlord" },
  { value: "COMMERCIAL_LANDLORD", label: "Commercial Landlord" },
  { value: "BUILD_TO_RENT", label: "Build-to-Rent Operator" },
  { value: "PROPERTY_MANAGEMENT_CO", label: "Property Management Company" },
  { value: "SUPPORTED_HOUSING", label: "Supported Housing Provider" },
  { value: "PROPERTY_INVESTOR", label: "Property Investor" },
  { value: "OTHER", label: "Other" },
] as const;
