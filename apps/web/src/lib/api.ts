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
  mfa_enabled: boolean;
  mfa_backup_codes_remaining: number;
  memberships: Membership[];
};

export type LoginResult =
  | { mfa_required: false; user_id: string }
  | { mfa_required: true; mfa_token: string };

export type MfaEnrollment = {
  secret: string;
  otpauth_url: string;
};

export type MfaVerifyResult = {
  mfa_enabled: boolean;
  backup_codes: string[];
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

export type HandoverCheck = {
  check_code: string;
  label: string;
  weight: number;
  applicable_count: number;
  failing_count: number;
  pass_ratio: number;
  missing_items: string[];
};

export type HandoverReadiness = {
  development_id: string;
  score_pct: number;
  threshold_pct: number;
  ready: boolean;
  checks: HandoverCheck[];
  missing: string[];
};

export type HandoverRecordOut = {
  id: string;
  property_id: string;
  development_id: string;
  readiness_score_pct: number;
  readiness_snapshot: Record<string, unknown>[];
  override_reason: string | null;
  created_by: string | null;
  created_at: string;
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

export type SpecificationOut = {
  id: string;
  lineage_id: string;
  specification_reference: string;
  related_entity_type: string;
  related_entity_id: string;
  title: string;
  description: string | null;
  revision: string;
  status: "ACTIVE" | "SUPERSEDED";
  effective_date: string | null;
  superseded_date: string | null;
  related_component_type: string | null;
  source_document_id: string | null;
  approved_by: string | null;
  approved_at: string | null;
  source_type: string;
  created_by: string | null;
  created_at: string;
};

export type SpecificationDetail = SpecificationOut & { versions: SpecificationOut[] };

export type GoldenThreadResponsibleParty = {
  created_by_name: string | null;
  created_by_email: string | null;
  source_type: string;
  source_system: string | null;
  contractor_reference: string | null;
};

export type ChangeControlOut = {
  id: string;
  change_reference: string;
  specification_id: string;
  related_entity_type: string;
  related_entity_id: string;
  previous_value: Record<string, unknown>;
  proposed_value: Record<string, unknown>;
  reason: string;
  impact_description: string | null;
  status: "PROPOSED" | "UNDER_REVIEW" | "APPROVED" | "REJECTED" | "IMPLEMENTED" | "CANCELLED";
  approved_by: string | null;
  approved_date: string | null;
  implemented_specification_id: string | null;
  external_approval_reference: string | null;
  source_type: string;
  created_by: string | null;
  created_at: string;
};

export type GoldenThreadComponent = {
  id: string;
  component_reference: string;
  component_type_name: string;
  status: string;
  specifications: SpecificationOut[];
  responsible_party: GoldenThreadResponsibleParty;
  evidence: DocumentOut[];
  changes: ChangeControlOut[];
  external_references: Record<string, string>;
  inspections: InspectionOut[];
};

export type GoldenThread = {
  building_id: string;
  building_reference: string;
  building_name: string;
  specifications: SpecificationOut[];
  evidence: DocumentOut[];
  changes: ChangeControlOut[];
  external_references: Record<string, string>;
  inspections: InspectionOut[];
  components: GoldenThreadComponent[];
  not_yet_available: string[];
};

export type DefectOut = {
  id: string;
  defect_reference: string;
  development_id: string | null;
  building_id: string | null;
  property_id: string | null;
  component_id: string | null;
  category: string;
  description: string;
  severity: "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";
  reported_date: string;
  contractor: string | null;
  responsible_party: string | null;
  target_date: string | null;
  completion_date: string | null;
  status: "OPEN" | "ASSIGNED" | "IN_PROGRESS" | "READY_FOR_INSPECTION" | "COMPLETED" | "REJECTED" | "CLOSED";
  estimated_cost_pence: number | null;
  actual_cost_pence: number | null;
  warranty_related: boolean;
  source_type: string;
  created_by: string | null;
  created_at: string;
};

export type DefectsByKey = { key: string; count: number };

export type DefectsIntelligence = {
  total_count: number;
  open_count: number;
  overdue_count: number;
  warranty_related_count: number;
  by_contractor: DefectsByKey[];
  by_category: DefectsByKey[];
  by_component_type: DefectsByKey[];
  repeat_categories: DefectsByKey[];
  total_estimated_cost_pence: number;
  total_actual_cost_pence: number;
  average_resolution_days: number | null;
};

export type WarrantyOut = {
  id: string;
  warranty_reference: string;
  provider: string;
  development_id: string | null;
  building_id: string | null;
  property_id: string | null;
  component_id: string | null;
  warranty_type: string;
  start_date: string;
  expiry_date: string;
  terms_reference: string | null;
  document_id: string | null;
  status: "ACTIVE" | "VOID";
  is_expired: boolean;
  days_until_expiry: number;
  source_type: string;
  created_by: string | null;
  created_at: string;
};

export type TimelineEvent = {
  action_code: string;
  entity_type: string;
  entity_id: string | null;
  actor_name: string | null;
  before: Record<string, unknown> | null;
  after: Record<string, unknown> | null;
  created_at: string;
};

export type Property360 = {
  property: PropertyOut;
  development: DevelopmentOut | null;
  building: BuildingOut | null;
  floor: FloorOut | null;
  specifications: SpecificationOut[];
  evidence: DocumentOut[];
  changes: ChangeControlOut[];
  components: GoldenThreadComponent[];
  warranties: WarrantyOut[];
  defects: DefectOut[];
  repairs: RepairOut[];
  leases: LeaseOut[];
  handover_record: HandoverRecordOut | null;
  data_health_findings: DataHealthFinding[];
  timeline: TimelineEvent[];
  not_yet_available: string[];
};

export type PortfolioStatusCount = { key: string; count: number };

export type DevelopmentReadinessSummary = {
  development_id: string;
  development_reference: string;
  name: string;
  score_pct: number;
};

export type PortfolioSummary = {
  total_properties: number;
  total_developments: number;
  total_buildings: number;
  total_components: number;
  properties_by_status: PortfolioStatusCount[];
  data_health_score_pct: number;
  open_defects_count: number;
  overdue_defects_count: number;
  warranties_expiring_within_90_days_count: number;
  development_readiness: DevelopmentReadinessSummary[];
};

export type RepairOut = {
  id: string;
  repair_reference: string;
  property_id: string;
  component_id: string | null;
  category: string;
  description: string;
  priority: "EMERGENCY" | "URGENT" | "ROUTINE" | "PLANNED";
  is_emergency: boolean;
  reported_date: string;
  contractor: string | null;
  completed_date: string | null;
  cost_pence: number | null;
  status: "REPORTED" | "SCHEDULED" | "IN_PROGRESS" | "COMPLETED" | "CANCELLED";
  source_type: string;
  created_by: string | null;
  created_at: string;
};

export type RepeatRepairSignal = {
  property_id: string;
  repair_count: number;
  window_months: number;
  threshold: number;
  repair_ids: string[];
};

export type RepeatFailureSignal = {
  component_id: string;
  repair_count: number;
  window_months: number;
  threshold: number;
  repair_ids: string[];
};

export type ModelTrendSignal = {
  component_type_id: string;
  manufacturer: string;
  model: string;
  installed_count: number;
  failed_count: number;
  failure_ratio: number;
  threshold_ratio: number;
  component_ids: string[];
};

export type RepairsByKey = { key: string; count: number };

export type RepairsIntelligence = {
  total_count: number;
  open_count: number;
  completed_count: number;
  emergency_count: number;
  by_category: RepairsByKey[];
  by_contractor: RepairsByKey[];
  total_cost_pence: number;
  average_completion_days: number | null;
  repeat_repair_properties: RepeatRepairSignal[];
  repeat_failure_components: RepeatFailureSignal[];
};

export type RepairRuleConfig = {
  rule_code: string;
  window_months: number | null;
  threshold: number | null;
  threshold_ratio: number | null;
  min_installed_base: number | null;
};

export type ComplianceFrameworkOut = {
  id: string;
  organisation_id: string | null;
  name: string;
  version: number;
};

export type ComplianceDomainOut = {
  id: string;
  organisation_id: string | null;
  framework_id: string;
  code: string;
  name: string;
  description: string | null;
};

export type ComplianceRequirementOut = {
  id: string;
  organisation_id: string | null;
  domain_id: string;
  code: string;
  title: string;
  description: string | null;
  cadence: string | null;
  version: number;
  effective_date: string;
  superseded_date: string | null;
  hard_deadline: boolean;
};

export type ComplianceRequirementDetail = ComplianceRequirementOut & { versions: ComplianceRequirementOut[] };

export type RequirementApplicabilityOut = {
  id: string;
  requirement_id: string;
  entity_type: string;
  entity_id: string;
  applicable_from: string;
  applicable_to: string | null;
  basis: string | null;
};

export type InspectionOut = {
  id: string;
  requirement_id: string;
  entity_type: string;
  entity_id: string;
  inspector: string;
  inspection_date: string;
  result: string;
  next_due_date: string | null;
  evidence_document_id: string | null;
};

export type ComplianceActionOut = {
  id: string;
  inspection_id: string | null;
  requirement_id: string;
  entity_type: string;
  entity_id: string;
  description: string;
  deadline: string;
  status: string;
  completed_date: string | null;
  evidence_document_id: string | null;
};

export type HazardOut = {
  id: string;
  property_id: string;
  hazard_type: string;
  reported_date: string;
  severity: string;
  investigation_status: string;
  findings: string | null;
  deadline: string | null;
  status: string;
};

export type HazardActionOut = {
  id: string;
  hazard_id: string;
  description: string;
  deadline: string;
  status: string;
  completed_date: string | null;
  evidence_document_id: string | null;
};

export type RepeatHazardSignal = {
  property_id: string;
  hazard_type: string;
  hazard_count: number;
  window_months: number;
  threshold: number;
  hazard_ids: string[];
};

export type StockConditionSurveyOut = {
  id: string;
  property_id: string;
  survey_date: string;
  surveyor: string;
  condition_ratings: Record<string, string>;
  next_survey_due: string | null;
  document_id: string | null;
};

export type PlannedInvestmentFactorOut = {
  factor_code: string;
  label: string;
  weight: number;
  applicable: boolean;
  value: number | null;
  detail: string;
};

export type PlannedInvestmentScoreOut = {
  component_id: string;
  component_reference: string;
  component_type_name: string;
  priority_score: number;
  factors: PlannedInvestmentFactorOut[];
};

export type PlannedInvestmentWeightOut = {
  factor_code: string;
  label: string;
  weight: number;
};

export type PlannedInvestmentConfig = {
  repair_frequency_window_months: number;
  repair_frequency_threshold: number;
};

export type ComplianceStatusOut = {
  status: string;
  requirement_id: string;
  domain_id: string;
  entity_type: string;
  entity_id: string;
  latest_inspection: InspectionOut | null;
  open_action: ComplianceActionOut | null;
  days_to_due: number | null;
};

export type TenantOut = {
  id: string;
  name: string;
  contact_details: Record<string, string>;
};

export type LeaseOut = {
  id: string;
  property_id: string;
  tenant_id: string;
  lease_reference: string;
  lease_start: string;
  lease_expiry: string;
  break_date: string | null;
  rent_review_date: string | null;
  contractual_rent_pence: number;
  rent_frequency: string;
  service_charge_amount_pence: number | null;
  occupancy_status: string;
  lease_status: string;
};

export type ComplianceStatusConfig = {
  due_soon_days: number;
  never_assessed_grace_days: number;
};

export type RentObligationOut = {
  id: string;
  lease_id: string;
  obligation_type: string;
  due_date: string;
  period_start: string;
  period_end: string;
  amount_due_pence: number;
  currency: string;
  invoice_reference: string | null;
  status: string;
  outstanding_pence: number;
};

export type PaymentTransactionOut = {
  id: string;
  lease_id: string | null;
  amount_pence: number;
  currency: string;
  received_date: string;
  payer_reference: string | null;
  method: string | null;
};

export type PaymentAllocationOut = {
  id: string;
  payment_transaction_id: string;
  rent_obligation_id: string | null;
  amount_allocated_pence: number;
  allocation_status: string;
  source_type: string;
};

export type CreatePaymentResult = {
  payment: PaymentTransactionOut;
  allocation: PaymentAllocationOut;
};

export type PaymentReconciliationConfig = {
  due_date_window_days: number;
};

export type ArrearsSnapshot = {
  lease_id: string;
  as_of: string;
  total_due_pence: number;
  outstanding_pence: number;
  ageing_pence: Record<string, number>;
  credits_pence: number;
  unallocated_pence: number;
};

export type CollectionRate = {
  period_start: string;
  period_end: string;
  due_pence: number;
  collected_pence: number;
  collection_rate: number;
};

export type AttentionRuleOut = {
  id: string;
  code: string;
  name: string;
  domain_scope: string;
  rule_definition: Record<string, unknown>;
  severity_default: string;
  is_active: boolean;
};

export type AttentionSignalExplanation = {
  what: string;
  why: string;
  supporting_record_ids: string[];
  recommended_investigation: string;
};

export type AttentionSignalOut = {
  id: string;
  rule_id: string;
  rule_code: string;
  entity_type: string;
  entity_id: string;
  severity: string;
  detected_at: string;
  explanation: AttentionSignalExplanation;
  status: string;
};

export type AttentionScanResult = {
  rules_evaluated: number;
  signals_created: number;
  signals_refreshed: number;
};

export type ToolResultOut = {
  tool_name: string;
  dataset: string;
  fields: string[];
  filters: Record<string, string>;
  time_period: { start: string | null; end: string | null } | null;
  records: Record<string, unknown>[];
  calculation: string | null;
};

export type AskResponse = {
  answer_text: string;
  tool_results: ToolResultOut[];
  grounded: boolean;
  suggested_follow_ups: string[];
};

export type BoardAssuranceDomainSummary = {
  domain_id: string;
  domain_code: string;
  domain_name: string;
  status_counts: Record<string, number>;
  open_actions: number;
  overdue_actions: number;
};

export type BoardAssuranceReport = {
  domains: BoardAssuranceDomainSummary[];
  total_open_actions: number;
  total_overdue_actions: number;
  hazard_status_counts: Record<string, number>;
  open_hazard_severity_counts: Record<string, number>;
};

export const REPORT_TYPES = [
  { value: "DEVELOPMENT_SUMMARY", label: "Development Summary" },
  { value: "HANDOVER_READINESS", label: "Handover Readiness" },
  { value: "COMPLIANCE_EXECUTIVE_SUMMARY", label: "Compliance Executive Summary" },
  { value: "BOARD_ASSURANCE", label: "Board Assurance" },
  { value: "COMMERCIAL_PORTFOLIO", label: "Commercial Portfolio" },
] as const;

export const REPORT_FORMATS = ["PDF", "XLSX", "CSV"] as const;

export type ReportType = (typeof REPORT_TYPES)[number]["value"];
export type ReportFormatValue = (typeof REPORT_FORMATS)[number];

export type ReportJobOut = {
  id: string;
  report_type: ReportType;
  format: ReportFormatValue;
  filters: Record<string, string>;
  status: "PENDING" | "RUNNING" | "READY" | "FAILED";
  requested_by: string;
  requested_at: string;
  completed_at: string | null;
  error_message: string | null;
  file_size_bytes: number | null;
};

export type Member = {
  user_id: string;
  name: string;
  email: string;
  role_code: string;
  status: string;
};

export type Invitation = {
  id: string;
  email: string;
  role_code: string;
  status: string;
  expires_at: string;
  invite_url: string;
};

export type PublicInvitation = {
  organisation_name: string;
  email: string;
  role_code: string;
  account_exists: boolean;
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
    request<LoginResult>("/api/v1/auth/login", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  mfaChallenge: (mfaToken: string, code: string) =>
    request<{ user_id: string }>("/api/v1/auth/mfa/challenge", {
      method: "POST",
      body: JSON.stringify({ mfa_token: mfaToken, code }),
    }),
  mfaEnroll: () => request<MfaEnrollment>("/api/v1/auth/mfa/enroll", { method: "POST" }),
  mfaVerify: (code: string) =>
    request<MfaVerifyResult>("/api/v1/auth/mfa/verify", {
      method: "POST",
      body: JSON.stringify({ code }),
    }),
  mfaRegenerateBackupCodes: (password: string) =>
    request<{ backup_codes: string[] }>("/api/v1/auth/mfa/backup-codes/regenerate", {
      method: "POST",
      body: JSON.stringify({ password }),
    }),
  mfaDisable: (password: string) =>
    request<{ mfa_enabled: boolean }>("/api/v1/auth/mfa/disable", {
      method: "POST",
      body: JSON.stringify({ password }),
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
  getHandoverReadiness: (organisationId: string, developmentId: string) =>
    request<HandoverReadiness>(`/api/v1/developments/${developmentId}/handover-readiness`, { organisationId }),
  authoriseHandover: (organisationId: string, developmentId: string, overrideReason?: string) =>
    request<HandoverRecordOut[]>(`/api/v1/developments/${developmentId}/handover/authorise`, {
      method: "POST",
      organisationId,
      body: JSON.stringify({ override_reason: overrideReason || undefined }),
    }),
  listHandoverRecords: (organisationId: string, developmentId: string) =>
    request<HandoverRecordOut[]>(`/api/v1/developments/${developmentId}/handover-records`, { organisationId }),
  updatePropertyStatus: (organisationId: string, propertyId: string, newStatus: string) =>
    request<PropertyOut>(`/api/v1/properties/${propertyId}/status`, {
      method: "POST",
      organisationId,
      body: JSON.stringify({ status: newStatus }),
    }),
  getProperty360: (organisationId: string, propertyId: string) =>
    request<Property360>(`/api/v1/properties/${propertyId}/360`, { organisationId }),
  portfolioSummary: (organisationId: string) =>
    request<PortfolioSummary>("/api/v1/portfolio/summary", { organisationId }),
  createRepair: (
    organisationId: string,
    payload: {
      property_id: string;
      component_id?: string;
      category: string;
      description: string;
      reported_date: string;
      priority?: string;
      contractor?: string;
      cost_pence?: number;
    },
  ) => request<RepairOut>("/api/v1/repairs", { method: "POST", organisationId, body: JSON.stringify(payload) }),
  updateRepairStatus: (
    organisationId: string,
    repairId: string,
    payload: { status: string; completed_date?: string; cost_pence?: number },
  ) =>
    request<RepairOut>(`/api/v1/repairs/${repairId}/status`, {
      method: "POST",
      organisationId,
      body: JSON.stringify(payload),
    }),
  listRepairs: (organisationId: string, filters?: { property_id?: string; component_id?: string }) => {
    const params = new URLSearchParams();
    if (filters?.property_id) params.set("property_id", filters.property_id);
    if (filters?.component_id) params.set("component_id", filters.component_id);
    const qs = params.toString();
    return request<RepairOut[]>(`/api/v1/repairs${qs ? `?${qs}` : ""}`, { organisationId });
  },
  repairsIntelligence: (organisationId: string) =>
    request<RepairsIntelligence>("/api/v1/repairs/intelligence", { organisationId }),
  propertyRepeatRepairs: (organisationId: string, propertyId: string) =>
    request<RepeatRepairSignal | null>(`/api/v1/properties/${propertyId}/repeat-repairs`, { organisationId }),
  componentRepeatFailures: (organisationId: string, componentId: string) =>
    request<RepeatFailureSignal | null>(`/api/v1/components/${componentId}/repeat-failures`, { organisationId }),
  repairModelTrend: (organisationId: string, componentTypeId: string, manufacturer: string, model: string) =>
    request<ModelTrendSignal | null>(
      `/api/v1/repairs/model-trend?${new URLSearchParams({ component_type_id: componentTypeId, manufacturer, model })}`,
      { organisationId },
    ),
  listRepairRuleConfigs: (organisationId: string) =>
    request<RepairRuleConfig[]>("/api/v1/repair-rule-configs", { organisationId }),
  updateRepairRuleConfig: (organisationId: string, ruleCode: string, updates: Partial<RepairRuleConfig>) =>
    request<RepairRuleConfig>(`/api/v1/repair-rule-configs/${ruleCode}`, {
      method: "PATCH",
      organisationId,
      body: JSON.stringify(updates),
    }),
  listComplianceFrameworks: (organisationId: string) =>
    request<ComplianceFrameworkOut[]>("/api/v1/compliance/frameworks", { organisationId }),
  listComplianceDomains: (organisationId: string) =>
    request<ComplianceDomainOut[]>("/api/v1/compliance/domains", { organisationId }),
  createComplianceDomain: (organisationId: string, payload: { code: string; name: string; description?: string }) =>
    request<ComplianceDomainOut>("/api/v1/compliance/domains", {
      method: "POST",
      organisationId,
      body: JSON.stringify(payload),
    }),
  listComplianceRequirements: (
    organisationId: string,
    filters?: { domain_id?: string; current_only?: boolean },
  ) => {
    const params = new URLSearchParams();
    if (filters?.domain_id) params.set("domain_id", filters.domain_id);
    if (filters?.current_only !== undefined) params.set("current_only", String(filters.current_only));
    const qs = params.toString();
    return request<ComplianceRequirementOut[]>(`/api/v1/compliance/requirements${qs ? `?${qs}` : ""}`, { organisationId });
  },
  getComplianceRequirement: (organisationId: string, requirementId: string) =>
    request<ComplianceRequirementDetail>(`/api/v1/compliance/requirements/${requirementId}`, { organisationId }),
  createComplianceRequirement: (
    organisationId: string,
    payload: {
      domain_id: string;
      code: string;
      title: string;
      description?: string;
      cadence?: string;
      effective_date: string;
      hard_deadline?: boolean;
    },
  ) =>
    request<ComplianceRequirementOut>("/api/v1/compliance/requirements", {
      method: "POST",
      organisationId,
      body: JSON.stringify(payload),
    }),
  reviseComplianceRequirement: (
    organisationId: string,
    requirementId: string,
    payload: { title?: string; description?: string; cadence?: string; effective_date: string },
  ) =>
    request<ComplianceRequirementOut>(`/api/v1/compliance/requirements/${requirementId}/versions`, {
      method: "POST",
      organisationId,
      body: JSON.stringify(payload),
    }),
  createApplicability: (
    organisationId: string,
    payload: { requirement_id: string; entity_type: string; entity_id: string; applicable_from: string; basis?: string },
  ) =>
    request<RequirementApplicabilityOut>("/api/v1/compliance/applicability", {
      method: "POST",
      organisationId,
      body: JSON.stringify(payload),
    }),
  listApplicability: (
    organisationId: string,
    filters?: { entity_type?: string; entity_id?: string; requirement_id?: string },
  ) => {
    const params = new URLSearchParams();
    if (filters?.entity_type) params.set("entity_type", filters.entity_type);
    if (filters?.entity_id) params.set("entity_id", filters.entity_id);
    if (filters?.requirement_id) params.set("requirement_id", filters.requirement_id);
    const qs = params.toString();
    return request<RequirementApplicabilityOut[]>(`/api/v1/compliance/applicability${qs ? `?${qs}` : ""}`, { organisationId });
  },
  listInspections: (
    organisationId: string,
    filters?: { entity_type?: string; entity_id?: string; requirement_id?: string },
  ) => {
    const params = new URLSearchParams();
    if (filters?.entity_type) params.set("entity_type", filters.entity_type);
    if (filters?.entity_id) params.set("entity_id", filters.entity_id);
    if (filters?.requirement_id) params.set("requirement_id", filters.requirement_id);
    const qs = params.toString();
    return request<InspectionOut[]>(`/api/v1/compliance/inspections${qs ? `?${qs}` : ""}`, { organisationId });
  },
  createInspection: (
    organisationId: string,
    payload: {
      requirement_id: string;
      entity_type: string;
      entity_id: string;
      inspector: string;
      inspection_date: string;
      result: string;
      next_due_date?: string;
    },
  ) =>
    request<InspectionOut>("/api/v1/compliance/inspections", {
      method: "POST",
      organisationId,
      body: JSON.stringify(payload),
    }),
  listComplianceActions: (
    organisationId: string,
    filters?: { entity_type?: string; entity_id?: string; requirement_id?: string; action_status?: string },
  ) => {
    const params = new URLSearchParams();
    if (filters?.entity_type) params.set("entity_type", filters.entity_type);
    if (filters?.entity_id) params.set("entity_id", filters.entity_id);
    if (filters?.requirement_id) params.set("requirement_id", filters.requirement_id);
    if (filters?.action_status) params.set("action_status", filters.action_status);
    const qs = params.toString();
    return request<ComplianceActionOut[]>(`/api/v1/compliance/actions${qs ? `?${qs}` : ""}`, { organisationId });
  },
  createComplianceAction: (
    organisationId: string,
    payload: {
      requirement_id: string;
      entity_type: string;
      entity_id: string;
      description: string;
      deadline: string;
      inspection_id?: string;
    },
  ) =>
    request<ComplianceActionOut>("/api/v1/compliance/actions", {
      method: "POST",
      organisationId,
      body: JSON.stringify(payload),
    }),
  updateComplianceActionStatus: (organisationId: string, actionId: string, payload: { status: string; completed_date?: string }) =>
    request<ComplianceActionOut>(`/api/v1/compliance/actions/${actionId}/status`, {
      method: "POST",
      organisationId,
      body: JSON.stringify(payload),
    }),
  listHazards: (organisationId: string, filters?: { property_id?: string }) => {
    const params = new URLSearchParams();
    if (filters?.property_id) params.set("property_id", filters.property_id);
    const qs = params.toString();
    return request<HazardOut[]>(`/api/v1/hazards${qs ? `?${qs}` : ""}`, { organisationId });
  },
  createHazard: (
    organisationId: string,
    payload: { property_id: string; hazard_type: string; reported_date: string; severity?: string },
  ) => request<HazardOut>("/api/v1/hazards", { method: "POST", organisationId, body: JSON.stringify(payload) }),
  updateHazardStatus: (
    organisationId: string,
    hazardId: string,
    payload: { status: string; investigation_status?: string; findings?: string; deadline?: string },
  ) =>
    request<HazardOut>(`/api/v1/hazards/${hazardId}/status`, {
      method: "POST",
      organisationId,
      body: JSON.stringify(payload),
    }),
  listHazardActions: (organisationId: string, hazardId: string) =>
    request<HazardActionOut[]>(`/api/v1/hazards/${hazardId}/actions`, { organisationId }),
  createHazardAction: (organisationId: string, hazardId: string, payload: { description: string; deadline: string }) =>
    request<HazardActionOut>(`/api/v1/hazards/${hazardId}/actions`, {
      method: "POST",
      organisationId,
      body: JSON.stringify(payload),
    }),
  updateHazardActionStatus: (
    organisationId: string,
    actionId: string,
    payload: { status: string; completed_date?: string },
  ) =>
    request<HazardActionOut>(`/api/v1/hazard-actions/${actionId}/status`, {
      method: "POST",
      organisationId,
      body: JSON.stringify(payload),
    }),
  repeatHazardsForProperty: (organisationId: string, propertyId: string, hazardType: string) =>
    request<RepeatHazardSignal | null>(
      `/api/v1/properties/${propertyId}/repeat-hazards?hazard_type=${encodeURIComponent(hazardType)}`,
      { organisationId },
    ),
  endApplicability: (organisationId: string, applicabilityId: string, applicableTo: string) =>
    request<RequirementApplicabilityOut>(`/api/v1/compliance/applicability/${applicabilityId}/end`, {
      method: "POST",
      organisationId,
      body: JSON.stringify({ applicable_to: applicableTo }),
    }),
  getComplianceStatus: (organisationId: string, entityType: string, entityId: string, requirementId: string) =>
    request<ComplianceStatusOut>(
      `/api/v1/compliance/status?entity_type=${encodeURIComponent(entityType)}&entity_id=${entityId}&requirement_id=${requirementId}`,
      { organisationId },
    ),
  listComplianceStatuses: (organisationId: string, entityType: string, entityId: string) =>
    request<ComplianceStatusOut[]>(
      `/api/v1/compliance/statuses?entity_type=${encodeURIComponent(entityType)}&entity_id=${entityId}`,
      { organisationId },
    ),
  getComplianceStatusConfig: (organisationId: string) =>
    request<ComplianceStatusConfig>("/api/v1/compliance/status-config", { organisationId }),
  updateComplianceStatusConfig: (
    organisationId: string,
    payload: { due_soon_days?: number; never_assessed_grace_days?: number },
  ) =>
    request<ComplianceStatusConfig>("/api/v1/compliance/status-config", {
      method: "PATCH",
      organisationId,
      body: JSON.stringify(payload),
    }),
  getAssuranceReport: (organisationId: string, filters?: { building_id?: string; property_id?: string }) => {
    const params = new URLSearchParams();
    if (filters?.building_id) params.set("building_id", filters.building_id);
    if (filters?.property_id) params.set("property_id", filters.property_id);
    const qs = params.toString();
    return request<BoardAssuranceReport>(`/api/v1/compliance/assurance-report${qs ? `?${qs}` : ""}`, { organisationId });
  },
  listStockConditionSurveys: (organisationId: string, filters?: { property_id?: string }) => {
    const params = new URLSearchParams();
    if (filters?.property_id) params.set("property_id", filters.property_id);
    const qs = params.toString();
    return request<StockConditionSurveyOut[]>(`/api/v1/stock-condition-surveys${qs ? `?${qs}` : ""}`, { organisationId });
  },
  createStockConditionSurvey: (
    organisationId: string,
    payload: {
      property_id: string;
      survey_date: string;
      surveyor: string;
      condition_ratings?: Record<string, string>;
      next_survey_due?: string;
    },
  ) =>
    request<StockConditionSurveyOut>("/api/v1/stock-condition-surveys", {
      method: "POST",
      organisationId,
      body: JSON.stringify(payload),
    }),
  getComponentPlannedInvestment: (organisationId: string, componentId: string) =>
    request<PlannedInvestmentScoreOut>(`/api/v1/components/${componentId}/planned-investment`, { organisationId }),
  listPlannedInvestment: (
    organisationId: string,
    filters?: { development_id?: string; building_id?: string; property_id?: string },
  ) => {
    const params = new URLSearchParams();
    if (filters?.development_id) params.set("development_id", filters.development_id);
    if (filters?.building_id) params.set("building_id", filters.building_id);
    if (filters?.property_id) params.set("property_id", filters.property_id);
    const qs = params.toString();
    return request<PlannedInvestmentScoreOut[]>(`/api/v1/planned-investment${qs ? `?${qs}` : ""}`, { organisationId });
  },
  listPlannedInvestmentWeights: (organisationId: string) =>
    request<PlannedInvestmentWeightOut[]>("/api/v1/planned-investment-weights", { organisationId }),
  updatePlannedInvestmentWeight: (organisationId: string, factorCode: string, weight: number) =>
    request<PlannedInvestmentWeightOut>(`/api/v1/planned-investment-weights/${factorCode}`, {
      method: "PATCH",
      organisationId,
      body: JSON.stringify({ weight }),
    }),
  getPlannedInvestmentConfig: (organisationId: string) =>
    request<PlannedInvestmentConfig>("/api/v1/planned-investment-config", { organisationId }),
  updatePlannedInvestmentConfig: (
    organisationId: string,
    payload: { repair_frequency_window_months?: number; repair_frequency_threshold?: number },
  ) =>
    request<PlannedInvestmentConfig>("/api/v1/planned-investment-config", {
      method: "PATCH",
      organisationId,
      body: JSON.stringify(payload),
    }),
  listTenants: (organisationId: string) => request<TenantOut[]>("/api/v1/tenants", { organisationId }),
  createTenant: (organisationId: string, payload: { name: string; contact_details?: Record<string, string> }) =>
    request<TenantOut>("/api/v1/tenants", { method: "POST", organisationId, body: JSON.stringify(payload) }),
  listLeases: (organisationId: string, filters?: { property_id?: string; tenant_id?: string; lease_status?: string }) => {
    const params = new URLSearchParams();
    if (filters?.property_id) params.set("property_id", filters.property_id);
    if (filters?.tenant_id) params.set("tenant_id", filters.tenant_id);
    if (filters?.lease_status) params.set("lease_status", filters.lease_status);
    const qs = params.toString();
    return request<LeaseOut[]>(`/api/v1/leases${qs ? `?${qs}` : ""}`, { organisationId });
  },
  createLease: (
    organisationId: string,
    payload: {
      property_id: string;
      tenant_id: string;
      lease_start: string;
      lease_expiry: string;
      break_date?: string;
      rent_review_date?: string;
      contractual_rent_pence: number;
      rent_frequency: string;
      service_charge_amount_pence?: number;
    },
  ) => request<LeaseOut>("/api/v1/leases", { method: "POST", organisationId, body: JSON.stringify(payload) }),
  updateLeaseStatus: (organisationId: string, leaseId: string, statusValue: string) =>
    request<LeaseOut>(`/api/v1/leases/${leaseId}/status`, {
      method: "POST",
      organisationId,
      body: JSON.stringify({ status: statusValue }),
    }),
  updateLeaseOccupancy: (organisationId: string, leaseId: string, occupancyStatus: string) =>
    request<LeaseOut>(`/api/v1/leases/${leaseId}/occupancy`, {
      method: "POST",
      organisationId,
      body: JSON.stringify({ occupancy_status: occupancyStatus }),
    }),
  listRentObligations: (organisationId: string, filters?: { lease_id?: string; obligation_status?: string }) => {
    const params = new URLSearchParams();
    if (filters?.lease_id) params.set("lease_id", filters.lease_id);
    if (filters?.obligation_status) params.set("obligation_status", filters.obligation_status);
    const qs = params.toString();
    return request<RentObligationOut[]>(`/api/v1/rent-obligations${qs ? `?${qs}` : ""}`, { organisationId });
  },
  createRentObligation: (
    organisationId: string,
    payload: {
      lease_id: string;
      obligation_type: string;
      due_date: string;
      period_start: string;
      period_end: string;
      amount_due_pence: number;
      currency?: string;
      invoice_reference?: string;
    },
  ) => request<RentObligationOut>("/api/v1/rent-obligations", { method: "POST", organisationId, body: JSON.stringify(payload) }),
  listPayments: (organisationId: string, filters?: { lease_id?: string }) => {
    const params = new URLSearchParams();
    if (filters?.lease_id) params.set("lease_id", filters.lease_id);
    const qs = params.toString();
    return request<PaymentTransactionOut[]>(`/api/v1/payments${qs ? `?${qs}` : ""}`, { organisationId });
  },
  createPayment: (
    organisationId: string,
    payload: { lease_id?: string; amount_pence: number; received_date: string; payer_reference?: string; method?: string },
  ) => request<CreatePaymentResult>("/api/v1/payments", { method: "POST", organisationId, body: JSON.stringify(payload) }),
  listPaymentAllocations: (organisationId: string, filters?: { allocation_status?: string; lease_id?: string }) => {
    const params = new URLSearchParams();
    if (filters?.allocation_status) params.set("allocation_status", filters.allocation_status);
    if (filters?.lease_id) params.set("lease_id", filters.lease_id);
    const qs = params.toString();
    return request<PaymentAllocationOut[]>(`/api/v1/payment-allocations${qs ? `?${qs}` : ""}`, { organisationId });
  },
  resolvePaymentAllocation: (organisationId: string, allocationId: string, payload: { rent_obligation_id: string; amount_allocated_pence: number }) =>
    request<PaymentAllocationOut>(`/api/v1/payment-allocations/${allocationId}/resolve`, {
      method: "POST",
      organisationId,
      body: JSON.stringify(payload),
    }),
  createManualAllocation: (organisationId: string, paymentId: string, payload: { rent_obligation_id: string; amount_allocated_pence: number }) =>
    request<PaymentAllocationOut>(`/api/v1/payments/${paymentId}/allocations`, {
      method: "POST",
      organisationId,
      body: JSON.stringify(payload),
    }),
  getPaymentReconciliationConfig: (organisationId: string) =>
    request<PaymentReconciliationConfig>("/api/v1/payment-reconciliation-config", { organisationId }),
  updatePaymentReconciliationConfig: (organisationId: string, dueDateWindowDays: number) =>
    request<PaymentReconciliationConfig>("/api/v1/payment-reconciliation-config", {
      method: "PATCH",
      organisationId,
      body: JSON.stringify({ due_date_window_days: dueDateWindowDays }),
    }),
  getLeaseArrears: (organisationId: string, leaseId: string, asOf?: string) =>
    request<ArrearsSnapshot>(`/api/v1/leases/${leaseId}/arrears${asOf ? `?as_of=${asOf}` : ""}`, { organisationId }),
  getCollectionRate: (organisationId: string, periodStart: string, periodEnd: string) =>
    request<CollectionRate>(`/api/v1/collection-rate?period_start=${periodStart}&period_end=${periodEnd}`, { organisationId }),
  listAttentionRules: (organisationId: string) =>
    request<AttentionRuleOut[]>("/api/v1/attention/rules", { organisationId }),
  updateAttentionRule: (organisationId: string, ruleId: string, payload: { is_active?: boolean; rule_definition?: Record<string, unknown> }) =>
    request<AttentionRuleOut>(`/api/v1/attention/rules/${ruleId}`, { method: "PATCH", organisationId, body: JSON.stringify(payload) }),
  listAttentionSignals: (organisationId: string, filters?: { signal_status?: string; entity_type?: string; severity?: string }) => {
    const params = new URLSearchParams();
    if (filters?.signal_status) params.set("signal_status", filters.signal_status);
    if (filters?.entity_type) params.set("entity_type", filters.entity_type);
    if (filters?.severity) params.set("severity", filters.severity);
    const qs = params.toString();
    return request<AttentionSignalOut[]>(`/api/v1/attention/signals${qs ? `?${qs}` : ""}`, { organisationId });
  },
  updateAttentionSignalStatus: (organisationId: string, signalId: string, statusValue: string) =>
    request<AttentionSignalOut>(`/api/v1/attention/signals/${signalId}/status`, {
      method: "POST",
      organisationId,
      body: JSON.stringify({ status: statusValue }),
    }),
  triggerAttentionScan: (organisationId: string) =>
    request<AttentionScanResult>("/api/v1/attention/scan", { method: "POST", organisationId }),
  askDataLume: (organisationId: string, payload: { question: string; entity_type: string; entity_id: string }) =>
    request<AskResponse>("/api/v1/ask", { method: "POST", organisationId, body: JSON.stringify(payload) }),
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
  createSpecification: (
    organisationId: string,
    payload: {
      related_entity_type: string;
      related_entity_id: string;
      title: string;
      description?: string;
      related_component_type?: string;
      effective_date?: string;
      source_document_id?: string;
    },
  ) =>
    request<SpecificationOut>("/api/v1/specifications", {
      method: "POST",
      organisationId,
      body: JSON.stringify(payload),
    }),
  reviseSpecification: (
    organisationId: string,
    specificationId: string,
    payload: {
      revision: string;
      title?: string;
      description?: string;
      related_component_type?: string;
      effective_date?: string;
      source_document_id?: string;
    },
  ) =>
    request<SpecificationOut>(`/api/v1/specifications/${specificationId}/versions`, {
      method: "POST",
      organisationId,
      body: JSON.stringify(payload),
    }),
  approveSpecification: (organisationId: string, specificationId: string) =>
    request<SpecificationOut>(`/api/v1/specifications/${specificationId}/approve`, {
      method: "POST",
      organisationId,
    }),
  listSpecifications: (
    organisationId: string,
    filters?: { related_entity_type?: string; related_entity_id?: string },
  ) => {
    const params = new URLSearchParams();
    if (filters?.related_entity_type) params.set("related_entity_type", filters.related_entity_type);
    if (filters?.related_entity_id) params.set("related_entity_id", filters.related_entity_id);
    const qs = params.toString();
    return request<SpecificationOut[]>(`/api/v1/specifications${qs ? `?${qs}` : ""}`, { organisationId });
  },
  getSpecification: (organisationId: string, specificationId: string) =>
    request<SpecificationDetail>(`/api/v1/specifications/${specificationId}`, { organisationId }),
  getGoldenThread: (organisationId: string, buildingId: string) =>
    request<GoldenThread>(`/api/v1/buildings/${buildingId}/golden-thread`, { organisationId }),
  submitChangeControl: (
    organisationId: string,
    payload: {
      specification_id: string;
      proposed_value: Record<string, unknown>;
      reason: string;
      impact_description?: string;
    },
  ) =>
    request<ChangeControlOut>("/api/v1/change-control", {
      method: "POST",
      organisationId,
      body: JSON.stringify(payload),
    }),
  listChangeControl: (
    organisationId: string,
    filters?: { specification_id?: string; related_entity_type?: string; related_entity_id?: string },
  ) => {
    const params = new URLSearchParams();
    if (filters?.specification_id) params.set("specification_id", filters.specification_id);
    if (filters?.related_entity_type) params.set("related_entity_type", filters.related_entity_type);
    if (filters?.related_entity_id) params.set("related_entity_id", filters.related_entity_id);
    const qs = params.toString();
    return request<ChangeControlOut[]>(`/api/v1/change-control${qs ? `?${qs}` : ""}`, { organisationId });
  },
  startChangeControlReview: (organisationId: string, changeControlId: string) =>
    request<ChangeControlOut>(`/api/v1/change-control/${changeControlId}/start-review`, {
      method: "POST",
      organisationId,
    }),
  approveChangeControl: (organisationId: string, changeControlId: string, externalApprovalReference?: string) =>
    request<ChangeControlOut>(`/api/v1/change-control/${changeControlId}/approve`, {
      method: "POST",
      organisationId,
      body: JSON.stringify({ external_approval_reference: externalApprovalReference || undefined }),
    }),
  rejectChangeControl: (organisationId: string, changeControlId: string) =>
    request<ChangeControlOut>(`/api/v1/change-control/${changeControlId}/reject`, {
      method: "POST",
      organisationId,
    }),
  cancelChangeControl: (organisationId: string, changeControlId: string) =>
    request<ChangeControlOut>(`/api/v1/change-control/${changeControlId}/cancel`, {
      method: "POST",
      organisationId,
    }),
  implementChangeControl: (organisationId: string, changeControlId: string) =>
    request<ChangeControlOut>(`/api/v1/change-control/${changeControlId}/implement`, {
      method: "POST",
      organisationId,
    }),
  createDefect: (
    organisationId: string,
    payload: {
      category: string;
      description: string;
      reported_date: string;
      severity?: string;
      contractor?: string;
      target_date?: string;
      estimated_cost_pence?: number;
      warranty_related?: boolean;
      development_id?: string;
      building_id?: string;
      property_id?: string;
      component_id?: string;
    },
  ) =>
    request<DefectOut>("/api/v1/defects", { method: "POST", organisationId, body: JSON.stringify(payload) }),
  updateDefectStatus: (
    organisationId: string,
    defectId: string,
    payload: { status: string; completion_date?: string; actual_cost_pence?: number },
  ) =>
    request<DefectOut>(`/api/v1/defects/${defectId}/status`, {
      method: "POST",
      organisationId,
      body: JSON.stringify(payload),
    }),
  listDefects: (
    organisationId: string,
    filters?: { building_id?: string; property_id?: string; component_id?: string },
  ) => {
    const params = new URLSearchParams();
    if (filters?.building_id) params.set("building_id", filters.building_id);
    if (filters?.property_id) params.set("property_id", filters.property_id);
    if (filters?.component_id) params.set("component_id", filters.component_id);
    const qs = params.toString();
    return request<DefectOut[]>(`/api/v1/defects${qs ? `?${qs}` : ""}`, { organisationId });
  },
  defectsIntelligence: (organisationId: string, filters?: { building_id?: string; development_id?: string }) => {
    const params = new URLSearchParams();
    if (filters?.building_id) params.set("building_id", filters.building_id);
    if (filters?.development_id) params.set("development_id", filters.development_id);
    const qs = params.toString();
    return request<DefectsIntelligence>(`/api/v1/defects/intelligence${qs ? `?${qs}` : ""}`, { organisationId });
  },
  createWarranty: (
    organisationId: string,
    payload: {
      provider: string;
      warranty_type: string;
      start_date: string;
      expiry_date: string;
      terms_reference?: string;
      document_id?: string;
      development_id?: string;
      building_id?: string;
      property_id?: string;
      component_id?: string;
    },
  ) =>
    request<WarrantyOut>("/api/v1/warranties", { method: "POST", organisationId, body: JSON.stringify(payload) }),
  voidWarranty: (organisationId: string, warrantyId: string) =>
    request<WarrantyOut>(`/api/v1/warranties/${warrantyId}/void`, { method: "POST", organisationId }),
  listWarranties: (
    organisationId: string,
    filters?: { building_id?: string; property_id?: string; component_id?: string; expiring_within_days?: number },
  ) => {
    const params = new URLSearchParams();
    if (filters?.building_id) params.set("building_id", filters.building_id);
    if (filters?.property_id) params.set("property_id", filters.property_id);
    if (filters?.component_id) params.set("component_id", filters.component_id);
    if (filters?.expiring_within_days !== undefined)
      params.set("expiring_within_days", String(filters.expiring_within_days));
    const qs = params.toString();
    return request<WarrantyOut[]>(`/api/v1/warranties${qs ? `?${qs}` : ""}`, { organisationId });
  },
  requestReport: (
    organisationId: string,
    payload: {
      report_type: ReportType;
      format: ReportFormatValue;
      building_id?: string;
      property_id?: string;
      period_start?: string;
      period_end?: string;
    },
  ) => request<ReportJobOut>("/api/v1/reports", { method: "POST", organisationId, body: JSON.stringify(payload) }),
  listReports: (organisationId: string) => request<ReportJobOut[]>("/api/v1/reports", { organisationId }),
  getReport: (organisationId: string, reportJobId: string) =>
    request<ReportJobOut>(`/api/v1/reports/${reportJobId}`, { organisationId }),
  // Same reasoning as downloadDocument — a plain <a href> can't carry
  // the X-Organisation-Id header, so this goes through fetch and hands
  // back a Blob to save via an object URL.
  downloadReport: async (organisationId: string, reportJobId: string): Promise<Blob> => {
    const res = await fetch(`${API_URL}/api/v1/reports/${reportJobId}/download`, {
      credentials: "include",
      headers: { "X-Organisation-Id": organisationId },
    });
    if (!res.ok) throw new ApiError(res.status, "Download failed");
    return res.blob();
  },
  listMembers: (organisationId: string) => request<Member[]>("/api/v1/organisations/members", { organisationId }),
  listInvitations: (organisationId: string) =>
    request<Invitation[]>("/api/v1/organisations/invitations", { organisationId }),
  inviteMember: (organisationId: string, email: string, roleCode: string) =>
    request<Invitation>("/api/v1/organisations/invitations", {
      method: "POST",
      organisationId,
      body: JSON.stringify({ email, role_code: roleCode }),
    }),
  revokeInvitation: (organisationId: string, invitationId: string) =>
    request<void>(`/api/v1/organisations/invitations/${invitationId}`, { method: "DELETE", organisationId }),
  getInvitation: (token: string) => request<PublicInvitation>(`/api/v1/invitations/${token}`),
  acceptInvitation: (token: string, payload: { name?: string; password?: string }) =>
    request<{ organisation_id: string; user_id: string }>(`/api/v1/invitations/${token}/accept`, {
      method: "POST",
      body: JSON.stringify(payload),
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

// Mirrors SYSTEM_ROLE_CODES in apps/api/app/auth/rbac.py — every role
// code the backend will accept for an invitation. Labels are just the
// code title-cased, matching how _get_or_create_role names a Role row
// the first time a code is used.
export const MEMBER_ROLES = [
  "OWNER",
  "ADMIN",
  "DATA_ANALYST",
  "MANAGER",
  "VIEWER",
  "DEVELOPMENT_MANAGER",
  "HANDOVER_MANAGER",
  "ASSET_MANAGER",
  "REPAIRS_MANAGER",
  "COMPLIANCE_MANAGER",
  "BUILDING_SAFETY_MANAGER",
  "PROPERTY_MANAGER",
  "COMMERCIAL_PROPERTY_MANAGER",
  "LEASE_MANAGER",
  "RENT_MANAGER",
  "FINANCE_VIEWER",
  "EXECUTIVE",
].map((code) => ({
  value: code,
  label: code
    .split("_")
    .map((w) => w[0] + w.slice(1).toLowerCase())
    .join(" "),
}));
