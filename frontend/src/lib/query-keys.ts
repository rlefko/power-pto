export const queryKeys = {
  policies: {
    all: (companyId: string) => ["policies", companyId] as const,
    detail: (companyId: string, policyId: string) => ["policies", companyId, policyId] as const,
    versions: (companyId: string, policyId: string) => ["policies", companyId, policyId, "versions"] as const,
  },
  assignments: {
    byPolicy: (companyId: string, policyId: string) => ["assignments", companyId, "policy", policyId] as const,
    byEmployee: (companyId: string, employeeId: string) => ["assignments", companyId, "employee", employeeId] as const,
  },
  balances: {
    byEmployee: (companyId: string, employeeId: string) => ["balances", companyId, employeeId] as const,
  },
  ledger: {
    byEmployeePolicy: (companyId: string, employeeId: string, policyId: string) =>
      ["ledger", companyId, employeeId, policyId] as const,
  },
  requests: {
    all: (companyId: string, filters?: Record<string, string>) => ["requests", companyId, filters] as const,
    detail: (companyId: string, requestId: string) => ["requests", companyId, requestId] as const,
  },
  employees: {
    all: (companyId: string) => ["employees", companyId] as const,
    detail: (companyId: string, employeeId: string) => ["employees", companyId, employeeId] as const,
  },
  holidays: {
    all: (companyId: string, year?: number) => ["holidays", companyId, year] as const,
  },
  auditLog: {
    all: (companyId: string, filters?: Record<string, unknown>) => ["audit-log", companyId, filters] as const,
  },
  reports: {
    balances: (companyId: string) => ["reports", "balances", companyId] as const,
  },
};
