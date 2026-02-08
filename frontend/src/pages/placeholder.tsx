import { PageHeader } from "@/components/shared/page-header";

export function PoliciesPage() {
  return <PageHeader title="Policies" subtitle="Manage time-off policies" />;
}

export function PolicyDetailPage() {
  return <PageHeader title="Policy Detail" />;
}

export function EmployeesPage() {
  return <PageHeader title="Employees" subtitle="Manage employees" />;
}

export function EmployeeDetailPage() {
  return <PageHeader title="Employee Detail" />;
}

export function MyBalancesPage() {
  return <PageHeader title="My Balances" subtitle="View your time-off balances" />;
}

export function MyRequestsPage() {
  return <PageHeader title="My Requests" subtitle="View your time-off requests" />;
}

export function ApprovalsPage() {
  return <PageHeader title="Pending Approvals" subtitle="Review pending time-off requests" />;
}

export function HolidaysPage() {
  return <PageHeader title="Company Holidays" subtitle="Manage company holidays" />;
}

export function AuditLogPage() {
  return <PageHeader title="Audit Log" subtitle="View system audit trail" />;
}
