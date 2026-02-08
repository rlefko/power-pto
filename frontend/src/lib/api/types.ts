// ---------------------------------------------------------------------------
// Enum types (mirroring backend enums)
// ---------------------------------------------------------------------------

export type PolicyCategory = "VACATION" | "SICK" | "PERSONAL" | "BEREAVEMENT" | "PARENTAL" | "OTHER";

export type PolicyType = "UNLIMITED" | "ACCRUAL";

export type AccrualMethod = "TIME" | "HOURS_WORKED";

export type AccrualFrequency = "DAILY" | "MONTHLY" | "YEARLY";

export type AccrualTiming = "START_OF_PERIOD" | "END_OF_PERIOD";

export type ProrationMethod = "DAYS_ACTIVE" | "NONE";

export type RequestStatus = "DRAFT" | "SUBMITTED" | "APPROVED" | "DENIED" | "CANCELLED";

export type LedgerEntryType = "ACCRUAL" | "HOLD" | "HOLD_RELEASE" | "USAGE" | "ADJUSTMENT" | "EXPIRATION" | "CARRYOVER";

export type LedgerSourceType = "REQUEST" | "PAYROLL" | "ADMIN" | "SYSTEM";

export type DisplayUnit = "MINUTES" | "HOURS" | "DAYS";

// ---------------------------------------------------------------------------
// Generic pagination wrapper
// ---------------------------------------------------------------------------

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
}

// ---------------------------------------------------------------------------
// Policy types
// ---------------------------------------------------------------------------

export interface TenureTier {
  min_months: number;
  accrual_rate_minutes: number;
}

export interface CarryoverSettings {
  enabled: boolean;
  cap_minutes: number | null;
  expires_after_days: number | null;
}

export interface ExpirationSettings {
  enabled: boolean;
  expires_after_days: number | null;
  expires_on_month: number | null;
  expires_on_day: number | null;
}

export interface AccrualRatio {
  accrue_minutes: number;
  per_worked_minutes: number;
}

export interface UnlimitedSettings {
  type: "UNLIMITED";
  unit: DisplayUnit;
}

export interface TimeAccrualSettings {
  type: "ACCRUAL";
  accrual_method: "TIME";
  unit: DisplayUnit;
  accrual_frequency: AccrualFrequency;
  accrual_timing: AccrualTiming;
  rate_minutes_per_year: number | null;
  rate_minutes_per_month: number | null;
  rate_minutes_per_day: number | null;
  proration: ProrationMethod;
  allow_negative: boolean;
  negative_limit_minutes: number | null;
  bank_cap_minutes: number | null;
  tenure_tiers: TenureTier[];
  carryover: CarryoverSettings;
  expiration: ExpirationSettings;
}

export interface HoursWorkedAccrualSettings {
  type: "ACCRUAL";
  accrual_method: "HOURS_WORKED";
  unit: DisplayUnit;
  accrual_ratio: AccrualRatio;
  allow_negative: boolean;
  negative_limit_minutes: number | null;
  bank_cap_minutes: number | null;
  tenure_tiers: TenureTier[];
  carryover: CarryoverSettings;
  expiration: ExpirationSettings;
}

export type PolicySettings = UnlimitedSettings | TimeAccrualSettings | HoursWorkedAccrualSettings;

export interface PolicyVersionInput {
  effective_from: string;
  settings: PolicySettings;
  change_reason?: string | null;
}

export interface PolicyCreate {
  key: string;
  category: PolicyCategory;
  version: PolicyVersionInput;
}

export interface PolicyUpdate {
  version: PolicyVersionInput;
}

export interface PolicyVersion {
  id: string;
  policy_id: string;
  version: number;
  effective_from: string;
  effective_to: string | null;
  type: PolicyType;
  accrual_method: AccrualMethod | null;
  settings: PolicySettings;
  created_by: string;
  change_reason: string | null;
  created_at: string;
}

export interface Policy {
  id: string;
  company_id: string;
  key: string;
  category: PolicyCategory;
  created_at: string;
  current_version: PolicyVersion | null;
}

// ---------------------------------------------------------------------------
// Assignment types
// ---------------------------------------------------------------------------

export interface AssignmentCreate {
  employee_id: string;
  effective_from: string;
  effective_to?: string | null;
}

export interface PolicyAssignment {
  id: string;
  company_id: string;
  employee_id: string;
  policy_id: string;
  effective_from: string;
  effective_to: string | null;
  created_by: string;
  created_at: string;
}

// ---------------------------------------------------------------------------
// Balance types
// ---------------------------------------------------------------------------

export interface EmployeeBalance {
  policy_id: string;
  policy_key: string;
  policy_category: string;
  accrued_minutes: number;
  used_minutes: number;
  held_minutes: number;
  available_minutes: number | null;
  is_unlimited: boolean;
  updated_at: string | null;
}

// ---------------------------------------------------------------------------
// Ledger types
// ---------------------------------------------------------------------------

export interface LedgerEntry {
  id: string;
  policy_id: string;
  policy_version_id: string;
  entry_type: LedgerEntryType;
  amount_minutes: number;
  effective_at: string;
  source_type: LedgerSourceType;
  source_id: string;
  metadata_json: Record<string, unknown> | null;
  created_at: string;
}

// ---------------------------------------------------------------------------
// Adjustment types
// ---------------------------------------------------------------------------

export interface AdjustmentCreate {
  employee_id: string;
  policy_id: string;
  amount_minutes: number;
  reason: string;
}

// ---------------------------------------------------------------------------
// Request types
// ---------------------------------------------------------------------------

export interface TimeOffRequestCreate {
  employee_id: string;
  policy_id: string;
  start_at: string;
  end_at: string;
  reason?: string | null;
  idempotency_key?: string | null;
}

export interface TimeOffRequest {
  id: string;
  company_id: string;
  employee_id: string;
  policy_id: string;
  start_at: string;
  end_at: string;
  requested_minutes: number;
  reason: string | null;
  status: RequestStatus;
  submitted_at: string | null;
  decided_at: string | null;
  decided_by: string | null;
  decision_note: string | null;
  idempotency_key: string | null;
  created_at: string;
}

// ---------------------------------------------------------------------------
// Employee types
// ---------------------------------------------------------------------------

export interface EmployeeUpsert {
  first_name: string;
  last_name: string;
  email: string;
  pay_type?: string;
  workday_minutes?: number;
  timezone?: string;
  hire_date?: string | null;
}

export interface Employee {
  id: string;
  company_id: string;
  first_name: string;
  last_name: string;
  email: string;
  pay_type: string;
  workday_minutes: number;
  timezone: string;
  hire_date: string | null;
}

// ---------------------------------------------------------------------------
// Holiday types
// ---------------------------------------------------------------------------

export interface HolidayCreate {
  date: string;
  name: string;
}

export interface Holiday {
  id: string;
  company_id: string;
  date: string;
  name: string;
}

// ---------------------------------------------------------------------------
// Audit & report types
// ---------------------------------------------------------------------------

export interface AuditLogEntry {
  id: string;
  company_id: string;
  actor_id: string;
  entity_type: string;
  entity_id: string;
  action: string;
  before_json: Record<string, unknown> | null;
  after_json: Record<string, unknown> | null;
  created_at: string;
}

export interface BalanceSummary {
  employee_id: string;
  policy_id: string;
  policy_key: string;
  policy_category: string;
  accrued_minutes: number;
  used_minutes: number;
  held_minutes: number;
  available_minutes: number | null;
  is_unlimited: boolean;
}
