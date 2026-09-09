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
  const isFormData = rest.body instanceof FormData;
  const res = await fetch(`${API_URL}${path}`, {
    ...rest,
    credentials: "include",
    headers: {
      // Omit Content-Type for FormData bodies — fetch must set its own
      // multipart boundary, which a fixed header here would clobber.
      ...(isFormData ? {} : { "Content-Type": "application/json" }),
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

export type FieldSpec = {
  key: string;
  label: string;
  required: boolean;
  aliases: string[];
};

export type UploadResponse = {
  dataset_id: string;
  import_job_id: string;
  row_count: number;
  proposed_mapping: Record<string, string | null>;
  field_dictionary: FieldSpec[];
  suggested_mapping_from_template: boolean;
};

export type Dataset = {
  id: string;
  name: string;
  dataset_type: string;
  status: string;
  row_count: number;
  uploaded_at: string;
  source_file_document_id: string | null;
};

export type DatasetDetail = Dataset & {
  latest_job_status: string | null;
  row_status_counts: Record<string, number>;
};

export type ImportResult = {
  rows_processed: number;
  entities_created: number;
  importer_registered: boolean;
};

export type DocumentOut = {
  id: string;
  document_reference: string;
  title: string;
  document_type: string;
  revision: string;
  status: "ACTIVE" | "SUPERSEDED" | "ARCHIVED";
  uploaded_by: string;
  uploaded_at: string;
  effective_date: string | null;
  superseded_by_document_id: string | null;
  related_entity_type: string | null;
  related_entity_id: string | null;
  content_type: string;
  size_bytes: number;
  checksum: string;
};

export type DocumentDetail = DocumentOut & { versions: DocumentOut[] };

export type PropertyOut = {
  id: string;
  property_reference: string;
  address: string;
  postcode: string | null;
  uprn: string | null;
  property_type: string | null;
  status: string;
  development_id: string | null;
  building_id: string | null;
  floor_id: string | null;
  source_type: string;
  source_dataset_id: string | null;
  original_reference: string | null;
  created_at: string;
};

export type SpaceOut = {
  id: string;
  property_id: string | null;
  building_id: string | null;
  name: string;
  space_type: string | null;
  source_type: string;
  created_at: string;
};

export type DevelopmentOut = {
  id: string;
  development_reference: string;
  name: string;
  description: string | null;
  address: string | null;
  postcode: string | null;
  status: string;
  planning_reference: string | null;
  building_control_reference: string | null;
  bsr_reference: string | null;
  source_type: string;
  created_at: string;
};

export type BuildingOut = {
  id: string;
  building_reference: string;
  development_id: string | null;
  name: string;
  building_type: string | null;
  address: string | null;
  storeys: number | null;
  status: string;
  building_control_reference: string | null;
  bsr_reference: string | null;
  source_type: string;
  created_at: string;
};

export type FloorOut = {
  id: string;
  building_id: string;
  name: string;
  level_index: number | null;
  created_at: string;
};

export type FloorSummary = {
  id: string;
  name: string;
  level_index: number | null;
  property_count: number;
};

export type BuildingHierarchy = {
  id: string;
  building_reference: string;
  name: string;
  status: string;
  floors: FloorSummary[];
  unfloored_property_count: number;
};

export type DevelopmentHierarchy = {
  id: string;
  development_reference: string;
  name: string;
  status: string;
  buildings: BuildingHierarchy[];
  unbuilt_property_count: number;
};

export type DataHealthCheck = {
  check_code: string;
  applicable_count: number;
  failing_count: number;
  pass_ratio: number;
};

export type DataHealthFinding = {
  check_code: string;
  severity: "LOW" | "MEDIUM" | "HIGH";
  affected_entity_type: string;
  affected_entity_id: string;
  message: string;
};

export type DataHealth = {
  score_pct: number;
  checks: DataHealthCheck[];
  findings: DataHealthFinding[];
};

export type ReferencePattern = {
  entity_type: string;
  pattern: string;
  next_sequence: number;
};

export type ComponentType = {
  id: string;
  code: string;
  name: string;
  parent_type_id: string | null;
  organisation_id: string | null;
};

export type ComponentOut = {
  id: string;
  component_reference: string;
  component_type_id: string;
  component_type_name: string;
  component_subtype: string | null;
  manufacturer: string | null;
  model: string | null;
  serial_number: string | null;
  installer: string | null;
  installation_date: string | null;
  commissioning_date: string | null;
  warranty_start: string | null;
  warranty_expiry: string | null;
  expected_life_years: number | null;
  indicative_replacement_date: string | null;
  status: "ACTIVE" | "REPLACED" | "DISPOSED";
  development_id: string | null;
  building_id: string | null;
  property_id: string | null;
  space_id: string | null;
  parent_component_id: string | null;
  source_type: string;
  source_dataset_id: string | null;
  original_reference: string | null;
  created_at: string;
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
  fieldDictionaries: () => request<Record<string, FieldSpec[]>>("/api/v1/datasets/field-dictionaries"),
  listDatasets: (organisationId: string) =>
    request<Dataset[]>("/api/v1/datasets", { organisationId }),
  getDataset: (organisationId: string, datasetId: string) =>
    request<DatasetDetail>(`/api/v1/datasets/${datasetId}`, { organisationId }),
  uploadDataset: (organisationId: string, datasetType: string, name: string, file: File) => {
    const form = new FormData();
    form.append("dataset_type", datasetType);
    form.append("name", name);
    form.append("file", file);
    return request<UploadResponse>("/api/v1/uploads", { method: "POST", organisationId, body: form });
  },
  applyMapping: (organisationId: string, datasetId: string, columnMapping: Record<string, string | null>) =>
    request<DatasetDetail>(`/api/v1/datasets/${datasetId}/mapping`, {
      method: "POST",
      organisationId,
      body: JSON.stringify({ column_mapping: columnMapping }),
    }),
  triggerImport: (organisationId: string, datasetId: string) =>
    request<ImportResult>(`/api/v1/datasets/${datasetId}/import`, { method: "POST", organisationId }),
  listDocuments: (organisationId: string) =>
    request<DocumentOut[]>("/api/v1/documents", { organisationId }),
  getDocument: (organisationId: string, documentId: string) =>
    request<DocumentDetail>(`/api/v1/documents/${documentId}`, { organisationId }),
  uploadDocument: (organisationId: string, title: string, documentType: string, file: File) => {
    const form = new FormData();
    form.append("title", title);
    form.append("document_type", documentType);
    form.append("file", file);
    return request<DocumentOut>("/api/v1/documents", { method: "POST", organisationId, body: form });
  },
  uploadDocumentVersion: (organisationId: string, documentId: string, revision: string, file: File) => {
    const form = new FormData();
    form.append("revision", revision);
    form.append("file", file);
    return request<DocumentOut>(`/api/v1/documents/${documentId}/versions`, {
      method: "POST",
      organisationId,
      body: form,
    });
  },
  // A plain <a href> can't carry the X-Organisation-Id header the API
  // requires, so downloads go through fetch (with credentials + header)
  // and hand the caller a Blob to save via an object URL instead.
  downloadDocument: async (organisationId: string, documentId: string): Promise<Blob> => {
    const res = await fetch(`${API_URL}/api/v1/documents/${documentId}/download`, {
      credentials: "include",
      headers: { "X-Organisation-Id": organisationId },
    });
    if (!res.ok) throw new ApiError(res.status, "Download failed");
    return res.blob();
  },
  listProperties: (
    organisationId: string,
    filters?: { development_id?: string; building_id?: string },
  ) => {
    const params = new URLSearchParams();
    if (filters?.development_id) params.set("development_id", filters.development_id);
    if (filters?.building_id) params.set("building_id", filters.building_id);
    const qs = params.toString();
    return request<PropertyOut[]>(`/api/v1/properties${qs ? `?${qs}` : ""}`, { organisationId });
  },
  getProperty: (organisationId: string, propertyId: string) =>
    request<PropertyOut>(`/api/v1/properties/${propertyId}`, { organisationId }),
  createProperty: (
    organisationId: string,
    payload: {
      address: string;
      postcode?: string;
      uprn?: string;
      property_type?: string;
      development_id?: string;
      building_id?: string;
      floor_id?: string;
    },
  ) =>
    request<PropertyOut>("/api/v1/properties", {
      method: "POST",
      organisationId,
      body: JSON.stringify(payload),
    }),
  listSpaces: (organisationId: string, propertyId: string) =>
    request<SpaceOut[]>(`/api/v1/properties/${propertyId}/spaces`, { organisationId }),
  createSpace: (organisationId: string, propertyId: string, payload: { name: string; space_type?: string }) =>
    request<SpaceOut>(`/api/v1/properties/${propertyId}/spaces`, {
      method: "POST",
      organisationId,
      body: JSON.stringify(payload),
    }),
  dataHealth: (organisationId: string) =>
    request<DataHealth>("/api/v1/data-health", { organisationId }),
  listDevelopments: (organisationId: string) =>
    request<DevelopmentOut[]>("/api/v1/developments", { organisationId }),
  getDevelopment: (organisationId: string, developmentId: string) =>
    request<DevelopmentOut>(`/api/v1/developments/${developmentId}`, { organisationId }),
  getDevelopmentHierarchy: (organisationId: string, developmentId: string) =>
    request<DevelopmentHierarchy>(`/api/v1/developments/${developmentId}/hierarchy`, { organisationId }),
  createDevelopment: (
    organisationId: string,
    payload: { name: string; address?: string; planning_reference?: string },
  ) =>
    request<DevelopmentOut>("/api/v1/developments", {
      method: "POST",
      organisationId,
      body: JSON.stringify(payload),
    }),
  listBuildings: (organisationId: string, developmentId?: string) =>
    request<BuildingOut[]>(
      `/api/v1/buildings${developmentId ? `?development_id=${developmentId}` : ""}`,
      { organisationId },
    ),
  getBuilding: (organisationId: string, buildingId: string) =>
    request<BuildingOut>(`/api/v1/buildings/${buildingId}`, { organisationId }),
  createBuilding: (
    organisationId: string,
    payload: { name: string; development_id?: string; building_type?: string; storeys?: number },
  ) =>
    request<BuildingOut>("/api/v1/buildings", {
      method: "POST",
      organisationId,
      body: JSON.stringify(payload),
    }),
  listFloors: (organisationId: string, buildingId: string) =>
    request<FloorOut[]>(`/api/v1/floors?building_id=${buildingId}`, { organisationId }),
  createFloor: (organisationId: string, payload: { building_id: string; name: string; level_index?: number }) =>
    request<FloorOut>("/api/v1/floors", {
      method: "POST",
      organisationId,
      body: JSON.stringify(payload),
    }),
  listReferencePatterns: (organisationId: string) =>
    request<ReferencePattern[]>("/api/v1/reference-patterns", { organisationId }),
  updateReferencePattern: (organisationId: string, entityType: string, pattern: string) =>
    request<ReferencePattern>(`/api/v1/reference-patterns/${entityType}`, {
      method: "PATCH",
      organisationId,
      body: JSON.stringify({ pattern }),
    }),
  listComponentTypes: (organisationId: string) =>
    request<ComponentType[]>("/api/v1/component-types", { organisationId }),
  createComponent: (
    organisationId: string,
    payload: {
      component_type_id: string;
      manufacturer?: string;
      model?: string;
      serial_number?: string;
      installation_date?: string;
      expected_life_years?: number;
      property_id?: string;
      building_id?: string;
      parent_component_id?: string;
    },
  ) =>
    request<ComponentOut>("/api/v1/components", {
      method: "POST",
      organisationId,
      body: JSON.stringify(payload),
    }),
  listComponents: (
    organisationId: string,
    filters?: { property_id?: string; building_id?: string; parent_component_id?: string },
  ) => {
    const params = new URLSearchParams();
    if (filters?.property_id) params.set("property_id", filters.property_id);
    if (filters?.building_id) params.set("building_id", filters.building_id);
    if (filters?.parent_component_id) params.set("parent_component_id", filters.parent_component_id);
    const qs = params.toString();
    return request<ComponentOut[]>(`/api/v1/components${qs ? `?${qs}` : ""}`, { organisationId });
  },
  getComponent: (organisationId: string, componentId: string) =>
    request<ComponentOut>(`/api/v1/components/${componentId}`, { organisationId }),
  listComponentChildren: (organisationId: string, componentId: string) =>
    request<ComponentOut[]>(`/api/v1/components/${componentId}/children`, { organisationId }),
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
