import { createBrowserRouter, Navigate } from "react-router";
import { RootLayout } from "@/components/layout/root-layout";
import { ErrorFallback } from "@/components/shared/error-fallback";
import { PoliciesPage } from "@/features/policies/pages/policies-page";
import { PolicyDetailPage } from "@/features/policies/pages/policy-detail-page";
import {
  EmployeesPage,
  EmployeeDetailPage,
  MyBalancesPage,
  MyRequestsPage,
  ApprovalsPage,
  HolidaysPage,
  AuditLogPage,
} from "@/pages/placeholder";

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
