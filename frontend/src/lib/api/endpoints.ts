import type {
  AdjustmentCreate,
  AssignmentCreate,
  AuditLogEntry,
  BalanceSummary,
  Employee,
  EmployeeBalance,
  EmployeeUpsert,
  Holiday,
  HolidayCreate,
  LedgerEntry,
  PaginatedResponse,
  Policy,
  PolicyAssignment,
  PolicyCreate,
  PolicyUpdate,
  PolicyVersion,
  TimeOffRequest,
  TimeOffRequestCreate,
} from "./types";
import { apiClient } from "./client";

// ---------------------------------------------------------------------------
// Policies
// ---------------------------------------------------------------------------

export const policiesApi = {
  list(companyId: string, params?: Record<string, unknown>) {
    return apiClient.get<PaginatedResponse<Policy>>(`/companies/${companyId}/policies`, { params }).then((r) => r.data);
  },

  get(companyId: string, policyId: string) {
    return apiClient.get<Policy>(`/companies/${companyId}/policies/${policyId}`).then((r) => r.data);
  },

  create(companyId: string, data: PolicyCreate) {
    return apiClient.post<Policy>(`/companies/${companyId}/policies`, data).then((r) => r.data);
  },

  update(companyId: string, policyId: string, data: PolicyUpdate) {
    return apiClient.put<Policy>(`/companies/${companyId}/policies/${policyId}`, data).then((r) => r.data);
  },

  listVersions(companyId: string, policyId: string, params?: Record<string, unknown>) {
    return apiClient
      .get<PaginatedResponse<PolicyVersion>>(`/companies/${companyId}/policies/${policyId}/versions`, { params })
      .then((r) => r.data);
  },
};

// ---------------------------------------------------------------------------
// Assignments
// ---------------------------------------------------------------------------

export const assignmentsApi = {
  createForPolicy(companyId: string, policyId: string, data: AssignmentCreate) {
    return apiClient
      .post<PolicyAssignment>(`/companies/${companyId}/policies/${policyId}/assignments`, data)
      .then((r) => r.data);
  },

  listByPolicy(companyId: string, policyId: string, params?: Record<string, unknown>) {
    return apiClient
      .get<PaginatedResponse<PolicyAssignment>>(`/companies/${companyId}/policies/${policyId}/assignments`, { params })
      .then((r) => r.data);
  },

  listByEmployee(companyId: string, employeeId: string, params?: Record<string, unknown>) {
    return apiClient
      .get<
        PaginatedResponse<PolicyAssignment>
      >(`/companies/${companyId}/employees/${employeeId}/assignments`, { params })
      .then((r) => r.data);
  },

  endDate(companyId: string, assignmentId: string, effectiveTo?: string) {
    return apiClient
      .delete<PolicyAssignment>(`/companies/${companyId}/assignments/${assignmentId}`, {
        params: effectiveTo ? { effective_to: effectiveTo } : undefined,
      })
      .then((r) => r.data);
  },
};

// ---------------------------------------------------------------------------
// Balances
// ---------------------------------------------------------------------------

export const balancesApi = {
  getByEmployee(companyId: string, employeeId: string) {
    return apiClient
      .get<{ items: EmployeeBalance[]; total: number }>(`/companies/${companyId}/employees/${employeeId}/balances`)
      .then((r) => r.data.items);
  },

  getLedger(companyId: string, employeeId: string, policyId: string, params?: Record<string, unknown>) {
    return apiClient
      .get<
        PaginatedResponse<LedgerEntry>
      >(`/companies/${companyId}/employees/${employeeId}/ledger`, { params: { policy_id: policyId, ...params } })
      .then((r) => r.data);
  },
};

// ---------------------------------------------------------------------------
// Adjustments
// ---------------------------------------------------------------------------

export const adjustmentsApi = {
  create(companyId: string, data: AdjustmentCreate) {
    return apiClient.post<LedgerEntry>(`/companies/${companyId}/adjustments`, data).then((r) => r.data);
  },
};

// ---------------------------------------------------------------------------
// Requests
// ---------------------------------------------------------------------------

export const requestsApi = {
  submit(companyId: string, data: TimeOffRequestCreate) {
    return apiClient.post<TimeOffRequest>(`/companies/${companyId}/requests`, data).then((r) => r.data);
  },

  list(companyId: string, params?: Record<string, unknown>) {
    return apiClient
      .get<PaginatedResponse<TimeOffRequest>>(`/companies/${companyId}/requests`, { params })
      .then((r) => r.data);
  },

  get(companyId: string, requestId: string) {
    return apiClient.get<TimeOffRequest>(`/companies/${companyId}/requests/${requestId}`).then((r) => r.data);
  },

  approve(companyId: string, requestId: string, data?: Record<string, unknown>) {
    return apiClient
      .post<TimeOffRequest>(`/companies/${companyId}/requests/${requestId}/approve`, data)
      .then((r) => r.data);
  },

  deny(companyId: string, requestId: string, data?: Record<string, unknown>) {
    return apiClient
      .post<TimeOffRequest>(`/companies/${companyId}/requests/${requestId}/deny`, data)
      .then((r) => r.data);
  },

  cancel(companyId: string, requestId: string) {
    return apiClient.post<TimeOffRequest>(`/companies/${companyId}/requests/${requestId}/cancel`).then((r) => r.data);
  },
};

// ---------------------------------------------------------------------------
// Employees
// ---------------------------------------------------------------------------

export const employeesApi = {
  list(companyId: string) {
    return apiClient.get<Employee[]>(`/companies/${companyId}/employees`).then((r) => r.data);
  },

  get(companyId: string, employeeId: string) {
    return apiClient.get<Employee>(`/companies/${companyId}/employees/${employeeId}`).then((r) => r.data);
  },

  upsert(companyId: string, employeeId: string, data: EmployeeUpsert) {
    return apiClient.put<Employee>(`/companies/${companyId}/employees/${employeeId}`, data).then((r) => r.data);
  },
};

// ---------------------------------------------------------------------------
// Holidays
// ---------------------------------------------------------------------------

export const holidaysApi = {
  list(companyId: string, params?: Record<string, unknown>) {
    return apiClient
      .get<PaginatedResponse<Holiday>>(`/companies/${companyId}/holidays`, { params })
      .then((r) => r.data);
  },

  create(companyId: string, data: HolidayCreate) {
    return apiClient.post<Holiday>(`/companies/${companyId}/holidays`, data).then((r) => r.data);
  },

  delete(companyId: string, holidayId: string) {
    return apiClient.delete<void>(`/companies/${companyId}/holidays/${holidayId}`).then((r) => r.data);
  },
};

// ---------------------------------------------------------------------------
// Reports
// ---------------------------------------------------------------------------

export const reportsApi = {
  auditLog(companyId: string, params?: Record<string, unknown>) {
    return apiClient
      .get<PaginatedResponse<AuditLogEntry>>(`/companies/${companyId}/audit-log`, { params })
      .then((r) => r.data);
  },

  balanceSummary(companyId: string) {
    return apiClient.get<BalanceSummary[]>(`/companies/${companyId}/reports/balances`).then((r) => r.data);
  },

  ledgerExport(companyId: string, params?: Record<string, unknown>) {
    return apiClient.get<LedgerEntry[]>(`/companies/${companyId}/reports/ledger`, { params }).then((r) => r.data);
  },
};
