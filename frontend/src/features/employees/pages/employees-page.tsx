import { useMemo } from "react";
import { useNavigate } from "react-router";
import type { ColumnDef } from "@tanstack/react-table";
import { Button } from "@/components/ui/button";
import { PageHeader } from "@/components/shared/page-header";
import { DataTable } from "@/components/shared/data-table";
import { EmptyState } from "@/components/shared/empty-state";
import { EmployeeFormDialog } from "../components/employee-form";
import { useEmployees } from "../hooks/use-employees";
import { useAuth } from "@/lib/auth/use-auth";
import type { Employee } from "@/lib/api/types";
import { formatDate } from "@/lib/utils/format";
import { extractErrorMessage } from "@/lib/api/client";
import { Plus } from "lucide-react";

export function EmployeesPage() {
  const { role } = useAuth();
  const isAdmin = role === "admin";
  const navigate = useNavigate();
  const { data: employees, isLoading, isError, error } = useEmployees();

  const columns = useMemo<ColumnDef<Employee, unknown>[]>(
    () => [
      {
        accessorKey: "first_name",
        header: "Name",
        cell: ({ row }) => (
          <button
            className="text-left font-medium hover:underline"
            onClick={() => navigate(`/employees/${row.original.id}`)}
          >
            {row.original.first_name} {row.original.last_name}
          </button>
        ),
      },
      {
        accessorKey: "email",
        header: "Email",
      },
      {
        accessorKey: "pay_type",
        header: "Pay Type",
        cell: ({ row }) => <span className="capitalize">{row.original.pay_type.toLowerCase()}</span>,
      },
      {
        accessorKey: "workday_minutes",
        header: "Workday",
        cell: ({ row }) => `${row.original.workday_minutes / 60}h`,
      },
      {
        accessorKey: "timezone",
        header: "Timezone",
      },
      {
        accessorKey: "hire_date",
        header: "Hire Date",
        cell: ({ row }) => (row.original.hire_date ? formatDate(row.original.hire_date) : "—"),
      },
    ],
    [navigate],
  );

  if (isError) {
    return (
      <div className="space-y-6">
        <PageHeader title="Employees" />
        <div className="text-center text-destructive">{extractErrorMessage(error)}</div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Employees"
        subtitle="Manage company employees"
        actions={
          isAdmin ? (
            <EmployeeFormDialog
              trigger={
                <Button size="sm">
                  <Plus className="mr-1 h-4 w-4" />
                  Add Employee
                </Button>
              }
            />
          ) : undefined
        }
      />

      {!isLoading && (!employees || employees.length === 0) ? (
        <EmptyState title="No employees" description="No employees have been added yet." />
      ) : (
        <DataTable
          columns={columns}
          data={employees ?? []}
          total={employees?.length ?? 0}
          isLoading={isLoading}
          emptyMessage="No employees found"
        />
      )}
    </div>
  );
}
