import { createBrowserRouter, Navigate } from "react-router";
import { RootLayout } from "@/components/layout/root-layout";
import { ErrorFallback } from "@/components/shared/error-fallback";
import { PoliciesPage } from "@/features/policies/pages/policies-page";
import { PolicyDetailPage } from "@/features/policies/pages/policy-detail-page";
import { MyBalancesPage } from "@/features/balances/pages/my-balances-page";
import { MyRequestsPage } from "@/features/requests/pages/my-requests-page";
import { ApprovalsPage } from "@/features/requests/pages/approvals-page";
import { EmployeesPage } from "@/features/employees/pages/employees-page";
import { EmployeeDetailPage } from "@/features/employees/pages/employee-detail-page";
import { HolidaysPage } from "@/features/holidays/pages/holidays-page";
import { AuditLogPage } from "@/features/audit/pages/audit-log-page";

export const router = createBrowserRouter([
  {
    path: "/",
    element: <RootLayout />,
    errorElement: <ErrorFallback />,
    children: [
      { index: true, element: <Navigate to="/balances" replace /> },
      { path: "policies", element: <PoliciesPage /> },
      { path: "policies/:policyId", element: <PolicyDetailPage /> },
      { path: "employees", element: <EmployeesPage /> },
      { path: "employees/:employeeId", element: <EmployeeDetailPage /> },
      { path: "balances", element: <MyBalancesPage /> },
      { path: "requests", element: <MyRequestsPage /> },
      { path: "approvals", element: <ApprovalsPage /> },
      { path: "holidays", element: <HolidaysPage /> },
      { path: "audit-log", element: <AuditLogPage /> },
    ],
  },
]);
